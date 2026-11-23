# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Saved locators cannot adopt an old VM or choose privileged helper commands."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_source_base', REPO/'tests/prepare-source-base-boot.py')
prepare = importlib.util.module_from_spec(spec); spec.loader.exec_module(prepare)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(); self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name).resolve()
        self.old = self.root/'old-vm'; (self.old/'image').mkdir(parents=True)
        (self.old/'image/disk.img').write_bytes(b'existing VM must survive')
        self.build = self.root/'base-build'; self.release = self.build/'releases/base-0.2.0-x86_64'
        self.release.mkdir(parents=True)
        (self.build/'result.json').write_text(json.dumps(dict(format='mojt-base-source-build-v1',
            release=str(self.release), phases=[dict(phase='Build glibc', seconds=90.55),
                                              dict(phase='Package release', seconds=0.125)])))
        self.kernel = self.root/'kernel.tar.zst'; self.kernel.write_bytes(b'locator fixture; archive reader checks later')
        self.payload = self.root/'system-export'; self.payload.mkdir()
        (self.payload/'system.json').write_text('{"fixture":"metadata locator"}')
        self.seed = dict(format='mojt-boot-test-input-check-v1', profile='system-v2', verified=True,
            output=str(self.old), source=dict(path='/untrusted/checkout'),
            kernel=dict(path=str(self.kernel), artifact='sha256:'+'a'*64),
            system=dict(path=str(self.payload), record_sha256=hashlib.sha256((self.payload/'system.json').read_bytes()).hexdigest()))
        self.check = self.old/'input-check.json'; self.save()
        self.args = argparse.Namespace(from_check=self.check, base_build=self.build, output=self.root/'new-vm',
            busybox=Path('/usr/bin/busybox'))

    def save(self):self.check.write_text(json.dumps(self.seed))

    def snapshot(self):return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_locators_are_read_only_and_saved_output_is_not_adopted(self):
        before = self.snapshot(); seed, output = prepare.inputs(self.args)
        self.assertEqual(output, self.root/'new-vm')
        self.assertFalse(output.exists()); self.assertEqual(before, self.snapshot())
        self.assertEqual(self.args.base_release, self.release)
        self.assertEqual(self.args.kernel_package, self.kernel)
        self.assertEqual(seed['output'], str(self.old))

    def test_existing_vm_output_is_refused_without_changing_its_disk(self):
        self.args.output = self.old; before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'new nonsymlink'):
            prepare.inputs(self.args)
        self.assertEqual(before, self.snapshot())

    def test_build_report_size_and_object_limits_remain_enforced(self):
        path = self.build/'result.json'
        with mock.patch.object(prepare.artifact, 'MAX_METADATA', 64):
            with self.assertRaisesRegex(ValueError, 'exceeds size limit'):
                prepare.read_build_result(path)
        for content in ('[]', '{malformed'):
            with self.subTest(content=content):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    prepare.read_build_result(path)

    def test_canonical_input_metadata_still_rejects_floats(self):
        self.seed['unexpected_timing'] = 0.125; self.save()
        with self.assertRaisesRegex(ValueError, 'no floats/custom types'):
            prepare.inputs(self.args)
        self.assertFalse(self.args.output.exists())

    def test_saved_verified_flag_cannot_cover_changed_system_inputs(self):
        (self.payload/'system.json').write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError, 'changed since'):
            prepare.inputs(self.args)
        self.assertFalse(self.args.output.exists())

    def test_incomplete_or_external_base_release_is_refused(self):
        (self.build/'INCOMPLETE').write_text('build failed')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            prepare.inputs(self.args)
        (self.build/'INCOMPLETE').unlink()
        (self.build/'result.json').write_text(json.dumps(dict(format='mojt-base-source-build-v1', release=str(self.old))))
        with self.assertRaisesRegex(ValueError, 'belong to this Base build'):
            prepare.inputs(self.args)

    def test_bootstrap_targets_one_new_image_with_the_exact_requested_kernel(self):
        _, output = prepare.inputs(self.args)
        packed = dict(artifact=dict(id='sha256:'+'b'*64), archive=dict(file='base.tar.zst'))
        command = list(map(str, prepare.bootstrap_command(self.args, output, packed)))
        self.assertNotIn(str(self.old/'image/disk.img'), command)
        self.assertNotIn('--target-root', command)
        self.assertNotIn('/untrusted/checkout', command)
        self.assertEqual(command[command.index('--output')+1], str(output/'image'))
        self.assertEqual(command[command.index('--kernel-artifact')+1], self.seed['kernel']['artifact'])
        self.assertEqual(command[command.index('--system-payload')+1], str(self.payload))
        self.assertEqual(command[command.index('--system-generation')+1], 'system-source-base-test')
        self.assertEqual(Path(command[3]), REPO/'tools/mojt_bootstrap.py')
        self.args.with_build_tools=True
        self.assertIn('--with-build-tools',prepare.bootstrap_command(self.args,output,packed))

    def test_optional_update_disk_uses_a_frozen_package_and_the_new_image_only(self):
        import shutil
        import subprocess
        import mojt_boot
        output=self.root/'new-vm';(output/'image').mkdir(parents=True)
        (output/'image/run-qemu.sh').write_text(mojt_boot.run_script(network=True))
        package=self.root/'update.tar.zst';package.write_bytes(b'package fixture')
        calls=[]
        with mock.patch.object(prepare.artifact,'verify',return_value={'kind':'base','id':'fixed'}), \
             mock.patch.object(prepare.subprocess,'run',side_effect=lambda args,**kw:calls.append(args)):
            launcher=prepare.update_disk(output,package)
        self.assertEqual((output/'update-input/base.tar.zst').read_bytes(),package.read_bytes())
        self.assertIn('MOJT_BASE_UPDATE',calls[0]);self.assertIn('readonly=on',launcher.read_text())
        self.assertIn(str(output/'image'),launcher.read_text());self.assertNotIn(str(self.old),launcher.read_text())
        if shutil.which('bash'):subprocess.run(['bash','-n',str(launcher)],check=True)

    def test_input_check_never_invokes_sudo_or_creates_a_workspace(self):
        before = self.snapshot()
        with mock.patch.object(prepare.os, 'geteuid', return_value=1000), \
             mock.patch.object(prepare.shutil, 'which', return_value='/usr/bin/true'), \
             mock.patch.dict(os.environ), mock.patch.dict(prepare.shared, {
                 'FIRMWARE':(self.kernel,), 'check_source':lambda:dict(id='checked manager'),
                 'input_report':lambda *args:dict(image_written=False),
                 'run':mock.Mock(side_effect=AssertionError('must not run sudo or pack/install'))}):
            prepare.main(['--from-check',str(self.check),'--base-build',str(self.build),
                          '--output',str(self.args.output),'--busybox',str(self.kernel),'--check-inputs'])
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.args.output.exists())


if __name__ == '__main__':unittest.main()
