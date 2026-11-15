# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pinned private manager delivery refuses changed code and false timing samples."""
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

TOOLS=Path(__file__).resolve().parents[1]/'tools'
spec=importlib.util.spec_from_file_location('stage_fast_delivery',TOOLS/'mojt-stage-fast-test.py')
delivery=importlib.util.module_from_spec(spec);spec.loader.exec_module(delivery)


class ResultTests(unittest.TestCase):
    def test_only_complete_normal_samples_with_exact_warm_payload_can_pass(self):
        def result(reused,key='payload'):
            return dict(ok=True,returncode=0,processes={},result=dict(changed=True,verification_requested=False,
                        initramfs_payload=dict(inputs=key,reused=reused)))
        cold=delivery.validate_result(result(False))
        self.assertEqual(delivery.validate_result(result(True),warm=cold),dict(inputs='payload',reused=True))
        for report in (result(True),dict(result(False),ok=False),dict(result(False),returncode=1),
                       dict(result(False),processes={'--verify-path':{'calls':1}})):
            with self.subTest(report=report),self.assertRaises(ValueError):delivery.validate_result(report)
        with self.assertRaisesRegex(ValueError,'different payload'):delivery.validate_result(result(True,'other'),warm=cold)


@unittest.skipUnless(os.geteuid()==0,'sealed executable code needs real numeric root ownership')
class BundleTests(unittest.TestCase):
    def test_sealed_cohort_keeps_installed_files_and_refuses_damaged_replacements(self):
        with tempfile.TemporaryDirectory() as temporary:
            work=Path(temporary);installed=work/'installed';installed.mkdir()
            manifest=installed/'mojt_system.py';manifest.write_text("MPM_FILES=('mojt_system.py','mpm-system','update.py')\n")
            (installed/'mpm-system').write_text('original launcher');(installed/'update.py').write_text('old code')
            replacement=work/'update.py';replacement.write_text('reviewed new code')
            files={'update.py':hashlib.sha256(replacement.read_bytes()).hexdigest()}
            before={p.name:p.read_bytes() for p in installed.iterdir()}
            with mock.patch.object(delivery,'FILES',files):
                hashes=delivery.seal(installed,{'update.py':replacement},work/'code')
                self.assertEqual((work/'code/update.py').read_text(),'reviewed new code')
                self.assertEqual(hashes['update.py'],files['update.py'])
                self.assertEqual(stat.S_IMODE((work/'code').stat().st_mode),0o555)
                self.assertTrue(all(stat.S_IMODE(p.stat().st_mode)==0o444 for p in (work/'code').iterdir()))
                self.assertEqual({p.name:p.read_bytes() for p in installed.iterdir()},before)
                replacement.write_text('damaged input')
                with self.assertRaisesRegex(ValueError,'checksum differs'):
                    delivery.seal(installed,{'update.py':replacement},work/'bad')
                self.assertFalse((work/'bad').exists())
            # Namespace-root cannot portably remove a sealed directory otherwise.
            (work/'code').chmod(0o700)


if __name__=='__main__':unittest.main()
