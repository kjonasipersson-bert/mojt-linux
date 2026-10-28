# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Local discovery/policy acceptance with no Nix, network, payloads or state writes."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import mpm_catalog as discovery
from mpm_selection import CatalogError, ResolutionError


def fixture():
    return json.loads((REPO / "manifests/mpm-discovery-example.json").read_text())


def context(maximum="6.12.999"):
    result = json.loads((REPO / "manifests/mpm-kernel-base-example.json").read_text())
    result["kernel_max"] = maximum
    return result


def row(name, **extra):
    value = copy.deepcopy(fixture()["packages"][1])
    value.update(name=name, aliases=[])
    for c in value["releases"]["candidates"]:
        c.update(name=name, artifact="example:" + name + c["release_id"])
    value.update(extra)
    return value


class DiscoveryTests(unittest.TestCase):
    def test_known_but_absent_packages_group_releases_and_keep_source_evidence(self):
        catalog = discovery.DiscoveryCatalog.from_dict(fixture())
        hits = catalog.search(["neovim"])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["name"], "neovim")
        self.assertEqual(hits[0]["sources"]["local"]["backend"], "native")
        self.assertEqual(len(catalog.package("ports", "neovim").releases.candidates), 2)

    def test_search_is_literal_casefolded_and_never_regex(self):
        value = fixture()
        value["packages"] += [row("foo.bar"), row("fooxbar"), row("c++")]
        catalog = discovery.DiscoveryCatalog.from_dict(value)
        for query, expected in [("foo.bar", ["foo.bar"]), ("c++", ["c++"]),
                                ("NEOVIM", ["neovim"]), ("nvim", ["neovim"]),
                                (".*", []), ("foo*", []), ("[", [])]:
            with self.subTest(query=query):
                self.assertEqual([r["name"] for r in catalog.search([query])], expected)

    def test_rank_is_exact_alias_prefix_substring_then_description(self):
        value = fixture()
        value["packages"] = [row("zpaint"), row("paintbrush"), row("painting", aliases=["paint"]),
                             row("paint"), row("other", description="paint")]
        catalog = discovery.DiscoveryCatalog.from_dict(value)
        self.assertEqual([r["name"] for r in catalog.search(["paint"], description=True)],
                         ["paint", "painting", "paintbrush", "zpaint", "other"])
        value["packages"].reverse()
        self.assertEqual(catalog.search(["paint"], description=True),
                         discovery.DiscoveryCatalog.from_dict(value).search(["paint"], description=True))

    def test_description_is_opt_in_exact_does_not_broaden_and_terms_are_and(self):
        catalog = discovery.DiscoveryCatalog.from_dict(fixture())
        self.assertEqual(catalog.search(["Lua"]), [])
        self.assertEqual(len(catalog.search(["Lua"], description=True)), 1)
        self.assertEqual(catalog.search(["neo"], exact=True), [])
        self.assertEqual(len(catalog.search(["nvim"], exact=True)), 1)
        self.assertEqual(len(catalog.search(["neo", "vim"])), 1)
        self.assertEqual(catalog.search(["neo", "linux"]), [])
        self.assertEqual(catalog.search(["neovim"], area="kernel"), [])
        with self.assertRaises(ResolutionError):
            catalog.search(["neo", "vim"], exact=True)

    def test_unknown_incomplete_or_contradictory_envelopes_fail(self):
        mutations = [lambda v: v.update(format="future-v99"),
                     lambda v: v.update(complete=False), lambda v: v.update(complete=1),
                     lambda v: v.update(extra="unknown"),
                     lambda v: v["packages"].append(copy.deepcopy(v["packages"][1])),
                     lambda v: v["packages"][1].update(aliases=["bad\ntext"]),
                     lambda v: v["packages"][1]["releases"]["candidates"][0].update(name="wrong"),
                     lambda v: v["packages"][0]["kernel"]["releases"].pop("6.12.107"),
                     lambda v: v["packages"][0]["kernel"]["releases"]["6.12.107"].update(active_lts="yes"),
                     lambda v: v["packages"][0]["kernel"]["releases"]["6.12.107"].update(upstream_stable=False)]
        for mutate in mutations:
            value = fixture()
            mutate(value)
            with self.subTest(value=value), self.assertRaises((CatalogError, ValueError)):
                discovery.DiscoveryCatalog.from_dict(value)

    def test_missing_package_is_not_an_external_provider_fallback(self):
        with self.assertRaisesRegex(ResolutionError, "absent"):
            discovery.DiscoveryCatalog.from_dict(fixture()).package("ports", "absent")

    def test_legacy_release_schema_remains_strict(self):
        value = fixture()["packages"][0]["releases"]
        value["search_metadata"] = {}
        with self.assertRaises(CatalogError):
            discovery.Catalog.from_dict(value)


class KernelPolicyTests(unittest.TestCase):
    def plan(self, policy, maximum="6.12.999", value=None, **pin):
        catalog = discovery.DiscoveryCatalog.from_dict(value or fixture())
        return discovery.resolve_kernel(catalog, context(maximum), policy, **pin)

    def version(self, policy, maximum="6.12.999", **pin):
        return self.plan(policy, maximum, **pin)["selection"]["candidate"]["release_id"]

    def test_three_policies_with_and_without_base_ceiling(self):
        self.assertEqual(self.version("pinned", "9.0", series="6.12"), "6.12.107")
        self.assertEqual(self.version("latest-lts", "9.0"), "6.18.1")
        self.assertEqual(self.version("latest-upstream", "9.0"), "7.3")
        self.assertEqual(self.version("latest-lts"), "6.12.107")
        self.assertEqual(self.version("latest-upstream"), "6.12.107")
        # Apply compatibility before release ordering, with inclusive boundaries.
        self.assertEqual(self.version("pinned", "6.12.100", series="6.12"), "6.12.100")
        self.assertEqual(self.version("latest-upstream", "6.12.107"), "6.12.107")

    def test_exact_release_pin_and_no_fallback_for_impossible_requests(self):
        self.assertEqual(self.version("pinned", release="6.12.100"), "6.12.100")
        for policy, kwargs in [("pinned", dict(series="6.18")),
                               ("pinned", dict(release="7.2.9")),
                               ("pinned", dict(series="6.1", release="6.1.9")),
                               ("pinned", {}), ("latest-lts", dict(series="6.12"))]:
            with self.subTest(policy=policy, kwargs=kwargs), self.assertRaises(ResolutionError):
                self.plan(policy, **kwargs)
        with self.assertRaises(ResolutionError):
            self.plan("latest-lts", "6.1")

    def test_latest_lts_never_falls_back_to_non_lts(self):
        value = fixture()
        for labels in value["packages"][0]["kernel"]["releases"].values():
            labels["active_lts"] = False
        with self.assertRaises(ResolutionError):
            self.plan("latest-lts", "9.0", value=value)
        self.assertEqual(self.plan("latest-upstream", "9.0", value=value)
                         ["selection"]["candidate"]["release_id"], "7.3")

    def test_inactive_lts_can_still_be_explicitly_pinned(self):
        value = fixture()
        for version, labels in value["packages"][0]["kernel"]["releases"].items():
            if version.startswith("6.12."):
                labels["active_lts"] = False
        self.assertEqual(self.plan("pinned", value=value, series="6.12")
                         ["selection"]["candidate"]["release_id"], "6.12.107")

    def test_no_preview_or_unknown_upstream_classification_in_tracking(self):
        value = fixture()
        value["packages"][0]["releases"]["candidates"][-1]["stability"] = "preview"
        value["packages"][0]["kernel"]["releases"]["7.3"]["upstream_stable"] = False
        self.assertEqual(self.plan("latest-upstream", "9.0", value=value)
                         ["selection"]["candidate"]["release_id"], "7.2.9")

    def test_declared_incompatible_candidate_is_excluded(self):
        value = fixture()
        value["packages"][0]["releases"]["candidates"][2]["compatibility"] = "incompatible"
        self.assertEqual(self.plan("pinned", value=value, series="6.12")
                         ["selection"]["candidate"]["release_id"], "6.12.100")

    def test_missing_context_platform_and_invalid_range_fail_closed(self):
        catalog = discovery.DiscoveryCatalog.from_dict(fixture())
        mutations = [lambda c: c.update(kernel_max=None), lambda c: c.update(kernel_min="9.0"),
                     lambda c: c.update(platform="other"), lambda c: c["base"].pop("artifact")]
        for mutate in mutations:
            current = context()
            mutate(current)
            with self.subTest(current=current), self.assertRaises((CatalogError, ResolutionError)):
                discovery.resolve_kernel(catalog, current, "latest-lts")

    def test_plan_explains_base_exclusions_and_preserves_snapshot_identity(self):
        value, selected_base = fixture(), context()
        before = copy.deepcopy((value, selected_base))
        catalog = discovery.DiscoveryCatalog.from_dict(value)
        result = discovery.resolve_kernel(catalog, selected_base, "latest-upstream")
        self.assertIn("7.3", {c["release_id"] for c in result["excluded"]})
        self.assertEqual(result["discovery_digest"], catalog.digest)
        self.assertEqual(result["selection"]["catalog"]["digest"],
                         catalog.package("kernel", "linux").releases.digest)
        self.assertEqual(before, (value, selected_base))

    def test_build_ambiguity_reuses_existing_resolver(self):
        value = fixture()
        releases = value["packages"][0]["releases"]
        alternative = dict(releases["candidates"][2], artifact="example:another-build")
        releases["candidates"].append(alternative)
        with self.assertRaisesRegex(ResolutionError, "multiple builds"):
            self.plan("pinned", value=value, series="6.12")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.tools = self.directory / "tools"
        self.tools.mkdir()
        for name in ("mpm", "mpm_catalog.py", "mpm_selection.py"):
            shutil.copyfile(REPO / "tools" / name, self.tools / name)
        self.catalog = self.directory / "catalog.json"
        self.catalog.write_text(json.dumps(fixture()))
        self.base = self.directory / "base.json"
        self.base.write_text(json.dumps(context()))
        self.env = dict(os.environ, PATH=str(self.tools), PYTHONDONTWRITEBYTECODE="1")

    def cli(self, *args, success=True):
        # No backend file exists. -I excludes cwd/PYTHONPATH and disables user site.
        run = subprocess.run([sys.executable, "-I", "-B", str(self.tools / "mpm"), *args],
                             cwd=self.directory, env=self.env, text=True, capture_output=True)
        self.assertEqual(run.returncode == 0, success, run.stderr + run.stdout)
        self.assertNotIn("Traceback", run.stderr)
        return run

    def snapshot(self):
        return {str(p.relative_to(self.directory)): p.read_bytes()
                for p in self.directory.rglob("*") if p.is_file()}

    def test_native_commands_without_nix_or_any_provider_files_are_read_only(self):
        before = self.snapshot()
        for area, action, args in [("ports", "search", ("nvim",)),
                                   ("ports", "show", ("neovim",)),
                                   ("ports", "versions", ("neovim",)),
                                   ("kernel", "search", ("linux",)),
                                   ("catalog", "search", ("linux",)),
                                   ("kernel", "resolve", ("--policy", "latest-lts", "--base-context", str(self.base)))]:
            with self.subTest(action=action):
                run = self.cli(area, action, *args, "--catalog", str(self.catalog), "--json")
                self.assertEqual(json.loads(run.stdout)["publisher"], "example-only")
        self.assertEqual(before, self.snapshot())

    def test_unknown_missing_duplicate_or_nonfinite_metadata_reports_error_without_writes(self):
        for content in ('{"format":"unknown"}', '{"format":1,"format":2}', '{"x":NaN}', '{'):
            self.catalog.write_text(content)
            before = self.snapshot()
            self.cli("catalog", "search", "linux", "--catalog", str(self.catalog), success=False)
            self.assertEqual(before, self.snapshot())
        self.cli("kernel", "resolve", "--policy", "latest-lts", "--catalog", str(self.catalog),
                 success=False)  # Missing selected Base context.

    def test_scoped_area_cannot_be_overridden(self):
        self.cli("ports", "search", "linux", "--area", "kernel", "--catalog", str(self.catalog), success=False)

    def test_legacy_search_and_mutation_still_delegate_without_catalog_adoption(self):
        backend = self.tools / "mpm-nix-prototype"
        backend.write_text("import sys; print('backend:', repr(sys.argv[1:]))\n")
        for args in [("ports", "search", "neovim"), ("ports", "install", "hello", "-y"),
                     ("--root", "old-state", "ports", "status")]:
            run = self.cli(*args)
            self.assertIn("backend: " + repr(list(args)), run.stdout)


if __name__ == "__main__":
    unittest.main()
