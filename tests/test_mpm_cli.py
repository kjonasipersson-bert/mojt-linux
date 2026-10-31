# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Installed management files, isolated imports and explicit target defaults."""
import contextlib
import dataclasses
import io
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
import mpm_cli as cli


class DispatchTests(unittest.TestCase):
    def test_help_and_unsupported_system_mutations_never_load_a_provider(self):
        with mock.patch.object(cli.runpy, "run_path", side_effect=AssertionError("provider loaded")):
            for args in ([], ["--help"], ["kernel", "--help"]):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(args), 0)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["system", "upgrade"]), 1)

    def test_installed_ports_defaults_preserve_explicit_root_and_source(self):
        runtime = cli.Runtime()
        adapter = mock.Mock(return_value=0)
        with mock.patch.object(cli.runpy, "run_path", return_value={"main": adapter}):
            self.assertEqual(cli.main(["ports", "update", "--dry-run"], runtime=runtime), 0)
            self.assertEqual(adapter.call_args.args[0], ["--root", str(runtime.ports),
                "--source-manifest", str(runtime.source), "ports", "update", "--dry-run"])
            explicit = ["--root=/private", "--source-manifest", "/pin", "ports", "status"]
            self.assertEqual(cli.main(explicit, runtime=runtime), 0)
            self.assertEqual(adapter.call_args.args[0], explicit)

    def test_runtime_does_not_attach_running_record_to_an_explicit_disk(self):
        args = ["status", "--disk-root", "/other", "--baseline", "boot/mojt/other/1"]
        self.assertEqual(cli.boot_options(args, cli.Runtime()), args)

    def test_explicit_registry_status_is_not_reinterpreted_as_running_disk_status(self):
        runtime = dataclasses.replace(cli.Runtime(), running=Path(__file__))
        import mpm_kernel as kernel
        with mock.patch.object(kernel, "main", return_value=0) as run:
            self.assertEqual(cli.main(["kernel", "status", "--root=/private"], runtime=runtime), 0)
            self.assertEqual(run.call_args.args[0], ["status", "--root=/private"])

    def test_runtime_path_ignores_ports_commands_and_restores_callers_environment(self):
        with mock.patch.dict(os.environ, PATH="/hostile/ports/bin", PYTHONPATH="/hostile"):
            with cli.runtime_path(cli.Runtime()):
                self.assertNotIn("/hostile", os.environ["PATH"])
                self.assertTrue(os.environ["PATH"].startswith(str(cli.Runtime().helpers)))
            self.assertEqual(os.environ["PATH"], "/hostile/ports/bin")

    def test_missing_native_codec_fails_before_creating_installation_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = dataclasses.replace(cli.Runtime(), disk=root / "absent", helpers=root / "no-tools")
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                self.assertEqual(cli.main(["kernel", "install", "--from-file", "/absent",
                    "--expected-id", "sha256:" + "0" * 64, "--dry-run"], runtime=runtime), 1)
            self.assertIn("retained zstd", error.getvalue())
            self.assertEqual(list(root.iterdir()), [])

    def test_ordinary_user_mutations_are_refused_before_loading_providers_or_targets(self):
        with mock.patch.object(cli.os, "geteuid", return_value=1000), \
                mock.patch.object(cli.runpy, "run_path", side_effect=AssertionError("provider loaded")):
            for args in (["ports", "install", "hello", "-y"], ["kernel", "install"],
                         ["kernel", "stage"], ["kernel", "select"], ["kernel", "rollback"],
                         ["ports", "metadata"], ["--root=/private", "ports", "upgrade"]):
                with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()) as errors:
                    self.assertEqual(cli.main(args, runtime=cli.Runtime()), 1)
                    self.assertIn("administrator", errors.getvalue())

    def test_ordinary_user_can_inspect_ports_and_an_explicit_native_registry(self):
        import mpm_kernel as kernel
        with mock.patch.object(cli.os, "geteuid", return_value=1000), \
                mock.patch.object(cli.runpy, "run_path", return_value={"main": lambda args: 0}), \
                mock.patch.object(kernel, "main", return_value=0):
            self.assertEqual(cli.main(["ports", "history"], runtime=cli.Runtime()), 0)
            self.assertEqual(cli.main(["--root=/private", "kernel", "status"], runtime=cli.Runtime()), 0)


@unittest.skipUnless(os.geteuid() == 0 and shutil.which("zstd") and shutil.which("cpio"),
                     "requires native package fixture tools and root")
class InstalledNativeTests(unittest.TestCase):
    def setUp(self):
        # Reuse the real archive/installation fixture; no additional VM boots.
        import test_kernel_boot as fixtures
        self.fixture = fixtures.KernelBootTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.profile = self.root / "system/native-fixture"
        self.tools = self.fixture.fixture.work / "installed-tools"
        shutil.copytree(self.profile / "tools", self.tools)
        for name in ("mpm-nix-prototype", "mpm-nix-catalog.py"):
            (self.tools / name).unlink()  # Native commands cannot depend on these.
        helpers = self.fixture.fixture.work / "runtime-helpers"
        helpers.mkdir()
        (helpers / "zstd").symlink_to(shutil.which("zstd"))
        binaries = self.fixture.fixture.work / "runtime-bin"
        binaries.mkdir()
        (binaries / "modprobe").symlink_to(shutil.which("true"))
        self.runtime = cli.Runtime(disk=self.root, ports=self.root / "state/var/lib/mojt/ports",
            running=self.root / self.fixture.baseline / "deployment.json", helpers=helpers,
            source=self.profile / "ports.toml", system_bin=binaries)

    def run_cli(self, args, *, success=True):
        # Execute only the installed copy from /, with no checkout/PYTHONPATH.
        script = """import json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from mpm_cli import main,Runtime
r=Runtime(**{k:Path(v) for k,v in json.loads(sys.argv[2]).items()})
# The test disk is synthetic; the host is not actually running this fixture Kernel.
u=os.uname()
release=json.loads(r.running.read_text())['description']['kernel']['release']
os.uname=lambda: os.uname_result((u.sysname,u.nodename,release,u.version,u.machine))
args=sys.argv[3:]
if args[:1]==['--fixture-stage']:
    args=args[1:]
    import mpm_kernel_boot as manager
    vm=manager.vm_module()
    # Same synthetic executable/module substitutions as the existing boot fixture.
    vm.static_x86_64_elf=lambda path: True
    vm.validate_busybox_applets=lambda *a,**kw: None
    vm.module_paths=lambda release,p,**kw: [p/'kernel/example.ko']
    vm.os.mknod=lambda path,*a: path.touch()
    manager.vm_module=lambda: vm
sys.exit(main(args,runtime=r))
"""
        runtime = json.dumps({k: str(v) for k, v in dataclasses.asdict(self.runtime).items()})
        result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(self.tools), runtime, *args],
            cwd="/", env=dict(os.environ, PATH="", PYTHONPATH="/invalid"), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0 if success else 1, result.stderr + result.stdout)
        return json.loads(result.stdout) if success else result.stderr

    def test_installed_launcher_help_has_no_provider_or_checkout_dependency(self):
        result = subprocess.run([sys.executable, "-I", "-B", str(self.tools / "mpm-system"), "--help"],
            cwd="/", env=dict(os.environ, PATH=""), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("catalog", result.stdout)
        self.assertIn("Kernel selection changes next boot", result.stdout)

    def test_installed_catalog_reads_explicit_snapshot_without_provider_files(self):
        catalog = self.fixture.fixture.work / "catalog.json"
        shutil.copyfile(REPO / "manifests/mpm-discovery-example.json", catalog)
        before = self.fixture.snapshot()
        result = self.run_cli(["ports", "search", "neovim", "--catalog", str(catalog), "--json"])
        self.assertIn("neovim", json.dumps(result))
        self.assertEqual(before, self.fixture.snapshot())

    def test_installed_ports_resolve_is_provider_independent(self):
        catalog = self.fixture.fixture.work / "releases.json"
        shutil.copyfile(REPO / "manifests/mpm-release-example.json", catalog)
        before = self.fixture.snapshot()
        result = self.run_cli(["ports", "resolve", "paint@3.0", "--catalog", str(catalog), "--json"])
        self.assertEqual(result["candidate"]["release_id"], "3.0.10")
        self.assertEqual(before, self.fixture.snapshot())

    def test_installed_ports_status_uses_the_existing_state_root_and_real_adapter(self):
        shutil.copyfile(self.profile / "tools/mpm-nix-prototype", self.tools / "mpm-nix-prototype")
        before = self.fixture.snapshot()
        result = self.run_cli(["ports", "status"])
        self.assertEqual(result["installed"], {})
        self.assertEqual(before, self.fixture.snapshot())

    def test_installed_native_status_and_stage_preview_are_read_only(self):
        before = self.fixture.snapshot()
        status = self.run_cli(["kernel", "status", "--json"])
        self.assertEqual(status["selected"], self.fixture.old_id)
        self.assertEqual(status["running"]["deployment"], self.fixture.old_id)
        preview = self.run_cli(["kernel", "stage", "--artifact", self.fixture.candidate["id"], "--dry-run"])
        self.assertFalse(preview["changed"])
        self.assertEqual(before, self.fixture.snapshot())

    def test_installed_native_install_targets_disk_registry_without_selecting(self):
        import mpm_kernel as kernel
        import mojt_artifact as artifact
        package = self.fixture.fixture.work / "candidate-package"
        archive = next(package.glob("*.tar.zst"))
        before = artifact.file_sha(archive)
        kernel.clean_stage(self.root / "kernel/installed" / kernel.identifier(self.fixture.candidate["id"]))
        result = self.run_cli(["kernel", "install", "--from-file", str(archive),
            "--expected-id", self.fixture.candidate["id"], "-y"])
        self.assertTrue(result["changed"])
        self.assertEqual(result["plan"]["root"], str(self.root / "kernel"))
        self.assertEqual((self.root / "boot/mojt/grub.cfg").read_bytes(), self.fixture.menu)
        self.assertEqual(artifact.file_sha(archive), before)

    def test_installed_stage_builds_from_delivered_modules_and_repeat_is_noop(self):
        args = ["--fixture-stage", "kernel", "stage", "--artifact", self.fixture.candidate["id"], "-y"]
        staged = self.run_cli(args)
        self.assertTrue(staged["changed"])
        self.assertTrue((self.root / staged["slot"] / "initramfs.cpio.gz").is_file())
        self.assertEqual((self.root / "boot/mojt/grub.cfg").read_bytes(), self.fixture.menu)
        repeated = self.run_cli(args)
        self.assertFalse(repeated["changed"])
        self.assertEqual(repeated["deployment"], staged["deployment"])

    def test_installed_select_preserves_explicit_running_identity(self):
        staged = self.fixture.stage()
        result = self.run_cli(["kernel", "select", "--deployment", staged["deployment"],
            "--expected-selected", self.fixture.old_id, "-y"])
        self.assertTrue(result["changed"])
        status = self.run_cli(["kernel", "status", "--json"])
        self.assertEqual(status["selected"], staged["deployment"])
        self.assertEqual(status["running"]["deployment"], self.fixture.old_id)
        self.assertFalse(status["running_is_selected"])


if __name__ == "__main__":
    unittest.main()
