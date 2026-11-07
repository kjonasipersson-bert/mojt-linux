# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Three focused System/provider joins; no Nix store or VM is required."""
import copy
import os
import shutil
from types import SimpleNamespace
import unittest

from test_mpm_system import Fixture, pack, spec, tree
import mpm_base as base
import mpm_management as management
import mpm_system as system
import mpm_system_cli as cli
import mpm_system_model as model


class Adapter:
    def __init__(self):self.events = [];self.present = False;self.fail = False
    def describe(self, ref, root):
        if ref != {'provider':'fixture', 'identity':{'release':'exact-1'}}:raise ValueError('changed identity')
        self.events.append('describe');return dict(reference=copy.deepcopy(ref), commands={})
    def ensure(self, ref, root):
        self.events.append('ensure')
        if self.fail:raise OSError('injected provider failure')
        self.present = True
    def verify(self, ref, root):
        self.events.append('verify')
        if not self.present:raise ValueError('provider dependency damaged')


class ProviderFixture(Fixture):
    def setUp(self):
        super().setUp()
        self.provider = {'provider':'fixture', 'identity':{'release':'exact-1'}}
        result = pack(self.work / 'component-source', spec('component', dependencies=[self.provider]), self.work / 'provider-component')
        self.component = result['artifact'];self.component_archive = self.work / 'provider-component' / result['archive']['file']
        self.reference = dict(provider='native', artifact=self.component['id'])
        d = copy.deepcopy(self.composition['description'])
        d['components'][0]['reference'] = self.reference
        for mapping in d['profile']:mapping['source']['reference'] = self.reference
        self.composition = base.record(model.FORMAT, d)
        self.archive, self.body = self.package()
        self.adapter = Adapter();self.adapters = {'fixture':self.adapter}


@unittest.skipUnless(shutil.which('zstd'), 'requires archive codec')
class PreviewTests(ProviderFixture):
    def test_preview_is_pure_missing_adapter_blocks_and_offline_cli_cannot_use_host_nix(self):
        result = self.install(dry_run=True, adapters=self.adapters)
        self.assertEqual(result['plan']['description']['providers'], [self.provider])
        self.assertEqual(self.adapter.events, ['describe']);self.assertEqual(tree(self.root), {})
        with self.assertRaisesRegex(ValueError, 'adapter required'):self.install(dry_run=True)
        with self.assertRaisesRegex(ValueError, 'offline provider'):
            cli.ProviderAdapters(None)['nix']
        helpers = self.work / 'helpers';helpers.mkdir();(helpers / 'nix-store').symlink_to('/bin/sh')
        adapter = cli.ProviderAdapters(SimpleNamespace(system_bin=helpers))['nix']
        self.assertEqual(adapter.binary, str(helpers / 'nix-store'))
        self.assertEqual(adapter.executable, str((helpers / 'nix-store').resolve()))
        self.assertEqual(tree(self.root), {});self.assertFalse(self.marker.exists())


@unittest.skipUnless(os.geteuid() == 0 and shutil.which('zstd'), 'numeric-owner install requires root')
class InstallTests(ProviderFixture):
    def test_install_noop_verified_status_and_management_bind_exact_provider_dependency(self):
        self.assertTrue(self.install(adapters=self.adapters)['changed'])
        self.assertEqual(self.adapter.events.count('ensure'), 1)
        self.assertEqual(system.object_record(self.root, self.component['id'])[1]['description']['dependencies'], [self.provider])
        observed = management.observe_target(self.root)['description']['registries']
        self.assertEqual(observed[-1]['capabilities'], ['exact-provider-dependencies'])
        old = management.current();old['description']['management'][-1]['capabilities'] = []
        old = management.create(old['description'])
        self.assertFalse(management.check_transition(management.current(), old, management.observe_target(self.root))['compatible'])
        before = tree(self.root);self.adapter.events.clear()
        self.archive.unlink();self.component_archive.unlink()
        self.assertFalse(system.install(self.root, None, self.body['id'], yes=True, adapters=self.adapters)['changed'])
        self.assertNotIn('ensure', self.adapter.events);self.assertEqual(tree(self.root), before)
        self.adapter.present = False
        self.assertEqual(len(system.status(self.root)['installed']), 1)
        with self.assertRaisesRegex(ValueError, 'dependency damaged'):system.status(self.root, verify=True, adapters=self.adapters)
        with self.assertRaisesRegex(ValueError, 'dependency damaged'):system.install(self.root, None, self.body['id'], yes=True, adapters=self.adapters)
        self.assertEqual(tree(self.root), before)

    def test_failed_provider_import_retains_native_inputs_and_explicit_retry_finishes(self):
        self.adapter.fail = True
        with self.assertRaisesRegex(OSError, 'provider failure'):self.install(adapters=self.adapters)
        status = system.status(self.root)
        self.assertEqual(status['installed'], []);self.assertEqual(len(status['retained']), 1)
        self.archive.unlink();self.component_archive.unlink();self.adapter.fail = False
        self.assertTrue(system.install(self.root, None, self.body['id'], yes=True, adapters=self.adapters)['changed'])
        self.assertEqual(len(system.status(self.root, verify=True, adapters=self.adapters)['installed']), 1)
        self.assertFalse(self.marker.exists())
