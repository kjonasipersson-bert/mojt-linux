# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Fresh bootstrap publication boundaries and one shared install/stage fixture."""
import copy
import errno
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
import mojt_artifact as artifact
import mojt_bootstrap as bootstrap
import mojt_boot as boot
import mpm_base as base
import mpm_boot_selection as selection
import mpm_boot_v2 as model


def request(tree, result, seed, archive):
    return base.record(bootstrap.REQUEST,dict(tree=str(tree),result=str(result),tree_identity=[tree.stat().st_dev,tree.stat().st_ino],
        creator_mount_namespace=os.readlink('/proc/self/ns/mnt'),seed=seed,
        archive=dict(sha256=artifact.file_sha(archive),size=archive.stat().st_size),
        system_version='0.2',system_revision=1,code=bootstrap.code_identity()))


class BoundaryTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cp'),'requires sparse file copy')
    def test_cross_filesystem_image_staging_preserves_sparse_disk_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source';source.mkdir();destination=root/'destination'
            (source/'metadata.json').write_text('{"retained":true}\n')
            with (source/'disk.img').open('wb') as stream:
                stream.write(b'first');stream.seek(128*1024*1024);stream.write(b'last')
            with mock.patch.object(Path,'rename',side_effect=OSError(errno.EXDEV,'different filesystems')):
                bootstrap.native.transfer_image(source,destination)
            self.assertEqual((source/'disk.img').stat().st_size,(destination/'disk.img').stat().st_size)
            self.assertLess((destination/'disk.img').stat().st_blocks*512,1024*1024)
            with (destination/'disk.img').open('rb') as stream:
                self.assertEqual(stream.read(5),b'first');stream.seek(-4,2);self.assertEqual(stream.read(),b'last')
            self.assertEqual((source/'metadata.json').read_bytes(),(destination/'metadata.json').read_bytes())
            with mock.patch.object(Path,'rename',side_effect=PermissionError('refused')),\
                 mock.patch.object(bootstrap.native.subprocess,'run',side_effect=AssertionError('must not copy')):
                with self.assertRaises(PermissionError):bootstrap.native.transfer_image(source,root/'refused')

    def test_host_utilities_are_selected_before_installing_the_guest_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);binary=root/'bin';sbin=root/'sbin'
            binary.mkdir();sbin.mkdir()
            # Reproduce the Debian split: unshare is on the child's PATH, while
            # chroot/mount/umount are available only through the parent's PATH.
            unshare=binary/'unshare';unshare.write_text('#!/bin/sh\nwhile [ "$#" -gt 0 ]; do\n'
                'case "$1" in --*) shift ;; *) break ;; esac\ndone\nexec "$@"\n');unshare.chmod(0o755)
            for name in ('chroot','mount','umount'):
                path=sbin/name;path.write_text('#!/bin/sh\nprintf "%s\\n" "'+name+':$PATH"\n');path.chmod(0o755)
            guest=dict(PATH=str(binary),LC_ALL='C',HOME='/root')
            with mock.patch.dict(os.environ,dict(PATH=str(sbin)+os.pathsep+str(binary))):
                result=bootstrap.isolated(['chroot','/synthetic-jail'],root/'proc',env=guest,capture_output=True,text=True)
                self.assertEqual(result.stdout.strip(),'chroot:'+str(binary))
                for name in ('mount','umount'):
                    result=bootstrap.run(name,env=guest,capture_output=True,text=True)
                    self.assertEqual(result.stdout.strip(),name+':'+str(binary))
            self.assertEqual(guest,dict(PATH=str(binary),LC_ALL='C',HOME='/root'))

    def test_private_worker_direct_entrypoint_loads_bundled_code_with_isolated_python(self):
        result=subprocess.run([sys.executable,'-I','-B',str(REPO/'tools/mojt_bootstrap.py'),'--finalize-tree','/absent','--help'],
                              cwd='/',capture_output=True,text=True,env={'PATH':'/absent','PYTHONPATH':'/untrusted'})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Internal fresh-tree bootstrap worker',result.stdout)

    def test_private_worker_refuses_the_creator_namespace_before_mounting_or_writing(self):
        import test_mpm_base as fixtures
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);tree=root/'filesystem';tree.mkdir();result=root/'result';result.mkdir()
            seed=fixtures.baseline(tree,'sha256:'+'a'*64);archive=root/'base.tar.zst';archive.write_bytes(b'fixture')
            value=request(tree,result,seed,archive);base.io.write_json(result/'bootstrap-request.json',value)
            with mock.patch.object(bootstrap,'run',side_effect=AssertionError('must not mount')):
                with self.assertRaisesRegex(ValueError,'private mount namespace'):
                    bootstrap.finalize_child(tree,result,archive)
            self.assertFalse((tree/'artifacts').exists());self.assertEqual(archive.read_bytes(),b'fixture')

    @unittest.skipUnless(shutil.which('zstd') and shutil.which('cpio'),'requires native fixture codecs')
    def test_real_input_preview_is_read_only_and_the_payload_must_support_accounts(self):
        import test_native_image as fixtures
        import test_system_vm as system_fixtures
        f=fixtures.NativeImageTests();f.setUp();self.addCleanup(f.doCleanups)
        source=system_fixtures.SystemVmTests();source.setUp();self.addCleanup(source.doCleanups)
        source.fixture(10);f.args.system_payload=source.payload
        f.args.login_mode='password';f.args.dry_run=True;f.args.system_version='0.2';f.args.system_revision=1
        before=f.snapshot();payload_before=bootstrap.paths.tree_hash(source.payload)
        with mock.patch.object(bootstrap,'run',side_effect=AssertionError('must not execute a namespace')):
            result=bootstrap.build(f.args)
            self.assertEqual(result['layout'],'native-v2');self.assertFalse(result['image_written'] or result['boot_acceptance'])
            self.assertEqual(result['base'],f.base['id']);self.assertEqual(result['kernel'],f.kernel['id'])
        self.assertFalse(f.args.output.exists());self.assertEqual(before,f.snapshot())
        self.assertEqual(payload_before,bootstrap.paths.tree_hash(source.payload))
        f.args.login_mode='development'
        with self.assertRaisesRegex(ValueError,'password login'):bootstrap.build(f.args)
        self.assertFalse(f.args.output.exists())

    def test_native_disk_packer_cannot_regenerate_the_legacy_menu_or_change_scope(self):
        import test_mpm_boot_v2 as fixtures
        source=fixtures.fixture();deployment=fixtures.bound(source)
        choice=model.record(model.SELECTION,dict(installation=source['description']['installation'],selected=deployment['id'],previous=None,
            requests=[dict(area=a,state=None) for a in ('base','kernel','system')],entries=[dict(deployment=deployment['id'],path=model.slot(deployment['id']))]))
        entries={deployment['id']:dict(record=deployment)};i=source['description']
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);tree=root/'tree';tree.mkdir()
            with mock.patch.object(selection,'current',return_value=(choice,entries,b'v2 menu')), \
                 mock.patch.object(boot,'menu',side_effect=AssertionError('legacy menu overwritten')), \
                 mock.patch.object(boot.subprocess,'run',side_effect=RuntimeError('reached disk writer')) as run:
                with self.assertRaisesRegex(RuntimeError,'reached disk writer'):
                    boot.build_disk(root/'image',tree,root,512,i['boot']['root_uuid'],i['system']['generation'],i['base']['release'],native_selection=choice)
                run.reset_mock()
                with self.assertRaisesRegex(ValueError,'scope differs'):
                    boot.build_disk(root/'wrong-image',tree,root,512,i['boot']['root_uuid'],'wrong-System',i['base']['release'],native_selection=choice)
                run.assert_not_called()


@unittest.skipUnless(os.geteuid()==0 and all(shutil.which(p) for p in ('zstd','cpio','tar')),'requires root/native archive fixture tools')
class ConstructionTests(unittest.TestCase):
    def test_hardware_image_joins_accounts_firmware_and_exact_native_selection_before_publication(self):
        import test_native_image as fixtures
        import test_system_vm as system_fixtures
        import test_hardware_boot as hardware_fixtures
        import test_mpm_system_transition as provider_fixture
        import mojt_system_package as packer
        import mpm_boot_constructor as constructor
        f=fixtures.NativeImageTests();f.account_base=True;f.setUp();self.addCleanup(f.doCleanups)
        source=system_fixtures.SystemVmTests();source.setUp();self.addCleanup(source.doCleanups);source.fixture(10)
        hw=hardware_fixtures.HardwareTests();hw.setUp();self.addCleanup(hw.doCleanups)
        f.args.system_payload=source.payload;f.args.login_mode='password'
        foreign_home=f.work/'caller-home';foreign_home.mkdir(mode=0o700);f.args.output=foreign_home/'image'
        f.args.hardware_profile=bootstrap.native.hardware.PROFILE
        f.args.firmware_root=hw.firmware();f.args.with_build_tools=True
        firmware_before=bootstrap.paths.tree_hash(f.args.firmware_root)
        real_run=subprocess.run;which=shutil.which;tar=which('tar');seen=[]
        def finish(*,tree,result,base_package):
            runtime=tree/'system/native-fixture';manifest=base.read(runtime/'manifest.json')
            python_output=manifest['description']['artifacts']['nix']['packages']['python']['output']
            ref=dict(provider='nix',identity=dict(format='fixture-v1',output=python_output,objects=manifest['description']['artifacts']['nix']['objects']))
            adapter=provider_fixture.Adapter(tree,ref);adapter.binary=adapter.executable='/accepted/nix-store'
            adapter.boot_paths=lambda ref,target:sorted(r['path'].lstrip('/') for r in ref['identity']['objects'])
            adapter.boot_mounts=lambda ref,target:[dict(source='nix',target='nix')]
            prep=f.work/'preparation';prep.mkdir();archive=prep/'base.tar.zst';shutil.copyfile(base_package,archive)
            seed=base.read(result/'selected-deployment.json');value=request(tree,result,seed,archive)
            def run(args,**kwargs):
                if '--load-db' in args:return subprocess.CompletedProcess(args,0)
                return real_run(args,**kwargs)
            with mock.patch.object(bootstrap,'mountpoint',return_value=True),\
                 mock.patch.object(shutil,'which',side_effect=lambda name,*a,**kw:tar if str(name)==str(runtime/'libexec/mpm/bin/tar') else which(name,*a,**kw)),\
                 mock.patch.object(bootstrap.subprocess,'run',side_effect=run),\
                 mock.patch.object(packer,'nix_references',return_value=[ref]),\
                 mock.patch.object(constructor.archive,'vm_module',return_value=fixtures.fixtures.vm):
                outcome=bootstrap.construct(tree,runtime,value,prep/'work',adapter=adapter)
            bootstrap.record_result(tree,result,outcome);d=outcome['description'];seen.append(d)
            profile=tree/'realizations/system'/d['system'][7:]/'profile'
            self.assertTrue((profile/'units/mojt-console.service').is_file())
            self.assertEqual(bootstrap.native.hardware.native_firmware(profile),profile/'kernel/lib/firmware')
            self.assertFalse((profile/'kernel/lib/modules').exists())
            return d
        events=[];inspect=bootstrap.inspect_result;handoff=fixtures.fixtures.vm.handoff_result
        protected=bootstrap.tx.protected_directory
        def protect(path,**kwargs):
            # Emulate the invoking user's home even in single-UID user namespaces.
            if foreign_home == Path(path) or foreign_home in Path(path).parents:
                raise ValueError('unsafe Base target ancestor: caller-owned home')
            return protected(path,**kwargs)
        def inspect_owned(directory,**kwargs):
            events.append('verify');self.assertEqual((Path(directory)/'bootstrap.json').stat().st_uid,os.geteuid())
            return inspect(directory,**kwargs)
        def give_to_caller(directory):
            events.append('handoff');return handoff(directory)
        with mock.patch.object(fixtures.fixtures.vm,'password_hash_from_terminal',return_value='$6$synthetic$not-a-real-password'),\
             mock.patch.object(bootstrap,'inspect_result',side_effect=inspect_owned),\
             mock.patch.object(fixtures.fixtures.vm,'handoff_result',side_effect=give_to_caller),\
             mock.patch.object(bootstrap.tx,'protected_directory',side_effect=protect):
            built=f.synthetic_build(finalize_tree=finish)
        image=Path(built['output']);d=seen[0]
        self.assertEqual(events,['verify','verify','handoff']);self.assertEqual(built['bootstrap'],d)
        self.assertEqual(artifact.parse_json((image/'bootstrap.json').read_bytes())['description'],d)
        self.assertEqual((image/'bootstrap.json').stat().st_uid,int(os.environ.get('SUDO_UID','0')))
        self.assertEqual(d['deployment']['description']['inputs']['description']['boot']['profile'],model.HARDWARE_PROFILE)
        self.assertEqual(json.loads((image/'build.json').read_bytes())['boot_layout'],'native-v2')
        self.assertFalse((image/'run-qemu-direct.sh').exists())
        self.assertEqual(bootstrap.paths.tree_hash(f.args.firmware_root),firmware_before)

    def test_initial_native_install_stage_select_and_result_are_joined_without_state_changes(self):
        import test_kernel_boot as fixtures
        import test_mpm_system_transition as provider_fixture
        import mojt_system_package as packer
        import mpm_boot_constructor as constructor
        import mpm_system as system
        f=fixtures.KernelBootTests();f.setUp();self.addCleanup(f.doCleanups)
        root=f.root;runtime=root/'system/native-fixture';seed=f.entries[f.old_id]['record']
        manifest=base.read(runtime/'manifest.json')
        python_output=manifest['description']['artifacts']['nix']['packages']['python']['output']
        ref=dict(provider='nix',identity=dict(format='fixture-v1',output=python_output,objects=manifest['description']['artifacts']['nix']['objects']))
        adapter=provider_fixture.Adapter(root,ref)
        adapter.binary='/accepted/nix-store';adapter.executable='/accepted/nix-store'
        adapter.boot_paths=lambda ref,target:sorted(r['path'].lstrip('/') for r in ref['identity']['objects'])
        adapter.boot_mounts=lambda ref,target:[dict(source='nix',target='nix')]
        prep=f.fixture.work/'bootstrap-preparation';prep.mkdir();archive=prep/'base.tar.zst'
        shutil.copyfile(f.fixture.args.base_package,archive)
        result=prep/'result';result.mkdir();value=request(root,result,seed,archive)
        before={k:v for k,v in f.snapshot().items() if k.startswith('state/')}
        real_run=subprocess.run;registrations=[]
        which=shutil.which;tar=which('tar')
        def run(args,**kwargs):
            if '--load-db' in args:
                self.assertEqual(args,[adapter.binary,'--load-db']);registrations.append(args)
                return subprocess.CompletedProcess(args,0)
            return real_run(args,**kwargs)
        vm=constructor.archive.vm_module()
        with mock.patch.object(bootstrap,'mountpoint',return_value=True), \
             mock.patch.object(shutil,'which',side_effect=lambda name,*a,**kw:tar if str(name)==str(runtime/'libexec/mpm/bin/tar') else which(name,*a,**kw)), \
             mock.patch.object(bootstrap.subprocess,'run',side_effect=run), \
             mock.patch.object(packer,'nix_references',return_value=[ref]), \
             mock.patch.object(constructor.archive,'vm_module',return_value=vm), \
             mock.patch.object(vm,'module_paths',side_effect=lambda release,p,**kw:[p/'kernel/example.ko']), \
             mock.patch.object(vm,'static_x86_64_elf',return_value=True),mock.patch.object(vm,'validate_busybox_applets'), \
             mock.patch.object(vm.os,'mknod',side_effect=lambda path,*unused:path.touch()):
            completed=bootstrap.construct(root,runtime,value,prep/'work',adapter=adapter)
        d=completed['description'];self.assertEqual(len(registrations),1)
        self.assertEqual(d['layout'],'native-v2');self.assertFalse(d['boot_acceptance'])
        self.assertEqual(d['base'],f.fixture.base['id']);self.assertEqual(d['kernel'],f.fixture.kernel['id'])
        self.assertEqual(base.store_info(root)['installation'],d['installation'])
        current,entries,raw=selection.current(root,verify=True)
        self.assertEqual(current,d['selection']);self.assertEqual(current['description']['selected'],d['deployment']['id'])
        self.assertEqual(entries[d['deployment']['id']]['record'],d['deployment'])
        self.assertTrue(system.realization(root,d['system'],verify=True))
        self.assertEqual(before,{k:v for k,v in f.snapshot().items() if k.startswith('state/')})
        self.assertEqual((root/'boot/mojt/grub.cfg').read_bytes(),selection.HOOK)
        base.io.write_json(result/'bootstrap.json',completed);base.io.write_json(result/'selected-deployment.json',d['deployment'])
        with self.assertRaises(FileNotFoundError):bootstrap.inspect_result(result,base_artifact=d['base'],kernel_artifact=d['kernel'])
        for name in ('vmlinuz','initramfs.cpio.gz'):
            shutil.copyfile(root/model.slot(d['deployment']['id'])/name,result/name)
        self.assertEqual(bootstrap.inspect_result(result,base_artifact=d['base'],kernel_artifact=d['kernel']),d)
        (result/'run-qemu-direct.sh').write_text('must not bypass native selection')
        with self.assertRaisesRegex(ValueError,'direct-boot bypass'):bootstrap.inspect_result(result,base_artifact=d['base'],kernel_artifact=d['kernel'])
        with mock.patch.object(bootstrap,'mountpoint',return_value=True), \
             mock.patch.object(bootstrap.subprocess,'run',side_effect=AssertionError('repeat must not touch provider')):
            with self.assertRaisesRegex(ValueError,'already initialized'):
                bootstrap.construct(root,runtime,value,prep/'retry',adapter=adapter)

    def test_failed_tree_finalizer_precedes_mkfs_and_never_publishes_a_vm(self):
        import test_native_image as fixtures
        f=fixtures.NativeImageTests();f.setUp();self.addCleanup(f.doCleanups)
        before=f.snapshot();called=[]
        def fail(**args):
            called.append(args);self.assertTrue(args['tree'].is_dir())
            self.assertFalse((args['result']/'disk.img').exists())
            self.assertTrue(args['base_package'].is_file())
            raise ValueError('injected native-v2 constructor failure')
        with self.assertRaisesRegex(ValueError,'native-v2 constructor failure'):
            f.synthetic_build(finalize_tree=fail)
        self.assertEqual(len(called),1);self.assertFalse(f.args.output.exists());self.assertEqual(before,f.snapshot())


if __name__=='__main__':unittest.main()
