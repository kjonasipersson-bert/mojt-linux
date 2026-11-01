# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pure reason release and override reset; no files/providers/installed inference."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import mpm_requests as wishes


class RemovalTests(unittest.TestCase):
    def setUp(self):
        self.empty=wishes.empty_state('1'*32)
        self.ref=dict(provider='native',artifact='sha256:'+'a'*64)
        self.doc=dict(format=wishes.CONFIG,name='main',ports=dict(source='local',packages=['hello@2.12'],active={'hello':'hello@2.12'}))
        self.config=wishes.reconcile_configuration(self.empty,self.doc)

    def test_remove_releases_only_interactive_claim_and_restores_declared_default(self):
        state=wishes.request_interactively(self.config,'hello@2.12','local')
        claim=next(c for c in state['description']['claims'] if c['origin']['kind']=='interactive')
        d=state['description'];d['selections']=[dict(role='hello',origin=claim['origin'],mode='request',claim=claim['key'])]
        state=wishes.seal(d);before=copy.deepcopy(state)
        result=wishes.remove_interactive(state,['hello'])
        self.assertEqual(result,self.config);self.assertEqual(state,before)
        self.assertEqual(wishes.remove_interactive(result,['hello']),result)

    def test_selector_release_preserves_independent_exact_override(self):
        state=wishes.request_interactively(self.config,'hello@2.12','local')
        state=wishes.select_interactively(state,'hello',self.ref)
        result=wishes.remove_interactive(state,['hello@2.12'])
        self.assertEqual(result['description']['selections'],state['description']['selections'])
        self.assertEqual(result['description']['claims'],self.config['description']['claims'])
        self.assertEqual(wishes.remove_interactive(result,['hello']),self.config)

    def test_source_release_preserves_other_source_and_unbound_exact_override(self):
        state=wishes.request_interactively(self.empty,'hello','local')
        state=wishes.request_interactively(state,'hello','other')
        state=wishes.select_interactively(state,'hello',self.ref)
        result=wishes.remove_interactive(state,['hello'],source='local')
        self.assertEqual([c['source'] for c in result['description']['claims']],['other'])
        self.assertEqual(result['description']['selections'],state['description']['selections'])

    def test_reset_keeps_all_wishes_and_only_changes_requested_selection(self):
        state=wishes.request_interactively(self.config,'hello@=2.12.1','local')
        state=wishes.select_interactively(state,'hello',self.ref)
        state=wishes.select_interactively(state,'paint',dict(provider='native',artifact='sha256:'+'b'*64))
        before=copy.deepcopy(state)
        result=wishes.reset_selection(state,['hello'])
        self.assertEqual(result['description']['claims'],state['description']['claims'])
        self.assertEqual(result['description']['configurations'],state['description']['configurations'])
        selections={s['role']:s for s in result['description']['selections']}
        self.assertEqual(selections['hello'],self.config['description']['selections'][0])
        self.assertEqual(selections['paint'],next(s for s in state['description']['selections'] if s['role']=='paint'))
        self.assertEqual(state,before);self.assertEqual(wishes.reset_selection(result,['hello']),result)

    def test_reset_reveals_configuration_conflict_without_changing_input(self):
        state=wishes.select_interactively(self.empty,'hello',self.ref)
        state=wishes.reconcile_configuration(state,self.doc)
        other=copy.deepcopy(self.doc);other['name']='other'
        other['ports'].update(packages=['hello@3.0'],active={'hello':'hello@3.0'})
        state=wishes.reconcile_configuration(state,other);before=copy.deepcopy(state)
        with self.assertRaisesRegex(ValueError,'conflicting configuration defaults'):
            wishes.reset_selection(state,['hello'])
        with self.assertRaisesRegex(ValueError,'conflicting configuration defaults'):
            wishes.remove_interactive(state,['hello'])
        self.assertEqual(state,before)

    def test_missing_reasons_are_noops_and_reset_requires_bare_roles(self):
        self.assertEqual(wishes.remove_interactive(self.config,['absent']),self.config)
        self.assertEqual(wishes.reset_selection(self.config,['absent']),self.config)
        for action,arguments in ((wishes.remove_interactive,[]),(wishes.reset_selection,[]),(wishes.reset_selection,['hello@2.12'])):
            with self.assertRaises(ValueError):action(self.config,arguments)


if __name__=='__main__':unittest.main()
