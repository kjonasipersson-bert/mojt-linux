# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real native System archives/components; no Nix, package execution or VM boot."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
import mojt_artifact as artifact
import mojt_system as runtime
import mpm_base as base
import mpm_cli as cli
import mpm_management as management
import mpm_system as system
import mpm_system_model as model
import mpm_transaction as tx


def pack(source, specification, output):
    # Non-root previews still need a valid distributable header. Root CI also
    # exercises the actual numeric-owner materialization below.
    inventory = artifact.inventory
    def numeric_root(path):
        rows, locations = inventory(path)
        for row in rows:row['uid'] = row['gid'] = 0
        return rows, locations
    with mock.patch.object(artifact, 'inventory', side_effect=numeric_root):
        return artifact.pack(source, specification, output)


def spec(role, *, revision=1, dependencies=(), composition=None):
    return dict(format=artifact.SPEC_FORMAT, kind='system', name='mojt-system' if role == 'generation' else 'mojt-runtime',
        platform=os.uname().machine + '-linux', version=dict(upstream='0.2.0', scheme='dotted-v1', revision=revision),
        dependencies=list(dependencies), requirements={}, provides={}, provenance={'source_revision': 'native-fixture'},
        metadata=dict(system_role=role, **({'composition': composition} if composition else {})))


def tree(root):
    return {p.relative_to(root).as_posix(): (p.lstat().st_mode, p.read_bytes() if p.is_file() and not p.is_symlink() else None)
            for p in root.rglob('*')}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name);self.root = self.work / 'disk';self.root.mkdir()
        self.serial = 0
        content = self.work / 'component-source';(content / 'tools').mkdir(parents=True);(content / 'bin').mkdir()
        for name in runtime.MPM_FILES:shutil.copy2(REPO / 'tools' / name, content / 'tools' / name)
        self.marker = self.work / 'package-executed'
        for name in ('mpm', 'python3'):
            (content / 'bin' / name).write_text('#!/bin/sh\ntouch ' + str(self.marker) + '\n');(content / 'bin' / name).chmod(0o755)
        (content / 'private.conf').write_bytes(b'private fixture configuration\n');(content / 'private.conf').chmod(0o600)
        result = pack(content, spec('component'), self.work / 'component-package')
        self.component = result['artifact'];self.component_archive = self.work / 'component-package' / result['archive']['file']
        self.reference = dict(provider='native', artifact=self.component['id'])
        actions = base.record(model.LIFECYCLE, dict(platform=spec('component')['platform'], actions=[]))
        self.actions = actions
        d = dict(label='system-native-test', platform=spec('component')['platform'], components=[dict(role='runtime', reference=self.reference)],
            requirements=dict(base_abi=[dict(name='libc', value='glibc')], state_layout=1, kernel_capabilities=[], host_capabilities=[]),
            management=management.current()['description']['management'], state=[],
            profile=[dict(path='bin', source=dict(reference=self.reference, path='bin')), dict(path='tools', source=dict(reference=self.reference, path='tools'))],
            services=[], runtime=dict(interpreter='bin/python3', frontend='bin/mpm', module_root='tools'),
            lifecycle=dict(format=model.LIFECYCLE, id=actions['id'], path='payload/lifecycle.json'))
        self.composition = base.record(model.FORMAT, d)
        self.archive, self.body = self.package(self.composition, self.actions)

    def package(self, value=None, actions=None, *, revision=1, change_spec=None):
        self.serial += 1;source = self.work / ('generation-source-' + str(self.serial));source.mkdir()
        value = value or self.composition;actions = actions or self.actions
        (source / 'composition.json').write_bytes(artifact.canonical(value));(source / 'lifecycle.json').write_bytes(artifact.canonical(actions))
        s = spec('generation', revision=revision, dependencies=[self.reference], composition=dict(format=model.FORMAT, id=value['id'], path='payload/composition.json'))
        if change_spec:change_spec(s)
        dest = self.work / ('generation-package-' + str(self.serial));result = pack(source, s, dest)
        return dest / result['archive']['file'], result['artifact']

    def install(self, **kw):
        dependencies = kw.pop('dependency_files',[self.component_archive])
        return system.install(self.root,self.archive,self.body['id'],dependency_files=dependencies,yes=True,**kw)


@unittest.skipUnless(shutil.which('zstd'), 'requires real native archive codec')
class PreviewTests(Fixture):
    def test_real_composition_component_and_profile_preview_write_no_target(self):
        before = tree(self.root);result = self.install(dry_run=True)
        self.assertTrue(result['profile_validated']);self.assertFalse(result['archive_verified'])
        self.assertEqual(tree(self.root), before);self.assertFalse(self.marker.exists())
        self.assertFalse((self.root / 'artifacts').exists())

    def test_payload_hashing_is_optional_but_archive_structure_and_zstd_errors_are_not(self):
        import tarfile
        # Change payload bytes without updating the valid descriptor or tar sizes.
        raw = subprocess.run(['zstd','-qd','-c',str(self.component_archive)],check=True,capture_output=True).stdout
        original = b'private fixture configuration\n'
        self.assertIn(original,raw)
        changed = raw.replace(original,b'changed fixture configuration\n')
        encoded = subprocess.run(['zstd','-q','-c'],input=changed,check=True,capture_output=True).stdout
        damaged = self.work/'changed.tar.zst';damaged.write_bytes(encoded)
        self.install(dry_run=True,dependency_files=[damaged])
        with self.assertRaisesRegex(ValueError,'checksum differs'):
            self.install(dry_run=True,dependency_files=[damaged],verify=True)
        # Undeclared traversal and a truncated compressed frame fail in normal mode.
        content = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as source, tarfile.open(fileobj=content,mode='w') as target:
            for member in source:
                data = source.extractfile(member) if member.isfile() else None
                if member.name.endswith('/payload/private.conf'):member.name = '../../outside'
                target.addfile(member,data)
        damaged.write_bytes(subprocess.run(['zstd','-q','-c'],input=content.getvalue(),check=True,capture_output=True).stdout)
        with self.assertRaisesRegex(ValueError,'member differs'):
            self.install(dry_run=True,dependency_files=[damaged])
        damaged.write_bytes(encoded[:-8])
        with self.assertRaises((ValueError,tarfile.TarError)):
            self.install(dry_run=True,dependency_files=[damaged])
        self.assertEqual(tree(self.root),{});self.assertFalse((self.work/'outside').exists())

    def test_status_of_missing_target_has_no_codec_or_registry_dependency(self):
        absent = self.work / 'absent';result = system.status(absent)
        self.assertEqual(result['installed'], []);self.assertEqual(result['selected']['state'], 'unknown');self.assertFalse(absent.exists())
        p = subprocess.run([sys.executable, '-I', '-B', str(REPO / 'tools/mpm'), 'system', 'status', '--disk-root', str(absent), '--json'],
                           cwd='/', env=dict(os.environ, PATH=''), text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr);self.assertEqual(json.loads(p.stdout)['installed'], []);self.assertFalse(absent.exists())

    def test_unknown_provider_missing_dependency_and_outer_binding_fail_before_writes(self):
        d = copy.deepcopy(self.composition['description']);d['components'][0]['reference'] = dict(provider='other', identity={'object': 'opaque'})
        with self.assertRaisesRegex(ValueError, 'provider adapter unavailable'):model.validate(base.record(model.FORMAT, d))
        with self.assertRaises((ValueError, FileNotFoundError)):system.install(self.root, self.archive, self.body['id'], dry_run=True)
        archive, body = self.package(change_spec=lambda s:s.update(dependencies=[]))
        with self.assertRaisesRegex(ValueError, 'dependencies differ'):
            system.install(self.root, archive, body['id'], dependency_files=[self.component_archive], dry_run=True)
        self.assertEqual(tree(self.root), {})

    def test_path_overlap_undeclared_source_and_reserved_output_fail(self):
        for path in ('../etc/shadow', '/etc/passwd', 'management.json', 'generated/cache', 'tools/a'):
            d = copy.deepcopy(self.composition['description']);d['profile'].append(dict(path=path, source=dict(reference=self.reference, path='bin')))
            d['profile'].sort(key=lambda r:r['path'])
            with self.subTest(path=path), self.assertRaises(ValueError):model.validate(base.record(model.FORMAT, d))
        d = copy.deepcopy(self.composition['description']);d['profile'][0]['source']['reference'] = dict(provider='native', artifact='sha256:' + '1' * 64)
        with self.assertRaisesRegex(ValueError, 'undeclared'):model.validate(base.record(model.FORMAT, d))

    def test_required_actions_and_schema_claims_are_refused_not_executed(self):
        actions = base.record(model.LIFECYCLE, dict(platform=self.body['platform'], actions=[dict(type='run', command='touch ' + str(self.marker))]))
        d = copy.deepcopy(self.composition['description']);d['lifecycle']['id'] = actions['id']
        archive, body = self.package(base.record(model.FORMAT, d), actions)
        with self.assertRaisesRegex(ValueError, 'required lifecycle'):
            system.install(self.root, archive, body['id'], dependency_files=[self.component_archive], dry_run=True)
        self.assertFalse(self.marker.exists());self.assertEqual(tree(self.root), {})

    def test_metadata_cannot_overstate_the_actual_bundled_manager(self):
        d = copy.deepcopy(self.composition['description']);d['management'][0]['read'] = [1, 2];d['management'][0]['write'] = [1, 2]
        archive, body = self.package(base.record(model.FORMAT, d))
        with self.assertRaisesRegex(ValueError, 'overstates'):
            system.install(self.root, archive, body['id'], dependency_files=[self.component_archive], dry_run=True)
        self.assertEqual(tree(self.root), {})

    def test_changed_physical_target_is_refused_without_a_registry(self):
        build = system.build_profile
        moved = self.work / 'replaced-target'
        def replace_target(*args, **kwargs):
            result = build(*args, **kwargs)
            self.root.rename(moved);self.root.mkdir()
            return result
        with mock.patch.object(system, 'build_profile', side_effect=replace_target), self.assertRaisesRegex(ValueError, 'target changed'):
            self.install(dry_run=True)
        self.assertEqual(tree(self.root), {});self.assertEqual(tree(moved), {})

    def test_ordinary_user_denied_before_archive_or_codec_lookup(self):
        runtime = cli.Runtime(disk=self.root)
        with mock.patch.object(cli.os, 'geteuid', return_value=1000), contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(cli.main(['system', 'install', '--from-file', '/missing', '--expected-id', self.body['id'], '-y'], runtime=runtime), 1)
        self.assertIn('administrator', err.getvalue());self.assertEqual(tree(self.root), {})


@unittest.skipUnless(os.geteuid() == 0 and shutil.which('zstd'), 'real numeric-owner System installation requires root and zstd')
class InstallTests(Fixture):
    def test_install_noop_and_status_retain_exact_inputs_without_running_package_code(self):
        (self.root / 'state/etc').mkdir(parents=True);(self.root / 'state/etc/keep').write_bytes(b'local configuration\n')
        (self.root / 'state/var').mkdir();(self.root / 'state/var/keep').write_bytes(b'persistent state\n')
        before = tree(self.root / 'state');result = self.install()
        self.assertTrue(result['changed']);self.assertFalse(self.marker.exists());self.assertEqual(tree(self.root / 'state'), before)
        actual = system.status(self.root, verify=True)
        self.assertEqual(len(actual['installed']), 1);self.assertEqual(len(actual['components']), 1)
        private = system.object_path(self.root, self.component['id']) / 'payload/private.conf'
        self.assertEqual(private.stat().st_mode & 0o777, 0o400)
        self.assertIsNone(actual['running']['artifact']);self.assertIsNone(actual['selected']['artifact'])
        self.archive.unlink();self.component_archive.unlink()
        before = tree(self.root)
        repeat = system.install(self.root, None, self.body['id'], yes=True)
        self.assertFalse(repeat['changed']);self.assertEqual(tree(self.root), before)
        self.assertEqual(system.status(self.root, verify=True), actual)

    def test_default_install_does_not_scrub_and_builds_profile_once(self):
        with mock.patch.object(artifact,'verify',side_effect=AssertionError('implicit archive scrub')), \
             mock.patch.object(system,'build_profile',wraps=system.build_profile) as build, \
             mock.patch.object(system.io,'unpack_regular',wraps=system.io.unpack_regular) as unpack:
            self.assertTrue(self.install()['changed'])
            self.assertEqual(build.call_count,1)
            self.assertEqual(unpack.call_count,2)  # One pass per new archive.
            self.assertTrue(all(call.kwargs['verify'] is False for call in unpack.call_args_list))
            self.assertFalse(system.install(self.root,None,self.body['id'],yes=True)['changed'])
            self.assertEqual(unpack.call_count,2);self.assertEqual(build.call_count,1)
        system.status(self.root,verify=True)
        with mock.patch.object(artifact,'verify',wraps=artifact.verify) as audit:
            self.assertFalse(system.install(self.root,None,self.body['id'],yes=True,verify=True)['changed'])
            self.assertGreater(audit.call_count,0)

    def test_explicit_verification_detects_damage_in_final_profile_copy(self):
        copy_profile = system.copy_profile
        def corrupt(source,destination):
            copy_profile(source,destination)
            file = destination/'bin/mpm';file.chmod(0o755)
            file.write_bytes(b'x'*file.stat().st_size);file.chmod(0o555)
        with mock.patch.object(system,'copy_profile',side_effect=corrupt), \
             self.assertRaisesRegex(ValueError,'profile copy damaged'):
            self.install(verify=True)
        self.assertFalse(system.realization_path(self.root,self.body['id']).exists())

    def test_same_label_different_builds_coexist_and_label_is_not_selection(self):
        self.install();second, body = self.package(revision=2)
        system.install(self.root, second, body['id'], yes=True)
        status = system.status(self.root, verify=True)
        self.assertEqual({r['artifact'] for r in status['installed']}, {self.body['id'], body['id']})
        self.assertEqual({r['label'] for r in status['installed']}, {'system-native-test'})
        self.assertEqual(len({r['manifest'] for r in status['installed']}), 2)
        self.assertEqual(status['selected']['state'], 'unknown')

    def test_status_uses_exact_manifest_not_a_coincident_label(self):
        from test_mpm_base import baseline
        d = copy.deepcopy(self.composition['description']);d['label'] = 'system-test'
        self.archive, self.body = self.package(base.record(model.FORMAT, d))
        self.install()
        record = baseline(self.root, 'sha256:' + 'f' * 64)
        observed = system.status(self.root, running_record=record)
        self.assertEqual(observed['selected']['label'], 'system-test')
        self.assertIsNone(observed['selected']['artifact'])
        self.assertIsNone(observed['running']['artifact'])
        self.assertEqual(observed['running']['manifest'], record['description']['system']['manifest'])

    def test_interruption_retains_components_generation_and_allows_explicit_retry(self):
        with mock.patch.object(system, 'copy_profile', side_effect=OSError('injected realization failure')), self.assertRaises(OSError):self.install()
        status = system.status(self.root)
        self.assertEqual(len(status['retained']), 1);self.assertEqual(len(status['components']), 1);self.assertEqual(status['installed'], [])
        self.assertTrue(system.install(self.root, None, self.body['id'], yes=True)['changed'])
        self.assertEqual(len(system.status(self.root, verify=True)['installed']), 1)

    def test_post_publication_flush_failure_retains_complete_realization(self):
        real = tx.publish
        def uncertain(source, dest, **kw):
            if dest == system.realization_path(self.root, self.body['id']):
                def fail(path):raise OSError('injected final parent fsync')
                return real(source, dest, sync=fail)
            return real(source, dest, **kw)
        with mock.patch.object(tx, 'publish', side_effect=uncertain), self.assertRaises(tx.PublicationUncertain):self.install()
        self.assertEqual(len(system.status(self.root, verify=True)['installed']), 1)
        self.assertFalse(system.install(self.root, None, self.body['id'], yes=True)['changed'])

    def test_corrupt_component_or_profile_blocks_verified_status_and_reuse(self):
        self.install();path = system.realization_path(self.root, self.body['id']) / 'profile/bin/mpm'
        path.chmod(0o755);path.write_bytes(b'changed after install')
        with self.assertRaisesRegex(ValueError, 'profile content'):system.status(self.root, verify=True)
        self.assertFalse(system.install(self.root, None, self.body['id'], yes=True)['changed'])
        with self.assertRaises(ValueError):system.install(self.root, None, self.body['id'], yes=True,verify=True)

    def test_unsafe_target_and_missing_codec_do_not_initialize_a_registry(self):
        outside = self.work / 'outside';outside.mkdir();linked = self.work / 'linked';linked.symlink_to(outside)
        with self.assertRaises(ValueError):system.install(linked, self.archive, self.body['id'], dependency_files=[self.component_archive], yes=True)
        self.assertEqual(tree(outside), {})
        old = os.environ.get('PATH');os.environ['PATH'] = ''
        try:
            with self.assertRaises(FileNotFoundError):self.install()
        finally:
            if old is None:os.environ.pop('PATH', None)
            else:os.environ['PATH'] = old
        self.assertEqual(tree(self.root), {})
