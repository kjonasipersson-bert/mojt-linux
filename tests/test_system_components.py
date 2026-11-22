# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Component profile boundaries and real packages; no target boot claim."""
import copy
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest import mock
from test_mpm_system import Fixture,pack,spec
import mojt_artifact as artifact
import mojt_system_package as packaging
import mpm_base as base
import mpm_boot_inventory as inventory
import mpm_management as management
import mpm_system as system
import mpm_system_model as model
import mpm_system_transition as transition


@unittest.skipUnless(os.geteuid()==0 and shutil.which('zstd'),'requires numeric root ownership and native codec')
class Components(Fixture):
    def setUp(self):
        super().setUp()
        content=self.work/'component-source'
        firmware=content/'kernel/lib/firmware';firmware.mkdir(parents=True)
        (firmware/'fixture.bin').write_bytes(b'firmware content, never executed\n'*4096)
        (content/'start').write_text('#!/bin/sh\n/bin/busybox echo MOJT_COMPONENT_SYSTEM:$(/bin/busybox cat /run/mojt-system/version)\n')
        (content/'start').chmod(0o755)
        (content/'version').write_text('system-native-test\n')
        licenses=content/'kernel/licenses/vendor';licenses.mkdir(parents=True)
        (licenses/'copyright').write_text('upstream fixture attribution\n')
        result=pack(content,spec('component'),self.work/'firmware-original')
        self.component=result['artifact'];self.component_archive=self.work/'firmware-original'/result['archive']['file']
        self.reference=dict(provider='native',artifact=self.component['id'])
        d=copy.deepcopy(self.composition['description']);d['components']=[dict(role='runtime',reference=self.reference)]
        d['profile']=[dict(path=n,source=dict(reference=self.reference,path=n)) for n in ('bin','kernel','start','tools','version')]
        self.composition=base.record(model.FORMAT,d)
        self.archive,self.body=self.package(self.composition)
        self.install()

    def build(self,baseline=None,label='component-first',firmware='keep'):
        return packaging.package_installed(self.root,baseline or self.body['id'],self.work/label,label=label,firmware=firmware)

    def import_package(self,candidate):
        output=self.work/candidate['label']
        return system.install(self.root,output/candidate['generation'],candidate['artifact'],
            dependency_files=[output/p for p in candidate['dependency_files']],yes=True)

    def test_runtime_updates_reuse_firmware_without_reading_copying_or_packing_its_data(self):
        old=system.object_path(self.root,self.reference['artifact'])/'payload/kernel/lib/firmware'
        opener=Path.open
        def guarded(path,*args,**kwargs):
            if path.is_relative_to(old):raise AssertionError('firmware data read: '+str(path))
            return opener(path,*args,**kwargs)
        with mock.patch.object(Path,'open',guarded):
            a=self.build();self.import_package(a)
            b=self.build(a['artifact'],'component-second');self.import_package(b)
        self.assertEqual(a['firmware'],self.reference);self.assertEqual(b['firmware'],self.reference)
        self.assertFalse(self.marker.exists())
        profile=system.realization_path(self.root,b['artifact'])/'profile';manifest=base.read(profile/'manifest.json')
        self.assertLess(len(manifest['description']['profile']),20)
        original=base.read(system.realization_path(self.root,self.body['id'])/'profile/manifest.json')
        self.assertTrue(transition.profile_review(original,manifest,profile)['description']['compatible'])
        self.assertTrue((profile/'tools').is_symlink())
        self.assertEqual(system.profile_file(profile,'kernel/lib/firmware/fixture.bin'),old/'fixture.bin')
        self.assertTrue(management.retained(profile,manifest))
        previous=base.read(system.realization_path(self.root,a['artifact'])/'profile/manifest.json')
        self.assertTrue(transition.profile_review(previous,manifest,profile)['description']['compatible'])
        system.realization(self.root,b['artifact'],verify=True)

    def test_minimal_generation_has_no_firmware_component_or_bulk_payload(self):
        candidate=self.build(label='minimal',firmware='none');self.import_package(candidate)
        self.assertIsNone(candidate['firmware'])
        profile=system.realization_path(self.root,candidate['artifact'])/'profile';manifest=base.read(profile/'manifest.json')
        self.assertNotIn('kernel/lib/firmware',manifest['description']['profile'])
        original=base.read(system.realization_path(self.root,self.body['id'])/'profile/manifest.json')
        self.assertTrue(transition.profile_review(original,manifest,profile)['description']['compatible'])

    def test_minimal_hardware_selection_retains_module_policy_and_uses_no_firmware_mount(self):
        import mojt_hardware as hardware
        content=self.work/'component-source'
        data=dict(format=2,profile=hardware.PC_PROFILE,kernel_release='fixture-kernel',modules_tree_sha256='a'*64,
            firmware_tree_sha256='b'*64,licenses_tree_sha256='c'*64,early_modules=list(hardware.early_modules(hardware.PC_PROFILE)),
            runtime_modules=list(hardware.runtime_modules(hardware.PC_PROFILE)),modules_location='native-kernel')
        (content/'hardware.json').write_bytes(artifact.canonical(data))
        result=pack(content,spec('component'),self.work/'hardware-original')
        self.reference=dict(provider='native',artifact=result['artifact']['id'])
        self.component_archive=self.work/'hardware-original'/result['archive']['file']
        d=copy.deepcopy(self.composition['description']);d['components']=[dict(role='runtime',reference=self.reference)]
        d['profile']=[dict(path=n,source=dict(reference=self.reference,path=n)) for n in ('bin','hardware.json','kernel','start','tools','version')]
        self.composition=base.record(model.FORMAT,d);self.archive,self.body=self.package(self.composition)
        self.install()
        candidate=self.build(label='minimal-hardware',firmware='none');self.import_package(candidate)
        profile=system.realization_path(self.root,candidate['artifact'])/'profile';manifest=base.read(profile/'manifest.json')
        self.assertIsNone(hardware.native_firmware(profile))
        original=base.read(system.realization_path(self.root,self.body['id'])/'profile/manifest.json')
        review=transition.profile_review(original,manifest,profile)
        self.assertTrue(review['description']['compatible'],review)
        current=system.profile_file(profile,'hardware.json');current.chmod(0o644);current.write_bytes(b'{}');current.chmod(0o444)
        with self.assertRaisesRegex(ValueError,'metadata differs'):hardware.native_firmware(profile)

    def test_descriptor_measurement_matches_sealed_component_tree(self):
        root=system.object_path(self.root,self.reference['artifact'])/'payload'
        self.assertEqual(inventory.component_measurement(self.component),inventory.measure(root))

    def test_new_runtime_bytes_are_checked_during_normal_component_import(self):
        candidate=self.build();output=self.work/candidate['label']
        archive=output/candidate['dependency_files'][0]
        raw=subprocess.run(['zstd','-qd','-c',str(archive)],check=True,capture_output=True).stdout
        original=b'def component_profile(manifest):';self.assertIn(original,raw)
        damaged=self.work/'damaged-runtime.tar.zst'
        damaged.write_bytes(subprocess.run(['zstd','-q','-c'],input=raw.replace(original,b'def component_profile(manifesX):'),
            check=True,capture_output=True).stdout)
        with self.assertRaisesRegex(ValueError,'checksum differs'):
            system.install(self.root,output/candidate['generation'],candidate['artifact'],dependency_files=[damaged],yes=True)
        self.assertIsNone(system.realization(self.root,candidate['artifact']))

    def test_explicit_audit_detects_retained_firmware_damage(self):
        candidate=self.build();self.import_package(candidate)
        data=system.object_path(self.root,self.reference['artifact'])/'payload/kernel/lib/firmware/fixture.bin'
        data.chmod(0o644);data.write_bytes(b'damaged retained firmware');data.chmod(0o444)
        self.assertIsNotNone(system.realization(self.root,candidate['artifact']))
        with self.assertRaises(ValueError):system.realization(self.root,candidate['artifact'],verify=True)

    def test_projection_retargeting_is_refused_without_a_full_byte_audit(self):
        candidate=self.build();self.import_package(candidate)
        profile=system.realization_path(self.root,candidate['artifact'])/'profile'
        link=profile/'tools';profile.chmod(0o755);link.unlink();link.symlink_to('/etc');profile.chmod(0o555)
        with self.assertRaisesRegex(ValueError,'thin System profile differs'):
            system.realization(self.root,candidate['artifact'])
