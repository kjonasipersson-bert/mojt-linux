# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real retained transactions with a simulated initramfs producer; no boot claim."""
import copy
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

import test_mpm_boot_v2 as fixtures
import test_mpm_boot_payload as payload
import mojt_artifact as artifact
import mpm_base as base
import mpm_boot_constructor as constructor
import mpm_boot_handover as handover
import mpm_boot_selection as selection
import mpm_boot_update as update
import mpm_boot_v2 as model
import mpm_boot_v2_store as store
import mpm_native_io as io
import mpm_system as system
import mpm_transaction as tx


@unittest.skipUnless(os.geteuid()==0 and all(shutil.which(c) for c in ('tar','zstd','cpio')),
                     'requires root and retained archive tools')
class InstallationTransaction(unittest.TestCase):
    def setUp(self):
        f=fixtures.Retention();f.setUp();self.addCleanup(f.doCleanups)
        self.f=f;self.root=f.root;self.work=f.f.f.fixture.work
        adapter=f.f.adapter
        adapter.boot_paths=lambda ref,target:sorted(r['path'].lstrip('/') for r in ref['identity']['objects'])
        adapter.boot_mounts=lambda ref,target:[dict(source='nix',target='nix')]
        self.runtime=payload.runtime();self.bundle=self.work/'transaction-runtime';self.bundle.mkdir()
        io.write_json(self.bundle/'runtime.json',self.runtime)
        self.busybox=self.work/'transaction-busybox';self.busybox.write_bytes(b'simulated BusyBox');self.busybox.chmod(0o755)
        plan=f.f.plan();d=copy.deepcopy(f.source['description']);d['boot']['root_uuid']=plan['description']['root_uuid']
        d['constructor']=constructor.constructor(self.runtime,self.busybox,handover=True)
        source=model.record(model.INPUTS,d)
        contract=handover.prepare(self.root,source,plan,adapters=f.f.adapters)
        built=self.build(self.root,source,None,self.busybox,self.work/'initial-construction',handover=contract)
        item=fixtures.bound(source,built['archive'],f.image.stat().st_size)
        image=self.work/'initial-initramfs';image.write_bytes(built['archive'])
        store.retain(self.root,item,f.image,image,bounds=f.bounds,adapters=f.f.adapters)
        selection._admit(self.root,item,built,adapters=f.f.adapters)
        hook=self.root/'boot/mojt/grub.cfg';hook.chmod(0o644);hook.write_bytes(selection.HOOK);hook.chmod(0o444)
        selection.initialize(self.root,item['id'])
        self.before=(self.root/selection.MENU).read_bytes()
        self.candidate=f.f.candidate()
        self.options=dict(adapters=f.f.adapters,runtime_directory=self.bundle,busybox=self.busybox,yes=True)

    def build(self,root,source,runtime_directory,busybox,work,*,handover,entries=None,**kwargs):
        Path(work).mkdir(parents=True)
        raw=b'simulated initramfs for '+source['id'].encode()
        binding=model.record(model.BINDING,dict(inputs=source['id'],constructor=source['description']['constructor'],
            archive=dict(sha256=hashlib.sha256(raw).hexdigest(),size=len(raw))))
        proof=constructor.capture(root,source,self.f.f.adapters,entries=entries)
        return constructor.CompletedBuild(dict(archive=raw,binding=binding,proof=proof,handover_enabled=True,
            payload_key='sha256:'+'0'*64,payload_reused=True),handover)

    def test_component_generation_prepares_and_returns_to_legacy_without_changing_state(self):
        import mojt_system_package as package
        candidate=package.package_installed(self.root,self.candidate,self.work/'thin',label='thin-runtime',firmware='keep')
        system.install(self.root,self.work/'thin'/candidate['generation'],candidate['artifact'],
            dependency_files=[self.work/'thin'/p for p in candidate['dependency_files']],yes=True,adapters=self.f.f.adapters)
        with mock.patch.object(constructor,'_build_locked',side_effect=self.build):
            result=update.stage(self.root,'system',candidate['artifact'],**self.options)
        admitted=selection.ready(self.root,result['deployment'],verify=True)
        source=admitted['record']['description']['inputs'];proof=admitted['receipt']['description']['proof']
        context=handover.check(self.root,source,proof,admitted['receipt']['description']['handover'],verify_content=False)
        self.assertEqual(len(context['components']),1)
        start=handover.guest_file(self.root,context['tree'],context['profile'],context['provider_roots'],context['mounts'],
            '/run/mojt-system/start',components=context['components'])
        self.assertTrue(start.is_file());self.assertIn('/artifacts/system/installed/',str(start))
        old=selection.current(self.root)[0]['description']['selected']
        state={k:v for k,v in self.f.f.f.snapshot().items() if k.startswith('state/')}
        selection.select(self.root,result['deployment'],expected_selected=old,yes=True)
        selection.select(self.root,expected_selected=result['deployment'],rollback=True,yes=True)
        self.assertEqual(selection.current(self.root)[0]['description']['selected'],old)
        self.assertEqual({k:v for k,v in self.f.f.f.snapshot().items() if k.startswith('state/')},state)

    def test_one_plan_keeps_selection_exact_and_holds_writer_locks_through_construction(self):
        def build(*args,**kwargs):
            probe="import fcntl,sys; f=open(sys.argv[1],'r+'); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)"
            waiting=subprocess.run([sys.executable,'-c',probe,str(self.root/'boot/mpm/.lock')],capture_output=True)
            self.assertNotEqual(waiting.returncode,0);self.assertIn(b'BlockingIOError',waiting.stderr)
            return self.build(*args,**kwargs)
        with mock.patch.object(constructor,'_build_locked',side_effect=build),\
             mock.patch.object(update.transition,'_prepare',wraps=update.transition._prepare) as plan,\
             mock.patch.object(update.transition,'repeat',side_effect=AssertionError('ordinary transaction rebuilt its plan')):
            result=update.stage(self.root,'system',self.candidate,**self.options)
        self.assertEqual(plan.call_count,1)
        self.assertEqual((self.root/selection.MENU).read_bytes(),self.before)
        self.assertEqual(selection.ready(self.root,result['deployment'])['record']['description']['inputs']['description']['system']['artifact'],self.candidate)
        with mock.patch.object(constructor,'_build_locked',side_effect=AssertionError('completed preparation rebuilt')):
            self.assertFalse(update.stage(self.root,'system',self.candidate,**self.options)['changed'])

    def test_account_change_before_admission_leaves_no_ready_entry_and_retry_can_complete(self):
        passwd=self.root/'state/etc/passwd';original=passwd.read_bytes()
        before=set((self.root/'boot/mpm/ready').iterdir())
        def changed(*args,**kwargs):
            built=self.build(*args,**kwargs);passwd.write_bytes(original.replace(b'root:',b'edited:',1));return built
        with mock.patch.object(constructor,'_build_locked',side_effect=changed),\
             self.assertRaisesRegex(ValueError,'state or target changed'):
            update.stage(self.root,'system',self.candidate,**self.options)
        self.assertEqual(set((self.root/'boot/mpm/ready').iterdir()),before)
        self.assertEqual((self.root/selection.MENU).read_bytes(),self.before)
        passwd.write_bytes(original)
        with mock.patch.object(constructor,'_build_locked',side_effect=self.build):
            self.assertTrue(update.stage(self.root,'system',self.candidate,**self.options)['changed'])
        self.assertEqual((self.root/selection.MENU).read_bytes(),self.before)

    def test_uncertain_admission_keeps_the_complete_entry_and_retry_does_not_rebuild(self):
        publish=tx.publish
        def uncertain(source,destination):
            if destination.parent == self.root/'boot/mpm/ready':
                def failed_sync(path):raise OSError('injected admission flush failure')
                return publish(source,destination,sync=failed_sync)
            return publish(source,destination)
        with mock.patch.object(constructor,'_build_locked',side_effect=self.build),             mock.patch.object(tx,'publish',side_effect=uncertain),self.assertRaises(tx.PublicationUncertain):
            update.stage(self.root,'system',self.candidate,**self.options)
        self.assertEqual((self.root/selection.MENU).read_bytes(),self.before)
        with mock.patch.object(constructor,'_build_locked',side_effect=AssertionError('uncertain complete entry rebuilt')):
            result=update.stage(self.root,'system',self.candidate,**self.options)
        self.assertFalse(result['changed']);selection.ready(self.root,result['deployment'],verify=True)

    def test_unsupported_startup_change_is_refused_before_construction(self):
        candidate=self.f.f.candidate(service_change=True)
        with mock.patch.object(constructor,'_build_locked',side_effect=AssertionError('incompatible candidate constructed')),\
             self.assertRaisesRegex(ValueError,'boot update blocked'):
            update.stage(self.root,'system',candidate,**self.options)
        self.assertEqual((self.root/selection.MENU).read_bytes(),self.before)

    def test_explicit_verify_still_detects_damaged_installed_profile(self):
        file=system.realization_path(self.root,self.candidate)/'profile/tools/mpm_cli.py'
        file.chmod(0o644);file.write_bytes(file.read_bytes()+b'\n# damage\n');file.chmod(0o444)
        with mock.patch.object(constructor,'_build_locked',side_effect=AssertionError('damaged candidate constructed')),\
             self.assertRaisesRegex(ValueError,'profile content/modes damaged'):
            update.stage(self.root,'system',self.candidate,verify=True,**self.options)
        self.assertEqual((self.root/selection.MENU).read_bytes(),self.before)


if __name__=='__main__':unittest.main()
