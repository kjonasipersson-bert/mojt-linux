# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Kernel preparation boundaries; no real compiler/Nix build required."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

REPO=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,REPO/path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
kernel=load('kernel_build','tools/mojt-kernel-build.py')
env=load('kernel_environment','tools/mojt-build-env.py')


class KernelTests(unittest.TestCase):
    def test_source_lock_and_versioned_config_policy(self):
        plan=kernel.read_plan(REPO/'manifests/kernel-first-build.json')
        self.assertEqual(plan['source']['commit'],'f717995cb7dcd8998ab15516b8006aea09cfde0d')
        self.assertEqual(plan['version']+plan['localversion'],'6.12.107-mojt1')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config'
            lines=['CONFIG_'+x+'=y' for x in plan['configuration']['enable']]
            lines += ['# CONFIG_'+x+' is not set' for x in plan['configuration']['disable']]
            lines += ['CONFIG_'+k+'='+json.dumps(v) for k,v in dict(plan['configuration']['strings'],LOCALVERSION=plan['localversion']).items()]
            path.write_text('\n'.join(lines)+'\n');kernel.check_config(path,plan)
            path.write_text(path.read_text().replace('CONFIG_EXT4_FS=y','CONFIG_EXT4_FS=m'))
            with self.assertRaisesRegex(ValueError,'EXT4_FS'):kernel.check_config(path,plan)

    def test_make_uses_private_host_compiler_shell_and_out_of_tree_paths(self):
        command=kernel.make_command(Path('/private/source'),Path('/private/objects'),Path('/tools'),2,'INSTALL_MOD_PATH=/private/root','modules_install')
        self.assertIn('O=/private/objects',command)
        self.assertIn('HOSTCC=/tools/bin/gcc',command)
        self.assertIn('CONFIG_SHELL=/tools/bin/bash',command)
        self.assertIn('LD=/tools/bin/ld',command)
        self.assertIn('INSTALL_MOD_PATH=/private/root',command)
        self.assertNotIn('install',command)

    def test_kernel_environment_selects_dev_and_lib_outputs_without_changing_image_tools(self):
        self.assertEqual(env.ROLES['binutils'][1],['readelf'])
        self.assertNotIn('compiler',env.ROLES)
        self.assertIn('gcc',env.KERNEL_ROLES['compiler'][1])
        self.assertIn('ld',env.KERNEL_ROLES['binutils'][1])
        self.assertEqual(env.OUTPUT_SELECTION['elf-dev'],'dev')
        self.assertEqual(env.OUTPUT_SELECTION['crypto-lib'],'lib')
        self.assertIn('pkgs.lib.getDev p',env.EXPRESSION)
        self.assertIn('pkgs.lib.getLib p',env.EXPRESSION)
        launcher=env.launcher(Path('/pinned/busybox'),Path('/new/env'),'/pinned/cert',{'PKG_CONFIG_LIBDIR':'/elf-dev/lib/pkgconfig:/crypto-dev/lib/pkgconfig'})
        self.assertIn('PKG_CONFIG_LIBDIR=',launcher)
        self.assertNotIn('LD_LIBRARY_PATH',launcher)

    def test_compiler_probe_compiles_links_runs_and_audits_library_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            calls=[]
            def execute(args,environment):
                calls.append(list(map(str,args)))
                if '--cflags' in args:return '-I/pinned/include -L/pinned/lib -lelf -lcrypto'
                if '-o' in args:Path(args[args.index('-o')+1]).write_bytes(b'ELF result')
                return 'probe/version output'
            with mock.patch.object(env,'execute',side_effect=execute),mock.patch.object(env,'audit_program',return_value={'kind':'dynamic-elf'}) as audit:
                result=env.compiler_probe(root,Path('/pinned/readelf'),['/pinned'],{})
            self.assertEqual(result['elf']['kind'],'dynamic-elf')
            self.assertIn('-lelf',result['flags']);self.assertEqual(len(result['binary_sha256']),64)
            self.assertTrue(any('-o' in c for c in calls));self.assertTrue(audit.call_args.kwargs['allow_build_output'])
            self.assertEqual(audit.call_args.args[2],['/pinned'])

    def test_dry_run_never_fetches_or_creates_outputs_and_refuses_wrong_config_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);environment=root/'env';(environment/'bin').mkdir(parents=True)
            for name in ['make','bash','gcc','g++','ld','as','ar','nm','objcopy','objdump','strip','depmod','modinfo','git','bc','flex','bison','perl','pkg-config','gzip']:
                (environment/'bin'/name).write_text('tool')
            (environment/'environment.json').write_text(json.dumps(dict(format='mojt-build-env-v1',profile='kernel',probes={'compiler':{}})))
            config=root/'debian.config';config.write_text('CONFIG_X86_64=y\n')
            args=types.SimpleNamespace(plan=REPO/'manifests/kernel-first-build.json',config=config,config_sha256=kernel.sha(config),environment=environment,output=root/'new',jobs=2,dry_run=True,yes=False)
            with mock.patch.object(kernel.subprocess,'run',side_effect=AssertionError('executed command')):
                kernel.build(args)
                self.assertFalse(args.output.exists())
                args.config_sha256='0'*64
                with self.assertRaisesRegex(ValueError,'hash differs'):kernel.build(args)
            self.assertFalse(args.output.exists())

    def test_unknown_or_conflicting_policy_fails_before_build(self):
        original=json.loads((REPO/'manifests/kernel-first-build.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'plan.json'
            for mutate in (lambda x:x.update(format='future'),lambda x:x['configuration']['disable'].append('X86_64'),lambda x:x['source'].update(commit='branch-name')):
                value=copy.deepcopy(original);mutate(value);p.write_text(json.dumps(value))
                with self.assertRaises(ValueError):kernel.read_plan(p)


    def test_full_command_sequence_stages_versioned_pair_and_tag_mismatch_stops_early(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);environment=root/'env';(environment/'bin').mkdir(parents=True)
            for name in ['make','bash','gcc','g++','ld','as','ar','nm','objcopy','objdump','strip','depmod','modinfo','git','bc','flex','bison','perl','pkg-config','gzip']:
                (environment/'bin'/name).write_text('tool')
            (environment/'environment.json').write_text(json.dumps(dict(format='mojt-build-env-v1',profile='kernel',probes={'compiler':{}})))
            config=root/'debian.config';config.write_text('CONFIG_X86_64=y\n')
            args=types.SimpleNamespace(plan=REPO/'manifests/kernel-first-build.json',config=config,config_sha256=kernel.sha(config),environment=environment,output=root/'build',jobs=2,dry_run=False,yes=True)
            plan=kernel.read_plan(args.plan);calls=[];release=plan['version']+plan['localversion']
            def run(command,**kwargs):
                self.assertEqual(command[0],str(environment/'run'));calls.append(command)
                name=Path(command[1]).name;stdout=''
                if name=='git' and 'rev-parse' in command:stdout=plan['source']['commit']
                if name=='make':
                    if 'olddefconfig' in command:
                        text=['CONFIG_'+x+'=y' for x in plan['configuration']['enable']]
                        text+=['CONFIG_'+k+'='+json.dumps(v) for k,v in dict(plan['configuration']['strings'],LOCALVERSION=plan['localversion']).items()]
                        (args.output/'objects/.config').write_text('\n'.join(text)+'\n')
                    if 'kernelrelease' in command:stdout=release
                    if 'bzImage' in command:
                        p=args.output/'objects/arch/x86/boot/bzImage';p.parent.mkdir(parents=True);p.write_bytes(b'kernel')
                        (args.output/'objects/System.map').write_text('map')
                    if 'modules_install' in command:
                        modules=args.output/'root/lib/modules'/release;modules.mkdir(parents=True)
                        (modules/'modules.dep').write_text('dependencies')
                        (modules/'example.ko').write_bytes(b'module')
                        (modules/'build').symlink_to(args.output/'objects')
                if name=='modinfo':stdout=release+' SMP mod_unload'
                return types.SimpleNamespace(stdout=stdout)
            with mock.patch.object(kernel.subprocess,'run',side_effect=run):kernel.build(args)
            result=json.loads((args.output/'kernel.json').read_text())
            self.assertEqual(result['release'],release);self.assertEqual(result['module_count'],1)
            self.assertIn('boot/vmlinuz-'+release,result['files'])
            self.assertIn('lib/modules/'+release+'/example.ko',result['files'])
            self.assertFalse((args.output/'.building').exists())
            self.assertFalse((args.output/'root/lib/modules'/release/'build').exists())
            self.assertEqual(kernel.sha(config),args.config_sha256)
            self.assertTrue(any('INSTALL_MOD_PATH='+str(args.output/'root') in c for c in calls))
            args.output=root/'bad-source';calls.clear()
            def wrong(command,**kwargs):
                if 'rev-parse' in command:return types.SimpleNamespace(stdout='0'*40)
                return run(command,**kwargs)
            with mock.patch.object(kernel.subprocess,'run',side_effect=wrong),self.assertRaisesRegex(ValueError,'source commit differs'):kernel.build(args)
            self.assertTrue((args.output/'.building').exists())
            self.assertFalse((args.output/'kernel.json').exists())
            self.assertFalse(any(Path(c[1]).name=='make' for c in calls))


if __name__=='__main__':unittest.main()
