# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Small joined MBT checks; no repeated compiler, VM or provider matrix."""
import contextlib
import hashlib
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

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
import mbt_cli as mbt


class FrontendTests(unittest.TestCase):
    def test_help_unknown_commands_and_root_build_never_load_tools(self):
        with mock.patch.object(mbt,'helper',side_effect=AssertionError('helper loaded')):
            for args in ([],['--help'],['build','--help']):
                with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(mbt.main(args),0)
            with contextlib.redirect_stderr(io.StringIO()):
                for args in (['plan'],['unknown'],['build','other']):self.assertEqual(mbt.main(args),1)
                with mock.patch.object(mbt.os,'geteuid',return_value=0):
                    self.assertEqual(mbt.main(['build','kernel','--output','/absent']),1)

    def test_real_kernel_preview_creates_no_workspace_and_checks_frozen_config(self):
        kernel=mbt.helper('kernel')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);environment=root/'env';(environment/'bin').mkdir(parents=True)
            for name in kernel.REQUIRED_COMMANDS:
                p=environment/'bin'/name;p.write_text('synthetic tool; preview must not execute it');p.chmod(0o755)
            (environment/'environment.json').write_text(json.dumps(dict(format='mojt-build-env-v1',profile='kernel',probes={'compiler':{}})))
            config=root/'config';config.write_text('CONFIG_X86_64=y\n')
            output=root/'new-workspace'
            command=[sys.executable,'-I','-B',str(REPO/'tools/mbt'),'build','kernel',
                '--plan',str(REPO/'manifests/kernel-first-build.json'),'--config',str(config),
                '--config-sha256',hashlib.sha256(config.read_bytes()).hexdigest(),
                '--environment',str(environment),'--output',str(output),'--dry-run']
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('Preview only',result.stdout)
            self.assertFalse(output.exists())
            command[command.index('--config-sha256')+1]='0'*64
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('hash differs',result.stderr)
            self.assertFalse(output.exists())

    def test_each_helper_has_scoped_help_without_loading_a_provider(self):
        for args,usage in ((['env','--help'],'mbt env'),(['bootstrap','--help'],'mbt bootstrap'),(['build','kernel','--help'],'mbt build kernel'),
                           (['package','--help'],'mbt package')):
            with self.subTest(args=args):
                result=subprocess.run([sys.executable,'-I','-B',str(REPO/'tools/mbt'),*args],capture_output=True,text=True,
                                      env={'PATH':'/absent','PYTHONPATH':'/untrusted'})
                self.assertEqual(result.returncode,0,result.stderr);self.assertIn('usage: '+usage,result.stdout)


class BuilderDeliveryTests(unittest.TestCase):
    def test_optional_system_delivery_is_complete_and_packages_without_a_checkout(self):
        import test_system_vm as fixtures
        fixture=fixtures.SystemVmTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        model=fixtures.system;record=fixture.fixture(10)
        successor=fixture.root/'successor';shutil.copytree(fixture.tree,successor,symlinks=True)
        with mock.patch.object(model.os,'chown'):
            key=model.install(fixture.tree,fixture.payload,record,fixture.busybox,'password',REPO,with_build_tools=True)
        profile=fixture.tree/'system'/key;self.assertTrue(key.endswith('-builder'))
        wrapper=(profile/'bin/mbt').read_text()
        self.assertIn(' -I -B /run/mojt-system/tools/mbt',wrapper)
        self.assertNotIn('/var/lib/mojt/ports',wrapper)
        runtime=json.loads((profile/'mbt-runtime.json').read_text())
        self.assertEqual(runtime['files'],list(model.MBT_FILES))
        self.assertEqual(runtime['source_files'],list(model.MBT_SOURCE_FILES))
        for name in model.MBT_FILES:self.assertEqual((profile/'tools'/name).read_bytes(),(REPO/'tools'/name).read_bytes())
        for name in model.MBT_SOURCE_FILES:self.assertEqual((profile/name).read_bytes(),(REPO/name).read_bytes())
        # Consume the installed builder's code and fixed assembly assets, not the
        # original repository. The successor must be able to do the same again.
        installed_model=fixtures.module('installed_builder',str(profile/'tools/mojt_system.py'))
        with mock.patch.object(installed_model.os,'chown'):
            following=installed_model.install(successor,fixture.payload,record,fixture.busybox,'password',profile,with_build_tools=True)
        for name in (*model.MBT_SOURCE_FILES,*(str(Path('tools')/name) for name in model.MBT_FILES)):
            self.assertEqual((successor/'system'/following/name).read_bytes(),(profile/name).read_bytes())
        self.assertTrue((profile/'share/man/man1/mbt.1').is_file())
        self.assertTrue((profile/'share/mbt/kernel-first-build.json').is_file())
        installed=[sys.executable,'-I','-B',str(profile/'tools/mbt')]
        result=subprocess.run([*installed,'--help'],cwd=fixture.root,capture_output=True,text=True,env={'PATH':'/absent'})
        self.assertEqual(result.returncode,0,result.stderr)
        if not shutil.which('zstd'):return  # Pure delivery/help remains checked without the archive codec.
        source=fixture.root/'package-input';source.mkdir();(source/'marker').write_text('frozen native payload\n')
        spec=fixture.root/'spec.json';shutil.copyfile(REPO/'manifests/artifact-port-example.json',spec)
        output=fixture.root/'package-output'
        command=[*installed,'package','pack','--source',str(source),'--spec',str(spec),'--output',str(output)]
        packed=subprocess.run(command,cwd=fixture.root,capture_output=True,text=True)
        self.assertEqual(packed.returncode,0,packed.stderr);body=json.loads(packed.stdout)
        archive=output/body['archive']['file']
        verified=subprocess.run([*installed,'package','verify',str(archive),'--expected-id',body['artifact']['id']],
                                cwd=fixture.root,capture_output=True,text=True)
        self.assertEqual(verified.returncode,0,verified.stderr)
        self.assertEqual(json.loads(verified.stdout)['id'],body['artifact']['id'])
        self.assertEqual((source/'marker').read_text(),'frozen native payload\n')

    def test_default_system_has_no_builder_and_low_steps_refuse_before_writes(self):
        import test_system_vm as fixtures
        for enabled in (False,True):
            fixture=fixtures.SystemVmTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
            model=fixtures.system;record=fixture.fixture(1)
            with mock.patch.object(model.os,'chown'):
                if enabled:
                    before=list((fixture.tree/'system').iterdir()) if (fixture.tree/'system').exists() else []
                    with self.assertRaisesRegex(ValueError,'step 3'):
                        model.install(fixture.tree,fixture.payload,record,fixture.busybox,'development',REPO,with_build_tools=True)
                    self.assertEqual(before,list((fixture.tree/'system').iterdir()) if (fixture.tree/'system').exists() else [])
                else:
                    key=model.install(fixture.tree,fixture.payload,record,fixture.busybox,'development',REPO)
                    self.assertFalse((fixture.tree/'system'/key/'bin/mbt').exists())
                    self.assertFalse((fixture.tree/'system'/key/'mbt-runtime.json').exists())


if __name__=='__main__':unittest.main()
