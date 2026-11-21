# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pinned complete delivery, additive provider retention and detached build scope."""
import copy
import hashlib
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import test_system_fast_test as original
from test_mpm_system import REPO,tree
import mpm_system as system
import mpm_base as base
import mpm_system_transition as transition
import mojt_artifact as artifact

spec=importlib.util.spec_from_file_location('kernel_ssh_delivery',REPO/'tools/mojt-kernel-ssh-test.py')
delivery=importlib.util.module_from_spec(spec);spec.loader.exec_module(delivery)


class ResourceTests(unittest.TestCase):
    def test_declining_base_range_changes_neither_policy_nor_kernel(self):
        bridge=mock.Mock();bridge.read.return_value={'artifact':{'id':'new-kernel','version':{'upstream':'6.18.63'}}}
        bridge.snapshot.return_value={'selected':'current'}
        bridge.confirm.side_effect=ValueError('declined')
        inputs={'platform':'x86_64-linux','base':{'artifact':'same-base','release':'0.1.3','kernel_min':'6.1','kernel_max':'6.12.999'}}
        with mock.patch('mpm_boot_selection.current',return_value=({}, {'current':{'record':{}}},None)), \
             mock.patch('mpm_boot_status.description',return_value=inputs):
            with self.assertRaisesRegex(ValueError,'declined'):
                delivery.choose_kernel(bridge,SimpleNamespace(track='linux-kernel-lts'))
        bridge.run.assert_not_called();bridge.save.assert_not_called()

    def test_retained_activation_uses_public_selector_without_rebuilding(self):
        bridge=mock.Mock();bridge.read.return_value={'artifact':{'id':'exact-retained-kernel'}}
        delivery.activate_kernel(bridge,SimpleNamespace(track='linux-kernel-lts'))
        self.assertEqual(bridge.run.call_args.args,('activate-lts','kernel','activate','--artifact','exact-retained-kernel','-y','--json'))

    def test_closed_inventory_contains_ssh_and_both_track_recipes(self):
        for path in ('tools/mojt_sshd.py','tools/mojt-kernel-build.py','manifests/kernel-lts.json','manifests/kernel-stable.json','tools/mbt_runtime.py'):
            self.assertIn(path,delivery.FILES)
        self.assertEqual(hashlib.sha256((REPO/'tools/mojt-system-fast-test.py').read_bytes()).hexdigest(),delivery.DRIVER_SHA256)
        for name,digest in delivery.FILES.items():
            self.assertEqual(len(digest),64);self.assertTrue((REPO/name).is_file(),name)

    def test_build_command_runs_as_an_ordinary_user_and_changes_no_boot_choice(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);runtime=root/'runtime';(runtime/'manifests').mkdir(parents=True)
            plan=json.loads((REPO/'manifests/kernel-lts.json').read_text());(runtime/'manifests/kernel-lts.json').write_text(json.dumps(plan))
            home=root/'home';(home/'mojt-kernel-build').mkdir(parents=True,mode=0o700)
            user=SimpleNamespace(pw_uid=1000,pw_gid=1000,pw_dir=str(home))
            original_stat=Path.stat
            def file_stat(path,*args,**kwargs):
                if path==home/'mojt-kernel-build':return SimpleNamespace(st_uid=1000,st_mode=stat.S_IFDIR|0o700)
                return original_stat(path,*args,**kwargs)
            bridge=mock.Mock();bridge.read.return_value=dict(path='/frozen/debian.config',sha256='a'*64)
            before=dict(selected='old');bridge.snapshot.return_value=before
            args=SimpleNamespace(user='mojtbuild',track='linux-kernel-lts',jobs=2,resume=False)
            with mock.patch.object(delivery,'RUNTIME',runtime),mock.patch.object(delivery,'checked_state',return_value={}), \
                 mock.patch.object(delivery,'running_system',return_value=before),mock.patch.object(delivery,'tools_match'), \
                 mock.patch.object(delivery,'build_user',return_value=user),mock.patch.object(Path,'is_file',return_value=True),mock.patch.object(Path,'stat',new=file_stat), \
                 mock.patch.object(delivery.subprocess,'run') as run:
                delivery.build(bridge,args)
            command=run.call_args.args[0]
            self.assertIn('--uid',command);self.assertEqual(command[command.index('--uid')+1],str(user.pw_uid))
            self.assertIn('build',command);self.assertIn('--track',command);self.assertIn('linux-kernel-lts',command)
            self.assertNotIn('--wait',command);bridge.unchanged.assert_called_once_with(before,before)


@unittest.skipUnless(os.geteuid()==0 and original.shutil.which('zstd'),'numeric-root native packaging requires zstd')
class PackageTests(unittest.TestCase):
    def test_incomplete_preparation_retry_retains_files_and_refuses_a_completed_checkpoint(self):
        work=self.f.work/'preparation'
        with mock.patch.object(delivery,'WORK',work):
            delivery.start_preparation(False)
            (work/'downloaded-input').write_bytes(b'retain evidence')
            with self.assertRaisesRegex(ValueError,'test evidence exists'):
                delivery.start_preparation(False)
            delivery.start_preparation(True)
            previous=list(work.parent.glob('preparation.failed-prepare-*'))
            self.assertEqual(len(previous),1)
            self.assertEqual((previous[0]/'downloaded-input').read_bytes(),b'retain evidence')
            self.assertEqual(list(work.iterdir()),[])
            (work/'state.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'checkpoint exists'):
                delivery.start_preparation(True)
            self.assertTrue((work/'state.json').is_file())

    def test_main_prepare_creates_real_package_and_checkpoint_without_installing(self):
        f=self.f;work=f.work/'preparation';before=tree(f.root)
        baseline={'selected':'original-boot','status':{'running':{'artifact':f.body['id'],'deployment':'original-boot'}}}
        bridge=mock.Mock(write_data=self.bridge.write_data,specification=self.bridge.specification)
        bridge.snapshot.return_value=baseline
        bridge.save.side_effect=lambda name,value:(work/name).write_text(json.dumps(value))
        def download(command,**unused):
            Path(command[command.index('--output')+1]).write_bytes(b'fixture package driver')
        with mock.patch.object(delivery,'ROOT',f.root),mock.patch.object(delivery,'RUNTIME',self.runtime), \
             mock.patch.object(delivery,'WORK',work),mock.patch.object(delivery,'driver',return_value=bridge), \
             mock.patch.object(delivery,'fetch',return_value=(self.data,f.work/'code',{})), \
             mock.patch.object(delivery,'plain',return_value={'candidate':{'artifact':f.body['id']},'probe':{'artifact':f.body['id']}}), \
             mock.patch.object(delivery,'acquire_ssh',return_value=self.extra), \
             mock.patch.object(delivery.subprocess,'run',side_effect=download), \
             mock.patch.object(delivery.os.path,'ismount',return_value=True), \
             mock.patch.object(delivery.sys,'executable',str(self.runtime/'bin/python3')), \
             mock.patch.object(delivery.sys,'flags',SimpleNamespace(**({k:getattr(sys.flags,k) for k in dir(sys.flags) if not k.startswith('_')}|{'isolated':1}))), \
             mock.patch.object(delivery.sys,'dont_write_bytecode',True), \
             mock.patch.object(delivery.sys,'path',list(sys.path)),mock.patch.dict(os.environ):
            mask=os.umask(0o077)
            try:self.assertEqual(delivery.main(['prepare']),0)
            finally:os.umask(mask)
        saved=json.loads((work/'state.json').read_text())
        self.assertEqual(saved['baseline'],baseline)
        self.assertEqual(saved['candidate']['label'],'system-build-K')
        artifact.verify(work/'candidate'/saved['candidate']['generation'],expected_id=saved['candidate']['artifact'])
        self.assertEqual(before,tree(f.root));bridge.run.assert_not_called()

    def test_compiler_inputs_are_readable_without_modifying_store_targets(self):
        with tempfile.TemporaryDirectory() as t:
            env=Path(t)/'environment';env.mkdir(mode=0o700)
            record=env/'environment.json';record.write_text('{}');record.chmod(0o600)
            run=env/'run';run.write_text('launcher');run.chmod(0o700)
            target=Path(t)/'store-file';target.write_text('retained');target.chmod(0o600)
            (env/'linked').symlink_to(target)
            delivery.share_environment(env)
            self.assertEqual(env.stat().st_mode&0o777,0o755)
            self.assertEqual(record.stat().st_mode&0o777,0o444)
            self.assertEqual(run.stat().st_mode&0o777,0o555)
            self.assertEqual(target.stat().st_mode&0o777,0o600)

    def setUp(self):
        self.f=original.DeliveryTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.runtime=self.f.work/'runtime';(self.runtime/'bin').mkdir(parents=True)
        for name in ('systemd-run','systemctl','python3'):
            p=self.runtime/'bin'/name;p.write_text('retained fixture');p.chmod(0o555)
        self.ssh=self.f.work/'openssh';(self.ssh/'bin').mkdir(parents=True)
        for name in ('sshd','ssh-keygen'):
            p=self.ssh/'bin'/name;p.write_text('SSH provider fixture');p.chmod(0o555)
        patch=mock.patch.object(original.Provider,'contains',lambda adapter,ref,path:str(path).startswith(str(self.ssh)+'/') or str(path).startswith(str(self.runtime)+'/'),create=True)
        patch.start();self.addCleanup(patch.stop)
        self.bridge=SimpleNamespace(write_data=original.delivery.write_data,specification=original.delivery.specification)
        import mbt_runtime
        self.data={name:(REPO/name).read_bytes() for name in set(delivery.FILES)|set(mbt_runtime.resources(REPO))}
        patch=mock.patch.object(delivery,'FILES',{name:hashlib.sha256(data).hexdigest() for name,data in self.data.items()})
        patch.start();self.addCleanup(patch.stop)
        self.extra=dict(provider='fixture',identity=dict(output=str(self.ssh),closure='added SSH binaries'))

    def test_fresh_tooling_generation_retains_baseline_and_adds_closed_ssh_provider(self):
        f=self.f;before=tree(f.root)
        with mock.patch.object(delivery,'RUNTIME',self.runtime):
            row=delivery.package(self.bridge,f.root,f.body['id'],self.data,f.work/'K',self.extra)
        self.assertEqual(before,tree(f.root));kit=f.work/'K';component=artifact.verify(kit/row['component'])
        old_refs=system.object_record(f.root,f.reference['artifact'])[0]['dependencies']
        self.assertEqual(component['dependencies'],[*old_refs,self.extra])
        system.install(f.root,kit/row['generation'],row['artifact'],dependency_files=[kit/row['component']],adapters=f.adapters,yes=True)
        profile=system.realization_path(f.root,row['artifact'])/'profile'
        previous=system.realization_path(f.root,f.body['id'])/'profile'
        review=transition.tooling_review(base.read(previous/'manifest.json'),base.read(profile/'manifest.json'))
        self.assertTrue(review['description']['compatible'],review['description']['blockers'])
        for name in ('sshd','ssh-keygen','systemd-run'):self.assertTrue((profile/'bin'/name).is_symlink())
        self.assertIn('mojt_sshd.py',(profile/'bin/mojt-sshd').read_text())
        self.assertFalse((profile/'units/mojt-sshd.service').exists());self.assertFalse((f.root/'state/etc/ssh').exists())
        for name,digest in delivery.FILES.items():self.assertEqual(hashlib.sha256((profile/name).read_bytes()).hexdigest(),digest)
        self.assertFalse((f.root/'boot').exists());self.assertFalse(f.marker.exists())


if __name__=='__main__':unittest.main()
