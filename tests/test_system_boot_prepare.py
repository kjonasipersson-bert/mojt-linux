# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Focused unpublished-image boundaries and real assembled-default paths."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
import mpm_system_transition as transition
import mpm_management as management

spec = importlib.util.spec_from_file_location('system_boot_preparation',REPO/'tests/prepare-system-boot.py')
prepare = importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)
spec = importlib.util.spec_from_file_location('source_boot_preparation',REPO/'tests/prepare-kernel-source-boot.py')
source_prepare = importlib.util.module_from_spec(spec);spec.loader.exec_module(source_prepare)


class PreparationTests(unittest.TestCase):
    def test_group_writable_checkout_reports_exact_file_without_changing_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            tools = Path(temporary)/'tools';tools.mkdir()
            for name in management.CAPABILITY_FILES:
                shutil.copy2(REPO/'tools'/name,tools/name)
            checked = source_prepare.check_source(tools)
            helper = tools/'mpm_cli.py';before = helper.read_bytes();mode = helper.stat().st_mode & 0o777
            helper.chmod(mode | 0o020)
            with self.assertRaisesRegex(ValueError,r'mpm_cli\.py.*mode=0664'):
                source_prepare.check_source(tools)
            self.assertEqual(helper.read_bytes(),before)
            self.assertEqual(helper.stat().st_mode & 0o777,mode | 0o020)
            helper.chmod(mode)
            self.assertEqual(source_prepare.check_source(tools),checked)

    def test_failed_offline_workspace_is_retained_instead_of_recursively_cleaning_possible_mounts(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            with self.assertRaisesRegex(OSError,'mount cleanup'):
                with prepare.workspace(parent) as work:
                    (work/'evidence').write_text('retain')
                    raise OSError('mount cleanup')
            self.assertEqual((work/'evidence').read_text(),'retain')
            shutil.rmtree(work)
            with prepare.workspace(parent) as successful:
                (successful/'temporary').touch()
            self.assertFalse(successful.exists())

    def test_existing_published_image_is_refused_before_any_mount_or_loop_operation(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary)/'image';image.mkdir();(image/'disk.img').write_bytes(b'unchanged')
            with mock.patch.object(prepare.os,'geteuid',return_value=0),mock.patch.object(prepare,'run') as run:
                with self.assertRaisesRegex(ValueError,'unpublished'):
                    prepare.finalize(image,Path('/unrelated/base.tar.zst'),'sha256:'+'a'*64,'system-v2-bootstrap')
                run.assert_not_called()
            self.assertEqual((image/'disk.img').read_bytes(),b'unchanged')

    def test_systemd_resources_observe_actual_persistent_paths_and_refuse_linked_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);profile = root/'profile';(profile/'defaults').mkdir(parents=True)
            etc = root/'state/etc';(etc/'systemd').mkdir(parents=True)
            for name in ('journald.conf','timesyncd.conf'):
                (profile/'defaults'/name).write_text('resource')
                (etc/'systemd'/name).symlink_to('/run/mojt-system/defaults/'+name)
            first = transition.defaults(root,profile)
            self.assertEqual(first['missing'],[])
            self.assertFalse((etc/'journald.conf').exists())
            (etc/'systemd/timesyncd.conf').unlink()
            self.assertEqual(transition.defaults(root,profile)['missing'],['systemd/timesyncd.conf'])
            (etc/'systemd/journald.conf').unlink();(etc/'systemd').rmdir();(etc/'systemd').symlink_to(profile/'defaults')
            with self.assertRaisesRegex(ValueError,'parent'):transition.defaults(root,profile)


@unittest.skipUnless(os.geteuid() == 0 and shutil.which('unshare'),'requires root PID/mount namespaces')
class NamespaceTests(unittest.TestCase):
    def test_failed_constructor_cannot_leave_a_helper_pinning_its_store_or_output_pipe(self):
        probe = subprocess.run(['unshare','--pid','--fork','--kill-child','--mount-proc',sys.executable,'-I','-c','pass'],
                               capture_output=True,text=True)
        if probe.returncode:self.skipTest('kernel namespace permissions: '+probe.stderr.strip())
        # The child inherits stdout and holds its working directory. Without
        # namespace teardown, capture waits for that helper instead of returning
        # the constructor's failure. No real Nix daemon is required for this bug.
        with tempfile.TemporaryDirectory() as temporary:
            code = ('import subprocess,sys; subprocess.Popen([sys.executable,"-I","-c",'
                    '"import time; time.sleep(60)"]); print("constructor failed",flush=True); sys.exit(7)')
            with self.assertRaises(subprocess.CalledProcessError) as failure:
                prepare.isolated([sys.executable,'-I','-c',code],Path('/proc'),
                                 cwd=temporary,capture_output=True,text=True,timeout=10)
            self.assertEqual(failure.exception.returncode,7)
            self.assertEqual(failure.exception.stdout.strip(),'constructor failed')


if __name__ == '__main__':unittest.main()
