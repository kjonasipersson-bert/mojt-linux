# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Fixed two-generation delivery: actual archives, no external network or boot."""
import copy
import hashlib
import importlib.util
import os
import shutil
import unittest
from unittest import mock
from test_mpm_system import Fixture, REPO, pack, spec, tree
from test_system_ports_repair import Provider
import mojt_artifact as artifact
import mpm_base as base
import mpm_system as system
import mpm_system_model as model

specification = importlib.util.spec_from_file_location('activation_test', REPO/'tools/mojt-system-activation-test.py')
delivery = importlib.util.module_from_spec(specification);specification.loader.exec_module(delivery)


@unittest.skipUnless(os.geteuid() == 0 and shutil.which('zstd'), 'requires root-mapped install and zstd')
class DeliveryTests(Fixture):
    def setUp(self):
        super().setUp()
        content = self.work/'component-source'
        (content/'version').write_text('system-ports-fix-1\n')
        self.providers = {'fixture':Provider()}
        provider = dict(provider='fixture',identity=dict(closure='unchanged-runtime'))
        part = pack(content,spec('component',dependencies=[provider]),self.work/'baseline-runtime')
        self.reference = dict(provider='native',artifact=part['artifact']['id'])
        self.component_archive = self.work/'baseline-runtime'/part['archive']['file']
        d = copy.deepcopy(self.composition['description']);d['components'][0]['reference'] = self.reference
        for row in d['profile']:row['source']['reference'] = self.reference
        d['profile'].append(dict(path='version',source=dict(reference=self.reference,path='version')))
        d['profile'].sort(key=lambda row:row['path']);self.composition = base.record(model.FORMAT,d)
        self.archive,self.body = self.package(self.composition,self.actions);self.install(adapters=self.providers)
        self.downloads = {p:(REPO/p).read_bytes() for p in delivery.FILES}
        # Local package fixture, independent of future edits to historical pins.
        self.enterContext(mock.patch.object(delivery,'FILES',
            {p:hashlib.sha256(data).hexdigest() for p,data in self.downloads.items()}))

    def test_both_candidates_keep_old_content_and_dependencies_and_install_without_selection(self):
        before = tree(self.root)
        a = delivery.package(self.root,self.body['id'],self.downloads,self.work/'A')
        b = delivery.package(self.root,self.body['id'],self.downloads,self.work/'B',label='system-activation-B',revision=2)
        self.assertNotEqual(a['artifact'],b['artifact']);self.assertNotEqual(a['version'],b['version'])
        self.assertEqual(before,tree(self.root))
        for name,row in (('A',a),('B',b)):
            output = self.work/name
            new_part = artifact.verify(output/row['component'])
            old_part = system.object_record(self.root,self.reference['artifact'])[0]
            self.assertEqual(new_part['dependencies'],old_part['dependencies'])
            system.install(self.root,output/row['generation'],row['artifact'],
                dependency_files=[output/row['component']],adapters=self.providers,yes=True)
            profile = system.realization_path(self.root,row['artifact'])/'profile'
            self.assertEqual((profile/'version').read_text().strip(),row['label'])
            for path,expected in delivery.FILES.items():
                target = profile/path if path.startswith('tools/') else profile/'share/man/man1/mpm.1'
                self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),expected)
        self.assertFalse(any((self.root/'boot').glob('**/*')))
        self.assertFalse(self.marker.exists())

    def test_damaged_input_does_not_publish_a_candidate(self):
        self.downloads['tools/mpm_boot_update.py'] += b'changed'
        before = tree(self.root)
        with self.assertRaisesRegex(ValueError,'pinned data'):
            delivery.package(self.root,self.body['id'],self.downloads,self.work/'bad')
        self.assertEqual(before,tree(self.root));self.assertFalse((self.work/'bad').exists())


class Boundaries(unittest.TestCase):
    def test_delivery_requires_accepted_ssd_generation_and_no_pending_selection(self):
        row = dict(state='known',artifact='sha256:'+'a'*64,deployment='sha256:'+'b'*64,label='system-usb-installer')
        status = dict(running=dict(row),selected=dict(row))
        with mock.patch.object(delivery,'mpm',return_value=status):
            with self.assertRaisesRegex(ValueError,'SSD'):delivery.baseline()
            status['running']['label'] = 'system-ports-fix-1'
            self.assertEqual(delivery.baseline()['artifact'],row['artifact'])
            status['selected']['deployment'] = 'sha256:'+'c'*64
            with self.assertRaisesRegex(ValueError,'already selected'):delivery.baseline()
