# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Cheap authority boundaries; actual stage/select/recovery joins the archive case."""
import copy
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
