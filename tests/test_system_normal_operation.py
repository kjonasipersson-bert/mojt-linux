# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Normal work must follow exact inputs, independently of unrelated history."""
import os
import shutil
import unittest
from types import SimpleNamespace
from unittest import mock
from test_system_install_transaction import InstallationTransaction
import mpm_system as system
import mpm_boot_constructor as constructor
import mpm_boot_handover as handover
import mpm_boot_selection as selection
import mpm_boot_update as update
import mpm_management as management
import mpm_native_io as native
import mpm_boot_inventory as inventory


@unittest.skipUnless(os.geteuid()==0 and all(shutil.which(n) for n in ('tar','cpio','zstd')),'requires owned native fixture and codecs')
class NormalOperation(unittest.TestCase):
    def setUp(self):
        self.f=InstallationTransaction();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root
        self.selected=selection.current(self.root)[0]['description']['selected']
        self.entry=selection.ready(self.root,self.selected)

    def test_boot_reads_only_selected_system_even_with_unrelated_installed_history(self):
        for n in range(4):self.f.f.f.candidate()
        item=self.entry['record']['description']['inputs'];r=self.entry['receipt']['description']
        wanted=item['description']['system']['artifact'];allowed={wanted,*[d['artifact'] for d in system.object_record(self.root,wanted)[0]['dependencies']]}
        original=system.object_record;seen=[]
        def observed(root,identifier,**kwargs):
            self.assertIn(identifier,allowed);seen.append(identifier);return original(root,identifier,**kwargs)
        with mock.patch.object(system,'object_record',side_effect=observed),\
             mock.patch.object(system,'object_names',side_effect=AssertionError('boot enumerated objects')),\
             mock.patch.object(system,'registry_observation',side_effect=AssertionError('boot audited history')),\
             mock.patch.object(selection,'current',side_effect=AssertionError('boot decoded menu history')),\
             mock.patch.object(management,'observe_target',side_effect=AssertionError('boot observed unrelated history')):
            result=handover.check(self.root,item,r['proof'],r['handover'],verify_content=False)
        self.assertEqual(result['profile'],system.realization_path(self.root,wanted)/'profile')
        self.assertEqual(len(seen),len(allowed))

    def test_stage_accepts_new_links_once_and_passes_checked_facts_to_construction(self):
        with mock.patch.object(constructor,'_build_locked',side_effect=self.f.build),\
             mock.patch.object(system,'verify_links',wraps=system.verify_links) as links,\
             mock.patch.object(selection.store,'audit_inputs',side_effect=AssertionError('normal stage repeated input audit')),\
             mock.patch.object(selection,'current',side_effect=AssertionError('normal stage decoded historical receipts')),\
             mock.patch.object(management,'observe_target',side_effect=AssertionError('normal stage audited history')):
            result=update.stage(self.root,'system',self.f.candidate,**self.f.options)
        self.assertTrue(result['changed']);self.assertEqual(links.call_count,1)
        self.assertEqual(selection.selected(self.root)[0]['description']['selected'],self.selected)

    def test_changed_accepted_metadata_before_admission_is_refused(self):
        original=(self.root/selection.MENU).read_bytes()
        count=len(list((self.root/'boot/mpm/ready').iterdir()))
        def changed(*args,**kwargs):
            result=self.f.build(*args,**kwargs)
            path=system.realization_path(self.root,self.f.candidate)/'profile/manifest.json'
            path.chmod(0o644);path.write_bytes(path.read_bytes()+b' ');path.chmod(0o444)
            return result
        with mock.patch.object(constructor,'_build_locked',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'accepted System inputs changed'):
                update.stage(self.root,'system',self.f.candidate,**self.f.options)
        self.assertEqual((self.root/selection.MENU).read_bytes(),original)
        self.assertEqual(len(list((self.root/'boot/mpm/ready').iterdir())),count)

    def test_selected_entry_does_not_open_an_unrelated_broken_receipt(self):
        with mock.patch.object(constructor,'_build_locked',side_effect=self.f.build):
            prepared=update.stage(self.root,'system',self.f.candidate,**self.f.options)
        other=prepared['deployment'];selection.select(self.root,other,expected_selected=self.selected,yes=True)
        selection.select(self.root,self.selected,expected_selected=other,yes=True)
        receipt=self.root/'boot/mpm/ready'/(other[7:]+'.json')
        receipt.chmod(0o644);receipt.write_bytes(b'broken unrelated receipt');receipt.chmod(0o444)
        self.assertEqual(selection.selected(self.root)[0]['description']['selected'],self.selected)
        with self.assertRaises(ValueError):selection.current(self.root)

    def test_metadata_status_does_not_reconstruct_realizations_or_handover(self):
        with mock.patch.object(system,'realization',side_effect=AssertionError('status reconstructed a realization')),\
             mock.patch.object(selection,'ready',side_effect=AssertionError('status reconstructed readiness')):
            result=system.status(self.root)
        self.assertEqual(result['selected']['deployment'],self.selected)

    def test_retained_interpreter_descriptor_avoids_snapshots(self):
        constructor.retain_runtime(self.root,self.f.runtime);(self.root/'runtime').mkdir()
        d=self.f.runtime['description'];adapter=SimpleNamespace(inspect=mock.Mock(),verify=mock.Mock())
        with native.preparation(verify=False),mock.patch.object(inventory,'snapshot',side_effect=AssertionError('warm runtime scan')):
            value=constructor.retained_runtime(self.root,d['reference'],d['interpreter'],self.entry,adapters={'fixture':adapter})
        self.assertEqual(value,self.f.runtime);adapter.inspect.assert_called_once()
