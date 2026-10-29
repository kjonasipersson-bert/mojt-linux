# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real native inputs/install/cpio; disk and guest executables are synthetic fixtures."""
import contextlib
import copy
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import mojt_artifact as artifact
import mojt_native_image as native
import mpm_kernel as kernel

spec = importlib.util.spec_from_file_location("native_system_fixtures", Path(__file__).with_name("test_system_vm.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


def cpio(root):
    names = ["."] + ["./" + p.relative_to(root).as_posix() for p in sorted(root.rglob("*"))]
    packed = subprocess.run(["cpio", "--create", "--format=newc", "--null", "--quiet"], cwd=root,
        input=b"\0".join(os.fsencode(n) for n in names) + b"\0", capture_output=True, check=True).stdout
    return gzip.compress(packed, mtime=0)


@unittest.skipUnless(shutil.which("zstd") and shutil.which("cpio"), "requires real zstd and cpio")
class NativeImageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SystemVmTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.work = self.fixture.root
        self.fixture.fixture(6)
        self.fixture.busybox.write_text("#!/bin/sh\nprintf '%s\\n' cp ln umount halt\n")
        self.fixture.busybox.chmod(0o755)
        root = self.work / "base-root"
        for name in ("usr/bin", "usr/lib", "usr/etc", "etc", "var", "dev", "proc", "sys", "home", "root"):
            (root / name).mkdir(parents=True)
        (root / "bin").symlink_to("usr/bin")
        (root / "lib").symlink_to("usr/lib")
        (root / "usr/bin/sh").write_text("synthetic Base shell")
        (root / "usr/bin/sh").chmod(0o755)
        (root / "usr/lib/os-release").write_text('ID=mojt\nIMAGE_VERSION="0.1.3"\n')
        (root / "usr/etc/passwd").write_text("root:x:0:0:root:/root:/bin/sh\n")
        (root / "usr/etc/group").write_text("root:x:0:\n")
        (root / "usr/etc/hostname").write_text("mojt\n")
        release = self.work / "release"
        release.mkdir()
        def owner(info):
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            return info
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            archive.add(root, arcname=".", filter=owner)
        image = subprocess.check_output(["zstd", "-q", "-c"], input=stream.getvalue())
        (release / "rootfs.tar.zst").write_bytes(image)
        (release / "packages.txt").write_text("synthetic upstream package inventory\n")
        self.base_manifest = '''format=1
[base]
name="mojt"
version="0.1.3"
architecture="x86_64"
[abi]
libc="glibc"
libc_version="2.41"
[image]
file="rootfs.tar.zst"
sha256="@HASH@"
[state]
layout_version=1
etc_defaults="/usr/etc"
etc_policy="add-missing"
var_policy="persistent"
[build]
backend="fixture"
packages="packages.txt"
'''.replace("@HASH@", __import__("hashlib").sha256(image).hexdigest())
        (release / "manifest.toml").write_text(self.base_manifest)
        spec, unused = artifact.base_input(release, 1)
        base = artifact.pack(release, spec, self.work / "base-package")
        self.base = base["artifact"]
        kernel_source = self.work / "kernel-source"
        self.release = "6.12.107-mojt1"
        for name in ["boot/" + p + self.release for p in ("vmlinuz-", "config-", "System.map-")] + [
                "lib/modules/" + self.release + "/modules.dep", "lib/modules/" + self.release + "/kernel/example.ko"]:
            path = kernel_source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"native Kernel fixture")
        spec = dict(spec, kind="kernel", name="linux", version=dict(upstream="6.12.107", scheme="dotted-v1", revision=1),
                    metadata=dict(kernel_release=self.release), provenance={"fixture": True})
        result = artifact.pack(kernel_source, spec, self.work / "kernel-package")
        self.kernel = result["artifact"]
        self.registry = self.work / "kernel-registry"
        kernel.install(self.registry, self.work / "kernel-package" / result["archive"]["file"], self.kernel["id"], yes=True)
        bounds = dict(format=native.catalog.BASE_FORMAT, base=dict(artifact=self.base["id"], release="0.1.3"),
                      platform="x86_64-linux", kernel_min="6.12", kernel_max="6.12.999")
        self.bounds = self.work / "bounds.json"
        self.bounds.write_bytes(artifact.canonical(bounds))
        self.args = SimpleNamespace(base_package=self.work / "base-package" / base["archive"]["file"],
            base_artifact=self.base["id"], base_context=self.bounds, kernel_registry=self.registry,
            kernel_artifact=self.kernel["id"], system_payload=self.fixture.payload, output=self.work / "result",
            busybox=self.fixture.busybox, system_generation="native-fixture", disk_size_mib=512,
            login_mode="development", dry_run=False)

    def snapshot(self):
        sources = (self.args.base_package, self.registry, self.fixture.payload, self.args.base_context, self.args.busybox)
        return {str(path): (path.lstat().st_mode, path.lstat().st_mtime_ns,
                os.readlink(path) if path.is_symlink() else artifact.file_sha(path) if path.is_file() else None)
                for source in sources for path in (source, *source.rglob("*"))}

    def synthetic_build(self, corrupt=None):
        vm = fixtures.vm
        original = vm.make_initramfs
        def ramfs(root, *args, **kwargs):
            result = original(root, *args, **kwargs)
            if corrupt == "module":
                (root / "modules/0000.ko").write_bytes(b"wrong module")
                return cpio(root)
            if corrupt == "archive":
                return gzip.compress(b"not newc")
            return result
        def disk(path, tree, *args, **kwargs):
            native.boot.menu(tree, args[2], args[3], args[4])
            obj = tree / "kernel/installed" / self.kernel["id"].split(":")[1]
            kernel.object_record(obj, self.kernel["id"], verify=True)
            self.assertFalse((tree / "system/native-fixture/kernel").exists())
            path.write_bytes(b"synthetic disk; not guest boot acceptance")
            return {"synthetic": True}
        with mock.patch.object(vm, "static_x86_64_elf", return_value=True), \
                mock.patch.object(vm, "validate_busybox_applets"), \
                mock.patch.object(vm.shutil, "which", return_value="/synthetic/command"), \
                mock.patch.object(vm, "module_paths", side_effect=lambda release, root, **kw: [root / "kernel/example.ko"]), \
                mock.patch.object(vm.os, "mknod", side_effect=lambda path, *unused: path.touch()), \
                mock.patch.object(vm.boot, "build_disk", side_effect=disk), \
                mock.patch.object(vm, "make_initramfs", side_effect=ramfs), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return native.build(self.args, vm=vm)

    def test_real_input_preview_creates_no_output_import_or_state(self):
        self.args.dry_run = True
        before = self.snapshot()
        result = native.build(self.args)
        self.assertEqual(result["kernel"], self.kernel["id"])
        self.assertEqual(result["base"], self.base["id"])
        self.assertFalse(result["imports"])
        self.assertFalse(self.args.output.exists())
        self.assertEqual(self.snapshot(), before)

    def test_wrong_base_id_kernel_id_bounds_and_existing_output_fail_before_image(self):
        original = copy.copy(self.args)
        for key, value in (("base_artifact", "sha256:" + "0" * 64), ("kernel_artifact", "sha256:" + "0" * 64)):
            setattr(self.args, key, value)
            with self.subTest(key=key), self.assertRaises((ValueError, FileNotFoundError)):
                native.preview(self.args)
            self.args = copy.copy(original)
        bounds = json.loads(self.bounds.read_text())
        bounds["kernel_max"] = "6.12.106"
        self.bounds.write_text(json.dumps(bounds))
        with self.assertRaisesRegex(ValueError, "outside"):
            native.preview(self.args)
        bounds["kernel_max"] = "6.12.999"
        self.bounds.write_text(json.dumps(bounds))
        self.args.output.mkdir()
        (self.args.output / "disk.img").write_bytes(b"keep existing disk")
        with self.assertRaises(ValueError):
            native.preview(self.args)
        self.assertEqual((self.args.output / "disk.img").read_bytes(), b"keep existing disk")

    def test_base_extraction_keeps_original_release_bytes_and_extra_provenance(self):
        unpacked = self.work / "unpacked"
        native.unpack_base(self.args.base_package, self.base, unpacked)
        self.assertEqual((unpacked / "payload/manifest.toml").read_text(), self.base_manifest)
        self.assertEqual((unpacked / "payload/packages.txt").read_text(), "synthetic upstream package inventory\n")
        self.assertEqual(artifact.file_sha(unpacked / "payload/rootfs.tar.zst"),
                         artifact.regular_row(self.base["files"], "payload/rootfs.tar.zst")["sha256"])

    def test_base_adapter_cli_retains_original_release_and_versions(self):
        release = self.work / "release"
        before = {p.name: p.read_bytes() for p in release.iterdir()}
        output = self.work / "base-cli"
        result = subprocess.run([sys.executable, "-I", "-B", str(REPO / "tools/mojt-artifact-pack.py"), "base",
            "--release", str(release), "--revision", "1", "--output", str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        body = json.loads(result.stdout)["artifact"]
        self.assertEqual(body["id"], self.base["id"])
        self.assertEqual(body["version"]["release_id"], "0.1.3-r1")
        self.assertEqual(body["metadata"]["base_release"], "0.1.3")
        self.assertEqual({p.name: p.read_bytes() for p in release.iterdir()}, before)
        with self.assertRaises(ValueError):
            artifact.base_input(release, -1)

    def test_base_adapter_preserves_opaque_legacy_labels_and_rejects_bad_release_metadata(self):
        release = self.work / "opaque-release"
        shutil.copytree(self.work / "release", release)
        path = release / "manifest.toml"
        path.write_text(self.base_manifest.replace('version="0.1.3"', 'version="0.1.3-lab"'))
        spec, unused = artifact.base_input(release, 2)
        self.assertEqual(spec["version"], dict(upstream="0.1.3-lab", scheme="opaque-v1", revision=2))
        self.assertEqual(artifact.version(spec["version"])["release_id"], "0.1.3-lab-r2")
        path.write_text('format=1\nbase="not an object"\n')
        with self.assertRaisesRegex(ValueError, "invalid Base"):
            artifact.base_input(release, 1)

    def test_native_init_pins_artifact_mount_and_records_without_old_system_kernel(self):
        script = native.init_script(fixtures.system.init_script(fixtures.vm.INIT), self.kernel["id"], self.release,
                                    "0.1.3", "native-fixture")
        script = native.boot.init_script(script, "11111111-1111-4111-8111-111111111111", "native-fixture", "0.1.3")
        self.assertIn("/sysroot/kernel/installed/" + self.kernel["id"].split(":")[1] + "/payload/lib/modules", script)
        self.assertIn('mount -o remount,bind,ro /newroot/lib/modules', script)
        self.assertIn("/newroot/run/mojt/native-kernel-artifact", script)
        self.assertIn("/sysroot/boot/mojt/native-fixture/0.1.3/deployment.json", script)
        self.assertNotIn("/system/current", script)
        self.assertNotIn("/system/native-fixture/kernel", script)
        for bad in ("arbitrary script", fixtures.system.init_script(fixtures.vm.INIT).replace("mkdir /newroot/run/mojt", "mkdir /wrong")):
            with self.assertRaises(ValueError):
                native.init_script(bad, self.kernel["id"], self.release, "0.1.3", "native-fixture")

    def test_base_copy_allows_only_additive_mount_scaffolding(self):
        root = self.work / "copy-base"
        root.mkdir()
        (root / "lib").mkdir()
        (root / "lib/libc.so.6").write_bytes(b"original Base libc")
        old = native.base_inventory(root)
        (root / "lib/modules").mkdir()
        (root / "run").mkdir()
        self.assertEqual(native.check_base_copy(root, old)["added_scaffolding"], ["lib/modules", "run"])
        (root / "lib/libc.so.6").write_bytes(b"changed libc")
        with self.assertRaisesRegex(ValueError, "content/metadata changed"):
            native.check_base_copy(root, old)
        (root / "lib/libc.so.6").write_bytes(b"original Base libc")
        (root / "run/extra-library").write_bytes(b"not scaffolding")
        with self.assertRaisesRegex(ValueError, "unexpected addition"):
            native.check_base_copy(root, old)

    def test_fresh_authentication_resets_only_private_machine_defaults(self):
        target = self.work / "fresh-target"
        (target / "state/etc").mkdir(parents=True)
        (target / "base/0.1.3/usr/etc").mkdir(parents=True)
        for name in ("shadow", "gshadow", "securetty"):
            (target / "state/etc" / name).write_text("publisher default")
            (target / "base/0.1.3/usr/etc" / name).write_text("publisher default")
        native.fresh_login_state(target)
        for name in ("shadow", "gshadow", "securetty"):
            self.assertFalse((target / "state/etc" / name).exists())
            self.assertEqual((target / "base/0.1.3/usr/etc" / name).read_text(), "publisher default")
        (target / "state/etc/shadow").symlink_to("../keep")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            native.fresh_login_state(target)

    def test_actual_gzip_newc_inspection_catches_archive_bytes_and_tree_changes(self):
        root = self.work / "init-tree"
        (root / "modules").mkdir(parents=True)
        (root / "init").write_bytes(b"#!/bin/sh\n")
        (root / "modules/0000.ko").write_bytes(b"selected module")
        (root / "link").symlink_to("init")
        data = cpio(root)
        native.inspect_initramfs(data, root)
        (root / "init").write_bytes(b"wrong init")
        with self.assertRaisesRegex(ValueError, "contents differ"):
            native.inspect_initramfs(data, root)
        for bad in (data[:-4], gzip.compress(b"bad newc"), gzip.compress(gzip.decompress(data) + b"extra archive")):
            with self.subTest(size=len(bad)), self.assertRaises((ValueError, EOFError)):
                native.inspect_initramfs(bad, root)

    def test_newc_character_device_numbers_are_checked_without_creating_host_devices(self):
        def member(name, mode, major=0, minor=0):
            encoded = name.encode() + b"\0"
            fields = [1, mode, 0, 0, 1, 0, 0, 0, 0, major, minor, len(encoded), 0]
            header = b"070701" + b"".join(f"{value:08x}".encode() for value in fields) + encoded
            return header + b"\0" * (-len(header) % 4)
        expected = {"./dev/console": (0o020600, 0, 0, 5, 1, 0, __import__("hashlib").sha256(b"").hexdigest())}
        trailer = member("TRAILER!!!", 0)
        with mock.patch.object(native, "init_inventory", return_value=expected):
            native.inspect_initramfs(gzip.compress(member("dev/console", 0o020600, 5, 1) + trailer), self.work)
            with self.assertRaisesRegex(ValueError, "contents differ"):
                native.inspect_initramfs(gzip.compress(member("dev/console", 0o020600, 5, 2) + trailer), self.work)

    def test_absolute_guest_module_symlink_is_not_used_as_host_mount_target(self):
        tree = self.work / "unsafe-image"
        base = tree / "base/0.1.3"
        (base / "usr/lib").mkdir(parents=True)
        (base / "lib").symlink_to("/usr/lib")
        with self.assertRaisesRegex(ValueError, "absolute or escaping"):
            native.stage(tree, dict(registry=str(self.registry), kernel=self.kernel), "0.1.3")

    @unittest.skipUnless(os.geteuid() == 0, "real Base installation requires root")
    def test_full_native_input_pipeline_binds_real_cpio_and_preserves_originals(self):
        before = self.snapshot()
        self.synthetic_build()
        result = self.args.output
        selected = json.loads((result / "deployment.json").read_text())
        self.assertEqual(selected["description"]["base"]["artifact"], self.base["id"])
        self.assertEqual(selected["description"]["kernel"]["artifact"], self.kernel["id"])
        plan = json.loads((result / "kernel-plan.json").read_text())
        self.assertTrue(plan["no_change"])
        self.assertFalse(plan["boot_ready"])
        receipt = json.loads((result / "native-build-inputs.json").read_text())
        self.assertEqual(receipt["selection_origin"], "fresh-image-bootstrap")
        self.assertEqual(len(receipt["early_modules"]), 1)
        self.assertEqual(receipt["early_modules"][0]["stored_sha256"], receipt["early_modules"][0]["initramfs_sha256"])
        self.assertIn("usr/lib/modules", receipt["base_copy"]["added_scaffolding"])
        self.assertEqual(self.snapshot(), before)

    @unittest.skipUnless(os.geteuid() == 0, "real Base installation requires root")
    def test_corrupt_generated_module_or_archive_never_publishes_an_image(self):
        before = self.snapshot()
        for fault in ("module", "archive"):
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.synthetic_build(corrupt=fault)
            self.assertFalse(self.args.output.exists())
            self.assertEqual(self.snapshot(), before)

    @unittest.skipUnless(os.geteuid() == 0, "real Base installation requires root")
    def test_failed_final_plan_does_not_publish_completed_private_disk(self):
        before = self.snapshot()
        with mock.patch.object(native.deployment, "plan", side_effect=ValueError("injected final preflight failure")), \
                self.assertRaisesRegex(ValueError, "final preflight"):
            self.synthetic_build()
        self.assertFalse(self.args.output.exists())
        self.assertEqual(self.snapshot(), before)

    @unittest.skipUnless(os.geteuid() == 0, "real Base installation requires root")
    def test_password_mode_uses_terminal_callback_for_fresh_image_credentials(self):
        self.args.login_mode = "password"
        with mock.patch.object(fixtures.vm, "password_hash_from_terminal", return_value="$6$fixture$not-a-real-password") as prompt:
            self.synthetic_build()
        prompt.assert_called_once_with()
        record = json.loads((self.args.output / "build.json").read_text())
        self.assertEqual(record["login_mode"], "password")

    def test_cli_preview_works_without_privileged_build_or_nix_commands(self):
        command = [sys.executable, "-I", "-B", str(REPO / "tools/mojt-native-image.py"), "--dry-run"]
        for flag in ("base-package", "base-artifact", "base-context", "kernel-registry", "kernel-artifact",
                     "system-payload", "system-generation", "output"):
            command += ["--" + flag, str(getattr(self.args, flag.replace("-", "_")))]
        binaries = self.work / "preview-bin"
        binaries.mkdir()
        (binaries / "zstd").symlink_to(shutil.which("zstd"))
        result = subprocess.run(command, env=dict(os.environ, PATH=str(binaries)), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["image_written"])
        self.assertFalse(self.args.output.exists())


if __name__ == "__main__":
    unittest.main()
