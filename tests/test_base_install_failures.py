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

    def test_install_adds_private_root_and_preserves_existing_home_state(self):
        self.setup_existing_state()
        home = self.target / "state/home/example"
        home.mkdir(parents=True, mode=0o700)
        (home / "data").write_text("personal data")
        self.install()
        self.assertEqual((home / "data").read_text(), "personal data")
        self.assertEqual((home.stat().st_mode & 0o777), 0o700)
        self.assertEqual((self.target / "state/root").stat().st_mode & 0o777, 0o700)

    def test_conflicting_home_link_rejected_without_touching_its_target(self):
        self.setup_existing_state()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "data").write_text("keep")
        (self.target / "state/home").symlink_to(outside)
        with self.assertRaisesRegex(installer.InstallError, "mount point"):
            self.install()
        self.assertEqual((outside / "data").read_text(), "keep")
        self.assertFalse((self.target / "state/root").exists())
        self.assert_no_generation()

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


    def test_activation_requires_committed_metadata(self):
        base = self.target / "base"
        (base / self.version).mkdir(parents=True)
        with self.assertRaisesRegex(installer.InstallError, "metadata"):
            installer.activate(self.target, self.version)
        self.assertFalse((base / "current").is_symlink())

    def test_activation_sync_failure_keeps_selected_generation(self):
        self.setup_existing_state()
        original_sync = installer.sync_directory

        def fail_after_switch(path):
            if path == self.target / "base":
                link = self.target / "base/current"
                if link.is_symlink() and link.readlink().as_posix() == self.version:
                    raise OSError("injected fsync error after symlink swap")
            return original_sync(path)

        with mock.patch.object(installer, "sync_directory", side_effect=fail_after_switch):
            with self.assertRaisesRegex(OSError, "injected fsync"):
                self.install()
        self.assertEqual((self.target / "base/current").readlink().as_posix(),
                         self.version)
        self.assertTrue((self.target / "base" / self.version).is_dir())
        self.assertTrue((self.target / "releases" /
                         f"base-{self.version}.toml").is_file())
        self.assertTrue((self.target / "state/etc/a.conf").is_file())

    def test_recover_removes_only_recognized_staging(self):
        base = self.target / "base"
        base.mkdir()
        known = base / ".install-abandoned"
        known.mkdir()
        (known / ".mojt-install-stage").write_text(installer.STAGING_MARKER)
        (known / "partial").write_text("partial")
        unknown = base / ".install-unrelated"
        unknown.mkdir()
        (unknown / "something").write_text("keep")
        orphan = base / self.version
        orphan.mkdir()
        (orphan / "keep").write_text("important")

        installer.recover(self.target)

        self.assertFalse(known.exists())
        self.assertEqual((unknown / "something").read_text(), "keep")
        self.assertEqual((orphan / "keep").read_text(), "important")

    def test_install_syncs_rootfs_before_generation_publication(self):
        self.setup_existing_state()
        observed = []
        original_sync_tree = installer.sync_tree
        original_sync_directory = installer.sync_directory

        def record_tree(path):
            observed.append("tree")
            return original_sync_tree(path)

        def record_directory(path):
            if path == self.target / "base":
                destination = path / self.version
                if destination.exists():
                    observed.append("published")
            return original_sync_directory(path)

        with mock.patch.object(installer, "sync_tree", side_effect=record_tree):
            with mock.patch.object(installer, "sync_directory", side_effect=record_directory):
                self.install(no_activate=True)
        self.assertIn("tree", observed)
        self.assertIn("published", observed)
        self.assertLess(observed.index("tree"), observed.index("published"))



if __name__ == "__main__":
    unittest.main()
