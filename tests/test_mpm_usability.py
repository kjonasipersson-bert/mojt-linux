# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Public preparation boundary, readable metadata and atomic manual repair."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import mpm_system_cli as cli
import mpm_boot_update as update
import mpm_boot_selection as selection
import mpm_ui as ui
import mpm_man as manuals
import mpm_ports_profile as profiles
import test_mpm_boot_v2 as boot
import test_mpm_ports_profile as ports


class Installation(unittest.TestCase):
    def call(self,*flags,content=None,failure=None,live=True):
        runtime=SimpleNamespace(disk=Path('/fixture'),helpers=Path('/helpers')) if live else None
        out,err=io.StringIO(),io.StringIO()
        with mock.patch.object(cli.os.path,'ismount',return_value=True), \
             mock.patch.object(cli.system,'install',return_value=content or dict(changed=True)) as install, \
             mock.patch.object(selection,'present',return_value=True), \
             mock.patch.object(update,'stage',return_value=dict(changed=True,deployment='prepared'),side_effect=failure) as stage, \
             contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=cli.main(['install','--from-file','/generation','--expected-id','sha256:'+'1'*64,'-y','--json',*flags],runtime=runtime)
        return code,json.loads(out.getvalue()) if out.getvalue() else None,err.getvalue(),install,stage

    def test_live_install_prepares_without_selection_and_json_is_clean(self):
        code,result,err,install,stage=self.call('--verify')
        self.assertEqual(code,0);self.assertTrue(result['prepared']);self.assertFalse(result['selection_changed'])
        self.assertTrue(stage.call_args.kwargs['verify']);self.assertTrue(install.call_args.kwargs['verify'])
        self.assertIn('Install System content: done',err);self.assertIn('Prepare installed System for boot: done',err)
        # Retrying content already present must still repair missing preparation.
        self.assertTrue(self.call(content=dict(changed=False))[1]['prepared'])

    def test_content_only_offline_dry_run_and_cancel_do_not_prepare(self):
        for flags,content in [(('--content-only',),None),(('--disk-root','/offline'),None),(('--dry-run',),None),((),dict(changed=False,cancelled=True))]:
            with self.subTest(flags=flags,content=content):
                code,result,err,install,stage=self.call(*flags,content=content)
                self.assertEqual(code,0);stage.assert_not_called()

    def test_failure_reports_retained_content_without_claiming_boot_readiness(self):
        code,result,err,install,stage=self.call(failure=ValueError('injected preparation failure'))
        self.assertEqual(code,1);self.assertFalse(result['prepared']);self.assertTrue(result['changed'])
        self.assertFalse(result['selection_changed']);self.assertIn('next boot unchanged',err)
        self.assertIn('failed after',err)


class Presentation(unittest.TestCase):
    def test_preview_distinguishes_same_name_builds_and_reboot_state(self):
        before=boot.bound(boot.fixture());data=copy.deepcopy(before['description']['inputs']['description'])
        data['system']['artifact']='sha256:'+'9'*64
        after=boot.bound(selection.model.record(selection.model.INPUTS,data));err=io.StringIO()
        with contextlib.redirect_stderr(err):ui.preview(Path('/disk'),before,after,running=before)
        value=err.getvalue();self.assertIn('Base: '+data['base']['release']+' (unchanged)',value)
        self.assertIn(' -> ',value);self.assertIn('required to run',value)
        with contextlib.redirect_stderr(err:=io.StringIO()):ui.preview(Path('/disk'),after,before,running=before)
        self.assertIn('not needed; already running',err.getvalue())

    def test_prepared_choice_filters_other_base_and_cancels_without_publication(self):
        before=boot.bound(boot.fixture());data=copy.deepcopy(before['description']['inputs']['description'])
        data['base']['artifact']='sha256:'+'9'*64;data['system']['generation']='wrong-base'
        other=boot.bound(selection.model.record(selection.model.INPUTS,data))
        entries={r['id']:dict(record=r) for r in (before,other)};err=io.StringIO()
        with mock.patch.object(selection,'selected',return_value=(dict(description=dict(selected=before['id'])),entries,b'')), \
             mock.patch.object(selection,'summaries',return_value=(entries,[])), \
             mock.patch.object(update.system,'status',return_value=dict(installed=[])), \
             mock.patch('builtins.input',return_value='q'),contextlib.redirect_stderr(err), \
             self.assertRaisesRegex(ValueError,'cancelled'):
            update.choose_artifact(Path('/fixture'),'system',prepared=True)
        self.assertNotIn('wrong-base',err.getvalue())


class ManualRepair(ports.ProfileTests):
    def test_repair_adds_dependency_without_changing_binary_requests_or_activation(self):
        self.apply(self.state('hello@=2.12.1'));old=profiles.current(self.root)['record']['description']
        doc=copy.deepcopy(self.refs['2.12.3']);doc['identity']['command']='documentation-fixture'
        self.offers[0]['dependencies']=[doc]
        offer=copy.deepcopy(self.offers[1]);offer['reference']=doc;offer['artifact']='documentation';self.offers.append(offer)
        self.sources['local']['snapshot']='sha256:'+'a'*64
        self.adapter.documentation=lambda ref,source,role:dict(references=[doc],program='hello')
        state=old['requests'];keys=[r['key'] for r in state['description']['claims']]
        plan=profiles.preview(self.root,state,self.sources,self.adapters,refresh_dependencies=keys,**self.opts)
        profiles.apply(self.root,plan,self.sources,self.adapters,**self.opts)
        new=profiles.current(self.root)['record']['description'];a,b=old['packages'][0],new['packages'][0]
        for name in ('reference','installed','activated','release_id','commands'):self.assertEqual(a[name],b[name])
        self.assertEqual(old['requests'],new['requests']);self.assertEqual(old['active'],new['active'])
        self.assertEqual(b['manuals'],[doc]);self.assertNotIn('documentation-fixture',new['aliases'])
        # A later repeat uses accepted metadata, performs no further publication.
        self.assertFalse(self.apply(state)['changed'])

    def test_failed_manual_acquisition_retains_previous_profile(self):
        self.apply(self.state('hello@=2.12.1'));before=os.readlink(self.root/'current')
        doc=copy.deepcopy(self.refs['2.12.3']);self.offers[0]['dependencies']=[doc]
        self.adapter.fail=True;state=self.state('hello@=2.12.1')
        plan=profiles.preview(self.root,state,self.sources,self.adapters,refresh_dependencies=[r['key'] for r in state['description']['claims']],**self.opts)
        with self.assertRaisesRegex(ValueError,'acquisition failure'):profiles.apply(self.root,plan,self.sources,self.adapters,**self.opts)
        self.assertEqual(os.readlink(self.root/'current'),before);self.assertEqual(self.output(),'2.12.1')


class ManualReader(unittest.TestCase):
    def test_wrapper_dynamic_search_alias_and_argument_forwarding(self):
        program='/nix/store/'+'0'*32+'-man-db/bin/man';calls=[]
        def execute(*args):calls.append(args);raise SystemExit(0)
        with mock.patch.object(manuals,'manual_paths',return_value=(['/exact/share/man'],{'neovim':'nvim'})), \
             mock.patch.dict(os.environ,{'MANPATH':'/local/man:'},clear=True):
            for args,expected in [(['-w','neovim'],['-w','nvim']),(['1','neovim'],['1','nvim']),(['-M','/override','neovim'],['-M','/override','neovim'])]:
                with self.assertRaises(SystemExit):manuals.main([program,*args],execute=execute)
                self.assertEqual(calls[-1][1],[program,*expected]);self.assertEqual(calls[-1][2]['MANPATH'],'/exact/share/man:/local/man:')
        self.assertIn(' -I -B ',manuals.wrapper(program))
        with self.assertRaises(ValueError):manuals.wrapper('/tmp/man')

    def test_only_active_exact_manuals_are_searched_and_escape_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);active=base/'active';inactive=base/'inactive';doc=base/'doc'
            for p in (active,inactive,doc):(p/'share/man').mkdir(parents=True)
            def ref(path):return dict(provider='nix',identity=dict(output=str(path),closure=[dict(path=str(path))]))
            a,b,d=map(ref,(active,inactive,doc))
            packages=[dict(reference=a,commands={'nvim':'ignored'},manuals=[d],manual_program='nvim'),dict(reference=b,commands={})]
            description=dict(active=dict(neovim=a),packages=packages,objects=[dict(reference=r) for r in (a,b,d)])
            with mock.patch.object(profiles,'current',return_value=dict(record=dict(description=description))), \
                 mock.patch('mpm_nix_binary.NixBinaryAdapter.identity',side_effect=lambda r:r['identity']):
                paths,aliases=manuals.manual_paths(base)
                self.assertEqual(paths,[str(active/'share/man'),str(doc/'share/man')]);self.assertEqual(aliases,{'neovim':'nvim'})
                # A dependency manual must not outrank a directly active output.
                a['identity']['closure'].append(dict(path=str(inactive)))
                d['identity']['closure'].append(dict(path=str(inactive)))
                paths,_=manuals.manual_paths(base)
                self.assertEqual(paths,[str(active/'share/man'),str(doc/'share/man'),str(inactive/'share/man')])
                a['identity']['closure'].pop();d['identity']['closure'].pop()
                (doc/'share/man').rmdir();(doc/'share/man').symlink_to(inactive/'share/man')
                with self.assertRaisesRegex(ValueError,'escapes'):manuals.manual_paths(base)


if __name__=='__main__':unittest.main()
