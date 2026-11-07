# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Bounded defaults, local edits and real publication fault boundaries."""
import copy
import errno
import hashlib
import os
from pathlib import Path
import shutil
import stat
import sys
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
import mojt_artifact as artifact
import mpm_base as base
import mpm_defaults as defaults
import mpm_transaction as tx
from test_mpm_base import Fixture, entry


def synthetic_plan():
    return base.record(defaults.PLAN, dict(installation='1' * 32, owner='sha256:' + '2' * 64,
        realization='sha256:' + '3' * 64, target=dict(root='/offline', root_identity=dict(device=1, inode=2),
        etc=dict(device=1, inode=3), state=dict(device=1, inode=4)), handler=defaults.handler(),
        actions=[dict(path='hostname', source=dict(reference=dict(provider='native', artifact='sha256:' + '2' * 64),
        path='usr/etc/hostname', sha256='4' * 64), uid=0, gid=0, mode=0o644)]))


class ContractTests(unittest.TestCase):
    def test_paths_literal_and_special_state_files_rejected(self):
        for path in ('../bad', '/absolute', 'a//b', 'a/./b', 'a/../b', 'a/', 'a\\b', 'a:b',
                     'a\nb', 'passwd', 'shadow', 'group', 'gshadow', 'machine-id', 'os-release'):
            with self.subTest(path=path), self.assertRaises(ValueError):defaults.relative(path)
        self.assertEqual(defaults.relative('systemd/local.conf'), ['systemd', 'local.conf'])

    def test_unprivileged_or_unapproved_call_cannot_touch_target(self):
        with mock.patch.object(defaults.os, 'geteuid', return_value=1000), \
             mock.patch.object(defaults, '_validated') as validated, self.assertRaisesRegex(ValueError, 'administrator'):
            defaults.initialize('/absent', {}, yes=True)
        validated.assert_not_called()
        with mock.patch.object(defaults.os, 'geteuid', return_value=0), self.assertRaisesRegex(ValueError, 'approval'):
            defaults.initialize('/absent', {}, yes=False)

    def test_result_identity_and_closed_fact_vocabulary(self):
        plan = synthetic_plan();approval = defaults._approval(plan);run = '5' * 32
        start = defaults._result(plan, approval, run)
        check = defaults._check(dict(namespace='etc', path='hostname', sha256='4' * 64,
                                    uid=0, gid=0, mode=0o644), 'created')
        end = defaults._result(plan, approval, run, previous=start['id'], checks=[check])
        defaults._validate_result(start, plan, approval, run, 1, None)
        defaults._validate_result(end, plan, approval, run, 2, start['id'])
        for field, value in (('invocation', 'sha256:' + '6' * 64), ('approval', 'sha256:' + '6' * 64),
                             ('sequence', True), ('status', 'ready'), ('checks', [])):
            d = copy.deepcopy(end['description']);d[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                defaults._validate_result(base.record(defaults.RESULT, d), plan, approval, run, 2, start['id'])
        for change in (dict(path='other'), dict(sha256='f' * 64), dict(uid=True), dict(mode=0o666), dict(secret='not-allowed')):
            d = copy.deepcopy(end['description']);facts = dict(check['facts'], **change)
            d['checks'] = [defaults._check({k:v for k,v in facts.items() if k != 'outcome'}, 'created')]
            with self.subTest(change=change), self.assertRaises(ValueError):
                defaults._validate_result(base.record(defaults.RESULT, d), plan, approval, run, 2, start['id'])

    def test_invocation_binds_plan_not_time_or_random_run(self):
        plan = synthetic_plan()
        self.assertEqual(defaults.invocation(plan), defaults.invocation(copy.deepcopy(plan)))
        for field, value in (('owner', 'sha256:' + '6' * 64), ('installation', '7' * 32), ('handler', {})):
            d = copy.deepcopy(plan['description']);d[field] = value
            self.assertNotEqual(defaults.invocation(plan), defaults.invocation(base.record(defaults.PLAN, d)))


@unittest.skipUnless(os.geteuid() == 0 and shutil.which('zstd') and shutil.which('tar'),
                     'real root-owned Base/default effects require root, zstd and GNU tar')
class PreparationTests(Fixture):
    def setUp(self):
        super().setUp();self.install()
        for name in ('state/etc', 'state/var/lib/mojt'):
            (self.root / name).mkdir(parents=True, mode=0o755)
        self.plan = defaults.prepare(self.root, self.body['id'], ['hostname'])

    def apply(self, **options):return defaults.initialize(self.root, self.plan, yes=True, **options)
    def status(self):return defaults.status(self.root, self.plan)
    def registry(self):return defaults.location(self.root, self.plan)
    def destination(self):return self.root / 'state/etc/hostname'

    def test_preview_and_status_create_no_registry_locks_or_defaults(self):
        before = {str(p.relative_to(self.root)) for p in self.root.rglob('*')}
        state = self.status()
        self.assertEqual(state['attempts'], []);self.assertEqual(state['observed'], [None])
        self.assertFalse(self.destination().exists());self.assertFalse((self.root / defaults.REGISTRY).exists())
        self.assertEqual(before, {str(p.relative_to(self.root)) for p in self.root.rglob('*')})

    def test_creation_checks_and_exact_repeat_without_event(self):
        result = self.apply();self.assertTrue(result['changed'] and result['evidence_written'])
        self.assertEqual(self.destination().read_bytes(), b'mojt-default\n')
        self.assertEqual(stat.S_IMODE(self.destination().stat().st_mode), 0o644)
        state = self.status();self.assertEqual(len(state['attempts']), 1)
        self.assertEqual(state['attempts'][0]['checks'][0]['facts']['outcome'], 'created')
        before = {str(p):p.read_bytes() for p in self.registry().rglob('*.json')}
        self.assertEqual(self.apply(), dict(changed=False, evidence_written=False, invocation=defaults.invocation(self.plan)))
        self.assertEqual(before, {str(p):p.read_bytes() for p in self.registry().rglob('*.json')})

    def test_existing_and_later_manual_edits_preserved_and_reobserved(self):
        self.destination().write_bytes(b'local host\n');self.destination().chmod(0o600)
        self.assertFalse(self.apply()['changed'])
        first = self.status()['attempts'][0]['checks'][0]['facts']
        self.assertEqual(first['outcome'], 'preserved');self.assertEqual(first['mode'], 0o600)
        self.destination().write_bytes(b'edited later\n')
        self.assertFalse(self.apply()['changed'])
        state = self.status();self.assertEqual(len(state['attempts']), 2)
        self.assertEqual(self.destination().read_bytes(), b'edited later\n')
        self.assertEqual(state['observed'][0]['sha256'], hashlib.sha256(b'edited later\n').hexdigest())

    def test_source_mode_retained_without_umask_dependency(self):
        archive, body = self.package(extra=[entry('usr/etc/private.conf', b'private\n', mode=0o600)])
        base.install(self.root, archive, body['id'], yes=True)
        plan = defaults.prepare(self.root, body['id'], ['private.conf'])
        old = os.umask(0o077)
        try:defaults.initialize(self.root, plan, yes=True)
        finally:os.umask(old)
        self.assertEqual(stat.S_IMODE((self.root / 'state/etc/private.conf').stat().st_mode), 0o600)

    def test_tampered_plan_or_copied_target_refused_before_effect(self):
        for field, value in (('installation', '9' * 32), ('handler', {}), ('owner', 'sha256:' + '0' * 64)):
            d = copy.deepcopy(self.plan['description']);d[field] = value
            with self.subTest(field=field), self.assertRaises((ValueError, FileNotFoundError)):
                defaults.initialize(self.root, base.record(defaults.PLAN, d), yes=True)
        d = copy.deepcopy(self.plan['description']);d['actions'][0]['source']['sha256'] = 'f' * 64
        with self.assertRaises(ValueError):defaults.initialize(self.root, base.record(defaults.PLAN, d), yes=True)
        with self.assertRaises(ValueError):defaults.initialize(self.root, base.record('unknown-v2', self.plan['description']), yes=True)
        copyroot = self.work / 'copy';shutil.copytree(self.root, copyroot, symlinks=True)
        with self.assertRaisesRegex(ValueError, 'target changed'):defaults.initialize(copyroot, self.plan, yes=True)
        self.assertFalse(self.destination().exists());self.assertFalse((self.root / defaults.REGISTRY).exists())

    def test_writable_or_linked_registry_ancestor_refused(self):
        path = self.root / 'state/var/lib/mojt/lifecycle';path.mkdir();path.chmod(0o777)
        with self.assertRaises(ValueError):self.apply()
        self.assertFalse(self.destination().exists())
        path.rmdir();outside = self.work / 'outside';outside.mkdir();path.symlink_to(outside)
        with self.assertRaises((ValueError, OSError)):self.apply()
        self.assertEqual(list(outside.iterdir()), [])

    def test_target_conflicts_never_followed(self):
        outside = self.work / 'outside';outside.write_bytes(b'keep\n')
        for variant in ('symlink', 'hardlink', 'directory', 'fifo', 'writable'):
            with self.subTest(variant=variant):
                target = self.destination()
                if variant == 'symlink':target.symlink_to(outside)
                elif variant == 'hardlink':os.link(outside, target)
                elif variant == 'directory':target.mkdir()
                elif variant == 'fifo':os.mkfifo(target)
                else:target.write_bytes(b'keep\n');target.chmod(0o666)
                with self.assertRaises((ValueError, OSError)):self.apply()
                if target.is_dir():target.rmdir()
                else:target.unlink()
                self.assertEqual(outside.read_bytes(), b'keep\n')
        self.assertFalse((self.root / defaults.REGISTRY).exists())

    def test_source_symlink_and_missing_target_parent_rejected(self):
        import tarfile
        archive, body = self.package(extra=[entry('usr/etc/nested'), entry('usr/etc/nested/a', b'hello\n', mode=0o644),
             entry('usr/etc/link', kind=tarfile.SYMTYPE, link='hostname')])
        base.install(self.root, archive, body['id'], yes=True)
        with self.assertRaises(FileNotFoundError):defaults.prepare(self.root, body['id'], ['nested/a'])
        (self.root / 'state/etc/nested').mkdir()
        plan = defaults.prepare(self.root, body['id'], ['nested/a'])
        defaults.initialize(self.root, plan, yes=True)
        self.assertEqual((self.root / 'state/etc/nested/a').read_bytes(), b'hello\n')
        with self.assertRaises(OSError):defaults.prepare(self.root, body['id'], ['link'])

    def test_started_write_failure_never_creates_default(self):
        original = defaults._write
        def fail(path, value):
            if path.name == '000001.json':raise OSError(errno.EIO, 'injected intent failure')
            return original(path, value)
        with mock.patch.object(defaults, '_write', side_effect=fail), self.assertRaises(OSError):self.apply()
        self.assertFalse(self.destination().exists());self.assertEqual(self.status()['attempts'][0]['state'], 'interrupted')
        with self.assertRaises((ValueError, FileNotFoundError)):self.apply(reconcile=True)

    def test_crash_after_effect_requires_reconciliation_and_preserves_edit(self):
        original = defaults._write
        def fail(path, value):
            if path.name == '000002.json':raise OSError(errno.EIO, 'injected completion failure')
            return original(path, value)
        with mock.patch.object(defaults, '_write', side_effect=fail), self.assertRaises(OSError):self.apply()
        self.assertEqual(self.status()['attempts'][0]['state'], 'interrupted')
        self.assertEqual(self.destination().read_bytes(), b'mojt-default\n')
        before = {str(p):p.read_bytes() for p in self.registry().rglob('*.json')}
        self.status();self.assertEqual(before, {str(p):p.read_bytes() for p in self.registry().rglob('*.json')})
        with self.assertRaisesRegex(ValueError, 'reconciliation'):self.apply()
        self.destination().write_bytes(b'local edit after interruption\n')
        self.assertFalse(self.apply(reconcile=True)['changed'])
        state = self.status();self.assertEqual(len(state['attempts']), 1)
        self.assertEqual(state['attempts'][0]['checks'][0]['facts']['outcome'], 'preserved')
        self.assertEqual(self.destination().read_bytes(), b'local edit after interruption\n')

    def test_pre_effect_interruption_can_resume_same_bounded_action(self):
        with mock.patch.object(defaults, '_apply', side_effect=OSError('injected before effect')), self.assertRaises(OSError):self.apply()
        self.assertFalse(self.destination().exists());self.assertTrue(self.apply(reconcile=True)['changed'])
        self.assertEqual(self.status()['attempts'][0]['state'], 'completed')

    def fault_after_link(self, filename):
        original = defaults.publish
        def fail(fd, name, data, **kw):
            if name == filename:
                sync = defaults.os.fsync
                def injected(file):
                    if file == fd:raise OSError(errno.EIO, 'injected directory fsync error')
                    return sync(file)
                with mock.patch.object(defaults.os, 'fsync', side_effect=injected):return original(fd, name, data, **kw)
            return original(fd, name, data, **kw)
        return mock.patch.object(defaults, 'publish', side_effect=fail)

    def test_post_link_failure_retains_default_and_interrupted_intent(self):
        with self.fault_after_link('hostname'), self.assertRaises(tx.PublicationUncertain):self.apply()
        self.assertEqual(self.destination().read_bytes(), b'mojt-default\n')
        self.assertEqual(self.status()['attempts'][0]['state'], 'interrupted')
        self.assertFalse(self.apply(reconcile=True)['changed'])

    def test_post_terminal_failure_retains_default_and_visible_evidence(self):
        with self.fault_after_link('000002.json'), self.assertRaises(tx.PublicationUncertain):self.apply()
        self.assertEqual(self.destination().read_bytes(), b'mojt-default\n')
        self.assertEqual(self.status()['attempts'][0]['state'], 'completed')
        self.assertFalse(self.apply()['evidence_written'])

    def test_no_overwrite_loses_to_concurrent_local_writer(self):
        original = defaults.publish
        def race(fd, name, data, **kw):
            if name == 'hostname':self.destination().write_bytes(b'concurrent local writer\n')
            return original(fd, name, data, **kw)
        with mock.patch.object(defaults, 'publish', side_effect=race):self.assertFalse(self.apply()['changed'])
        self.assertEqual(self.destination().read_bytes(), b'concurrent local writer\n')
        self.assertFalse(any(p.name.startswith('.mpm-default-') for p in self.destination().parent.iterdir()))

    def test_corrupt_or_forked_results_block_retry(self):
        self.apply();run = next(p for p in self.registry().iterdir() if p.is_dir())
        terminal = run / '000002.json';original = terminal.read_bytes()
        terminal.write_bytes(original.replace(b'completed', b'corrupted'))
        with self.assertRaises(ValueError):self.status()
        with self.assertRaises(ValueError):self.apply()
        terminal.write_bytes(original);(run / '000003.json').write_bytes(original)
        with self.assertRaises(ValueError):self.status()

    def test_interruption_immediately_after_link_is_uncertain(self):
        link = defaults.os.link
        def interrupted(src, dst, **kw):
            link(src, dst, **kw)
            if dst == 'hostname':raise KeyboardInterrupt('injected after link')
        with mock.patch.object(defaults.os, 'link', side_effect=interrupted), self.assertRaises(tx.PublicationUncertain):self.apply()
        self.assertEqual(self.destination().read_bytes(), b'mojt-default\n')
        # Both links may survive this boundary: diagnose, never delete/adopt them.
        self.assertEqual(self.destination().stat().st_nlink, 2)
        with self.assertRaises(ValueError):self.apply(reconcile=True)

    def test_partial_multi_file_attempt_resumes_without_overwriting_first_file(self):
        archive, body = self.package(extra=[entry('usr/etc/locale.conf', b'LANG=C.UTF-8\n', mode=0o644)])
        base.install(self.root, archive, body['id'], yes=True)
        self.plan = defaults.prepare(self.root, body['id'], ['locale.conf', 'hostname'])
        original = defaults.publish
        def interrupted(fd, name, data, **kw):
            if name == 'locale.conf':raise OSError('injected second default failure')
            return original(fd, name, data, **kw)
        with mock.patch.object(defaults, 'publish', side_effect=interrupted), self.assertRaises(OSError):self.apply()
        self.assertEqual(self.destination().read_bytes(), b'mojt-default\n')
        self.assertFalse((self.root / 'state/etc/locale.conf').exists())
        self.destination().write_bytes(b'local edit during partial attempt\n')
        self.assertTrue(self.apply(reconcile=True)['changed'])
        self.assertEqual(self.destination().read_bytes(), b'local edit during partial attempt\n')
        self.assertEqual((self.root / 'state/etc/locale.conf').read_bytes(), b'LANG=C.UTF-8\n')
        self.assertEqual(len(self.status()['attempts']), 1)

    def test_source_hardlink_is_not_an_ordinary_default(self):
        import tarfile
        archive, body = self.package(extra=[entry('usr/etc/hard', kind=tarfile.LNKTYPE, link='usr/etc/hostname')])
        base.install(self.root, archive, body['id'], yes=True)
        with self.assertRaisesRegex(ValueError, 'unsafe'):defaults.prepare(self.root, body['id'], ['hard'])

    def test_directory_scan_stops_at_budget(self):
        self.apply();run = next(p for p in self.registry().iterdir() if p.is_dir())
        for number in range(5):(run / ('.result-' + f'{number:032x}')).write_bytes(b'incomplete')
        with self.assertRaisesRegex(ValueError, 'unbounded'):self.status()

    def test_limits_and_incomplete_temps_not_success(self):
        self.apply();run = next(p for p in self.registry().iterdir() if p.is_dir())
        temp = run / ('.result-' + 'a' * 32);temp.write_bytes(b'incomplete')
        self.assertIn(run.name + '/' + temp.name, self.status()['incomplete'])
        with self.assertRaisesRegex(ValueError, 'incomplete'):self.apply()
        temp.unlink();(run / '000002.json').write_bytes(b' ' * (defaults.MAX_RECORD + 1))
        with self.assertRaisesRegex(ValueError, 'unbounded'):self.status()
