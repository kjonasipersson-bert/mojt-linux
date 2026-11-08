# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Focused boot-v2 identity, immutable retention and publication failure cases."""
import copy
import hashlib
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import mojt_artifact as artifact
import mpm_base as base
import mpm_boot_v2 as model
import mpm_boot_v2_store as store
import mpm_catalog as catalog
import mpm_deployment as deployment
import mpm_native_io as io
import mpm_system as system
import mpm_transaction as tx
from mpm_request_plan import record


def fixture():
    return record(model.INPUTS, dict(installation='1'*32, platform='x86_64-linux', layout='native-v2',
        base=dict(artifact='sha256:'+'a'*64, release='0.1.3', rootfs_sha256='b'*64,
                  kernel_min='6.12.0', kernel_max='6.12.999', bounds_evidence='sha256:'+'c'*64),
        system=dict(artifact='sha256:'+'d'*64, composition='sha256:'+'e'*64, manifest='sha256:'+'f'*64, generation='system-A'),
        kernel=dict(artifact='sha256:'+'2'*64, release='6.12.107-mojt1', upstream='6.12.107', image_sha256='3'*64, modules_digest='sha256:'+'4'*64),
        firmware=[], boot=dict(root_uuid='12345678-1234-1234-1234-123456789abc', console='serial', profile=model.PROFILE, extra_args=['quiet']),
        constructor=dict(provider='fixture', identity={'version':1}), state_requirements=[], management_required=[]))


def bound(source, data=b'opaque constructor output', image_size=10):
    binding = record(model.BINDING, dict(inputs=source['id'], constructor=copy.deepcopy(source['description']['constructor']),
                                       archive=dict(sha256=hashlib.sha256(data).hexdigest(), size=len(data))))
    return model.compose(source, binding, image_size)


class Records(unittest.TestCase):
    def test_closed_acyclic_records_and_complete_menu_are_pure(self):
        source = fixture();value = bound(source);saved = copy.deepcopy(value)
        choice = record(model.SELECTION, dict(installation=source['description']['installation'], selected=value['id'], previous=None,
            requests=[dict(area=a, state=None) for a in ('base','kernel','system')], entries=[dict(deployment=value['id'], path=model.slot(value['id']))]))
        entries = {value['id']:value};menu = model.render(choice, entries)
        self.assertEqual(model.parse_menu(menu, entries), choice);self.assertEqual(value, saved)
        self.assertIn(('mojt.deployment='+value['id'][7:]).encode(), menu)
        self.assertNotIn(b'mojt.system=', menu)
        self.assertIn(('search --no-floppy --fs-uuid --set=root '+source['description']['boot']['root_uuid']).encode(),menu)
        with self.assertRaises(ValueError):model.parse_menu(menu+b'# edited\n', entries)
        for edit in (lambda d:d.update(layout='native-v1'), lambda d:d.update(extra=True),
                     lambda d:d['boot'].update(extra_args=['init=/evil']), lambda d:d['boot'].update(console='local'),
                     lambda d:d['base'].update(kernel_max='6.12.100'), lambda d:d['kernel'].update(upstream='6.12.107-mojt1'),
                     lambda d:d.update(firmware=[{'provider':'fixture','identity':{'x':1}}]),
                     lambda d:d.update(management_required=[dict(family='boot', read=[True], write=[True], capabilities=[])])):
            changed=copy.deepcopy(source['description']);edit(changed)
            with self.subTest(changed=changed), self.assertRaises(ValueError):model.inputs(record(model.INPUTS, changed))
        equivalent=copy.deepcopy(source['description']);equivalent['base'].update(kernel_min='6.12.0',kernel_max='6.12');equivalent['kernel']['upstream']='6.12'
        model.inputs(record(model.INPUTS,equivalent))
        broken=copy.deepcopy(value['description']);broken['initramfs']=record(model.BINDING,dict(broken['initramfs']['description'],inputs='sha256:'+'0'*64))
        with self.assertRaises(ValueError):model.deployment(record(model.DEPLOYMENT,broken))
        broken=copy.deepcopy(choice['description']);broken['entries'][0]['path']+='-other'
        with self.assertRaises(ValueError):model.selection(record(model.SELECTION,broken))
        broken=copy.deepcopy(choice['description']);broken['installation']='9'*32
        with self.assertRaises(ValueError):model.render(record(model.SELECTION,broken),entries)


@unittest.skipUnless(os.geteuid()==0 and all(shutil.which(c) for c in ('zstd','cpio','tar')), 'requires root and archive tools')
class Retention(unittest.TestCase):
    def setUp(self):
        import test_mpm_system_transition as fixtures
        self.f=fixtures.DiskTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root;self.bounds=base.read(self.f.f.fixture.bounds)
        source=fixture()['description'];source['installation']=base.store_info(self.root)['installation']
        body,receipt=base.object_record(self.root,self.bounds['base']['artifact'])
        realized=base.realization(self.root,body['id'],receipt)
        source['base']=dict(self.bounds['base'],rootfs_sha256=realized['description']['rootfs_sha256'],
            kernel_min=self.bounds['kernel_min'],kernel_max=self.bounds['kernel_max'],bounds_evidence=artifact.digest(self.bounds))
        realized=system.realization(self.root,self.f.identifier)
        source['system']=dict(artifact=self.f.identifier,composition=realized['description']['composition'],manifest=realized['description']['manifest'],generation='native-fixture')
        body=self.f.f.fixture.kernel;source['kernel']=dict(deployment.kernel_identity(body),upstream=body['version']['upstream'])
        self.source=record(model.INPUTS,source)
        self.image=self.f.f.fixture.work/'input-vmlinuz'
        shutil.copyfile(self.root/'kernel/installed'/io.identifier(body['id'])/'payload/boot'/('vmlinuz-'+source['kernel']['release']),self.image)
        self.initramfs=self.f.f.fixture.work/'constructor-output';self.initramfs.write_bytes(b'opaque constructor fixture; not boot acceptance')
        self.value=bound(self.source,self.initramfs.read_bytes(),self.image.stat().st_size)

    def retain(self, **kw):
        return store.retain(self.root,self.value,self.image,self.initramfs,bounds=self.bounds,adapters=self.f.adapters,**kw)

    def unchanged(self, before):
        after=self.f.f.snapshot()
        self.assertEqual(before,{p:after.get(p) for p in before})

    def test_retention_preview_retry_and_corruption_without_selection_or_input_dependency(self):
        before=self.f.f.snapshot();result=self.retain(dry_run=True)
        self.assertFalse(result['changed']);self.assertEqual(before,self.f.f.snapshot())
        wrong=copy.deepcopy(self.bounds);wrong['kernel_max']='6.12.998'
        with self.assertRaisesRegex(ValueError,'bounds evidence'):
            store.audit_inputs(self.root,self.source,wrong,adapters=self.f.adapters)
        result=self.retain();self.assertTrue(result['changed']);self.assertFalse(result['boot_ready'] or result['selection_changed'])
        self.assertEqual(store.inspect(self.root,self.value['id']),self.value)
        self.unchanged(before)
        self.image.unlink();self.initramfs.unlink();snapshot=self.f.f.snapshot()
        self.assertFalse(self.retain()['changed']);self.assertEqual(snapshot,self.f.f.snapshot())
        with self.assertRaisesRegex(ValueError,'unexpected boot inputs'):
            store.inspect(self.root,self.value['id'],expected_inputs='sha256:'+'0'*64)
        path=self.root/model.slot(self.value['id'])/'vmlinuz';path.chmod(0o644);path.write_bytes(b'damaged');path.chmod(0o444)
        with self.assertRaisesRegex(ValueError,'boot bytes damaged'):self.retain()

    def test_publication_failure_preserves_complete_uncertain_slot_and_previous_boot_choice(self):
        before=self.f.f.snapshot();destination=self.root/model.slot(self.value['id'])
        with mock.patch.object(tx,'publish',side_effect=OSError('before rename')):
            with self.assertRaisesRegex(OSError,'before rename'):self.retain()
        self.assertFalse(destination.exists());self.unchanged(before)
        publish=tx.publish
        def uncertain(src,dst):
            def fail(path):raise OSError('flush failure')
            publish(src,dst,sync=fail)
        with mock.patch.object(tx,'publish',side_effect=uncertain):
            with self.assertRaises(tx.PublicationUncertain):self.retain()
        self.assertEqual(store.inspect(self.root,self.value['id']),self.value);self.unchanged(before)
        self.assertFalse(self.retain()['changed']);self.unchanged(before)


if __name__=='__main__':unittest.main()
