# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Base boot slots: exact content, no state/selection effects, failure boundaries."""
import copy
import gzip
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import runpy
import unittest
from unittest import mock

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
import mojt_artifact as artifact
import mpm_base as base
import mpm_base_boot as manager
import mpm_kernel_boot as boot
import mpm_base_cli as cli
import mpm_base_status as base_status
import test_mpm_base as base_fixture
import test_mpm_base_transition as transition_fixture


class DefaultsTests(unittest.TestCase):
    def test_preserves_local_conflicts_and_does_not_follow_existing_state_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);src=root/'candidate/usr/etc';dst=root/'state/etc'
            (src/'config').mkdir(parents=True);dst.mkdir(parents=True)
            (src/'hostname').write_text('default');(dst/'hostname').write_text('local')
            (src/'config/missing').write_text('default');(dst/'config').symlink_to('/tmp')
            (src/'new').write_text('new');(src/'os-release').symlink_to('../lib/os-release')
            self.assertEqual(manager.defaults_check(root,root/'candidate')['missing'],['new'])
            self.assertEqual((dst/'hostname').read_text(),'local')
            self.assertEqual(os.readlink(dst/'config'),'/tmp')
            self.assertFalse((dst/'new').exists())


class AcceptanceFixtureTests(unittest.TestCase):
    def test_test_release_rewrite_changes_only_one_declared_field(self):
        helper=runpy.run_path(str(REPO/'tests/run-base-boot-acceptance.py'))['replace_field']
        raw='format=1\n[base]\nversion = "0.1.3"\nname="mojt"\n[image]\nsha256="old"\n'
        changed=helper(raw,'base','version','0.1.3-boot-test')
        self.assertEqual(changed,raw.replace('version = "0.1.3"','version = "0.1.3-boot-test"'))
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            helper(raw+'[base]\nversion="duplicate"\n','base','version','new')



@unittest.skipUnless(os.geteuid()==0 and shutil.which('cpio') and shutil.which('zstd') and shutil.which('tar'),
                     'requires root and real archive tools')
class BaseStageTests(unittest.TestCase):
    def setUp(self):
        # Share setup only; do not repeat the preflight test matrix here.
        self.f=transition_fixture.NativePreflightTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root
        archive,self.body=self.f.b.package(version='0.1.4',abi={'libc':'glibc','libc_version':'2.41'},
            extra=[base_fixture.entry('usr/bin/sh',b'#!/bin/sh\n# synthetic candidate shell\n'),
                   *[base_fixture.entry(n) for n in ('dev','proc','sys')]])
        base.install(self.root,archive,self.body['id'],yes=True)
        self.bounds=copy.deepcopy(self.f.bounds);self.bounds['base']['artifact']=self.body['id']
        self.baseline=self.f.f.baseline

    def builder(self,*args):
        vm=boot.vm_module()
        with mock.patch.object(boot,'vm_module',return_value=vm), \
             mock.patch.object(vm,'static_x86_64_elf',return_value=True), \
             mock.patch.object(vm,'validate_busybox_applets'), \
             mock.patch.object(vm,'module_paths',side_effect=lambda release,p,**kw:[p/'kernel/example.ko']), \
             mock.patch.object(vm.os,'mknod',side_effect=lambda path,*unused:path.touch()):
            return manager.build_initramfs(*args)

    def stage(self,**kwargs):
        return manager.stage(self.root,self.body['id'],self.bounds,baseline=self.baseline,
                             yes=True,builder=self.builder,**kwargs)

    def test_preview_creates_no_slot_registry_defaults_or_selection(self):
        before=self.f.f.snapshot();result=self.stage(dry_run=True)
        self.assertEqual(before,self.f.f.snapshot());self.assertFalse(result['changed'])
        self.assertFalse(result['plan']['persistent_state_changes'])

    def test_fresh_frontend_preview_uses_one_explicit_target(self):
        bounds=self.root.parent/'candidate-bounds.json';bounds.write_bytes(artifact.canonical(self.bounds))
        before=self.f.f.snapshot()
        result=subprocess.run([sys.executable,'-I','-B',str(REPO/'tools/mpm'),'base','stage',
            '--disk-root',str(self.root),'--baseline',self.baseline,'--artifact',self.body['id'],
            '--base-context',str(bounds),'--dry-run'],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('"persistent_state_changes": false',result.stdout)
        self.assertEqual(before,self.f.f.snapshot())

    def test_stage_binds_changed_base_and_readonly_mounts_without_changing_state_or_next_boot(self):
        old,entries,menu=boot.current(self.root,self.baseline)
        original=base.rootfs_inventory(base.realization_path(self.root,self.body['id'])/'tree/rootfs')
        before={k:v for k,v in self.f.f.snapshot().items() if k.startswith('state/')}
        result=self.stage();entry=boot.inspect_entry(self.root,result['slot']);d=entry['record']['description']
        self.assertEqual(d['base'],self.bounds['base'])
        self.assertEqual(d['kernel'],entries[old['selected']]['record']['description']['kernel'])
        self.assertEqual(d['system'],entries[old['selected']]['record']['description']['system'])
        self.assertEqual(boot.current(self.root,self.baseline)[2],menu)
        self.assertEqual(base.rootfs_inventory(base.realization_path(self.root,self.body['id'])/'tree/rootfs'),original)
        # Empty Ports lock infrastructure is the only cooperating state addition.
        after={k:v for k,v in self.f.f.snapshot().items() if k in before}
        self.assertEqual(after,before)
        self.assertEqual(boot.live_context(self.root,entry)[2]['format'],manager.INPUTS)
        raw=gzip.decompress((entry['path']/'initramfs.cpio.gz').read_bytes())
        self.assertIn(('/sysroot/'+result['slot']+'/tree/rootfs').encode(),raw)
        self.assertIn(b'mount -o remount,bind,ro "$root" /newroot',raw)
        self.assertNotIn(b'readlink /sysroot/base/current',raw)
        self.assertIn(b'/newroot/run/mojt/deployment.json',raw)
        self.assertFalse(result['boot_ready']);self.assertTrue(result['stage_ready'])
        repeat_before=self.f.f.snapshot();repeat=self.stage()
        self.assertFalse(repeat['changed']);self.assertEqual(result['deployment'],repeat['deployment'])
        self.assertEqual(repeat_before,self.f.f.snapshot())

    def test_kernel_selection_cannot_silently_select_a_changed_base(self):
        result=self.stage();state,unused,menu=boot.current(self.root,self.baseline)
        with self.assertRaisesRegex(ValueError,'selected Base'):
            boot.select(self.root,result['deployment'],expected_selected=state['selected'],baseline=self.baseline,yes=True)
        self.assertEqual(boot.current(self.root,self.baseline)[2],menu)

    def test_corrupt_copied_tree_blocks_repeat_without_selection_change(self):
        result=self.stage();path=self.root/result['slot']/'tree/rootfs/usr/bin/tool'
        path.write_text('corrupt');menu=(self.root/'boot/mojt/grub.cfg').read_bytes()
        with self.assertRaisesRegex(ValueError,'Base content|Base boot|immutable Base'):self.stage()
        self.assertEqual((self.root/'boot/mojt/grub.cfg').read_bytes(),menu)

    def test_missing_default_blocks_staging_instead_of_mutating_etc(self):
        (self.root/'state/etc/hostname').unlink();before=self.f.f.snapshot()
        with self.assertRaisesRegex(ValueError,'missing-default'):self.stage()
        self.assertEqual(before,self.f.f.snapshot())

    def test_old_system_without_matching_management_is_blocked(self):
        # Keep its manifest intact: exercise the gate directly before any writer.
        profile=self.root/'system/native-fixture'
        with mock.patch.object(manager,'CODE',(*manager.CODE,'not-installed.py')):
            with self.assertRaisesRegex(ValueError,'management'):manager.management(profile)

    def test_input_change_during_construction_publishes_no_slot(self):
        original=self.builder
        def mutate(*args):
            result=original(*args)
            path=base.realization_path(self.root,self.body['id'])/'tree/rootfs/usr/bin/tool'
            path.write_text('late change')
            return result
        menu=(self.root/'boot/mojt/grub.cfg').read_bytes()
        with mock.patch.object(self,'builder',side_effect=mutate),self.assertRaisesRegex(ValueError,'rootfs'):
            self.stage()
        self.assertEqual(list((self.root/'boot/mpm/slots').iterdir()),[])
        self.assertEqual((self.root/'boot/mojt/grub.cfg').read_bytes(),menu)

    def test_select_and_return_preserve_system_kernel_state_and_status_identity(self):
        result=self.stage();old,entries,menu=boot.current(self.root,self.baseline)
        running=entries[old['selected']]['record']
        state_before=manager.transition.state_inputs(self.root)
        before=self.f.f.snapshot()
        preview=manager.select(self.root,result['deployment'],expected_selected=old['selected'],baseline=self.baseline,dry_run=True)
        self.assertFalse(preview['changed']);self.assertEqual(before,self.f.f.snapshot())
        cli_preview=subprocess.run([sys.executable,'-I','-B',str(REPO/'tools/mpm'),'base','select',
            '--disk-root',str(self.root),'--baseline',self.baseline,'--deployment',result['deployment'],
            '--expected-selected',old['selected'],'--dry-run'],text=True,capture_output=True)
        self.assertEqual(cli_preview.returncode,0,cli_preview.stderr)
        self.assertEqual(before,self.f.f.snapshot())
        chosen=manager.select(self.root,result['deployment'],expected_selected=old['selected'],baseline=self.baseline,yes=True)
        self.assertTrue(chosen['changed'])
        state,new_entries,new_menu=boot.current(self.root)
        self.assertEqual(state['format'],boot.BASE_MENU_FORMAT)
        self.assertIn(b'Mojt Base 0.1.4',new_menu);self.assertIn(b'Mojt Base 0.1.3',new_menu)
        self.assertEqual(state['selected'],result['deployment']);self.assertEqual(state['previous'],old['selected'])
        self.assertEqual(set(new_entries),{old['selected'],result['deployment']})
        observed=base_status.status(self.root,running_record=running)
        self.assertEqual(observed['selected']['artifact'],self.body['id'])
        self.assertEqual(observed['running']['deployment'],old['selected']);self.assertFalse(observed['running_is_selected'])
        unchanged=self.f.f.snapshot()
        self.assertFalse(manager.select(self.root,result['deployment'],expected_selected=state['selected'],yes=True)['changed'])
        self.assertEqual(unchanged,self.f.f.snapshot())
        returned=manager.select(self.root,None,expected_selected=state['selected'],rollback=True,yes=True)
        self.assertEqual(returned['selected'],old['selected'])
        restored=base_status.status(self.root,running_record=running)
        self.assertTrue(restored['running_is_selected'])
        self.assertEqual(manager.transition.state_inputs(self.root),state_before)
        self.assertEqual(set(boot.current(self.root)[1]),set(new_entries))

    def test_selection_requires_the_expected_current_deployment(self):
        result=self.stage();menu=(self.root/'boot/mojt/grub.cfg').read_bytes()
        with self.assertRaisesRegex(ValueError,'selected deployment changed'):
            manager.select(self.root,result['deployment'],expected_selected='sha256:'+'0'*64,baseline=self.baseline,yes=True)
        self.assertEqual((self.root/'boot/mojt/grub.cfg').read_bytes(),menu)

    def test_base_selection_cannot_smuggle_a_kernel_change(self):
        original=self.f.f.old_id
        kernel_candidate=self.f.f.stage()
        menu=(self.root/'boot/mojt/grub.cfg').read_bytes()
        with self.assertRaisesRegex(ValueError,'preserve exact System/Kernel'):
            manager.select(self.root,kernel_candidate['deployment'],expected_selected=original,baseline=self.baseline,yes=True)
        self.assertEqual((self.root/'boot/mojt/grub.cfg').read_bytes(),menu)

    def test_late_candidate_tree_change_blocks_menu_publication(self):
        result=self.stage();original=manager.selection_context;calls=0
        def mutate(root,entry):
            nonlocal calls
            calls+=1
            if calls==3:(root/result['slot']/'tree/rootfs/usr/bin/tool').write_text('late corruption')
            return original(root,entry)
        menu=(self.root/'boot/mojt/grub.cfg').read_bytes()
        with mock.patch.object(manager,'selection_context',side_effect=mutate),self.assertRaisesRegex(ValueError,'Base content'):
            manager.select(self.root,result['deployment'],expected_selected=self.f.f.old_id,baseline=self.baseline,yes=True)
        self.assertEqual((self.root/'boot/mojt/grub.cfg').read_bytes(),menu)

    def test_selection_flush_uncertainty_retains_new_menu_and_both_entries(self):
        result=self.stage();original=manager.kernel.sync_directory
        def fail(path):
            if path==self.root/'boot/mojt':raise OSError('menu flush failed')
            return original(path)
        with mock.patch.object(manager.kernel,'sync_directory',side_effect=fail),self.assertRaises(tx_error()):
            manager.select(self.root,result['deployment'],expected_selected=self.f.f.old_id,baseline=self.baseline,yes=True)
        state,entries,raw=boot.current(self.root)
        self.assertEqual(state['selected'],result['deployment']);self.assertEqual(len(entries),2)
        for entry in entries.values():boot.live_context(self.root,entry)

    def test_kernel_update_after_base_selection_keeps_exact_base_slot_tree(self):
        first=self.stage()
        manager.select(self.root,first['deployment'],expected_selected=self.f.f.old_id,baseline=self.baseline,yes=True)
        def kernel_builder(*args,**kwargs):
            vm=boot.vm_module()
            with mock.patch.object(boot,'vm_module',return_value=vm), \
                 mock.patch.object(vm,'static_x86_64_elf',return_value=True), \
                 mock.patch.object(vm,'validate_busybox_applets'), \
                 mock.patch.object(vm,'module_paths',side_effect=lambda release,p,**kw:[p/'kernel/example.ko']), \
                 mock.patch.object(vm.os,'mknod',side_effect=lambda path,*unused:path.touch()):
                return boot.build_initramfs(*args,**kwargs)
        new=boot.stage(self.root,self.f.f.candidate['id'],yes=True,builder=kernel_builder)
        entry=boot.inspect_entry(self.root,new['slot'])
        receipt=boot.live_context(self.root,entry)[2]
        self.assertEqual(receipt['base_tree'],first['slot']+'/tree/rootfs')
        raw=gzip.decompress((entry['path']/'initramfs.cpio.gz').read_bytes())
        self.assertIn(('/sysroot/'+receipt['base_tree']).encode(),raw)
        self.assertNotIn(b'root="/sysroot/base/$version"',raw)
        boot.select(self.root,new['deployment'],expected_selected=first['deployment'],yes=True)
        state,entries,_=boot.current(self.root)
        self.assertEqual(entries[state['selected']]['record']['description']['base'],self.bounds['base'])
        self.assertEqual(state['selected'],new['deployment'])

    def test_post_publish_flush_failure_retains_complete_slot_and_old_selection(self):
        original=manager.kernel.sync_directory
        def fail(path):
            if path==self.root/'boot/mpm/slots':raise OSError('flush failed')
            return original(path)
        menu=(self.root/'boot/mojt/grub.cfg').read_bytes()
        with mock.patch.object(manager.kernel,'sync_directory',side_effect=fail),self.assertRaises(tx_error()):self.stage()
        slots=list((self.root/'boot/mpm/slots').iterdir());self.assertEqual(len(slots),1)
        entry=boot.inspect_entry(self.root,'boot/mpm/slots/'+slots[0].name)
        boot.live_context(self.root,entry)
        self.assertEqual((self.root/'boot/mojt/grub.cfg').read_bytes(),menu)


def tx_error():
    from mpm_transaction import PublicationUncertain
    return PublicationUncertain


if __name__=='__main__':unittest.main()
