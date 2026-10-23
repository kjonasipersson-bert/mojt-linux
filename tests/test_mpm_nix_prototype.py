#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""MPM/Nix orchestration regressions with a simulated backend; no real Nix."""

import contextlib
import copy
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("mpm_nix", str(REPO / "tools/mpm-nix-prototype"))
spec = importlib.util.spec_from_loader(loader.name, loader)
mpm = importlib.util.module_from_spec(spec)
loader.exec_module(mpm)


class MpmNixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mojt-nix-probe-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.root = self.directory / "experiment"
        self.store = self.directory / "store"
        self.store.mkdir()
        self.patch("STORE", self.store)
        self.calls = []
        self.registered_roots = set()
        self.source = self.object("0", "nixpkgs")
        (self.source / "nixpkgs").mkdir()
        (self.source / "nixpkgs/default.nix").write_text("{}")
        (self.source / "nixpkgs/.git-revision").write_text("a" * 40)
        self.output = self.object("1", "hello-1.0", command="hello", version="1.0")
        self.dependency = self.object("2", "libc")
        self.output2 = self.object("3", "hello-1.0", command="hello", version="1.0-rebuild")
        self.selected = [dict(name="hello", attribute="hello", commands=["hello"],
                              version="1.0", output=str(self.output))]
        self.patch("run", self.nix)
        self.manifest = self.directory / "ports.toml"
        self.write_manifest()

    def patch(self, name, value):
        patcher = mock.patch.object(mpm, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def object(self, character, name, command=None, version=None):
        path = self.store / (character * 32 + "-" + name)
        path.mkdir()
        if command:
            (path / "bin").mkdir()
            executable = path / "bin" / command
            executable.write_text(f"#!/bin/sh\nprintf '%s\\n' '{version}'\n")
            executable.chmod(0o755)
        return path

    def write_manifest(self, revision=None, attribute="hello", commands='["hello"]'):
        self.manifest.write_text(f'''format = 1
[nixpkgs]
path = "{self.source / 'nixpkgs'}"
revision = "{revision or 'a' * 40}"
system = "x86_64-linux"
[[ports]]
name = "hello"
attribute = "{attribute}"
commands = {commands}
''')

    def nix(self, *args):
        self.calls.append(args)
        if args[0] == "nix-instantiate":
            return json.dumps(self.selected)
        if args[1:3] == ("--query", "--hash"):
            return "\n".join("sha256:" + mpm.store_hash(p) for p in args[3:])
        if args[1:3] == ("--query", "--requisites"):
            return "\n".join((str(self.dependency), args[3]))
        if args[1] == "--realise":
            if "--dry-run" in args:
                return ""
            self.assertNotIn(".drv", args[2])
            link = Path(args[args.index("--add-root") + 1])
            if os.path.lexists(link):
                link.unlink()
            link.symlink_to(args[2])
            self.registered_roots.add(str(link))
            return str(link)
        self.fail(f"unexpected backend call: {args}")

    def cli(self, *args, success=True, answer="y"):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
                mock.patch("builtins.input", return_value=answer):
            result = mpm.main(["--root", str(self.root), "ports", *args])
        self.assertEqual(result, 0 if success else 1, stdout.getvalue() + stderr.getvalue())
        return stdout.getvalue() + stderr.getvalue()

    def update(self):
        return self.cli("update", "--manifest", str(self.manifest), "-y")

    def state(self):
        return json.loads(self.cli("status"))

    def hello(self, directory=None):
        return subprocess.check_output([str((directory or self.root / "current") / "bin/hello")],
                                       text=True).strip()

    def test_update_preserves_payload_selection_and_does_not_realise_output(self):
        self.update()
        self.assertEqual(self.state()["installed"], {})
        self.assertFalse(any(c[1] == "--realise" and c[2] == str(self.output) for c in self.calls))
        self.cli("install", "-y")
        old_generation = (self.root / "current").resolve()
        self.selected[0]["output"] = str(self.output2)
        self.update()
        self.assertEqual(self.hello(), "1.0")
        self.assertEqual(self.hello(old_generation), "1.0")

    def test_saved_catalog_used_after_manifest_disappears_and_backend_selection_changes(self):
        self.update()
        self.manifest.unlink()
        self.selected[0]["output"] = str(self.output2)
        self.calls.clear()
        self.cli("install", "hello", "-y")
        self.assertEqual(self.hello(), "1.0")
        self.assertFalse(any(c[0] == "nix-instantiate" for c in self.calls))

    def test_second_rebuild_retained_without_retargeting_default_and_exact_activation(self):
        self.update()
        self.cli("install", "-y")
        first = copy.deepcopy(self.state())
        old_generation = (self.root / "current").resolve()
        self.selected[0]["output"] = str(self.output2)
        self.update()
        self.cli("install", "-y")
        state = self.state()
        self.assertEqual(len(state["installed"]), 2)
        self.assertEqual(state["active"], first["active"])
        self.assertEqual(self.hello(), "1.0")
        for command in mpm.command_aliases(state):
            self.assertTrue(os.access(self.root / "current/bin" / command, os.X_OK))
        second = next(k for k in state["installed"] if k not in first["installed"])
        self.calls.clear()
        self.cli("activate", second, "-y")
        self.assertEqual(self.hello(), "1.0-rebuild")
        self.assertEqual(self.hello(old_generation), "1.0")
        self.assertFalse(any(c[0] == "nix-instantiate" for c in self.calls))
        self.assertEqual(self.state()["installed"], state["installed"])

    def test_gc_roots_stay_at_registered_paths_and_closure_has_hashes(self):
        self.update()
        self.cli("install", "-y")
        state = self.state()
        record = next(iter(state["installed"].values()))
        self.assertEqual({r["path"] for r in record["closure"]},
                         {str(self.output), str(self.dependency)})
        self.assertTrue(all(r["nar_hash"] for r in record["closure"]))
        for root in self.registered_roots:
            self.assertTrue(Path(root).is_symlink())
            self.assertTrue(Path(root).exists())
        self.assertIn(str(self.root / "gcroots" / self.source.name), self.registered_roots)
        self.assertIn(str(self.root / "gcroots" / self.output.name), self.registered_roots)

    def test_missing_gc_root_blocks_mutation_without_changing_current(self):
        self.update()
        self.cli("install", "-y")
        before = os.readlink(self.root / "current")
        (self.root / "gcroots" / self.output.name).unlink()
        self.cli("install", "-y", success=False)
        self.assertEqual(os.readlink(self.root / "current"), before)

    def test_preview_does_not_create_root_and_cancel_publishes_nothing(self):
        self.cli("update", "--manifest", str(self.manifest), "--dry-run")
        self.assertFalse(self.root.exists())
        self.cli("update", "--manifest", str(self.manifest), answer="n")
        self.assertFalse(os.path.lexists(self.root / "current"))
        self.assertEqual(list((self.root / "gcroots").iterdir()), [])

    def test_install_preview_does_not_register_payload_and_status_needs_no_nix(self):
        self.update()
        before = os.readlink(self.root / "current")
        self.cli("install", "--dry-run")
        self.assertEqual(os.readlink(self.root / "current"), before)
        self.assertEqual(len(self.registered_roots), 1)
        self.calls.clear()
        self.state()
        self.assertEqual(self.calls, [])

    def test_failed_second_payload_does_not_publish_partial_profile(self):
        self.update()
        self.cli("install", "-y")
        before = os.readlink(self.root / "current")
        self.selected[0]["output"] = str(self.output2)
        self.selected[0]["commands"] = ["missing"]
        self.write_manifest(commands='["missing"]')
        self.update()
        before = os.readlink(self.root / "current")
        self.cli("install", "-y", success=False)
        self.assertEqual(os.readlink(self.root / "current"), before)
        self.assertEqual(self.hello(), "1.0")

    def test_failure_at_publish_retains_old_generation_and_reusable_gc_roots(self):
        self.update()
        self.cli("install", "-y")
        self.selected[0]["output"] = str(self.output2)
        self.update()
        before = os.readlink(self.root / "current")
        with mock.patch.object(mpm.os, "replace", side_effect=OSError("injected failure")):
            self.cli("install", "-y", success=False)
        self.assertEqual(os.readlink(self.root / "current"), before)
        self.assertEqual(self.hello(), "1.0")
        self.assertTrue((self.root / "gcroots" / self.output2.name).exists())
        self.cli("install", "-y")
        self.assertEqual(len(self.state()["installed"]), 2)

    def test_command_conflict_detected_before_payload_import(self):
        self.update()
        self.cli("install", "-y")
        self.selected.append(dict(self.selected[0], name="another"))
        self.manifest.write_text(self.manifest.read_text() + '''
[[ports]]
name = "another"
attribute = "hello"
commands = ["hello"]
''')
        self.update()
        before = os.readlink(self.root / "current")
        self.calls.clear()
        self.cli("install", "another", "-y", success=False)
        self.assertEqual(os.readlink(self.root / "current"), before)
        self.assertEqual(self.calls, [])

    def test_changed_revision_rejected_before_evaluation(self):
        self.write_manifest(revision="b" * 40)
        self.cli("update", "--manifest", str(self.manifest), "-y", success=False)
        self.assertEqual(self.calls, [])
        self.assertFalse(os.path.lexists(self.root / "current"))

    def test_activate_never_installs_missing_request(self):
        self.update()
        self.calls.clear()
        before = os.readlink(self.root / "current")
        self.cli("activate", "hello@=missing", "-y", success=False)
        self.assertEqual(os.readlink(self.root / "current"), before)
        self.assertEqual(self.calls, [])

    def test_reinstall_is_idempotent(self):
        self.update()
        self.cli("install", "-y")
        before = os.readlink(self.root / "current")
        self.assertIn("No changes.", self.cli("install", "-y"))
        self.assertEqual(os.readlink(self.root / "current"), before)

    def test_unmanaged_root_and_alias_are_not_overwritten(self):
        self.root.mkdir()
        (self.root / "local-file").write_text("keep")
        self.cli("update", "--manifest", str(self.manifest), "-y", success=False)
        self.assertEqual((self.root / "local-file").read_text(), "keep")
        (self.root / "local-file").unlink()
        self.update()
        self.cli("install", "-y")
        command = self.root / "current/bin/hello"
        command.unlink()
        command.write_text("local command")
        self.cli("install", "-y", success=False)
        self.assertEqual(command.read_text(), "local command")

    def test_unsafe_attribute_and_command_rejected_before_nix(self):
        for attribute, commands in (("hello;bad", '["hello"]'), ("hello", '["../bad"]')):
            with self.subTest(attribute=attribute, commands=commands):
                self.write_manifest(attribute=attribute, commands=commands)
                self.cli("update", "--manifest", str(self.manifest), "-y", success=False)
                self.assertEqual(self.calls, [])

    def test_derivations_and_nonstore_paths_rejected(self):
        for value in ("/usr/bin/hello", str(self.store / ("0" * 32 + "-a.drv")),
                      str(self.output / "bin/hello")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                mpm.store_path(value)


if __name__ == "__main__":
    unittest.main()
