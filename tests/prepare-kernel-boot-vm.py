#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Copy a stopped native VM and attach a read-only acceptance-source disk."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import mojt_artifact as artifact
import mojt_boot as boot
import mpm_deployment as deployment


def require(ok, message):
    if not ok:
        raise ValueError(message)


def prepare(image, output):
    require(os.geteuid() != 0, "run as the ordinary Debian VM owner, without sudo")
    image, output = image.resolve(strict=True), Path(os.path.abspath(output))
    require(not os.path.lexists(output) and output == output.resolve(), "output must be a new nonsymlink directory")
    require(image not in output.parents and output not in image.parents, "source/output must be separate")
    for command in ("cp", "fuser", "mkfs.ext4"):
        require(shutil.which(command), "missing host command: " + command + " (include /usr/sbin in PATH)")
    disk = image / "disk.img"
    require(disk.is_file() and not disk.is_symlink(), "native regular-file disk required")
    record = deployment.read_json(image / "deployment.json")
    deployment.validate_deployment(record)
    script = (image / "run-qemu.sh").read_text()
    require(script == boot.run_script(network=True), "source must use the known native serial VirtIO launcher")
    probe = subprocess.run(["fuser", "--", str(disk)], capture_output=True)
    require(probe.returncode == 1, "source disk is open, or the open-file check failed; stop its QEMU first")
    before = disk.stat()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".kernel-boot-lab-", dir=output.parent) as temporary:
        temporary = Path(temporary)
        result = temporary / "vm"
        result.mkdir()
        subprocess.run(["cp", "--reflink=auto", "--sparse=always", "--", str(disk), str(result / "disk.img")], check=True)
        after = disk.stat()
        require((before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), "source disk changed while copying")
        inputs = temporary / "inputs"
        (inputs / "source/tests").mkdir(parents=True)
        shutil.copytree(REPO / "tools", inputs / "source/tools", ignore=shutil.ignore_patterns("__pycache__"))
        runner = "run-kernel-boot-acceptance.py"
        shutil.copy2(REPO / "tests" / runner, inputs / "source/tests" / runner)
        inventory = {p.relative_to(inputs).as_posix(): artifact.file_sha(p)
                     for p in inputs.rglob("*") if p.is_file()}
        (inputs / "inventory.json").write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
        with (result / "inputs.img").open("xb") as stream:
            stream.truncate(64 * 1024**2)
        subprocess.run(["mkfs.ext4", "-q", "-F", "-L", "MOJT-KERNEL-LAB", "-d", str(inputs),
                        str(result / "inputs.img")], check=True)
        require(script.count("    -nic ") == 1, "unexpected network launcher shape")
        script = script.replace("    -nic ",
            '    -drive "file=$here/inputs.img,if=virtio,format=raw,readonly=on" \\\n    -nic ', 1)
        (result / "run-qemu.sh").write_text(script)
        (result / "run-qemu.sh").chmod(0o755)
        (result / "lab.json").write_text(json.dumps(dict(format="mojt-kernel-boot-lab-v1",
            initial_deployment=record["id"], input_inventory=artifact.digest(inventory),
            source_disk="copied; never attached by this launcher", purpose="same-release exact-artifact selection/rollback"),
            indent=2) + "\n")
        require(not os.path.lexists(output), "output appeared while preparing")
        result.rename(output)
    print("PASS: stopped source VM copied; original disk is not attached")
    print("PASS: acceptance source disk is attached read-only")
    print("READY:", output / "run-qemu.sh")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.image, args.output)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print("prepare-kernel-boot-vm: " + str(error), file=sys.stderr)
        raise SystemExit(1)
