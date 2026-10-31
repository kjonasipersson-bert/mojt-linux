# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Existing native-disk transactions using real packages/cpio and synthetic guest files."""
import copy
import gzip
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import mojt_artifact as artifact
import mpm_kernel as kernel
import mpm_kernel_boot as manager

spec = importlib.util.spec_from_file_location("kernel_boot_fixtures", Path(__file__).with_name("test_native_image.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class InitramfsWriterTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cpio"), "requires independent GNU cpio reader")
    def test_python_archive_can_be_read_and_extracted_by_gnu_cpio(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "input"
            (root / "bin").mkdir(parents=True)
            (root / "init").write_bytes(b"#!/bin/sh\necho boot\n")
            (root / "init").chmod(0o755)
            (root / "bin/link").symlink_to("../init")
            raw = manager.write_initramfs(root)
            destination = Path(temporary) / "extracted"
            destination.mkdir()
            result = subprocess.run(["cpio", "-idm", "--quiet", "--no-absolute-filenames"], cwd=destination,
                                    input=gzip.decompress(raw), capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((destination / "init").read_bytes(), (root / "init").read_bytes())
            self.assertEqual(os.readlink(destination / "bin/link"), "../init")
            self.assertEqual((destination / "init").stat().st_mode & 0o777, 0o755)
            self.assertEqual(manager.write_initramfs(root), raw)


@unittest.skipUnless(os.geteuid() == 0 and shutil.which("cpio") and shutil.which("zstd"),
                     "requires root, real native package tools and cpio")
class KernelBootTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.NativeImageTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.work / "disk-root"
        original = fixtures.native.boot.menu
        def capture(tree, *args, **kwargs):
            result = original(tree, *args, **kwargs)
            shutil.copytree(tree, self.root, symlinks=True)
            return result
        with mock.patch.object(fixtures.native.boot, "menu", side_effect=capture):
            self.fixture.synthetic_build()
        self.baseline = "boot/mojt/native-fixture/0.1.3"
        self.old, self.entries, self.menu = manager.current(self.root, self.baseline)
        self.old_id = self.old["selected"]
        # A second exact artifact with the same actual Kernel release proves that
        # uname/release-string matching cannot stand in for deployment identity.
        old_body = self.fixture.kernel
        spec = {k: copy.deepcopy(old_body[k]) for k in
                ("kind", "name", "platform", "dependencies", "requirements", "provides", "provenance", "metadata")}
        spec["format"] = artifact.SPEC_FORMAT
        spec["version"] = dict(upstream="6.12.107", scheme="dotted-v1", revision=2)
        result = artifact.pack(self.root / "kernel/installed" / kernel.identifier(old_body["id"]) / "payload",
                               spec, self.fixture.work / "candidate-package")
        self.candidate = result["artifact"]
        kernel.install(self.root / "kernel", self.fixture.work / "candidate-package" / result["archive"]["file"],
                       self.candidate["id"], yes=True)

    def build(self, root, body, selected, slot, busybox, work):
        vm = manager.vm_module()
        with mock.patch.object(manager, "vm_module", return_value=vm), \
                mock.patch.object(vm, "static_x86_64_elf", return_value=True), \
                mock.patch.object(vm, "validate_busybox_applets"), \
                mock.patch.object(vm, "module_paths", side_effect=lambda release, p, **kw: [p / "kernel/example.ko"]), \
                mock.patch.object(vm.os, "mknod", side_effect=lambda path, *unused: path.touch()):
            return manager.build_initramfs(root, body, selected, slot, busybox, work)

    def stage(self, **kwargs):
        return manager.stage(self.root, self.candidate["id"], baseline=self.baseline,
                             busybox=self.fixture.args.busybox, yes=True, builder=self.build, **kwargs)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): (p.lstat().st_mode, os.readlink(p) if p.is_symlink()
                    else artifact.file_sha(p) if p.is_file() else None) for p in self.root.rglob("*")}

    def test_preview_does_not_create_boot_registry_or_change_any_bytes(self):
        before = self.snapshot()
        result = self.stage(dry_run=True)
        self.assertFalse(result["changed"])
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.root / "boot/mpm").exists())

    def test_preview_and_status_inspect_each_boot_entry_once(self):
        # A previously checked menu entry must not be rehashed by available().
        with mock.patch.object(manager, "inspect_entry", wraps=manager.inspect_entry) as check:
            preview = self.stage(dry_run=True)
            self.assertFalse(preview["changed"])
            self.assertEqual(check.call_count, 1)
        with mock.patch.object(manager, "inspect_entry", wraps=manager.inspect_entry) as check:
            status = manager.status(self.root, baseline=self.baseline)
            self.assertEqual(status["selected"], self.old_id)
            self.assertEqual(check.call_count, 1)

    def test_selection_rechecks_candidate_at_publication(self):
        staged = self.stage()
        path = self.root / staged["slot"] / "initramfs.cpio.gz"
        original = manager.checked_file
        def alter_after_preview(source, *args, **kwargs):
            data = original(source, *args, **kwargs)
            if source == self.root / "boot/mojt/grub.cfg":
                menu_reads[0] += 1
                if menu_reads[0] == 3:
                    path.chmod(0o644)
                    path.write_bytes(b"tampered before publication")
            return data
        menu_reads = [0]
        with mock.patch.object(manager, "checked_file", side_effect=alter_after_preview):
            with self.assertRaisesRegex(ValueError, "initramfs differs"):
                manager.select(self.root, staged["deployment"], expected_selected=self.old_id,
                               baseline=self.baseline, yes=True)
        self.assertGreaterEqual(menu_reads[0], 3)
        self.assertEqual((self.root / "boot/mojt/grub.cfg").read_bytes(), self.menu)

    def test_stage_select_noop_and_rollback_preserve_old_files_and_system(self):
        protected = {p.relative_to(self.root).as_posix(): artifact.file_sha(p) for top in
                     (self.root / self.baseline, self.root / "base", self.root / "system", self.root / "state")
                     for p in top.rglob("*") if p.is_file() and not p.is_symlink()}
        result = self.stage()
        self.assertNotEqual(result["deployment"], self.old_id)
        self.assertEqual((self.root / "boot/mojt/grub.cfg").read_bytes(), self.menu)
        staged = manager.inspect_entry(self.root, result["slot"])
        data = gzip.decompress((staged["path"] / "initramfs.cpio.gz").read_bytes())
        self.assertIn(("/sysroot/" + result["slot"] + "/deployment.json").encode(), data)
        self.assertIn(self.candidate["id"].encode(), data)
        selected = manager.select(self.root, result["deployment"], expected_selected=self.old_id,
                                  baseline=self.baseline, yes=True)
        self.assertTrue(selected["changed"])
        status = manager.status(self.root)
        self.assertEqual(status["selected_kernel"]["artifact"], self.candidate["id"])
        self.assertIsNone(status["running"]["artifact"])
        menu = (self.root / "boot/mojt/grub.cfg").read_bytes()
        self.assertIn(self.old_id.encode(), menu)
        self.assertIn(result["deployment"].encode(), menu)
        repeated = manager.select(self.root, result["deployment"], expected_selected=result["deployment"], yes=True)
        self.assertFalse(repeated["changed"])
        self.assertEqual((self.root / "boot/mojt/grub.cfg").read_bytes(), menu)
        manager.select(self.root, None, expected_selected=result["deployment"], rollback=True, yes=True)
        self.assertEqual(manager.status(self.root)["selected"], self.old_id)
        self.assertTrue(staged["path"].exists())
        for relative, checksum in protected.items():
            self.assertEqual(artifact.file_sha(self.root / relative), checksum, relative)

    def test_failed_initramfs_build_leaves_selection_and_no_published_slot(self):
        with mock.patch.object(self, "build", side_effect=ValueError("injected initramfs failure")):
            with self.assertRaisesRegex(ValueError, "injected"):
                self.stage()
        self.assertEqual((self.root / "boot/mojt/grub.cfg").read_bytes(), self.menu)
        self.assertEqual(list((self.root / "boot/mpm/slots").iterdir()), [])

    def test_repeat_staging_is_noop_without_new_slot_or_initramfs_build(self):
        first = self.stage()
        before = self.snapshot()
        with mock.patch.object(self, "build", side_effect=AssertionError("must not rebuild")):
            repeated = self.stage()
        self.assertFalse(repeated["changed"])
        self.assertEqual(repeated["deployment"], first["deployment"])
        self.assertEqual(before, self.snapshot())

    def test_failed_atomic_menu_replacement_leaves_old_selection(self):
        result = self.stage()
        with mock.patch.object(manager.os, "replace", side_effect=OSError("injected publication failure")):
            with self.assertRaisesRegex(OSError, "injected"):
                manager.select(self.root, result["deployment"], baseline=self.baseline,
                               expected_selected=self.old_id, yes=True)
        self.assertEqual((self.root / "boot/mojt/grub.cfg").read_bytes(), self.menu)
        self.assertFalse(list((self.root / "boot/mojt").glob(".grub-*")))

    def test_unmanaged_menu_wrong_baseline_and_stale_selection_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "specify.*baseline"):
            manager.current(self.root)
        with self.assertRaises((ValueError, FileNotFoundError)):
            manager.current(self.root, "../escape")
        with self.assertRaisesRegex(ValueError, "changed"):
            manager.select(self.root, self.old_id, expected_selected="sha256:" + "0" * 64,
                           baseline=self.baseline, dry_run=True)
        (self.root / "boot/mojt/grub.cfg").write_bytes(self.menu + b"# local custom menu\n")
        with self.assertRaisesRegex(ValueError, "complete existing boot menu"):
            self.stage(dry_run=True)

    def test_corrupt_staged_initramfs_blocks_selection(self):
        result = self.stage()
        path = self.root / result["slot"] / "initramfs.cpio.gz"
        path.chmod(0o644)
        path.write_bytes(b"corrupt staged archive")
        with self.assertRaisesRegex(ValueError, "initramfs differs"):
            manager.select(self.root, result["deployment"], expected_selected=self.old_id,
                           baseline=self.baseline, yes=True)
        self.assertEqual((self.root / "boot/mojt/grub.cfg").read_bytes(), self.menu)

    def test_base_and_system_tampering_fail_before_staging(self):
        path = self.root / "base/0.1.3/usr/lib/os-release"
        original = path.read_bytes()
        path.write_bytes(original + b"tampered\n")
        with self.assertRaisesRegex(ValueError, "Base content"):
            self.stage()
        path.write_bytes(original)
        profile = self.root / "system/native-fixture/record.json"
        profile.write_bytes(profile.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "System profile"):
            self.stage()
        self.assertFalse((self.root / "boot/mpm").exists())

    def test_changed_ports_capability_blocks_selection_after_staging(self):
        result = self.stage()
        state = self.root / "state/var/lib/mojt/ports/current"
        state.mkdir(parents=True)
        (state / "state.json").write_text(json.dumps(dict(format=999, capabilities={})))
        with self.assertRaisesRegex(ValueError, "Ports format"):
            manager.select(self.root, result["deployment"], expected_selected=self.old_id,
                           baseline=self.baseline, yes=True)
        self.assertEqual((self.root / "boot/mojt/grub.cfg").read_bytes(), self.menu)

    def test_ordinary_user_cannot_change_boot_selection(self):
        with mock.patch.object(manager.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(ValueError, "administrator"):
                self.stage()

    def test_runtime_identity_is_explicit_and_not_inferred_from_release(self):
        result = self.stage()
        manager.select(self.root, result["deployment"], expected_selected=self.old_id, baseline=self.baseline, yes=True)
        old = self.root / self.baseline / "deployment.json"
        with mock.patch.object(manager.os, "uname", return_value=type("U", (), {
                "release": self.fixture.release, "machine": os.uname().machine})()):
            status = manager.status(self.root, running_record=old)
        self.assertFalse(status["running_is_selected"])
        self.assertEqual(status["running"]["artifact"], self.fixture.kernel["id"])
        self.assertEqual(status["selected_kernel"]["artifact"], self.candidate["id"])
        self.assertEqual(status["running"]["release"], status["selected_kernel"]["release"])

    def test_cli_status_and_stage_preview_work_without_nix_or_disk_tools(self):
        command = [sys.executable, "-I", "-B", str(REPO / "tools/mpm"), "kernel", "status",
                   "--disk-root", str(self.root), "--baseline", self.baseline, "--json"]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["selected"], self.old_id)
        self.assertFalse((self.root / "boot/mpm").exists())

    @unittest.skipUnless(shutil.which("grub-script-check"), "requires independent GRUB parser")
    def test_selected_menu_passes_real_grub_parser(self):
        result = self.stage()
        manager.select(self.root, result["deployment"], expected_selected=self.old_id,
                       baseline=self.baseline, yes=True)
        parsed = subprocess.run(["grub-script-check"], input=(self.root / "boot/mojt/grub.cfg").read_bytes(),
                                capture_output=True)
        self.assertEqual(parsed.returncode, 0, parsed.stderr)

    def preparation_module(self):
        spec = importlib.util.spec_from_file_location("prepare_kernel_vm", REPO / "tests/prepare-kernel-boot-vm.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_vm_copy_refuses_open_source_without_creating_output(self):
        prepare = self.preparation_module()
        output = self.fixture.work / "vm-copy"
        with mock.patch.object(prepare.os, "geteuid", return_value=1000), \
                mock.patch.object(prepare.shutil, "which", return_value="/synthetic/tool"), \
                mock.patch.object(prepare.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            with self.assertRaisesRegex(ValueError, "source disk is open"):
                prepare.prepare(self.fixture.args.output, output)
        self.assertFalse(output.exists())

    @unittest.skipUnless(shutil.which("mkfs.ext4") and shutil.which("fuser"), "requires real host copy/ext4 tools")
    def test_vm_copy_keeps_source_and_attaches_only_copy_and_readonly_inputs(self):
        prepare = self.preparation_module()
        output = self.fixture.work / "vm-copy"
        source = self.fixture.args.output / "disk.img"
        before = source.read_bytes(), source.stat().st_mtime_ns
        original = subprocess.run
        def run(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 1) if argv[0] == "fuser" else original(argv, **kwargs)
        with mock.patch.object(prepare.os, "geteuid", return_value=1000), \
                mock.patch.object(prepare.subprocess, "run", side_effect=run):
            prepare.prepare(self.fixture.args.output, output)
        self.assertEqual((source.read_bytes(), source.stat().st_mtime_ns), before)
        self.assertEqual((output / "disk.img").read_bytes(), source.read_bytes())
        script = (output / "run-qemu.sh").read_text()
        self.assertIn('file=$here/inputs.img,if=virtio,format=raw,readonly=on', script)
        self.assertNotIn(str(source), script)
        self.assertEqual((output / "inputs.img").stat().st_size, 64 * 1024**2)


if __name__ == "__main__":
    unittest.main()
