# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Adapter protocol checks; these do not claim a live Nix import."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from mpm_nix_binary import NixBinaryAdapter


class NixAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'retained').mkdir()
        self.output='/nix/store/'+'a'*32+'-hello-2.12.3'
        self.hash='sha256:'+'b'*52
        self.ref=dict(provider='nix',identity=dict(format='mojt-nix-output-v1',output=self.output,closure=[dict(path=self.output,nar_hash=self.hash)],commands=[]))
        self.calls=[];self.bad=False;self.corrupt=False
        self.adapter=NixBinaryAdapter('/pinned/nix/bin/nix-store',self.run_nix)

    def run_nix(self,args):
        self.calls.append(args)
        if '--realise' in args:
            root=Path(args[args.index('--add-root')+1]);root.symlink_to(self.output)
            return self.output
        if '--requisites' in args:return self.output+'-wrong' if self.bad else self.output
        if '--hash' in args:return self.hash
        if '--verify-path' in args:
            if self.corrupt:raise ValueError('content differs')
            return ''
        raise AssertionError(args)

    def test_readonly_description_and_binary_only_retention_protocol(self):
        self.assertEqual(self.adapter.describe(self.ref,self.root)['commands'],{})
        self.assertEqual(self.calls,[]);self.assertEqual(list((self.root/'retained').iterdir()),[])
        with mock.patch.object(Path,'is_dir',lambda p:str(p)==self.output):self.adapter.ensure(self.ref,self.root)
        args=self.calls[0]
        self.assertEqual(args[:3],['/pinned/nix/bin/nix-store','--realise',self.output])
        self.assertIn('--indirect',args)
        for option,value in (('max-jobs','0'),('builders',''),('require-sigs','true')):
            self.assertIn(['--option',option,value],[args[n:n+3] for n in range(len(args)-2)])
        self.assertTrue(any('--verify-path' in c for c in self.calls))
        self.assertEqual(os.readlink(self.root/'retained/nix'/Path(self.output).name),self.output)

    def test_wrong_closure_and_actual_content_verification_failure_are_refused(self):
        directory=self.root/'retained/nix';directory.mkdir();(directory/Path(self.output).name).symlink_to(self.output)
        with mock.patch.object(Path,'is_dir',lambda p:str(p)==self.output):
            self.bad=True
            with self.assertRaisesRegex(ValueError,'closure differs'):self.adapter.verify(self.ref,self.root)
            self.bad=False;self.corrupt=True
            with self.assertRaisesRegex(ValueError,'content differs'):self.adapter.verify(self.ref,self.root)

    def test_derivations_unknown_formats_and_incomplete_closures_are_rejected(self):
        for change in ('derivation','format','closure','command'):
            ref=copy.deepcopy(self.ref);i=ref['identity']
            if change=='derivation':i['output']+='.drv'
            if change=='format':i['format']='future-v99'
            if change=='closure':i['closure']=[]
            if change=='command':i['commands']=['../escape']
            with self.subTest(change=change),self.assertRaises(ValueError):self.adapter.describe(ref,self.root)
        self.assertEqual(self.calls,[])

    def test_catalog_bundle_exports_exact_frontend_bindings_without_import(self):
        import importlib.util
        import types
        import mpm_selection as selection
        import mpm_request_plan as planning
        import mpm_ports_cli as frontend
        import mpm_requests as wishes
        spec=importlib.util.spec_from_file_location('bundle_export',Path(__file__).resolve().parents[1]/'tools/mpm-nix-catalog.py')
        exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
        backend=types.SimpleNamespace(selection_core=lambda:selection,require=wishes.require,discover_commands=lambda r:['hello'])
        catalog=dict(format=selection.FORMAT,area='ports',name='ports-main',channel='stable',platform='x86_64-linux',
            sources=dict(pinned=dict(backend='nix',identity=dict(revision='a'*40))),candidates=[dict(name='hello',release_id='2.12.3',
            upstream_version='2.12.3',version_scheme='dotted-v1',stability='stable',source='pinned',artifact=self.output,
            integrity=dict(closure=self.ref['identity']['closure']))])
        bundle=exporter.prepare_bundle(backend,catalog,'hello')
        view=frontend.source_bundle(bundle,'x86_64-linux')
        state=wishes.request_interactively(wishes.empty_state('1'*32),'hello','local')
        lock=planning.resolve_requests(state,view,platform='x86_64-linux')
        ref=lock['description']['resolutions'][0]['reference']
        self.assertEqual(ref['identity']['commands'],['hello'])
        self.assertEqual(ref['identity']['output'],self.output)
        self.assertEqual(ref['identity']['closure'],self.ref['identity']['closure'])
        self.assertEqual(self.calls,[])

    def test_real_symlink_keeps_argv0_and_pins_executable_for_both_frontends(self):
        import types
        import mpm_ports_cli as frontend
        directory=self.root/'helpers';directory.mkdir()
        alias=directory/'nix-store';alias.symlink_to('/bin/sh')
        sources={'local':{'offers':[{'reference':self.ref}]}}
        for installed in (False,True):
            alias.unlink();alias.symlink_to('/bin/sh')
            runtime=types.SimpleNamespace(system_bin=directory) if installed else None
            with self.subTest(installed=installed),mock.patch.object(frontend.shutil,'which',return_value=str(alias)):
                adapter=frontend.adapters_for(sources,None,runtime)['nix']
                self.assertEqual(adapter.binary,str(alias))
                self.assertEqual(adapter.executable,str(Path('/bin/sh').resolve()))
                # A real executable reports its invocation name through $0;
                # this is not a mocked subprocess assertion.
                self.assertEqual(adapter.runner([adapter.binary,'-c','printf "%s" "$0"']),str(alias))
                alias.unlink();alias.symlink_to('/bin/false')
                self.assertEqual(adapter.runner([adapter.binary,'-c','printf "%s" "$0"']),str(alias))


if __name__=='__main__':unittest.main()
