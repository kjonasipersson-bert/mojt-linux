#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Failure regression tests for mojt-base-install (no host Base release needed).

Host: Python 3.11+, GNU tar, zstd. Run as an ordinary user:
    python3 -m unittest discover -s tests -p 'test_base_install_failures.py' -v

The tests create throwaway synthetic rootfs releases and do not modify /etc,
the host rootfs, or a production Mojt installation. Ownership changes are
mocked to permit running as an ordinary user.
"""

import hashlib
import importlib.machinery
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parent.parent
INSTALLER_PATH = REPO / "tools" / "mojt-base-install"
loader = importlib.machinery.SourceFileLoader("mojt_base_install_tested", str(INSTALLER_PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
installer = importlib.util.module_from_spec(spec)
loader.exec_module(installer)


@unittest.skipUnless(shutil.which("zstd") and shutil.which("tar"), "GNU tar and zstd required")
class InstallFailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mojt-install-failures-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / "target"
        self.target.mkdir()
        self.release = self.root / "release"
        self.release.mkdir()
        self.version = "0.1.9-test"
        self.make_release()
        # chown would require elevated privileges on some ordinary-user hosts.
        ownership = mock.patch.object(installer, "copy_ownership")
        ownership.start()
        self.addCleanup(ownership.stop)

    def make_release(self):
        rootfs = self.root / "rootfs"
        (rootfs / "usr/lib").mkdir(parents=True)
        (rootfs / "usr/etc").mkdir()
        (rootfs / "etc").mkdir()
        (rootfs / "var").mkdir()
        (rootfs / "usr/lib/os-release").write_text(
            f'NAME="Mojt"\nID=mojt\nIMAGE_VERSION="{self.version}"\n',
            encoding="utf-8",
        )
        (rootfs / "usr/etc/a.conf").write_text("default a\n", encoding="utf-8")
        (rootfs / "usr/etc/b.conf").write_text("default b\n", encoding="utf-8")
        tarpath = self.root / "image.tar"
        with tarpath.open("wb") as stream:
            subprocess.run(["tar", "-cf", "-", "-C", str(rootfs), "."],
                           stdout=stream, check=True)
        image = self.release / "rootfs.tar.zst"
        with image.open("wb") as stream:
            subprocess.run(["zstd", "-q", "-c", str(tarpath)],
                           stdout=stream, check=True)
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        (self.release / "manifest.toml").write_text(
            'format = 1\n'
            '[base]\nname = "mojt"\n'
            f'version = "{self.version}"\n'
            f'architecture = "{installer.platform.machine()}"\n'
            '[image]\nfile = "rootfs.tar.zst"\n'
            f'sha256 = "{digest}"\n'
            '[state]\nlayout_version = 1\n'
            'etc_defaults = "/usr/etc"\n'
            'etc_policy = "add-missing"\n'
            'var_policy = "persistent"\n',
            encoding="utf-8",
        )

    def install(self, no_activate=False):
        args = types.SimpleNamespace(release=self.release, no_activate=no_activate)
        installer.install(args, self.target)

    def setup_existing_state(self):
        etc = self.target / "state/etc"
        var = self.target / "state/var"
        etc.mkdir(parents=True)
        var.mkdir()
        (etc / "local.conf").write_text("local untouched\n", encoding="utf-8")
        (var / "data").write_text("persistent untouched\n", encoding="utf-8")
        return etc, var

    def assert_no_generation(self):
        self.assertFalse((self.target / "base" / self.version).exists())
        self.assertFalse((self.target / "base/current").is_symlink())
        self.assertFalse((self.target / "releases" / f"base-{self.version}.toml").exists())

    def test_corrupted_hash_rejected_without_state_mutation(self):
        etc, var = self.setup_existing_state()
        image = self.release / "rootfs.tar.zst"
        image.write_bytes(image.read_bytes() + b"corruption")
        with self.assertRaises(installer.InstallError):
            self.install()
        self.assertEqual((etc / "local.conf").read_text(), "local untouched\n")
        self.assertEqual((var / "data").read_text(), "persistent untouched\n")
        self.assertFalse((self.target / "base").exists())
        self.assert_no_generation()

    def test_failure_mid_defaults_removes_only_new_entries(self):
        etc, var = self.setup_existing_state()
        def fail_on_b(source, target, *, follow_symlinks=True):
            if target.name == "b.conf":
                raise OSError("injected failure copying second default")
        with mock.patch.object(installer, "copy_ownership", side_effect=fail_on_b):
            with self.assertRaisesRegex(OSError, "injected failure"):
                self.install()
        self.assertEqual(sorted(p.name for p in etc.iterdir()), ["local.conf"])
        self.assertEqual((etc / "local.conf").read_text(), "local untouched\n")
        self.assertEqual((var / "data").read_text(), "persistent untouched\n")
        self.assertFalse((self.target / "state/layout-version").exists())
        self.assert_no_generation()

    def test_activation_failure_rolls_back_state_generation_and_metadata(self):
        etc, var = self.setup_existing_state()
        with mock.patch.object(installer, "activate", side_effect=OSError("injected activation failure")):
            with self.assertRaisesRegex(OSError, "injected activation"):
                self.install()
        self.assertEqual(sorted(p.name for p in etc.iterdir()), ["local.conf"])
        self.assertEqual((var / "data").read_text(), "persistent untouched\n")
        self.assert_no_generation()

    def test_conflicting_os_release_rejected_before_defaults(self):
        etc, _ = self.setup_existing_state()
        (etc / "os-release").write_text("LOCAL=yes\n", encoding="utf-8")
        with self.assertRaisesRegex(installer.InstallError, "os-release"):
            self.install()
        self.assertEqual(sorted(p.name for p in etc.iterdir()), ["local.conf", "os-release"])
        self.assertEqual((etc / "os-release").read_text(), "LOCAL=yes\n")
        self.assert_no_generation()

    def test_success_preserves_local_files_and_activates(self):
        etc, var = self.setup_existing_state()
        self.install()
        self.assertEqual((self.target / "base/current").readlink().as_posix(), self.version)
        self.assertTrue((self.target / "base" / self.version).is_dir())
        self.assertEqual((etc / "a.conf").read_text(), "default a\n")
        self.assertEqual((etc / "b.conf").read_text(), "default b\n")
        self.assertEqual((etc / "local.conf").read_text(), "local untouched\n")
        self.assertEqual((var / "data").read_text(), "persistent untouched\n")
        self.assertEqual((etc / "os-release").readlink().as_posix(),
                         "../usr/lib/os-release")


if __name__ == "__main__":
    unittest.main()
