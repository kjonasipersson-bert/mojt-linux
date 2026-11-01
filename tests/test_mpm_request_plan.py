# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import mpm_requests as wishes
import mpm_request_plan as planner


class RequestPlanTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]/'docs/formats/draft-v1/workflow-examples'
        self.before = wishes.empty_state('1'*32)
        self.after = wishes.reconcile_configuration(self.before,dict(format=wishes.CONFIG,name='main',ports=dict(source='local',packages=['hello@2.12'])))
        catalog = json.loads((root/'catalog.fixture').read_text())
        candidate = catalog['candidates'][0]
        self.ref = dict(provider='native',artifact=candidate['artifact'])
        self.sources = dict(local=dict(snapshot='sha256:'+'3'*64,catalogs=dict(hello=catalog),offers=[dict(backend='native',artifact=candidate['artifact'],integrity=candidate['integrity'],reference=self.ref,dependencies=[],transport_sha256=candidate['integrity']['sha256'])]))
        self.options = dict(platform='x86_64-linux',target_identity='sha256:'+'4'*64,executor=dict(provider='native',artifact='sha256:'+'5'*64))

    def lock(self,state=None,sources=None):
        return planner.resolve_requests(state or self.after,self.sources if sources is None else sources,platform='x86_64-linux')

    def plan(self,before=None,after=None,**kwargs):
        state = after or self.after
        return planner.prepare_requests(self.before if before is None else before,state,self.lock(state),self.sources,**self.options,**kwargs)

    def test_resolution_matches_shared_selector_and_freezes_inputs(self):
        before = copy.deepcopy((self.after,self.sources))
        lock = self.lock()
        self.assertEqual(lock['description']['requests'],self.after['id'])
        self.assertEqual(lock['description']['resolutions'][0]['reference'],self.ref)
        self.assertEqual(before,(self.after,self.sources))
        self.assertEqual(lock,self.lock())

    def test_two_origins_share_import_without_losing_claims(self):
        state = wishes.request_interactively(self.after,'hello@=2.12.3','local')
        self.assertEqual(len(self.lock(state)['description']['resolutions']),2)
        plan = self.plan(after=state)
        self.assertEqual([r['type'] for r in plan['description']['steps']].count('install'),1)
        self.assertFalse(any(s['type'] in ('publish-profile','select-boot') for s in plan['description']['steps']))

    def test_verified_content_avoids_import_and_repeat_is_noop(self):
        plan = self.plan(before=self.after,installed=[self.ref])
        self.assertEqual(plan['description']['outcome'],'no-op')
        self.assertEqual(plan['description']['steps'],[])

    def test_empty_configuration_is_metadata_preparation_not_gc(self):
        after = wishes.reconcile_configuration(self.after,dict(format=wishes.CONFIG,name='main'))
        plan = self.plan(before=self.after,after=after)
        self.assertEqual([r['type'] for r in plan['description']['steps']],['retain-requests'])

    def test_missing_source_never_falls_back(self):
        with self.assertRaises(ValueError):self.lock(sources={})
        wrong = copy.deepcopy(self.sources);wrong['other']=wrong.pop('local')
        with self.assertRaises(ValueError):self.lock(sources=wrong)

    def test_unsupported_exact_version_and_platform_fail(self):
        state = wishes.request_interactively(self.after,'hello@=99.0','local')
        with self.assertRaises(ValueError):self.lock(state)
        with self.assertRaises(ValueError):planner.resolve_requests(self.after,self.sources,platform='aarch64-linux')

    def test_latest_series_and_exact_use_the_same_resolver(self):
        old='sha256:'+'7'*64
        catalog=self.sources['local']['catalogs']['hello']
        candidate=copy.deepcopy(catalog['candidates'][0])
        candidate.update(release_id='2.12.1',upstream_version='2.12.1',artifact=old,integrity={'sha256':'8'*64})
        catalog['candidates'].append(candidate)
        offer=copy.deepcopy(self.sources['local']['offers'][0])
        offer.update(artifact=old,reference=dict(provider='native',artifact=old),integrity=candidate['integrity'],transport_sha256='8'*64)
        self.sources['local']['offers'].append(offer)
        for selector,expected in [('hello',self.ref['artifact']),('hello@2.12',self.ref['artifact']),('hello@=2.12.1',old)]:
            state=wishes.request_interactively(self.before,selector,'local')
            self.assertEqual(self.lock(state)['description']['resolutions'][0]['reference']['artifact'],expected)

    def test_contradictory_offer_integrity_and_duplicate_binding_fail(self):
        for mode in ('integrity','duplicate'):
            source = copy.deepcopy(self.sources)
            if mode == 'integrity':source['local']['offers'][0]['integrity']={'bad':'evidence'}
            else:source['local']['offers'].append(copy.deepcopy(source['local']['offers'][0]))
            with self.assertRaises(ValueError):self.lock(sources=source)

    def test_stale_lock_cannot_be_reused(self):
        lock = self.lock(); source = copy.deepcopy(self.sources);source['local']['snapshot']='sha256:'+'6'*64
        with self.assertRaises(ValueError):planner.prepare_requests(self.before,self.after,lock,source,**self.options)

    def test_dependency_closure_order_missing_offer_and_cycle(self):
        dep = dict(provider='native',artifact='sha256:'+'7'*64)
        self.sources['local']['offers'][0]['dependencies']=[dep]
        with self.assertRaises(ValueError):self.plan()
        self.sources['local']['offers'].append(dict(backend='native',artifact=dep['artifact'],integrity={'sha256':'8'*64},reference=dep,dependencies=[],transport_sha256='8'*64))
        plan = self.plan(); steps=plan['description']['steps']
        root=next(s for s in steps if s['type']=='install' and s['subject']==self.ref)
        leaf=next(s for s in steps if s['type']=='install' and s['subject']==dep)
        self.assertIn(leaf['key'],root['after'])
        self.sources['local']['offers'][1]['dependencies']=[self.ref]
        with self.assertRaises(ValueError):self.plan()

    def test_active_override_needs_verified_installed_content(self):
        state = wishes.select_interactively(self.after,'hello',self.ref)
        with self.assertRaises(ValueError):self.plan(after=state)
        self.assertTrue(self.plan(after=state,installed=[self.ref]))

    def test_provider_identity_is_explicit_not_inferred_as_nix(self):
        source = copy.deepcopy(self.sources)
        catalog=source['local']['catalogs']['hello'];catalog['sources']['local']['backend']='custom'
        reference=dict(provider='custom',identity=dict(object='exact-custom-build'))
        offer=source['local']['offers'][0];offer.update(backend='custom',reference=reference,transport_sha256=None)
        lock=self.lock(sources=source)
        self.assertEqual(lock['description']['resolutions'][0]['reference'],reference)

    def test_late_baseline_guard_uses_selected_not_running(self):
        selected='sha256:'+'9'*64
        plan=self.plan(selected=selected,running='sha256:'+'a'*64)
        opts=dict(installation='1'*32,current=self.before,selected=selected,target_identity=self.options['target_identity'],executor=self.options['executor'])
        self.assertTrue(planner.revalidate_preparation(plan,**opts))
        for field,value in [('current',self.after),('selected',None),('installation','2'*32),('target_identity','sha256:'+'b'*64),('executor',self.ref)]:
            changed=dict(opts,**{field:value})
            with self.assertRaises(ValueError):planner.revalidate_preparation(plan,**changed)

    def test_preparation_guard_cannot_be_used_as_publication_authorization(self):
        plan=self.plan()
        plan['description']['steps'][0]['type']='publish-profile'
        plan=planner.record(plan['format'],plan['description'])
        with self.assertRaises(ValueError):planner.revalidate_preparation(plan,installation='1'*32,current=self.before,selected=None,target_identity=self.options['target_identity'],executor=self.options['executor'])


if __name__ == '__main__':unittest.main()
