# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Combined profiler/package delivery; real native content, simulated live context."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import os
import json
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from test_mpm_system import REPO
import mbt_runtime
import mpm_cli
import mpm_boot_update
import mpm_boot_selection
import mpm_system as system
import mpm_base as base
import mpm_system_transition as transition
import test_system_firmware as firmware

spec=importlib.util.spec_from_file_location('install_profile_test',REPO/'tools/mojt-system-install-profile.py')
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)


@unittest.skipUnless(os.geteuid()==0,'requires protected root-owned execution resources')
class FreezeTests(unittest.TestCase):
    def test_two_samples_are_distinct_operations_and_failure_stops_the_run(self):
        with mock.patch.object(driver.os.path,'ismount',return_value=True),             mock.patch.object(driver,'sample',side_effect=[0,0]) as sample:
            self.assertEqual(driver.main(['--samples','2']),0)
            self.assertEqual(sample.call_count,2)
        with mock.patch.object(driver.os.path,'ismount',return_value=True),             mock.patch.object(driver,'sample',return_value=1) as sample:
            self.assertEqual(driver.main(['--samples','2']),1)
            sample.assert_called_once()

    def test_one_command_freezes_its_cohort_and_support_then_uses_retained_python_and_disk_tmp(self):
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)/'diagnostic';before=dict(running='sha256:'+'a'*64,selected='sha256:'+'b'*64)
            snapshot=SimpleNamespace(snapshot=lambda:before,mpm=lambda *a:{'running':{'deployment':before['selected']}})
            with mock.patch.object(driver,'WORK',work),mock.patch.object(driver.os.path,'ismount',return_value=True),\
                 mock.patch.object(sys,'path',list(sys.path)),mock.patch.object(driver,'load',return_value=snapshot),\
                 mock.patch.object(driver.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run:
                self.assertEqual(driver.main([]),0)
            evidence=next(work.glob('run-*'));saved=json.loads((evidence/'context.json').read_text())
            self.assertEqual(saved['baseline'],before)
            self.assertEqual(mbt_runtime.verify(Path(saved['code']))['id'],saved['execution']['id'])
            for name,digest in saved['support'].items():self.assertEqual(hashlib.sha256((evidence/name).read_bytes()).hexdigest(),digest)
            self.assertEqual(run.call_args.args[0][0],str(driver.RUNTIME/'bin/python3'))
            self.assertEqual(run.call_args.kwargs['env']['TMPDIR'],str(evidence/'tmp'))
            self.assertEqual(run.call_args.args[0][-2:],['--child',str(evidence)])


@unittest.skipUnless(os.geteuid()==0 and shutil.which('zstd'),'requires root and native archive codec')
class IntegrationTests(firmware.PackageTests):
    def test_combined_driver_keeps_reports_and_never_selects_after_real_packaging_and_import(self):
        run=self.work/'run-driver';run.mkdir(mode=0o700)
        code=Path(tempfile.mkdtemp(prefix=mbt_runtime.PREFIX,dir=run));execution=mbt_runtime.freeze(REPO,code)
        hashes={}
        for name,path in driver.SUPPORT.items():
            data=(REPO/path).read_bytes();(run/name).write_bytes(data);(run/name).chmod(0o444)
            hashes[name]=hashlib.sha256(data).hexdigest()
        before={'running':self.body['id']}
        driver.write(run/'context.json',dict(format=driver.FORMAT,baseline=before,code=str(code),execution=execution,support=hashes))
        snapshot=SimpleNamespace(unchanged=mock.Mock())
        original_load=driver.load
        def load(name,path):return snapshot if name=='snapshot' else original_load(name,path)
        runtime=mpm_cli.Runtime(disk=self.root,helpers=Path(shutil.which('zstd')).parent)
        with mock.patch.object(driver,'ROOT',self.root),mock.patch.object(driver,'load',side_effect=load),\
             mock.patch.object(sys,'path',list(sys.path)),mock.patch.object(mpm_cli,'Runtime',return_value=runtime),\
             mock.patch.object(mpm_boot_selection,'present',return_value=True),mock.patch.object(os.path,'ismount',return_value=True),\
             mock.patch.object(mpm_boot_update,'stage',return_value=dict(changed=True,deployment='fixture-slot',initramfs_payload={'reused':True})),\
             contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(driver.child(run),0)
        self.assertEqual(snapshot.unchanged.call_count,3)
        report=json.loads((run/'profile.json').read_text())
        self.assertTrue(report['result']['content_changed'] and report['result']['prepared'])
        self.assertFalse(report['result']['selection_changed'])
        self.assertTrue((run/'summary.txt').is_file());self.assertFalse(self.marker.exists())

    def test_reviewed_resource_cohort_packages_unchanged_firmware_and_uses_public_install(self):
        packager=driver.load('test_package',REPO/'tools/mojt_system_tooling.py')
        profiler=driver.load('test_profile',REPO/'tools/mojt-stage-profile.py')
        data={n:(REPO/n).read_bytes() for n in mbt_runtime.resources(REPO)}
        hashes={n:hashlib.sha256(v).hexdigest() for n,v in data.items()}
        candidate=packager.package(self.root,self.body['id'],data,self.work/'measured-package',
            label='system-install-measured',expected_files=hashes,source_revision='reviewed-fixture')
        run=self.work/'measure';run.mkdir(mode=0o700)
        runtime=mpm_cli.Runtime(disk=self.root,helpers=Path(shutil.which('zstd')).parent)
        command=['system','install','--from-file',str(self.work/'measured-package'/candidate['generation']),
            '--dependency-file',str(self.work/'measured-package'/candidate['component']),'--expected-id',candidate['artifact'],'-y','--json']
        with mock.patch.object(mpm_cli,'Runtime',return_value=runtime),\
             mock.patch.object(mpm_boot_selection,'present',return_value=True),\
             mock.patch.object(os.path,'ismount',return_value=True),\
             mock.patch.object(mpm_boot_update,'stage',return_value=dict(changed=True,deployment='fixture-slot',
                 initramfs_payload={'reused':True})) as stage,contextlib.redirect_stderr(io.StringIO()):
            report=driver.measure(REPO/'tools',command,profiler,run)
        self.assertEqual(report['returncode'],0);self.assertTrue(report['result']['changed'])
        self.assertTrue(report['result']['prepared']);self.assertTrue(report['result']['content_changed'])
        self.assertFalse(report['result']['selection_changed'])
        self.assertEqual(stage.call_args.args,(self.root,'system',candidate['artifact']))
        self.assertIs(stage.call_args.kwargs['verify'],False)
        self.assertGreater(report['total']['wall_ns'],0)
        self.assertEqual(report['io']['mpm_system._retain'].get('copy_calls',0),0)
        self.assertEqual(report['io']['mpm_system._retain']['renames'],2)
        self.assertEqual(report['io']['mpm_system.copy_profile']['renames'],1)
        self.assertEqual(report['io']['mpm_system.copy_profile'].get('file_fsync',0),0)
        old=system.realization_path(self.root,self.body['id'])/'profile'
        new=system.realization_path(self.root,candidate['artifact'])/'profile'
        self.assertEqual(transition.firmware_inventory(base.read(old/'manifest.json')['description']['profile']),
                         transition.firmware_inventory(base.read(new/'manifest.json')['description']['profile']))
        system.realization(self.root,candidate['artifact'],verify=True)
        self.assertFalse(self.marker.exists())

    def test_failed_public_install_keeps_its_result_and_does_not_select(self):
        profiler=driver.load('failure_profile',REPO/'tools/mojt-stage-profile.py')
        run=self.work/'failed-measure';run.mkdir(mode=0o700)
        runtime=mpm_cli.Runtime(disk=self.root,helpers=Path(shutil.which('zstd')).parent)
        command=['system','install','--disk-root',str(self.root),'--from-file','/missing/archive',
            '--expected-id','sha256:'+'f'*64,'-y','--json']
        before=copy.deepcopy(system.status(self.root))
        with mock.patch.object(mpm_cli,'Runtime',return_value=runtime),contextlib.redirect_stderr(io.StringIO()):
            report=driver.measure(REPO/'tools',command,profiler,run)
        self.assertEqual(report['returncode'],1);self.assertIsNone(report['result'])
        self.assertEqual(system.status(self.root),before)
        self.assertTrue((run/'phases.log').is_file())


if __name__=='__main__':unittest.main()
