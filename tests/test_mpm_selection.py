# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Backend-independent selector/resolver/upgrade policy; no package manager."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("selection_test_core", REPO / "tools/mpm_selection.py")
core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = core
spec.loader.exec_module(core)


def candidate(version="3.0.9", *, source="a", artifact=None, name="paint", revision=None,
              scheme="dotted-v1", stability="stable", **extra):
    release = version + ("-r" + str(revision) if revision is not None else "")
    return dict(name=name, release_id=release, upstream_version=version, version_scheme=scheme,
                revision_scheme="mojt-r-v1" if revision is not None else None,
                package_revision=revision, stability=stability, source=source,
                artifact=artifact or "bundle:" + release,
                integrity={"digest": "digest-" + (artifact or release)}, **extra)


def view(*rows, **extra):
    result = dict(format=core.FORMAT, area="ports", name="apps", channel="stable", platform="machine-A",
                sources={"a": dict(backend="archive", identity={"snapshot": "old"}),
                         "b": dict(backend="alternate", identity={"snapshot": "new"})},
                candidates=list(rows))
    result.update(extra)
    return result


def catalog(*rows, **extra):
    return core.Catalog.from_dict(view(*rows, **extra))


class SelectorTests(unittest.TestCase):
    def test_valid_latest_series_exact_and_backend_style_names(self):
        for value, expected in [
            ("paint", dict(name="paint", kind="latest")),
            ("paint@3.0", dict(name="paint", kind="series", components=[3, 0])),
            ("paint@=3.0-r2", dict(name="paint", kind="exact", release_id="3.0-r2")),
            ("python312Packages.requests", dict(name="python312Packages.requests", kind="latest")),
        ]:
            with self.subTest(value=value):
                parsed = core.parse_selector(value)
                self.assertEqual(parsed.to_dict(), expected)
                self.assertEqual(core.render_selector(parsed), value)

    def test_invalid_selectors_do_not_become_globs_ranges_or_exact_requests(self):
        for value in ("", "x@", "x@=", "x@@3", "x@03.0", "x@3.00", "x@3.*", "x@>=3.0",
                      "x@3.0rc1", "x@=1:2", "x y", "x@=a/b", " x", "x\n", None):
            with self.subTest(value=value), self.assertRaises(core.SelectorError):
                core.parse_selector(value)

    def test_exact_equality_does_not_normalize_missing_components_or_leading_zeros(self):
        c = catalog(candidate("3.0"), candidate("3.0.0"), candidate("3.00", scheme="opaque-v1"))
        for value in ("3.0", "3.0.0", "3.00"):
            self.assertEqual(core.resolve(c, "paint@=" + value).candidate.release_id, value)
        with self.assertRaises(core.AmbiguousSelection):
            core.resolve(catalog(candidate("3.0"), candidate("3.0.0")), "paint@3.0")

    def test_structured_selector_cannot_bypass_parser(self):
        with self.assertRaises(core.SelectorError):
            core.resolve(catalog(candidate()), core.Selector("paint", "series", (True,)))


class ResolutionTests(unittest.TestCase):
    def test_series_matches_components_and_numeric_order(self):
        c = catalog(candidate("3.0.9"), candidate("3.0.10"), candidate("3.1"),
                    candidate("13.0"), candidate("3.00", scheme="opaque-v1"),
                    candidate("3.0rc1", scheme="opaque-v1", stability="preview"))
        self.assertEqual(core.resolve(c, "paint@3.0").candidate.release_id, "3.0.10")
        self.assertEqual(core.resolve(catalog(candidate("3.0")), "paint@3.0").candidate.release_id, "3.0")

    def test_latest_never_claims_numeric_or_channel_names_imply_stability(self):
        c = catalog(candidate("3.0"), candidate("99.0", stability="unknown"),
                    candidate("100.0", stability="preview"))
        self.assertEqual(core.resolve(c, "paint").candidate.release_id, "3.0")
        self.assertEqual(core.resolve(c, "paint@=100.0").candidate.release_id, "100.0")
        self.assertEqual(core.resolve(c, "paint@=99.0").candidate.release_id, "99.0")
        with self.assertRaises(core.ResolutionError):
            core.resolve(catalog(candidate("99.0", stability="unknown")), "paint")

    def test_declared_revision_order_and_exact_revision(self):
        c = catalog(candidate("3.0.8", revision=2), candidate("3.0.8", revision=10))
        self.assertEqual(core.resolve(c, "paint@3.0").candidate.release_id, "3.0.8-r10")
        self.assertEqual(core.resolve(c, "paint@=3.0.8-r2").candidate.package_revision, 2)

    def test_opaque_stable_version_requires_exact_selection(self):
        c = catalog(candidate("1.9.17p2", scheme="opaque-v1"), candidate("2.0"))
        with self.assertRaises(core.ResolutionError):
            core.resolve(c, "paint")
        self.assertEqual(core.resolve(c, "paint@=1.9.17p2").candidate.release_id, "1.9.17p2")

    def test_unrelated_revision_models_are_not_compared(self):
        with self.assertRaises(core.ResolutionError):
            core.resolve(catalog(candidate("3.0"), candidate("3.0", revision=2)), "paint")

    def test_known_incompatible_candidate_is_excluded_and_platform_is_checked(self):
        c = catalog(candidate("3.0"), candidate("4.0", compatibility="incompatible"))
        self.assertEqual(core.resolve(c, "paint").candidate.release_id, "3.0")
        self.assertEqual(core.resolve(c, "paint").candidate.compatibility, "unknown")
        with self.assertRaises(core.ResolutionError):
            core.resolve(c, "paint@=4.0")
        with self.assertRaises(core.ResolutionError):
            core.resolve(c, "paint", platform="machine-B")

    def test_missing_package_or_series_is_not_resolved_to_another_release(self):
        for request in ("other", "paint@2", "paint@=3.0"):
            with self.subTest(request=request), self.assertRaises(core.ResolutionError):
                core.resolve(catalog(candidate()), request)

    def test_same_release_build_ambiguity_never_sorts_backend_ids(self):
        c = catalog(candidate(artifact="aaa"), candidate(artifact="zzz"))
        with self.assertRaises(core.AmbiguousSelection):
            core.resolve(c, "paint")

    def test_explicit_preferred_build_and_source_preference(self):
        rows = (candidate(artifact="aaa"), candidate(artifact="zzz", source="b"))
        self.assertEqual(core.resolve(catalog(*rows, source_preference=["b", "a"]), "paint").candidate.artifact, "zzz")
        self.assertEqual(core.resolve(catalog(rows[0], dict(rows[1], preferred=True)), "paint").candidate.backend, "alternate")
        with self.assertRaises(core.AmbiguousSelection):
            core.resolve(catalog(*(dict(r, preferred=True) for r in rows)), "paint")
        with self.assertRaises(core.AmbiguousSelection):
            core.resolve(catalog(candidate(artifact="a"), candidate(artifact="b"), source_preference=["a"]), "paint")

    def test_newest_release_is_selected_before_build_preference(self):
        c = catalog(candidate("3.0", preferred=True), candidate("4.0", source="b"), source_preference=["a"])
        self.assertEqual(core.resolve(c, "paint").candidate.release_id, "4.0")

    def test_two_backends_with_same_opaque_id_are_distinct_artifacts(self):
        with self.assertRaises(core.AmbiguousSelection):
            core.resolve(catalog(candidate(artifact="same"), candidate(source="b", artifact="same")), "paint")

    def test_duplicate_artifact_merges_provenance_but_not_conflicting_evidence(self):
        value = view(candidate(artifact="same"), candidate(source="b", artifact="same"))
        value["sources"]["b"]["backend"] = "archive"
        resolved = core.resolve(core.Catalog.from_dict(value), "paint")
        self.assertEqual([p["source"] for p in resolved.provenance], ["a", "b"])
        value["candidates"][1]["integrity"] = {"digest": "different"}
        with self.assertRaises(core.CatalogError):
            core.Catalog.from_dict(value)

    def test_contradictory_release_metadata_is_not_a_build_preference(self):
        value = view(candidate(), candidate(source="b", stability="preview"))
        with self.assertRaises(core.CatalogError):
            core.Catalog.from_dict(value)

    def test_input_catalog_and_output_copies_do_not_mutate_accepted_records(self):
        value = view(candidate())
        original = copy.deepcopy(value)
        c = core.Catalog.from_dict(value)
        selected = core.resolve(c, "paint")
        self.assertEqual(value, original)
        value["candidates"][0]["integrity"]["digest"] = "changed externally"
        result = selected.to_dict()
        result["candidate"]["integrity"]["digest"] = "changed in display copy"
        self.assertEqual(selected.candidate.integrity, original["candidates"][0]["integrity"])
        self.assertEqual(c.digest, core.Catalog.from_dict(original).digest)

    def test_invalid_catalogs_fail_before_resolution(self):
        changes = [dict(format=1), dict(unexpected=True), dict(source_preference=["missing"]),
                   dict(source_preference=["a", "a"]), dict(candidates="wrong"), dict(sources={})]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(core.CatalogError):
                core.Catalog.from_dict(dict(view(candidate()), **change))
        bad_rows = [dict(release_id="other"), dict(package_revision=True, revision_scheme="mojt-r-v1"),
                    dict(version_scheme="guess"), dict(source="missing"), dict(preferred=1),
                    dict(upstream_version="03.0", release_id="03.0"), dict(compatibility="maybe"),
                    dict(integrity={}), dict(integrity={"digest": float("nan")})]
        for change in bad_rows:
            with self.subTest(change=change), self.assertRaises(core.CatalogError):
                catalog(dict(candidate(), **change))


class UpgradePolicyTests(unittest.TestCase):
    def test_series_advances_inside_its_line_and_retains_old_records(self):
        current = core.resolve(catalog(candidate("3.0.9")), "paint@3.0")
        before = current.to_dict()
        plan = core.plan_upgrade(catalog(candidate("3.0.10"), candidate("3.1")), current)
        self.assertTrue(plan.changed)
        self.assertEqual(plan.after.candidate.release_id, "3.0.10")
        self.assertEqual(plan.before.to_dict(), before)

    def test_exact_release_keeps_its_build_even_when_catalog_withdraws_it(self):
        current = core.resolve(catalog(candidate("3.0")), "paint@=3.0")
        for next_catalog in (catalog(), catalog(candidate("3.0", artifact="replacement", preferred=True))):
            plan = core.plan_upgrade(next_catalog, current)
            self.assertFalse(plan.changed)
            self.assertIs(plan.after, current)

    def test_same_release_new_opaque_dependency_build_can_advance_following(self):
        current = core.resolve(catalog(candidate("3.0", artifact="consumer-old-runtime")), "paint@3")
        new = candidate("3.0", artifact="consumer-new-runtime", preferred=True)
        plan = core.plan_upgrade(catalog(candidate("3.0", artifact="consumer-old-runtime"), new), current)
        self.assertTrue(plan.changed)
        self.assertEqual(plan.reason, "same-release build replacement")
        self.assertEqual(plan.before.candidate.artifact, "consumer-old-runtime")

    def test_noop_preserves_original_resolution_provenance(self):
        current = core.resolve(catalog(candidate()), "paint")
        value = view(candidate())
        value["sources"]["a"]["identity"] = {"snapshot": "another-view"}
        plan = core.plan_upgrade(core.Catalog.from_dict(value), current)
        self.assertFalse(plan.changed)
        self.assertIs(plan.after, current)

    def test_downgrade_integrity_drift_and_binding_changes_are_rejected(self):
        current = core.resolve(catalog(candidate("3.0")), "paint")
        with self.assertRaises(core.ResolutionError):
            core.plan_upgrade(catalog(candidate("2.0")), current)
        changed = dict(candidate("3.0"), integrity={"digest": "altered"})
        with self.assertRaises(core.ResolutionError):
            core.plan_upgrade(catalog(changed), current)
        with self.assertRaises(core.ResolutionError):
            core.plan_upgrade(catalog(candidate("4.0"), name="other-catalog"), current)
        with self.assertRaises(core.ResolutionError):
            core.plan_upgrade(catalog(candidate("4.0"), area="system"), current)
        with self.assertRaises(core.AmbiguousSelection):
            core.plan_upgrade(catalog(candidate("3.0.0")), current)

    def test_new_release_can_reference_same_backend_object_without_losing_new_release(self):
        current = core.resolve(catalog(candidate("3.0", artifact="shared")), "paint")
        plan = core.plan_upgrade(catalog(candidate("3.1", artifact="shared")), current)
        self.assertTrue(plan.changed)
        self.assertEqual(plan.after.candidate.release_id, "3.1")


class IsolatedCliTests(unittest.TestCase):
    def test_release_resolution_under_isolated_python_needs_no_backend_and_writes_no_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_file = root / "catalog.json"
            catalog_file.write_text(json.dumps(view(candidate("3.0.9"), candidate("3.0.10"))))
            state_root = root / "state"
            result = subprocess.run([sys.executable, "-I", str(REPO / "tools/mpm"),
                "--root", str(state_root), "ports", "resolve", "paint@3.0",
                "--catalog", str(catalog_file), "--json"],
                env={**os.environ, "PATH": "/does-not-exist"}, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["candidate"]["release_id"], "3.0.10")
            self.assertFalse(state_root.exists())
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["catalog.json"])


if __name__ == "__main__":
    unittest.main()
