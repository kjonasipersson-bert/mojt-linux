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

    def make_guest_account_tree(self, root):
        etc = root / "state/etc"
        etc.mkdir(parents=True)
        (etc / "passwd").write_text(
            "root:x:0:0:root:/root:/bin/sh\n"
            "daemon:x:1:1:daemon:/var/empty:/bin/false\n",
            encoding="utf-8",
        )
        (etc / "group").write_text(
            "root:x:0:\ndaemon:x:1:\n", encoding="utf-8",
        )
        return etc

    def test_password_login_provisions_only_guest_shadow(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            etc = self.make_guest_account_tree(tree)
            digest = "$6$testsalt$synthetic-unit-test-only"
            with mock.patch.object(vm.os, "chown"):
                vm.provision_vm_root_login(tree, digest)
            shadow = etc / "shadow"
            self.assertEqual(shadow.stat().st_mode & 0o777, 0o600)
            contents = shadow.read_text()
            self.assertIn(f"root:{digest}:", contents)
            self.assertIn("daemon:!:", contents)
            self.assertTrue((etc / "gshadow").is_file())
            self.assertEqual((etc / "gshadow").stat().st_mode & 0o777, 0o600)
            self.assertEqual((etc / "securetty").read_text(), "ttyS0\n")
            self.assertEqual((etc / "passwd").read_text().splitlines()[0],
                             "root:x:0:0:root:/root:/bin/sh")

    def test_existing_shadow_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            etc = self.make_guest_account_tree(tree)
            shadow = etc / "shadow"
            shadow.write_text("root:$6$existing$hash:0:0:99999:7:::\n")
            shadow.chmod(0o600)
            with mock.patch.object(vm.os, "chown"):
                vm.provision_vm_root_login(tree)
            self.assertEqual(shadow.read_text(),
                             "root:$6$existing$hash:0:0:99999:7:::\n")
            with mock.patch.object(vm.os, "chown"):
                with self.assertRaisesRegex(ValueError, "overwrite"):
                    vm.provision_vm_root_login(tree, "$6$new$hash")

    def test_locked_or_unsafe_shadow_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            etc = self.make_guest_account_tree(tree)
            shadow = etc / "shadow"
            shadow.write_text("root:!:0:0:99999:7:::\n")
            shadow.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "locked"):
                vm.provision_vm_root_login(tree)
            shadow.write_text("root:$6$secret$hash:0:0:99999:7:::\n")
            shadow.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "permissions"):
                vm.provision_vm_root_login(tree)

    def test_symlink_shadow_and_insecure_serial_policy_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            etc = self.make_guest_account_tree(tree)
            shadow = etc / "shadow"
            shadow.symlink_to("/etc/shadow")
            with self.assertRaisesRegex(ValueError, "unsafe account file"):
                vm.provision_vm_root_login(tree, "$6$test$hash")
            shadow.unlink()
            (etc / "securetty").write_text("tty1\n")
            with mock.patch.object(vm.os, "chown"):
                with self.assertRaisesRegex(ValueError, "ttyS0"):
                    vm.provision_vm_root_login(tree, "$6$test$hash")

    def test_password_mode_wont_preserve_open_root_console(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            etc = tree / "state/etc"
            etc.mkdir(parents=True)
            (etc / "inittab").write_text(vm.SYSTEM_INITTAB)
            binary = tree / "fake"
            binary.write_bytes(b"fake")
            with mock.patch.object(vm.os, "chown"):
                with self.assertRaisesRegex(ValueError, "unauthenticated|root shell"):
                    vm.install_system_init(tree, binary, "password")
            self.assertEqual((etc / "inittab").read_text(), vm.SYSTEM_INITTAB)

    def test_new_password_mode_uses_getty_and_login_from_system(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            (tree / "state/etc").mkdir(parents=True)
            binary = tree / "fake"
            binary.write_bytes(b"fake")
            with mock.patch.object(vm.os, "chown"):
                vm.install_system_init(tree, binary, "password")
            inittab = (tree / "state/etc/inittab").read_text()
            self.assertIn("getty -L -l /run/mojt-system/login", inittab)
            self.assertNotIn("respawn:/bin/sh", inittab)
            self.assertEqual((tree / "system/prototype-init/login").readlink().as_posix(),
                             "busybox")
            self.assertIn("passwd", vm.LOGIN_APPLETS)

    def test_missing_busybox_login_applet_rejected(self):
        fake_applets = vm.REQUIRED_APPLETS | {"login", "getty"}
        with mock.patch.object(
            vm.subprocess, "run",
            return_value=types.SimpleNamespace(stdout="\n".join(fake_applets)),
        ):
            with self.assertRaisesRegex(ValueError, "passwd"):
                vm.validate_busybox_applets(Path("/test/fake-busybox"), "password")

    def test_password_prompt_passes_secret_on_stdin_only(self):
        with mock.patch.object(vm.sys.stdin, "isatty", return_value=True):
            with mock.patch.object(vm.getpass, "getpass",
                                   side_effect=["synthetic-testing-password",
                                                "synthetic-testing-password"]):
                with mock.patch.object(
                    vm.subprocess, "run",
                    return_value=types.SimpleNamespace(stdout="$6$salt$test-hash\n"),
                ) as call:
                    self.assertEqual(vm.password_hash_from_terminal(), "$6$salt$test-hash")
        args, kwargs = call.call_args
        self.assertEqual(args[0], ["openssl", "passwd", "-6", "-stdin"])
        self.assertEqual(kwargs["input"], "synthetic-testing-password\n")
        self.assertNotIn("synthetic-testing-password", " ".join(args[0]))

    def test_module_compression_plain_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "dummy.ko"
            module.write_bytes(b"test module")
            self.assertEqual(vm.module_bytes(module), b"test module")


if __name__ == "__main__":
    unittest.main()
