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


if __name__=='__main__':unittest.main()
