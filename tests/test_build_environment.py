# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pinned build-tool preparation and libc guard boundaries; no real Nix imports."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import types

REPO=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build_environment',REPO/'tools/mojt-build-env.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)


class BuildEnvironmentTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.output=self.root/'env';self.source=self.root/'source';self.source.mkdir()
        self.rows=[]
        for role,(attribute,commands) in build.ROLES.items():
            path=self.root/role;path.mkdir();(path/'bin').mkdir()
            for name in commands+(['busybox'] if role=='busybox' else []):
                p=path/'bin'/name;p.write_bytes(b'\x7fELFsynthetic');p.chmod(0o755)
            if role=='cacert':
                (path/'etc/ssl/certs').mkdir(parents=True)
                (path/'etc/ssl/certs/ca-bundle.crt').write_text('test-cert')
            self.rows.append(dict(role=role,attribute=attribute,output=str(path),version='test'))
        self.libc=self.root/'python/libc.so.6';self.libc.write_text('synthetic libc')
        self.calls=[]
        def run(*args):
            self.calls.append(args)
            if args[1:3]==('--query','--requisites'):
                return '\n'.join(str(p) for p in [self.source,*[Path(r['output']) for r in self.rows]])
            if args[1:3]==('--query','--hash'):return '\n'.join('hash:'+p for p in args[3:])
            return ''
        def retain(root,path):
            self.calls.append(('retain',str(root),path));(root/'gcroots'/Path(path).name).symlink_to(path)
        self.nix=types.SimpleNamespace(catalog_from_manifest=lambda p:dict(source=dict(system='x86_64-linux',store=str(self.source))),
            evaluate=lambda *a,**k:self.rows,store_path=lambda p:Path(p),run=run,retain=retain)
        self.args=types.SimpleNamespace(output=self.output,source_manifest=self.root/'pin.toml',dry_run=False,yes=True)
        self.patches=[mock.patch.dict(os.environ,{},clear=True),
            mock.patch.object(build,'audit_program',side_effect=lambda path,*a:dict(kind='static-elf' if Path(path).name=='busybox' else 'dynamic-elf')),
            mock.patch.object(build,'execute',side_effect=self.execute)]
        for patch in self.patches:patch.start();self.addCleanup(patch.stop)

    def execute(self,args,env):
        self.assertNotIn('LD_LIBRARY_PATH',env)
        if args[-1]=='--list':return 'sh\nenv\nswitch_root\nmount\nfindfs\ncp\nln'
        if '-c' in args:return json.dumps(dict(uid=0,user='root',maps='address perms offset dev inode '+str(self.libc)))
        return 'version test\n'

    def test_complete_environment_retains_final_roots_without_activation(self):
        build.prepare(self.args,self.nix)
        record=json.loads((self.output/'environment.json').read_text())
        self.assertFalse((self.output/'.preparing').exists())
        self.assertEqual(record['probes']['python-runtime']['verified_libraries'],[str(self.libc)])
        self.assertTrue((self.output/'bin/grub-mkstandalone').is_symlink())
        self.assertTrue((self.output/'run').read_text().startswith('#!'+str(self.root/'busybox/bin/busybox')+' sh'))
        self.assertIn('env -i',(self.output/'run').read_text())
        self.assertTrue(all(c[1]==str(self.output) for c in self.calls if c[0]=='retain'))
        self.assertFalse((self.root/'ports').exists())

    def test_preview_and_cancel_have_no_outputs_or_roots(self):
        self.args.dry_run=True;build.prepare(self.args,self.nix)
        self.assertFalse(self.output.exists());self.assertFalse(any(c[0]=='retain' for c in self.calls))
        self.args.dry_run=False;self.args.yes=False
        with mock.patch('builtins.input',return_value='n'):build.prepare(self.args,self.nix)
        self.assertFalse(self.output.exists())
        for c in self.calls:
            if '--realise' in c:
                self.assertIn('--dry-run',c);self.assertIn('max-jobs',c);self.assertIn('builders',c)

    def test_foreign_runtime_reference_blocks_completion_and_preserves_incomplete_lab(self):
        foreign=self.root/'foreign/libc.so.6';foreign.parent.mkdir();foreign.write_text('foreign')
        with mock.patch.object(build,'execute',side_effect=lambda args,env: json.dumps(dict(maps='a b c d e '+str(foreign)))
                               if '-c' in args else self.execute(args,env)):
            with self.assertRaisesRegex(ValueError,'outside pinned closure'):build.prepare(self.args,self.nix)
        self.assertTrue((self.output/'.preparing').exists())
        self.assertFalse((self.output/'run').exists());self.assertFalse((self.output/'environment.json').exists())

    def test_dynamic_busybox_and_missing_commands_fail_closed(self):
        with mock.patch.object(build,'audit_program',return_value=dict(kind='dynamic-elf')):
            with self.assertRaisesRegex(ValueError,'must be static'):build.prepare(self.args,self.nix)
        self.assertTrue((self.output/'.preparing').exists())
        with self.assertRaisesRegex(ValueError,'missing executable'):build.find_command(str(self.root),'missing')

    def test_clean_environment_drops_loader_python_locale_and_plugin_overrides(self):
        with mock.patch.dict(os.environ,dict(LD_PRELOAD='foreign',PYTHONPATH='foreign',LOCALE_ARCHIVE='foreign',GIO_EXTRA_MODULES='foreign')):
            env=build.clean_environment('/private/bin','/private/cert')
            self.assertEqual(env['PATH'],'/private/bin')
            self.assertEqual(env['LC_ALL'],'C')
            for key in ('LD_PRELOAD','PYTHONPATH','LOCALE_ARCHIVE','GIO_EXTRA_MODULES'):self.assertNotIn(key,env)
            with self.assertRaisesRegex(ValueError,'without LD_'):build.prepare(self.args,self.nix)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_not_adopted_or_modified(self):
        self.output.mkdir();(self.output/'data').write_text('keep')
        with self.assertRaisesRegex(ValueError,'must not exist'):build.prepare(self.args,self.nix)
        self.assertEqual((self.output/'data').read_text(),'keep')


class ElfBoundaryTests(unittest.TestCase):
    def test_elf_loader_resolution_records_exact_objects_and_rejects_missing_libraries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);binary=root/'tool';binary.write_bytes(b'\x7fELFfake')
            loader=root/'ld-linux.so.2';loader.write_text('loader')
            libc=root/'libc.so.6';libc.write_text('libc')
            def run(args,env):
                if '--program-headers' in args:return '[Requesting program interpreter: '+str(loader)+']'
                if '--dynamic' in args:return '(NEEDED) libc.so.6'
                return 'libc.so.6 => '+str(libc)+' (0x123)\n'+str(loader)+' (0x123)'
            with mock.patch.object(build,'execute',side_effect=run):
                report=build.audit_program(binary,'readelf',[str(root)],{})
            self.assertEqual(report['loader'],str(loader));self.assertEqual(report['libc'],[str(libc)])
            with mock.patch.object(build,'execute',side_effect=[ '[Requesting program interpreter: '+str(loader)+']', '(NEEDED)', 'libc.so.6 => not found']):
                with self.assertRaisesRegex(ValueError,'missing loader dependency'):build.audit_program(binary,'readelf',[str(root)],{})

    def test_scripts_with_base_interpreters_are_reported_as_boundary_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'script';path.write_text('#!/bin/sh\nexit 0\n')
            with self.assertRaisesRegex(ValueError,'non-store script interpreter'):build.audit_program(path,'readelf',[str(root)],{})


if __name__=='__main__':unittest.main()
