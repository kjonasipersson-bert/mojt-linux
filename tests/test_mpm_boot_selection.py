# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Cheap authority boundaries; actual stage/select/recovery joins the archive case."""
import copy
from contextlib import nullcontext
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_mpm_boot_v2 as fixtures
import mpm_boot_selection as selection
import mpm_boot_status as status
import mpm_boot_constructor as constructor
import mpm_system_cli as cli


class Boundaries(unittest.TestCase):
    def test_selection_defers_full_audit_until_locked_publication(self):
        wanted='sha256:'+'2'*64;before='sha256:'+'1'*64
        entry=dict(record=fixtures.bound(fixtures.fixture()))
        old=dict(description=dict(selected=before,previous=None,entries=[]))
        with mock.patch.object(selection.os,'geteuid',return_value=0), \
             mock.patch.object(selection.store,'target',side_effect=lambda p:p), \
             mock.patch.object(selection,'current',side_effect=lambda p:(copy.deepcopy(old),{before:entry},b'menu')), \
             mock.patch.object(selection,'ready',return_value=entry), \
             mock.patch('mpm_base_transition.read_locks',side_effect=lambda p:nullcontext()), \
             mock.patch.object(selection,'locked',side_effect=lambda p:nullcontext()), \
             mock.patch.object(selection,'_gates') as gates, \
             mock.patch.object(selection,'_publish') as publish:
            selection.select(Path('/fixture'),wanted,expected_selected=before,dry_run=True)
            gates.assert_not_called();publish.assert_not_called()
            selection.select(Path('/fixture'),wanted,expected_selected=before,dry_run=True,verify=True)
            self.assertEqual(gates.call_count,1);publish.assert_not_called();gates.reset_mock()
            with mock.patch('builtins.input',return_value='n'),self.assertRaisesRegex(ValueError,'cancelled'):
                selection.select(Path('/fixture'),wanted,expected_selected=before)
            gates.assert_not_called();publish.assert_not_called()
            selection.select(Path('/fixture'),wanted,expected_selected=before,yes=True)
            self.assertEqual(gates.call_count,1);publish.assert_called_once();publish.reset_mock()
            gates.side_effect=ValueError('damaged retained tree')
            with self.assertRaisesRegex(ValueError,'damaged retained tree'):
                selection.select(Path('/fixture'),wanted,expected_selected=before,yes=True)
            publish.assert_not_called()

    def test_candidate_choice_is_explicit_and_does_not_install(self):
        import mpm_boot_update as update
        rows=[dict(version=dict(release_id='A'),artifact='sha256:'+'1'*64),
              dict(version=dict(release_id='B'),artifact='sha256:'+'2'*64)]
        with mock.patch.object(update.system,'status',return_value=dict(installed=rows)), \
             mock.patch('builtins.input',side_effect=['0','invalid','2']), \
             mock.patch('sys.stderr',new_callable=io.StringIO):
            self.assertEqual(update.choose_artifact(Path('/fixture'),'system'),rows[1]['artifact'])
        with mock.patch.object(update.system,'status',return_value=dict(installed=rows)), \
             mock.patch('builtins.input',return_value='q'), \
             mock.patch('sys.stderr',new_callable=io.StringIO),self.assertRaisesRegex(ValueError,'cancelled'):
            update.choose_artifact(Path('/fixture'),'system')

    def test_cli_requires_exact_candidate_for_scripts_and_passes_terminal_choice(self):
        import mpm_boot_update as update
        identifier='sha256:'+'3'*64
        with mock.patch.object(update.selection,'present',return_value=True), \
             mock.patch.object(update,'choose_artifact',return_value=identifier) as choose, \
             mock.patch.object(update,'stage',return_value=dict(changed=False)) as stage, \
             mock.patch('sys.stdin.isatty',return_value=False), \
             mock.patch('sys.stderr',new_callable=io.StringIO):
            self.assertEqual(update.main('system',['stage','--disk-root','/fixture','--yes']),1)
            choose.assert_not_called();stage.assert_not_called()
            with mock.patch('sys.stdin.isatty',return_value=True):
                self.assertEqual(update.main('system',['stage','--disk-root','/fixture','--json']),1)
                with mock.patch('sys.stdout',new_callable=io.StringIO):
                    self.assertEqual(update.main('system',['stage','--disk-root','/fixture']),0)
            choose.assert_called_once_with(Path('/fixture'),'system')
            self.assertEqual(stage.call_args.args[2],identifier)

    def test_update_keeps_existing_management_requirements_and_other_area_inputs(self):
        import mpm_boot_update as update
        source=fixtures.fixture();before=source['description']
        requirement=dict(family='application-state',read=[1],write=[1],capabilities=['read-settings'])
        before['management_required']=[requirement]
        source=selection.model.record(selection.model.INPUTS,before)
        candidate=copy.deepcopy(before['system']);candidate['artifact']='sha256:'+'9'*64
        fields=dict(base=before['base'],system=candidate,kernel=before['kernel'])
        plan=dict(description=dict(baseline_inputs=source))
        with mock.patch.object(update.transition,'boot_fields',return_value=fields), \
             mock.patch.object(constructor,'constructor',return_value=before['constructor']):
            result=update.source_for(plan,{},Path('/fixture/busybox'))['description']
        self.assertEqual(result['base'],before['base']);self.assertEqual(result['kernel'],before['kernel'])
        self.assertEqual(result['system'],candidate)
        self.assertIn(requirement,result['management_required'])
        self.assertIn(selection.MANAGEMENT_SUPPORT[0],result['management_required'])
        self.assertEqual(source['description']['management_required'],[requirement])

    def test_json_and_diagnostic_results_cannot_authorize_selection_or_create_a_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'absent'
            for value in ({'handover_enabled':True},constructor.CompletedBuild({'handover_enabled':False},None)):
                with self.assertRaisesRegex(ValueError,'manager-owned'):
                    selection._admit(root,{},value,adapters={})
            with mock.patch.object(selection.os,'geteuid',return_value=1000),self.assertRaisesRegex(ValueError,'administrator'):
                selection.select(root,'sha256:'+'1'*64,expected_selected='sha256:'+'2'*64,yes=True)
            self.assertFalse(root.exists())
        record=fixtures.bound(fixtures.fixture())
        wrapper=dict(format='mojt-running-native-v2',deployment=record,inputs=record['description']['inputs']['id'],installation='1'*32)
        self.assertEqual(status.unwrap(wrapper),record);self.assertEqual(status.description(wrapper)['system']['artifact'],'sha256:'+'d'*64)
        changed=copy.deepcopy(wrapper);changed['inputs']='sha256:'+'0'*64
        with self.assertRaisesRegex(ValueError,'binding'):status.unwrap(changed)
        with mock.patch.object(selection,'select',return_value={'changed':False}) as choose:
            self.assertEqual(cli.main(['select','--disk-root','/explicit-target','--deployment',record['id'],
                '--expected-selected',record['id'],'--dry-run','--json']),0)
            self.assertTrue(choose.call_args.kwargs['dry_run'])


if __name__=='__main__':unittest.main()
