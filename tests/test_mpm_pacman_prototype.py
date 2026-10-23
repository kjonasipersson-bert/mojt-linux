#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pacman environment orchestration tests; package manager/namespaces simulated."""

import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("mpm_pacman", str(REPO / "tools/mpm-pacman-prototype"))
spec = importlib.util.spec_from_loader(loader.name, loader)
mpm = importlib.util.module_from_spec(spec)
loader.exec_module(mpm)


class PacmanEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mojt-pacman-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "private lab"
        self.calls = []
        self.bad_archive = False
        self.wrong_versions = False
        self.patch("build_run", self.backend)
        self.patch_os_uid = mock.patch.object(mpm.os, "geteuid", return_value=1000)
        self.patch_os_uid.start()
        self.addCleanup(self.patch_os_uid.stop)

    def patch(self, name, value):
        patcher = mock.patch.object(mpm, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def records(self, config):
        newer = "2025/06/01" in Path(config).read_text()
        packages = []
        for name in ("filesystem", "bash", "coreutils", "python", "curl", "ca-certificates"):
            version = ("3.13.1-1" if newer else "3.12.1-1") if name == "python" else "1.0-1"
            content = (name + version).encode()
            packages.append(dict(name=name, version=version, sha256=hashlib.sha256(content).hexdigest(),
                                 file=name + "-" + version + ".pkg.tar.zst", size=len(content)))
        return packages

    def backend(self, root, command, guest=None, capture=False):
        self.assertEqual(root, self.root)
        self.calls.append(command)
        if command[0] == "/usr/bin/pacman-key":
            self.assertIn("--gpgdir", command)
            return ""
        self.assertEqual(command[0], "/usr/bin/pacman")
        config = Path(command[command.index("--config") + 1])
        db = Path(command[command.index("--dbpath") + 1])
        cache = Path(command[command.index("--cachedir") + 1])
        self.assertTrue(config.is_relative_to(root))
        self.assertTrue(db.is_relative_to(root))
        self.assertTrue(cache.is_relative_to(root / "cache"))
        self.assertIn("SigLevel = Required DatabaseOptional", config.read_text())
        self.assertNotIn("Never", config.read_text())
        if "-Sy" in command:
            (db / "sync").mkdir()
            for repo in ("core", "extra"):
                (db / "sync" / (repo + ".db")).write_text(repo + config.read_text())
            return ""
        records = self.records(config)
        if "-Sp" in command:
            return "\n".join("\t".join(str(p[k]) for k in ("name", "version", "sha256", "file", "size"))
                             for p in records)
        if "-S" in command:
            self.assertIsNotNone(guest)
            self.assertNotIn("--noscriptlet", command)
            (guest / "usr/bin").mkdir(parents=True)
            for name in ("python", "curl"):
                path = guest / "usr/bin" / name
                path.write_text("#!/bin/sh\nprintf '%s\\n' 'synthetic runtime'\n")
                path.chmod(0o755)
            for p in records:
                content = (p["name"] + p["version"]).encode()
                (cache / p["file"]).write_bytes(b"bad" if self.bad_archive else content)
            return ""
        if "-Q" in command:
            return "\n".join(p["name"] + " " + ("bad" if self.wrong_versions else p["version"])
                             for p in records)
        self.fail(f"unexpected pacman operation: {command}")

    def cli(self, *args, success=True, answer="y"):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output), \
                mock.patch("builtins.input", return_value=answer):
            code = mpm.main(["--root", str(self.root), "ports", *args])
        self.assertEqual(code, 0 if success else 1, output.getvalue())
        return output.getvalue()

    def update(self, letter="a"):
        return self.cli("update", "--manifest", str(REPO / f"manifests/mpm-pacman-{letter}.toml"), "-y")

    def state(self):
        return json.loads(self.cli("status"))

    def test_update_only_resolves_and_retains_metadata(self):
        self.update()
        state = self.state()
        self.assertEqual(state["installed"], {})
        self.assertEqual(state["active"], {})
        self.assertEqual(len(state["catalog"]["resolved"]), 6)
        self.assertFalse(any("-S" in c for c in self.calls))
        self.assertEqual(list((self.root / "environments").iterdir()), [])

    def test_install_uses_saved_catalog_without_refresh(self):
        self.update()
        self.calls.clear()
        self.cli("install", "-y")
        self.assertFalse(any("-Sy" in c or "-Sp" in c for c in self.calls))
        self.assertEqual(len(self.state()["installed"]), 1)

    def test_parallel_snapshots_keep_default_and_old_profile(self):
        self.update()
        self.cli("install", "-y")
        first = self.state()
        old_profile = (self.root / "current").resolve()
        old_launcher = (old_profile / "bin/python3").read_bytes()
        first_key = first["active"]["cli"]
        old_record_bytes = (self.root / "environments" / first_key / "record.json").read_bytes()
        first_cache = self.root / "cache" / first["catalog"]["catalog_id"]
        old_archives = {p.name: p.read_bytes() for p in first_cache.iterdir()}
        self.update("b")
        self.assertEqual(self.state()["installed"], first["installed"])
        self.cli("install", "-y")
        second = self.state()
        self.assertEqual(len(second["installed"]), 2)
        self.assertEqual(second["active"], first["active"])
        second_key = next(k for k in second["installed"] if k != first_key)
        self.calls.clear()
        self.cli("activate", second_key, "-y")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.state()["active"]["cli"], second_key)
        self.assertEqual((old_profile / "bin/python3").read_bytes(), old_launcher)
        self.assertEqual((self.root / "environments" / first_key / "record.json").read_bytes(), old_record_bytes)
        self.assertEqual({p.name: p.read_bytes() for p in first_cache.iterdir()}, old_archives)
        self.assertIn(first_key, (self.root / "current/bin" / ("python3-env-" + first_key)).read_text())

    def test_idempotence_does_not_reinstall_or_publish(self):
        self.update()
        self.cli("install", "-y")
        before = os.readlink(self.root / "current")
        self.calls.clear()
        self.assertIn("No changes.", self.cli("install", "-y"))
        self.assertEqual(os.readlink(self.root / "current"), before)
        self.assertEqual(self.calls, [])

    def test_previews_and_cancel_do_not_publish_or_download(self):
        self.cli("update", "--manifest", str(REPO / "manifests/mpm-pacman-a.toml"), "--dry-run")
        self.assertFalse(self.root.exists())
        self.cli("update", "--manifest", str(REPO / "manifests/mpm-pacman-a.toml"), answer="n")
        self.assertEqual(self.calls, [])
        self.assertFalse(os.path.lexists(self.root / "current"))
        self.update()
        before = os.readlink(self.root / "current")
        self.calls.clear()
        self.cli("install", "--dry-run")
        self.assertEqual(self.calls, [])
        self.assertEqual(os.readlink(self.root / "current"), before)

    def test_missing_activation_never_installs(self):
        self.update()
        self.calls.clear()
        self.cli("activate", "unknown", "-y", success=False)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.state()["installed"], {})

    def test_modified_sync_database_blocks_install_even_in_preview(self):
        self.update()
        record = self.state()["catalog"]
        directory = self.root / "catalogs" / record["catalog_id"]
        (directory / "db/sync/core.db").write_text("changed")
        before = os.readlink(self.root / "current")
        self.cli("install", "--dry-run", success=False)
        self.assertEqual(os.readlink(self.root / "current"), before)

    def test_bad_package_digest_never_publishes_environment(self):
        self.update()
        before = os.readlink(self.root / "current")
        self.bad_archive = True
        self.cli("install", "-y", success=False)
        self.assertEqual(os.readlink(self.root / "current"), before)
        self.assertEqual(self.state()["installed"], {})
        self.assertTrue(all(p.name.startswith(".stage-") for p in (self.root / "environments").iterdir()))

    def test_installed_versions_must_match_plan(self):
        self.update()
        self.wrong_versions = True
        self.cli("install", "-y", success=False)
        self.assertEqual(self.state()["installed"], {})

    def test_publish_failure_preserves_profile_and_candidate_is_reused(self):
        self.update()
        before = os.readlink(self.root / "current")
        with mock.patch.object(mpm.os, "replace", side_effect=OSError("injected failure")):
            self.cli("install", "-y", success=False)
        self.assertEqual(os.readlink(self.root / "current"), before)
        self.calls.clear()
        self.cli("install", "-y")
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.state()["installed"]), 1)

    def test_unmanaged_files_and_modified_launchers_are_preserved(self):
        self.root.mkdir()
        local = self.root / "local-file"
        local.write_text("keep")
        self.cli("install", "-y", success=False)
        self.assertEqual(local.read_text(), "keep")
        local.unlink()
        self.update()
        self.cli("install", "-y")
        path = self.root / "current/bin/curl"
        path.chmod(0o755)
        path.write_text("local command")
        self.cli("install", "-y", success=False)
        self.assertEqual(path.read_text(), "local command")

    def test_builder_caps_and_writable_bind_are_scoped_to_lab(self):
        guest = self.root / "environments/.stage-test/rootfs"
        args = mpm.builder_arguments(self.root, ["/usr/bin/pacman", "-S", "python"], guest)
        binds = [args[i+1:i+3] for i, arg in enumerate(args) if arg == "--bind"]
        self.assertEqual(binds, [[str(self.root), str(self.root)]])
        self.assertIn("--unshare-user", args)
        self.assertIn("CAP_SYS_CHROOT", args)
        self.assertNotIn("CAP_SYS_ADMIN", args)
        self.assertIn(str(guest / "dev"), args)
        self.assertNotIn("--unshare-net", args)

    def test_runtime_selects_guest_root_and_workdir_without_host_usr(self):
        work = Path(self.tmp.name)
        guest = self.root / "environments/test/rootfs"
        args = mpm.runtime_arguments(guest, "/usr/bin/python", ["-I", "-c", "print(1)"], work)
        ro_binds = [args[i+1:i+3] for i, arg in enumerate(args) if arg == "--ro-bind"]
        self.assertIn([str(guest), "/"], ro_binds)
        self.assertNotIn(["/usr", "/usr"], ro_binds)
        self.assertIn("/work", args)
        self.assertIn("--cap-drop", args)
        self.assertNotIn("--cap-add", args)

    def test_failed_metadata_download_leaves_current_unchanged(self):
        self.update()
        before = os.readlink(self.root / "current")
        with mock.patch.object(mpm, "build_run", side_effect=subprocess.CalledProcessError(1, "pacman")):
            self.update_failed()
        self.assertEqual(os.readlink(self.root / "current"), before)

    def update_failed(self):
        self.cli("update", "--manifest", str(REPO / "manifests/mpm-pacman-b.toml"), "-y", success=False)

    def test_unsafe_manifests_rejected_before_backend(self):
        source = (REPO / "manifests/mpm-pacman-a.toml").read_text()
        path = Path(self.tmp.name) / "bad.toml"
        for text in (source.replace("2024/06/01", "2024/99/01"),
                     source.replace("/usr/bin/python", "/usr/bin/../bad"),
                     source.replace('"python"', '"python;bad"')):
            with self.subTest(text=text):
                path.write_text(text)
                self.cli("update", "--manifest", str(path), "-y", success=False)
                self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
