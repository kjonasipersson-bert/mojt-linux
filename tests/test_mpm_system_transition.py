# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Three focused System preflight cases; real retained files, no guest/provider execution."""
import copy
import os
from pathlib import Path
import shutil
import unittest
from unittest import mock

from test_mpm_system import REPO
import mojt_artifact as artifact
import mojt_system as legacy
import mojt_system_manifest as manifests
import mojt_system_package as packer
import mpm_base as base
import mpm_nix_binary as nix
from mpm_nix_boot import NixBootAdapter
import mpm_management as management
import mpm_system as system
import mpm_system_transition as transition


class ReviewTests(unittest.TestCase):
    def test_tooling_only_policy_and_exact_provider_preservation_are_pure(self):
        old = manifests.create(dict(label='same-label', architecture='x86_64',
            requirements=dict(base_abi={'libc':'glibc'}, state_layout=1), support=dict(ports=dict(read=[], write=[], capabilities=[])),
            provides=[], artifacts={'fixture':True}, provenance={'fixture':True},
            profile={'setup':{'sha256':'a'*64,'mode':0o755},'tools/admin.py':{'sha256':'b'*64,'mode':0o644}}))
        d = copy.deepcopy(old['description']);d['profile']['tools/admin.py'] = {'sha256':'c'*64,'mode':0o444}
        d['profile']['setup']['mode'] = 0o555
        candidate = manifests.create(d);before = copy.deepcopy((old, candidate))
        self.assertTrue(transition.tooling_review(old, candidate)['description']['compatible'])
        self.assertEqual((old, candidate), before)
        builder = copy.deepcopy(candidate['description'])
        builder['profile'].update({'bin/mbt':{'sha256':'f'*64,'mode':0o755},
            'mbt-runtime.json':{'sha256':'f'*64,'mode':0o644},
            'share/mbt':{'directory':True,'mode':0o755},
            'share/mbt/kernel-first-build.json':{'sha256':'f'*64,'mode':0o644},
            'share/man/man1/mbt.1':{'sha256':'f'*64,'mode':0o644}})
        self.assertTrue(transition.tooling_review(old,manifests.create(builder))['description']['compatible'])
        self.assertTrue(transition.tooling_review(manifests.create(builder),old)['description']['compatible'])
        d['profile']['setup']['sha256'] = 'd'*64
        report = transition.tooling_review(old, manifests.create(d))['description']
        self.assertFalse(report['compatible']);self.assertIn('setup', report['blockers'])
        output = '/nix/store/' + 'a'*32 + '-runtime'
        row = dict(path=output,nar_hash='sha256:'+'a'*52)
        ref = dict(provider='nix', identity=dict(format='mojt-nix-output-v1', output=output, closure=[row], commands=[]))
        def forbidden(args):raise AssertionError('no provider command allowed during pure preservation comparison')
        adapter = NixBootAdapter('/pinned/nix-store', forbidden)
        self.assertTrue(adapter.preserves([ref], {'objects':[row]})['compatible'])
        native=dict(format='mojt-system-provider-baseline-v1',references=[ref,ref])
        self.assertTrue(adapter.preserves([ref],native)['compatible'])
        self.assertFalse(adapter.preserves([],native)['compatible'])
        self.assertFalse(adapter.preserves([], {'objects':[row]})['compatible'])
        changed = copy.deepcopy(ref);changed['identity']['closure'][0]['nar_hash'] = 'sha256:'+'b'*52
        self.assertFalse(adapter.preserves([changed], {'objects':[row]})['compatible'])
        self.assertFalse(adapter.preserves([changed],native)['compatible'])
        with self.assertRaisesRegex(ValueError,'conflicting selected'):
            adapter.preserves([ref],dict(native,references=[ref,changed]))
        denied=transition.providers(old,candidate,[ref],{'nix':adapter},baseline_refs=[ref])
        self.assertFalse(denied['compatible'])
        self.assertTrue(any('provider runtime change' in e for e in denied['errors']))
        def delivered(value):
            d=copy.deepcopy(value['description']);d['profile']['tools/mpm_nix_binary.py']={'sha256':'e'*64,'mode':0o444}
            return manifests.create(d)
        self.assertTrue(transition.providers(delivered(old),delivered(candidate),[ref],{'nix':adapter},baseline_refs=[ref])['compatible'])
        unknown=dict(ref,provider='native')
        self.assertFalse(transition.providers(old,candidate,[unknown],{},baseline_refs=[unknown])['compatible'])


class Adapter:
    """Guest-tree fixture; production selects the retained Nix adapter instead."""
    def __init__(self, root, reference):self.root = root;self.reference = reference
    def describe(self, ref, root):
        if ref != self.reference:raise ValueError('wrong fixture dependency')
        return dict(reference=copy.deepcopy(ref), commands={})
    def contains(self, ref, value):
        return ref == self.reference and '..' not in Path(value).parts and any(
            value == row['path'] or value.startswith(row['path'] + '/') for row in ref['identity']['objects'])
    def ensure(self, ref, root):self.verify(ref, root)
    def verify(self, ref, root):
        self.describe(ref, root)
        for row in ref['identity']['objects']:
            if legacy.tree_hash(self.root / row['path'].lstrip('/')) != row['tree_sha256']:raise ValueError('fixture store changed')
    def verify_path(self, ref, value, *, executable=False):
        if not self.contains(ref, value):raise ValueError('outside fixture closure')
        path = legacy.virtual_file(self.root, value)
        if not path.exists() or executable and (not path.is_file() or not path.stat().st_mode & 1):raise ValueError('fixture path unavailable')
    def preserves(self, refs, baseline):
        if baseline.get('format') == 'mojt-system-provider-baseline-v1':
            baseline={'objects':baseline['references'][0]['identity']['objects']}
        return dict(compatible=refs == [self.reference] and baseline['objects'] == self.reference['identity']['objects'],
                    policy='fixture-exact', runtime_files=['tools/mpm_nix_binary.py'])


@unittest.skipUnless(os.geteuid() == 0 and shutil.which('zstd') and shutil.which('cpio') and shutil.which('tar'), 'real retained disk preflight requires root/archive tools')
class DiskTests(unittest.TestCase):
    def setUp(self):
        from test_kernel_boot import KernelBootTests
        self.f = KernelBootTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root = self.f.root;self.counter = 0
        base.install(self.root, self.f.fixture.args.base_package, self.f.fixture.base['id'], yes=True)
        self.selected = base.read(self.root / 'system/native-fixture/manifest.json')
        self.ref = dict(provider='nix', identity=dict(format='fixture-v1', objects=self.selected['description']['artifacts']['nix']['objects']))
        self.adapter = Adapter(self.root, self.ref);self.adapters = {'nix':self.adapter}
        self.identifier = self.candidate()

    def candidate(self, service_change=False):
        self.counter += 1;work = self.f.fixture.work / ('system-change-' + str(self.counter));work.mkdir()
        profile = work / 'input/system/native-fixture';profile.parent.mkdir(parents=True)
        shutil.copytree(self.root / 'system/native-fixture', profile, symlinks=True)
        with (profile / 'tools/mpm_cli.py').open('a') as stream:stream.write('\n# Synthetic next tooling revision.\n')
        (profile / 'bin/diagnose').write_text('#!/bin/sh\necho synthetic\n');(profile / 'bin/diagnose').chmod(0o755)
        if service_change:
            unit = profile / 'units/NetworkManager.service'
            if unit.is_symlink():unit.unlink()
            unit.write_text('[Service]\nExecStart=/new-service-contract\n')
            with (profile / 'tools/mpm_nix_binary.py').open('a') as stream:stream.write('\n# Different provider implementation.\n')
        # Tooling revisions now include measured boot/frontend code. Regenerate
        # its declaration instead of keeping the previous code's support record.
        (profile/management.FILENAME).write_bytes(artifact.canonical(management.produce(profile/'tools',legacy.MPM_FILES))+b'\n')
        d = copy.deepcopy(self.selected['description']);d['profile'] = system.inventory(profile)
        d['provides'] = sorted(set(d['provides']) | {'/run/mojt-system/bin/diagnose'})
        manifest = manifests.create(d);(profile / 'manifest.json').write_bytes(artifact.canonical(manifest))
        kit = work / 'kit'
        with mock.patch.object(packer, 'nix_references', return_value=[self.ref]):
            result = packer.package(work / 'input', 'native-fixture', '0.2.0', self.counter, kit, adapter=self.adapter)
        generation = artifact.read_json(kit / 'generation/archive.json');component = artifact.read_json(kit / 'component/archive.json')
        system.install(self.root, kit / 'generation' / generation['file'], generation['artifact'],
            dependency_files=[kit / 'component' / component['file']], yes=True, adapters=self.adapters)
        return result['kit']['description']['generation']

    def plan(self, identifier=None):
        return transition.prepare(self.root, identifier or self.identifier, baseline=self.f.baseline, adapters=self.adapters)

    def test_exact_installed_system_plan_preserves_base_kernel_state_and_menu_without_writes(self):
        before = self.f.snapshot();plan = self.plan();d = base.envelope(plan, transition.FORMAT)
        self.assertTrue(d['checks']['compatible'], d['checks']['errors'])
        self.assertEqual(d['candidate_system']['artifact'], self.identifier)
        selected = self.f.entries[self.f.old_id]['record']['description']
        self.assertEqual({k:d['retained_base'][k] for k in ('artifact','release')}, selected['base'])
        self.assertEqual(d['retained_kernel'], selected['kernel'])
        self.assertEqual(d['selected'], self.f.old_id);self.assertFalse(d['writes'] or d['effects'] or d['stage_ready'] or d['boot_ready'])
        self.assertEqual(transition.recheck(self.root, plan, adapters=self.adapters), plan)
        self.assertEqual(self.f.snapshot(), before)

    def test_service_change_blocks_and_persistent_account_edit_invalidates_the_old_plan(self):
        plan = self.plan();candidate = self.candidate(service_change=True)
        before = self.f.snapshot();d = self.plan(candidate)['description']
        self.assertFalse(d['checks']['compatible'])
        self.assertIn('units/NetworkManager.service', d['checks']['startup']['description']['blockers'])
        self.assertTrue(any('provider runtime change' in e for e in d['checks']['providers']['errors']))
        self.assertEqual(self.f.snapshot(), before)
        plan = self.plan()
        passwd = self.root / 'state/etc/passwd';passwd.write_text(passwd.read_text().replace('root:x:0:0:root:', 'root:x:0:0:edited label:'))
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            transition.recheck(self.root, plan, adapters=self.adapters)
