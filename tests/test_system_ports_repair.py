# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Fixed repair bridge: actual native archives and installation, no live network."""
import copy
import importlib.util
import os
from pathlib import Path
import shutil
import unittest
from unittest import mock

from test_mpm_system import Fixture, REPO, pack, spec, tree
import mojt_artifact as artifact
import mpm_base as base
import mpm_system as system
import mpm_system_model as model
import mpm_system_transition as transition

loader = importlib.util.spec_from_file_location('ports_repair', REPO / 'tools/mojt-system-ports-repair.py')
repair = importlib.util.module_from_spec(loader); loader.loader.exec_module(repair)


class Provider:
    def describe(self, reference, root): return dict(reference=copy.deepcopy(reference), commands={})
    def ensure(self, reference, root): pass
    def verify(self, reference, root): pass


@unittest.skipUnless(os.geteuid() == 0 and shutil.which('zstd'), 'requires root-mapped native install and zstd')
class RepairTests(Fixture):
    def setUp(self):
        super().setUp()
        content = self.work / 'component-source'
        (content / 'version').write_text('system-native-test\n')
        (content / 'tools/mpm_ports_nix_source.py').unlink()
        path = content / 'tools/mojt_system.py'
        path.write_text(path.read_text().replace('"mpm_ports_nix_source.py", ', ''))
        self.providers = {'fixture':Provider()}
        provider = dict(provider='fixture', identity=dict(closure='accepted-startup-runtime'))
        part = pack(content, spec('component', dependencies=[provider]), self.work / 'original-runtime')
        self.reference = dict(provider='native', artifact=part['artifact']['id'])
        self.component_archive = self.work / 'original-runtime' / part['archive']['file']
        d = copy.deepcopy(self.composition['description']); d['components'][0]['reference'] = self.reference
        for row in d['profile']: row['source']['reference'] = self.reference
        d['profile'].append(dict(path='version', source=dict(reference=self.reference, path='version')))
        d['profile'].sort(key=lambda r:r['path']); self.composition = base.record(model.FORMAT, d)
        self.archive, self.body = self.package(self.composition, self.actions)
        self.install(adapters=self.providers)
        self.downloads = {p:(REPO / p).read_bytes() for p in repair.FILES}

    def test_fixed_generation_installs_with_existing_manager_and_old_content_unchanged(self):
        before = tree(self.root); output = self.work / 'repair-kit'
        result = repair.package(self.root, self.body['id'], self.downloads, output)
        self.assertEqual(before, tree(self.root)); self.assertFalse(self.marker.exists())
        new = artifact.verify(output / result['generation'], result['artifact'])
        self.assertEqual(new['version']['release_id'], '0.2.0-r2')
        self.assertEqual(new['provenance']['ports_repair']['baseline'], self.body['id'])
        new_component = artifact.verify(output / result['component'])
        old_component = system.object_record(self.root, self.reference['artifact'])[0]
        self.assertEqual(new_component['dependencies'], old_component['dependencies'])
        self.assertFalse(any((self.root / 'boot').glob('**/*')))
        system.install(self.root, output / result['generation'], result['artifact'],
            dependency_files=[output / result['component']], adapters=self.providers, yes=True)
        old_profile = system.realization_path(self.root, self.body['id']) / 'profile'
        new_profile = system.realization_path(self.root, result['artifact']) / 'profile'
        report = transition.tooling_review(base.read(old_profile / 'manifest.json'), base.read(new_profile / 'manifest.json'))
        self.assertTrue(report['description']['compatible'], report)
        self.assertEqual((new_profile / 'version').read_text().strip(), repair.LABEL)
        self.assertEqual((old_profile / 'version').read_text().strip(), 'system-native-test')
        self.assertTrue((new_profile / 'tools/mpm_ports_nix_source.py').is_file())
        self.assertFalse((old_profile / 'tools/mpm_ports_nix_source.py').exists())
        self.assertEqual({r['artifact'] for r in system.status(self.root)['installed']}, {self.body['id'], result['artifact']})

    def test_bad_network_bytes_fail_before_packaging_or_installation(self):
        before = tree(self.root); self.downloads['tools/mpm_cli.py'] += b'\n# damaged\n'
        with self.assertRaisesRegex(ValueError, 'pinned data'):
            repair.package(self.root, self.body['id'], self.downloads, self.work / 'bad-kit')
        self.assertEqual(before, tree(self.root)); self.assertFalse((self.work / 'bad-kit').exists())


class DownloadTests(unittest.TestCase):
    def test_usb_runtime_and_pending_boot_choice_are_refused(self):
        row = dict(state='known', artifact='sha256:' + 'a'*64, deployment='sha256:' + 'b'*64, label='system-usb-installer')
        status = dict(running=dict(row), selected=dict(row))
        with mock.patch.object(repair, 'mpm', return_value=status), self.assertRaisesRegex(ValueError, 'SSD'):
            repair.baseline()
        status['running']['label'] = 'system-ssd-A'
        status['selected']['deployment'] = 'sha256:' + 'c'*64
        with mock.patch.object(repair, 'mpm', return_value=status), self.assertRaisesRegex(ValueError, 'already selected'):
            repair.baseline()

    def test_failed_checksum_is_not_returned_for_execution_or_packaging(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            def curl(args, **kwargs):
                self.assertIn('--proto-redir', args)
                self.assertTrue(args[-1].startswith(repair.ORIGIN))
                Path(args[args.index('--output') + 1]).write_bytes(b'wrong bytes')
            with mock.patch.object(repair.subprocess, 'run', side_effect=curl), self.assertRaisesRegex(ValueError, 'checksum differs'):
                repair.fetch(Path(temp))
