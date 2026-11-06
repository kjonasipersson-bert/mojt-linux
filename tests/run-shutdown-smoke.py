#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Boot a synthetic native-layout disk with host systemd and real shutdown.

No Nix or full Mojt userspace acceptance: use this to reproduce mapped-file
holders, umount.target and the final static exitrd on a disposable regular file.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import mojt_system as system
import mpm_kernel_boot as manager


def command(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def copy_binary(root, path):
    path = Path(path)
    target = root / path.relative_to("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    target.chmod(0o755)
    libraries = command("ldd", path, capture_output=True, text=True).stdout
    for library in set(re.findall(r"(?:=> )?(/[A-Za-z0-9_./+:-]+)", libraries)):
        source = Path(library)
        destination = root / source.relative_to("/")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(0o755)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--modules-dir", type=Path, required=True)
    parser.add_argument("--busybox", type=Path, default=Path("/usr/bin/busybox"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--legacy", action="store_true", help="expect the old early unmount failure")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run this disposable-disk fixture as root")
    output = args.output.absolute()
    output.mkdir(mode=0o700)
    tree = output / "tree"
    base = tree / "base/probe-base"
    for name in ("usr/bin", "usr/lib", "lib64", "etc", "var", "home", "root", "nix", "run", "dev", "proc", "sys", "tmp"):
        (base / name).mkdir(parents=True)
    (base / "bin").symlink_to("usr/bin")
    (base / "lib").symlink_to("usr/lib")
    (tree / "base/current").symlink_to("probe-base")
    (tree / "releases").mkdir()
    (tree / "releases/base-probe-base.toml").write_text("format=1\n")
    for name in ("etc", "var", "home", "root"):
        (tree / "state" / name).mkdir(parents=True)
    (tree / "state/etc/hostname").write_text("mojt-shutdown-probe\n")
    (tree / "state/etc/passwd").write_text("root:x:0:0:root:/root:/bin/sh\n")
    (tree / "state/etc/group").write_text("root:x:0:\n")
    (tree / "state/etc/machine-id").write_text("0123456789abcdef0123456789abcdef\n")
    (tree / "state/etc/systemd").mkdir()
    (tree / "state/etc/systemd/journald.conf").write_text("[Journal]\nStorage=persistent\n")
    (tree / "state/var/log/journal").mkdir(parents=True)
    (tree / "nix").mkdir()
    profile = tree / "system/probe-system"
    units = profile / "units"
    units.mkdir(parents=True)
    (tree / "system/current").symlink_to("probe-system")
    (profile / "version").write_text("probe-system\n")
    (profile / "assembled-at-utc").write_text("synthetic-shutdown-test\n")
    shutil.copyfile(args.busybox, base / "usr/bin/busybox")
    (base / "usr/bin/busybox").chmod(0o755)
    (base / "usr/bin/sh").symlink_to("busybox")
    for name in ("systemd", "systemd-shutdown", "systemd-journald", "systemd-executor"):
        copy_binary(base, Path("/usr/lib/systemd") / name)
    (base / "usr/lib/os-release").write_text('ID=mojt-shutdown-fixture\nPRETTY_NAME="Mojt shutdown test fixture"\n')
    copy_binary(base, Path("/usr/bin/systemctl"))
    for name in ("mount", "umount"):
        copy_binary(base, Path(shutil.which(name)))
    vendor = Path("/usr/lib/systemd/system")
    for name in ("systemd-journald.service", "systemd-journald.socket", "systemd-journald-dev-log.socket",
                 "systemd-poweroff.service", "poweroff.target", "shutdown.target", "umount.target", "final.target"):
        shutil.copyfile(vendor / name, units / name)
    for name in ("sysinit.target", "basic.target", "sockets.target"):
        (units / name).write_text("[Unit]\nDefaultDependencies=no\n")
    (units / "probe.target").write_text("[Unit]\nDefaultDependencies=no\nWants=holder.service controller.service\n")
    (units / "holder.service").write_text("[Unit]\nDefaultDependencies=no\nBefore=sysinit.target\n"
        "[Service]\nExecStart=/run/mojt-system/holder\nStandardOutput=tty\nTTYPath=/dev/ttyS0\n")
    (units / "controller.service").write_text("[Unit]\nAfter=holder.service systemd-journald.service\n"
        "Requires=holder.service systemd-journald.service\n[Service]\nType=oneshot\n"
        "ExecStart=/bin/sh /controller\nStandardOutput=tty\nStandardError=tty\nTTYPath=/dev/ttyS0\n")
    (base / "controller").write_text("#!/bin/sh\nset -eu\n/bin/busybox sleep 2\n"
        "/usr/bin/systemctl kill --signal=USR1 systemd-journald.service\n/bin/busybox sleep 1\n"
        "/usr/bin/systemctl is-active --quiet holder.service\n"
        "hp=$(/usr/bin/systemctl show --value -p MainPID holder.service)\n"
        "/bin/busybox grep -E '/run/mojt-system/hwdb.bin|/usr/lib/modules/modules.dep.bin|/var/held.journal' /proc/$hp/maps\n"
        "jp=$(/usr/bin/systemctl show --value -p MainPID systemd-journald.service)\n"
        "/bin/busybox grep '/var/log/journal/' /proc/$jp/maps\n"
        "/usr/bin/systemctl show --no-pager 'run-mojt\\x2dsystem.mount' usr-lib-modules.mount var.mount -p Id -p DefaultDependencies\n"
        "echo MOJT_SHUTDOWN_HOLDERS_READY\n/usr/bin/systemctl --no-block poweroff\n")
    (profile / "start").write_text("#!/bin/sh\nexport SYSTEMD_UNIT_PATH=/run/systemd/system:/run/mojt-system/units\n"
        "export SYSTEMD_GENERATOR_PATH=/run/mojt-system/empty\nexport SYSTEMD_ENVIRONMENT_GENERATOR_PATH=/run/mojt-system/empty\n"
        "exec /usr/lib/systemd/systemd --system --unit=probe.target\n")
    (profile / "start").chmod(0o755)
    (profile / "empty").mkdir()
    (profile / "hwdb.bin").write_bytes(b"x" * 4096)
    (base / "usr/lib/modules").mkdir()
    modules = tree / "native-modules"
    modules.mkdir()
    (modules / "modules.dep.bin").write_bytes(b"x" * 4096)
    source = output / "holder.c"
    source.write_text('#include <sys/mman.h>\n#include <fcntl.h>\n#include <unistd.h>\n'
        'int main(void) { const char *p[]={"/run/mojt-system/hwdb.bin", "/usr/lib/modules/modules.dep.bin", "/var/held.journal"};'
        'for (int i=0;i<3;i++) { int fd=open(p[i],i==2 ? O_RDWR|O_CREAT : O_RDONLY,0600); if(fd<0)return 1;'
        'if(i==2 && ftruncate(fd,4096)<0)return 2; if(mmap(0,4096,PROT_READ|(i==2?PROT_WRITE:0),MAP_SHARED,fd,0)==MAP_FAILED)return 3; }'
        'for(;;)pause(); }\n')
    command("gcc", "-O2", source, "-o", profile / "holder")
    # holder only needs libc, already included by systemd's closure.
    vm = manager.vm_module()
    release = vm.kernel_release_from_path(args.kernel)
    early = vm.module_paths(release, args.modules_dir)
    script = system.init_script(vm.INIT)
    if args.legacy:
        script = script.replace(system.shutdown_mount_policy(), "")
    script = script.replace('mount --bind /sysroot/nix /newroot/nix || panic "cannot attach Nix store"',
        'mount --bind /sysroot/nix /newroot/nix || panic "cannot attach Nix store"\n'
        'mount --bind /sysroot/native-modules /newroot/usr/lib/modules || panic "cannot attach probe modules"')
    shutdown = system.SHUTDOWN
    if args.legacy:
        shutdown = '#!/bin/sh\nPATH=/bin\nexport PATH\nbusybox sync\nbusybox umount -a -r\nbusybox sync\nexec busybox poweroff -f\n'
    # Serialize real character-device headers without needing host CAP_MKNOD.
    nodes = {}
    original_stat = Path.lstat
    def node(path, mode, device):
        path.touch()
        nodes[path] = (mode, device)
    def info(path):
        if path not in nodes:
            return original_stat(path)
        mode, device = nodes[path]
        return SimpleNamespace(st_mode=mode, st_uid=0, st_gid=0, st_size=0, st_rdev=device)
    with mock.patch.object(vm.os, "mknod", side_effect=node), mock.patch.object(Path, "lstat", info):
        initramfs = vm.make_initramfs(output / "initroot", args.busybox, early, script, shutdown,
                                     archive_writer=manager.write_initramfs)
    (output / "initramfs.gz").write_bytes(initramfs)
    disk = output / "disk.img"
    with disk.open("xb") as stream:
        stream.truncate(256 * 1024**2)
    command("mkfs.ext4", "-q", "-F", "-d", tree, disk)
    env = dict(os.environ, SYSTEMD_LOG_LEVEL="info")
    launch = ["qemu-system-x86_64", "-machine", "q35,accel=tcg", "-m", "512", "-smp", "2",
        "-kernel", str(args.kernel), "-initrd", str(output / "initramfs.gz"),
        "-append", "console=ttyS0,115200 rdinit=/init panic=1", "-drive", f"file={disk},if=virtio,format=raw",
        "-nic", "none", "-display", "none", "-serial", "stdio", "-no-reboot"]
    with (output / "serial.log").open("wb") as serial:
        try:
            result = subprocess.run(launch, env=env, stdout=serial, stderr=subprocess.STDOUT, timeout=90)
        except subprocess.TimeoutExpired as error:
            raise ValueError("shutdown fixture timed out; inspect serial.log") from error
    text = (output / "serial.log").read_text(errors="replace")
    if result.returncode != 0 or "reboot: Power down" not in text:
        raise ValueError("fixture did not power off normally; inspect serial.log")
    if "MOJT_SHUTDOWN_HOLDERS_READY" not in text:
        raise ValueError("probe did not reach systemd shutdown; inspect serial.log")
    for path in ("/run/mojt-system/hwdb.bin", "/usr/lib/modules/modules.dep.bin", "/var/held.journal", "/var/log/journal/"):
        if path not in text:
            raise ValueError("expected mapped-file holder not observed: " + path)
    if args.legacy:
        journal = output / "legacy.journal"
        destination = str(journal).replace("\\", "\\\\").replace('"', '\\"')
        command("debugfs", "-R", 'dump /state/var/log/journal/0123456789abcdef0123456789abcdef/system.journal "' +
                destination + '"', disk, capture_output=True)
        report = command("journalctl", "--file", journal, "--no-pager", "-u", "run-mojt\\x2dsystem.mount",
                         "-u", "usr-lib-modules.mount", "-u", "var.mount", text=True, capture_output=True).stdout
        (output / "unmount-journal.log").write_text(report)
        if "target is busy" not in report or "Failed unmounting" not in text:
            raise ValueError("legacy probe did not reproduce mapped-file unmount failure")
        print("PASS: reproduced legacy mapped-file unmount failure")
    else:
        if ("Mojt shutdown: old root and backing filesystem fully unmounted" not in text or
                "target is busy" in text or "Failed unmounting" in text or "Mojt shutdown: ERROR" in text):
            raise ValueError("corrected shutdown did not release mounts cleanly; inspect serial.log")
        if text.count("DefaultDependencies=no") < 3:
            raise ValueError("PID 1 did not load runtime mount policy")
        check = command("e2fsck", "-fn", disk, capture_output=True, text=True)
        (output / "ext4-check.log").write_text(check.stdout + check.stderr)
        print("PASS: real systemd shutdown, static exitrd unmount and offline ext4 check")
    print("Evidence:", output / "serial.log")


if __name__ == "__main__":
    main()
