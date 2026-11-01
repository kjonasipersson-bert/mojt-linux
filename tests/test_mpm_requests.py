# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import mpm_requests as r


class RequestsTests(unittest.TestCase):
    def setUp(self):
        self.empty = r.empty_state('1'*32)
        self.doc = dict(format=r.CONFIG,name='workstation',ports=dict(source='local',packages=['hello@2.12'],active=dict(hello='hello@2.12')))
        self.ref = dict(provider='native',artifact='sha256:'+'2'*64)

    def test_toml_normalization_all_areas_and_version_gate(self):
        raw = b'''format = "mojt-configuration-v1"
name = "main"
[base]
selector = "mojt@=0.1.3"
[kernel]
policy = "pinned"
series = "6.12"
[system]
packages = ["systemd"]
[ports]
packages = ["python@3.12", "hello@=2.12.3", "neovim"]
'''
        doc = r.parse_configuration(raw)
        self.assertEqual(doc['ports']['packages'], sorted(doc['ports']['packages']))
        self.assertEqual(r.digest(doc),r.digest(r.parse_configuration(b'# comment\n'+raw)))
        for bad in [raw.replace(b'v1',b'v2'),raw.replace(b'@3.12',b'@3.*'),raw.replace(b'"pinned"',b'"latest-lts"'),b'',raw+b'unknown=true\n']:
            with self.assertRaises(ValueError):r.parse_configuration(bad)

    def test_idempotence_input_immutability_and_configuration_removal(self):
        before = copy.deepcopy(self.empty)
        state = r.reconcile_configuration(self.empty,self.doc)
        self.assertEqual(before,self.empty)
        self.assertEqual(state,r.reconcile_configuration(state,self.doc))
        self.assertEqual(len(state['description']['claims']),1)
        empty_doc = dict(format=r.CONFIG,name='workstation',ports=dict(packages=[]))
        result = r.reconcile_configuration(state,empty_doc)
        self.assertEqual(result['description']['claims'],[])
        self.assertEqual(result['description']['selections'],[])
        # Whole omitted table releases the same source's wishes as well.
        self.assertEqual(r.reconcile_configuration(state,dict(format=r.CONFIG,name='workstation'))['description']['claims'],[])

    def test_configuration_cannot_remove_interactive_claim_or_override(self):
        state = r.reconcile_configuration(self.empty,self.doc)
        state = r.request_interactively(state,'hello@=2.12.3','local')
        old_choice = copy.deepcopy(state['description']['selections'])
        self.assertEqual(old_choice[0]['origin']['kind'],'configuration')
        state = r.select_interactively(state,'hello',self.ref)
        self.assertEqual(state,r.reconcile_configuration(state,self.doc))
        changed = copy.deepcopy(self.doc)
        changed['ports'].update(packages=['hello@3.0'],active=dict(hello='hello@3.0'))
        result = r.reconcile_configuration(state,changed)
        self.assertEqual(result['description']['selections'],state['description']['selections'])
        result = r.reconcile_configuration(result,dict(format=r.CONFIG,name='workstation'))
        self.assertEqual(len(result['description']['claims']),1)
        self.assertEqual(result['description']['claims'][0]['origin']['kind'],'interactive')
        self.assertEqual(result['description']['selections'][0]['reference'],self.ref)

    def test_manual_install_of_existing_content_is_an_independent_reason(self):
        state = r.reconcile_configuration(self.empty,self.doc)
        result = r.request_interactively(state,'hello@2.12','local')
        self.assertEqual(len(result['description']['claims']),2)
        self.assertEqual(result['description']['selections'],state['description']['selections'])
        self.assertEqual(result,r.request_interactively(result,'hello@2.12','local'))

    def test_other_configuration_retains_its_claim(self):
        state = r.reconcile_configuration(self.empty,self.doc)
        other = copy.deepcopy(self.doc);other['name']='second'
        state = r.reconcile_configuration(state,other)
        state = r.reconcile_configuration(state,dict(format=r.CONFIG,name='workstation'))
        self.assertEqual(len(state['description']['claims']),1)
        self.assertEqual(state['description']['selections'][0]['origin']['name'],'second')

    def test_conflicts_block_without_mutating_input(self):
        state = r.reconcile_configuration(self.empty,self.doc)
        before = copy.deepcopy(state)
        other = copy.deepcopy(self.doc);other['name']='other';other['ports'].update(packages=['hello@3.0'],active=dict(hello='hello@3.0'))
        with self.assertRaises(ValueError):r.reconcile_configuration(state,other)
        self.assertEqual(state,before)
        override = r.select_interactively(state,'hello',self.ref)
        self.assertEqual(r.reconcile_configuration(override,other)['description']['selections'],override['description']['selections'])

    def test_source_binding_does_not_silently_follow_changed_default(self):
        doc = copy.deepcopy(self.doc);del doc['ports']['source']
        with self.assertRaises(ValueError):r.reconcile_configuration(self.empty,doc)
        state = r.reconcile_configuration(self.empty,doc,default_source='one')
        state = r.reconcile_configuration(state,doc,default_source='two')
        self.assertEqual(state['description']['claims'][0]['source'],'one')

    def test_corrupt_unknown_or_orphan_state_is_refused(self):
        state = r.reconcile_configuration(self.empty,self.doc)
        for mutate in [lambda s:s.update(format='mojt-request-state-v2'),lambda s:s.update(id='sha256:'+'0'*64),lambda s:s['description']['claims'].clear()]:
            bad = copy.deepcopy(state);mutate(bad)
            with self.assertRaises(ValueError):r.validate(bad)
        self.assertEqual(r.validate(state),state)

    def test_existing_first_install_default_survives_reapplication(self):
        doc = copy.deepcopy(self.doc);del doc['ports']['active']
        state = r.reconcile_configuration(self.empty,doc)
        c = state['description']['claims'][0]
        d = copy.deepcopy(state['description'])
        d['selections'] = [dict(role='hello',origin=c['origin'],mode='request',claim=c['key'])]
        state = r.seal(d)
        self.assertEqual(state,r.reconcile_configuration(state,doc))

    def test_identical_selector_with_different_source_is_not_a_precedence_rule(self):
        state = r.reconcile_configuration(self.empty,self.doc)
        doc = copy.deepcopy(self.doc);doc['name']='other';doc['ports']['source']='different'
        with self.assertRaises(ValueError):r.reconcile_configuration(state,doc)

    def test_runtime_model_matches_the_versioned_specification_examples(self):
        root = Path(__file__).resolve().parents[1] / 'docs/formats/draft-v1/workflow-examples'
        example = json.loads((root/'request-state.json').read_text())
        doc = r.parse_configuration((root/'mojt-configuration.toml').read_bytes())
        state = r.reconcile_configuration(r.empty_state(example['description']['installation']),doc)
        state = r.request_interactively(state,'hello@=2.12.3','local')
        state = r.select_interactively(state,'hello',example['description']['selections'][0]['reference'])
        self.assertEqual(state,example)
        removed = json.loads((root/'request-state-config-removed.json').read_text())
        self.assertEqual(r.reconcile_configuration(state,removed['description']['configurations'][0]['document']),removed)

    def test_malformed_nested_state_has_a_uniform_validation_error(self):
        for claims in [[None],[{}],['bad']]:
            bad = copy.deepcopy(self.empty)
            bad['description']['claims'] = claims
            with self.assertRaises(ValueError):r.validate(bad)

    def test_configuration_rejects_oversize_package_names(self):
        doc = copy.deepcopy(self.doc)
        doc['ports'] = dict(packages=['x'*257])
        with self.assertRaises(ValueError):r.configuration(doc)


if __name__ == '__main__':unittest.main()
