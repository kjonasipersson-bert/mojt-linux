# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real local Kernel imports, atomic registration, readonly status and scope guards."""
import copy
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import mojt_artifact as artifact
import mpm_kernel as kernel


@unittest.skipUnless(shutil.which("zstd"), "requires zstd")
class KernelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.root = self.work / "registry"
        self.source = self.work / "source"
        self.source.mkdir()
        self.release = "6.12.107-mojt1"
        paths = ["boot/" + p + self.release for p in ("vmlinuz-", "config-", "System.map-")]
        paths += ["lib/modules/" + self.release + "/modules.dep", "lib/modules/" + self.release + "/kernel/example.ko"]
        for path in paths:
            target = self.source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"frozen Kernel fixture")
        self.spec = dict(format=artifact.SPEC_FORMAT, kind="kernel", name="linux", platform=os.uname().machine + "-linux",
            version=dict(upstream="6.12.107", scheme="dotted-v1", revision=1), dependencies=[], requirements={},
            provides={}, provenance=dict(source_commit="a" * 40), metadata=dict(kernel_release=self.release))
        self.serial = 0
        self.archive, self.body = self.package()
        self.identifier = self.body["id"]

    def package(self, spec=None):
        self.serial += 1
        output = self.work / ("package-" + str(self.serial))
        result = artifact.pack(self.source, spec or self.spec, output)
        return output / result["archive"]["file"], result["artifact"]

    def install(self, **kwargs):
        return kernel.install(self.root, self.archive, self.identifier, yes=True, **kwargs)

    def snapshot(self, path):
        if not path.exists():
            return None
        result = {}
        for item in (path, *path.rglob("*")):
            st = item.lstat()
            result[item.relative_to(path).as_posix()] = (stat.S_IMODE(st.st_mode), st.st_mtime_ns,
                                                       item.read_bytes() if item.is_file() else None)
        return result

    def test_status_missing_registry_and_preview_do_not_create_state(self):
        before = self.snapshot(self.work)
        result = kernel.status(self.root)
        self.assertEqual(result["installed"], [])
        self.assertEqual(result["selected"]["state"], "unknown")
        self.assertIsNone(result["running"]["artifact"])
        plan = self.install(dry_run=True)
        self.assertFalse(plan["changed"])
        self.assertEqual(plan["plan"]["action"], "install")
        self.assertEqual(self.snapshot(self.work), before)

    def test_real_import_retains_archive_private_tree_and_complete_record(self):
        before = self.snapshot(self.source)
        sentinel = self.work / "selected-deployment.json"
        sentinel.write_bytes(b"selected-Base-System-Kernel unchanged")
        result = self.install()
        self.assertTrue(result["changed"])
        target = Path(result["installed_path"])
        self.assertEqual((target / "archive.tar.zst").read_bytes(), self.archive.read_bytes())
        self.assertEqual((target / "artifact.json").read_bytes(), artifact.canonical(self.body) + b"\n")
        for row in self.body["files"]:
            item = target / row["path"]
            self.assertEqual(stat.S_IMODE(item.stat().st_mode), kernel.stored_mode(row))
            if row["type"] == "file":
                self.assertEqual(artifact.file_sha(item), row["sha256"])
        status = kernel.status(self.root, verify=True)
        self.assertEqual(status["installed"][0]["artifact"], self.identifier)
        self.assertEqual(status["installed"][0]["integrity"], "verified-now")
        self.assertIsNone(status["selected"]["artifact"])
        self.assertEqual(sentinel.read_bytes(), b"selected-Base-System-Kernel unchanged")
        self.assertEqual(self.snapshot(self.source), before)

    def test_repeat_install_is_a_complete_metadata_no_op(self):
        self.install()
        before = self.snapshot(self.root)
        result = self.install()
        self.assertFalse(result["changed"])
        self.assertEqual(result["plan"]["action"], "no-change")
        self.assertEqual(self.snapshot(self.root), before)

    def test_two_builds_of_same_kernel_release_are_retained_without_collision(self):
        first = Path(self.install()["installed_path"])
        before = self.snapshot(first)
        (self.source / ("boot/vmlinuz-" + self.release)).write_bytes(b"different build")
        second_archive, second = self.package()
        result = kernel.install(self.root, second_archive, second["id"], yes=True)
        self.assertTrue(result["changed"])
        self.assertNotEqual(second["id"], self.identifier)
        self.assertEqual(self.snapshot(first), before)
        self.assertEqual(len(kernel.status(self.root)["installed"]), 2)

    def test_running_release_match_never_guesses_selected_or_running_build(self):
        self.install()
        actual = os.uname()
        with mock.patch.object(kernel.os, "uname", return_value=type("Uname", (), dict(machine=actual.machine, release=self.release))()):
            result = kernel.status(self.root)
        self.assertTrue(result["installed"][0]["release_matches_running"])
        self.assertIsNone(result["running"]["artifact"])
        self.assertEqual(result["selected"]["state"], "unknown")

    def test_unimplemented_dependencies_and_requirements_fail_before_state_writes(self):
        for field, value in [("dependencies", [dict(provider="native", artifact="sha256:" + "a" * 64)]),
                             ("requirements", dict(base_abi="unknown"))]:
            spec = copy.deepcopy(self.spec)
            spec[field] = value
            archive, body = self.package(spec)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "cannot be ignored"):
                kernel.install(self.root, archive, body["id"], yes=True)
            self.assertFalse(self.root.exists())

    def test_wrong_area_platform_or_expected_identity_never_initializes_registry(self):
        for change in (dict(kind="port"), dict(platform="different-platform")):
            spec = copy.deepcopy(self.spec)
            spec.update(change)
            archive, body = self.package(spec)
            with self.subTest(change=change), self.assertRaises(ValueError):
                kernel.install(self.root, archive, body["id"], yes=True)
        for value in ("eed451", "sha256:../escape", "sha256:" + "0" * 64):
            with self.subTest(value=value), self.assertRaises(ValueError):
                kernel.install(self.root, self.archive, value, yes=True)
        self.assertFalse(self.root.exists())

    def test_corrupt_input_never_publishes(self):
        self.archive.write_bytes(self.archive.read_bytes()[:-5])
        with self.assertRaises((ValueError, artifact.tarfile.TarError)):
            self.install()
        self.assertFalse(self.root.exists())

    def test_valid_package_symlinks_in_provenance_are_outside_installer_subset(self):
        rows, locations = artifact.inventory(self.source)
        rows += [dict(path="provenance", type="directory", mode=0o755, uid=0, gid=0),
                 dict(path="provenance/link", type="symlink", target="/etc/shadow", mode=0o777, uid=0, gid=0)]
        body = artifact.descriptor(self.spec, rows)
        buffer = io.BytesIO()
        artifact._write_tar(buffer, body, locations)
        archive = self.work / "linked.tar.zst"
        archive.write_bytes(subprocess.check_output(["zstd", "-q", "-c"], input=buffer.getvalue()))
        artifact.verify(archive, body["id"])
        with self.assertRaisesRegex(ValueError, "regular files/directories"):
            kernel.install(self.root, archive, body["id"], yes=True)
        self.assertFalse(self.root.exists())

    def test_store_normalization_never_installs_special_privilege_bits(self):
        path = self.source / ("boot/vmlinuz-" + self.release)
        path.chmod(0o6755)
        archive, body = self.package()
        result = kernel.install(self.root, archive, body["id"], yes=True)
        target = Path(result["installed_path"]) / ("payload/boot/vmlinuz-" + self.release)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o555)
        self.assertEqual(target.stat().st_uid, os.geteuid())

    def test_failures_during_extract_or_publish_leave_no_partial_installation(self):
        self.install()
        first = self.root / "installed" / self.identifier.split(":")[1]
        before = self.snapshot(first)
        (self.source / ("boot/vmlinuz-" + self.release)).write_bytes(b"new build")
        archive, body = self.package()
        for fault in ("extract", "publish"):
            original = Path.rename
            def rename(path, target):
                if path.parent == self.root / "installed" and path.name.startswith(".install-"):
                    raise OSError("injected publication failure")
                return original(path, target)
            patcher = (mock.patch.object(kernel, "unpack_kernel", side_effect=ValueError("injected extraction failure"))
                       if fault == "extract" else mock.patch.object(Path, "rename", rename))
            with self.subTest(fault=fault), patcher, self.assertRaises((ValueError, OSError)):
                kernel.install(self.root, archive, body["id"], yes=True)
            self.assertEqual(self.snapshot(first), before)
            self.assertEqual(list((self.root / "staging").iterdir()), [])
            self.assertFalse(list((self.root / "installed").glob(".install-*")))
            self.assertEqual(len(kernel.status(self.root)["installed"]), 1)

    def test_input_changed_after_plan_is_verified_again_after_freezing(self):
        alternate = copy.deepcopy(self.spec)
        alternate["version"]["revision"] = 2
        archive, _ = self.package(alternate)
        other_bytes = archive.read_bytes()
        original = kernel.frozen_copy
        def mutate(source, destination):
            source.write_bytes(other_bytes)
            return original(source, destination)
        with mock.patch.object(kernel, "frozen_copy", side_effect=mutate), self.assertRaises(ValueError):
            self.install()
        self.assertEqual(kernel.status(self.root)["installed"], [])
        self.assertEqual(list((self.root / "staging").iterdir()), [])

    def test_status_reports_interrupted_staging_without_adopting_or_deleting_it(self):
        self.install()
        partial = self.root / "staging/.install-interrupted"
        partial.mkdir()
        (partial / "partial").write_bytes(b"incomplete")
        before = self.snapshot(self.root)
        result = kernel.status(self.root)
        self.assertEqual(result["staging_entries"], [partial.name])
        self.assertEqual(len(result["installed"]), 1)
        self.assertEqual(self.snapshot(self.root), before)

    def test_bitrot_is_reported_and_repeat_install_does_not_overwrite_it(self):
        path = Path(self.install()["installed_path"])
        item = path / ("payload/boot/vmlinuz-" + self.release)
        item.chmod(0o644)
        item.write_bytes(b"damaged")
        item.chmod(0o444)
        self.assertEqual(kernel.status(self.root)["installed"][0]["integrity"], "verified-at-installation")
        for action in (lambda: kernel.status(self.root, verify=True), self.install):
            with self.assertRaisesRegex(ValueError, "content differs"):
                action()
        self.assertEqual(item.read_bytes(), b"damaged")

    def test_unmanaged_root_symlink_root_and_unknown_registry_version_are_refused(self):
        self.root.mkdir()
        keeper = self.root / "ports-state.json"
        keeper.write_bytes(b"do not adopt")
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual(keeper.read_bytes(), b"do not adopt")
        other = self.work / "symlink-root"
        other.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            kernel.status(other)
        keeper.unlink()
        self.install()
        (self.root / kernel.MARKER).write_text("future-registry-v99\n")
        with self.assertRaisesRegex(ValueError, "unsupported"):
            kernel.status(self.root)

    def test_shared_install_admin_gate_and_readonly_status_are_separate(self):
        with mock.patch.object(kernel.os, "geteuid", return_value=12345):
            with self.assertRaisesRegex(ValueError, "administrator"):
                kernel.install(kernel.DEFAULT_ROOT, self.archive, self.identifier, yes=True)
        self.install()
        with mock.patch.object(kernel.os, "geteuid", return_value=12345):
            self.assertEqual(len(kernel.status(self.root)["installed"]), 1)

    def cli_copy(self):
        tools, binaries = self.work / "tools", self.work / "bin"
        tools.mkdir()
        binaries.mkdir()
        for name in ("mpm", "mpm_cli.py", "mpm_kernel.py", "mojt_artifact.py", "mpm_selection.py", "mpm_transaction.py"):
            shutil.copyfile(REPO / "tools" / name, tools / name)
        (binaries / "zstd").symlink_to(shutil.which("zstd"))
        return tools, dict(os.environ, PATH=str(binaries))

    def test_cli_without_any_provider_files_and_global_or_action_root(self):
        tools, environment = self.cli_copy()
        def cli(*args):
            run = subprocess.run([sys.executable, "-I", "-B", str(tools / "mpm"), *args],
                                 text=True, capture_output=True, env=environment)
            self.assertEqual(run.returncode, 0, run.stderr)
            return json.loads(run.stdout)
        first = cli("--root", str(self.root), "kernel", "status", "--json")
        self.assertEqual(first["installed"], [])
        preview = cli("kernel", "install", "--root", str(self.root), "--from-file", str(self.archive),
                      "--expected-id", self.identifier, "--dry-run")
        self.assertFalse(preview["changed"])
        self.assertFalse(self.root.exists())
        installed = cli("--root=" + str(self.root), "kernel", "install", "--from-file", str(self.archive),
                        "--expected-id", self.identifier, "-y")
        self.assertTrue(installed["changed"])
        self.archive.unlink()  # No original package/catalog needed for status/scrub.
        result = cli("kernel", "status", "--root", str(self.root), "--verify", "--json")
        self.assertEqual(result["installed"][0]["artifact"], self.identifier)

    def test_concurrent_installs_register_one_complete_object(self):
        with kernel.registry_lock(self.root):
            pass
        tools, environment = self.cli_copy()
        command = [sys.executable, "-I", "-B", str(tools / "mpm"), "--root", str(self.root), "kernel", "install",
                   "--from-file", str(self.archive), "--expected-id", self.identifier, "-y"]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment)
                     for _ in range(2)]
        results = []
        outputs = [process.communicate(timeout=30) for process in processes]
        for process, (output, errors) in zip(processes, outputs):
            self.assertEqual(process.returncode, 0, errors)
            results.append(json.loads(output))
        self.assertEqual(sum(r["changed"] for r in results), 1)
        self.assertEqual(len(kernel.status(self.root, verify=True)["installed"]), 1)


if __name__ == "__main__":
    unittest.main()


