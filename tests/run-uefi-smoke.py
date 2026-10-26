#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real firmware/disk boot probe with a synthetic static guest, not Mojt service acceptance."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import tempfile
import time
import uuid


def load_vm():
    spec = importlib.util.spec_from_file_location("mojt_uefi_smoke_vm",
                Path(__file__).resolve().parents[1] / "tools/mojt-vm-build.py")
    vm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vm)
    return vm


def firmware_boot(launcher, env, index=None, login=None):
    """Select a real GRUB menu entry over its serial terminal when requested."""
    if index is None:
        return subprocess.run(["bash", str(launcher)], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=90, env=env)
    process = subprocess.Popen(["bash", str(launcher)], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    output, chosen = bytearray(), False
    login_step, password_end = 0, 0
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                for key, unused in selector.select(timeout=1):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        process.wait(timeout=5)
                        if not chosen:
                            output.extend(b"\nMOJT_GRUB_MENU_NOT_OBSERVED\n")
                        return subprocess.CompletedProcess(process.args, process.returncode, bytes(output))
                    output.extend(chunk)
                if not chosen and b"Use the" in output:
                    process.stdin.write(b"\x1b[B" * index + b"\r")
                    process.stdin.flush()
                    chosen = True
                if login is not None and chosen:
                    if login_step == 0 and b"mojt-smoke login:" in output:
                        process.stdin.write(b"root\n")
                        process.stdin.flush()
                        login_step = 1
                    elif login_step == 1 and b"Password:" in output:
                        process.stdin.write(login.encode() + b"\n")
                        process.stdin.flush()
                        password_end = len(output)
                        login_step = 2
                    elif login_step == 2 and b"# " in output[password_end:]:
                        process.stdin.write(
                            b'[ "$(/run/mojt-system/busybox id -u)" = 0 ] && '
                            b'[ "$(cat /etc/uefi-smoke-marker)" = retained ] && '
                            b'[ "$(cat /var/uefi-smoke-marker)" = retained ] && '
                            b'echo MOJT_SERIAL_LOGIN_PASS\n'
                            b'/run/mojt-system/busybox sync\n'
                            b'/run/mojt-system/busybox poweroff -f\n')
                        process.stdin.flush()
                        login_step = 3
        raise subprocess.TimeoutExpired(process.args, 90, output=bytes(output))
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdin.close()
        process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--modules-dir", type=Path, required=True)
    parser.add_argument("--busybox", type=Path, default=Path("/usr/bin/busybox"))
    parser.add_argument("--output", type=Path, required=True, help="new retained test directory")
    parser.add_argument("--hardware-profile", choices=("thinkpad-x1-carbon-3",))
    parser.add_argument("--disk-bus", choices=("sata", "usb"), default="sata")
    parser.add_argument("--switch-bus", choices=("sata", "usb"),
                        help="second boot changes bus while retaining the same disk and OVMF variables")
    parser.add_argument("--firmware-root", type=Path,
                        help="optional real extracted Debian firmware root instead of the synthetic fixture")
    parser.add_argument("--generations", action="store_true",
                        help="select A/A, A/B, B/B and A/A through real GRUB; poison both current links")
    parser.add_argument("--serial-login", action="store_true",
                        help="adapt a copy, authenticate on ttyS0 and execute guest shell commands")
    args = parser.parse_args()
    vm = load_vm()
    spec = importlib.util.spec_from_file_location("mojt_uefi_smoke_system",
                Path(__file__).resolve().parents[1] / "tools/mojt_system.py")
    system = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(system)
    release = vm.kernel_release_from_path(args.kernel)
    vm.validate_busybox_applets(args.busybox, extra=("findfs", "cp", "ln", "uname", "cat", "grep"))
    if args.serial_login:
        vm.validate_busybox_applets(args.busybox, "password", extra=("id",))
    physical = bool(args.hardware_profile)
    if args.serial_login and not physical:
        parser.error("--serial-login adapts a local-console hardware-profile fixture")
    if args.switch_bus and not physical:
        parser.error("--switch-bus requires --hardware-profile")
    console = "local" if physical else "serial"
    modules = vm.module_paths(release, args.modules_dir,
                             names=vm.hardware.EARLY_MODULES if physical else None)
    output = args.output.absolute()
    output.mkdir(mode=0o700)  # Never reuse an existing test disk.
    selected, base, root_uuid = "smoke-system", "smoke-base", str(uuid.uuid4())
    with tempfile.TemporaryDirectory(prefix=".uefi-smoke-", dir=output) as temp:
        work = Path(temp)
        tree = work / "tree"
        basepath = tree / "base" / base
        for name in ("usr/bin", "usr/lib", "etc", "var", "home", "root", "dev", "proc", "sys", "run", "nix", "tmp"):
            (basepath / name).mkdir(parents=True)
        (basepath / "bin").symlink_to("usr/bin")
        (basepath / "lib").symlink_to("usr/lib")
        (basepath / "usr/bin/sh").symlink_to("/run/mojt-system/busybox")
        (basepath / "usr/lib/generation").write_text(base + "\n")
        if args.generations:
            shutil.copytree(basepath, tree / "base/smoke-base-b", symlinks=True)
            (tree / "base/smoke-base-b/usr/lib/generation").write_text("smoke-base-b\n")
        (tree / "base/current").symlink_to(base)
        (tree / "state/etc").mkdir(parents=True)
        (tree / "state/var").mkdir()
        (tree / "state/home").mkdir()
        (tree / "state/root").mkdir(mode=0o700)
        (tree / "state/etc/hostname").write_text("mojt-smoke\n")
        password = "mojt-serial-test-only" if args.serial_login else None
        if args.serial_login:
            # Synthetic fixture only; the adaptation tool never provisions a password.
            hashed = subprocess.run(["openssl", "passwd", "-6", "-stdin"], input=password + "\n",
                                    check=True, capture_output=True, text=True).stdout.strip()
            system.write(tree / "state/etc/passwd", "root:x:0:0:root:/:/bin/sh\n")
            system.write(tree / "state/etc/shadow", f"root:{hashed}:0:0:99999:7:::\n", 0o600)
            system.write(tree / "state/etc/group", "root:x:0:\n")
            system.write(tree / "state/etc/securetty", "tty1\n")
        (tree / "releases").mkdir()
        (tree / "releases" / ("base-" + base + ".toml")).write_text("format = 1\n")
        if args.generations:
            (tree / "releases/base-smoke-base-b.toml").write_text("format = 1\n")
        (tree / "nix").mkdir()
        profile = tree / "system" / selected
        (profile / "bin").mkdir(parents=True)
        shutil.copy2(args.busybox, profile / "busybox")
        if args.serial_login:
            (profile / "login").symlink_to("busybox")
        for name in ("cat", "uname", "grep"):
            (profile / "bin" / name).symlink_to("../busybox")
        (profile / "version").write_text(selected + "\n")
        (profile / "assembled-at-utc").write_text("synthetic-smoke-fixture\n")
        if physical:
            # This tests module/firmware mounts, not actual Wi-Fi firmware loading.
            fw = args.firmware_root or work / "synthetic-firmware"
            if args.firmware_root is None:
                system.write(fw / "usr/lib/firmware/iwlwifi-7265D-29.ucode", "synthetic fixture")
                for name in ("regulatory.db-debian", "regulatory.db.p7s-debian"):
                    system.write(fw / "usr/lib/firmware" / name, "synthetic fixture")
                for package in vm.hardware.LICENSE_PACKAGES:
                    system.write(fw / "usr/share/doc" / package / "copyright", "synthetic fixture")
            (profile / "units").mkdir()
            vm.hardware.stage(tree, selected, args.modules_dir, release, fw, system)
        # A deliberately unusable current link proves that the boot pair pins System.
        (tree / "system/current").symlink_to("unselected-and-absent")
        (profile / "start").write_text('''#!/bin/sh
set -eu
exec >/dev/ttyS0 2>&1
export PATH=/run/mojt-system/bin
[ -d /sys/firmware/efi ]
[ "$(uname -r)" = "@RELEASE@" ]
selected="$(cat /run/mojt-system/version)"
base="$(cat /usr/lib/generation)"
grep -q "mojt.system=$selected" /proc/cmdline
grep -q "mojt.base=$base" /proc/cmdline
grep -q 'root=UUID=@UUID@' /proc/cmdline
[ -f "/run/mojt-disk/boot/mojt/$selected/$base/boot.json" ]
echo "MOJT_GENERATION_PAIR_${base}_${selected}"
@HARDWARE_CHECK@
if [ -f /etc/uefi-smoke-marker ]; then
    [ "$(cat /var/uefi-smoke-marker)" = retained ]
    [ "$(cat /home/uefi-smoke-marker)" = retained ]
    [ "$(cat /root/uefi-smoke-marker)" = retained ]
    echo MOJT_UEFI_SMOKE_PERSISTED
else
    echo retained >/etc/uefi-smoke-marker
    echo retained >/var/uefi-smoke-marker
    echo retained >/home/uefi-smoke-marker
    echo retained >/root/uefi-smoke-marker
    echo MOJT_UEFI_SMOKE_FIRST_BOOT
fi
grep -q ' /home ' /proc/mounts
grep -q ' /root ' /proc/mounts
echo MOJT_UEFI_SMOKE_BOOT_PASS
if [ -f /etc/systemd/system/mojt-serial-console.service ]; then
    grep -q 'TTYPath=/dev/ttyS0' /etc/systemd/system/mojt-serial-console.service
    [ -L /etc/systemd/system/mojt.target.wants/mojt-serial-console.service ]
    grep -q '^ttyS0$' /etc/securetty
    exec /run/mojt-system/busybox getty -f /run/mojt/issue -l /run/mojt-system/login -L 115200 ttyS0 vt100
fi
/run/mojt-system/busybox sync
/run/mojt-system/busybox poweroff -f
'''.replace("@RELEASE@", release).replace("@UUID@", root_uuid).replace(
    "@HARDWARE_CHECK@", '''grep -q 'console=tty0' /proc/cmdline
[ -f /lib/modules/@RELEASE@/modules.dep ]
[ -f /lib/firmware/iwlwifi-7265D-29.ucode ]
grep -q ' /usr/lib/modules [^ ]* ro,' /proc/mounts
grep -q ' /usr/lib/firmware [^ ]* ro,' /proc/mounts
grep -q '^tty0 ' /proc/consoles
echo MOJT_HARDWARE_MOUNTS_PASS'''.replace("@RELEASE@", release) if physical else ":"))
        (profile / "start").chmod(0o755)
        pairs = [(base, selected)]
        if args.generations:
            second = tree / "system/smoke-system-b"
            shutil.copytree(profile, second, symlinks=True)
            (second / "version").write_text("smoke-system-b\n")
            if physical:
                for name in ("modules", "firmware"):
                    (tree / "base/smoke-base-b/usr/lib" / name).mkdir(exist_ok=True)
            pairs += [(base, "smoke-system-b"), ("smoke-base-b", "smoke-system-b")]
            # The hardware helper needed a valid link during staging only.
            (tree / "base/current").unlink()
            (tree / "base/current").symlink_to("unselected-and-absent")
        boot_records = []
        for number, (pair_base, pair_system) in enumerate(pairs):
            script = system.init_script(vm.INIT)
            if physical:
                script = vm.hardware.init_script(script)
            script = vm.boot.init_script(script, root_uuid, pair_system, pair_base)
            initramfs = vm.make_initramfs(work / ("initramfs-" + str(number)), args.busybox, modules,
                                          script, system.SHUTDOWN, extra_applets=("findfs",))
            boot_records.append(vm.boot.stage(
                tree, args.kernel, initramfs, modules, release=release, base=pair_base,
                system=pair_system, root_uuid=root_uuid, console=console))
        parts = vm.boot.build_disk(output / "disk.img", tree, work, 2048 if physical else 512,
                                   root_uuid, selected, base, console=console)
        if args.serial_login:
            baseline = output / "baseline"
            baseline.mkdir()
            (output / "disk.img").rename(baseline / "disk.img")
            system.write(baseline / "build.json", json.dumps(dict(
                format=1, boot_mode="uefi", login_mode="password", disk_layout=parts,
                system_step=0, hardware={"profile": args.hardware_profile} if physical else None,
                boot_record=boot_records[0], additional_boot_records=boot_records[1:])))
            spec = importlib.util.spec_from_file_location("mojt_serial_smoke",
                        Path(__file__).resolve().parents[1] / "tools/mojt-vm-serial.py")
            adapter = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(adapter)
            adapter.prepare(baseline, output / "serial")
    active = output / "serial" if args.serial_login else output
    # No external kernel, initramfs, filesystem tree or payload survives into boot.
    launcher = active / "run-qemu.sh"
    if not args.serial_login:
        launcher.write_text(vm.boot.run_script(local_console=physical))
    launcher.chmod(0o755)
    order = (0, 1, 2, 0) if args.generations else ((0, 0) if args.serial_login else (None, None))
    for number, index in enumerate(order, 1):
        bus = args.switch_bus if number == 2 and args.switch_bus else args.disk_bus
        try:
            run = firmware_boot(launcher, {**os.environ, "QEMU_DISPLAY": "none", "QEMU_DISK_BUS": bus}, index,
                                login=password)
        except subprocess.TimeoutExpired as error:
            (output / f"boot-{number}.log").write_bytes(error.stdout or b"")
            raise RuntimeError(f"firmware boot {number} timed out; inspect {output}/boot-{number}.log") from error
        (output / f"boot-{number}.log").write_bytes(run.stdout)
        expected = b"MOJT_UEFI_SMOKE_FIRST_BOOT" if number == 1 else b"MOJT_UEFI_SMOKE_PERSISTED"
        if run.returncode or b"MOJT_UEFI_SMOKE_BOOT_PASS" not in run.stdout or expected not in run.stdout:
            raise RuntimeError(f"firmware boot {number} failed; inspect {output}/boot-{number}.log")
        print(f"PASS: UEFI/GRUB boot {number}; UUID discovery, pinned System and persistent state", flush=True)
        if args.serial_login:
            if b"\nMOJT_SERIAL_LOGIN_PASS\n" not in run.stdout.replace(b"\r", b""):
                raise RuntimeError("authenticated serial guest shell probe did not pass")
            print("PASS: serial root password login and guest shell commands", flush=True)
        if index is not None:
            pair_base, pair_system = pairs[index]
            expected_pair = f"MOJT_GENERATION_PAIR_{pair_base}_{pair_system}".encode()
            if expected_pair not in run.stdout:
                raise RuntimeError("GRUB started an unexpected Base/System pair")
            print(f"PASS: GRUB selected Base {pair_base} / System {pair_system}; both current links unusable", flush=True)
        if args.switch_bus:
            print(f"PASS: {bus} disk boot with shared firmware variables", flush=True)
    fresh = output / "disk-only-copy"
    fresh.mkdir()
    subprocess.run(["cp", "--sparse=always", str(active / "disk.img"), str(fresh / "disk.img")], check=True)
    (fresh / "run-qemu.sh").write_text(vm.boot.run_script(local_console=physical))
    run = firmware_boot(fresh / "run-qemu.sh", {**os.environ, "QEMU_DISPLAY": "none",
                        "QEMU_DISK_BUS": args.switch_bus or args.disk_bus},
                        2 if args.generations else (0 if args.serial_login else None), login=password)
    (fresh / "boot.log").write_bytes(run.stdout)
    if run.returncode or b"MOJT_UEFI_SMOKE_PERSISTED" not in run.stdout:
        raise RuntimeError(f"disk-only copy boot failed; inspect {fresh}/boot.log")
    if args.serial_login and b"\nMOJT_SERIAL_LOGIN_PASS\n" not in run.stdout.replace(b"\r", b""):
        raise RuntimeError("disk-only copy serial login failed")
    print("PASS: disk-only copy boots with fresh firmware variables; no external boot payload", flush=True)
    print("Synthetic static guest only; full Mojt login/services/network/Ports acceptance remains required.")


if __name__ == "__main__":
    main()
