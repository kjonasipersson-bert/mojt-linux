#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real firmware/disk boot probe with a synthetic static guest, not Mojt service acceptance."""

import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid


def load_vm():
    spec = importlib.util.spec_from_file_location("mojt_uefi_smoke_vm",
                Path(__file__).resolve().parents[1] / "tools/mojt-vm-build.py")
    vm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vm)
    return vm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--modules-dir", type=Path, required=True)
    parser.add_argument("--busybox", type=Path, default=Path("/usr/bin/busybox"))
    parser.add_argument("--output", type=Path, required=True, help="new retained test directory")
    args = parser.parse_args()
    vm = load_vm()
    spec = importlib.util.spec_from_file_location("mojt_uefi_smoke_system",
                Path(__file__).resolve().parents[1] / "tools/mojt_system.py")
    system = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(system)
    release = vm.kernel_release_from_path(args.kernel)
    vm.validate_busybox_applets(args.busybox, extra=("findfs", "cp", "ln", "uname", "cat", "grep"))
    modules = vm.module_paths(release, args.modules_dir)
    output = args.output.absolute()
    output.mkdir(mode=0o700)  # Never reuse an existing test disk.
    selected, base, root_uuid = "smoke-system", "smoke-base", str(uuid.uuid4())
    with tempfile.TemporaryDirectory(prefix=".uefi-smoke-", dir=output) as temp:
        work = Path(temp)
        tree = work / "tree"
        basepath = tree / "base" / base
        for name in ("usr/bin", "etc", "var", "dev", "proc", "sys", "run", "nix", "tmp"):
            (basepath / name).mkdir(parents=True)
        (basepath / "bin").symlink_to("usr/bin")
        (basepath / "usr/bin/sh").symlink_to("/run/mojt-system/busybox")
        (tree / "base/current").symlink_to(base)
        (tree / "state/etc").mkdir(parents=True)
        (tree / "state/var").mkdir()
        (tree / "state/etc/hostname").write_text("mojt-smoke\n")
        (tree / "releases").mkdir()
        (tree / "releases" / ("base-" + base + ".toml")).write_text("format = 1\n")
        (tree / "nix").mkdir()
        profile = tree / "system" / selected
        (profile / "bin").mkdir(parents=True)
        shutil.copy2(args.busybox, profile / "busybox")
        for name in ("cat", "uname", "grep"):
            (profile / "bin" / name).symlink_to("../busybox")
        (profile / "version").write_text(selected + "\n")
        (profile / "assembled-at-utc").write_text("synthetic-smoke-fixture\n")
        # A deliberately unusable current link proves that the boot pair pins System.
        (tree / "system/current").symlink_to("unselected-and-absent")
        (profile / "start").write_text('''#!/bin/sh
set -eu
export PATH=/run/mojt-system/bin
[ -d /sys/firmware/efi ]
[ "$(uname -r)" = "@RELEASE@" ]
[ "$(cat /run/mojt-system/version)" = smoke-system ]
grep -q 'root=UUID=@UUID@' /proc/cmdline
[ -f /run/mojt-disk/boot/mojt/smoke-system/boot.json ]
if [ -f /etc/uefi-smoke-marker ]; then
    [ "$(cat /var/uefi-smoke-marker)" = retained ]
    echo MOJT_UEFI_SMOKE_PERSISTED
else
    echo retained >/etc/uefi-smoke-marker
    echo retained >/var/uefi-smoke-marker
    echo MOJT_UEFI_SMOKE_FIRST_BOOT
fi
echo MOJT_UEFI_SMOKE_BOOT_PASS
/run/mojt-system/busybox sync
/run/mojt-system/busybox poweroff -f
'''.replace("@RELEASE@", release).replace("@UUID@", root_uuid))
        (profile / "start").chmod(0o755)
        script = vm.boot.init_script(system.init_script(vm.INIT), root_uuid, selected)
        initramfs = vm.make_initramfs(work / "initramfs", args.busybox, modules,
                                      script, system.SHUTDOWN, extra_applets=("findfs",))
        vm.boot.stage(tree, args.kernel, initramfs, modules, release=release, base=base,
                      system=selected, root_uuid=root_uuid)
        vm.boot.build_disk(output / "disk.img", tree, work, 512, root_uuid, selected)
    # No external kernel, initramfs, filesystem tree or payload survives into boot.
    launcher = output / "run-qemu.sh"
    launcher.write_text(vm.boot.run_script())
    launcher.chmod(0o755)
    for number in (1, 2):
        run = subprocess.run(["bash", str(launcher)], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=90)
        (output / f"boot-{number}.log").write_bytes(run.stdout)
        expected = b"MOJT_UEFI_SMOKE_FIRST_BOOT" if number == 1 else b"MOJT_UEFI_SMOKE_PERSISTED"
        if run.returncode or b"MOJT_UEFI_SMOKE_BOOT_PASS" not in run.stdout or expected not in run.stdout:
            raise RuntimeError(f"firmware boot {number} failed; inspect {output}/boot-{number}.log")
        print(f"PASS: UEFI/GRUB boot {number}; UUID discovery, pinned System and persistent state", flush=True)
    fresh = output / "disk-only-copy"
    fresh.mkdir()
    subprocess.run(["cp", "--sparse=always", str(output / "disk.img"), str(fresh / "disk.img")], check=True)
    (fresh / "run-qemu.sh").write_text(vm.boot.run_script())
    run = subprocess.run(["bash", str(fresh / "run-qemu.sh")], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, timeout=90)
    (fresh / "boot.log").write_bytes(run.stdout)
    if run.returncode or b"MOJT_UEFI_SMOKE_PERSISTED" not in run.stdout:
        raise RuntimeError(f"disk-only copy boot failed; inspect {fresh}/boot.log")
    print("PASS: disk-only copy boots with fresh firmware variables; no external boot payload", flush=True)
    print("Synthetic static guest only; full Mojt login/services/network/Ports acceptance remains required.")


if __name__ == "__main__":
    main()
