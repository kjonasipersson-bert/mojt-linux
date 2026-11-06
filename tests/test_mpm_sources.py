# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Named source to delivered frontend to real native cache; no Nix or VM."""
import contextlib
import copy
import dataclasses
import fcntl
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import mpm_cli as cli
import mpm_sources as sources
import test_mpm_native_cache as fixture


@unittest.skipUnless(shutil.which('zstd'), 'requires zstd')
class SourceTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.CacheTests(); self.f.setUp(); self.f.setup_kind('kernel')
        self.addCleanup(self.f.doCleanups)
        self.work = self.f.work
        self.root = self.work / 'sources'; self.cache = self.work / 'cache'
        self.name = 'local'; self.source = self.f.args['source']; self.policy = self.f.policy_file
        self.write_snapshot()

    def write_snapshot(self):
        for name, raw in (('snapshot.json', fixture.raw(self.f.args['snapshot'])),
                          ('catalog.json', self.f.args['catalog_bytes']),
                          ('acquisition-map.json', self.f.args['acquisition_bytes'])):
            (self.f.repo / name).write_bytes(raw)

    def add(self, **kwargs):
        args = dict(source=self.source, policy_file=self.policy, **kwargs)
        return sources.add(self.root, self.name, sources.prepare_add(self.root, self.name, **args), **args)

    def update(self):
        return sources.update(self.root, self.name, sources.prepare_update(self.root, self.name))

    def selection(self):
        return dict(kind='kernel', archive_sha256=self.f.args['archive_sha256'])

    def fetch(self, **kwargs):
        selection = dict(self.selection(), **kwargs)
        plan = sources.prepare_fetch(self.root, self.cache, self.name, self.f.body['id'], **selection)
        return sources.fetch(self.root, self.cache, self.name, self.f.body['id'], plan, **selection)

    def tree(self):
        return {str(p.relative_to(self.root)): (os.readlink(p) if p.is_symlink() else p.read_bytes())
                for p in self.root.rglob('*') if p.is_file() or p.is_symlink()}

    def rebind(self, catalog=None, mapping=None):
        if catalog is not None:self.f.args['catalog_bytes'] = fixture.raw(catalog)
        if mapping is None:mapping = json.loads(self.f.args['acquisition_bytes'])['description']
        mapping['catalog_sha256'] = fixture.evidence(self.f.args['catalog_bytes'])['sha256']
        mapping = sources.record('mojt-acquisition-map-v1', mapping)
        self.f.args['acquisition_bytes'] = fixture.raw(mapping)
        snap = copy.deepcopy(self.f.args['snapshot']['description'])
        snap['catalog'].update(fixture.evidence(self.f.args['catalog_bytes']))
        snap['acquisition'] = dict(id=mapping['id'], **fixture.evidence(fixture.raw(mapping)))
        self.f.args['snapshot'] = sources.record('mojt-source-snapshot-v1', snap)
        self.write_snapshot()

    def test_preview_readonly_status_and_registration_noop(self):
        self.assertEqual(sources.list_sources(self.root), [])
        sources.prepare_add(self.root, self.name, source=self.source, policy_file=self.policy)
        self.assertFalse(self.root.exists())
        self.add(); self.assertTrue(sources.inspect(self.root, self.name)['refresh_required'])
        before = self.tree(); self.assertFalse(self.add()['changed'])
        self.assertEqual(self.tree(), before); self.assertFalse(self.cache.exists())

    def test_update_freezes_metadata_and_fetch_reuses_it_offline(self):
        self.add(); plan = sources.prepare_update(self.root, self.name); before = self.tree()
        self.assertEqual(self.tree(), before)
        self.assertTrue(sources.update(self.root, self.name, plan)['changed'])
        before = self.tree(); self.assertFalse(self.update()['changed']); self.assertEqual(self.tree(), before)
        for name in ('snapshot.json', 'catalog.json', 'acquisition-map.json', 'artifact.json'):
            (self.f.repo / name).unlink()
        result = self.fetch(); self.assertTrue(result['changed'])
        self.assertEqual(Path(result['archive']).read_bytes(), self.f.archive.read_bytes())
        self.assertEqual(self.tree(), before)
        shutil.rmtree(self.f.repo)
        self.assertFalse(self.fetch()['changed'])
        self.assertFalse(sources.inspect(self.root, self.name)['local_directory_available'])

    def test_corrupt_refresh_preserves_current_snapshot(self):
        self.add(); self.update(); before = self.tree()
        (self.f.repo / 'catalog.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'size'):sources.prepare_update(self.root, self.name)
        self.assertEqual(self.tree(), before); self.assertTrue(self.fetch()['changed'])

    def test_changed_snapshot_after_preview_is_not_silently_accepted(self):
        self.add(); plan = sources.prepare_update(self.root, self.name); before = self.tree()
        (self.f.repo / 'artifact.json').write_bytes(b'{}')
        with self.assertRaises(ValueError):sources.update(self.root, self.name, plan)
        self.assertEqual(self.tree(), before)
        self.assertTrue(sources.inspect(self.root, self.name)['refresh_required'])

    def test_old_snapshot_can_be_pinned_after_metadata_refresh(self):
        self.add(); self.update(); old = self.f.args['snapshot']['id']
        mapping = json.loads(self.f.args['acquisition_bytes'])['description']
        mapping['offers'][0]['archives'][0]['paths'].append('zz-mirror.tar.zst')
        self.rebind(mapping=mapping); self.update()
        result = self.fetch(snapshot=old)
        self.assertEqual(result['record']['description']['source_snapshot'], old)
        self.assertNotEqual(sources.inspect(self.root, self.name)['snapshot']['id'], old)

    def test_empty_catalog_withdrawal_keeps_old_snapshot_usable(self):
        self.add(); self.update(); old = self.f.args['snapshot']['id']
        catalog = json.loads(self.f.args['catalog_bytes']); catalog['candidates'] = []
        self.rebind(catalog=catalog, mapping=dict(offers=[])); self.update()
        with self.assertRaisesRegex(ValueError, 'absent'):self.fetch()
        self.assertTrue(self.fetch(snapshot=old)['changed'])
        self.assertEqual(sources.inspect(self.root, self.name)['catalog']['candidates'], [])

    def test_reconfiguration_requires_replace_and_invalidates_old_authorization(self):
        self.add(); self.update(); old = self.f.args['snapshot']['id']
        plan = sources.prepare_fetch(self.root, self.cache, self.name, self.f.body['id'], **self.selection())
        policy = copy.deepcopy(self.f.policy['description']); policy['max_expanded'] += 1
        changed = sources.record(sources.cache.POLICY, policy); self.policy.write_bytes(fixture.raw(changed))
        src = copy.deepcopy(self.source['description']); src['trust']['policy'] = changed['id']
        self.source = sources.record('mojt-source-v1', src)
        with self.assertRaisesRegex(ValueError, 'replace'):self.add()
        self.add(replace=True); self.assertTrue(sources.inspect(self.root, self.name)['refresh_required'])
        with self.assertRaisesRegex(ValueError, 'binding'):
            sources.fetch(self.root, self.cache, self.name, self.f.body['id'], plan, snapshot=old, **self.selection())
        self.assertFalse(self.cache.exists()); self.assertTrue((self.root / sources.object_path(old)).exists())

    def test_post_pointer_flush_failure_retains_new_current(self):
        self.add(); plan = sources.prepare_update(self.root, self.name)
        def sync(directory):
            if directory == self.root / 'names' / self.name:raise OSError('flush')
            sources.cache.tx.sync_directory(directory)
        with self.assertRaises(sources.cache.tx.PublicationUncertain):
            sources.update(self.root, self.name, plan, sync=sync)
        self.assertEqual(sources.inspect(self.root, self.name)['snapshot']['id'], self.f.args['snapshot']['id'])
        self.assertFalse(self.update()['changed'])

    def test_metadata_failure_preserves_last_good_pointer(self):
        self.add(); before = sources.current(self.root, self.name); plan = sources.prepare_update(self.root, self.name)
        retain = sources.cache.retain_bytes
        def fail(root, path, raw, **kwargs):
            if path.startswith('metadata/'):raise OSError('metadata interrupted')
            return retain(root, path, raw, **kwargs)
        with mock.patch.object(sources.cache, 'retain_bytes', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'interrupted'):sources.update(self.root, self.name, plan)
        self.assertEqual(sources.current(self.root, self.name), before); self.assertTrue(self.update()['changed'])

    def test_symlinks_escapes_and_corrupt_retained_metadata_fail(self):
        self.add(); (self.f.repo / 'snapshot.json').unlink()
        outside = self.work / 'snapshot.json'; outside.write_bytes(fixture.raw(self.f.args['snapshot']))
        (self.f.repo / 'snapshot.json').symlink_to(outside)
        with self.assertRaises(OSError):sources.prepare_update(self.root, self.name)
        with self.assertRaises(ValueError):sources.prepare_update(self.root, self.name, snapshot_file='../snapshot.json')
        (self.f.repo / 'snapshot.json').unlink(); self.write_snapshot(); self.update()
        evidence = json.loads(self.f.args['acquisition_bytes'])['description']['offers'][0]['descriptor']
        path = self.root / 'metadata' / evidence['sha256']; path.chmod(0o644); path.write_bytes(b'bad')
        with self.assertRaises(ValueError):self.fetch()
        self.assertFalse(self.cache.exists())

    def test_authorization_lock_is_held_during_slow_acquisition(self):
        self.add(); self.update(); acquire = sources.cache.acquire
        def check(*args, **kwargs):
            with (self.root / '.lock').open('rb') as lock:
                with self.assertRaises(BlockingIOError):fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return acquire(*args, **kwargs)
        with mock.patch.object(sources.cache, 'acquire', side_effect=check):self.fetch()

    def test_nested_roots_and_invalid_registration_pointers_fail(self):
        self.add(); self.update()
        nested = self.root / 'nested-cache'
        with self.assertRaisesRegex(ValueError, 'separate'):
            sources.prepare_fetch(self.root, nested, self.name, self.f.body['id'], **self.selection())
        self.assertFalse(nested.exists())
        pointer = self.root / 'names' / self.name / 'current'
        pointer.unlink(); pointer.symlink_to('../../objects/../outside.json')
        with self.assertRaises(ValueError):sources.inspect(self.root, self.name)

    def test_delivered_copy_flow_without_checkout_or_provider(self):
        tools = self.work / 'delivered'; tools.mkdir()
        for name in ('mpm', 'mpm_cli.py', 'mpm_sources.py', 'mpm_sources_cli.py', 'mpm_native_cache.py',
                     'mpm_transaction.py', 'mpm_request_plan.py', 'mpm_requests.py', 'mpm_selection.py', 'mojt_artifact.py'):
            shutil.copyfile(Path(sources.__file__).parent / name, tools / name)
        source_file = self.work / 'source.json'; source_file.write_bytes(fixture.raw(self.source))
        def call(root, *args):
            result = subprocess.run([sys.executable, '-I', '-B', str(tools / 'mpm'), '--root', str(root), *args],
                cwd='/', text=True, capture_output=True, env=dict(os.environ, PYTHONPATH='/invalid'))
            self.assertEqual(result.returncode, 0, result.stderr); return json.loads(result.stdout)
        args = ('source', 'add', self.name, '--from-file', str(source_file), '--policy-file', str(self.policy))
        call(self.root, *args, '--dry-run'); self.assertFalse(self.root.exists())
        call(self.root, *args, '-y'); call(self.root, 'source', 'update', self.name, '-y')
        args = ('cache', 'fetch', self.f.body['id'], '--sources-root', str(self.root), '--source', self.name,
                '--kind', 'kernel', '--archive-sha256', self.selection()['archive_sha256'])
        self.assertTrue(call(self.cache, *args, '--dry-run')['dry_run']); self.assertFalse(self.cache.exists())
        self.assertTrue(call(self.cache, *args, '-y')['changed']); self.assertFalse(call(self.cache, *args, '-y')['changed'])
        self.assertEqual(call(self.root, 'source', 'show', self.name)['snapshot']['id'], self.f.args['snapshot']['id'])

    def test_system_readonly_access_and_codec_gate(self):
        runtime = dataclasses.replace(cli.Runtime(), sources=self.root, cache=self.cache,
                                      helpers=self.work / 'no-codec', system_bin=self.work / 'no-bin')
        with mock.patch.object(cli.os, 'geteuid', return_value=1000):
            for argv in (['source', 'add'], ['source', 'update'], ['cache', 'fetch']):
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(cli.main(argv, runtime=runtime), 1); self.assertIn('administrator', err.getvalue())
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(cli.main(['source', 'list', '--json'], runtime=runtime), 0)
                self.assertEqual(json.loads(out.getvalue()), [])
        with mock.patch.object(cli.os, 'geteuid', return_value=0), contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(cli.main(['cache', 'fetch', self.f.body['id'], '--source', self.name,
                '--kind', 'kernel', '--archive-sha256', self.selection()['archive_sha256'], '-y'], runtime=runtime), 1)
            self.assertIn('retained zstd', err.getvalue())
        self.assertFalse(self.root.exists()); self.assertFalse(self.cache.exists())


if __name__ == '__main__':unittest.main()
