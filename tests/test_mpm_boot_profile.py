# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Timing must preserve real inventory results, refusals and installed code."""
from contextlib import redirect_stderr
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
import mojt_artifact as artifact
import mpm_boot_inventory as inventory

spec = importlib.util.spec_from_file_location('boot_profile',TOOLS/'mojt-boot-profile.py')
profile = importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)


class ProfileTests(unittest.TestCase):
    def test_probe_joins_running_receipt_and_checks_without_entering_handover(self):
        import mpm_boot_early as early
        import mpm_boot_handover as handover
        import mpm_boot_selection as selection
        import mpm_boot_status as status
        source = {'fixture':'exact inputs'};proof = {'fixture':'retained proof'}
        contract = {'fixture':'retained handover'}
        running = dict(format='mojt-boot-deployment-v2',id='fixture-running',description=dict(inputs=source))
        with mock.patch.object(profile,'installed_tools',return_value=TOOLS),mock.patch.object(profile.os,'geteuid',return_value=0),\
             mock.patch.object(status,'read_running',return_value=running),\
             mock.patch.object(selection,'ready',return_value=dict(receipt=dict(description=dict(proof=proof,handover=contract)))) as ready,\
             mock.patch.object(early,'verify',return_value=dict(verified=True)) as verify,\
             mock.patch.object(handover,'check') as check,mock.patch.object(handover,'enter') as enter,\
             mock.patch.object(handover,'_enter') as raw_enter,redirect_stderr(io.StringIO()):
            previous = sys.path[:]
            try:report = profile.measure_boot()
            finally:sys.path[:] = previous
        self.assertEqual(report['deployment'],'fixture-running')
        self.assertFalse(report['handover_executed']);enter.assert_not_called();raw_enter.assert_not_called()
        ready.assert_called_once_with(Path('/run/mojt-disk'),'fixture-running',verify=False)
        self.assertEqual(verify.call_args.args[1:3],(source,proof))
        check.assert_called_once_with(Path('/run/mojt-disk'),source,proof,contract)
        self.assertTrue(all(p['ok'] for p in report['phases']))

    def test_observers_preserve_real_inventory_and_tamper_refusal_and_restore_functions(self):
        timings = profile.Timings();measure = inventory.measure;canonical = artifact.canonical
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);(root/'file').write_bytes(b'original')
            expected = inventory.measure(root);before = inventory.snapshot(root)
            with redirect_stderr(io.StringIO()):
                with timings.observe(inventory,'measure',detail=timings.trees),timings.observe(artifact,'canonical'):
                    with timings.phase('verified scan'):inventory.verify(root,expected)
                    self.assertEqual(inventory.snapshot(root),before)
                    (root/'file').write_bytes(b'tampered')
                    with self.assertRaisesRegex(ValueError,'immutable tree differs'):
                        with timings.phase('refused scan'):inventory.verify(root,expected)
            self.assertIs(inventory.measure,measure);self.assertIs(artifact.canonical,canonical)
            report = timings.report()
            self.assertEqual([p['ok'] for p in report['phases']],[True,False])
            self.assertEqual(report['calls']['mpm_boot_inventory.measure']['calls'],2)
            self.assertEqual([r['nodes'] for r in report['trees']],[2,2])
            self.assertGreater(report['calls']['mojt_artifact.canonical']['calls'],0)

    def test_instrumented_failure_propagates_and_restores_the_original(self):
        timings = profile.Timings();measure = inventory.measure
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary)/'missing'
            with self.assertRaises(FileNotFoundError):
                with timings.observe(inventory,'measure',detail=timings.trees):inventory.measure(missing)
        self.assertIs(inventory.measure,measure)
        self.assertEqual(timings.report()['calls']['mpm_boot_inventory.measure']['failed'],1)
        self.assertFalse(timings.trees[0]['ok'])


if __name__ == '__main__':unittest.main()
