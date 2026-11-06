# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Host acceptance preparation: fresh output and actual QEMU disk isolation."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import mojt_boot
import mpm_catalog

spec = importlib.util.spec_from_file_location('prepare_source_boot', ROOT/'tests/prepare-kernel-source-boot.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PreparationTests(unittest.TestCase):
    def test_existing_output_and_input_overlap_refused_without_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            original = root/'input'; original.mkdir()
            sentinel = original/'retain'; sentinel.write_text('original')
            for output in (original, original/'nested', root):
                with self.assertRaises(ValueError):
                    prepare.fresh_output(output, (original,))
            self.assertEqual(sentinel.read_text(), 'original')
            fresh = root/'fresh'
            self.assertEqual(prepare.fresh_output(fresh, (original,)), fresh)
            self.assertFalse(fresh.exists())

    def test_symlinked_output_parent_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root/'real').mkdir(); (root/'alias').symlink_to(root/'real', target_is_directory=True)
            with self.assertRaises(ValueError):
                prepare.fresh_output(root/'alias/new', ())
            self.assertFalse((root/'real/new').exists())

    def test_context_bounds_are_only_the_previously_accepted_pair(self):
        base = dict(id='sha256:'+'a'*64, platform='x86_64-linux', version=dict(upstream='0.1.3'))
        kernel = dict(platform='x86_64-linux', version=dict(upstream='6.12.107'))
        bounds = mpm_catalog.base_context(prepare.context(base, kernel, mpm_catalog.BASE_FORMAT))
        self.assertEqual(bounds['kernel_min'], '6.12.107')
        self.assertEqual(bounds['kernel_min'], bounds['kernel_max'])
        with self.assertRaises(ValueError):
            prepare.context(base, {**kernel, 'platform':'aarch64-linux'}, mpm_catalog.BASE_FORMAT)

    def test_launcher_attaches_only_private_vm_and_read_only_test_disk(self):
        with tempfile.TemporaryDirectory(prefix='mojt test ') as tmp:
            root = Path(tmp).resolve(); image = root/'image'; image.mkdir()
            (image/'disk.img').touch(); (image/'OVMF_VARS.fd').touch()
            firmware = root/'firmware'; firmware.touch()
            inputs = root/'test inputs.img'; inputs.touch()
            qemu = root/'qemu-system-x86_64'
            qemu.write_text('#!'+sys.executable+'\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n')
            qemu.chmod(0o755)
            original = mojt_boot.run_script(network=True)
            script = root/'run-qemu.sh'
            script.write_text(prepare.launcher(original, image, inputs))
            subprocess.run(['bash','-n',script], check=True)
            env = dict(os.environ, PATH=str(root)+':'+os.environ['PATH'],
                       OVMF_CODE=str(firmware), OVMF_VARS_TEMPLATE=str(firmware))
            args = json.loads(subprocess.check_output(['bash',str(script)], env=env, text=True))
            disks = [args[i+1] for i, v in enumerate(args) if v == '-drive']
            self.assertEqual(len(disks), 4)  # Two firmware drives, the new VM, the test-only input.
            self.assertEqual(disks[2], 'file='+str(image/'disk.img')+',if=virtio,format=raw')
            self.assertEqual(disks[3], 'file='+str(inputs)+',if=virtio,format=raw,readonly=on')
            self.assertEqual(original, mojt_boot.run_script(network=True))

    def test_unknown_launcher_refused_instead_of_guessing(self):
        with self.assertRaises(ValueError):
            prepare.launcher('#!/bin/bash\necho changed\n', Path('/image'), Path('/inputs'))


if __name__ == '__main__':
    unittest.main()
