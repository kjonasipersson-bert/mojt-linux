# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Standalone diagnostic on older layouts; never installs or selects content."""
import importlib.util
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
spec = importlib.util.spec_from_file_location('inventory', REPO/'tools/mojt-libc-inventory.py')
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


class InventoryTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('readelf'), 'requires standard ELF inspector')
    def test_real_loader_agrees_with_readelf_and_does_not_run_program_entry(self):
        target = shutil.which('false')
        loader = inventory.interpreter(target)
        reference = subprocess.check_output(['readelf', '-l', target], text=True)
        self.assertIn(loader, reference)
        report = inventory.program(target, shutil.which('readelf'))
        self.assertEqual(report['loader_list']['exit'], 0)  # false itself returns 1.
        self.assertIn('libc.so', report['loader_list']['stdout'])
        self.assertIn('GLIBC_', ' '.join(report['required_glibc_versions']))

    def test_loader_resolution_works_without_binutils(self):
        report = inventory.program(sys.executable, None)
        self.assertEqual(report['loader_list']['exit'], 0)
        self.assertIn('readelf unavailable', report['elf_details'])

    def test_missing_optional_program_and_truncated_elf_are_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'old-system-without-sshd'
            self.assertIn('error', inventory.program(path, None))
            path.write_bytes(b'\x7fELF\x02\x01')
            self.assertIn('unsupported ELF header', inventory.program(path, None)['error'])

    def test_old_vm_needs_no_current_runtime_metadata_or_dns_lookup(self):
        def old_files(path):
            if str(path) == '/usr/lib/os-release':
                return 'ID=mojt\nVERSION_ID=0.1.3\n'
            if str(path) == '/run/mojt-system/version':
                return 'system-A\n'
            raise PermissionError('not available in this fixture')
        with mock.patch.object(inventory, 'read_text', side_effect=old_files), \
             mock.patch.object(inventory, 'program', side_effect=lambda path, tool: dict(path=path)), \
             mock.patch.object(inventory, 'command', return_value=dict(exit=0, stdout='', stderr='')) as run:
            report = inventory.inventory()
        self.assertEqual(report['identities']['system'], 'system-A')
        self.assertIn('0.1.3', report['identities']['base'])
        self.assertIn('error', report['mapped_libraries']['init'])
        self.assertNotIn('base_dns', report['probes'])
        self.assertTrue(all(not any('nix-store' in part for part in call.args[0]) for call in run.call_args_list))

    def test_copied_single_file_runs_without_repository_and_only_emits_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'inventory.py'
            shutil.copyfile(REPO/'tools/mojt-libc-inventory.py', path)
            before = path.read_bytes()
            result = subprocess.run([sys.executable, '-I', '-B', str(path)], cwd=tmp,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['format'], 'mojt-libc-inventory-v1')
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(os.listdir(tmp), ['inventory.py'])


if __name__ == '__main__':
    unittest.main()
