# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Reusable payload inputs, sealed cache and real concatenated archive bytes."""
import copy
import gzip
from contextlib import nullcontext
from pathlib import Path
import os
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zlib

import test_mpm_boot_v2 as fixtures
import mojt_artifact as artifact
import mpm_boot_constructor as constructor
import mpm_boot_early as early
import mpm_boot_inventory as inventory
import mpm_boot_v2 as model
import mpm_native_io as io
import mpm_transaction as tx


def runtime():
    return model.record(early.RUNTIME,dict(reference=dict(provider='fixture',identity=dict(revision=1)),
        interpreter='/runtime/bin/python3',trees={'runtime':{'.':dict(type='directory')}}))


def source():
    value=fixtures.fixture()['description'];value=copy.deepcopy(value)
    names=('mpm_boot_constructor.py','mpm_boot_inventory.py','mpm_native_io.py','mpm_kernel_boot.py',
           'mojt-vm-build.py','mojt_hardware.py','mojt_native_image.py','mpm_cli.py')
    value['constructor']=dict(provider='mojt',identity=dict(busybox_sha256='b'*64,code={n:'c'*64 for n in names}))
    return model.record(model.INPUTS,value)


def members(raw):
    result=[]
    while raw:
        stream=zlib.decompressobj(16+zlib.MAX_WBITS)
        decoded=stream.decompress(raw)+stream.flush()
        assert stream.eof
        result.append(decoded);raw=stream.unused_data
    return result


class Inputs(unittest.TestCase):
    def test_base_system_labels_root_uuid_and_unrelated_cli_do_not_rebuild_heavy_payload(self):
        first=source();key=constructor.payload_key(first,runtime(),handover=True)
        d=copy.deepcopy(first['description'])
        d['base']['artifact']='sha256:'+'1'*64;d['base']['release']='0.1.4'
        d['system'].update(artifact='sha256:'+'8'*64,generation='system-other')
        d['boot']['root_uuid']='87654321-4321-4321-4321-abcdefabcdef'
        d['constructor']['identity']['code']['mpm_cli.py']='d'*64
        self.assertEqual(key,constructor.payload_key(model.record(model.INPUTS,d),runtime(),handover=True))
        text=artifact.canonical(key)
        self.assertNotIn(b'system-A',text);self.assertNotIn(first['description']['base']['artifact'].encode(),text)

    def test_kernel_runtime_busybox_producer_and_required_applets_invalidate_cache(self):
        first=source();key=constructor.payload_key(first,runtime(),handover=True)
        for change in ('kernel','busybox','producer'):
            d=copy.deepcopy(first['description'])
            if change=='kernel':d['kernel']['artifact']='sha256:'+'5'*64
            elif change=='busybox':d['constructor']['identity']['busybox_sha256']='e'*64
            else:d['constructor']['identity']['code']['mpm_boot_constructor.py']='f'*64
            with self.subTest(change=change):
                self.assertNotEqual(key,constructor.payload_key(model.record(model.INPUTS,d),runtime(),handover=True))
        changed=model.record(early.RUNTIME,dict(runtime()['description'],reference=dict(provider='fixture',identity=dict(revision=2))))
        self.assertNotEqual(key,constructor.payload_key(first,changed,handover=True))
        with mock.patch.object(constructor.paths,'SHUTDOWN_APPLETS',constructor.paths.SHUTDOWN_APPLETS|{'new-applet'}):
            self.assertNotEqual(key,constructor.payload_key(first,runtime(),handover=True))


@unittest.skipUnless(os.geteuid()==0,'cache sealing uses actual numeric root ownership')
class Cache(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.work=Path(self.temp.name);self.root=self.work/'disk';(self.root/'boot/mpm').mkdir(parents=True)
        self.key=constructor.payload_key(source(),runtime(),handover=True)

    def test_reuse_checks_exact_bytes_and_does_not_run_builder_again(self):
        raw=gzip.compress(b'owned payload',mtime=0)
        self.assertEqual(constructor.cached_payload(self.root,self.key,lambda:raw),(raw,False))
        build=mock.Mock(side_effect=AssertionError('unexpected rebuild'))
        self.assertEqual(constructor.cached_payload(self.root,self.key,build),(raw,True))
        build.assert_not_called()
        path=self.root/'boot/mpm/initramfs-payloads'/self.key['id'][7:]/'initramfs.cpio.gz'
        path.chmod(0o644);path.write_bytes(b'x'*len(raw));path.chmod(0o444)
        with self.assertRaisesRegex(ValueError,'bytes damaged'):
            constructor.cached_payload(self.root,self.key,lambda:raw)
        self.assertEqual(path.read_bytes(),b'x'*len(raw))

    def test_publication_failure_preserves_old_boot_choice_and_uncertain_cache(self):
        menu=self.root/'boot/mpm/grub.cfg';menu.write_bytes(b'old selection')
        raw=gzip.compress(b'payload',mtime=0)
        with mock.patch.object(tx,'publish',side_effect=OSError('before cache rename')):
            with self.assertRaisesRegex(OSError,'before cache rename'):
                constructor.cached_payload(self.root,self.key,lambda:raw)
        destination=self.root/'boot/mpm/initramfs-payloads'/self.key['id'][7:]
        self.assertFalse(destination.exists());self.assertEqual(menu.read_bytes(),b'old selection')
        publish=tx.publish
        def uncertain(source,target):
            def fail(path):raise OSError('cache parent flush')
            return publish(source,target,sync=fail)
        with mock.patch.object(tx,'publish',side_effect=uncertain):
            with self.assertRaises(tx.PublicationUncertain):constructor.cached_payload(self.root,self.key,lambda:raw)
        self.assertTrue(destination.exists());self.assertEqual(menu.read_bytes(),b'old selection')
        self.assertEqual(constructor.cached_payload(self.root,self.key,lambda:b'never'),(raw,True))

    def test_real_constructor_reuses_runtime_and_drivers_but_binds_fresh_system_overlay(self):
        bundle=self.work/'bundle';(bundle/'tree/runtime/bin').mkdir(parents=True)
        python=bundle/'tree/runtime/bin/python3';python.write_bytes(b'#!/bin/sh\nexit 0\n');python.chmod(0o755)
        d=dict(reference=dict(provider='fixture',identity=dict(revision=1)),interpreter='/runtime/bin/python3',
               trees={'runtime':inventory.snapshot(bundle/'tree/runtime')})
        frozen=model.record(early.RUNTIME,d);io.write_json(bundle/'runtime.json',frozen)
        busybox=self.work/'busybox';busybox.write_bytes(b'fake static BusyBox fixture');busybox.chmod(0o755)
        first=fixtures.fixture()['description'];first=copy.deepcopy(first)
        first['constructor']=constructor.constructor(frozen,busybox)
        for key in ('base','system'):
            path=self.root/('realizations/'+key+'/'+first[key]['artifact'][7:])/('tree/rootfs' if key=='base' else 'profile')
            path.mkdir(parents=True);(path/'fixture').write_text(key)
        modules=self.root/'kernel/installed'/first['kernel']['artifact'][7:]/'payload/lib/modules'
        modules.mkdir(parents=True)
        def make(root,busybox,modules,script,shutdown,*,extra_applets,archive_writer):
            root.mkdir();(root/'bin').mkdir();shutil.copy2(busybox,root/'bin/busybox')
            (root/'init').write_text(script);(root/'init').chmod(0o755)
            return archive_writer(root)
        vm=SimpleNamespace(static_x86_64_elf=lambda p:True,validate_busybox_applets=lambda *a,**k:None,
                           module_paths=mock.Mock(return_value=[]),make_initramfs=mock.Mock(side_effect=make))
        with mock.patch.object(constructor.store,'target',side_effect=lambda p:p), \
             mock.patch.object(constructor.store,'audit_inputs'), \
             mock.patch('mpm_base_transition.read_locks',side_effect=lambda p:nullcontext()), \
             mock.patch.object(constructor.system,'retained_providers',return_value=[]), \
             mock.patch.object(constructor.system,'native_components',return_value=[]), \
             mock.patch.object(constructor.archive,'vm_module',return_value=vm), \
             mock.patch.object(inventory,'clone_runtime',wraps=inventory.clone_runtime) as clone:
            source_a=model.record(model.INPUTS,first)
            a=constructor.build(self.root,source_a,bundle,busybox,self.work/'a',bounds={},adapters={},reuse_payload=True)
            self.assertFalse(a['payload_reused']);self.assertEqual(clone.call_count,1)
            second=copy.deepcopy(first);second['system'].update(artifact='sha256:'+'7'*64,generation='system-B')
            profile=self.root/'realizations/system'/second['system']['artifact'][7:]/'profile'
            profile.mkdir(parents=True);(profile/'fixture').write_text('second System')
            source_b=model.record(model.INPUTS,second)
            with mock.patch.object(constructor,'freeze_runtime',side_effect=AssertionError('warm reuse copied runtime')):
                b=constructor.build(self.root,source_b,None,busybox,self.work/'b',bounds={},adapters={},reuse_payload=True,runtime_value=frozen)
            self.assertTrue(b['payload_reused']);self.assertEqual(a['payload_key'],b['payload_key'])
            self.assertEqual(vm.make_initramfs.call_count,1);self.assertEqual(clone.call_count,1)
        frame_a=members(a['archive']);frame_b=members(b['archive'])
        self.assertEqual(len(frame_a),2);self.assertEqual(frame_a[0],frame_b[0]);self.assertNotEqual(frame_a[1],frame_b[1])
        self.assertIn(source_a['id'].encode(),frame_a[1]);self.assertIn(source_b['id'].encode(),frame_b[1])
        self.assertNotIn(source_a['id'].encode(),frame_a[0]);self.assertNotIn(b'mojt/inputs.json',frame_a[0])
        self.assertNotEqual(a['binding']['id'],b['binding']['id']);model.binding(b['binding'],source_b)
        self.assertFalse((self.root/'boot/mpm/grub.cfg').exists())


if __name__=='__main__':unittest.main()
