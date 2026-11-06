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
import unittest
from unittest import mock

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
import mojt_artifact as artifact
import mpm_base as base
import mpm_base_boot as manager
import mpm_kernel_boot as boot
import mpm_base_cli as cli
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
