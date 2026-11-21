#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Hardware staging, local-console selection, and input rejection contracts."""

import importlib.util
import contextlib
import io
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

    def firmware(self, profile=hw.PROFILE):
        root = self.root / "firmware-root"
        system.write(root / "usr/lib/firmware/iwlwifi-7265D-29.ucode", "synthetic firmware")
        for name in ("regulatory.db-debian", "regulatory.db.p7s-debian"):
            system.write(root / "usr/lib/firmware" / name, "synthetic regulatory database")
        if profile == hw.PC_PROFILE:
            for name in ('i915/test.bin','amdgpu/test.bin','rtl_nic/test.bin',
                         'ath10k/test/firmware.bin','mediatek/test.bin','brcm/test.bin'):
                system.write(root / 'usr/lib/firmware' / name, 'synthetic firmware')
        for package in hw.license_packages(profile):
            system.write(root / "usr/share/doc" / package / "copyright", "synthetic license")
        return root

    def test_pc_profile_binds_firmware_licenses_and_probes_present_devices_without_intel_requirements(self):
        firmware=self.firmware(hw.PC_PROFILE)
        # The generic policy accepts another Intel Wi-Fi generation, not only 7265.
        (firmware/'usr/lib/firmware/iwlwifi-7265D-29.ucode').rename(firmware/'usr/lib/firmware/iwlwifi-test.ucode')
        modules=self.root/'lib/modules/test';system.write(modules/'kernel/test.ko','synthetic module')
        tree=self.root/'pc-image';(tree/'base/b/usr/lib').mkdir(parents=True)
        (tree/'base/current').symlink_to('b');(tree/'base/b/lib').symlink_to('usr/lib')
        profile=tree/'system/pc';(profile/'units').mkdir(parents=True)
        row=hw.stage(tree,'pc',modules,'test',firmware,system,native_kernel=True,hardware_profile=hw.PC_PROFILE)
        self.assertEqual(row['runtime_modules'],[])
        self.assertTrue({'nvme','virtio_scsi','ahci','usb_storage','ext4'} <= set(row['early_modules']))
        self.assertEqual(hw.native_firmware(profile,hw.boot_profile(hw.PC_PROFILE)),profile/'kernel/lib/firmware')
        with self.assertRaisesRegex(ValueError,'bound boot profile'):
            hw.native_firmware(profile,hw.boot_profile(hw.PROFILE))
        script=(profile/'load-hardware').read_text();self.assertNotIn('modprobe ',script)
        self.assertIn('After=mojt-setup.service systemd-udevd.service',(profile/'units/mojt-hardware.service').read_text())
        commands=self.root/'commands';commands.mkdir();log=self.root/'events';knob=self.root/'printk';knob.write_text('7\n')
        system.write(commands/'udevadm','#!/bin/sh\nprintf "%s\\n" "$*" >>"$EVENT_LOG"\n[ -z "${FAIL_PROBE-}" ]\n',0o755)
        driver=script.replace('. /run/mojt-system/environment',f'PATH="{commands}:$PATH"\nexport PATH').replace('/proc/sys/kernel/printk',str(knob))
        env={**os.environ,'EVENT_LOG':str(log),'FAIL_PROBE':''}
        subprocess.run(['sh'],input=driver,text=True,env=env,check=True)
        self.assertEqual(log.read_text().splitlines(),['trigger --action=add --type=subsystems --settle','trigger --action=add --type=devices --settle'])
        self.assertEqual(knob.read_text(),'3\n')
        knob.write_text('7\n')
        self.assertNotEqual(subprocess.run(['sh'],input=driver,text=True,env={**env,'FAIL_PROBE':'1'}).returncode,0)
        self.assertEqual(knob.read_text(),'7\n')
        (profile/'kernel/licenses/firmware-realtek/copyright').unlink()
        with self.assertRaisesRegex(ValueError,'license'):hw.native_firmware(profile)

    def test_pc_firmware_freeze_preserves_all_declared_families_and_refuses_missing_payload(self):
        root=self.firmware(hw.PC_PROFILE)
        expected=hw.input_identity(root,'test',system,hw.PC_PROFILE)
        copied=self.root/'pc-frozen'
        hw.freeze_inputs(root,copied,'test',system,expected,hw.PC_PROFILE)
        self.assertEqual(hw.input_identity(copied,'test',system,hw.PC_PROFILE),expected)
        (root/'usr/lib/firmware/amdgpu/test.bin').unlink()
        with self.assertRaisesRegex(ValueError,'firmware-amd-graphics'):
            hw.firmware_inputs(root,hw.PC_PROFILE)

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

    def test_native_inputs_are_frozen_without_copying_an_extracted_distribution_kernel(self):
        root=self.firmware();system.write(root/'boot/vmlinuz-unrelated','not a bootstrap input')
        expected=hw.input_identity(root,'test',system)
        copied=self.root/'frozen';hw.freeze_inputs(root,copied,'test',system,expected)
        self.assertEqual(hw.input_identity(copied,'test',system),expected)
        self.assertFalse((copied/'boot').exists())
        (root/'usr/lib/firmware/iwlwifi-7265D-29.ucode').write_text('changed')
        with self.assertRaisesRegex(ValueError,'changed after preview'):
            hw.freeze_inputs(root,self.root/'retry','test',system,expected)
        self.assertFalse((self.root/'retry').exists())

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

    def test_nvme_launcher_is_only_exported_for_generic_pc_policy(self):
        script=vm.boot.run_script(local_console=True,hardware_profile=hw.PC_PROFILE)
        self.assertIn('nvme,drive=mojt,serial=mojt-test,bootindex=1',script)
        self.assertNotIn('nvme)',vm.boot.run_script(local_console=True,hardware_profile=hw.PROFILE))
        subprocess.run(['bash','-n'],input=script,text=True,check=True)

    def test_readiness_probe_only_resolves_drivers_and_enumerates_devices(self):
        probe=load('pc_readiness','../tests/check-pc-hardware.py')
        modules=self.root/'lib/modules/test';modules.mkdir(parents=True)
        commands=[]
        def run(args,**kwargs):
            commands.append(args)
            if args[0] == 'modprobe':
                self.assertIn('--show-depends',args)
                return subprocess.CompletedProcess(args,0,stdout='builtin test\n')
            self.assertEqual(args,['udevadm','trigger','--dry-run','--action=add','--type=devices'])
            return subprocess.CompletedProcess(args,0,stdout='/sys/devices/test\n')
        before=system.tree_hash(self.root)
        with mock.patch.object(subprocess,'run',side_effect=run),contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(probe.main(['--modules-dir',str(modules)]),0)
        self.assertEqual([args[-1] for args in commands[:-1]],list(hw.PC_EARLY_MODULES))
        self.assertIn('NOT TESTED: new firmware inputs',output.getvalue())
        self.assertEqual(system.tree_hash(self.root),before)
        with mock.patch.object(subprocess,'run',side_effect=subprocess.CalledProcessError(1,['modprobe'])),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError):probe.main(['--modules-dir',str(modules)])

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
