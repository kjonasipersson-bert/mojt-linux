# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Mounted-target guards, portable input data and EFI publication failures."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'tools'))
import mojt_artifact as artifact
import mojt_bootstrap as bootstrap
import mojt_bootstrap_inputs as kits
import mojt_mounted_install as mounted

UUID = '11111111-1111-4111-8111-111111111111'
ESP_UUID = '22222222-2222-4222-8222-222222222222'
IDENTITY = 'sha256:'+'a'*64


class PortableInputsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ('registry','payload'):
            (self.root/name).mkdir(); (self.root/name/'retained').write_text(name)
        for name in ('archive','busybox'):(self.root/name).write_bytes(name.encode())
        self.args = SimpleNamespace(base_artifact=IDENTITY, kernel_artifact='sha256:'+'b'*64,
                                    system_generation='system-installer', system_version='0.2',
                                    system_revision=1, with_build_tools=True, hardware_profile=None)
        self.kit = self.root/'kit'
        self.record = self.write_kit(self.kit)

    def write_kit(self, destination):
        return kits.write(destination, archive=self.root/'archive', bounds={'exact':'fixture'},
                                 registry=self.root/'registry', payload=self.root/'payload',
                                 busybox=self.root/'busybox', firmware=None, args=self.args)

    def test_exported_guest_links_are_preserved_without_a_host_nix_store(self):
        target = '/nix/store/'+'c'*32+'-guest-runtime/lib/libc.so.6'
        source = self.root/'payload'
        (source/'guest-library').symlink_to(target)
        (source/'guest-directory').symlink_to(target.rsplit('/',1)[0])
        before = kits.paths.tree_hash(source)
        destination = self.root/'linked-kit'
        record = self.write_kit(destination)
        directory, checked = kits.read(destination)
        self.assertEqual(checked,record)
        self.assertEqual(os.readlink(directory/'system-payload/guest-library'),target)
        self.assertTrue((directory/'system-payload/guest-directory').is_symlink())
        self.assertEqual(kits.paths.tree_hash(source),before)
        link = directory/'system-payload/guest-library'
        link.unlink(); link.symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError,'input changed'):kits.read(destination)

    def test_registry_links_still_cannot_escape_their_resource(self):
        secret = self.root/'host-secret'; secret.write_text('host-only bytes')
        (self.root/'registry/outside').symlink_to(secret)
        with self.assertRaisesRegex(ValueError,'link escapes'):
            self.write_kit(self.root/'unsafe-kit')

    def test_closed_inputs_expand_fixed_paths_and_preserve_explicit_target_and_label(self):
        details = {}
        args = kits.expand(['--inputs',str(self.kit),'--target-root','/mnt/root',
                            '--efi-directory','/mnt/esp','--system-generation','system-ssd'], details=details)
        parsed = bootstrap.parser().parse_args(args)
        self.assertEqual(parsed.base_package,self.kit/'base.tar.zst')
        self.assertEqual(parsed.base_artifact,IDENTITY)
        self.assertEqual(parsed.busybox,self.kit/'busybox')
        self.assertEqual(parsed.system_generation,'system-ssd')
        self.assertEqual(parsed.target_root,Path('/mnt/root'))
        self.assertEqual(details['id'],self.record['id'])
        self.assertNotIn('shadow',{p.name for p in self.kit.iterdir()})
        with self.assertRaisesRegex(ValueError,'do not mix'):
            kits.expand(['--inputs='+str(self.kit),'--base-artifact',IDENTITY])
        # Abbreviations must not override options bound by the closed kit.
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            bootstrap.parser().parse_args(kits.expand(['--inputs',str(self.kit),
                '--target-root','/mnt/root','--system-pay','/competing-payload']))

    def test_changed_extra_linked_and_unbounded_input_records_are_rejected(self):
        point = self.kit/'system-payload/retained'; original = point.read_bytes()
        point.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'input changed'):kits.read(self.kit)
        point.write_bytes(original); (self.kit/'extra').write_text('unknown')
        with self.assertRaisesRegex(ValueError,'unexpected'):kits.read(self.kit)
        (self.kit/'extra').unlink(); metadata = self.kit/'inputs.json'; content = metadata.read_bytes()
        metadata.unlink(); metadata.symlink_to(self.root/'archive')
        with self.assertRaisesRegex(ValueError,'regular installer'):kits.read(self.kit)
        metadata.unlink(); metadata.write_bytes(content+b' '*65536)
        with self.assertRaisesRegex(ValueError,'bounded'):kits.read(self.kit)

    def test_help_does_not_read_an_input_directory_or_relax_existing_input_requirements(self):
        self.assertEqual(kits.expand(['--inputs','/absent','--help']),['--inputs','/absent','--help'])
        command = [sys.executable,'-I','-B',str(REPO/'tools/mbt'),'bootstrap','--help']
        result = subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('--target-root',result.stdout); self.assertIn('--inputs',result.stdout)


class PartitionProbeTests(unittest.TestCase):
    def probe(self, *, role='root', label='gpt', partition_type=None, fs_type=None, version=None, uppercase_ids=False):
        table = dict(label=label,id='ABCDEF12-1111-4111-8111-111111111111' if uppercase_ids else UUID,sectorsize=512,partitions=[
            dict(node='/dev/test1',uuid='FEDCBA98-2222-4222-8222-222222222222' if uppercase_ids else ESP_UUID,type=partition_type or (mounted.ROOT_TYPE if role=='root' else mounted.ESP_TYPE),start=2048,size=100000)])
        filesystem = 'TYPE='+str(fs_type or ('ext4' if role=='root' else 'vfat'))+'\nUUID='+ (UUID if role=='root' else '1234-ABCD')+'\n'
        if role != 'root':filesystem += 'VERSION='+str(version or 'FAT32')+'\n'
        responses = [SimpleNamespace(stdout=json.dumps({'partitiontable':table})),SimpleNamespace(stdout=filesystem)]
        with mock.patch.object(mounted,'device',return_value=(Path('/dev/test1'),'8:1')),\
             mock.patch.object(mounted,'parent_disk',return_value=('/dev/test','8:0')),\
             mock.patch.object(mounted,'run',side_effect=responses):
            return mounted.probe_partition(dict(source='/dev/test1',device='8:1',fstype='ext4' if role=='root' else 'vfat'),role=role)

    def test_gpt_filesystem_and_partition_identities_are_bound(self):
        root = self.probe(); esp = self.probe(role='efi')
        self.assertEqual(root['uuid'],UUID); self.assertEqual(esp['partuuid'],ESP_UUID)
        uppercase=self.probe(uppercase_ids=True)
        self.assertEqual(uppercase['disk_id'],'abcdef12-1111-4111-8111-111111111111')
        self.assertEqual(uppercase['partuuid'],'fedcba98-2222-4222-8222-222222222222')
        for kwargs in ({'label':'dos'},{'partition_type':mounted.ESP_TYPE},{'fs_type':'xfs'},
                       {'role':'efi','version':'FAT16'}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):self.probe(**kwargs)

    def test_nested_live_and_shared_writable_target_paths_fail_before_device_access(self):
        with mock.patch.object(mounted.os,'geteuid',return_value=0),\
             mock.patch.object(mounted,'probe_partition',side_effect=AssertionError('must not probe')):
            for root,esp in (('/mnt/mojt','/mnt/mojt/boot/efi'),('/','/mnt/esp'),('/var/lib/target','/mnt/esp')):
                with self.subTest(root=root),self.assertRaises(ValueError):mounted.inspect(root,esp)


@unittest.skipUnless(os.geteuid()==0,'requires root-owned directory checks')
class MountedInspectionTests(unittest.TestCase):
    """Kernel device/mount metadata is injected; directory checks are real."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'root';self.esp=Path(self.tmp.name)/'esp'
        self.root.mkdir();self.esp.mkdir();self.swap=False;self.duplicate=False
        self.rows=[dict(id=i,device='8:'+str(i),root='/',path=str(p),options=['rw'],
                        fstype=fs,source='/dev/test'+str(i))
                   for i,p,fs in ((1,self.root,'ext4'),(2,self.esp,'vfat'))]
        original_stat=Path.stat;original_file=Path.is_file;original_read=Path.read_text
        def current_stat(path,*a,**kw):
            if str(path)=='/dev/test3':return SimpleNamespace(st_mode=stat.S_IFBLK,st_rdev=os.makedev(8,3))
            actual=original_stat(path,*a,**kw)
            if path in (self.root,self.esp):
                fields=list(actual);fields[2]=os.makedev(8,1 if path==self.root else 2);return os.stat_result(fields)
            return actual
        def current_file(path):
            return True if str(path)=='/sys/dev/block/8:3/partition' else original_file(path)
        def current_read(path,*a,**kw):
            if str(path)=='/proc/swaps':return 'Filename Type Size Used Priority\n'+('/dev/test3 partition 1024 0 -2\n' if self.swap else '')
            return original_read(path,*a,**kw)
        def probe(row,*,role):
            return dict(source=row['source'],device=row['device'],disk='/dev/test',disk_device='8:0',
                        disk_id=UUID,partuuid=UUID if role=='root' else ESP_UUID,
                        uuid=UUID if role=='root' else '1234-ABCD',start=2048,sectors=100000,sector_size=512)
        def device(path):return Path(path),'8:'+str(path)[-1]
        def run(*a,**kw):return SimpleNamespace(stdout='/dev/test1\n'+('/dev/test4\n' if self.duplicate else ''))
        for patch in (mock.patch.object(mounted,'mounts',side_effect=lambda:copy.deepcopy(self.rows)),
                      mock.patch.object(mounted,'probe_partition',side_effect=probe),
                      mock.patch.object(mounted,'device',side_effect=device),
                      mock.patch.object(mounted,'parent_disk',return_value=('/dev/test','8:0')),
                      mock.patch.object(mounted,'storage_drivers',return_value=['virtio_blk']),
                      mock.patch.object(mounted,'run',side_effect=run),
                      mock.patch.object(Path,'stat',new=current_stat),
                      mock.patch.object(Path,'is_file',new=current_file),
                      mock.patch.object(Path,'read_text',new=current_read)):
            patch.start();self.addCleanup(patch.stop)

    def test_only_empty_targets_with_stable_mount_identity_are_accepted(self):
        (self.root/'lost+found').mkdir()
        value=mounted.inspect(self.root,self.esp)
        mounted.recheck(value,fresh=True)
        self.rows[0]['id']=99
        with self.assertRaisesRegex(ValueError,'identity changed'):mounted.recheck(value,fresh=True)
        self.rows[0]['id']=1;(self.root/'keep').write_text('existing data')
        with self.assertRaisesRegex(ValueError,'not empty'):mounted.inspect(self.root,self.esp)

    def test_aliases_child_mounts_live_disk_swap_duplicate_uuid_and_existing_efi_are_refused(self):
        original=copy.deepcopy(self.rows)
        for extra in (dict(self.rows[0],path='/elsewhere'),
                      dict(self.rows[0],path=str(self.root/'child'),device='8:3'),
                      dict(self.rows[0],path='/running-root',device='8:3')):
            self.rows=copy.deepcopy(original)+[extra]
            with self.subTest(extra=extra),self.assertRaises(ValueError):mounted.inspect(self.root,self.esp)
        self.rows=original;self.swap=True
        with self.assertRaisesRegex(ValueError,'active swap'):mounted.inspect(self.root,self.esp)
        self.swap=False;self.duplicate=True
        with self.assertRaisesRegex(ValueError,'duplicated'):mounted.inspect(self.root,self.esp)
        self.duplicate=False;(self.esp/'EFI').mkdir()
        with self.assertRaisesRegex(ValueError,'not empty'):mounted.inspect(self.root,self.esp)

    def test_preview_is_read_only_and_writes_require_both_reviewed_target_identities(self):
        args=SimpleNamespace(target_root=self.root,efi_directory=self.esp,dry_run=True,
                             expected_root_uuid=None,expected_efi_partuuid=None)
        before=(list(self.root.iterdir()),list(self.esp.iterdir()))
        with mock.patch.object(native_module:=bootstrap.native,'preview',return_value={'base':{'id':'base'},'kernel':{'id':'kernel'}}),\
             mock.patch.object(bootstrap,'preflight',return_value={'privileged':'fixture'}):
            result=mounted.build(args)
        self.assertFalse(result['target_written'])
        self.assertEqual(before,(list(self.root.iterdir()),list(self.esp.iterdir())))
        with mock.patch.object(mounted,'storage_drivers',return_value=['nvme']),\
             mock.patch.object(native_module,'preview',side_effect=AssertionError('must not assemble')):
            with self.assertRaisesRegex(ValueError,'outside the selected initial boot profile'):
                mounted.build(args)
        args.dry_run=False
        with mock.patch.object(native_module,'build',side_effect=AssertionError('must not assemble')):
            with self.assertRaisesRegex(ValueError,'require --expected'):mounted.build(args)
            args.expected_root_uuid='wrong'
            with self.assertRaisesRegex(ValueError,'UUID differs'):mounted.build(args)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name); self.root = self.work/'target'; self.esp = self.work/'esp'
        self.tree = self.work/'filesystem'; self.result = self.work/'result'
        for path in (self.root,self.esp,self.tree,self.result):path.mkdir()
        (self.tree/'boot/mojt').mkdir(parents=True)
        (self.tree/'boot/mojt/grub.cfg').write_text('exact menu\n')
        (self.tree/'retained').write_bytes(b'installed artifact bytes')
        self.deployment = dict(id=IDENTITY,description={'inputs':{'description':{'boot':{'root_uuid':UUID,'console':'serial'}}}})
        self.choice = dict(description={'selected':IDENTITY})
        self.outcome = dict(base='base',kernel='kernel',system='system',deployment=self.deployment,selection=self.choice)
        self.value = dict(root={'path':str(self.root),'uuid':UUID},efi={'path':str(self.esp)})
        self.events = []; self.fail = None
        original_run = mounted.run
        def run(name,*args,**kwargs):
            if name == 'sync':
                self.events.append(('sync',str(args[-1]),(self.esp/'EFI').exists()))
                if self.fail == 'after-publication' and (self.esp/'EFI').exists():raise OSError('late flush failure')
                return subprocess.CompletedProcess([],0)
            if name == 'cp' and self.fail == 'copy':
                (self.root/'partial').write_text('incomplete copy');raise OSError('copy failed')
            return original_run(name,*args,**kwargs)
        def verify(root,**kwargs):
            if root == self.root:
                self.events.append(('target-verified',))
                if self.fail == 'verify':raise ValueError('copied proof differs')
                self.assertEqual((self.root/'retained').read_bytes(),b'installed artifact bytes')
                self.assertFalse((self.esp/'EFI').exists())
            return self.choice,{IDENTITY:{'record':self.deployment}},b'menu'
        def loader(config,work,*args):
            path=work/'loader';path.write_bytes(b'synthetic EFI bytes');return path
        def recheck(value,*,fresh):
            if fresh:mounted.empty(self.root,root=True);mounted.empty(self.esp)
        for target,attribute,side in ((mounted,'run',run),(mounted,'recheck',recheck),
                                     (mounted.boot,'efi_loader',loader),(mounted.selection,'current',verify)):
            patch=mock.patch.object(target,attribute,side_effect=side);patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(bootstrap,'inspect_result',return_value=self.outcome);patch.start();self.addCleanup(patch.stop)

    def publish(self):
        return mounted.publish(self.value,tree=self.tree,result=self.result,bootstrap=self.outcome,inputs_id=IDENTITY)

    def test_content_is_verified_and_flushed_before_fallback_efi_publication(self):
        result=self.publish()
        self.assertEqual(result['deployment'],IDENTITY)
        self.assertEqual((self.esp/'EFI/BOOT/BOOTX64.EFI').read_bytes(),b'synthetic EFI bytes')
        self.assertFalse((self.root/mounted.MARKER).exists())
        receipt=json.loads((self.root/mounted.RECEIPT).read_text())
        self.assertEqual(receipt['inputs_id'],IDENTITY);self.assertFalse(receipt['boot_acceptance'])
        self.assertEqual(self.events[0],('target-verified',))
        self.assertEqual(self.events[1],('sync',str(self.root),False))
        self.assertEqual(self.events[2],('sync',str(self.esp),False))
        self.assertEqual(self.events[3],('sync',str(self.esp),True))

    def test_copy_or_verification_failure_retains_partial_content_without_bootloader(self):
        for phase in ('copy','verify'):
            with self.subTest(phase=phase):
                self.fail=phase
                with self.assertRaises((OSError,ValueError)):self.publish()
                self.assertTrue((self.root/mounted.MARKER).is_file())
                self.assertFalse((self.esp/'EFI').exists())
                if phase == 'copy':self.assertTrue((self.root/'partial').exists())
                shutil.rmtree(self.root);self.root.mkdir()
                shutil.rmtree(self.result.parent/'mounted-efi')

    def test_capacity_failure_writes_no_target_marker_or_efi(self):
        with mock.patch.object(mounted.os,'statvfs',return_value=SimpleNamespace(f_bavail=0,f_frsize=4096)):
            with self.assertRaisesRegex(ValueError,'free space'):self.publish()
        self.assertEqual(list(self.root.iterdir()),[]);self.assertEqual(list(self.esp.iterdir()),[])

    def test_post_publication_failure_is_explicit_and_never_removes_the_loader(self):
        self.fail='after-publication'
        with self.assertRaisesRegex(mounted.tx.PublicationUncertain,'may be bootable'):self.publish()
        self.assertTrue((self.esp/'EFI/BOOT/BOOTX64.EFI').is_file())
        self.assertTrue((self.root/mounted.MARKER).is_file())


if __name__ == '__main__':unittest.main()
