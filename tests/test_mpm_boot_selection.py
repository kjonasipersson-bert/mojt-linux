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
