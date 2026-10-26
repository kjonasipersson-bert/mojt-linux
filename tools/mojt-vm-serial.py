#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Create a private serial-console copy of a stopped, password-login UEFI VM.

Preserves the original image and all guest generations/state. Uses qemu-img,
debugfs and regular partition files; no host mounts or root privileges.
"""

import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


spec = importlib.util.spec_from_file_location("mojt_boot", Path(__file__).with_name("mojt_boot.py"))
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)

SERVICE = "/state/etc/systemd/system/mojt-serial-console.service"
WANTS = "/state/etc/systemd/system/mojt.target.wants"
LINK = WANTS + "/mojt-serial-console.service"
UNIT = """# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
[Unit]
Description=Mojt authenticated serial console
After=mojt-setup.service systemd-user-sessions.service

[Service]
ExecStart=/run/mojt-system/busybox getty -f /run/mojt/issue -l /run/mojt-system/login -L 115200 ttyS0 vt100
Restart=always
RestartSec=1
Environment=PATH=/run/mojt-system/bin:/usr/bin:/bin
StandardInput=tty
StandardOutput=tty
StandardError=journal
TTYPath=/dev/ttyS0
TTYReset=yes
TTYVHangup=yes

[Install]
WantedBy=mojt.target
"""
COMMANDS = ("qemu-img", "sfdisk", "debugfs", "e2fsck", "fallocate")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def regular(path):
    require(not path.is_symlink() and path.is_file(), f"expected regular file: {path}")
    return path


class Ext4:
    """Fixed guest paths and local relative dump names, never shell commands."""
    def __init__(self, image, work):
        self.image, self.work, self.counter = image, work, 0

    def run(self, command, write=False):
        args = ["debugfs"] + (["-w"] if write else []) + ["-R", command, str(self.image)]
        return subprocess.run(args, cwd=self.work, check=True, text=True,
                              capture_output=True).stdout

    def inode(self, path):
        text = self.run("stat " + path)
        found = re.search(r"Type:\s+(\w+)\s+Mode:\s+([0-7]+)", text)
        if found is None:
            return None
        return dict(kind=found[1], mode=int(found[2], 8), text=text)

    def directory(self, path, create=False):
        info = self.inode(path)
        if info is None and create:
            self.run("mkdir " + path, write=True)
            self.attributes(path, 0o40755)
            info = self.inode(path)
        require(info is not None and info["kind"] == "directory",
                f"guest path must be a real directory: {path}")

    def read(self, path):
        info = self.inode(path)
        require(info is not None and info["kind"] == "regular", f"unsafe guest file: {path}")
        size = re.search(r"\bSize:\s+(\d+)", info["text"])
        require(size is not None and int(size[1]) <= 65536, f"guest config too large: {path}")
        name = "dump-" + str(self.counter)
        self.counter += 1
        destination = self.work / name
        self.run(f"dump {path} {name}")
        require(destination.is_file(), f"cannot read guest file: {path}")
        return destination.read_bytes()

    def attributes(self, path, mode):
        for field, value in (("uid", "0"), ("gid", "0"), ("mode", f"0{mode:o}")):
            self.run(f"set_inode_field {path} {field} {value}", write=True)

    def write(self, path, data, replace=False):
        old = self.inode(path)
        if old is not None:
            require(old["kind"] == "regular", f"refusing linked/special guest config: {path}")
            if self.read(path) == data:
                return
            require(replace, f"conflicting guest configuration: {path}")
            self.run("rm " + path, write=True)
        name = "input-" + str(self.counter)
        self.counter += 1
        (self.work / name).write_bytes(data)
        self.run(f"write {name} {path}", write=True)
        self.attributes(path, 0o100644)
        require(self.read(path) == data, f"guest write verification failed: {path}")


def configure(image, work):
    fs = Ext4(image, work)
    fs.directory("/state")
    fs.directory("/state/etc")
    shadow = fs.inode("/state/etc/shadow")
    require(shadow is not None and shadow["kind"] == "regular" and
            not shadow["mode"] & 0o077, "source needs protected persistent shadow credentials")
    secure = "/state/etc/securetty"
    data = fs.read(secure) if fs.inode(secure) is not None else b""
    if "ttyS0" not in {line.strip() for line in data.decode("utf-8").splitlines()}:
        data += (b"\n" if data and not data.endswith(b"\n") else b"") + b"ttyS0\n"
        fs.write(secure, data, replace=True)
    for path in ("/state/etc/systemd", "/state/etc/systemd/system", WANTS):
        fs.directory(path, create=True)
    fs.write(SERVICE, UNIT.encode("ascii"))
    link = fs.inode(LINK)
    if link is None:
        fs.run(f"symlink {LINK} ../mojt-serial-console.service", write=True)
        link = fs.inode(LINK)
    require(link is not None and link["kind"] == "symlink" and
            'Fast link dest: "../mojt-serial-console.service"' in link["text"],
            "conflicting serial console enablement link")


def extract_partition(disk, destination, offset, length):
    """Read an exact extent into a new sparse regular file."""
    with disk.open("rb") as incoming, destination.open("xb") as outgoing:
        incoming.seek(offset)
        outgoing.truncate(length)
        remaining = length
        while remaining:
            data = incoming.read(min(boot.MIB, remaining))
            require(bool(data), "unexpected end of disk image")
            if data.strip(b"\0"):
                outgoing.write(data)
            else:
                outgoing.seek(len(data), 1)
            remaining -= len(data)


def prepare(source, output):
    source = source.resolve(strict=True)
    require(not output.is_symlink(), "refusing symlink output")
    output = output.resolve()
    require(not output.exists() and not output.is_symlink(), "refusing existing output")
    require(source != output and source not in output.parents and output not in source.parents,
            "source VM and output must be separate directories")
    for command in COMMANDS:
        require(shutil.which(command), f"missing host command: {command}")
    disk = regular(source / "disk.img")
    record = json.loads(regular(source / "build.json").read_text())
    require(record.get("format") == 1 and record.get("boot_mode") == "uefi" and
            record.get("login_mode") == "password", "requires a password-login Mojt UEFI build")
    entries = [record.get("boot_record"), *record.get("additional_boot_records", [])]
    require(all(isinstance(entry, dict) and entry.get("console") == "local" for entry in entries),
            "source must use local-console boot pairs; serial-only VMs already have a serial getty")
    parts = record["disk_layout"]
    offset, length = parts["root_offset"], parts["root_bytes"]
    require(type(offset) is int and type(length) is int and offset > 0 and length > 0 and
            offset % 4096 == 0 and length % 4096 == 0 and offset + length <= disk.stat().st_size,
            "invalid root partition extent")
    boot.fs_uuid(parts["root_uuid"])
    table = json.loads(subprocess.run(["sfdisk", "--json", str(disk)], check=True,
                                     capture_output=True, text=True).stdout)["partitiontable"]
    require(table["label"] == "gpt" and table.get("sectorsize") == 512 and
            any((p["start"] * 512, p["size"] * 512) == (offset, length) for p in table["partitions"]),
            "source GPT differs from recorded root extent")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mojt-serial-", dir=output.parent) as temp:
        work = Path(temp)
        result = work / "result"
        result.mkdir(mode=0o700)
        variables = source / "OVMF_VARS.fd"
        if variables.exists() or variables.is_symlink():
            shutil.copy2(regular(variables), result / variables.name)
            (result / variables.name).chmod(0o600)
        copy = result / "disk.img"
        # Default QEMU locking is required: never pass --force-share/-U.
        subprocess.run(["qemu-img", "convert", "-f", "raw", "-O", "raw", str(disk), str(copy)], check=True)
        copy.chmod(0o600)
        root = work / "root.ext4"
        extract_partition(copy, root, offset, length)
        subprocess.run(["e2fsck", "-f", "-n", str(root)], check=True, capture_output=True)
        fs = Ext4(root, work)
        require(parts["root_uuid"] in fs.run("stats"), "root filesystem UUID differs from build record")
        configure(root, work)
        subprocess.run(["e2fsck", "-f", "-n", str(root)], check=True, capture_output=True)
        # Clear this extent before sparse insertion, including old nonzero bytes.
        subprocess.run(["fallocate", "--punch-hole", "--keep-size", "--offset", str(offset),
                        "--length", str(length), str(copy)], check=True)
        boot.copy_partition(root, copy, offset, length)
        launcher = boot.run_script(network=record.get("system_step", 0) >= 2,
                                   local_console=bool(record.get("hardware")))
        launcher = launcher.replace('${QEMU_DISPLAY:-gtk}', '${QEMU_DISPLAY:-none}')
        (result / "run-qemu.sh").write_text(launcher, encoding="ascii")
        (result / "run-qemu.sh").chmod(0o755)
        record["serial_console_copy"] = dict(format=1, source=str(source), unit=SERVICE,
                                             credentials="retained", generations="retained")
        (result / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="ascii")
        require(not output.exists() and not output.is_symlink(), "output appeared during preparation")
        result.rename(output)
    print(f"Serial-console VM: {output}")
    print("Existing guest password and state retained; source VM unchanged.")
    print(f"Launch from the SSH terminal: {output / 'run-qemu.sh'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="stopped existing VM directory")
    parser.add_argument("--output", type=Path, required=True, help="new private output directory")
    args = parser.parse_args()
    try:
        prepare(args.source, args.output)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"mojt-vm-serial: {error}\n")


if __name__ == "__main__":
    main()
