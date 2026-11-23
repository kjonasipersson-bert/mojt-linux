# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Source-only test delivery: real packaging and unchanged input/copy boundaries."""
import argparse
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

import test_base_source_build as source_tests
import test_mpm_boot_v2 as fixtures

REPO=Path(__file__).resolve().parents[1]


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,REPO/'tests'/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


host=load('prepare_base_transition','prepare-source-base-transition.py')
guest=load('run_base_transition','run-source-base-transition.py')


@unittest.skipUnless(shutil.which('zstd'),'real Base packaging requires zstd')
class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory();self.addCleanup(self.work.cleanup)
        self.root=Path(self.work.name).resolve();self.build=self.root/'build';self.build.mkdir()
        tree=self.build/'rootfs';tree.mkdir();source_tests.builder.skeleton(tree);source_tests.builder.defaults(tree)
        (tree/'usr/bin/sh').write_text('#!/bin/sh\n');(tree/'usr/bin/sh').chmod(0o755)
        config=self.build/'base.toml'
        config.write_text('format=1\n[base]\nname="mojt"\nversion="0.2.0"\narchitecture="x86_64"\n'
                          '[abi]\nlibc="glibc"\nlibc_version="2.44"\n[build]\nbackend="source"\n')
        (self.build/'packages.txt').write_text('source fixture\n')
        subprocess.run([sys.executable,'-I','-B',str(REPO/'tools/mojt-base-pack'),str(tree),str(config),
            str(self.build/'releases'),'--normalize-owner','--packages',str(self.build/'packages.txt')],
            check=True,capture_output=True)
        self.release=self.build/'releases/base-0.2.0-x86_64'
        (self.build/'result.json').write_text(json.dumps(dict(format='mojt-base-source-build-v1',
            release=str(self.release),phases=[dict(seconds=0.125)])))
        spec,_=host.artifact.base_input(self.release,1)
        d=copy.deepcopy(fixtures.fixture()['description']);d['base'].update(release='0.2.0',
            rootfs_sha256=spec['provenance']['rootfs_sha256'])
        self.original=fixtures.bound(fixtures.record(fixtures.model.INPUTS,d))
        self.vm=self.root/'vm/image';self.vm.mkdir(parents=True)
        (self.vm/'disk.img').write_bytes(b'original VM disk fixture'.ljust(4096,b'\0'))
        (self.vm/'bootstrap.json').write_text(json.dumps(host.base.record('mojt-bootstrap-result-v1',
            dict(layout='native-v2',deployment=self.original))))
        self.output=self.root/'new-test'
        self.argv=['--vm',str(self.vm),'--base-build',str(self.build),'--output',str(self.output)]

    def snapshot(self):
        return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_preview_accepts_real_build_timings_without_mutation_or_commands(self):
        before=self.snapshot()
        with mock.patch.object(host.os,'geteuid',return_value=1000),\
             mock.patch.object(host.shutil,'which',return_value='/usr/bin/fixture'),\
             mock.patch.dict(os.environ),\
             mock.patch.object(host.subprocess,'run',side_effect=AssertionError('preview must not execute')):
            host.main([*self.argv,'--check-inputs'])
        self.assertEqual(before,self.snapshot());self.assertFalse(self.output.exists())

    def test_existing_output_wrong_base_and_mismatched_build_are_refused(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError,'new nonsymlink'):
            host.inputs(argparse.Namespace(vm=self.vm,base_build=self.build,output=self.output))
        self.output.rmdir()
        record=host.read(self.vm/'bootstrap.json');d=record['description']
        changed=copy.deepcopy(self.original['description']['inputs']['description']);changed['base']['release']='0.1.3'
        d['deployment']=fixtures.bound(fixtures.record(fixtures.model.INPUTS,changed))
        (self.vm/'bootstrap.json').write_text(json.dumps(host.base.record('mojt-bootstrap-result-v1',d)))
        with self.assertRaisesRegex(ValueError,'source Base 0.2.0'):
            host.inputs(argparse.Namespace(vm=self.vm,base_build=self.build,output=self.output))
        d['deployment']=self.original
        (self.vm/'bootstrap.json').write_text(json.dumps(host.base.record('mojt-bootstrap-result-v1',d)))
        (self.release/'rootfs.tar.zst').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'archive differs'):
            host.inputs(argparse.Namespace(vm=self.vm,base_build=self.build,output=self.output))

    def test_real_successor_packaging_and_launcher_leave_source_and_disk_untouched(self):
        before=self.snapshot();run=subprocess.run
        def execute(argv,**kwargs):
            argv=list(map(str,argv))
            if argv[0]=='qemu-img':
                self.assertNotIn('-U',argv);shutil.copyfile(argv[-2],argv[-1]);return subprocess.CompletedProcess(argv,0)
            if argv[0]=='mkfs.ext4':return subprocess.CompletedProcess(argv,0)
            return run(argv,**kwargs)
        which=shutil.which
        with mock.patch.object(host.os,'geteuid',return_value=1000),\
             mock.patch.object(host.shutil,'which',side_effect=lambda name:which(name) if name not in ('qemu-img','mkfs.ext4') else '/fixture/'+name),\
             mock.patch.dict(os.environ),mock.patch.object(host.subprocess,'run',side_effect=execute):
            host.main(self.argv)
        after=self.snapshot();self.assertEqual(before,{name:after[name] for name in before})
        plan=host.read(self.output/'inputs/plan.json')
        self.assertEqual(plan['original'],self.original)
        self.assertNotEqual(plan['candidate'],self.original['description']['inputs']['description']['base']['artifact'])
        image=self.output/'releases'/('base-'+host.VERSION+'-x86_64/rootfs.tar.zst')
        with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['zstd','-dc',str(image)]))) as archive:
            self.assertEqual(archive.extractfile('./'+host.MARKER).read(),(host.VERSION+'\n').encode())
            self.assertIn(('VERSION_ID="'+host.VERSION+'"').encode(),archive.extractfile('./usr/lib/os-release').read())
        script=(self.output/'run-qemu.sh').read_text()
        self.assertIn(str(self.output/'image'),script);self.assertNotIn(str(self.vm),script)
        self.assertIn('readonly=on',script);self.assertNotIn('-kernel',script)
        self.assertFalse((self.output/'INCOMPLETE').exists())

    @unittest.skipUnless(shutil.which('qemu-img') and (shutil.which('mkfs.ext4') or Path('/usr/sbin/mkfs.ext4').is_file()),
                         'real image-copy/input-disk smoke requires qemu-utils and e2fsprogs')
    def test_real_qemu_copy_and_ext4_input_disk(self):
        before=self.snapshot()
        with mock.patch.object(host.os,'geteuid',return_value=1000),mock.patch.dict(os.environ):
            host.main(self.argv)
        after=self.snapshot();self.assertEqual(before,{name:after[name] for name in before})
        self.assertEqual((self.vm/'disk.img').read_bytes(),(self.output/'image/disk.img').read_bytes())
        result=subprocess.check_output(['/usr/sbin/debugfs','-R','cat /plan.json',str(self.output/'inputs.img')],
                                       stderr=subprocess.DEVNULL,text=True)
        self.assertEqual(json.loads(result)['original'],self.original)


class GuestTests(unittest.TestCase):
    def test_resume_retries_preparation_without_reinstalling_or_replacing_bounds(self):
        import mpm_boot_status
        original=fixtures.bound(fixtures.fixture());candidate='sha256:'+'9'*64
        state=dict(phase='started',original=original,candidate=candidate,initial_boot='older-boot')
        plan=dict(candidate=candidate,release='0.2.0-test1')
        old=mpm_boot_status.description(original)
        bounds=dict(format=fixtures.catalog.BASE_FORMAT,base=dict(artifact=candidate,release=plan['release']),
            platform=old['platform'],kernel_min=old['kernel']['upstream'],kernel_max=old['kernel']['upstream'])
        with tempfile.TemporaryDirectory() as temporary,\
             mock.patch.object(guest,'LAB',Path(temporary)),\
             mock.patch.object(guest,'status',mpm_boot_status,create=True),\
             mock.patch.object(guest,'catalog',fixtures.catalog,create=True),\
             mock.patch.object(guest,'artifact',fixtures.artifact,create=True),\
             mock.patch.object(guest,'io_native',fixtures.io,create=True),\
             mock.patch.object(guest,'transaction',fixtures.tx,create=True),\
             mock.patch.object(guest,'running',return_value=original),\
             mock.patch.object(guest,'boot_id',return_value='resumed-boot'),\
             mock.patch.object(guest,'check'),mock.patch.object(guest,'select') as select,\
             mock.patch.object(guest,'call') as call:
            path=Path(temporary)/'bounds.json';fixtures.io.write_json(path,bounds);before=path.stat()
            call.side_effect=ValueError('injected preparation failure')
            with self.assertRaisesRegex(ValueError,'preparation failure'):guest.resume(state,plan)
            self.assertEqual(state['phase'],'started');select.assert_not_called()
            call.side_effect=None;call.return_value=dict(selected=original['id'],deployment='sha256:'+'8'*64)
            guest.resume(state,plan)
            self.assertEqual(state['phase'],'selected');self.assertEqual(state['initial_boot'],'resumed-boot')
            self.assertEqual(path.stat().st_ino,before.st_ino)
            self.assertEqual(host.read(path),bounds)
            self.assertTrue(all(c.args[:2]==('base','stage') for c in call.call_args_list))
            select.assert_called_once_with('sha256:'+'8'*64,original['id'])
            call.reset_mock();guest.resume(dict(state,phase='staged'),plan)
            call.assert_not_called()  # A completed preparation needs only selection.
            with self.assertRaisesRegex(ValueError,'started/staged'):
                guest.resume(dict(state,phase='return-selected'),plan)

    def test_calls_use_the_installed_mpm_and_checkpoint_can_be_updated(self):
        with mock.patch.object(guest.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'{"changed":true}','')) as run:
            self.assertTrue(guest.call('base','status')['changed'])
            self.assertEqual(run.call_args.args[0],['/run/mojt-system/bin/mpm','base','status','--json'])
            self.assertNotIn('stderr',run.call_args.kwargs)  # Phase output stays live.
        with tempfile.TemporaryDirectory() as temporary,\
             mock.patch.object(guest,'LAB',Path(temporary)),\
             mock.patch.object(guest,'io_native',fixtures.io,create=True),\
             mock.patch.object(guest,'transaction',fixtures.tx,create=True):
            guest.checkpoint(dict(phase='selected'));guest.checkpoint(dict(phase='complete'))
            self.assertEqual(host.read(Path(temporary)/'state.json'),dict(phase='complete'))

    def test_changed_system_is_rejected_before_probes_or_return_selection(self):
        original=fixtures.bound(fixtures.fixture());d=copy.deepcopy(original['description']['inputs']['description'])
        d['system']['artifact']='sha256:'+'8'*64;changed=fixtures.bound(fixtures.record(fixtures.model.INPUTS,d))
        import mpm_boot_status
        with mock.patch.object(guest,'running',return_value=changed),\
             mock.patch.object(guest,'status',mpm_boot_status,create=True),\
             mock.patch.object(guest.subprocess,'run',side_effect=AssertionError('must not probe/select')):
            with self.assertRaisesRegex(ValueError,'input changed: system'):
                guest.check(dict(original=original),{},candidate=True)


if __name__=='__main__':unittest.main()
