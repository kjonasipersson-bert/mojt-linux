# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Source/cache/Kernel publication join with real archives and isolated MPM."""
import contextlib
import copy
import dataclasses
import fcntl
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import mpm_cli as cli
import mpm_kernel as kernel
import mpm_kernel_source as join
import test_mpm_sources as fixture


@unittest.skipUnless(shutil.which('zstd'), 'requires zstd')
class KernelSourceTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.SourceTests(); self.f.setUp(); self.f.add(); self.f.update()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.work / 'kernel'
        self.artifact = self.f.f.body['id']
        self.kwargs = dict(archive_sha256=self.f.selection()['archive_sha256'])

    def prepare(self):
        return join.prepare(self.root, self.f.root, self.f.cache, self.f.name, self.artifact, **self.kwargs)

    def install(self, **kwargs):
        return join.install(self.root, self.f.root, self.f.cache, self.f.name, self.artifact,
                            yes=True, **self.kwargs, **kwargs)

    def test_preview_checks_eligibility_without_archive_reads_or_writes(self):
        before = self.f.tree()
        self.f.f.archive.unlink()
        result = self.install(dry_run=True)
        self.assertTrue(result['dry_run']); self.assertFalse(result['changed'])
        self.assertEqual(result['plan']['description']['installation']['selected'], 'unchanged')
        self.assertFalse(self.root.exists()); self.assertFalse(self.f.cache.exists())
        self.assertEqual(self.f.tree(), before)

    def test_source_install_retains_origin_and_matching_tree_without_selection(self):
        sentinel = self.f.work / 'selected'; sentinel.write_bytes(b'Base/System/boot unchanged')
        result = self.install(); self.assertTrue(result['changed'])
        status = kernel.status(self.root, verify=True)
        row = status['installed'][0]
        self.assertEqual(row['artifact'], self.artifact)
        self.assertEqual(row['trust']['kind'], 'registered-native-source')
        evidence = row['acquisition']
        self.assertEqual(evidence['source'], self.f.source['id'])
        self.assertEqual(evidence['verification'], result['acquisition']['record'])
        self.assertEqual(evidence['verification']['description']['source_snapshot'], self.f.f.args['snapshot']['id'])
        self.assertIsNone(status['selected']['artifact']); self.assertIsNone(status['running']['artifact'])
        self.assertEqual(sentinel.read_bytes(), b'Base/System/boot unchanged')

    def test_vm_fixture_publisher_builds_a_valid_real_source(self):
        import test_mojt_artifact as packages
        helper = runpy.run_path(str(Path(__file__).with_name('run-kernel-source-acceptance.py')))
        lab = self.f.work/'acceptance'; lab.mkdir()
        archive, _ = self.f.f.package.package(packages.spec('kernel', version='6.12.107', revision=2))
        body, checksum = helper['prepare_repository'](archive, lab, 'acceptance',
            artifact=kernel.artifact, cache=join.sources.cache)
        source = json.loads((lab/'source.json').read_bytes())
        registry = self.f.work/'acceptance-sources'
        args = dict(source=source, policy_file=lab/'policy.json')
        plan = join.sources.prepare_add(registry, 'acceptance', **args)
        join.sources.add(registry, 'acceptance', plan, **args)
        join.sources.update(registry, 'acceptance', join.sources.prepare_update(registry, 'acceptance'))
        result = join.install(self.root, registry, self.f.cache, 'acceptance', body['id'],
                              archive_sha256=checksum, yes=True)
        self.assertTrue(result['changed'])

    def test_status_rejects_origin_archive_mismatch_without_silent_repair(self):
        result = self.install(); path = Path(result['installation']['installed_path'])/'installed.json'
        record = json.loads(path.read_bytes())
        receipt = record['acquisition']['verification']['description']
        receipt['archive']['sha256'] = '0'*64
        record['acquisition']['verification'] = join.sources.record(join.sources.cache.RECORD, receipt)
        record['trust']['verification'] = record['acquisition']['verification']['id']
        path.chmod(0o644); path.write_bytes(kernel.artifact.canonical(record)+b'\n'); path.chmod(0o444)
        damaged = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'encoding differs'):kernel.status(self.root)
        with self.assertRaises(ValueError):self.install()
        self.assertEqual(path.read_bytes(), damaged)

    def test_repeat_preserves_record_and_needs_neither_source_bytes_nor_cache(self):
        result = self.install()
        target = Path(result['installation']['installed_path'])
        before = (target / 'installed.json').read_bytes()
        shutil.rmtree(self.f.f.repo); shutil.rmtree(self.f.cache)
        again = self.install()
        self.assertFalse(again['changed']); self.assertIsNone(again['acquisition'])
        self.assertFalse(self.f.cache.exists())
        self.assertEqual((target / 'installed.json').read_bytes(), before)

    def test_existing_file_install_does_not_get_relabelled_as_source_install(self):
        result = kernel.install(self.root, self.f.f.archive, self.artifact, yes=True)
        record = Path(result['installed_path']) / 'installed.json'; before = record.read_bytes()
        self.assertFalse(self.install()['changed'])
        self.assertFalse(self.f.cache.exists()); self.assertEqual(record.read_bytes(), before)
        self.assertEqual(kernel.status(self.root)['installed'][0]['trust']['kind'], 'explicit-local-file')

    def test_unsupported_dependency_and_requirements_fail_before_acquisition(self):
        _, _, body, _, _ = join.sources.cache.inputs(self.f.cache,
            **join.sources.acquisition_inputs(self.f.root, self.f.name, self.artifact,
                kind='kernel', **self.kwargs))
        for key, value in [('dependencies', [dict(provider='native', artifact='sha256:'+'a'*64)]),
                           ('requirements', dict(base_abi='unsupported'))]:
            changed = copy.deepcopy(body); changed[key] = value
            with self.subTest(key=key), mock.patch.object(kernel.artifact, 'validate_descriptor'), \
                    mock.patch.object(join.sources.cache, 'inputs', return_value=(None, {}, changed, [], [])):
                with self.assertRaisesRegex(ValueError, 'cannot be ignored'):self.prepare()
            self.assertFalse(self.root.exists()); self.assertFalse(self.f.cache.exists())

    def test_changed_source_authorization_invalidates_preview(self):
        plan = self.prepare()
        policy = copy.deepcopy(self.f.f.policy['description']); policy['max_expanded'] += 1
        changed = join.sources.record(join.sources.cache.POLICY, policy)
        self.f.policy.write_bytes(fixture.fixture.raw(changed))
        src = copy.deepcopy(self.f.source['description']); src['trust']['policy'] = changed['id']
        self.f.source = join.sources.record('mojt-source-v1', src); self.f.add(replace=True)
        with self.assertRaisesRegex(ValueError, 'binding'):join.execute(plan)
        self.assertFalse(self.root.exists()); self.assertFalse(self.f.cache.exists())

    def test_failed_extraction_retains_cache_but_no_installed_object(self):
        with mock.patch.object(kernel, 'unpack_kernel', side_effect=OSError('injected extraction')):
            with self.assertRaisesRegex(OSError, 'injected'):self.install()
        self.assertEqual(kernel.status(self.root)['installed'], [])
        self.assertTrue((self.f.cache / 'archives/sha256' / self.kwargs['archive_sha256']).is_file())
        self.assertTrue(self.install()['changed'])

    def test_copy_rechecks_raw_encoding_even_when_artifact_is_identical(self):
        raw = subprocess.check_output(['zstd', '-q', '-d', '-c', str(self.f.f.archive)])
        alternate = subprocess.check_output(['zstd', '-q', '-c'], input=raw+b'\0'*10240)
        original = kernel.frozen_copy
        def mutate(source, destination):
            source.chmod(0o644); source.write_bytes(alternate); source.chmod(0o444)
            return original(source, destination)
        with mock.patch.object(kernel, 'frozen_copy', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'encoding differs'):self.install()
        self.assertEqual(kernel.status(self.root)['installed'], [])

    def test_source_lock_is_held_through_kernel_publication(self):
        original = kernel.install
        def check(*args, **kwargs):
            with (self.f.root / '.lock').open('rb') as lock:
                with self.assertRaises(BlockingIOError):fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
            return original(*args, **kwargs)
        with mock.patch.object(kernel, 'install', side_effect=check):self.install()

    def test_nesting_installation_inside_metadata_or_cache_is_refused(self):
        for root in (self.f.root / 'kernel', self.f.cache / 'kernel'):
            with self.subTest(root=root), self.assertRaisesRegex(ValueError, 'separate'):
                join.prepare(root, self.f.root, self.f.cache, self.f.name, self.artifact, **self.kwargs)
        self.assertFalse(self.f.cache.exists())

    def test_delivered_cli_installs_and_inspects_without_provider_or_checkout(self):
        tools = self.f.work / 'delivered'; tools.mkdir()
        for name in ('mpm', 'mpm_cli.py', 'mpm_kernel.py', 'mpm_kernel_source.py', 'mpm_sources.py',
                     'mpm_sources_cli.py', 'mpm_native_cache.py', 'mpm_transaction.py',
                     'mpm_request_plan.py', 'mpm_requests.py', 'mpm_selection.py', 'mojt_artifact.py'):
            shutil.copyfile(Path(kernel.__file__).parent / name, tools / name)
        def call(*args):
            result = subprocess.run([sys.executable, '-I', '-B', str(tools/'mpm'), '--root', str(self.root),
                'kernel', *args], cwd='/', env=dict(os.environ, PYTHONPATH='/invalid'), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr); return json.loads(result.stdout)
        args = ('install', '--source', self.f.name, '--expected-id', self.artifact,
                '--archive-sha256', self.kwargs['archive_sha256'], '--sources-root', str(self.f.root),
                '--cache-root', str(self.f.cache))
        self.assertTrue(call(*args, '--dry-run')['dry_run']); self.assertFalse(self.root.exists())
        self.assertTrue(call(*args, '-y')['changed']); self.assertFalse(call(*args, '-y')['changed'])
        self.assertEqual(call('status', '--verify', '--json')['installed'][0]['artifact'], self.artifact)

    def test_installed_dispatch_binds_runtime_paths_and_preview_needs_no_codec(self):
        disk = self.f.work / 'disk'; (disk/'boot/mojt').mkdir(parents=True)
        runtime = dataclasses.replace(cli.Runtime(), disk=disk, sources=self.f.root, cache=self.f.cache,
            helpers=self.f.work/'missing-codec')
        with mock.patch.object(cli.os, 'geteuid', return_value=0), \
                mock.patch.object(kernel, 'main', return_value=0) as run:
            self.assertEqual(cli.main(['kernel', 'install', '--source', self.f.name, '--dry-run'], runtime=runtime), 0)
            args = run.call_args.args[0]
            self.assertIn(str(disk/'kernel'), args)
            self.assertEqual(args[args.index('--sources-root')+1], str(self.f.root))
            self.assertEqual(args[args.index('--cache-root')+1], str(self.f.cache))
        self.assertFalse(self.root.exists()); self.assertFalse(self.f.cache.exists())


if __name__ == '__main__':unittest.main()
