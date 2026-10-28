# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real tar/zstd round trips for four native artifact kinds; no install or Nix."""
import copy
import difflib
import hashlib
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

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import mojt_artifact as artifact
from mpm_selection import Catalog


def spec(kind, version="1.2.3", revision=None, scheme="dotted-v1"):
    return dict(format=artifact.SPEC_FORMAT, kind=kind, name="linux" if kind == "kernel" else "example",
                platform="x86_64-linux", version=dict(upstream=version, revision=revision, scheme=scheme),
                dependencies=[], requirements={}, provides={}, provenance={},
                metadata=dict(kernel_release="6.12.107-mojt1") if kind == "kernel" else
                dict(system_role="component") if kind == "system" else {})


def compress(raw):
    return subprocess.check_output(["zstd", "-q", "-3", "-T1", "-c"], input=raw)


def raw_tar(path):
    return subprocess.check_output(["zstd", "-q", "-d", "-c", "--", str(path)])


def members(path):
    return tarfile.open(fileobj=io.BytesIO(raw_tar(path)), mode="r:")


@unittest.skipUnless(shutil.which("zstd"), "requires zstd")
class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.source = self.work / "source"
        self.source.mkdir()
        self.serial = 0

    def file(self, path, content=b"payload", mode=0o644):
        target = self.source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(mode)
        return target

    def package(self, value=None, source=None, attachments=None):
        self.serial += 1
        output = self.work / ("package-" + str(self.serial))
        result = artifact.pack(source or self.source, value or spec("port"), output, attachments)
        return output / result["archive"]["file"], result

    def kernel(self):
        release = "6.12.107-mojt1"
        for path in ("boot/vmlinuz-", "boot/config-", "boot/System.map-"):
            self.file(path + release)
        self.file("lib/modules/" + release + "/modules.dep", b"kernel/example.ko:\n")
        self.file("lib/modules/" + release + "/kernel/example.ko", b"synthetic module")

    def base(self):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:") as inner:
            directory = tarfile.TarInfo("./usr")
            directory.type, directory.mode = tarfile.DIRTYPE, 0o755
            inner.addfile(directory)
            link = tarfile.TarInfo("./bin")
            link.type, link.linkname = tarfile.SYMTYPE, "usr/bin"
            inner.addfile(link)
            executable = tarfile.TarInfo("./usr/tool")
            executable.size, executable.mode, executable.uid = 4, 0o4755, 1001
            inner.addfile(executable, io.BytesIO(b"base"))
        image = compress(stream.getvalue())
        self.file("rootfs.tar.zst", image)
        checksum = hashlib.sha256(image).hexdigest()
        self.file("manifest.toml", ('format = 1\n[base]\nversion = "1.2.3"\n'
                  '[image]\nfile = "rootfs.tar.zst"\nsha256 = "' + checksum + '"\n').encode())
        return image

    def test_all_four_kinds_have_only_category_members_and_embedded_detached_descriptor(self):
        for kind in artifact.KINDS:
            with self.subTest(kind=kind):
                shutil.rmtree(self.source)
                self.source.mkdir()
                if kind == "base":
                    self.base()
                elif kind == "kernel":
                    self.kernel()
                else:
                    self.file("bin/tool", mode=0o755)
                package, result = self.package(spec(kind))
                body = artifact.verify(package, result["artifact"]["id"])
                self.assertEqual(body["kind"], kind)
                with members(package) as archive:
                    self.assertTrue(all(m.name == "./" + kind or m.name.startswith("./" + kind + "/") for m in archive))
                    embedded = archive.extractfile("./" + kind + "/artifact.json").read()
                self.assertEqual(embedded, (package.parent / "artifact.json").read_bytes())
                self.assertEqual(hashlib.sha256(package.read_bytes()).hexdigest(), result["archive"]["sha256"])
                if shutil.which("tar"):
                    listing = subprocess.check_output(["tar", "-tf", "-"], input=raw_tar(package)).decode().splitlines()
                    self.assertTrue(listing)
                    self.assertTrue(all(name.startswith("./" + kind + "/") for name in listing))

    def test_base_inner_archive_is_unchanged_including_ownership_modes_and_symlink(self):
        image = self.base()
        package, _ = self.package(spec("base"))
        with members(package) as outer:
            packed = outer.extractfile("./base/payload/rootfs.tar.zst").read()
        self.assertEqual(packed, image)
        decoded = subprocess.check_output(["zstd", "-q", "-d", "-c"], input=packed)
        with tarfile.open(fileobj=io.BytesIO(decoded)) as archive:
            self.assertEqual(archive.getmember("./bin").linkname, "usr/bin")
            self.assertEqual(archive.getmember("./usr/tool").uid, 1001)
            self.assertEqual(archive.getmember("./usr/tool").mode, 0o4755)

    def test_base_hash_or_version_mismatch_is_rejected(self):
        self.base()
        self.file("rootfs.tar.zst", b"corrupt")
        with self.assertRaisesRegex(ValueError, "hash"):
            self.package(spec("base"))
        self.base()
        with self.assertRaisesRegex(ValueError, "version"):
            self.package(spec("base", "2.0"))

    def test_base_release_outer_files_can_be_hardlinked_without_losing_image_checks(self):
        self.base()
        os.link(self.source / "manifest.toml", self.source / "aaa-manifest")
        os.link(self.source / "rootfs.tar.zst", self.source / "aaa-image")
        package, result = self.package(spec("base"))
        self.assertEqual(artifact.verify(package)["id"], result["artifact"]["id"])
        with members(package) as archive:
            self.assertTrue(archive.getmember("./base/payload/manifest.toml").islnk())
            self.assertTrue(archive.getmember("./base/payload/rootfs.tar.zst").islnk())

    def test_tree_owners_modes_symlinks_hardlinks_and_long_unicode_paths_survive(self):
        original = self.file("bin/tool", mode=0o4755)
        os.link(original, self.source / "bin/tool-copy")
        (self.source / "bin/alias").symlink_to("tool")
        (self.source / "external").symlink_to("/nix/store/" + "a" * 120 + "/bin/tool")
        long_name = "share/" + "a" * 100 + "/" + "b" * 100 + "/åäö.txt"
        self.file(long_name, b"long path")
        package, result = self.package()
        artifact.verify(package)
        with members(package) as archive:
            first = archive.getmember("./port/payload/bin/tool")
            hardlink = archive.getmember("./port/payload/bin/tool-copy")
            self.assertEqual((first.mode, first.uid, first.gid), (0o4755, original.stat().st_uid, original.stat().st_gid))
            self.assertTrue(hardlink.islnk())
            self.assertEqual(hardlink.linkname, "./port/payload/bin/tool")
            self.assertEqual(archive.getmember("./port/payload/bin/alias").linkname, "tool")
            self.assertTrue(archive.getmember("./port/payload/external").issym())
            self.assertEqual(archive.extractfile("./port/payload/" + long_name).read(), b"long path")

    def test_system_composition_and_provider_references_do_not_fetch_or_relocate(self):
        value = spec("system", "system-A", scheme="opaque-v1")
        value["metadata"]["system_role"] = "generation"
        value["dependencies"] = [dict(provider="native", artifact="sha256:" + "a" * 64),
                                 dict(provider="example-provider", identity=dict(reference="exact-build-1"))]
        self.file("composition.json", b'{"component":"exact-build-1"}')
        package, result = self.package(value)
        self.assertEqual(artifact.verify(package)["dependencies"], value["dependencies"])
        self.assertEqual(result["artifact"]["version"]["release_id"], "system-A")

    def test_content_identity_excludes_paths_mtimes_and_compressed_transport_hash(self):
        path = self.file("bin/tool")
        one, first = self.package()
        os.utime(path, (123456, 654321))
        two, second = self.package()
        self.assertEqual(first["artifact"]["id"], second["artifact"]["id"])
        self.assertEqual(one.read_bytes(), two.read_bytes())
        self.assertNotIn("sha256", first["artifact"])  # No self/archive checksum field.
        descriptor = json.loads((one.parent / "artifact.json").read_bytes())
        identifier = descriptor.pop("id")
        expected = json.dumps(descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        self.assertEqual(identifier, "sha256:" + hashlib.sha256(expected).hexdigest())
        self.assertNotIn(str(self.source), one.parent.joinpath("artifact.json").read_text())

    def test_bytes_modes_revision_dependencies_and_provenance_change_identity(self):
        path = self.file("tool")
        _, original = self.package()
        original_id = original["artifact"]["id"]
        path.write_bytes(b"changed")
        _, changed = self.package()
        self.assertNotEqual(original_id, changed["artifact"]["id"])
        path.write_bytes(b"payload")
        path.chmod(0o755)
        _, changed = self.package()
        self.assertNotEqual(original_id, changed["artifact"]["id"])
        path.chmod(0o644)
        for key, replacement in [("version", dict(upstream="1.2.3", scheme="dotted-v1", revision=1)),
                                 ("dependencies", [dict(provider="native", artifact="sha256:" + "b" * 64)]),
                                 ("provenance", dict(source_commit="f" * 40))]:
            value = spec("port")
            value[key] = replacement
            _, changed = self.package(value)
            self.assertNotEqual(original_id, changed["artifact"]["id"])

    def test_numeric_revision_maps_to_existing_catalog_without_touching_kernel_release(self):
        self.kernel()
        value = spec("kernel", "6.12.107", revision=1)
        package, result = self.package(value)
        body = result["artifact"]
        self.assertEqual(body["version"]["release_id"], "6.12.107-r1")
        self.assertEqual(body["metadata"]["kernel_release"], "6.12.107-mojt1")
        self.assertIn("6.12.107-r1", package.name)
        self.assertTrue(any("vmlinuz-6.12.107-mojt1" in row["path"] for row in body["files"]))
        Catalog.from_dict(dict(format="mpm-release-catalog-v1", area="kernel", name="local", channel="stable",
            platform=body["platform"], sources={"local": dict(backend="native", identity=dict(publisher="local"))},
            candidates=[dict(name=body["name"], release_id=body["version"]["release_id"], upstream_version="6.12.107",
                version_scheme="dotted-v1", package_revision=1, revision_scheme="mojt-r-v1", stability="stable",
                source="local", artifact=body["id"], integrity=dict(descriptor=body["id"]))]))

    def test_invalid_metadata_paths_revisions_and_float_evidence_fail(self):
        self.file("tool")
        for mutate in [lambda v: v.update(kind="ports"), lambda v: v.update(name="../bad"),
                       lambda v: v["version"].update(upstream="01.2"), lambda v: v["version"].update(revision=True),
                       lambda v: v["version"].update(revision=-1), lambda v: v["provenance"].update(number=1.5),
                       lambda v: v["dependencies"].append(dict(provider="native", artifact="unversioned"))]:
            value = spec("port")
            mutate(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.package(value)
        for name in ("../escape", "/outside", "directory/file", "artifact\n.json"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.package(attachments={name: self.source / "tool"})

    def test_no_overwrite_or_output_inside_source_and_no_special_file_loss(self):
        self.file("tool")
        output = self.work / "existing"
        output.mkdir()
        marker = output / "keep"
        marker.write_bytes(b"unchanged")
        with self.assertRaises(ValueError):
            artifact.pack(self.source, spec("port"), output)
        self.assertEqual(marker.read_bytes(), b"unchanged")
        with self.assertRaises(ValueError):
            artifact.pack(self.source, spec("port"), self.source / "output")
        os.mkfifo(self.source / "pipe")
        with self.assertRaisesRegex(ValueError, "FIFO"):
            self.package()
        self.assertFalse(list(self.work.glob(".mojt-pack-*")))

    def test_xattrs_are_rejected_instead_of_silently_dropped(self):
        path = self.file("tool")
        try:
            os.setxattr(path, "user.mojt-test", b"evidence")
        except OSError:
            self.skipTest("filesystem lacks user xattrs")
        with self.assertRaisesRegex(ValueError, "xattrs"):
            self.package()

    def test_source_mutation_during_packaging_leaves_no_published_package(self):
        path = self.file("tool")
        writer = artifact._write_tar
        def mutate(*args):
            writer(*args)
            path.write_bytes(b"changed after streaming")
        with mock.patch.object(artifact, "_write_tar", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "changed while packaging"):
                self.package()
        self.assertFalse((self.work / "package-1").exists())
        self.assertFalse(list(self.work.glob(".mojt-pack-*")))

    def corrupt(self, package, mutation):
        output = self.work / ("corrupt-" + str(self.serial) + ".tar.zst")
        self.serial += 1
        with members(package) as original:
            entries = [(member, original.extractfile(member).read() if member.isfile() else None) for member in original]
        entries = mutation(entries)
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:", format=tarfile.PAX_FORMAT) as archive:
            for member, content in entries:
                archive.addfile(member, io.BytesIO(content) if content is not None else None)
        output.write_bytes(compress(stream.getvalue()))
        return output

    def test_verify_rejects_tampered_payload_extra_categories_traversal_and_identity(self):
        self.file("tool", b"original")
        package, _ = self.package()
        def payload(entries):
            member, raw = entries[-1]
            return [*entries[:-1], (member, b"modified")]
        def extra(entries):
            member = tarfile.TarInfo("./kernel/surprise")
            return [*entries, (member, b"")]
        def escape(entries):
            entries[-1][0].name = "./port/../../escape"
            return entries
        for mutate in (payload, extra, escape):
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                artifact.verify(self.corrupt(package, mutate))
        with self.assertRaisesRegex(ValueError, "identity"):
            artifact.verify(package, "sha256:" + "0" * 64)

    def test_verify_rejects_second_tar_after_end_marker_and_truncated_zstd(self):
        self.file("tool")
        package, _ = self.package()
        second = io.BytesIO()
        with tarfile.open(fileobj=second, mode="w:") as archive:
            archive.addfile(tarfile.TarInfo("./kernel/unlisted"), io.BytesIO(b""))
        extra = self.work / "extra-frame.tar.zst"
        extra.write_bytes(package.read_bytes() + compress(second.getvalue()))
        with self.assertRaises(ValueError):
            artifact.verify(extra)
        broken = self.work / "truncated.tar.zst"
        broken.write_bytes(package.read_bytes()[:-5])
        with self.assertRaises((ValueError, tarfile.TarError)):
            artifact.verify(broken)

    def test_symlink_must_not_be_an_ancestor_of_an_inventory_entry(self):
        self.file("tool")
        _, result = self.package()
        body = result["artifact"]
        body["files"] += [dict(path="payload/link", type="symlink", mode=0o777, uid=0, gid=0, target="/tmp"),
                          dict(path="payload/link/escape", type="directory", mode=0o755, uid=0, gid=0)]
        body.pop("id")
        body["id"] = artifact.digest(body)
        with self.assertRaisesRegex(ValueError, "ancestor"):
            artifact.validate_descriptor(body)

    def test_kernel_adapter_preserves_original_build_record_and_detects_changes(self):
        self.kernel()
        build = self.work / "build"
        build.mkdir()
        self.source.rename(build / "root")
        self.source = build / "root"
        rows, _ = artifact.inventory(self.source)
        (build / "debian.config").write_text("seed\n")
        (build / "config.diff").write_text("".join(difflib.unified_diff(["seed\n"], ["payload"],
                                           fromfile="debian.config", tofile="mojt.config")))
        source = dict(url="https://example.invalid/linux.git", tag="v6.12.107", commit="f" * 40)
        record = dict(format="mojt-kernel-input-v1", release="6.12.107-mojt1", architecture="x86_64",
            source=source, plan=dict(version="6.12.107", localversion="-mojt1", source=source),
            files={r["path"][len("payload/"):]: dict(sha256=r["sha256"], mode=r["mode"]) for r in rows if r["type"] == "file"},
            config_sha256=artifact.file_sha(self.source / "boot/config-6.12.107-mojt1"),
            base_config_sha256=artifact.file_sha(build / "debian.config"),
            sample_vermagic="6.12.107-mojt1 SMP", compiler_environment_sha256="a" * 64)
        record["id"] = artifact.digest(record)
        raw = (json.dumps(record, indent=2) + "\n").encode()
        (build / "kernel.json").write_bytes(raw)
        value, attachments = artifact.kernel_input(build, 1)
        package, result = self.package(value, attachments=attachments)
        with members(package) as archive:
            self.assertEqual(archive.extractfile("./kernel/provenance/kernel.json").read(), raw)
        self.assertEqual(result["artifact"]["provenance"]["kernel_build_id"], record["id"])
        self.assertEqual((build / "kernel.json").read_bytes(), raw)
        (build / "debian.config").write_text("changed seed\n")
        with self.assertRaisesRegex(ValueError, "seed config"):
            artifact.kernel_input(build, 1)
        (build / "debian.config").write_text("seed\n")
        saved_diff = (build / "config.diff").read_bytes()
        (build / "config.diff").write_text("incorrect diff")
        with self.assertRaisesRegex(ValueError, "config diff"):
            artifact.kernel_input(build, 1)
        (build / "config.diff").write_bytes(saved_diff)
        self.file("boot/vmlinuz-6.12.107-mojt1", b"tampered")
        with self.assertRaisesRegex(ValueError, "staged files"):
            artifact.kernel_input(build, 1)

    def test_isolated_cli_has_no_provider_code_and_does_not_activate(self):
        self.file("bin/tool")
        tools, binaries = self.work / "tools", self.work / "bin"
        tools.mkdir()
        binaries.mkdir()
        for name in ("mojt-artifact-pack.py", "mojt_artifact.py", "mpm_selection.py"):
            shutil.copyfile(REPO / "tools" / name, tools / name)
        (binaries / "zstd").symlink_to(shutil.which("zstd"))
        recipe = self.work / "spec.json"
        recipe.write_text(json.dumps(spec("port")))
        environment = dict(os.environ, PATH=str(binaries))
        run = subprocess.run([sys.executable, "-I", "-B", str(tools / "mojt-artifact-pack.py"), "pack",
            "--source", str(self.source), "--spec", str(recipe), "--output", str(self.work / "output")],
            env=environment, text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        package = self.work / "output" / result["archive"]["file"]
        self.assertEqual(artifact.verify(package)["kind"], "port")
        self.assertEqual((self.source / "bin/tool").read_bytes(), b"payload")
        self.assertFalse((self.work / "current").exists())


if __name__ == "__main__":
    unittest.main()
