# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Complete explicit plans with real installed tar/zstd content and no boot writes."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import mojt_artifact as artifact
import mojt_boot as boot
import mojt_system_manifest as system
import mpm_catalog as catalog
import mpm_deployment as deployment
import mpm_kernel as kernel


@unittest.skipUnless(shutil.which("zstd"), "requires zstd for real installation fixture")
class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.root = self.work / "registry"
        self.bundle = self.work / "bundle"
        self.bundle.mkdir()
        self.source = self.work / "payload"
        self.source.mkdir()
        self.release = "6.12.107-mojt1"
        for path in ["boot/" + p + self.release for p in ("vmlinuz-", "config-", "System.map-")] + [
                "lib/modules/" + self.release + "/modules.dep", "lib/modules/" + self.release + "/kernel/example.ko"]:
            target = self.source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"test Kernel content")
        self.spec = dict(format=artifact.SPEC_FORMAT, kind="kernel", name="linux", platform=os.uname().machine + "-linux",
            version=dict(upstream="6.12.107", scheme="dotted-v1", revision=1), dependencies=[], requirements={},
            provides={}, provenance={"fixture": True}, metadata=dict(kernel_release=self.release))
        self.body = self.install_package("package")
        self.manifest = system.create(dict(label="system-fixture", architecture=os.uname().machine,
            requirements=dict(base_abi={"libc": "fixture-libc"}, state_layout=1),
            support=dict(ports=dict(read=[3], write=[3], capabilities=["mpm-ports-selectors-v1"])),
            provides=["/run/mojt-system/bin/bash"], artifacts={"fixture-provider": {"exact": "opaque-object"}},
            provenance={"fixture": True}, profile={"bin/bash": {"link": "opaque-fixture-target"}}))
        base = dict(artifact="sha256:" + "a" * 64, release="example-1")
        selected_system = dict(manifest=self.manifest["id"], generation="system-fixture")
        uuid = "11111111-1111-4111-8111-111111111111"
        boot_ref = dict(root_uuid=uuid, console="serial", cmdline=boot.cmdline(uuid, "system-fixture", "example-1"))
        self.selected = deployment.create(dict(platform=self.spec["platform"], base=base, system=selected_system,
            kernel=dict(artifact="sha256:" + "b" * 64, release="6.12.1-old", image_sha256="c" * 64,
                        modules_digest="sha256:" + "d" * 64),
            initramfs=dict(archive=dict(sha256="e" * 64, size=123), binding="sha256:" + "f" * 64), boot=boot_ref))
        self.bounds = dict(format=catalog.BASE_FORMAT, base=base, platform=self.spec["platform"],
                           kernel_min="6.1", kernel_max="6.12.999")
        self.context = dict(format=deployment.CONTEXT, selected=self.selected["id"], base=base, root_uuid=uuid,
            facts=dict(format=system.CONTEXT, architecture=os.uname().machine, base_abi={"libc": "fixture-libc"},
                state_layout=1, ports=dict(format=3, capabilities=dict(reader="mpm-ports-selectors-v1", writer="mpm-ports-selectors-v1")),
                required_system_paths=["/run/mojt-system/bin/bash"]))
        # Deliberately not real cpio: checksum/binding tests cannot prove bootability.
        (self.bundle / "initramfs.cpio.gz").write_bytes(b"synthetic initramfs fixture, not a bootable archive")
        self.binding = self.make_binding()
        self.request = dict(format=deployment.REQUEST, kernel=self.body["id"], selected="selected.json",
            base_context="bounds.json", system_manifest="system.json", system_context="context.json",
            initramfs="initramfs.cpio.gz", initramfs_binding="binding.json")
        self.write_bundle()

    def install_package(self, name):
        output = self.work / name
        result = artifact.pack(self.source, self.spec, output)
        kernel.install(self.root, output / result["archive"]["file"], result["artifact"]["id"], yes=True)
        return result["artifact"]

    def make_binding(self):
        old = self.selected["description"]
        return deployment.create(dict(platform=old["platform"], base=old["base"], system=old["system"], boot=old["boot"],
            kernel=deployment.kernel_identity(self.body), archive=deployment.initramfs_evidence(self.bundle / "initramfs.cpio.gz")),
            deployment.BINDING)

    def write_bundle(self):
        for name, value in (("request", self.request), ("selected", self.selected), ("bounds", self.bounds),
                            ("system", self.manifest), ("context", self.context), ("binding", self.binding)):
            (self.bundle / (name + ".json")).write_bytes(artifact.canonical(value) + b"\n")

    def plan(self):
        return deployment.plan(self.bundle / "request.json", self.root)

    def snapshot(self):
        return {str(p.relative_to(self.work)): (stat.S_IMODE(p.lstat().st_mode), p.lstat().st_mtime_ns,
                hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() else None)
                for p in self.work.rglob("*")}

    def test_complete_plan_uses_installed_exact_build_preserves_userspace_and_writes_nothing(self):
        before = self.snapshot()
        result = self.plan()
        candidate = result["candidate"]["description"]
        self.assertEqual(candidate["kernel"], deployment.kernel_identity(self.body))
        for name in ("base", "system", "boot", "platform"):
            self.assertEqual(candidate[name], self.selected["description"][name])
        self.assertEqual(set(result["changes"]), {"kernel", "initramfs"})
        self.assertFalse(result["boot_ready"])
        self.assertFalse(result["writes"])
        self.assertFalse(result["selected"]["authoritative_lookup"])
        self.assertEqual(result["evidence"]["kernel_integrity"], "verified-now")
        self.assertIn("not inspected", result["evidence"]["initramfs"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(result, self.plan())

    def test_candidate_equal_to_explicit_selection_is_no_change_without_status_adoption(self):
        self.selected = self.plan()["candidate"]
        self.context["selected"] = self.selected["id"]
        self.write_bundle()
        result = self.plan()
        self.assertTrue(result["no_change"])
        self.assertEqual(result["changes"], {})
        self.assertIsNone(kernel.status(self.root)["selected"]["artifact"])

    def test_base_lower_upper_and_missing_bounds_fail_without_fallback(self):
        original = copy.deepcopy(self.bounds)
        for change in ({"kernel_max": "6.12.106"}, {"kernel_min": "6.12.108"}, {"kernel_max": "6.0"}):
            self.bounds = dict(original, **change)
            self.write_bundle()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.plan()
        self.bounds = original
        del self.bounds["kernel_max"]
        self.write_bundle()
        with self.assertRaises(ValueError):
            self.plan()

    def test_bounds_for_another_base_or_platform_do_not_apply(self):
        for name, value in (("base", dict(artifact="sha256:" + "1" * 64, release="example-1")),
                            ("platform", "other-linux")):
            old = copy.deepcopy(self.bounds)
            self.bounds[name] = value
            self.write_bundle()
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.plan()
            self.bounds = old

    def test_kernel_plan_cannot_substitute_another_system_userspace(self):
        for key, value in (("label", "other-System"), ("provenance", {"source": "different"})):
            old = copy.deepcopy(self.manifest)
            d = copy.deepcopy(self.manifest["description"])
            d[key] = value
            self.manifest = system.create(d)
            self.write_bundle()
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "preserve the exact"):
                self.plan()
            self.manifest = old

    def test_system_abi_layout_ports_capability_and_shell_gates_are_reused(self):
        changes = [("base_abi", {"libc": "other"}), ("state_layout", 2),
                   ("ports", dict(format=4, capabilities={})),
                   ("ports", dict(format=3, capabilities=dict(reader="unknown", writer="unknown"))),
                   ("required_system_paths", ["/run/mojt-system/bin/missing"]), ("architecture", "other")]
        old = copy.deepcopy(self.context)
        for key, value in changes:
            self.context = copy.deepcopy(old)
            self.context["facts"][key] = value
            self.write_bundle()
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.plan()

    def test_context_must_bind_selected_identity_base_and_root_not_running_host(self):
        original = copy.deepcopy(self.context)
        for key, value in (("selected", "sha256:" + "0" * 64), ("base", dict(original["base"], release="other")),
                           ("root_uuid", "22222222-2222-4222-8222-222222222222")):
            self.context = dict(original, **{key: value})
            self.write_bundle()
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "not bound"):
                self.plan()

    def test_validly_rehashed_wrong_initramfs_bindings_are_rejected(self):
        original = copy.deepcopy(self.binding["description"])
        for key in ("platform", "base", "system", "kernel", "boot", "archive"):
            d = copy.deepcopy(original)
            if key == "platform":
                d[key] = "other-linux"
            elif key == "archive":
                d[key]["sha256"] = "0" * 64
            else:
                field = {"base": "artifact", "system": "manifest", "kernel": "artifact", "boot": "root_uuid"}[key]
                d[key][field] = "wrong-binding"
            self.binding = deployment.create(d, deployment.BINDING)
            self.write_bundle()
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.plan()

    def test_changed_initramfs_bytes_and_size_are_rejected(self):
        path = self.bundle / "initramfs.cpio.gz"
        original = path.read_bytes()
        for value in (original + b"changed", b"x" * len(original), b""):
            path.write_bytes(value)
            with self.subTest(size=len(value)), self.assertRaises(ValueError):
                self.plan()

    def test_missing_or_damaged_installed_kernel_is_not_plannable(self):
        self.request["kernel"] = "sha256:" + "0" * 64
        self.write_bundle()
        with self.assertRaises(FileNotFoundError):
            self.plan()
        self.request["kernel"] = self.body["id"]
        self.write_bundle()
        binary = self.root / "installed" / self.body["id"].split(":")[1] / ("payload/boot/vmlinuz-" + self.release)
        binary.chmod(0o644)
        binary.write_bytes(b"damaged")
        binary.chmod(0o444)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "content differs"):
            self.plan()
        self.assertEqual(self.snapshot(), before)

    def test_absent_registry_is_not_created_by_plan(self):
        path = self.work / "absent"
        with self.assertRaisesRegex(ValueError, "absent"):
            deployment.plan(self.bundle / "request.json", path)
        self.assertFalse(path.exists())

    def test_same_release_different_build_requires_its_own_binding_and_deployment_id(self):
        first = self.plan()
        (self.source / ("boot/vmlinuz-" + self.release)).write_bytes(b"second build of same release")
        self.body = self.install_package("package-2")
        self.request["kernel"] = self.body["id"]
        self.write_bundle()
        with self.assertRaisesRegex(ValueError, "exact candidate"):
            self.plan()
        self.binding = self.make_binding()
        self.write_bundle()
        second = self.plan()
        self.assertEqual(first["candidate"]["description"]["kernel"]["release"], self.release)
        self.assertNotEqual(first["candidate"]["id"], second["candidate"]["id"])
        self.assertEqual(len(kernel.status(self.root)["installed"]), 2)

    def test_corrupt_ids_unknown_formats_extra_fields_and_duplicate_keys_fail(self):
        for filename, field, value in (("selected", "id", "sha256:" + "0" * 64),
                ("selected", "format", "future"), ("binding", "format", "future"),
                ("context", "format", "future"), ("request", "format", "future"), ("request", "extra", True)):
            self.write_bundle()
            path = self.bundle / (filename + ".json")
            d = json.loads(path.read_text())
            d[field] = value
            path.write_text(json.dumps(d))
            with self.subTest(filename=filename, field=field), self.assertRaises(ValueError):
                self.plan()
        self.write_bundle()
        (self.bundle / "request.json").write_text('{"format":"one","format":"two"}')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.plan()

    def test_unsafe_selected_cmdline_fails_even_with_recomputed_id(self):
        for cmdline in (self.selected["description"]["boot"]["cmdline"] + " root=/dev/wrong", "quiet"):
            d = copy.deepcopy(self.selected["description"])
            d["boot"]["cmdline"] = cmdline
            self.selected = deployment.create(d)
            self.write_bundle()
            with self.assertRaisesRegex(ValueError, "command line differs"):
                self.plan()

    def test_local_input_links_fifo_and_urls_are_rejected_without_following_or_blocking(self):
        path = self.bundle / "selected.json"
        target = self.bundle / "real-selected.json"
        path.rename(target)
        path.symlink_to(target.name)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            self.plan()
        path.unlink()
        os.mkfifo(path)
        with self.assertRaisesRegex(ValueError, "regular local"):
            self.plan()
        path.unlink()
        target.rename(path)
        self.request["selected"] = "https://invalid.example/selected.json"
        self.write_bundle()
        with self.assertRaisesRegex(ValueError, "local input"):
            self.plan()

    def test_cli_runs_without_provider_files_or_executables_from_another_directory(self):
        tools = self.work / "isolated-tools"
        tools.mkdir()
        names = ("mpm", "mpm_deployment.py", "mpm_kernel.py", "mojt_artifact.py", "mpm_selection.py",
                 "mojt_boot.py", "mojt_system_manifest.py", "mpm_catalog.py", "mpm_transaction.py")
        for name in names:
            shutil.copyfile(REPO / "tools" / name, tools / name)
        environment = dict(os.environ, PATH="", PYTHONDONTWRITEBYTECODE="1")
        before = self.snapshot()
        command = [sys.executable, "-I", "-B", str(tools / "mpm"), "--root", str(self.root),
                   "kernel", "plan", "--request", str(self.bundle / "request.json"), "--json"]
        result = subprocess.run(command, cwd="/", env=environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["boot_ready"])
        self.assertEqual(self.snapshot(), before)
        alternate = [sys.executable, "-I", "-B", str(tools / "mpm"), "kernel", "plan", "--root=" + str(self.root),
                     "--request", str(self.bundle / "request.json"), "--json"]
        other = subprocess.run(alternate, cwd="/", env=environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(other.returncode, 0, other.stderr)
        self.assertEqual(json.loads(other.stdout), json.loads(result.stdout))
        duplicate = subprocess.run([*command, "--root", str(self.work / "wrong")], cwd="/", env=environment,
                                   capture_output=True, text=True, timeout=10)
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn("only once", duplicate.stderr)
        (self.bundle / "selected.json").unlink()
        result = subprocess.run(command, cwd="/", env=environment, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("Nix", result.stderr)


if __name__ == "__main__":
    unittest.main()

