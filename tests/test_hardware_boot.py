#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Hardware staging, local-console selection, and input rejection contracts."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, REPO / "tools" / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


vm = load("hardware_test_vm", "mojt-vm-build.py")
system = load("hardware_test_system", "mojt_system.py")
hw = vm.hardware
UUID = "38ae152c-b81a-44da-b23a-3341398debe6"


class HardwareTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mojt-hardware-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def firmware(self):
        root = self.root / "firmware-root"
        system.write(root / "usr/lib/firmware/iwlwifi-7265D-29.ucode", "synthetic firmware")
        for name in ("regulatory.db-debian", "regulatory.db.p7s-debian"):
            system.write(root / "usr/lib/firmware" / name, "synthetic regulatory database")
        for package in hw.LICENSE_PACKAGES:
            system.write(root / "usr/share/doc" / package / "copyright", "synthetic license")
        return root

    def test_staging_keeps_complete_module_tree_and_licenses_without_source_changes(self):
        modules = self.root / "kernel/lib/modules/test"
        system.write(modules / "kernel/extra.ko", "not only early-boot modules")
        system.write(modules / "modules.dep", "kernel/extra.ko:\n")
        (modules / "build").symlink_to("/nonexistent/host/headers")
        before = system.tree_hash(modules)
        firmware = self.firmware()
        tree = self.root / "image"
        (tree / "base/b/usr/lib").mkdir(parents=True)
        (tree / "base/current").symlink_to("b")
        (tree / "base/b/lib").symlink_to("usr/lib")
        profile = tree / "system/s"
        (profile / "units").mkdir(parents=True)
        result = hw.stage(tree, "s", modules, "test", firmware, system)
        self.assertEqual(system.tree_hash(modules), before)
        self.assertTrue((profile / "kernel/lib/modules/test/kernel/extra.ko").is_file())
        self.assertFalse((profile / "kernel/lib/modules/test/build").is_symlink())
        self.assertTrue((tree / "base/b/usr/lib/modules").is_dir())
        self.assertTrue((profile / "kernel/licenses/firmware-iwlwifi/copyright").is_file())
        self.assertEqual((profile / "kernel/lib/firmware/regulatory.db").read_text(),
                         "synthetic regulatory database")
        self.assertEqual(result, json.loads((profile / "hardware.json").read_text()))
        self.assertTrue((profile / "units/mojt.target.wants/mojt-hardware.service").is_file())
        # Execute the generated driver script with a fake module loader and
        # sysctl file. Driver failure must not suppress its boot diagnostics.
        commands = self.root / "commands"
        commands.mkdir()
        system.write(commands / "modprobe", '#!/bin/sh\n[ "$1" != "${FAIL_MODULE-}" ]\n', 0o755)
        knob = self.root / "printk"
        driver = (profile / "load-hardware").read_text().replace(
            ". /run/mojt-system/environment", f'PATH="{commands}:$PATH"\nexport PATH').replace(
            "/proc/sys/kernel/printk", str(knob))
        knob.write_text("7\n")
        failed = subprocess.run(["sh"], input=driver, text=True,
                                env={**os.environ, "FAIL_MODULE": hw.RUNTIME_MODULES[0]})
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(knob.read_text(), "7\n")
        subprocess.run(["sh"], input=driver, text=True, check=True,
                       env={**os.environ, "FAIL_MODULE": ""})
        self.assertEqual(knob.read_text(), "3\n")
        script = hw.init_script(system.init_script(vm.INIT))
        script = vm.boot.init_script(script, UUID, "s", "b")
        self.assertIn("/sysroot/system/s/kernel/lib/modules", script)
        self.assertIn("/newroot/lib/firmware", script)
        self.assertNotIn("/sysroot/system/current", script)
        self.assertIn('exec /bin/sh </dev/console >/dev/console 2>&1', script)
        self.assertIn('module unavailable: $module', script)
        self.assertIn('panic "cannot mount Mojt ext4 partition"', script)
        subprocess.run(["sh", "-n"], input=script, text=True, check=True)

    def test_firmware_requires_7265_and_upstream_licenses(self):
        root = self.firmware()
        (root / "usr/share/doc/firmware-iwlwifi/copyright").unlink()
        with self.assertRaisesRegex(ValueError, "license"):
            hw.firmware_inputs(root)
        system.write(root / "usr/share/doc/firmware-iwlwifi/copyright", "license")
        (root / "usr/lib/firmware/iwlwifi-7265D-29.ucode").unlink()
        with self.assertRaisesRegex(ValueError, "7265"):
            hw.firmware_inputs(root)

    def test_special_files_and_escaping_links_are_rejected(self):
        root = self.root / "tree"
        root.mkdir()
        outside = self.root / "outside"
        outside.write_text("outside")
        (root / "escape").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "escapes"):
            hw.checked_tree(root)
        (root / "escape").unlink()
        os.mkfifo(root / "pipe")
        with self.assertRaisesRegex(ValueError, "special"):
            hw.checked_tree(root)

    def test_local_boot_uses_firmware_console_and_kernel_tty0(self):
        command = vm.boot.cmdline(UUID, "s", "b", console="local")
        self.assertIn("console=ttyS0,115200 console=tty0", command)
        self.assertIn("terminal_input console serial", vm.boot.terminal("local"))
        for bus in ("sata", "usb"):
            script = vm.boot.run_script(network=True, local_console=True)
            self.assertIn(bus + ")", script)
            self.assertIn("bus=ide.0,bootindex=1", script)
            self.assertIn("bus=xhci.0,bootindex=1", script)
            self.assertIn("user,model=e1000e", script)
            self.assertIn('QEMU_DISPLAY:-gtk', script)
            self.assertNotIn("if=virtio", script)
            subprocess.run(["bash", "-n"], input=script, text=True, check=True)
        with self.assertRaises(ValueError):
            vm.boot.terminal("invalid")

    def test_physical_development_console_is_rejected_before_staging(self):
        args = types.SimpleNamespace(boot_mode="uefi", hardware_profile=hw.PROFILE,
                                     login_mode="development")
        with mock.patch.object(vm.os, "geteuid", return_value=0), \
                mock.patch.object(vm.platform, "machine", return_value="x86_64"), \
                mock.patch.object(vm.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "password"):
                vm.build(args)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
