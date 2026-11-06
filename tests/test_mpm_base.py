# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real Base archives and content-only target publication, without VM boot."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
import mojt_artifact as artifact
import mpm_base as base
import mpm_base_status as status
import mpm_base_source as source
import mpm_cli as cli
import mpm_sources as sources


def entry(name,content=None,*,kind=None,link='',mode=0o755):
    t=tarfile.TarInfo('./'+name);t.uid=t.gid=0;t.mode=mode
    if kind is not None:t.type=kind;t.linkname=link
    elif content is None:t.type=tarfile.DIRTYPE
    else:t.size=len(content)
    return t,content


def baseline(root,base_id):
    import mpm_deployment as dep
    import mojt_boot as boot
    d=dict(platform=os.uname().machine+'-linux',base=dict(artifact=base_id,release='0.1.3'),
        system=dict(manifest='sha256:'+'b'*64,generation='system-test'),
        kernel=dict(artifact='sha256:'+'c'*64,release='6.12.107-mojt1',image_sha256='d'*64,modules_digest='sha256:'+'e'*64),
        initramfs=dict(archive=dict(sha256='f'*64,size=10),binding='sha256:'+'1'*64),
        boot=dict(root_uuid='12345678-1234-1234-1234-123456789abc',console='serial',
                  cmdline=boot.cmdline('12345678-1234-1234-1234-123456789abc','system-test','0.1.3','serial')))
    value=dep.create(d);dep.validate_deployment(value)
    relative='boot/mojt/system-test/0.1.3';path=root/relative;path.mkdir(parents=True)
    (path/'deployment.json').write_bytes(artifact.canonical(value))
    menu=boot.terminal('serial')+'set timeout=10\nset default=0\n'
    menu+=(f"menuentry 'Mojt Base 0.1.3 / System system-test (Linux 6.12.107-mojt1)' {{\n"
           f"    linux /{relative}/vmlinuz {d['boot']['cmdline']}\n"
           f"    initrd /{relative}/initramfs.cpio.gz\n}}\n")
    (root/'boot/mojt/grub.cfg').write_text(menu)
    return value


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.work=Path(self.tmp.name);self.root=self.work/'disk';self.root.mkdir()
        self.serial=0;self.archive,self.body=self.package()

    def package(self,*,extra=(),revision=1,change=None):
        self.serial+=1;release=self.work/('release-'+str(self.serial));release.mkdir()
        rows=[entry(n) for n in ('.','usr','usr/lib','usr/etc','usr/bin','etc','var','home')]
        rows += [entry('root',mode=0o700),entry('usr/lib/os-release',b'ID=mojt\nIMAGE_VERSION="0.1.3"\n',mode=0o644),
                 entry('usr/bin/tool',b'#!/bin/sh\necho Base fixture\n'),entry('usr/etc/hostname',b'mojt-default\n',mode=0o644),
                 entry('lib',kind=tarfile.SYMTYPE,link='/usr/lib'),entry('bin',kind=tarfile.SYMTYPE,link='usr/bin')]
        if change:rows=change(rows)
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w:') as tar:
            for member,content in [*rows,*extra]:tar.addfile(member,io.BytesIO(content) if content is not None else None)
        compressed=subprocess.check_output(['zstd','-q','-c'],input=stream.getvalue())
        (release/'rootfs.tar.zst').write_bytes(compressed)
        checksum=artifact.file_sha(release/'rootfs.tar.zst')
        (release/'manifest.toml').write_text(f'''format = 1
[base]
name = "mojt"
version = "0.1.3"
architecture = "{os.uname().machine}"
[image]
file = "rootfs.tar.zst"
sha256 = "{checksum}"
[state]
layout_version = 1
etc_defaults = "/usr/etc"
etc_policy = "add-missing"
var_policy = "persistent"
''')
        spec,attachments=artifact.base_input(release,revision)
        result=artifact.pack(release,spec,self.work/('package-'+str(self.serial)),attachments)
        return self.work/('package-'+str(self.serial))/result['archive']['file'],result['artifact']

    def install(self,**kwargs):return base.install(self.root,self.archive,self.body['id'],yes=True,**kwargs)

    def source(self):
        helper=runpy.run_path(str(REPO/'tests/run-kernel-source-acceptance.py'))
        lab=self.work/'source-fixture';lab.mkdir()
        body,checksum=helper['prepare_repository'](self.archive,lab,'local',artifact=artifact,cache=sources.cache)
        registry=self.work/'sources';cache=self.work/'cache'
        args=dict(source=json.loads((lab/'source.json').read_text()),policy_file=lab/'policy.json')
        sources.add(registry,'local',sources.prepare_add(registry,'local',**args),**args)
        sources.update(registry,'local',sources.prepare_update(registry,'local'))
        return registry,cache,checksum,lab


@unittest.skipUnless(shutil.which('zstd'),'requires real zstd')
class PreviewTests(Fixture):
    def test_real_wrapper_and_rootfs_audited_without_target_writes(self):
        result=self.install(dry_run=True)
        self.assertTrue(result['archive_verified'] and result['rootfs_audited'])
        self.assertEqual(result['plan']['description']['selected'],'unchanged')
        self.assertEqual(list(self.root.iterdir()),[])

    def test_status_of_missing_target_creates_nothing(self):
        root=self.work/'absent'
        result=status.status(root)
        self.assertEqual(result['installed'],[]);self.assertIsNone(result['installation'])
        self.assertEqual(result['running']['state'],'unknown');self.assertFalse(root.exists())

    def test_interrupted_store_initialization_is_visible_without_adoption(self):
        stage=self.root/'.artifacts-init-retained';stage.mkdir();(stage/'partial').write_text('retain')
        result=status.status(self.root)
        self.assertEqual(result['installed'],[]);self.assertIsNone(result['installation'])
        self.assertEqual(result['incomplete'],[stage.name]);self.assertEqual((stage/'partial').read_text(),'retain')
        self.assertFalse((self.root/'artifacts').exists())

    def test_cli_status_needs_neither_provider_codec_nor_writable_target(self):
        env=dict(os.environ,PATH='/no-management-tools')
        p=subprocess.run([sys.executable,'-I','-B',str(REPO/'tools/mpm'),'base','status','--disk-root',str(self.root),'--json'],text=True,capture_output=True,env=env,cwd='/')
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['installed'],[])
        self.assertEqual(list(self.root.iterdir()),[])

    def test_base_area_help_lists_supported_operations_without_target_or_helpers(self):
        for command in (['base'],['base','--help']):
            p=subprocess.run([sys.executable,'-I','-B',str(REPO/'tools/mpm'),*command],cwd='/',
                             env=dict(os.environ,PATH='/absent'),text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertIn('install',p.stdout);self.assertIn('status',p.stdout)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_unsafe_linked_target_and_unsupported_store_refused(self):
        linked=self.work/'alias';linked.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):status.status(linked)
        (self.root/'artifacts').mkdir();(self.root/'artifacts/store.json').write_text('{}')
        with self.assertRaises(ValueError):status.status(self.root)

    def test_wrong_id_and_requirements_refused_before_target_changes(self):
        with self.assertRaises(ValueError):base.install(self.root,self.archive,'sha256:'+'0'*64,dry_run=True)
        body=copy.deepcopy(self.body);body['requirements']={'unsupported':'required'}
        body['id']=artifact.digest({k:v for k,v in body.items() if k!='id'})
        with self.assertRaisesRegex(ValueError,'requirements'):base.prepare(self.root,body)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_inner_traversal_symlink_descendants_and_state_data_rejected(self):
        cases=[entry('../escape',b'bad'),entry('etc/passwd',b'bad'),entry('lib/host-write',b'bad'),
               entry('usr/bin/hard',kind=tarfile.LNKTYPE,link='/host')]
        for extra in cases:
            with self.subTest(extra=extra[0].name):
                archive,body=self.package(extra=[extra])
                with self.assertRaises(ValueError):base.install(self.root,archive,body['id'],dry_run=True)
                self.assertEqual(list(self.root.iterdir()),[])
        self.assertFalse((self.work/'escape').exists())

    def test_identity_symlink_cannot_read_host_os_release(self):
        def change(rows):return [entry('usr/lib/os-release',kind=tarfile.SYMTYPE,link='/etc/os-release') if m.name=='./usr/lib/os-release' else (m,c) for m,c in rows]
        archive,body=self.package(change=change)
        with self.assertRaisesRegex(ValueError,'regular os-release'):base.install(self.root,archive,body['id'],dry_run=True)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_inner_decompression_and_header_budgets_are_bounded(self):
        with mock.patch.object(base,'MAX_ROOTFS',512),self.assertRaisesRegex(ValueError,'decompression'):
            self.install(dry_run=True)
        with mock.patch.object(base.artifact,'MAX_ENTRIES',12),self.assertRaises(ValueError):
            self.install(dry_run=True)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_source_preview_uses_only_frozen_metadata_and_no_archive(self):
        registry,cache,checksum,lab=self.source()
        (lab/'repository/kernel.tar.zst').unlink()
        result=source.install(self.root,registry,cache,'local',self.body['id'],archive_sha256=checksum,dry_run=True)
        self.assertTrue(result['dry_run']);self.assertFalse(result['plan']['description']['archive_verified'])
        self.assertFalse(cache.exists());self.assertEqual(list(self.root.iterdir()),[])

    def test_shared_mutation_denied_before_source_or_provider_work(self):
        with mock.patch.object(cli.os,'geteuid',return_value=1000),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['base','install','--source','unknown','--expected-id',self.body['id'],'-y'],runtime=cli.Runtime()),1)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_offline_status_never_attaches_inspector_running_identity(self):
        value=baseline(self.root,self.body['id'])
        (self.work/'running.json').write_text(json.dumps(value))
        runtime=cli.Runtime(disk=self.root,running=self.work/'running.json')
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):self.assertEqual(cli.main(['base','status','--disk-root',str(self.root),'--json'],runtime=runtime),0)
        result=json.loads(stream.getvalue());self.assertEqual(result['running']['state'],'unknown')
        self.assertEqual(result['selected']['state'],'unknown')
        known=status.status(self.root,running_record=value)
        self.assertEqual(known['selected']['artifact'],self.body['id']);self.assertTrue(known['running_is_selected'])
        self.assertEqual(known['running']['retention'],'not-in-this-store')

    def test_unknown_managed_boot_format_is_not_an_empty_success(self):
        (self.root/'boot/mojt').mkdir(parents=True)
        (self.root/'boot/mpm').mkdir()
        (self.root/'boot/mojt/grub.cfg').write_text('unsupported managed menu')
        (self.root/'boot/mpm/format').write_text('future-version\n')
        with self.assertRaisesRegex(ValueError,'managed boot'):status.status(self.root)

    def test_linked_store_marker_is_not_followed(self):
        outside=self.work/'external.json';outside.write_text('{}')
        (self.root/'artifacts').mkdir();(self.root/'artifacts/store.json').symlink_to(outside)
        with self.assertRaises(OSError):status.status(self.root)
        self.assertEqual(outside.read_text(),'{}')


@unittest.skipUnless(os.geteuid()==0 and shutil.which('tar') and shutil.which('zstd'),'requires root and GNU tar/zstd')
class BaseInstallTests(Fixture):
    def test_full_install_preserves_state_boot_and_target_owners(self):
        for name in ('state/etc/local','state/var/marker','state/home/user/file','state/root/file','boot/mojt/grub.cfg'):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('retain '+name)
        before={p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result=self.install();self.assertTrue(result['changed'])
        for name,data in before.items():self.assertEqual((self.root/name).read_bytes(),data)
        report=status.status(self.root,verify=True);self.assertEqual(len(report['installed']),1)
        tree=Path(report['installed'][0]['realization']);self.assertEqual(os.readlink(tree/'lib'),'/usr/lib')
        self.assertEqual((tree/'usr/bin/tool').stat().st_uid,0)
        self.assertEqual(stat.S_IMODE((tree/'root').stat().st_mode),0o700)
        self.assertFalse((self.root/'state/etc/hostname').exists());self.assertFalse((self.root/'base/current').exists())

    def test_same_label_distinct_artifacts_coexist(self):
        self.install();archive,body=self.package(extra=[entry('usr/bin/addition',b'extra')])
        self.assertEqual(body['version'],self.body['version']);self.assertNotEqual(body['id'],self.body['id'])
        base.install(self.root,archive,body['id'],yes=True)
        self.assertEqual({r['artifact'] for r in status.status(self.root,verify=True)['installed']},{self.body['id'],body['id']})

    def test_exact_repeat_without_original_archive_preserves_receipts(self):
        self.install();obj=base.object_path(self.root,self.body['id']);real=base.realization_path(self.root,self.body['id'])
        before=((obj/'installed.json').read_bytes(),(real/'realization.json').read_bytes())
        self.archive.unlink();self.assertFalse(self.install()['changed'])
        self.assertEqual(before,((obj/'installed.json').read_bytes(),(real/'realization.json').read_bytes()))

    def test_corrupt_runtime_detected_and_never_silently_repaired(self):
        self.install();tree=base.realization_path(self.root,self.body['id'])/'rootfs'
        (tree/'usr/bin/tool').write_bytes(b'corrupt')
        self.assertEqual(len(status.status(self.root)['installed']),1)
        with self.assertRaisesRegex(ValueError,'rootfs'):status.status(self.root,verify=True)
        with self.assertRaises(ValueError):self.install()
        self.assertEqual((tree/'usr/bin/tool').read_bytes(),b'corrupt')

    def test_no_installed_claim_when_extraction_fails_and_retry_uses_retained_object(self):
        original=base.subprocess.run
        def fail(command,**kwargs):
            if '-xf' in command:raise subprocess.CalledProcessError(2,command)
            return original(command,**kwargs)
        with mock.patch.object(base.subprocess,'run',side_effect=fail),self.assertRaises(subprocess.CalledProcessError):self.install()
        report=status.status(self.root,verify=True);self.assertEqual(report['installed'],[]);self.assertEqual(len(report['retained']),1)
        self.archive.unlink();self.assertTrue(self.install()['changed'])
        self.assertEqual(len(status.status(self.root)['installed']),1)

    def test_late_publication_uncertainty_retains_complete_realization(self):
        original=base.tx.publish
        def uncertain(source,dest):
            if dest.parent==self.root/'realizations/base':
                return original(source,dest,sync=lambda _:(_ for _ in ()).throw(OSError('injected flush failure')))
            return original(source,dest)
        with mock.patch.object(base.tx,'publish',side_effect=uncertain),self.assertRaises(base.tx.PublicationUncertain):self.install()
        self.assertEqual(len(status.status(self.root,verify=True)['installed']),1)
        self.assertFalse(self.install()['changed'])

    def test_source_origin_retained_and_repeat_needs_no_source_archive_or_cache(self):
        registry,cache,checksum,lab=self.source()
        args=dict(archive_sha256=checksum,yes=True)
        self.assertTrue(source.install(self.root,registry,cache,'local',self.body['id'],**args)['changed'])
        before=base.object_record(self.root,self.body['id'])[1]
        self.assertEqual(before['description']['trust']['kind'],'registered-native-source')
        shutil.rmtree(lab/'repository');shutil.rmtree(cache)
        self.assertFalse(source.install(self.root,registry,cache,'local',self.body['id'],**args)['changed'])
        self.assertEqual(before,base.object_record(self.root,self.body['id'],verify=True)[1])

    def test_installed_cli_runs_without_checkout_provider_or_path_fallback(self):
        import mojt_system as system
        copied=self.work/'delivered';copied.mkdir()
        for name in system.MPM_FILES:shutil.copyfile(REPO/'tools'/name,copied/name)
        helpers=self.work/'helpers';helpers.mkdir()
        for name in ('zstd','tar'):(helpers/name).symlink_to(shutil.which(name))
        launcher=self.work/'installed.py'
        launcher.write_text(f"import sys\nfrom pathlib import Path\nsys.path.insert(0,{str(copied)!r})\nfrom mpm_cli import main,Runtime\nraise SystemExit(main(runtime=Runtime(disk=Path({str(self.root)!r}),helpers=Path({str(helpers)!r}))))\n")
        command=[sys.executable,'-I','-B',str(launcher),'base','install','--disk-root',str(self.root),'--from-file',str(self.archive),'--expected-id',self.body['id'],'-y']
        p=subprocess.run(command,cwd='/',env=dict(os.environ,PATH='/absent'),text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertTrue(json.loads(p.stdout)['changed'])
        p=subprocess.run(command[:4]+['base','status','--disk-root',str(self.root),'--verify','--json'],cwd='/',env=dict(os.environ,PATH='/absent'),text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(len(json.loads(p.stdout)['installed']),1)

    def test_concurrent_fresh_imports_publish_one_complete_base(self):
        command=[sys.executable,'-I','-B',str(REPO/'tools/mpm'),'base','install','--disk-root',str(self.root),
                 '--from-file',str(self.archive),'--expected-id',self.body['id'],'-y']
        processes=[subprocess.Popen(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        results=[]
        for process in processes:
            output,error=process.communicate(timeout=30)
            self.assertEqual(process.returncode,0,error);results.append(json.loads(output))
        self.assertEqual(sum(r['changed'] for r in results),1)
        self.assertEqual(len(status.status(self.root,verify=True)['installed']),1)

    def test_failed_new_realization_keeps_previous_complete_base(self):
        self.install();archive,body=self.package(extra=[entry('usr/bin/second',b'new')])
        original=base.tx.publish
        def fail(source,dest):
            if dest.parent==self.root/'realizations/base':raise OSError('injected pre-publication failure')
            return original(source,dest)
        with mock.patch.object(base.tx,'publish',side_effect=fail),self.assertRaises(OSError):
            base.install(self.root,archive,body['id'],yes=True)
        report=status.status(self.root,verify=True)
        self.assertEqual([r['artifact'] for r in report['installed']],[self.body['id']])
        self.assertEqual([r['artifact'] for r in report['retained']],[body['id']])

    def test_damaged_origin_or_realization_record_is_rejected(self):
        self.install();path=base.realization_path(self.root,self.body['id'])/'realization.json'
        value=base.read(path);value['description']['artifact']='sha256:'+'0'*64
        path.chmod(0o644);path.write_text(json.dumps(base.record(base.REALIZATION,value['description'])));path.chmod(0o444)
        with self.assertRaisesRegex(ValueError,'binding'):status.status(self.root)

    def test_managed_selection_and_running_are_separate_metadata_observations(self):
        import mpm_deployment as dep
        import mpm_kernel_boot as boot
        self.install();running=baseline(self.root,self.body['id'])
        d=copy.deepcopy(running['description']);d['kernel']['artifact']='sha256:'+'8'*64;new=dep.create(d)
        slot='boot/mpm/slots/'+'2'*32;folder=self.root/slot;folder.mkdir(parents=True)
        (self.root/'boot/mpm/format').write_text(boot.FORMAT+'\n')
        (folder/'deployment.json').write_text(json.dumps(new))
        entries={running['id']:dict(record=running,relative='boot/mojt/system-test/0.1.3'),new['id']:dict(record=new,relative=slot)}
        state=dict(format=boot.FORMAT,selected=new['id'],previous=running['id'],entries={k:v['relative'] for k,v in entries.items()})
        (self.root/'boot/mojt/grub.cfg').write_bytes(boot.menu(state,entries))
        with mock.patch.object(artifact,'verify',side_effect=AssertionError('default status must not decode archives')):
            result=status.status(self.root,running_record=running)
        self.assertEqual(result['running']['deployment'],running['id'])
        self.assertEqual(result['selected']['deployment'],new['id'])
        self.assertFalse(result['running_is_selected'])


if __name__=='__main__':unittest.main()
