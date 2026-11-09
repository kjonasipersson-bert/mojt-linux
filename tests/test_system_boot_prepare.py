# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Focused unpublished-image boundaries and real assembled-default paths."""
import importlib.util
import copy
import contextlib
import io
import json
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
import mojt_boot
import mojt_system

spec = importlib.util.spec_from_file_location('system_boot_preparation',REPO/'tests/prepare-system-boot.py')
prepare = importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)
spec = importlib.util.spec_from_file_location('source_boot_preparation',REPO/'tests/prepare-kernel-source-boot.py')
source_prepare = importlib.util.module_from_spec(spec);spec.loader.exec_module(source_prepare)


class PreparationTests(unittest.TestCase):
    def test_deferred_detach_waits_for_only_its_own_mapping_without_detaching_other_devices(self):
        disk = Path('/private/new.img')
        with mock.patch.object(prepare,'run') as run, mock.patch.object(prepare.time,'sleep') as pause, \
             mock.patch.object(prepare.subprocess,'check_output',side_effect=[
                 '/dev/loop7: pending\n/dev/loop8: unrelated\n','/dev/loop8: unrelated\n']):
            prepare.detach_root('/dev/loop7',disk)
            run.assert_called_once_with('losetup','--detach','/dev/loop7')
            pause.assert_called_once_with(0.05)
        with mock.patch.object(prepare,'run'),mock.patch.object(prepare.time,'monotonic',side_effect=[0,6]), \
             mock.patch.object(prepare.subprocess,'check_output',return_value='/dev/loop7: pending\n'):
            with self.assertRaisesRegex(ValueError,'pending/in use'):prepare.detach_root('/dev/loop7',disk)

    def test_exact_root_extent_ignores_partition_node_names_and_refuses_wrong_geometry(self):
        table = dict(label='gpt',unit='sectors',sectorsize=512,partitions=[
            dict(node='/dev/nonexistentp1',start=2048,size=262144),
            dict(node='/dev/nonexistentp2',start=264192,size=782336)])
        self.assertEqual(prepare.root_extent(512*1024**2,table),(129*1024**2,382*1024**2))
        for changed in (dict(table,sectorsize=4096),dict(table,label='dos'),dict(table,partitions=table['partitions'][::-1])):
            with self.assertRaises(ValueError):prepare.root_extent(512*1024**2,changed)
        changed = copy.deepcopy(table);changed['partitions'][1]['start'] += 1
        with self.assertRaisesRegex(ValueError,'extents'):prepare.root_extent(512*1024**2,changed)

    def test_wrong_payload_reports_the_path_and_missing_roles_before_scanning_or_writing(self):
        import test_system_vm as fixtures
        fixture=fixtures.SystemVmTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        record=fixture.fixture(10);record['packages']['old-role']=record['packages'].pop('tar')
        (fixture.payload/'system.json').write_text(json.dumps(record))
        with mock.patch.object(mojt_system,'tree_hash',side_effect=AssertionError('must reject roles first')):
            with self.assertRaisesRegex(ValueError,r'system.json.*missing=tar; unexpected=old-role'):
                mojt_system.load_payload(fixture.payload)
        self.assertFalse((fixture.root/'new-output').exists())

    @unittest.skipUnless(shutil.which('zstd') and shutil.which('cpio'),'requires real package tools')
    def test_public_input_check_joins_real_inputs_without_output_sudo_or_path_changes(self):
        import test_native_image as fixtures
        f=fixtures.NativeImageTests();f.setUp();self.addCleanup(f.doCleanups)
        f.fixture.fixture(10)
        output=f.work/'new-output';path_file=f.work/'selected-test';path_file.write_text('previous test\n')
        argv=['prepare-system-boot.py','--base-release',str(f.work/'release'),
            '--kernel-package',str(f.args.kernel_registry.parent/'kernel-package'/json.loads(
                (f.work/'kernel-package/archive.json').read_text())['file']),
            '--expected-kernel',f.kernel['id'],'--system-payload',str(f.fixture.payload),
            '--busybox',str(f.args.busybox),'--output',str(output),'--path-file',str(path_file),'--check-inputs']
        before=f.snapshot();finish=mock.Mock(side_effect=AssertionError('must not construct an image'))
        with mock.patch.object(sys,'argv',argv),mock.patch.object(source_prepare,'FIRMWARE',()), \
                mock.patch.object(source_prepare.shutil,'which',return_value='/host-fixture/command'), \
                mock.patch.object(source_prepare.os,'geteuid',return_value=path_file.stat().st_uid), \
                mock.patch.object(source_prepare,'run',side_effect=AssertionError('must not invoke sudo/import')), \
                contextlib.redirect_stdout(io.StringIO()):
            result=source_prepare.main(profile='system-v2',finish=finish)
        self.assertTrue(result['verified']);self.assertFalse(result['image_written'] or result['boot_acceptance'])
        self.assertEqual(result['system']['path'],str(f.fixture.payload.resolve()))
        self.assertIn('tar',result['system']['roles']);self.assertEqual(result['kernel']['artifact'],f.kernel['id'])
        self.assertFalse(output.exists());self.assertEqual(path_file.read_text(),'previous test\n')
        self.assertEqual(before,f.snapshot());finish.assert_not_called()

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
    @unittest.skipUnless(all(shutil.which(c) for c in ('sfdisk','mkfs.ext4','losetup','blkid','blockdev')),
                         'requires real GPT/ext4/loop tools')
    def test_root_only_mapping_reads_uuid_and_length_without_partition_scan_and_rejects_wrong_uuid(self):
        probe = subprocess.run(['losetup','--find'],capture_output=True,text=True)
        if probe.returncode:self.skipTest('loop device availability: '+probe.stderr.strip())
        with tempfile.TemporaryDirectory() as temporary:
            disk = Path(temporary)/'new.img';layout = mojt_boot.layout(512)
            with disk.open('xb') as stream:stream.truncate(layout['disk_bytes'])
            subprocess.run(['sfdisk','--no-reread','--no-tell-kernel',str(disk)],
                input=mojt_boot.partition_script(layout),capture_output=True,text=True,check=True)
            expected = '12345678-1234-1234-1234-123456789abc'
            filesystem = Path(temporary)/'root.ext4'
            with filesystem.open('xb') as stream:stream.truncate(layout['root_bytes'])
            subprocess.run(['mkfs.ext4','-F','-q','-U',expected,str(filesystem)],check=True)
            mojt_boot.copy_partition(filesystem,disk,layout['root_offset'],layout['root_bytes'])
            loop = prepare.attach_root(disk,expected)
            try:
                length = int(subprocess.check_output(['blockdev','--getsize64',loop],text=True))
                self.assertEqual(length,layout['root_bytes'])
            finally:prepare.detach_root(loop,disk)
            with self.assertRaisesRegex(ValueError,'UUID differs'):
                prepare.attach_root(disk,'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')
            self.assertEqual(subprocess.check_output(['losetup','--associated',str(disk)],text=True).strip(),'')

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
