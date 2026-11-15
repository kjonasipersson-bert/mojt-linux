# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Diagnostic observers preserve stage behavior, constructor identity and errors."""
from contextlib import redirect_stderr, redirect_stdout
import copy
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

TOOLS=Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
spec=importlib.util.spec_from_file_location('stage_profile',TOOLS/'mojt-stage-profile.py')
profile=importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)


class TimingTests(unittest.TestCase):
    def test_nested_own_time_subtracts_children_without_double_counting(self):
        module=SimpleNamespace(__name__='fixture')
        module.child=lambda: 'unchanged result'
        module.parent=lambda: module.child()
        original_parent=module.parent;original_child=module.child
        timings=profile.Timings()
        with mock.patch.object(profile,'clock',side_effect=[(0,0,0),(10,2,0),(40,8,4),(100,20,10)]), \
             redirect_stderr(io.StringIO()):
            with timings.observe(module,'parent',phase=True),timings.observe(module,'child',phase=True):
                self.assertEqual(module.parent(),'unchanged result')
        parent=timings.calls['fixture.parent'];child=timings.calls['fixture.child']
        self.assertEqual((parent['wall_ns'],parent['own_wall_ns'],child['wall_ns']),(100,70,30))
        self.assertEqual((parent['own_python_cpu_ns'],parent['own_child_cpu_ns']),(14,6))
        self.assertEqual(sum(row['own_wall_ns'] for row in timings.calls.values()),100)
        rows=sorted(timings.phases,key=lambda row:row['id'])
        self.assertEqual(rows[1]['parent'],rows[0]['id'])
        self.assertIs(module.parent,original_parent);self.assertIs(module.child,original_child)

    def test_real_inventory_and_tamper_refusal_are_unchanged_and_restored(self):
        import mpm_boot_inventory as inventory
        timings=profile.Timings();measure=inventory.measure
        with tempfile.TemporaryDirectory() as temporary:
            tree=Path(temporary);(tree/'file').write_bytes(b'original')
            expected=inventory.measure(tree)
            with timings.observe(inventory,'measure',tree=True):
                inventory.verify(tree,expected)
                (tree/'file').write_bytes(b'tampered')
                with self.assertRaisesRegex(ValueError,'immutable tree differs'):inventory.verify(tree,expected)
            self.assertIs(inventory.measure,measure)
            self.assertEqual(timings.calls['mpm_boot_inventory.measure']['calls'],2)
            self.assertEqual([row['nodes'] for row in timings.trees],[2,2])
            self.assertTrue(all(row['path']==str(tree) for row in timings.trees))

    def test_failed_call_propagates_same_exception_and_closes_stack(self):
        failure=ValueError('original refusal')
        def fail():raise failure
        module=SimpleNamespace(__name__='fixture',fail=fail);timings=profile.Timings()
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(ValueError) as error:
                with timings.observe(module,'fail',phase=True):module.fail()
        self.assertIs(error.exception,failure);self.assertIs(module.fail,fail)
        self.assertEqual(timings.stack,[]);self.assertFalse(timings.phases[0]['ok'])
        self.assertEqual(timings.calls['fixture.fail']['failed'],1)


class RunnerTests(unittest.TestCase):
    def test_provider_subprocess_arguments_and_results_are_preserved_and_grouped(self):
        import mpm_nix_binary as nix
        adapter=nix.NixBinaryAdapter(sys.executable);timings=profile.Timings();original=nix.NixBinaryAdapter._run
        commands=[[sys.executable,'--query','--requisites','output'],
                  [sys.executable,'--query','--hash','output'],[sys.executable,'--verify-path','output']]
        with mock.patch.object(nix.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=' result\n')) as run:
            with timings.observe(nix.NixBinaryAdapter,'_run'):
                for command in commands:self.assertEqual(adapter._run(command),'result')
        self.assertEqual([call.args[0] for call in run.call_args_list],commands)
        self.assertEqual(set(timings.processes),{'--query --requisites','--query --hash','--verify-path'})
        self.assertEqual(sum(row['calls'] for row in timings.processes.values()),3)
        self.assertIs(nix.NixBinaryAdapter._run,original)

    def test_real_installed_launcher_dispatches_stage_and_restores_all_observers(self):
        import mpm_boot_update as update
        import mpm_boot_constructor as constructor
        import mpm_boot_inventory as inventory
        import mpm_cli as cli
        import mojt_artifact as artifact
        import test_mpm_boot_payload as fixtures
        runtime=fixtures.runtime();busybox=TOOLS/'mpm-system'
        identity=constructor.constructor(runtime,busybox,handover=True)
        source=fixtures.source();key=constructor.payload_key(source,runtime,handover=True)
        original_canonical=artifact.canonical;original_stage=update.stage;original_main=cli.main
        original_measure=inventory.measure;timings=profile.Timings()
        result=dict(changed=True,deployment='exact-slot',initramfs_payload=dict(inputs='payload',reused=True))
        seen=[]
        def stage(*args,**kwargs):
            seen.append((args,kwargs))
            self.assertEqual(constructor.constructor(runtime,busybox,handover=True),identity)
            self.assertEqual(constructor.payload_key(source,runtime,handover=True),key)
            return result
        stdout=io.StringIO();argv=sys.argv;path=sys.path[:]
        command=['system','stage','--artifact','sha256:'+'1'*64,'-y','--json']
        with mock.patch.object(update.selection,'present',return_value=True), \
             mock.patch.object(cli.os,'geteuid',return_value=0), \
             mock.patch.object(update.os.path,'ismount',return_value=True), \
             mock.patch.object(cli,'require_codec'),mock.patch.object(update,'stage',side_effect=stage), \
             redirect_stderr(io.StringIO()):
            self.assertEqual(profile.run_mpm(TOOLS,command,timings,stdout),0)
        import json
        self.assertEqual(json.loads(stdout.getvalue()),result)
        self.assertEqual(seen[0][0][1:],('system','sha256:'+'1'*64))
        self.assertTrue(seen[0][1]['yes']);self.assertFalse(seen[0][1]['dry_run'])
        self.assertEqual(timings.calls['mpm_cli.main']['calls'],1)
        self.assertEqual(timings.calls['mpm_boot_update.stage']['calls'],1)
        self.assertIs(artifact.canonical,original_canonical);self.assertIs(update.stage,original_stage)
        self.assertIs(inventory.measure,original_measure);self.assertIs(cli.main,original_main)
        self.assertIs(sys.argv,argv);self.assertEqual(sys.path,path)

    def test_stage_failure_keeps_mpm_exit_status_and_restores_functions(self):
        import mpm_boot_update as update
        import mpm_cli as cli
        stage=update.stage;main=cli.main;timings=profile.Timings()
        with mock.patch.object(update.selection,'present',return_value=True), \
             mock.patch.object(cli.os,'geteuid',return_value=0), \
             mock.patch.object(update.os.path,'ismount',return_value=True),mock.patch.object(cli,'require_codec'), \
             mock.patch.object(update,'stage',side_effect=ValueError('retained bytes damaged')), \
             redirect_stderr(io.StringIO()) as stderr:
            code=profile.run_mpm(TOOLS,['system','stage','--artifact','sha256:'+'1'*64,'-y','--json'],timings,io.StringIO())
        self.assertEqual(code,1);self.assertIn('retained bytes damaged',stderr.getvalue())
        self.assertIs(update.stage,stage);self.assertIs(cli.main,main)
        self.assertEqual(timings.calls['mpm_boot_update.stage']['failed'],1)

    def test_default_candidate_is_retained_e_and_requires_accepted_f_context(self):
        before=dict(inputs=dict(system=dict(artifact='F'),**{key:key for key in profile.AREAS}))
        saved=dict(format='mojt-initramfs-payload-test-55-v1',probe=dict(artifact='F'),
                   candidate=dict(artifact='sha256:'+'1'*64),baseline=dict(preserved={key:key for key in profile.AREAS}))
        warm=dict(changed=True,initramfs_payload=dict(inputs='payload-key',reused=True))
        with mock.patch('mpm_transaction.protected_directory'),mock.patch('mpm_base.read',side_effect=lambda path:saved if path.name=='state.json' else warm):
            self.assertEqual(profile.candidate(before,None),('sha256:'+'1'*64,'payload-key'))
            changed=copy.deepcopy(before);changed['inputs']['kernel']='different'
            with self.assertRaisesRegex(ValueError,'context differs'):profile.candidate(changed,None)
            before['inputs']['system']['artifact']='foreign'
            with self.assertRaisesRegex(ValueError,'accepted F'):profile.candidate(before,None)


if __name__=='__main__':unittest.main()
