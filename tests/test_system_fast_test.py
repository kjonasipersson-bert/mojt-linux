# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Successor delivery: real archives and installed-command evidence, no physical boot."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from test_mpm_system import Fixture, REPO, pack, spec, tree
from test_system_ports_repair import Provider
import mojt_artifact as artifact
import mpm_base as base
import mpm_system as system
import mpm_system_model as model

specification = importlib.util.spec_from_file_location('fast_delivery',REPO/'tools/mojt-system-fast-test.py')
delivery = importlib.util.module_from_spec(specification);specification.loader.exec_module(delivery)


@unittest.skipUnless(os.geteuid() == 0 and shutil.which('zstd'),'requires numeric-owner native installation and zstd')
class DeliveryTests(Fixture):
    def setUp(self):
        super().setUp()
        content = self.work/'component-source';(content/'version').write_text('system-activation-A\n')
        self.adapters = {'fixture':Provider()}
        provider = dict(provider='fixture',identity=dict(closure='unchanged-runtime'))
        packed = pack(content,spec('component',dependencies=[provider]),self.work/'baseline-runtime')
        self.reference = dict(provider='native',artifact=packed['artifact']['id'])
        self.component_archive = self.work/'baseline-runtime'/packed['archive']['file']
        d = copy.deepcopy(self.composition['description']);d['components'][0]['reference'] = self.reference
        for row in d['profile']:row['source']['reference'] = self.reference
        d['profile'].append(dict(path='version',source=dict(reference=self.reference,path='version')))
        d['profile'].sort(key=lambda row:row['path']);self.composition = base.record(model.FORMAT,d)
        self.archive,self.body = self.package(self.composition,self.actions);self.install(adapters=self.adapters)
        self.downloads = {name:(REPO/name).read_bytes() for name in delivery.FILES}
        self.enterContext(mock.patch.object(delivery,'FILES',{name:hashlib.sha256(data).hexdigest() for name,data in self.downloads.items()}))

    def test_successor_generations_deliver_all_changed_tools_and_preserve_provider_and_original(self):
        before = tree(self.root)
        c = delivery.package(self.root,self.body['id'],self.downloads,self.work/'C')
        d = delivery.package(self.root,self.body['id'],self.downloads,self.work/'D',label=delivery.PROBE_LABEL,revision=2)
        self.assertNotEqual(c['artifact'],d['artifact']);self.assertEqual(tree(self.root),before)
        for name,row in (('C',c),('D',d)):
            kit = self.work/name
            body = artifact.verify(kit/row['component'])
            self.assertEqual(body['dependencies'],system.object_record(self.root,self.reference['artifact'])[0]['dependencies'])
            system.install(self.root,kit/row['generation'],row['artifact'],dependency_files=[kit/row['component']],adapters=self.adapters,yes=True)
            profile = system.realization_path(self.root,row['artifact'])/'profile'
            self.assertEqual((profile/'version').read_text().strip(),row['label'])
            for path,expected in delivery.FILES.items():
                target = profile/path if path.startswith('tools/') else profile/'share/man/man1/mpm.1'
                self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),expected)
            system.realization(self.root,row['artifact'],verify=True)
        self.assertFalse((self.root/'boot').exists());self.assertFalse(self.marker.exists())

    def test_damaged_download_cannot_publish_successor_packages(self):
        self.downloads['tools/mpm_system.py'] += b'changed'
        before = tree(self.root)
        with self.assertRaisesRegex(ValueError,'pinned data'):
            delivery.package(self.root,self.body['id'],self.downloads,self.work/'bad')
        self.assertEqual(tree(self.root),before);self.assertFalse((self.work/'bad').exists())


class Boundaries(unittest.TestCase):
    def test_baseline_accepts_original_test_ssd_and_refuses_installer_or_pending_selection(self):
        snap = dict(selected='old',status=dict(running=dict(label='system-activation-A',deployment='old')))
        with mock.patch.object(delivery,'snapshot',return_value=snap):
            self.assertEqual(delivery.baseline(),snap)
            snap['status']['running']['label'] = 'system-usb-installer'
            with self.assertRaisesRegex(ValueError,'SSD'):delivery.baseline()
            snap['status']['running']['label'] = 'system-activation-A';snap['selected'] = 'pending'
            with self.assertRaisesRegex(ValueError,'pending'):delivery.baseline()

    def test_bootstrap_runs_only_c_through_separate_public_install_stage_and_select(self):
        before = dict(selected='old',selection='menu-old',status=dict(running=dict(artifact='old',label='system-activation-A')))
        state = dict(baseline=before,candidate=dict(artifact='C',label=delivery.LABEL,generation='generation/C',component='component/C'))
        calls = []
        def run(name,*args,**kwargs):
            calls.append((name,args));return dict(result=dict(deployment='C-slot'))
        after = dict(selected='C-slot')
        with mock.patch.object(delivery,'baseline',return_value=before), \
             mock.patch.object(delivery,'snapshot',return_value=before), \
             mock.patch.object(delivery,'confirm'),mock.patch.object(delivery,'unchanged'), \
             mock.patch.object(delivery,'check',return_value=after),mock.patch.object(delivery,'save'), \
             mock.patch.object(delivery,'run',side_effect=run),contextlib.redirect_stdout(io.StringIO()):
            delivery.enter(state)
        self.assertEqual([args[1][1] for args in calls],['install','stage','select'])
        self.assertTrue(all('--verify' not in args[1] for args in calls))
        self.assertIn('C-slot',calls[-1][1]);self.assertIn('old',calls[-1][1]);self.assertNotIn('reboot',str(calls))
        with mock.patch.object(delivery,'baseline',return_value=dict(before,selected='changed')), \
             mock.patch.object(delivery,'run') as run, self.assertRaisesRegex(ValueError,'baseline changed'):
            delivery.enter(state)
        run.assert_not_called()

    def test_cancellation_rejects_unrelated_failure_even_when_boot_is_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary);(work/'cancel.log').write_text('unrelated MPM failure\n')
            with mock.patch.object(delivery,'WORK',work),mock.patch.object(delivery,'check',return_value={}), \
                 mock.patch.object(delivery,'tools_match'),mock.patch.object(delivery,'unchanged'), \
                 mock.patch.object(delivery.sys.stdin,'isatty',return_value=True), \
                 mock.patch.object(delivery,'run',return_value=dict(returncode=1)), \
                 contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'reprompt'):
                delivery.exercise('cancel',{})

    def test_wrong_manager_or_scope_blocks_before_any_measured_command(self):
        state = dict(baseline=dict(installation='one',preserved={'base':'B'}),candidate=dict(artifact='C',label='C'))
        snap = dict(installation='one',preserved={'base':'B'},selected='C-slot',
                    status=dict(running=dict(artifact='old',deployment='C-slot')))
        with mock.patch.object(delivery,'snapshot',return_value=snap):
            with self.assertRaisesRegex(ValueError,'boot C first'):delivery.check(state,'candidate')
            snap['installation'] = 'foreign'
            with self.assertRaisesRegex(ValueError,'differs from baseline'):delivery.check(state,'candidate')
        with mock.patch.object(delivery,'check',side_effect=ValueError('wrong running manager')), \
             mock.patch.object(delivery,'run') as run,self.assertRaisesRegex(ValueError,'wrong running'):
            delivery.exercise('install',state)
        run.assert_not_called()

    def test_measured_activation_uses_new_installed_mpm_after_preparation_without_verify(self):
        before = dict(selected='C-slot',status=dict(running={'artifact':'C'}));after = dict(selected='D-slot',status=dict(running={'artifact':'C'}))
        state = dict(probe=dict(artifact='D',label='D'))
        with mock.patch.object(delivery,'check',side_effect=[before,after]), \
             mock.patch.object(delivery,'tools_match'),mock.patch.object(delivery,'confirm'), \
             mock.patch.object(delivery,'read',return_value=dict(deployment='D-slot')), \
             mock.patch.object(delivery,'snapshot',return_value=after),mock.patch.object(delivery,'save'), \
             mock.patch.object(delivery,'run',return_value=dict(result=dict(selected='D-slot'))) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            delivery.exercise('activate',state)
        self.assertEqual(run.call_args.args,('activate','system','activate','--artifact','D','--expected-selected','C-slot','-y','--json'))
        self.assertEqual(run.call_args.kwargs['before'],before)

    def test_cached_content_is_not_reported_as_a_fresh_performance_sample(self):
        state = dict(probe=dict(artifact='D'))
        before = dict(status=dict(installed=[dict(artifact='D')],staged_deployments=[dict(artifact='D')]))
        with mock.patch.object(delivery,'check',return_value=before), \
             mock.patch.object(delivery,'tools_match'),mock.patch.object(delivery,'run') as run:
            for action in ('install','stage'):
                with self.subTest(action=action),self.assertRaisesRegex(ValueError,'already'):
                    delivery.exercise(action,state)
            run.assert_not_called()

    def test_missing_running_mount_or_unprivileged_user_cannot_prepare_files(self):
        with mock.patch.object(delivery.os,'geteuid',return_value=1000), \
             mock.patch.object(delivery,'fetch') as fetch,self.assertRaisesRegex(ValueError,'installed Mojt'):
            delivery.main(['prepare'])
        fetch.assert_not_called()


class EvidenceTests(unittest.TestCase):
    def test_real_child_stdout_stderr_metrics_and_repeated_evidence_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);(root/'bin').mkdir();work = root/'evidence';work.mkdir()
            command = root/'bin/mpm'
            command.write_text('#!'+sys.executable+'\nimport sys,json\nprint("phase",file=sys.stderr)\nprint(json.dumps({"selected":"exact-slot"}))\n')
            command.chmod(0o755)
            with mock.patch.object(delivery,'WORK',work),mock.patch.object(delivery,'RUNTIME',root),contextlib.redirect_stdout(io.StringIO()):
                report = delivery.run('sample','system','activate','--json',before={'selected':'old'})
                self.assertEqual(report['result']['selected'],'exact-slot');self.assertGreater(report['elapsed_ns'],0)
                self.assertEqual(json.loads((work/'sample.json').read_text())['before'],{'selected':'old'})
                self.assertIn('phase',(work/'sample.log').read_text())
                before = (work/'sample.log').read_bytes()
                with self.assertRaisesRegex(ValueError,'evidence already exists'):delivery.run('sample','system','activate','--json')
                self.assertEqual((work/'sample.log').read_bytes(),before)
                command.write_text('#!'+sys.executable+'\nimport sys\nprint("failed",file=sys.stderr)\nsys.exit(23)\n');command.chmod(0o755)
                with self.assertRaisesRegex(ValueError,'MPM failed'):delivery.run('failure','system','install','--json')
                self.assertEqual(json.loads((work/'failure.json').read_text())['returncode'],23)
                self.assertFalse((work/'failure-result.json').exists())


if __name__ == '__main__':unittest.main()
