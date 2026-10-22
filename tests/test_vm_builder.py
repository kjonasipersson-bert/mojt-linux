#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""VM builder smoke tests. Run with Python 3.11+ and standard library."""

import importlib.machinery
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import types


SCRIPT = Path(__file__).resolve().parents[1] / "tools/mojt-vm-build.py"
loader = importlib.machinery.SourceFileLoader("mojt_vm_builder", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
vm = importlib.util.module_from_spec(spec)
loader.exec_module(vm)


class VmBuilderTests(unittest.TestCase):
    def test_version_validation(self):
        self.assertEqual(vm.label("0.1.3"), "0.1.3")
        for value in ("../other", "a/b", "..", "", "a b"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                vm.label(value)

    def test_kernel_release_name(self):
        self.assertEqual(
            vm.kernel_release_from_path(Path("/boot/vmlinuz-6.1.0-42-amd64")),
            "6.1.0-42-amd64",
        )
        with self.assertRaises(ValueError):
            vm.kernel_release_from_path(Path("bzImage"))

    def test_initramfs_scripts_reference_persistent_state(self):
        init = vm.INIT
        for required in ("base/current", "state/etc", "state/var",
                         "mount --bind", "switch_root", "Selected Base"):
            self.assertIn(required, init)
        launcher = vm.run_script()
        self.assertIn("if=virtio,format=raw", launcher)
        self.assertIn("console=ttyS0", launcher)
        self.assertIn("accel=kvm:tcg", launcher)

    def test_populate_disk_preserves_version_and_separate_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            generation = target / "base/0.1.3"
            (generation / "etc").mkdir(parents=True)
            (generation / "var").mkdir()
            (generation / "usr/lib").mkdir(parents=True)
            (target / "state/etc").mkdir(parents=True)
            (target / "state/var").mkdir()
            (target / "releases").mkdir()
            (target / "state/etc/local.conf").write_text("preserved")
            (target / "state/var/data").write_text("persistent")
            (target / "state/layout-version").write_text("1\n")
            (target / "releases/base-0.1.3.toml").write_text("format = 1\n")
            tree = Path(tmp) / "tree"
            tree.mkdir()
            with mock.patch.object(vm.os, "chown"):
                vm.populate_disk_tree(target, "0.1.3", tree)
            self.assertEqual((tree / "base/current").readlink().as_posix(), "0.1.3")
            self.assertEqual((tree / "state/etc/local.conf").read_text(), "preserved")
            self.assertEqual((tree / "state/var/data").read_text(), "persistent")
            self.assertTrue((tree / "base/0.1.3/etc").is_dir())

    def test_busybox_init_is_system_owned_and_preserves_inittab(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            (tree / "state/etc").mkdir(parents=True)
            fake_busybox = tree / "fake-busybox"
            fake_busybox.write_bytes(b"fake")
            with mock.patch.object(vm.os, "chown"):
                vm.install_system_init(tree, fake_busybox)
            system_binary = tree / "system/prototype-init/busybox"
            self.assertEqual(system_binary.read_bytes(), b"fake")
            self.assertIn("ttyS0::respawn:", (tree / "state/etc/inittab").read_text())
            (tree / "state/etc/inittab").write_text("custom admin config\n")
            with mock.patch.object(vm.os, "chown"):
                vm.install_system_init(tree, fake_busybox)
            self.assertEqual((tree / "state/etc/inittab").read_text(),
                             "custom admin config\n")

    def test_inittab_conflict_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            (tree / "state/etc").mkdir(parents=True)
            (tree / "state/etc/inittab").symlink_to("/etc/other")
            fake_busybox = tree / "fake-busybox"
            fake_busybox.write_bytes(b"fake")
            with mock.patch.object(vm.os, "chown"):
                with self.assertRaisesRegex(ValueError, "inittab"):
                    vm.install_system_init(tree, fake_busybox)
            self.assertTrue((tree / "state/etc/inittab").is_symlink())

    def test_root_shadow_missing_diagnostic_does_not_change_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            (tree / "state/etc").mkdir(parents=True)
            passwd = tree / "state/etc/passwd"
            passwd.write_text("root:x:0:0:root:/root:/bin/sh\n")
            with mock.patch.object(vm.sys, "stderr") as err:
                vm.warn_missing_shadow(tree)
            self.assertTrue(err.write.called or err.method_calls)
            self.assertFalse((tree / "state/etc/shadow").exists())
            self.assertEqual(passwd.read_text(), "root:x:0:0:root:/root:/bin/sh\n")

    def test_init_handoff_and_poweroff_contract(self):
        self.assertIn("switch_root -c /dev/console /newroot /run/mojt-system/busybox init", vm.INIT)
        self.assertIn("mount -t tmpfs", vm.INIT)
        self.assertIn("mount --bind /sysroot/system/prototype-init", vm.INIT)
        self.assertIn("ttyS0::respawn:", vm.SYSTEM_INITTAB)
        self.assertIn("::shutdown:", vm.SYSTEM_INITTAB)
        self.assertIn("poweroff", vm.REQUIRED_APPLETS)

    def test_module_compression_plain_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "dummy.ko"
            module.write_bytes(b"test module")
            self.assertEqual(vm.module_bytes(module), b"test module")


if __name__ == "__main__":
    unittest.main()
