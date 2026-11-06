#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Debian-host preparation of a private build VM and frozen input workspace.

Only new regular image files are written. Shut down the source VM first.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import uuid


def require(ok, message):
    if not ok:
        raise ValueError(message)


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def inventory(root):
    rows = {}
    pending = [Path(root)]
    while pending:
        path = pending.pop()
        info = path.lstat()
        name = path.relative_to(root).as_posix()
        mode = stat.S_IMODE(info.st_mode)
        if stat.S_ISLNK(info.st_mode):
            row = dict(kind="link", mode=mode, target=os.readlink(path))
        elif stat.S_ISDIR(info.st_mode):
            row = dict(kind="directory", mode=mode)
            pending.extend(sorted(path.iterdir(), reverse=True))
        elif stat.S_ISREG(info.st_mode):
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            row = dict(kind="file", mode=mode, sha256=digest)
        else:
            raise ValueError("unexpected special input file: " + str(path))
        rows[name] = row
    return rows


def patch_launcher(text):
    needle = "exec qemu-system-x86_64 \\\n"
    require(text.count(needle) == 1 and text.count("-m 1024 -smp 2") == 1,
            "source launcher differs from reviewed UEFI template")
    require("workspace.img" not in text, "source already has a workspace drive")
    return text.replace(needle, needle + '    -drive "file=$here/workspace.img,if=virtio,format=raw" \\\n').replace(
        "-m 1024 -smp 2", "-m 4096 -smp 2")


def prepare(args):
    require(os.geteuid() == 0, "run on the Debian host with sudo")
    for command in ("git", "cp", "qemu-img", "mkfs.ext4", "e2fsck"):
        require(shutil.which(command), "missing host tool: " + command)
    require(not os.path.lexists(args.output), "output must not exist")
    output = args.output.resolve()
    target, payload, source, vm = [p.resolve(strict=True) for p in
                                  (args.target, args.payload, args.source, args.vm)]
    require(not any(p == output or p in output.parents or output in p.parents for p in
                    (target, payload, source, vm)), "output and inputs must be separate")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", args.base), "invalid Base version")
    kernel, modules = args.kernel.resolve(strict=True), args.modules.resolve(strict=True)
    require(kernel.is_file() and kernel.name.startswith("vmlinuz-") and modules.is_dir(), "invalid kernel inputs")
    release = kernel.name.removeprefix("vmlinuz-")
    require(modules.name == release, "kernel and module release differ")
    require(args.workspace_gib >= 32, "workspace must be at least 32 GiB")
    require((target / ".install-lock").is_file(), "target has no installation lock")
    for path in (target / "base" / args.base, target / "state", target / "releases" / f"base-{args.base}.toml",
                 payload / "system.json", vm / "disk.img", vm / "run-qemu.sh", vm / "build.json"):
        require(path.exists() and not path.is_symlink(), "missing or linked input: " + str(path))
    launcher = patch_launcher((vm / "run-qemu.sh").read_text())
    git = ["git", "-c", "safe.directory=" + str(source), "-C", source]
    require(not run(*git, "status", "--porcelain", capture_output=True, text=True).stdout.strip(), "source checkout must be clean")
    revision = run(*git, "rev-parse", "HEAD", capture_output=True, text=True).stdout.strip()
    output.mkdir(parents=True, mode=0o700)
    (output / ".preparing").write_text("Incomplete workspace preparation\n")
    owner = (int(os.environ.get("SUDO_UID", "0")), int(os.environ.get("SUDO_GID", "0")))
    stage = output / "staging"
    inputs = stage / "inputs"
    inputs.mkdir(parents=True)
    private = output / "vm"
    private.mkdir()
    # QEMU's source locking rejects a live writer; never use force-share.
    run("qemu-img", "convert", "-f", "raw", "-O", "raw", vm / "disk.img", private / "disk.img")
    for name in ("build.json", "OVMF_VARS.fd"):
        if (vm / name).exists():
            shutil.copy2(vm / name, private / name)
    (private / "run-qemu.sh").write_text(launcher)
    (private / "run-qemu.sh").chmod(0o755)
    with (target / ".install-lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        base = inputs / "base-target"
        (base / "base").mkdir(parents=True)
        (base / "releases").mkdir()
        for a,b in ((target / "base" / args.base, base / "base" / args.base),
                    (target / "state", base / "state"),
                    (target / "releases" / f"base-{args.base}.toml", base / "releases" / f"base-{args.base}.toml")):
            run("cp", "-a", "--", a, b)
        (base / "base/current").symlink_to(args.base)
        (base / ".install-lock").touch()
    run("cp", "-a", "--", payload, inputs / "system-payload")
    (inputs / "kernel/lib/modules").mkdir(parents=True)
    shutil.copy2(kernel, inputs / "kernel" / kernel.name)
    run("cp", "-a", "--", modules, inputs / "kernel/lib/modules" / release)
    archive = output / "source.tar"
    run(*git, "archive", "--format=tar", "--output=" + str(archive), revision)
    (inputs / "source").mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(inputs / "source", filter="data")
    archive.unlink()
    (stage / "output").mkdir()
    record = dict(format="mojt-build-inputs-v1", revision=revision, base=args.base,
                  kernel_release=release, workspace_uuid=str(uuid.uuid4()), inventory=inventory(inputs))
    (stage / "inputs.json").write_text(json.dumps(record, indent=2) + "\n")
    (output / "inputs.json").write_text(json.dumps(record, indent=2) + "\n")
    workspace = private / "workspace.img"
    with workspace.open("xb") as stream:
        stream.truncate(args.workspace_gib * 1024**3)
    run("mkfs.ext4", "-F", "-q", "-L", "MOJT-BUILD", "-U", record["workspace_uuid"], "-d", stage, workspace)
    run("e2fsck", "-f", "-n", workspace)
    for path in [output, private, output / "inputs.json", *private.iterdir()]:
        os.chown(path, *owner)
    for path in (private / "disk.img", workspace, private / "OVMF_VARS.fd"):
        if path.exists(): path.chmod(0o600)
    (output / ".preparing").unlink()
    print("READY: " + str(private / "run-qemu.sh"))
    print("Workspace UUID: " + record["workspace_uuid"])
    print("Frozen input inventory: " + str(output / "inputs.json"))
    print("Source VM unchanged; private VM has 4 GiB RAM and a separate workspace disk.")


def verify(workspace):
    workspace = Path(workspace)
    record = json.loads((workspace / "inputs.json").read_text())
    require(record.get("format") == "mojt-build-inputs-v1", "unsupported frozen input format")
    require(inventory(workspace / "inputs") == record["inventory"], "frozen input inventory differs")
    print("PASS: frozen Base/System/kernel/source inputs match their inventory")
    print("Source revision: " + record["revision"])
    print("Base: " + record["base"] + "; kernel: " + record["kernel_release"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--verify", type=Path, help="verify an existing mounted workspace; no host preparation")
    for flag in ("target", "payload", "source", "vm", "kernel", "modules", "output"):
        p.add_argument("--" + flag, type=Path)
    p.add_argument("--base", default="0.1.3")
    p.add_argument("--workspace-gib", type=int, default=64)
    args = p.parse_args()
    try:
        if args.verify:
            verify(args.verify)
        else:
            require(all(getattr(args, name) is not None for name in
                        ("target", "payload", "source", "vm", "kernel", "modules", "output")), "all host preparation paths are required")
            prepare(args)
    except (ValueError, OSError, subprocess.CalledProcessError, tarfile.TarError) as error:
        p.exit(1, "mojt-build-workspace: " + str(error) + "\nIncomplete outputs are retained; use a new output directory on retry.\n")


if __name__ == "__main__":
    main()
