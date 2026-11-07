# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Capability declarations, measured code and real persistent defaults evidence."""
import copy
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
import mojt_system as system
import mojt_system_manifest as manifests
import mpm_base as base
import mpm_defaults as defaults
import mpm_management as management
from test_mpm_base import Fixture


def required_action(**changes):
    return dict(type='missing-default', version=1, phase='initialize', contract=defaults.PLAN, **changes)


def registry_context():
    return management.context(registries=[dict(family='mpm-defaults', version=1, capabilities=[], evidence='sha256:' + '1' * 64)])


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), stat.S_IMODE(p.stat().st_mode))
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


class ProfileFixture:
    def profile(self, work):
        profile = work / 'system-B';(profile / 'tools').mkdir(parents=True)
        for name in system.MPM_FILES:shutil.copy2(REPO / 'tools' / name, profile / 'tools' / name)
        return profile

    def measure(self, profile, *, evidence=None):
        if evidence is None:evidence = management.produce(profile / 'tools', system.MPM_FILES)
        (profile / management.FILENAME).write_text(json.dumps(evidence))
        inventory = {}
        for file in profile.rglob('*'):
            name = file.relative_to(profile).as_posix()
            if file.is_dir():inventory[name] = dict(directory=True, mode=stat.S_IMODE(file.stat().st_mode))
            else:inventory[name] = dict(sha256=management.file_hash(file), mode=stat.S_IMODE(file.stat().st_mode))
        return manifests.create(dict(label=profile.name, architecture=os.uname().machine,
            requirements=dict(base_abi={'libc': 'glibc'}, state_layout=1),
            support=dict(ports=dict(read=[], write=[], capabilities=[])), provides=[],
            artifacts={'fixture': {'object': 'opaque'}}, provenance={'fixture': True}, profile=inventory))


class ModelTests(unittest.TestCase):
    def test_actual_runtime_matches_declared_bounded_handler_without_mutating_inputs(self):
        actual = management.current()
        self.assertEqual(actual['description']['management'], defaults.MANAGEMENT_SUPPORT)
        self.assertEqual(actual['description']['handlers'], defaults.HANDLER_SUPPORT)
        self.assertEqual(actual['description']['state'], [])
        context = management.context(actions=[required_action()]);before = copy.deepcopy((actual, context))
        self.assertTrue(management.check_transition(actual, actual, context)['compatible'])
        self.assertEqual((actual, context), before)

    def test_old_reader_or_writer_fails_even_if_other_runtime_supports_registry(self):
        current = management.current();observed = registry_context()
        for operation in ('read', 'write'):
            changed = copy.deepcopy(current['description'])
            changed['management'][0][operation] = []
            if operation == 'read':changed['management'][0]['write'] = []
            old = management.create(changed)
            for preparing, candidate, role in ((old, current, 'preparing'), (current, old, 'candidate')):
                with self.subTest(operation=operation, role=role):
                    result = management.check_transition(preparing, candidate, observed)
                    self.assertFalse(result['compatible'])
                    self.assertTrue(any(e.startswith(role + ':') and operation in e for e in result['errors']))

    def test_future_handler_phase_and_generic_contract_are_not_advertised(self):
        current = management.current()
        for changes in (dict(type='ensure-account'), dict(version=2), dict(phase='stage'), dict(contract='mojt-lifecycle-set-v1')):
            action = dict(required_action(), **changes)
            result = management.check_transition(current, current, management.context(actions=[action]))
            self.assertFalse(result['compatible']);self.assertIn('required handler unsupported', result['errors'][0])

    def test_candidate_claim_does_not_give_preparing_manager_new_handler_support(self):
        current = management.current();required = dict(required_action(), type='ensure-account')
        claimed = copy.deepcopy(current['description']);claimed['handlers'] = [required]
        report = management.check_transition(current, management.create(claimed), management.context(actions=[required]))
        self.assertFalse(report['compatible']);self.assertTrue(all(e.startswith('preparing:') for e in report['errors']))

    def test_managed_state_requires_exact_owner_path_family_and_read_write_version(self):
        current = management.current();d = copy.deepcopy(current['description'])
        row = dict(owner='demo', namespace='var', path='lib/demo', family='demo-data', read=[1], write=[1])
        d['state'] = [row];supported = management.create(d)
        fact = dict(owner='demo', namespace='var', path='lib/demo', family='demo-data', version=1, evidence='sha256:' + '2' * 64)
        self.assertTrue(management.check(supported, management.context(state=[fact]))['compatible'])
        for changes in (dict(owner='other'), dict(path='lib/demo/child'), dict(family='other'), dict(version=2)):
            report = management.check(supported, management.context(state=[dict(fact, **changes)]))
            self.assertFalse(report['compatible'])
        self.assertFalse(management.check(current, management.context(state=[fact]))['compatible'])
        d['state'][0]['write'] = []
        self.assertFalse(management.check(management.create(d), management.context(state=[fact]))['compatible'])

    def test_unknown_versions_bad_lists_overlap_and_forged_hash_refused(self):
        current = management.current()
        for value in (dict(current, format='future'), dict(current, id='sha256:' + '0' * 64)):
            with self.assertRaises(ValueError):management.validate(value)
        for read, write in (([True], []), ([2, 1], [1]), ([1], [2]), ([1, 1], [1])):
            d = copy.deepcopy(current['description']);d['management'][0].update(read=read, write=write)
            with self.assertRaises(ValueError):management.create(d)
        d = copy.deepcopy(current['description'])
        row = dict(owner='a', namespace='var', path='lib/a', family='data', read=[1], write=[1])
        d['state'] = [row, dict(row, owner='b', path='lib/a/child')]
        with self.assertRaisesRegex(ValueError, 'ownership'):management.create(d)
        with self.assertRaises(ValueError):management.context(registries=[dict(family='x', version=True, capabilities=[], evidence='sha256:' + '3' * 64)])

    def test_missing_declaration_means_unknown_not_capable(self):
        self.assertTrue(management.check(None, management.context())['compatible'])
        self.assertFalse(management.check(None, registry_context())['compatible'])
        self.assertFalse(management.check(None, management.context(actions=[required_action()]))['compatible'])


class MeasuredProfileTests(ProfileFixture, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name);self.candidate = self.profile(self.work)
        self.manifest = self.measure(self.candidate)

    def test_export_and_retained_reader_are_deterministic_and_read_only(self):
        before = snapshot(self.work)
        first = management.retained(self.candidate, self.manifest)
        self.assertEqual(first, management.produce(self.candidate / 'tools', system.MPM_FILES))
        self.assertEqual(snapshot(self.work), before)

    def test_metadata_cannot_claim_support_absent_from_bundled_code(self):
        evidence = management.produce(self.candidate / 'tools', system.MPM_FILES)
        evidence['description']['management'][0]['write'] = [1, 2]
        evidence['description']['management'][0]['read'] = [1, 2]
        evidence = management.create(evidence['description'])
        manifest = self.measure(self.candidate, evidence=evidence)
        with self.assertRaisesRegex(ValueError, 'declarations differ'):management.retained(self.candidate, manifest)

    def test_changed_helper_linked_code_and_unmeasured_sidecar_refused(self):
        helper = self.candidate / 'tools/mpm_defaults.py';original = helper.read_bytes()
        helper.write_bytes(original + b'\n# modified\n')
        with self.assertRaisesRegex(ValueError, 'code differs'):management.retained(self.candidate, self.manifest)
        helper.write_bytes(original)
        outside = self.work / 'outside.py';shutil.copyfile(helper, outside);helper.unlink();helper.symlink_to(outside)
        with self.assertRaises(ValueError):management.retained(self.candidate, self.manifest)
        d = copy.deepcopy(self.manifest['description']);del d['profile'][management.FILENAME]
        with self.assertRaisesRegex(ValueError, 'unmeasured'):management.retained(self.candidate, manifests.create(d))

    def test_measurement_never_imports_candidate_python_or_uses_it_as_handler(self):
        marker = self.work / 'executed'
        helper = self.candidate / 'tools/mpm_defaults.py'
        with helper.open('a') as file:file.write(f'\n__import__("pathlib").Path({str(marker)!r}).write_text("executed")\n')
        value = management.produce(self.candidate / 'tools', system.MPM_FILES)
        self.assertEqual(value['description']['handlers'], defaults.HANDLER_SUPPORT)
        self.assertFalse(marker.exists())

    def test_incomplete_or_unknown_literal_support_is_not_guessed_from_filenames(self):
        helper = self.candidate / 'tools/mpm_defaults.py';original = helper.read_text()
        helper.write_text(original.replace('MANAGEMENT_SUPPORT =', 'MISSING_SUPPORT ='))
        with self.assertRaisesRegex(ValueError, 'literal manager declaration'):management.produce(self.candidate / 'tools', system.MPM_FILES)
        helper.write_text(original.replace("'read': [1]", "'read': __import__('os').getuid()"))
        with self.assertRaises(ValueError):management.produce(self.candidate / 'tools', system.MPM_FILES)


@unittest.skipUnless(os.geteuid() == 0 and shutil.which('zstd') and shutil.which('tar'), 'real root-owned registry requires root and archive tools')
class TargetTests(ProfileFixture, Fixture):
    def setUp(self):
        super().setUp();self.install()
        for name in ('state/etc', 'state/var/lib/mojt'):(self.root / name).mkdir(parents=True)
        self.candidate = self.profile(self.work)
        self.manifest = self.measure(self.candidate)

    def initialize(self):
        plan = defaults.prepare(self.root, self.body['id'], ['hostname'])
        defaults.initialize(self.root, plan, yes=True)
        return plan

    def test_absent_state_creates_no_registry_or_locks_and_restores_python_search_path(self):
        before = snapshot(self.work);path = sys.path[:]
        report = management.check_target(self.root, self.candidate, self.manifest)
        self.assertTrue(report['compatible']);self.assertEqual(report['observed']['description']['registries'], [])
        self.assertEqual(sys.path, path);self.assertEqual(snapshot(self.work), before)

    def test_real_state_blocks_older_writer_without_any_target_writes(self):
        self.initialize();helper = self.candidate / 'tools/mpm_defaults.py'
        helper.write_text(helper.read_text().replace("'write': [1]", "'write': []"))
        self.manifest = self.measure(self.candidate)
        before = snapshot(self.work)
        report = management.check_target(self.root, self.candidate, self.manifest)
        self.assertFalse(report['compatible']);self.assertTrue(any('unsupported for write' in e for e in report['errors']))
        self.assertEqual(snapshot(self.work), before)

    def test_valid_previous_handler_code_identity_remains_readable_not_executable_authority(self):
        previous = copy.deepcopy(defaults.handler())
        previous['implementation']['identity']['files']['mpm_defaults.py'] = 'e' * 64
        with mock.patch.object(defaults, 'handler', return_value=previous):plan = self.initialize()
        before = snapshot(self.work)
        report = management.check_target(self.root, self.candidate, self.manifest)
        self.assertTrue(report['compatible']);self.assertEqual(len(report['observed']['description']['registries']), 1)
        self.assertEqual(snapshot(self.work), before)
        with self.assertRaisesRegex(ValueError, 'prepare again'):defaults.initialize(self.root, plan, yes=True)

    def test_unknown_registry_version_symlinks_and_corrupt_records_not_treated_as_absence(self):
        path = self.root / 'state/var/lib/mojt/lifecycle';path.mkdir();(path / 'defaults-v2').mkdir()
        with self.assertRaisesRegex(ValueError, 'unsupported lifecycle registry'):management.check_target(self.root, self.candidate, self.manifest)
        (path / 'defaults-v2').rmdir();path.rmdir();path.symlink_to(self.work)
        with self.assertRaises(ValueError):management.check_target(self.root, self.candidate, self.manifest)
        path.unlink();plan = self.initialize();scope = defaults.location(self.root, plan)
        run = next(p for p in scope.iterdir() if p.is_dir())
        result = run / '000002.json';result.write_bytes(result.read_bytes().replace(b'completed', b'corrupted'))
        with self.assertRaises(ValueError):management.check_target(self.root, self.candidate, self.manifest)

    def test_interrupted_preparation_blocks_transition_until_explicit_reconciliation(self):
        plan = defaults.prepare(self.root, self.body['id'], ['hostname'])
        with mock.patch.object(defaults, '_apply', side_effect=OSError('injected interruption')), self.assertRaises(OSError):
            defaults.initialize(self.root, plan, yes=True)
        before = snapshot(self.work)
        with self.assertRaisesRegex(ValueError, 'reconcile explicitly'):management.check_target(self.root, self.candidate, self.manifest)
        self.assertEqual(snapshot(self.work), before)
        defaults.initialize(self.root, plan, yes=True, reconcile=True)
        self.assertTrue(management.check_target(self.root, self.candidate, self.manifest)['compatible'])

    def test_both_preparing_and_candidate_runtimes_checked_for_required_action(self):
        required = management.context(actions=[required_action()])
        self.assertTrue(management.check_target(self.root, self.candidate, self.manifest, required=required)['compatible'])
        unsupported = management.context(actions=[dict(required_action(), type='ensure-account')])
        report = management.check_target(self.root, self.candidate, self.manifest, required=unsupported)
        self.assertFalse(report['compatible'])
        self.assertTrue(any(e.startswith('preparing:') for e in report['errors']))
        self.assertTrue(any(e.startswith('candidate:') for e in report['errors']))
