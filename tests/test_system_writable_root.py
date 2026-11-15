# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pinned root delivery: native G/H packaging and checked private-launch boundaries."""
import hashlib
import errno
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from test_mpm_system import REPO
import test_system_fast_test as original

spec=importlib.util.spec_from_file_location('writable_root_delivery',REPO/'tools/mojt-writable-root-test.py')
delivery=importlib.util.module_from_spec(spec);spec.loader.exec_module(delivery)


class InputTests(unittest.TestCase):
    def test_probe_paths_require_a_finite_hex_token(self):
        paths=delivery.markers('a'*32)
        self.assertEqual(len(paths),8)
        self.assertIn(Path('/usr/local/mojt-root-test-'+'a'*32+'/marker'),paths)
        for value in ('../etc/passwd','',None,'g'*32):
            with self.assertRaises(ValueError):delivery.markers(value)

    def test_driver_is_pinned_and_payload_contains_the_root_changes(self):
        data=(REPO/'tools/mojt-system-fast-test.py').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),delivery.DRIVER_SHA256)
        for name in ('tools/mpm_boot_handover.py','tools/mpm_base_boot.py','tools/mojt_native_image.py'):
            self.assertIn(name,delivery.FILES)


@unittest.skipUnless(os.geteuid()==0,'checked candidate code requires numeric root ownership')
class LauncherTests(unittest.TestCase):
    def test_marker_check_preserves_existing_data_and_distinguishes_temporary_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'tmp').mkdir()
            paths=[root/name/'marker' for name in ('data','opt','local')]
            state=dict(token='a'*32,baseline=dict(installation='1'*32))
            bridge=mock.Mock()
            real_path=Path
            with mock.patch.object(delivery,'markers',return_value=paths),\
                 mock.patch.object(delivery,'RUNTIME',root/'runtime'),\
                 mock.patch.object(delivery,'Path',side_effect=lambda name:root/'tmp' if name=='/tmp' else real_path(name)),\
                 mock.patch.object(delivery,'plain',return_value=dict(format='mojt-writable-root-v1',installation='1'*32)),\
                 mock.patch.object(delivery.os.path,'samefile',return_value=True),\
                 mock.patch.object(delivery.os,'open',side_effect=OSError(errno.EROFS,'read-only mount')),\
                 mock.patch.object(delivery.subprocess,'run'):
                delivery.check_root(bridge,state,seed=True)
                delivery.check_root(bridge,state,rebooted=False)
                with self.assertRaisesRegex(ValueError,'survived reboot'):delivery.check_root(bridge,state)
                (root/'tmp'/('mojt-root-test-'+state['token'])).unlink()
                delivery.check_root(bridge,state)
                with self.assertRaisesRegex(ValueError,'already exists'):delivery.check_root(bridge,state,seed=True)
                self.assertEqual(paths[0].read_text(),state['token'])
                paths[0].write_text('changed data')
                with self.assertRaisesRegex(ValueError,'persistent probe changed'):delivery.check_root(bridge,state)

    def test_installed_g_cohort_is_checked_before_private_launcher_and_tampering_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);identifier='sha256:'+'1'*64
            folder=root/'realizations/system'/identifier[7:]/'profile/tools';folder.mkdir(parents=True)
            (folder/'mojt_system.py').write_text("MPM_FILES=('mojt_system.py','mpm-system')\n")
            (folder/'mpm-system').write_text('candidate launcher')
            code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
            state=dict(candidate=dict(artifact=identifier),code=code)
            with mock.patch.object(delivery,'ROOT',root),mock.patch.object(delivery,'checked_state',return_value=state),\
                 mock.patch.object(delivery,'FILES',{'tools/'+n:h for n,h in code.items()}),\
                 mock.patch.object(delivery.runpy,'run_path') as launch,\
                 mock.patch.object(sys,'argv',sys.argv[:]),mock.patch.object(sys,'path',sys.path[:]):
                delivery.private_stage();launch.assert_called_once_with(str(folder/'mpm-system'),run_name='__main__')
                self.assertEqual(sys.argv[1:],['system','stage','--artifact',identifier,'-y','--json'])
                (folder/'mpm-system').write_text('tampered candidate')
                with self.assertRaisesRegex(ValueError,'code changed'):delivery.private_stage()
                self.assertEqual(launch.call_count,1)
                (folder/'mpm-system').write_text('candidate launcher')
                (folder/'mojt_system.py').write_text("MPM_FILES=('mojt_system.py','mpm-system','unexpected.py')\n")
                with self.assertRaisesRegex(ValueError,'cohort differs'):delivery.private_stage()


@unittest.skipUnless(os.geteuid()==0 and original.shutil.which('zstd'),'numeric-owner packaging requires root and zstd')
class PackageTests(original.DeliveryTests):
    def setUp(self):
        self.enterContext(mock.patch.object(original.delivery,'FILES',delivery.FILES))
        self.enterContext(mock.patch.object(original.delivery,'REVISION',delivery.REVISION))
        super().setUp()


if __name__=='__main__':unittest.main()
