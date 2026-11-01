# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import mpm_ports_profile as ports
import mpm_request_plan as planning
import mpm_requests as wishes
import mpm_transaction as transaction


class CopyAdapter:
    """Actual file acquisition/execution fixture, not a native package provider."""
    def __init__(self):self.fetches=0;self.fail=False;self.broken=False
    def describe(self,ref,root):
        i=ref['identity'];target=Path(root)/'retained/copy'/i['sha256']/'hello'
        return dict(reference=copy.deepcopy(ref),commands={i.get('command','hello'):str(target)})
    def ensure(self,ref,root):
        if self.fail:raise ValueError('injected acquisition failure')
        self.fetches+=1;i=ref['identity'];target=Path(next(iter(self.describe(ref,root)['commands'].values())))
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():shutil.copyfile(i['path'],target);target.chmod(0o555)
        self.verify(ref,root)
    def verify(self,ref,root):
        if self.broken:raise ValueError('injected verification failure')
        target=Path(next(iter(self.describe(ref,root)['commands'].values())))
        if hashlib.sha256(target.read_bytes()).hexdigest()!=ref['identity']['sha256']:raise ValueError('wrong copied bytes')


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.parent=Path(self.tmp.name);self.root=self.parent/'ports'
        self.adapter=CopyAdapter();self.adapters={'copy':self.adapter}
        self.empty=wishes.empty_state('1'*32)
        self.opts=dict(platform='x86_64-linux',executor=dict(provider='native',artifact='sha256:'+'f'*64),target_identity='sha256:'+'e'*64)
        self.refs={};self.candidates=[];self.offers=[]
        for version in ('2.12.1','2.12.3'):
            source=self.parent/('hello-'+version)
            source.write_text('#!/bin/sh\nprintf "'+version+'\\n"\n');source.chmod(0o555)
            sha=hashlib.sha256(source.read_bytes()).hexdigest()
            ref=dict(provider='copy',identity=dict(format='test-copy-v1',path=str(source),sha256=sha));self.refs[version]=ref
            self.candidates.append(dict(name='hello',release_id=version,upstream_version=version,version_scheme='dotted-v1',stability='stable',source='test',artifact=version,integrity=dict(sha256=sha),compatibility='verified'))
            self.offers.append(dict(backend='copy',artifact=version,integrity=dict(sha256=sha),reference=ref,dependencies=[],transport_sha256=None))
        self.sources=dict(local=dict(snapshot='sha256:'+'d'*64,catalogs=dict(hello=dict(format='mpm-release-catalog-v1',area='ports',name='hello',channel='stable',platform='x86_64-linux',sources=dict(test=dict(backend='copy',identity=dict(fixture='explicit'))),candidates=self.candidates)),offers=self.offers))

    def state(self,selector='hello@2.12',active=True):
        current=ports.current(self.root)
        before=current['record']['description']['requests'] if current else self.empty
        area=dict(source='local',packages=[selector])
        if active:area['active']={'hello':selector}
        return wishes.reconcile_configuration(before,dict(format=wishes.CONFIG,name='main',ports=area))
    def preview(self,state):return ports.preview(self.root,state,self.sources,self.adapters,**self.opts)
    def apply(self,state,**kwargs):return ports.apply(self.root,self.preview(state),self.sources,self.adapters,**self.opts,**kwargs)
    def output(self,name='hello'):return subprocess.check_output([str(self.root/'current/bin'/name)],text=True).strip()

    def test_preview_is_read_only_and_real_copy_publishes_executable_aliases(self):
        plan=self.preview(self.state())
        self.assertFalse(self.root.exists());self.assertEqual(self.adapter.fetches,0)
        ports.apply(self.root,plan,self.sources,self.adapters,**self.opts)
        self.assertEqual(self.output(),'2.12.3');self.assertEqual(self.output('hello-2.12'),'2.12.3')
        aliases=ports.current(self.root)['record']['description']['aliases']
        exact=[k for k in aliases if k.startswith('hello-2.12.3-')]
        self.assertEqual(len(exact),1);self.assertEqual(self.output(exact[0]),'2.12.3')
        self.assertEqual(len(ports.history(self.root)),1)

    def test_repeat_is_a_complete_noop_without_fetch_or_history(self):
        self.apply(self.state());before=os.readlink(self.root/'current');fetches=self.adapter.fetches
        result=self.apply(self.state())
        self.assertFalse(result['changed']);self.assertEqual(before,os.readlink(self.root/'current'))
        self.assertEqual(fetches,self.adapter.fetches);self.assertEqual(len(ports.history(self.root)),1)

    def test_upgrade_keeps_old_exact_alias_and_ownership(self):
        self.candidates[:]=self.candidates[:1];self.apply(self.state())
        oldaliases=ports.current(self.root)['record']['description']['aliases']
        old=next(k for k in oldaliases if k.startswith('hello-2.12.1-'))
        self.candidates.append(dict(name='hello',release_id='2.12.3',upstream_version='2.12.3',version_scheme='dotted-v1',stability='stable',source='test',artifact='2.12.3',integrity=self.offers[1]['integrity'],compatibility='verified'))
        self.sources['local']['snapshot']='sha256:'+'c'*64
        self.apply(self.state())
        self.assertEqual(self.output(),'2.12.3');self.assertEqual(self.output(old),'2.12.1')
        self.assertEqual(len(ports.current(self.root)['record']['description']['packages']),2)
        self.assertEqual([r['description']['sequence'] for r in ports.history(self.root)],[2,1])

    def test_interactive_override_and_reason_survive_configuration_removal(self):
        self.apply(self.state('hello@=2.12.1'))
        state=ports.current(self.root)['record']['description']['requests']
        state=wishes.request_interactively(state,'hello@=2.12.3','local');self.apply(state)
        self.assertEqual(self.output(),'2.12.1')
        state=ports.current(self.root)['record']['description']['requests']
        state=wishes.select_interactively(state,'hello',self.refs['2.12.3']);self.apply(state)
        state=wishes.reconcile_configuration(state,dict(format=wishes.CONFIG,name='main'))
        self.apply(state)
        self.assertEqual(self.output(),'2.12.3')
        packages=ports.current(self.root)['record']['description']['packages']
        self.assertEqual(len(packages),1);self.assertEqual(packages[0]['reference'],self.refs['2.12.3'])
        self.assertTrue((self.root/'profiles').is_dir())

    def test_configuration_only_removal_deactivates_without_deleting_content(self):
        self.apply(self.state());old=ports.current(self.root);target=old['record']['description']['aliases']['hello']
        state=wishes.reconcile_configuration(old['record']['description']['requests'],dict(format=wishes.CONFIG,name='main'))
        self.apply(state)
        self.assertFalse((self.root/'current/bin/hello').exists());self.assertTrue(Path(target).exists())
        self.assertTrue((self.root/old['path']).exists())

    def test_failure_and_late_verification_preserve_complete_old_profile(self):
        self.apply(self.state('hello@=2.12.1'));old=os.readlink(self.root/'current')
        state=self.state('hello@2.12');self.adapter.fail=True
        with self.assertRaises(ValueError):self.apply(state)
        self.assertEqual(os.readlink(self.root/'current'),old);self.assertEqual(self.output(),'2.12.1')
        self.adapter.fail=False;self.adapter.broken=True
        with self.assertRaises(ValueError):self.apply(state)
        self.assertEqual(os.readlink(self.root/'current'),old)

    def test_pre_and_post_publication_flush_failures_are_distinct(self):
        self.apply(self.state('hello@=2.12.1'));old=os.readlink(self.root/'current')
        def pre(path):
            if Path(path).name=='bin':raise OSError('pre')
            transaction.sync_directory(path)
        with self.assertRaises(OSError):self.apply(self.state('hello@2.12'),sync=pre)
        self.assertEqual(os.readlink(self.root/'current'),old)
        def post(path):
            if Path(path)==self.root:raise OSError('post')
            transaction.sync_directory(path)
        with self.assertRaises(transaction.PublicationUncertain):self.apply(self.state('hello@2.12'),sync=post)
        self.assertNotEqual(os.readlink(self.root/'current'),old);self.assertEqual(self.output(),'2.12.3')
        self.assertTrue((self.root/old).exists());self.assertEqual(len(ports.history(self.root)),2)

    def test_stale_preview_cannot_change_selection(self):
        self.apply(self.state('hello@=2.12.1'));plan=self.preview(self.state('hello@2.12'))
        self.apply(wishes.request_interactively(ports.current(self.root)['record']['description']['requests'],'hello@=2.12.1','local'))
        current=os.readlink(self.root/'current')
        with self.assertRaises(ValueError):ports.apply(self.root,plan,self.sources,self.adapters,**self.opts)
        self.assertEqual(os.readlink(self.root/'current'),current)

    def test_alias_tampering_and_unmanaged_or_symlink_roots_are_refused(self):
        self.apply(self.state());alias=self.root/'current/bin/hello';alias.unlink();alias.symlink_to('/bin/true')
        with self.assertRaises(ValueError):ports.current(self.root)
        link=self.parent/'link';link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):ports.current(link)

    def test_first_install_default_is_recorded_and_not_recreated_as_a_new_event(self):
        self.apply(self.state(active=False));state=ports.current(self.root)['record']['description']['requests']
        self.assertEqual(state['description']['selections'][0]['origin']['kind'],'configuration')
        self.assertFalse(self.apply(self.state(active=False))['changed'])

    def test_conflicting_or_reserved_exports_fail_before_acquisition(self):
        self.refs['2.12.3']['identity']['command']='mpm'
        with self.assertRaisesRegex(ValueError,'reserved management alias'):self.preview(self.state())
        self.assertFalse(self.root.exists());self.assertEqual(self.adapter.fetches,0)

    def test_actual_retained_byte_corruption_blocks_noop_verification(self):
        self.apply(self.state());old=os.readlink(self.root/'current')
        target=Path(ports.current(self.root)['record']['description']['aliases']['hello'])
        target.chmod(0o755);target.write_text('#!/bin/sh\nexit 0\n')
        with self.assertRaisesRegex(ValueError,'wrong copied bytes'):self.apply(self.state())
        self.assertEqual(os.readlink(self.root/'current'),old)
        self.assertEqual(len(ports.history(self.root)),1)

    def test_history_checks_parent_content_identity(self):
        self.apply(self.state('hello@=2.12.1'));self.apply(self.state('hello@2.12'))
        old=ports.history(self.root)[1];directory=self.root/old['description']['profile']
        state=ports.read(directory/'state.json');state['description']['event_sequence']+=1
        state=planning.record(ports.PROFILE,state['description'])
        old['description']['after']=state['id'];old=planning.record(ports.HISTORY,old['description'])
        for name,value in (('state.json',state),('transaction.json',old)):
            (directory/name).unlink();ports.write(directory/name,value)
        with self.assertRaisesRegex(ValueError,'parent identity'):ports.history(self.root)

    def test_ambiguous_first_install_requires_explicit_choice(self):
        state=wishes.reconcile_configuration(self.empty,dict(format=wishes.CONFIG,name='main',ports=dict(source='local',packages=['hello@=2.12.1','hello@=2.12.3'])))
        with self.assertRaisesRegex(ValueError,'explicit active choice'):self.preview(state)
        self.assertFalse(self.root.exists());self.assertEqual(self.adapter.fetches,0)

    def test_dependencies_are_acquired_before_the_selected_output(self):
        self.offers[1]['dependencies']=[self.refs['2.12.1']]
        order=[];ensure=self.adapter.ensure
        def acquire(ref,root):order.append(ref);ensure(ref,root)
        self.adapter.ensure=acquire
        self.apply(self.state())
        self.assertEqual(order,[self.refs['2.12.1'],self.refs['2.12.3']])
        self.assertEqual(self.output(),'2.12.3')
        self.assertEqual(len(ports.current(self.root)['record']['description']['packages']),1)

    def test_removing_config_default_falls_back_to_independently_owned_version(self):
        self.apply(self.state('hello@=2.12.1'))
        state=ports.current(self.root)['record']['description']['requests']
        self.apply(wishes.request_interactively(state,'hello@=2.12.3','local'))
        self.assertEqual(self.output(),'2.12.1')
        state=ports.current(self.root)['record']['description']['requests']
        state=wishes.reconcile_configuration(state,dict(format=wishes.CONFIG,name='main'))
        self.apply(state)
        self.assertEqual(self.output(),'2.12.3')
        self.assertFalse(self.apply(state)['changed'])


if __name__=='__main__':unittest.main()
