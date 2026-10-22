#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Backend-free MPM acceptance tests; no root, network, or real packages."""

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools/mpm-prototype"
FIXTURES = REPO / "tests/fixtures/mpm"
loader = importlib.machinery.SourceFileLoader("mpm_prototype", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
mpm = importlib.util.module_from_spec(spec)
loader.exec_module(mpm)


class MpmPrototypeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mojt-mpm-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "experiment"
        self.cli("update", "--catalog", str(FIXTURES / "catalog-1.toml"), "-y")

    def command(self, *args):
        return [sys.executable, str(SCRIPT), "--root", str(self.root), "ports", *args]

    def cli(self, *args, success=True, input=None):
        result = subprocess.run(self.command(*args), input=input, text=True, capture_output=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def update(self):
        self.cli("update", "--catalog", str(FIXTURES / "catalog-2.toml"), "-y")

    def run_alias(self, alias, version):
        result = subprocess.run([str(self.root / "current/bin" / alias)],
                                text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(), f"{alias.split('-')[0]} {version}")

    def state(self):
        return json.loads(self.cli("status").stdout)

    def test_worked_example_parallel_series_upgrade_and_old_aliases(self):
        first = self.cli("install", "blender@4.9", "-y")
        self.assertIn("Active: blender = blender@4.9", first.stdout)
        self.run_alias("blender", "4.9.12-r1")
        self.cli("install", "blender@5.3", "-y")
        self.run_alias("blender", "4.9.12-r1")
        self.run_alias("blender-5.3", "5.3.7-r1")
        self.cli("activate", "blender@5.3", "-y")
        self.run_alias("blender", "5.3.7-r1")
        self.update()
        self.run_alias("blender", "5.3.7-r1")
        self.cli("upgrade", "-y")
        self.run_alias("blender", "5.3.8-r1")
        self.run_alias("blender-4.9", "4.9.13-r1")
        self.run_alias("blender-4.9.12-r1", "4.9.12-r1")
        self.run_alias("blender-5.3.7-r1", "5.3.7-r1")
        self.assertEqual(self.state()["active"]["blender"], "blender@5.3")

    def test_install_newer_in_same_series_does_not_retarget(self):
        self.cli("install", "blender@4.9", "-y")
        self.update()
        self.cli("install", "blender@4.9", "-y")
        self.run_alias("blender", "4.9.12-r1")
        self.run_alias("blender-4.9", "4.9.12-r1")
        self.run_alias("blender-4.9.13-r1", "4.9.13-r1")
        self.cli("upgrade", "-y")
        self.run_alias("blender-4.9", "4.9.13-r1")
        self.run_alias("blender", "4.9.13-r1")

    def test_explicit_activation_selects_newest_installed_not_catalog(self):
        self.cli("install", "blender@4.9", "-y")
        self.update()
        self.cli("activate", "blender@4.9", "-y")
        self.run_alias("blender", "4.9.12-r1")
        self.cli("install", "blender@=4.9.13-r1", "-y")
        self.run_alias("blender", "4.9.12-r1")
        self.cli("activate", "blender@4.9", "-y")
        self.run_alias("blender", "4.9.13-r1")

    def test_exact_first_install_stays_pinned_through_series_upgrade(self):
        self.cli("install", "blender@=4.9.12-r1", "-y")
        self.cli("install", "blender@4.9", "-y")
        self.update()
        self.cli("upgrade", "-y")
        self.run_alias("blender", "4.9.12-r1")
        self.run_alias("blender-4.9", "4.9.13-r1")
        self.assertEqual(self.state()["active"]["blender"], "blender@=4.9.12-r1")

    def test_exact_requests_never_upgrade_and_exact_matching_is_literal(self):
        self.cli("install", "gimp@=3.0.9-r1", "-y")
        self.update()
        before = os.readlink(self.root / "current")
        self.cli("upgrade", "-y")
        self.assertEqual(os.readlink(self.root / "current"), before)
        self.cli("install", "gimp@=3.0", "-y", success=False)
        self.assertEqual(len(self.state()["installed"]), 1)

    def test_series_activation_of_exact_install_does_not_change_upgrade_intent(self):
        self.cli("install", "blender@=4.9.12-r1", "-y")
        self.cli("activate", "blender@4.9", "-y")
        self.run_alias("blender-4.9", "4.9.12-r1")
        self.update()
        self.cli("upgrade", "-y")
        self.run_alias("blender", "4.9.12-r1")
        self.assertEqual(self.state()["requests"], ["blender@=4.9.12-r1"])

    def test_numeric_ordering_rebuilds_and_stable_filter(self):
        self.update()
        self.cli("install", "gimp@3.0", "-y")
        self.run_alias("gimp", "3.0.10-r2")
        self.cli("install", "blender@5.3", "-y")
        self.run_alias("blender", "5.3.8-r1")
        self.cli("install", "blender@=5.3.99-r1", "-y")
        self.run_alias("blender-5.3.99-r1", "5.3.99-r1")
        self.run_alias("blender", "5.3.8-r1")

    def test_selectors_reject_ambiguous_prefixes_and_unsafe_names(self):
        for request in ("gimp@3.00", "gimp@13.0", "gimp@3.0rc1", "../gimp@3.0",
                        "gimp@3.0-r2", "gimp", "gimp@", "gimp@=../../other"):
            with self.subTest(request=request):
                self.cli("install", request, "-y", success=False)
        record = dict(name="gimp", version="3.0.10-r2", channel="stable")
        self.assertTrue(mpm.matches(record, "gimp@3.0"))
        self.assertFalse(mpm.matches(record, "gimp@3.1"))
        self.assertFalse(mpm.matches(record, "gimp@13.0"))

    def test_activate_missing_version_never_installs(self):
        before = self.state()
        self.cli("activate", "blender@5.3", "-y", success=False)
        self.assertEqual(self.state(), before)
        self.assertEqual(list((self.root / "store").iterdir()), [])

    def test_install_requires_explicit_snapshot_update(self):
        self.root = Path(self.tmp.name) / "fresh"
        result = self.cli("install", "blender@4.9", "-y", success=False)
        self.assertIn("run ports update", result.stderr)
        self.assertFalse((self.root / "current").exists())

    def test_local_snapshot_is_copied_and_never_refreshed_implicitly(self):
        catalog = Path(self.tmp.name) / "catalog.toml"
        catalog.write_bytes((FIXTURES / "catalog-1.toml").read_bytes())
        self.cli("update", "--catalog", str(catalog), "-y")
        catalog.write_bytes((FIXTURES / "catalog-2.toml").read_bytes())
        self.cli("install", "gimp@3.0", "-y")
        self.cli("upgrade", "-y")
        self.run_alias("gimp", "3.0.9-r1")
        self.assertEqual(self.state()["catalog"]["snapshot"], "experiment-1")

    def test_pin_and_old_generation_survive_upgrade(self):
        self.cli("install", "blender@4.9", "-y")
        record = self.state()["installed"]["blender@=4.9.12-r1"]
        pin_file = Path(self.tmp.name) / "project-pin.json"
        # A test reference, not an implemented project profile or lock format.
        pin_file.write_text(json.dumps(dict(artifact=record, dependencies=[])))
        saved_pin = pin_file.read_bytes()
        old = (self.root / "current").resolve()
        command = mpm.object_command(self.root, record)
        saved_payload = command.read_bytes()
        self.update()
        self.cli("upgrade", "-y")
        self.assertEqual(command.read_bytes(), saved_payload)
        self.assertEqual(pin_file.read_bytes(), saved_pin)
        self.assertEqual(subprocess.check_output([str(old / "bin/blender")], text=True).strip(),
                         "blender 4.9.12-r1")
        self.cli("activate", "blender@=4.9.12-r1", "-y")
        self.run_alias("blender", "4.9.12-r1")

    def test_publication_failure_keeps_complete_previous_profile(self):
        self.cli("install", "blender@4.9", "-y")
        self.update()
        old = os.readlink(self.root / "current")
        state = mpm.load_state(self.root)
        proposed = mpm.plan(state, "upgrade")
        profiles = set((self.root / "profiles").iterdir())
        with mock.patch.object(mpm.os, "replace", side_effect=OSError("injected publication failure")):
            with self.assertRaises(OSError):
                mpm.publish(self.root, proposed)
        self.assertEqual(os.readlink(self.root / "current"), old)
        self.assertEqual(mpm.load_state(self.root), state)
        self.assertEqual(set((self.root / "profiles").iterdir()), profiles)
        self.run_alias("blender", "4.9.12-r1")
        self.cli("upgrade", "-y")  # Retained objects can be reused on retry.
        self.run_alias("blender", "4.9.13-r1")

    def test_dry_run_and_declined_upgrade_preserve_profile(self):
        self.cli("install", "blender@4.9", "-y")
        self.update()
        before = os.readlink(self.root / "current")
        preview = self.cli("upgrade", "--dry-run")
        self.assertIn("blender@=4.9.13-r1", preview.stdout)
        self.cli("upgrade", input="n\n")
        self.assertEqual(os.readlink(self.root / "current"), before)
        self.run_alias("blender", "4.9.12-r1")
        self.root = Path(self.tmp.name) / "preview-only"
        self.cli("update", "--catalog", str(FIXTURES / "catalog-1.toml"), "--dry-run")
        self.assertFalse(self.root.exists())

    def test_invalid_catalog_does_not_publish(self):
        catalog = Path(self.tmp.name) / "bad.toml"
        before = os.readlink(self.root / "current")
        for text in ("format = 2\n", "not valid toml!", (FIXTURES / "catalog-1.toml").read_text()
                     .replace('version = "4.9.12-r1"', 'version = "../escape"')):
            catalog.write_text(text)
            self.cli("update", "--catalog", str(catalog), "-y", success=False)
            self.assertEqual(os.readlink(self.root / "current"), before)

    def test_unmanaged_root_and_current_paths_are_preserved(self):
        (self.root / "current").unlink()
        (self.root / "current").write_text("administrator owned")
        self.cli("install", "blender@4.9", "-y", success=False)
        self.assertEqual((self.root / "current").read_text(), "administrator owned")
        self.root = Path(self.tmp.name) / "unmanaged"
        self.root.mkdir()
        local = self.root / "blender"
        local.write_text("local command")
        self.cli("update", "--catalog", str(FIXTURES / "catalog-1.toml"), "-y", success=False)
        self.assertEqual(local.read_text(), "local command")
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_unmanaged_bin_collision_is_preserved(self):
        self.cli("install", "blender@4.9", "-y")
        conflict = self.root / "current/bin/gimp"
        conflict.write_text("local command")
        before = os.readlink(self.root / "current")
        self.cli("install", "gimp@3.0", "-y", success=False)
        self.assertEqual(conflict.read_text(), "local command")
        self.assertEqual(os.readlink(self.root / "current"), before)

    def test_corrupt_store_object_is_not_overwritten(self):
        self.cli("install", "blender@4.9", "-y")
        command = (self.root / "current/bin/blender").resolve()
        self.assertEqual(command.stat().st_mode & 0o222, 0)
        command.chmod(0o755)
        command.write_text("modified locally")
        before = os.readlink(self.root / "current")
        self.cli("install", "blender@4.9", "-y", success=False)
        self.assertEqual(command.read_text(), "modified locally")
        self.assertEqual(os.readlink(self.root / "current"), before)

    def test_parallel_writers_do_not_lose_installs(self):
        children = [subprocess.Popen(self.command("install", request, "-y"),
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    for request in ("blender@4.9", "gimp@3.0")]
        for child in children:
            stdout, stderr = child.communicate(timeout=15)
            self.assertEqual(child.returncode, 0, stdout + stderr)
        self.run_alias("blender", "4.9.12-r1")
        self.run_alias("gimp", "3.0.9-r1")
        self.assertEqual(len(self.state()["requests"]), 2)

    def test_other_areas_are_rejected(self):
        for area in ("base", "system", "kernel"):
            result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root),
                                     area, "upgrade", "-y"], capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
