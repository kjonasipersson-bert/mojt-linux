# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Three focused package/link/source joins; provider I/O is simulated, archives are real."""
import copy
import os
from pathlib import Path
import shutil
import unittest
from unittest import mock

from test_mpm_system import Fixture, tree
import mojt_artifact as artifact
import mojt_system_manifest as manifests
import mojt_system_package as package
import mpm_management as management
import mpm_nix_binary as nix
import mpm_sources as sources
import mpm_system as system
import mpm_system_source as source_install


class Adapter:
    binary = '/explicit/nix-store'
    def __init__(self, ref):self.ref = ref;self.events = [];self.present = True
    def describe(self, ref, root):
        if ref != self.ref:raise ValueError('reference changed')
        self.events.append('describe')
        return dict(reference=copy.deepcopy(ref), commands={'python3':ref['identity']['output'] + '/bin/python3'})
    def contains(self, ref, path):
        root = self.ref['identity']['output']
        return ref == self.ref and '..' not in Path(path).parts and (path == root or path.startswith(root + '/'))
    def ensure(self, ref, root):self.events.append('ensure');self.present = True
    def verify(self, ref, root):
        self.events.append('verify')
        if not self.present:raise ValueError('provider missing')
    def verify_path(self, ref, path, *, executable=False):
        self.events.append(('path', path, executable))
        if not self.present or not self.contains(ref, path):raise ValueError('provider link unavailable')


class PackageFixture(Fixture):
    def setUp(self):
        super().setUp()
        output = '/nix/store/' + 'a' * 32 + '-runtime'
        self.provider = dict(provider='nix', identity=dict(format='mojt-nix-output-v1', output=output,
            closure=[dict(path=output, nar_hash='sha256:' + 'b' * 52)], commands=['python3']))
        self.adapter = Adapter(self.provider)
        self.tree = self.work / 'assembled';self.profile = self.tree / 'system/system-package-test'
        self.profile.parent.mkdir(parents=True);shutil.copytree(self.work / 'component-source', self.profile)
        (self.profile / 'bin/python3').unlink();(self.profile / 'bin/python3').symlink_to(output + '/bin/python3')
        (self.profile / 'bin/daemon').symlink_to(output + '/sbin/daemon')
        units = self.profile / 'units';units.mkdir();(units / 'mojt.target').write_text('[Unit]\nWants=demo.service\n')
        (units / 'demo.service').write_text('[Service]\nExecStart=/run/mojt-system/bin/mpm\n')
        (units / 'mojt.target.wants').mkdir();(units / 'mojt.target.wants/demo.service').symlink_to('../demo.service')
        (units / 'default.target').symlink_to('mojt.target')
        (self.profile / 'bin/sudo').symlink_to('/run/mojt-privileged/sudo')
        (self.profile / 'privileged-inputs.json').write_text('{}\n')
        (self.profile / 'privileged-setup.py').write_text('# Not executed during content installation.\n')
        (units / 'mojt-privileged.service').write_text('[Service]\nType=oneshot\n')
        (self.profile / 'hwdb.bin').write_bytes(b'fixture-hwdb')
        (self.profile / 'defaults').mkdir();(self.profile / 'defaults/hwdb.bin').symlink_to('/run/mojt-system/hwdb.bin')
        (self.profile / 'ports-roots').mkdir();(self.profile / 'ports-roots/runtime').symlink_to(output)
        self.write_manifest()
        self.kit = self.work / 'kit';self.source_root = self.work / 'sources';self.cache_root = self.work / 'cache'

    def write_manifest(self):
        support = management.produce(self.profile / 'tools', management.literal(self.profile / 'tools/mojt_system.py', 'MPM_FILES'))
        (self.profile / management.FILENAME).write_bytes(package.raw(support))
        self.manifest = manifests.create(dict(label='system-package-test', architecture=os.uname().machine,
            requirements=dict(base_abi={'libc':'glibc'}, state_layout=1), support=dict(ports=dict(read=[], write=[], capabilities=[])),
            provides=['/run/mojt-system/bin/python3'], artifacts=dict(nix=dict(fixture=True)),
            provenance=dict(builder='test'), profile=system.inventory(self.profile)))
        (self.profile / 'manifest.json').write_bytes(package.raw(self.manifest))

    def pack(self, destination=None):
        with mock.patch.object(package, 'nix_references', return_value=[self.provider]):
            return package.package(self.tree, 'system-package-test', '0.2.0', 3, destination or self.kit, adapter=self.adapter)

    def register(self):
        source = artifact.read_json(self.kit / 'source.json');policy = self.kit / 'policy.json'
        args = dict(source=source, policy_file=policy)
        sources.add(self.source_root, 'system-kit', sources.prepare_add(self.source_root, 'system-kit', **args), **args)
        sources.update(self.source_root, 'system-kit', sources.prepare_update(self.source_root, 'system-kit'))
        record = artifact.read_json(self.kit / 'generation/archive.json')
        return dict(archive_sha256=record['sha256'])


@unittest.skipUnless(shutil.which('zstd'), 'requires real archive codec')
class PackageTests(PackageFixture):
    def test_real_packages_keep_links_version_provenance_and_source_preview_is_metadata_only(self):
        calls = []
        def query(args):
            calls.append(args)
            if '--requisites' in args:return self.provider['identity']['output']
            if '--hash' in args:return self.provider['identity']['closure'][0]['nar_hash']
            if '--verify-path' in args:return ''
            raise AssertionError(args)
        data = dict(objects=self.provider['identity']['closure'], source={'store':self.provider['identity']['output']},
                    packages={'runtime':{'output':self.provider['identity']['output']}})
        exact = package.nix_references({'description':{'artifacts':{'nix':data}}}, nix.NixBinaryAdapter('/explicit/nix-store', query))
        self.assertEqual(exact[0]['identity']['closure'], self.provider['identity']['closure'])
        self.assertTrue(calls);self.assertFalse(any('--realise' in args or '--add-root' in args for args in calls))
        before = tree(self.profile);result = self.pack();second = self.pack(self.work / 'kit-again')
        self.assertEqual(result['kit']['description']['generation'], second['kit']['description']['generation'])
        component = artifact.read_json(self.kit / 'component/artifact.json')
        self.assertTrue(all(r['uid'] == r['gid'] == 0 for r in component['files']))
        self.assertEqual(component['dependencies'], [self.provider]);self.assertEqual(component['version']['release_id'], '0.2.0-r3')
        self.assertEqual(component['provenance']['assembled_manifest'], self.manifest['id'])
        self.assertIn(dict(path='payload/units/default.target', type='symlink', mode=0o777, uid=0, gid=0, target='mojt.target'), component['files'])
        options = self.register();events = list(self.adapter.events)
        with mock.patch.dict(os.environ, {'PATH':''}):
            preview = source_install.install(self.root, self.source_root, self.cache_root, 'system-kit',
                result['kit']['description']['generation'], dry_run=True, **options)
        self.assertFalse(preview['plan']['description']['profile_validated']);self.assertEqual(tree(self.root), {})
        self.assertFalse(self.cache_root.exists());self.assertEqual(self.adapter.events, events)
        self.assertEqual(tree(self.profile), before);self.assertFalse(self.marker.exists())

    def test_escaping_dangling_and_looping_links_are_refused_without_publishing_a_kit(self):
        path = self.profile / 'bad-link'
        for index, target in enumerate(('/etc/shadow', '../outside', 'missing', 'bad-link', self.provider['identity']['output'] + '-other/file')):
            with self.subTest(target=target):
                if path.is_symlink():path.unlink()
                path.symlink_to(target);self.write_manifest();destination = self.work / ('bad-kit-' + str(index))
                with self.assertRaises(ValueError):self.pack(destination)
                self.assertFalse(destination.exists());self.assertEqual(tree(self.root), {})
        real = nix.NixBinaryAdapter('/pinned/nix-store')
        self.assertTrue(real.contains(self.provider, self.provider['identity']['output'] + '/bin/python3'))
        with mock.patch.object(Path, 'resolve', return_value=Path('/etc/shadow')):
            with self.assertRaisesRegex(ValueError, 'escapes closure'):real.verify_path(self.provider, self.provider['identity']['output'] + '/bin/python3')


@unittest.skipUnless(os.geteuid() == 0 and shutil.which('zstd'), 'numeric-owner source installation requires root')
class SourceInstallTests(PackageFixture):
    def test_named_source_fetches_whole_bundle_and_retains_component_origin_links_and_noop_offline(self):
        result = self.pack();options = self.register();identifier = result['kit']['description']['generation']
        actual = source_install.install(self.root, self.source_root, self.cache_root, 'system-kit', identifier,
            yes=True, adapters={'nix':self.adapter}, **options)
        self.assertTrue(actual['changed']);self.assertEqual(self.adapter.events.count('ensure'), 1)
        status = system.status(self.root, verify=True, adapters={'nix':self.adapter})
        self.assertEqual(len(status['installed']), 1)
        for row in status['components'] + status['installed']:
            self.assertEqual(row['acquisition']['name'], 'system-kit')
        profile = Path(status['installed'][0]['profile'])
        measured = artifact.read_json(profile / 'manifest.json')
        self.assertIn('/run/mojt-system/bin/daemon', measured['description']['provides'])
        self.assertIn(('path', self.provider['identity']['output'] + '/sbin/daemon', True), self.adapter.events)
        self.assertEqual(os.readlink(profile / 'units/default.target'), 'mojt.target')
        self.assertEqual(os.readlink(profile / 'bin/python3'), self.provider['identity']['output'] + '/bin/python3')
        self.assertIn('profile-symlinks', system.required_capabilities(self.root))
        self.assertIn('profile-runtime-outputs', system.required_capabilities(self.root))
        self.assertFalse(result['kit']['description']['deployment_ready'])
        before = tree(self.root);cache_before = tree(self.cache_root);self.adapter.events.clear()
        shutil.rmtree(self.kit)
        self.assertFalse(source_install.install(self.root, self.source_root, self.cache_root, 'system-kit', identifier,
            yes=True, adapters={'nix':self.adapter}, **options)['changed'])
        self.assertNotIn('ensure', self.adapter.events);self.assertEqual(tree(self.root), before);self.assertEqual(tree(self.cache_root), cache_before)
        self.assertFalse(self.marker.exists());self.assertEqual(status['selected']['state'], 'unknown')
