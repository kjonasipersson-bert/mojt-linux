#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Stage only the running System's three privileged ELF files in private tmpfs."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

NAMES = {"sudo", "passwd", "unix_chkpwd"}


def verified_inputs(record):
    if set(record) != NAMES:
        raise ValueError("unexpected privileged helper selection")
    for name, item in record.items():
        source = item["source"]
        if (set(item) != {"source", "sha256"} or
                not re.fullmatch(r"/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[^/]+/(bin|sbin)/[a-z_]+", source) or
                not source.endswith("/" + name) or
                not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])):
            raise ValueError("unsafe privileged helper source")
    result = {}
    for name, item in record.items():
        data = Path(item["source"]).read_bytes()
        if not data.startswith(b"\x7fELF") or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("privileged helper integrity mismatch: " + name)
        result[name] = data
    return result


def stage_helpers(data, directory):
    for name in NAMES:
        fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data[name])
            stream.flush()
            os.fchown(stream.fileno(), 0, 0)


def main():
    if os.geteuid() != 0:
        raise ValueError("privileged setup requires root")
    profile = Path("/run/mojt-system")
    data = verified_inputs(json.loads((profile / "privileged-inputs.json").read_text()))
    mounts = {line.split()[4]: line.split()[3] for line in Path("/proc/self/mountinfo").read_text().splitlines()}
    if any(mounts.get("/" + name) != "/state/" + name for name in ("home", "root")):
        raise ValueError("persistent homes must be mounted before account setup")
    destination = Path("/run/mojt-privileged")
    if os.path.lexists(destination):
        raise ValueError("privileged runtime already exists; reboot to reconstruct it")
    destination.mkdir(mode=0o755)
    subprocess.run([str(profile / "busybox"), "mount", "-t", "tmpfs", "-o",
                    "mode=0755,nodev,suid,exec", "tmpfs", str(destination)], check=True)
    try:
        stage_helpers(data, destination)
        subprocess.run([str(profile / "bin/visudo"), "-c", "-f", "/etc/sudoers"], check=True)
        wrappers = Path("/run/wrappers")
        if os.path.lexists(wrappers):
            raise ValueError("unexpected existing PAM wrapper directory")
        (wrappers / "bin").mkdir(parents=True, mode=0o755)
        (wrappers / "bin/unix_chkpwd").symlink_to(destination / "unix_chkpwd")
        for name in NAMES:
            (destination / name).chmod(0o4755)
    except BaseException:
        for name in NAMES:
            path = destination / name
            if path.exists() and not path.is_symlink():
                path.chmod(0o600)
        subprocess.run([str(profile / "busybox"), "umount", str(destination)], check=False)
        raise


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        raise SystemExit("mojt privileged setup: " + str(error))
