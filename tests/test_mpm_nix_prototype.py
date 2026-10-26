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
        self.attributes = {"hello": dict(version="1.0", output=str(self.output), description="Hello")}
        self.materialize = {}
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
            request = json.loads(args[args.index("requestJSON") + 1])
            expression = args[args.index("--expr") + 1]
            if expression == mpm.RESOLVE:
                return json.dumps(self.attributes[request["attribute"]])
            if expression == mpm.SEARCH:
                return json.dumps(dict(matches=[dict(attribute="hello", version="1.0",
                                                     description="Hello")], matchedAttributes=1))
            return json.dumps(self.selected)
        if args[1:3] == ("--query", "--hash"):
            return "\n".join("sha256:" + mpm.store_hash(p) for p in args[3:])
        if args[1:3] == ("--query", "--requisites"):
            return "\n".join((str(self.dependency), args[3]))
        if args[1] == "--realise":
            if "--dry-run" in args:
                return ""
            if args[2] in self.materialize:
                self.materialize.pop(args[2])()
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

    def variant(self, attribute, character, version):
        output = self.object(character, "hello-" + version, command="hello", version=version)
        self.attributes[attribute] = dict(version=version, output=str(output), description=attribute)
        self.cli("install", "hello", "--attribute", attribute, "-y")
        return next(k for k, r in self.state()["installed"].items() if r["attribute"] == attribute)

    def test_generic_install_uses_pinned_source_and_discovers_commands_without_toml_entry(self):
        self.manifest.write_text(self.manifest.read_text().split("[[ports]]")[0])
        self.update()
        source = self.state()["catalog"]["source"]
        self.manifest.unlink()
        extra = self.output / "bin/hello-extra"
        extra.symlink_to("hello")
        self.cli("install", "hello", "-y")
        state = self.state()
        record = next(iter(state["installed"].values()))
        self.assertEqual(record["commands"], ["hello", "hello-extra"])
        self.assertEqual(record["source"], source)
        self.assertEqual(self.hello(), "1.0")
        self.assertTrue((self.root / "current/bin/hello-extra").exists())
        self.assertEqual(state["catalog"]["packages"], {})
        requests = [json.loads(c[c.index("requestJSON") + 1]) for c in self.calls
                    if c[0] == "nix-instantiate"]
        self.assertTrue(all(r["source"] == source for r in requests))

    def test_search_info_and_list_are_read_only_and_show_source(self):
        self.update()
        before = os.readlink(self.root / "current")
        self.calls.clear()
        found = json.loads(self.cli("search", "HeL", "--json"))
        self.assertEqual(found["source"]["revision"], "a" * 40)
        self.assertEqual(found["matches"][0]["attribute"], "hello")
        record = json.loads(self.cli("info", "hello", "--json"))
        self.assertEqual(record["output"], str(self.output))
        self.assertEqual(json.loads(self.cli("list", "--json")), [])
        self.assertEqual(os.readlink(self.root / "current"), before)
        self.assertFalse(any(c[0] == "nix-store" and c[1] == "--realise" for c in self.calls))

    def test_update_without_manifest_reuses_saved_pin_and_never_reads_channel(self):
        self.update()
        self.manifest.unlink()
        self.calls.clear()
        before = os.readlink(self.root / "current")
        self.assertIn("No changes.", self.cli("update", "-y"))
        self.assertEqual(os.readlink(self.root / "current"), before)
        self.assertEqual(self.calls, [])

    def test_initial_update_can_use_system_source_manifest(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = mpm.main(["--root", str(self.root), "--source-manifest", str(self.manifest),
                             "ports", "update", "-y"])
        self.assertEqual(code, 0)
        self.assertIsNotNone(self.state()["catalog"])

    def test_initial_preview_accepts_empty_mktemp_directory_without_writing(self):
        self.root.mkdir()
        self.cli("update", "--manifest", str(self.manifest), "--dry-run")
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(self.state()["installed"], {})

    def test_discovery_after_import_and_late_conflict_preserve_old_profile(self):
        self.update()
        self.cli("install", "hello", "-y")
        before = os.readlink(self.root / "current")
        output = self.store / ("4" * 32 + "-other-2.0")
        self.attributes["other"] = dict(version="2.0", output=str(output), description="Collision")
        self.materialize[str(output)] = lambda: self.object("4", "other-2.0", command="hello", version="2.0")
        preview = self.cli("install", "other", "--dry-run")
        self.assertIn("discover after binary import", preview)
        self.assertFalse(output.exists())
        self.cli("install", "other", "-y", success=False)
        self.assertTrue(output.exists())
        self.assertEqual(os.readlink(self.root / "current"), before)
        self.assertEqual(self.hello(), "1.0")
        self.assertEqual(len(self.state()["installed"]), 1)
        # The same imported output can subsequently be retained without claiming defaults.
        self.cli("install", "other", "--no-activate", "-y")
        self.assertEqual(self.hello(), "1.0")
        self.assertEqual(len(self.state()["installed"]), 2)

    def test_remove_active_uses_activation_history_before_newer_never_active_version(self):
        self.update()
        a = self.variant("a", "4", "1.0")
        saved = (self.root / "current").resolve()
        b = self.variant("b", "5", "2.0")
        self.cli("activate", b, "-y")
        c = self.variant("c", "6", "99.0")
        preview = self.cli("remove", b, "--dry-run")
        self.assertIn("Activate: hello -> " + a, preview)
        self.cli("remove", b, "-y")
        self.assertEqual(self.state()["active"]["hello"], a)
        self.assertEqual(set(self.state()["installed"]), {a, c})
        self.assertEqual(self.hello(saved), "1.0")
        self.assertTrue((self.root / "gcroots" / ("5" * 32 + "-hello-2.0")).exists())
        self.cli("remove", a, "-y")
        self.assertEqual(self.state()["active"]["hello"], c)
        self.cli("remove", "hello", "-y")
        self.assertEqual(self.state()["active"], {})
        self.assertEqual(self.state()["installed"], {})
        self.assertFalse((self.root / "current/bin/hello").exists())
        self.assertEqual(self.hello(saved), "1.0")
        self.assertFalse(any("--gc" in call or "--delete" in call for call in self.calls))

    def test_remove_active_uses_last_activation_rather_than_install_or_version_order(self):
        self.update()
        a = self.variant("a", "4", "9.0")
        b = self.variant("b", "5", "2.0")
        c = self.variant("c", "6", "1.0")
        self.cli("activate", c, "-y")
        self.cli("activate", b, "-y")
        self.cli("activate", a, "-y")
        self.cli("remove", a, "-y")
        self.assertEqual(self.state()["active"]["hello"], b)
        self.assertEqual(self.hello(), "2.0")

    def test_never_active_fallback_uses_install_order_and_multi_remove_excludes_all_targets(self):
        self.update()
        a = self.variant("a", "4", "1.0")
        b = self.variant("b", "5", "99.0")
        c = self.variant("c", "6", "2.0")
        self.cli("remove", a, "-y")
        self.assertEqual(self.state()["active"]["hello"], c)
        self.cli("install", "hello", "--attribute", "a", "-y")
        self.cli("remove", a, c, "-y")
        self.assertEqual(self.state()["active"]["hello"], b)

    def test_remove_inactive_and_repeat_activate_do_not_reorder_history(self):
        self.update()
        a = self.variant("a", "4", "1.0")
        b = self.variant("b", "5", "1.0-rebuild")
        active_history = self.state()["history"]["activated"]
        self.cli("activate", a, "-y")  # Explicit exact activation pins, without reordering.
        self.assertEqual(self.state()["history"]["activated"], active_history)
        before = os.readlink(self.root / "current")
        self.assertIn("No changes.", self.cli("activate", a, "-y"))
        self.assertEqual(os.readlink(self.root / "current"), before)
        active_history = self.state()["history"]["activated"]
        self.cli("remove", b, "-y")
        self.assertEqual(self.state()["active"]["hello"], a)
        self.assertEqual(self.state()["history"]["activated"], active_history)

    def test_ambiguous_remove_and_activation_require_exact_identity(self):
        self.update()
        self.variant("a", "4", "1.0")
        self.variant("b", "5", "2.0")
        before = os.readlink(self.root / "current")
        for action in ("activate", "remove"):
            self.assertIn("multiple versions", self.cli(action, "hello", "-y", success=False))
        self.assertEqual(os.readlink(self.root / "current"), before)

    def test_remove_preview_cancel_and_publish_failure_leave_history_and_default_unchanged(self):
        self.update()
        a = self.variant("a", "4", "1.0")
        self.variant("b", "5", "2.0")
        before = self.state()
        profile = os.readlink(self.root / "current")
        self.cli("remove", a, "--dry-run")
        self.cli("remove", a, answer="n")
        with mock.patch.object(mpm.os, "replace", side_effect=OSError("injected failure")):
            self.cli("remove", a, "-y", success=False)
        self.assertEqual(self.state(), before)
        self.assertEqual(os.readlink(self.root / "current"), profile)
        self.assertEqual(self.hello(), "1.0")

    def test_legacy_history_baseline_is_explicit_and_read_only_commands_do_not_migrate(self):
        self.update()
        a = self.variant("a", "4", "1.0")
        b = self.variant("b", "5", "2.0")
        state = self.state()
        del state["history"]
        (self.root / "current/state.json").write_text(json.dumps(state))
        self.assertNotIn("history", self.state())
        self.assertIn("earlier activation order is unknown", self.cli("remove", a, "-y"))
        self.assertEqual(self.state()["active"]["hello"], b)

    def test_conflicting_removal_fallback_aborts_without_removing_active_version(self):
        self.update()
        a = self.variant("a", "4", "1.0")
        output = self.object("5", "hello-2.0", command="hello", version="2.0")
        (output / "bin/extra").symlink_to("hello")
        self.attributes["b"] = dict(version="2.0", output=str(output), description="b")
        self.cli("install", "hello", "--attribute", "b", "-y")
        b = next(k for k, r in self.state()["installed"].items() if r["attribute"] == "b")
        self.cli("activate", b, "-y")
        self.cli("activate", a, "-y")
        other = self.object("6", "other-1.0", command="extra", version="other")
        self.attributes["other"] = dict(version="1.0", output=str(other), description="other")
        self.cli("install", "other", "-y")
        before = self.state()
        self.assertIn("command alias conflict: extra", self.cli("remove", a, "-y", success=False))
        self.assertEqual(self.state(), before)
        self.assertEqual(self.hello(), "1.0")

    def test_profile_flush_failure_before_commit_preserves_old_selection(self):
        self.update()
        a = self.variant("a", "4", "1.0")
        self.variant("b", "5", "2.0")
        before = os.readlink(self.root / "current")
        with mock.patch.object(mpm, "sync_directory", side_effect=OSError("flush failed")):
            self.cli("remove", a, "-y", success=False)
        self.assertEqual(os.readlink(self.root / "current"), before)
        self.assertEqual(self.hello(), "1.0")

    def test_post_commit_flush_failure_retains_selected_generation_and_reports_uncertainty(self):
        self.update()
        self.variant("a", "4", "1.0")
        b = self.variant("b", "5", "2.0")
        original = mpm.sync_directory

        def fail_at_root(path):
            if path == self.root:
                raise OSError("post-commit flush failed")
            original(path)

        with mock.patch.object(mpm, "sync_directory", side_effect=fail_at_root):
            result = self.cli("activate", b, "-y", success=False)
        self.assertIn("Profile selection may have committed", result)
        self.assertEqual(self.state()["active"]["hello"], b)
        self.assertEqual(self.hello(), "2.0")

    def test_reserved_manager_commands_can_only_be_retained_inactive(self):
        self.update()
        output = self.object("4", "other-1.0", command="mpm", version="other")
        self.attributes["other"] = dict(version="1.0", output=str(output), description="other")
        self.assertIn("reserved System management command", self.cli("install", "other", "-y", success=False))
        self.cli("install", "other", "--no-activate", "-y")
        self.assertNotIn("other", self.state()["active"])


    def prepare_upgrade(self, version="2.0"):
        self.update()
        self.cli("install", "hello", "-y")
        old = copy.deepcopy(self.state())
        self.selected[0].update(version=version, output=str(self.output2))
        self.update()
        return old

    def test_upgrade_retains_old_artifact_and_advances_following_selection(self):
        old = self.prepare_upgrade()
        captured = next(self.root.glob("profiles/*/state.json"))
        source = self.state()["catalog"]["source"]
        self.cli("upgrade", "hello", "-y")
        state = self.state()
        old_key = old["active"]["hello"]
        new_key = state["active"]["hello"]
        self.assertNotEqual(new_key, old_key)
        self.assertIn(old_key, state["installed"])
        self.assertEqual(state["installed"][old_key], old["installed"][old_key])
        self.assertEqual(state["requests"]["hello:hello"]["target"], new_key)
        self.assertEqual(state["selection_policy"]["hello"], "hello:hello")
        self.assertEqual(state["catalog"]["source"], source)
        self.assertTrue(captured.exists())
        self.assertEqual(self.hello(), "1.0-rebuild")
        before = os.readlink(self.root / "current")
        self.assertIn("No changes.", self.cli("upgrade", "-y"))
        self.assertEqual(os.readlink(self.root / "current"), before)

    def test_exact_active_pin_survives_upgrade_and_can_explicitly_follow_again(self):
        old = self.prepare_upgrade()
        old_key = old["active"]["hello"]
        self.cli("activate", old_key, "-y")
        self.cli("upgrade", "-y")
        state = self.state()
        self.assertEqual(state["active"], old["active"])
        self.assertIsNone(state["selection_policy"]["hello"])
        new_key = state["requests"]["hello:hello"]["target"]
        self.cli("activate", old_key, "--follow", "-y", success=False)
        self.cli("activate", new_key, "--follow", "-y")
        self.assertEqual(self.state()["selection_policy"]["hello"], "hello:hello")
        self.assertEqual(self.state()["active"]["hello"], new_key)

    def test_upgrade_preview_cancel_and_failures_leave_snapshot_and_history(self):
        self.prepare_upgrade()
        before = os.readlink(self.root / "current")
        roots = set(self.registered_roots)
        records = self.cli("history", "--json")
        self.cli("upgrade", "--dry-run")
        self.cli("upgrade", answer="n")
        self.assertEqual(set(self.registered_roots), roots)
        self.assertEqual(os.readlink(self.root / "current"), before)
        with mock.patch.object(mpm.os, "replace", side_effect=OSError("injected before commit")):
            self.cli("upgrade", "-y", success=False)
        self.assertEqual(os.readlink(self.root / "current"), before)
        self.assertEqual(self.cli("history", "--json"), records)
        self.assertEqual(self.hello(), "1.0")

    def test_upgrade_refuses_downgrades_unknown_versions_and_untracked_names(self):
        for version in ("0.9", "2.0-rc1"):
            with self.subTest(version=version):
                if not self.root.exists():
                    self.prepare_upgrade(version)
                else:
                    self.selected[0]["version"] = version
                    self.update()
                before = os.readlink(self.root / "current")
                self.cli("upgrade", "-y", success=False)
                self.assertEqual(os.readlink(self.root / "current"), before)
        self.assertIn("no recorded request", self.cli("upgrade", "missing", "-y", success=False))

    def test_equal_numeric_version_rebuild_upgrades_without_replacing_old_build(self):
        self.prepare_upgrade("1.0")
        self.cli("upgrade", "-y")
        self.assertEqual(len(self.state()["installed"]), 2)
        self.assertEqual(self.hello(), "1.0-rebuild")

    def test_upgrade_uses_saved_snapshot_not_changed_backend_catalog(self):
        self.prepare_upgrade()
        self.selected[0]["output"] = str(self.output)  # Unpublished backend change.
        self.calls.clear()
        self.cli("upgrade", "-y")
        self.assertEqual(self.hello(), "1.0-rebuild")
        self.assertFalse(any(c[0] == "nix-instantiate" for c in self.calls))

    def test_multiple_requests_and_inactive_request_upgrade_independently(self):
        self.update()
        a = self.variant("a", "4", "1.0")
        b = self.variant("b", "5", "1.0")
        new_a = self.object("6", "hello-a-2.0", command="hello", version="2.0-a")
        new_b = self.object("7", "hello-b-2.0", command="hello", version="2.0-b")
        self.attributes["a"].update(output=str(new_a), version="2.0")
        self.attributes["b"].update(output=str(new_b), version="2.0")
        self.cli("upgrade", "hello", "-y")
        state = self.state()
        self.assertEqual(len(state["requests"]), 2)
        self.assertEqual(len(state["installed"]), 4)
        self.assertNotEqual(state["requests"]["hello:b"]["target"], b)
        self.assertEqual(state["active"]["hello"], state["requests"]["hello:a"]["target"])
        self.assertIn(a, state["installed"])
        self.assertEqual(self.hello(), "2.0-a")

    def test_failed_multi_request_upgrade_does_not_publish_first_success(self):
        self.update()
        self.variant("a", "4", "1.0")
        self.variant("b", "5", "1.0")
        new_a = self.object("6", "hello-a-2.0", command="hello", version="2.0-a")
        self.attributes["a"].update(output=str(new_a), version="2.0")
        self.attributes["b"].update(output=str(self.output2), version="0.9")
        before = self.state()
        self.cli("upgrade", "-y", success=False)
        self.assertEqual(self.state(), before)

    def test_legacy_migration_does_not_infer_intent_or_active_following(self):
        self.update()
        self.cli("install", "-y")
        path = self.root / "current/state.json"
        legacy = self.state()
        legacy["format"] = 1
        del legacy["requests"], legacy["selection_policy"]
        path.write_text(json.dumps(legacy))
        self.assertEqual(self.state()["format"], 1)
        self.cli("upgrade", "-y", success=False)
        self.cli("install", "hello", "--dry-run")
        self.assertEqual(self.state()["format"], 1)
        self.cli("install", "hello", "-y")
        state = self.state()
        self.assertEqual(state["format"], 2)
        self.assertEqual(state["active"], legacy["active"])
        self.assertIsNone(state["selection_policy"]["hello"])
        self.cli("activate", "hello", "--follow", "-y")
        self.assertEqual(self.state()["selection_policy"]["hello"], "hello:hello")

    def test_history_records_only_commits_and_needs_no_nix(self):
        self.prepare_upgrade()
        self.cli("upgrade", "-y")
        self.calls.clear()
        rows = json.loads(self.cli("history", "--json"))
        self.assertEqual([r["sequence"] for r in rows], [4, 3, 2, 1])
        self.assertEqual([r["action"] for r in rows], ["upgrade", "update", "install", "update"])
        self.assertEqual(rows[0]["parent"], rows[1]["profile"])
        self.assertEqual(rows[0]["after"]["requests"], self.state()["requests"])
        self.assertEqual(rows[0]["uid"], os.getuid())
        self.assertEqual(len(json.loads(self.cli("history", "--json", "--limit", "1"))), 1)
        self.assertEqual(self.calls, [])
        self.cli("history", "--limit", "0", success=False)

    def test_remove_reconciles_request_and_policy_without_dangling_targets(self):
        old = self.prepare_upgrade()
        self.cli("upgrade", "-y")
        latest = self.state()["active"]["hello"]
        self.cli("remove", latest, "-y")
        self.assertEqual(self.state()["requests"]["hello:hello"]["target"], old["active"]["hello"])
        self.cli("remove", "hello", "-y")
        self.assertEqual(self.state()["requests"], {})
        self.assertEqual(self.state()["selection_policy"], {})

    def test_upgrade_retains_intentionally_inactive_request(self):
        self.update()
        self.cli("install", "hello", "--no-activate", "-y")
        self.selected[0].update(output=str(self.output2), version="2.0")
        self.update()
        self.cli("upgrade", "-y")
        state = self.state()
        self.assertEqual(state["active"], {})
        self.assertEqual(len(state["installed"]), 2)
        self.assertEqual(len(state["requests"]), 1)

    def test_upgrade_filter_changes_only_named_request_and_not_other_area_files(self):
        self.update()
        self.cli("install", "hello", "-y")
        other = self.object("4", "less-1", command="less", version="1")
        self.attributes["less"] = dict(output=str(other), version="1", description="Less")
        self.cli("install", "less", "-y")
        prior = self.state()
        sentinel = self.directory / "system-deployment.json"
        sentinel.write_text('{"selected":"system-A","running":"system-B"}')
        self.selected[0].update(output=str(self.output2), version="2.0")
        self.update()
        self.cli("upgrade", "hello", "-y")
        state = self.state()
        self.assertEqual(state["active"]["less"], prior["active"]["less"])
        self.assertEqual(state["requests"]["less:less"], prior["requests"]["less:less"])
        self.assertEqual(sentinel.read_text(), '{"selected":"system-A","running":"system-B"}')


if __name__ == "__main__":
    unittest.main()
