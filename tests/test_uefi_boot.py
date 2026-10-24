#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""UEFI image contracts and real regular-file GPT/FAT/GRUB assembly."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, REPO / "tools" / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


boot = module("mojt_uefi_test", "mojt_boot.py")
vm = module("mojt_uefi_vm_test", "mojt-vm-build.py")
system = module("mojt_uefi_system_test", "mojt_system.py")
UUID = "38ae152c-b81a-44da-b23a-3341398debe6"
SYSTEM = "0.2-step5"


class UefiTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mojt-uefi-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def stage(self):
        tree = self.root / "tree"
        tree.mkdir()
        kernel = self.root / "vmlinuz-6.8-test"
        kernel.write_bytes(b"synthetic kernel")
        module = self.root / "virtio.ko"
        module.write_bytes(b"synthetic module")
        record = boot.stage(tree, kernel, b"synthetic initramfs", [module],
                            release="6.8-test", base="0.1.3", system=SYSTEM, root_uuid=UUID)
        return tree, record

    def test_layout_reserves_aligned_esp_and_backup_gpt_space(self):
        p = boot.layout(512)
        self.assertEqual(p["esp_offset"] % boot.MIB, 0)
        self.assertEqual(p["esp_offset"] + p["esp_bytes"], p["root_offset"])
        self.assertEqual(p["disk_bytes"] - p["root_offset"] - p["root_bytes"], boot.MIB)
        for size in (0, 256, 511, True, "512"):
            with self.assertRaises(ValueError):
                boot.layout(size)

    def test_boot_selectors_cannot_inject_shell_or_grub_syntax(self):
        for value in ("../current", "a/b", "a'b", "a;b", "a b", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                boot.cmdline(UUID, value)
        for value in ("root=/dev/vda", UUID.upper(), "not-a-uuid"):
            with self.assertRaises(ValueError):
                boot.cmdline(value, SYSTEM)

    def test_early_init_uses_uuid_and_exact_system_including_identity_reads(self):
        script = boot.init_script(system.init_script(vm.INIT), UUID, SYSTEM)
        self.assertIn('findfs "$mojt_root"', script)
        self.assertIn('root=*) mojt_root=${mojt_arg#root=}', script)
        self.assertIn(f'[ "$mojt_system" = "{SYSTEM}" ]', script)
        self.assertIn(f'/sysroot/system/{SYSTEM}/start', script)
        self.assertIn(f'/sysroot/system/{SYSTEM}/version', script)
        self.assertNotIn('/sysroot/system/current', script)
        self.assertNotIn('/dev/vda', script)
        subprocess.run(["sh", "-n"], input=script, text=True, check=True, capture_output=True)
        with self.assertRaisesRegex(ValueError, "template"):
            boot.init_script(vm.INIT, UUID, SYSTEM)

    def test_stage_records_hashes_of_exact_disk_boot_pair_and_module_inputs(self):
        tree, record = self.stage()
        path = tree / "boot/mojt" / SYSTEM
        self.assertEqual(record["kernel_sha256"], boot.digest(path / "vmlinuz"))
        self.assertEqual(record["initramfs_sha256"], boot.digest(path / "initramfs.cpio.gz"))
        self.assertEqual(record["module_inputs"][0]["sha256"], boot.digest(self.root / "virtio.ko"))
        self.assertEqual(json.loads((path / "boot.json").read_text()), record)
        config = (path / "grub.cfg").read_text()
        self.assertIn(record["cmdline"], config)
        self.assertIn(f'initrd /boot/mojt/{SYSTEM}/initramfs.cpio.gz', config)
        self.assertEqual(config.count("menuentry "), 1)

    def test_findfs_applet_required_for_uefi_only(self):
        fake = mock.Mock(stdout="\n".join(vm.REQUIRED_APPLETS))
        with mock.patch.object(vm.subprocess, "run", return_value=fake):
            vm.validate_busybox_applets(Path("/test/busybox"))
            with self.assertRaisesRegex(ValueError, "findfs"):
                vm.validate_busybox_applets(Path("/test/busybox"), extra=("findfs",))

    def test_external_module_tree_is_used_for_kmod_dependency_resolution(self):
        modules = self.root / "kernel/lib/modules/6.8-test"
        modules.mkdir(parents=True)
        path = modules / "virtio.ko"
        path.write_bytes(b"module")
        with mock.patch.object(vm.subprocess, "run", return_value=mock.Mock(stdout=f"insmod {path}\n")) as run:
            self.assertEqual(vm.module_paths("6.8-test", modules), [path])
        self.assertEqual(run.call_args.args[0][:3], ["modprobe", "--dirname", str(self.root / "kernel")])

    def test_uefi_without_system_fails_before_host_commands_or_output_creation(self):
        args = mock.Mock(boot_mode="uefi", system_payload=None)
        with mock.patch.object(vm.os, "geteuid", return_value=0), \
                mock.patch.object(vm.platform, "machine", return_value="x86_64"), \
                mock.patch.object(vm.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "requires --system-payload"):
                vm.build(args)
            run.assert_not_called()

    def test_launcher_boots_firmware_and_retains_private_per_vm_variables(self):
        directory = self.root / "vm with spaces"
        directory.mkdir()
        script = directory / "run-qemu.sh"
        script.write_text(boot.run_script(network=True))
        for option in ("-kernel", "-initrd", "-append"):
            self.assertNotIn(option, script.read_text())
        subprocess.run(["bash", "-n", str(script)], check=True)
        code, template = self.root / "CODE.fd", self.root / "VARS.fd"
        code.write_text("firmware")
        template.write_text("fresh variables")
        commands = self.root / "commands"
        commands.mkdir()
        capture = self.root / "args.json"
        fake = commands / "qemu-system-x86_64"
        fake.write_text("#!/usr/bin/env python3\nimport os,sys,json\n"
                        "from pathlib import Path\n"
                        "Path(os.environ['CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n")
        fake.chmod(0o755)
        env = {**os.environ, "PATH": str(commands) + ":" + os.environ["PATH"],
               "OVMF_CODE": str(code), "OVMF_VARS_TEMPLATE": str(template), "CAPTURE": str(capture)}
        subprocess.run(["bash", str(script)], env=env, check=True)
        variables = directory / "OVMF_VARS.fd"
        self.assertEqual(variables.read_text(), "fresh variables")
        self.assertEqual(variables.stat().st_mode & 0o777, 0o600)
        self.assertIn("user,model=virtio-net-pci", json.loads(capture.read_text()))
        variables.write_text("retained firmware state")
        subprocess.run(["bash", str(script)], env=env, check=True)
        self.assertEqual(variables.read_text(), "retained firmware state")
        self.assertEqual(code.read_text(), "firmware")
        self.assertEqual(template.read_text(), "fresh variables")

    def test_launcher_missing_firmware_fails_before_creating_variables(self):
        script = self.root / "run.sh"
        script.write_text(boot.run_script())
        result = subprocess.run(["bash", str(script)], env={**os.environ,
            "OVMF_CODE": str(self.root / "missing"), "OVMF_VARS_TEMPLATE": str(self.root / "missing")},
            text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OVMF firmware missing", result.stderr)
        self.assertFalse((self.root / "OVMF_VARS.fd").exists())

    def test_partition_copy_checks_extent_size_and_leaves_adjacent_bytes_untouched(self):
        source, disk = self.root / "partition", self.root / "disk"
        source.write_bytes(b"DATA")
        disk.write_bytes(b"A" * 12)
        boot.copy_partition(source, disk, 4, 4)
        self.assertEqual(disk.read_bytes(), b"AAAADATAAAAA")
        with self.assertRaisesRegex(ValueError, "size"):
            boot.copy_partition(source, disk, 4, 5)
        with self.assertRaisesRegex(ValueError, "outside"):
            boot.copy_partition(source, disk, 10, 4)

    def test_existing_disk_is_not_overwritten(self):
        disk = self.root / "existing.img"
        disk.write_bytes(b"keep this disk")
        with self.assertRaises(FileExistsError):
            boot.build_disk(disk, self.root, self.root, 512, UUID, SYSTEM)
        self.assertEqual(disk.read_bytes(), b"keep this disk")
        link = self.root / "link.img"
        link.symlink_to(self.root / "outside.img")
        with self.assertRaisesRegex(ValueError, "symlink"):
            boot.build_disk(link, self.root, self.root, 512, UUID, SYSTEM)
        self.assertFalse((self.root / "outside.img").exists())

    @unittest.skipUnless(all(shutil.which(c) for c in boot.COMMANDS + ("debugfs",)),
                         "UEFI host image tools unavailable")
    def test_real_gpt_fat_grub_image_contains_exact_boot_pair_and_matching_uuid(self):
        tree, record = self.stage()
        work = self.root / "work"
        work.mkdir()
        disk = self.root / "disk.img"
        parts = boot.build_disk(disk, tree, work, 512, UUID, SYSTEM)
        self.assertEqual(disk.stat().st_size, 512 * boot.MIB)
        with disk.open("rb") as stream:
            stream.seek(512)
            self.assertEqual(stream.read(8), b"EFI PART")
        loader = self.root / "extracted.efi"
        subprocess.run(["mcopy", "-i", f"{disk}@@{parts['esp_offset']}",
                        "::/EFI/BOOT/BOOTX64.EFI", str(loader)], check=True)
        self.assertEqual(boot.digest(loader), parts["efi_loader_sha256"])
        self.assertEqual(loader.read_bytes()[:2], b"MZ")
        root = work / "mojt.ext4"
        result = subprocess.run(["debugfs", "-R", "stats", str(root)],
                                capture_output=True, text=True, check=True)
        self.assertIn(UUID, result.stdout)
        for filename, expected in (("vmlinuz", b"synthetic kernel"),
                                   ("initramfs.cpio.gz", b"synthetic initramfs")):
            destination = self.root / ("extracted-" + filename)
            subprocess.run(["debugfs", "-R", f"dump /boot/mojt/{SYSTEM}/{filename} {destination}", str(root)],
                           capture_output=True, check=True)
            self.assertEqual(destination.read_bytes(), expected)
        self.assertEqual(record["root_uuid"], parts["root_uuid"])


if __name__ == "__main__":
    unittest.main()
