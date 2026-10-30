#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pinned boot selections and multi-generation assembly/failure contracts."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import unittest
from unittest import mock
import types


spec = importlib.util.spec_from_file_location("generation_fixtures", Path(__file__).with_name("test_system_vm.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
vm, system = fixtures.vm, fixtures.system
boot, generations = vm.boot, vm.generations
UUID = "38ae152c-b81a-44da-b23a-3341398debe6"


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SystemVmTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.target = self.fixture.root, self.fixture.tree

    def prepare(self):
        self.fixture.fixture(5)
        first = self.target / "base/0.1.3"
        for name in ("etc", "var", "dev", "proc", "sys"):
            (first / name).mkdir()
        shutil.copytree(first, self.target / "base/0.1.4")
        (self.target / "base/current").symlink_to("0.1.4")
        system.write(self.target / ".install-lock", "")
        system.write(self.target / "state/layout-version", "1\n")
        for version in ("0.1.3", "0.1.4"):
            system.write(self.target / "releases" / f"base-{version}.toml", f'''format = 1
[base]
version = "{version}"
architecture = "x86_64"
[abi]
libc = "glibc"
libc_version = "2.41"
[state]
layout_version = 1
etc_policy = "add-missing"
var_policy = "persistent"
''')
        system.write(self.target / "state/var/retained", "machine data")
        system.write(self.target / "state/home/example/data", "personal data")
        system.write(self.target / "state/root/.lesshst", "root history")
        (self.target / "state/root").chmod(0o700)
        kernel = self.root / "vmlinuz-test"
        kernel.write_bytes(b"kernel A")
        modules = self.root / "modules"
        modules.mkdir()
        self.fixture.busybox.write_text("#!/bin/sh\nprintf '%s\\n' cp ln umount halt sort printf\n")
        self.fixture.busybox.chmod(0o755)
        plan = self.root / "plan.toml"
        plan.write_text('format = 1\n[[boot]]\nbase = "0.1.3"\nsystem = "B"\n'
                        '[[boot]]\nbase = "0.1.4"\nsystem = "B"\n')
        return types.SimpleNamespace(
            boot_mode="uefi", system_payload=self.fixture.payload, disk_size_mib=512,
            target=self.target, output=self.root / "new-image", kernel=kernel,
            modules_dir=modules, busybox=self.fixture.busybox, login_mode="development",
            root_shell=None, base_generation="0.1.3", system_generation="A",
            additional_generations=plan, hardware_profile=None, firmware_root=None)

    def build(self, args, *, fail_initramfs=None, assemble=None):
        calls = []

        def initramfs(*unused, **options):
            script = unused[3]
            calls.append(script)
            if fail_initramfs and len(calls) == fail_initramfs:
                raise ValueError("injected generation build interruption")
            return script.encode("ascii")

        def disk(path, tree, work, size, root_uuid, selected, base, **options):
            if assemble:
                assemble(tree, root_uuid)
            boot.menu(tree, root_uuid, selected, base)
            path.write_bytes(b"synthetic disk")
            return {"root_uuid": root_uuid}

        with mock.patch.object(vm.os, "geteuid", return_value=0), \
                mock.patch.object(vm.platform, "machine", return_value="x86_64"), \
                mock.patch.object(vm.os, "chown"), \
                mock.patch.object(vm.shutil, "which", return_value="/synthetic/command"), \
                mock.patch.object(vm, "static_x86_64_elf", return_value=True), \
                mock.patch.object(vm, "validate_busybox_applets"), \
                mock.patch.object(vm, "module_paths", return_value=[]), \
                mock.patch.object(vm, "make_initramfs", side_effect=initramfs), \
                mock.patch.object(vm.boot, "build_disk", side_effect=disk), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            vm.build(args)
        return calls

    def test_mixed_account_and_legacy_profiles_are_refused_before_assembly(self):
        args = self.prepare()
        entries = generations.plan(args.additional_generations, boot.generation)
        support = types.SimpleNamespace(load_payload=lambda _: {"step": 10})
        output = self.root / "unpublished"
        with self.assertRaisesRegex(ValueError, "legacy"):
            vm.additional_pairs(entries, tree=output, work=self.root,
                target=self.target, first_base="0.1.3", support=support, args=args,
                root_uuid=UUID, console="serial", assembled_at="test", account_mode=False)
        self.assertFalse(output.exists())

    def test_three_pairs_keep_first_default_and_source_state_unchanged(self):
        args = self.prepare()
        before = system.tree_hash(self.target)

        def inspect(tree, root_uuid):
            menu = boot.menu(tree, root_uuid, "A", "0.1.3")
            self.assertEqual({(r["system_generation"], r["base"]) for r in menu},
                             {("A", "0.1.3"), ("B", "0.1.3"), ("B", "0.1.4")})
            self.assertEqual(menu[0]["system_generation"], "A")
            self.assertEqual((tree / "base/current").readlink().as_posix(), "0.1.3")
            self.assertEqual((tree / "system/current").readlink().as_posix(), "A")
            self.assertEqual((tree / "state/var/retained").read_text(), "machine data")
            self.assertEqual((tree / "state/home/example/data").read_text(), "personal data")
            self.assertEqual((tree / "state/root/.lesshst").read_text(), "root history")
            for name in ("passwd", "inittab"):
                self.assertEqual((tree / "state/etc" / name).read_bytes(),
                                 (self.target / "state/etc" / name).read_bytes())
            for selected in ("A", "B"):
                roots = tree / "nix/var/nix/gcroots/mojt-system" / selected
                self.assertTrue(any(roots.iterdir()))
                self.assertIn(".mojt-registration-loaded-" + selected,
                              (tree / "system" / selected / "setup").read_text())
            self.assertEqual(len(list((tree / "nix/store").iterdir())),
                             len(list((self.fixture.payload / "nix/store").iterdir())))

        scripts = self.build(args, assemble=inspect)
        self.assertEqual(len(scripts), 3)
        for script, base, selected in zip(scripts, ("0.1.3", "0.1.3", "0.1.4"), ("A", "B", "B")):
            self.assertNotIn("/sysroot/base/current", script)
            self.assertNotIn("/sysroot/system/current", script)
            self.assertIn('version="' + base + '"', script)
            self.assertIn("/sysroot/system/" + selected + "/start", script)
        self.assertEqual(system.tree_hash(self.target), before)
        record = json.loads((args.output / "build.json").read_text())
        self.assertEqual(len(record["additional_boot_records"]), 2)

    def test_failure_in_second_pair_preserves_source_and_previous_disk(self):
        args = self.prepare()
        previous = self.root / "known-good.img"
        previous.write_bytes(b"known good disk")
        before = system.tree_hash(self.target)
        with self.assertRaisesRegex(ValueError, "interruption"):
            self.build(args, fail_initramfs=2)
        self.assertFalse(args.output.exists())
        self.assertEqual(previous.read_bytes(), b"known good disk")
        self.assertEqual(system.tree_hash(self.target), before)
        self.assertEqual(list(self.root.glob(".mojt-vm-*")), [])

    def test_existing_output_is_refused_before_staging(self):
        args = self.prepare()
        args.output.mkdir()
        (args.output / "disk.img").write_bytes(b"retained boot image")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.build(args)
        self.assertEqual((args.output / "disk.img").read_bytes(), b"retained boot image")

    def test_undeclared_abi_change_blocks_second_base(self):
        args = self.prepare()
        manifest = self.target / "releases/base-0.1.4.toml"
        manifest.write_text(manifest.read_text().replace('"2.41"', '"2.42"'))
        with self.assertRaisesRegex(ValueError, "identical declared Base ABI"):
            self.build(args)
        self.assertFalse(args.output.exists())

    def test_generation_plan_rejects_duplicate_unknown_and_mutable_labels(self):
        path = self.root / "bad.toml"
        for contents in ('format = true\nboot = []\n',
                         'format = 1\n[[boot]]\nbase="b"\nsystem="current"\n',
                         'format = 1\n[[boot]]\nbase="b"\nsystem="s"\nunsafe=true\n',
                         'format=1\n[[boot]]\nbase="b"\nsystem="s"\n[[boot]]\nbase="b"\nsystem="s"\n'):
            path.write_text(contents)
            with self.subTest(contents=contents), self.assertRaises(ValueError):
                generations.plan(path, boot.generation)

    def test_reused_system_name_with_different_kernel_is_rejected(self):
        args = self.prepare()
        other = self.root / "vmlinuz-other"
        other.write_bytes(b"different kernel")
        args.additional_generations.write_text(
            'format=1\n[[boot]]\nbase="0.1.4"\nsystem="A"\nkernel="vmlinuz-other"\n')
        with self.assertRaisesRegex(ValueError, "different kernel inputs"):
            self.build(args)
        self.assertFalse(args.output.exists())

    def test_shared_store_object_conflicts_are_rejected(self):
        source, destination = self.root / "source", self.root / "destination"
        system.write(source / "bin/tool", "first")
        shutil.copytree(source, destination)
        generations.identical_or_copy(source, destination, system.tree_hash)
        (source / "bin/tool").write_text("second")
        with self.assertRaisesRegex(ValueError, "conflicting immutable"):
            generations.identical_or_copy(source, destination, system.tree_hash)
        self.assertEqual((destination / "bin/tool").read_text(), "first")

    def test_corrupted_boot_artifact_does_not_replace_a_verified_menu(self):
        tree = self.root / "image"
        kernel = self.root / "vmlinuz-test"
        kernel.write_bytes(b"known kernel")
        boot.stage(tree, kernel, b"known initramfs", [], release="test",
                   base="base-A", system="A", root_uuid=UUID)
        boot.menu(tree, UUID, "A", "base-A")
        menu = tree / "boot/mojt/grub.cfg"
        original = menu.read_bytes()
        boot.stage(tree, kernel, b"second initramfs", [], release="test",
                   base="base-B", system="B", root_uuid=UUID)
        (tree / "boot/mojt/B/base-B/initramfs.cpio.gz").write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "recorded hash"):
            boot.menu(tree, UUID, "B", "base-B")
        self.assertEqual(menu.read_bytes(), original)

    def test_missing_defaults_do_not_follow_existing_state_symlink(self):
        source, destination, outside = (self.root / n for n in ("defaults", "state", "outside"))
        system.write(source / "sub/new", "new default")
        destination.mkdir()
        outside.mkdir()
        (destination / "sub").symlink_to(outside)
        generations.add_missing(source, destination)
        self.assertEqual(list(outside.iterdir()), [])

    def test_boot_selectors_are_checked_by_executing_generated_shell(self):
        script = boot.init_script(system.init_script(vm.INIT), UUID, "A", "base-A")
        selectors = script[script.index("IFS= read -r mojt_cmdline"):script.index("tries=0")]
        command = self.root / "cmdline"
        selectors = selectors.replace("</proc/cmdline", "<" + shlex.quote(str(command)))
        valid = boot.cmdline(UUID, "A", "base-A")
        cases = [valid, valid.replace("mojt.base=base-A", ""),
                 valid.replace("mojt.base=base-A", "mojt.base=base-B"),
                 valid.replace("mojt.system=A", "mojt.system=B"),
                 valid + " mojt.base=base-A", "mojt.base= " + valid,
                 valid + " root=UUID=" + UUID]
        for index, contents in enumerate(cases):
            command.write_text(contents + "\n")
            run = subprocess.run(["sh"], text=True, capture_output=True,
                                 input='panic() { echo "$*"; exit 42; }\n' + selectors + '\necho accepted\n')
            self.assertEqual(run.returncode, 0 if index == 0 else 42, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()

