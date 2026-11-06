# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Request/alias policy tested with opaque non-Nix artifacts and no backend."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import mpm_selection as core
import mpm_selector_ports as ports


class SelectorPortsTests(unittest.TestCase):
    def setUp(self):
        self.value = dict(format=core.FORMAT, area="ports", name="apps", channel="stable", platform="test",
            sources={"a": dict(backend="archive", identity={"snapshot": "one"})}, candidates=[])
        for version in ("1.0", "1.1", "2.0"):
            self.value["candidates"].append(dict(name="paint", release_id=version, upstream_version=version,
                version_scheme="dotted-v1", stability="stable", source="a", artifact="object:" + version,
                integrity={"digest": "content:" + version}))
        self.catalog = core.Catalog.from_dict(self.value)
        self.state = dict(format=2, catalog=None, installed={}, active={}, requests={}, selection_policy={})
        self.state, _ = ports.metadata(self.state, self.value, [], [])

    def item(self, request):
        selection = core.resolve(self.catalog, request)
        return ("opaque-key:" + selection.candidate.artifact,
                dict(name="paint", commands=["paint", "paint-tool"], payload={"opaque": True}), selection)

    def test_distinct_series_requests_export_all_commands_without_backend_identity_rules(self):
        old = copy.deepcopy(self.state)
        state = ports.install(self.state, [self.item("paint@1"), self.item("paint@2")])
        self.assertEqual(self.state, old)
        self.assertEqual(len(state["requests"]), 2)
        self.assertEqual(set(ports.aliases(state)), {"paint-1", "paint-tool-1", "paint-2", "paint-tool-2"})
        self.assertEqual(state["installed"][state["active"]["paint"]]["payload"], {"opaque": True})

    def test_later_install_retains_accepted_target_until_explicit_activation(self):
        self.catalog = core.Catalog.from_dict(dict(self.value, candidates=self.value["candidates"][:1]))
        state = ports.install(self.state, [self.item("paint@1")])
        before = copy.deepcopy(state)
        self.catalog = core.Catalog.from_dict(self.value)
        state = ports.install(state, [self.item("paint@1")])
        self.assertEqual(state["requests"], before["requests"])
        self.assertEqual(state["active"], before["active"])
        self.assertEqual(len(state["installed"]), 2)
        state = ports.activate(state, self.item("paint@1"))
        self.assertEqual(state["active"]["paint"], self.item("paint@1")[0])

    def test_exact_literal_activation_does_not_destroy_series_request(self):
        item = self.item("paint@1")
        state = ports.install(self.state, [item])
        before = copy.deepcopy(state["requests"])
        state = ports.activate(state, item, literal=True)
        self.assertIsNone(state["selection_policy"]["paint"])
        self.assertEqual(state["requests"], before)
        state = ports.activate(state, item, literal=True, follow=True)
        self.assertEqual(state["selection_policy"]["paint"], ports.request_id(item[2]))

    def test_exact_selector_cannot_become_following_and_ambiguity_is_explicit(self):
        state = ports.install(self.state, [self.item("paint@=1.0")])
        with self.assertRaisesRegex(ValueError, "cannot unpin"):
            ports.activate(state, self.item("paint@=1.0"), follow=True)
        view = core.installed_view(self.catalog, [self.item("paint@=1.0")[2]])
        with self.assertRaises(core.ResolutionError):
            core.resolve(view, "paint@=1.1")

    def test_restored_selection_rejects_corrupt_selector_backend_and_digest(self):
        original = self.item("paint@1")[2].to_dict()
        self.assertEqual(core.Selection.from_dict(original).to_dict(), original)
        for field, value in (("selector", {"name": "paint", "kind": "series", "components": [True]}),
                             ("catalog", dict(original["catalog"], digest="bad")),
                             ("candidate", dict(original["candidate"], backend="other"))):
            with self.subTest(field=field), self.assertRaises(ValueError):
                core.Selection.from_dict(dict(original, **{field: value}))

    def test_state_validation_rejects_capabilities_and_request_target_drift(self):
        state = ports.install(self.state, [self.item("paint@1"), self.item("paint@2")])
        changed = copy.deepcopy(state)
        changed["capabilities"]["writer"] = "future-writer"
        with self.assertRaisesRegex(ValueError, "capabilities"):
            ports.validate(changed)
        changed = copy.deepcopy(state)
        requests = list(changed["requests"].values())
        requests[0]["target"] = requests[1]["target"]
        with self.assertRaisesRegex(ValueError, "evidence differs"):
            ports.validate(changed)

    def test_installed_view_forgets_historical_preferences_so_build_ties_fail(self):
        value = copy.deepcopy(self.value)
        row = copy.deepcopy(value["candidates"][0])
        row.update(artifact="replacement", integrity={"digest": "replacement"}, preferred=True)
        value["candidates"].append(row)
        newer = core.Catalog.from_dict(value)
        old = core.resolve(self.catalog, "paint@=1.0")
        replacement = core.resolve(newer, "paint@=1.0")
        with self.assertRaises(core.AmbiguousSelection):
            core.resolve(core.installed_view(newer, [old, replacement]), "paint@1")


if __name__ == "__main__":
    unittest.main()
