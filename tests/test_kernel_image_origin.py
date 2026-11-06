# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real Kernel origin transfer into the private native-image input registry."""
import copy
import json
from pathlib import Path
import shutil
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import mojt_native_image as native
import mpm_kernel as kernel
import test_mpm_kernel_source as fixture


@unittest.skipUnless(shutil.which('zstd'), 'requires zstd')
class ImageOriginTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.KernelSourceTests(); self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.install()
        self.identifier = self.f.artifact
        self.obj = self.f.root/'installed'/kernel.identifier(self.identifier)
        self.body, self.record = kernel.object_record(self.obj, self.identifier, verify=True)
        self.destination = self.f.f.work/'private-image-kernel'
        self.digest = native.artifact.digest(self.record)

    def test_source_origin_and_encoding_survive_new_installation(self):
        before = (self.obj/'installed.json').read_bytes()
        body, record = native.copy_kernel_input(self.f.root, self.destination, self.identifier, self.digest)
        self.assertEqual(body, self.body)
        self.assertEqual(record['acquisition'], self.record['acquisition'])
        self.assertEqual(record['trust'], self.record['trust'])
        self.assertEqual(record['archive_sha256'], self.record['archive_sha256'])
        self.assertEqual((self.obj/'installed.json').read_bytes(), before)
        native.check_kernel_installation(record, dict(kernel_installation_digest=native.artifact.digest(record),
                                                      kernel_acquisition=record['acquisition']))

    def test_changed_source_install_record_fails_before_copy(self):
        path = self.obj/'installed.json'
        record = copy.deepcopy(self.record); record['installed_utc'] = '2026-01-01T00:00:00+00:00'
        path.chmod(0o644); path.write_text(json.dumps(record)); path.chmod(0o444)
        with self.assertRaisesRegex(ValueError, 'after preview'):
            native.copy_kernel_input(self.f.root, self.destination, self.identifier, self.digest)
        self.assertFalse(self.destination.exists())

    def test_late_input_change_prevents_image_input_acceptance(self):
        original = kernel.install
        def mutate(*args, **kwargs):
            result = original(*args, **kwargs)
            path = self.obj/'installed.json'
            record = copy.deepcopy(self.record); record['installed_utc'] = '2026-01-01T00:00:00+00:00'
            path.chmod(0o644); path.write_text(json.dumps(record)); path.chmod(0o444)
            return result
        with mock.patch.object(kernel, 'install', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'while freezing'):
                native.copy_kernel_input(self.f.root, self.destination, self.identifier, self.digest)

    def test_origin_drop_is_detected_even_when_artifact_is_unchanged(self):
        original = kernel.install
        def drop(*args, **kwargs):
            kwargs.pop('acquisition', None)
            return original(*args, **kwargs)
        with mock.patch.object(kernel, 'install', side_effect=drop):
            with self.assertRaisesRegex(ValueError, 'origin or encoding'):
                native.copy_kernel_input(self.f.root, self.destination, self.identifier, self.digest)

    def test_origin_evidence_does_not_silently_accept_another_record(self):
        with self.assertRaisesRegex(ValueError, 'origin differs'):
            native.check_kernel_installation(self.record, dict(kernel_installation_digest=self.digest,
                                                               kernel_acquisition=None))


if __name__ == '__main__':unittest.main()
