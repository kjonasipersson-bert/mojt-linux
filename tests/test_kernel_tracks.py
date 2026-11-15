# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pinned track selection and additive, backward-compatible package metadata."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import test_kernel_build as fixtures
import test_mojt_artifact as artifacts
import mojt_system as system


class TrackTests(unittest.TestCase):
    def test_both_tracks_pin_exact_commits_and_separate_module_releases(self):
        lts=fixtures.kernel.read_plan(fixtures.REPO/'manifests/kernel-lts.json')
        stable=fixtures.kernel.read_plan(fixtures.REPO/'manifests/kernel-stable.json')
        self.assertEqual((lts['track'],lts['version'],lts['source']['commit']),('linux-kernel-lts','6.18.63','1cdda838e8475edf89b73ff0cc952005dd0b1fa7'))
        self.assertEqual((stable['track'],stable['version'],stable['source']['commit']),('linux-kernel','7.3.4','7595a62d45ee1a2297eafa5f2ef5d0a45142d84d'))
        self.assertNotEqual(lts['version']+lts['localversion'],stable['version']+stable['localversion'])
        for p in (lts,stable):self.assertEqual(p['source']['tag'],'v'+p['version'])
        for name in ('manifests/kernel-lts.json','manifests/kernel-stable.json'):self.assertIn(name,system.MBT_SOURCE_FILES)

    def test_public_track_resolves_bundled_plan_without_fetching_or_executing(self):
        for name,recipe in [('linux-kernel-lts','kernel-lts.json'),('linux-kernel','kernel-stable.json')]:
            with mock.patch.object(fixtures.kernel,'build') as build:
                fixtures.kernel.main(['--track',name,'--config','/seed','--config-sha256','0'*64,'--environment','/env','--output','/out','--dry-run'])
            self.assertEqual(build.call_args.args[0].plan,fixtures.REPO/'manifests'/recipe)

    def test_unknown_track_is_not_silently_treated_as_stable(self):
        with tempfile.TemporaryDirectory() as t:
            value=json.loads((fixtures.REPO/'manifests/kernel-lts.json').read_text());value['track']='linux-next'
            p=Path(t)/'plan.json';p.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'unsupported Kernel track'):fixtures.kernel.read_plan(p)


if __name__=='__main__':unittest.main()
