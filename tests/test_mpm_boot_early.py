# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Three focused reader/runtime cases; the chroot case is not a Kernel boot."""
import copy
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import mojt_artifact as artifact
import mpm_boot_constructor as constructor
import mpm_boot_early as early
import mpm_boot_inventory as inventory
import mpm_boot_handover as transfer
import mpm_boot_v2 as model
import mpm_boot_v2_store as store
import mpm_boot_selection as selection
from mpm_request_plan import record
import test_mpm_boot_v2 as fixtures


class ReaderTests(unittest.TestCase):
    def test_inventory_is_bounded_covers_links_modes_and_never_follows_a_fifo(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'file').write_bytes(b'unchanged');os.link(root/'file',root/'hardlink')
            (root/'link').symlink_to('/unrelated/host/path')
            before=inventory.snapshot(root)
            self.assertEqual(before['hardlink']['hardlink_to'],'file');self.assertEqual(before['link']['target'],'/unrelated/host/path')
            with self.assertRaisesRegex(ValueError,'limit|unbounded'):inventory.snapshot(root,maximum=1)
            (root/'file').chmod(0o600);self.assertNotEqual(inventory.snapshot(root),before)
            os.mkfifo(root/'fifo')
            with self.assertRaisesRegex(ValueError,'unsupported'):inventory.snapshot(root)
            with self.assertRaisesRegex(ValueError,'linked'):inventory.path(root,'link')
            compressed=root/'large.ko.gz';compressed.write_bytes(gzip.compress(b'x'*4096))
            with mock.patch.object(model,'MAX_BOOT',1024),self.assertRaisesRegex(ValueError,'modules exceed limit'):
                constructor.decode_modules([compressed],root/'decoded')

    def test_early_selector_is_exact_and_provider_export_cannot_adopt_an_offline_store(self):
        value=fixtures.bound(fixtures.fixture());valid=model.cmdline(value)
        early.command_line(valid,value)
        for bad in (valid+' mojt.deployment='+value['id'][7:], valid+' root=UUID=other',valid+' init=/evil',
                    valid.replace('console=ttyS0,115200','console=tty0'), 'BOOT_IMAGE=/elsewhere '+valid):
            with self.subTest(command=bad),self.assertRaises(ValueError):early.command_line(bad,value)
        from mpm_nix_boot import NixBootAdapter
        path='/nix/store/'+'a'*32+'-python'
        ref=dict(provider='nix',identity=dict(format='mojt-nix-output-v1',output=path,closure=[dict(path=path,nar_hash='sha256:'+'a'*52)],commands=[]))
        adapter=NixBootAdapter('/pinned/nix-store',lambda args:self.fail('no Nix execution during path projection'))
        with self.assertRaisesRegex(ValueError,'accepted live'):adapter.boot_paths(ref,Path('/nonexistent-offline-disk'))
        with self.assertRaisesRegex(ValueError,'export contract'):
            constructor.provider_paths(Path('/'),dict(provider='fixture',identity={'id':1}),{'fixture':object()})


class PythonAdapter:
    """Explicit trusted host runtime fixture, not a production provider backend."""
    def __init__(self,ref,roots):self.ref=ref;self.roots=roots
    def verify(self,ref,root):
        if ref!=self.ref:raise ValueError('wrong trusted runtime')
        for p,expected in self.roots.items():
            if inventory.snapshot(root/p)!=expected:raise ValueError('trusted runtime changed')
    def boot_paths(self,ref,root):return sorted(self.roots)


@unittest.skipUnless(os.geteuid()==0 and all(shutil.which(c) for c in ('zstd','cpio','tar','chroot','ldd','busybox')),
                     'requires root and real archive/runtime tools')
class ConstructorTests(unittest.TestCase):
    def test_actual_archive_runs_its_reader_in_chroot_and_refuses_tampered_content(self):
        f=fixtures.Retention();f.setUp();self.addCleanup(f.doCleanups)
        root=f.root;work=f.f.f.fixture.work
        provider=f.f.adapter
        provider.boot_paths=lambda ref,target:sorted(r['path'].lstrip('/') for r in ref['identity']['objects'])
        provider.boot_mounts=lambda ref,target:[dict(source='nix',target='nix')]
        # Freeze a small distro Python closure only as independent CI evidence.
        host=Path('/usr/bin/python3').resolve()
        stdlib=Path(subprocess.check_output([str(host),'-I','-S','-c','import sysconfig;print(sysconfig.get_path("stdlib"))'],text=True).strip())
        runtime_source=work/'runtime-source';runtime_source.mkdir(mode=0o700)
        names=['usr/bin/python3',str(stdlib).lstrip('/')]
        (runtime_source/'usr/bin').mkdir(parents=True);shutil.copy2(host,runtime_source/'usr/bin/python3')
        # Normalize distro stdlib links while copying this trusted fixture; the
        # production Nix bundle preserves and confines its actual closure links.
        shutil.copytree(stdlib,runtime_source/names[1],symlinks=False,ignore=shutil.ignore_patterns('__pycache__','site-packages','dist-packages'))
        libraries=set()
        for executable in [host,*sorted(stdlib.rglob('*.so'))]:
            result=subprocess.run(['ldd',str(executable)],text=True,capture_output=True,check=False)
            for line in result.stdout.splitlines():
                match=re.search(r'=> (/[^\s()]+)|^\s*(/[^\s()]+)',line)
                if match:libraries.add(match.group(1) or match.group(2))
        for name in sorted(libraries):
            relative=name.lstrip('/');destination=runtime_source/relative
            if any(relative==p or relative.startswith(p+'/') for p in names):continue
            destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(Path(name).resolve(),destination);names.append(relative)
        ref=dict(provider='trusted-python-fixture',identity={'revision':1})
        runtime_adapter=PythonAdapter(ref,{p:inventory.snapshot(runtime_source/p) for p in sorted(names)})
        bundle=work/'bootstrap-python';runtime=constructor.freeze_runtime(runtime_source,ref,'/usr/bin/python3',bundle,adapters={ref['provider']:runtime_adapter})
        busybox=Path(shutil.which('busybox'));source=copy.deepcopy(f.source['description'])
        plan=f.f.plan();source['boot']['root_uuid']=plan['description']['root_uuid']
        source['constructor']=constructor.constructor(runtime,busybox,handover=True);source=record(model.INPUTS,source)
        contract=transfer.prepare(root,source,plan,adapters=f.f.adapters)
        before=f.f.f.snapshot();vm=constructor.archive.vm_module()
        module=root/'kernel/installed'/source['description']['kernel']['artifact'][7:]/'payload/lib/modules'/source['description']['kernel']['release']/'kernel/example.ko'
        build=work/'v2-construction'
        with mock.patch.object(constructor.archive,'vm_module',return_value=vm),mock.patch.object(vm,'module_paths',return_value=[module]):
            result=constructor.build(root,source,bundle,busybox,build,bounds=f.bounds,adapters=f.f.adapters,handover=contract)
        self.assertEqual(before,f.f.f.snapshot());self.assertFalse(result['boot_ready'] or result['selection_changed'])
        self.assertTrue(result['handover_enabled']);self.assertIn('--handover /mojt/handover.json',(build/'initroot/init').read_text())
        self.assertIn('env -i',(build/'initroot/init').read_text());self.assertIn('old root and backing filesystem fully unmounted',(build/'initroot/shutdown').read_text())
        image=work/'actual-initramfs';image.write_bytes(result['archive'])
        value=model.compose(source,result['binding'],f.image.stat().st_size)
        store.retain(root,value,f.image,image,bounds=f.bounds,adapters=f.f.adapters)
        receipt=selection._admit(root,value,result,adapters=f.f.adapters)
        self.assertEqual(selection.ready(root,value['id'])['receipt'],receipt)
        # A second native generation keeps startup/Base/Kernel unchanged. Its
        # exact artifact/profile IDs differ, even with the same human label.
        other=f.f.candidate();realized=constructor.system.realization(root,other)
        next_source=copy.deepcopy(source['description'])
        next_source['system']=dict(artifact=other,composition=realized['description']['composition'],
            manifest=realized['description']['manifest'],generation='native-fixture')
        next_source=record(model.INPUTS,next_source)
        next_contract=transfer.prepare(root,next_source,f.f.plan(other),adapters=f.f.adapters)
        with mock.patch.object(constructor.archive,'vm_module',return_value=vm),mock.patch.object(vm,'module_paths',return_value=[module]):
            staged=selection.stage(root,next_source,bundle,busybox,work/'second-construction',
                bounds=f.bounds,adapters=f.f.adapters,contract=next_contract)
        other_id=staged['deployment'];old_menu=(root/'boot/mojt/grub.cfg').read_bytes()
        self.assertNotEqual(other_id,value['id']);self.assertEqual((root/'boot/mojt/grub.cfg').read_bytes(),old_menu)
        hook=root/'boot/mojt/grub.cfg';hook.chmod(0o644);hook.write_bytes(selection.HOOK);hook.chmod(0o444)
        choice=selection.initialize(root,value['id']);self.assertEqual(choice['description']['selected'],value['id'])
        before_preview=f.f.f.snapshot()
        preview=selection.select(root,other_id,expected_selected=value['id'],dry_run=True)
        self.assertFalse(preview['changed']);self.assertEqual(before_preview,f.f.f.snapshot())
        publish=selection.tx.publish
        with mock.patch.object(selection.tx,'publish',side_effect=OSError('before menu rename')):
            with self.assertRaisesRegex(OSError,'before menu rename'):selection.select(root,other_id,expected_selected=value['id'],yes=True)
        self.assertEqual(before_preview,f.f.f.snapshot())
        def uncertain(src,dst):
            def fail(path):raise OSError('injected menu flush failure')
            publish(src,dst,sync=fail)
        with mock.patch.object(selection.tx,'publish',side_effect=uncertain):
            with self.assertRaises(selection.tx.PublicationUncertain):selection.select(root,other_id,expected_selected=value['id'],yes=True)
        self.assertEqual(selection.current(root)[0]['description']['selected'],other_id)
        from mpm_boot_status import description
        from mpm_base_status import status as base_status
        from mpm_system import status as system_status
        running=dict(format='mojt-running-native-v2',deployment=value,inputs=source['id'],installation=source['description']['installation'])
        actual_uname=os.uname();reported=os.uname_result((actual_uname.sysname,actual_uname.nodename,source['description']['kernel']['release'],actual_uname.version,actual_uname.machine))
        def forbidden(*args,**kwargs):raise AssertionError('metadata status must not scan payloads or run helpers')
        with mock.patch.object(selection.os,'uname',return_value=reported),mock.patch.object(constructor.inventory,'snapshot',side_effect=forbidden),mock.patch.object(constructor.store,'audit_inputs',side_effect=forbidden):
            self.assertEqual(base_status(root,running_record=running)['running']['deployment'],value['id'])
            observed=system_status(root,running_record=running)
            kernel_view=selection.status(root,running_record=running)
            self.assertEqual(kernel_view['running']['deployment'],value['id']);self.assertEqual(kernel_view['selected'],other_id)
            self.assertFalse(kernel_view['running_is_selected']);self.assertEqual(kernel_view['integrity'],'metadata-only')
        self.assertEqual(observed['running']['artifact'],source['description']['system']['artifact'])
        self.assertEqual(observed['selected']['artifact'],other)
        unchanged=f.f.f.snapshot();self.assertFalse(selection.select(root,other_id,expected_selected=other_id,yes=True)['changed'])
        self.assertEqual(unchanged,f.f.f.snapshot())
        with self.assertRaisesRegex(ValueError,'selected deployment changed'):selection.select(root,value['id'],expected_selected=value['id'],yes=True)
        selection.select(root,expected_selected=other_id,rollback=True,yes=True)
        self.assertEqual(selection.current(root)[0]['description']['selected'],value['id'])
        self.assertEqual(set(selection.current(root)[1]),{value['id'],other_id})
        with self.assertRaisesRegex(ValueError,'v1 writer'):constructor.archive.current(root,f.f.f.baseline)
        extracted=work/'independent-extraction';extracted.mkdir()
        subprocess.run(['cpio','-idm','--quiet','--no-absolute-filenames'],cwd=extracted,input=gzip.decompress(result['archive']),check=True)
        shutil.copytree(root,extracted/'test-target',symlinks=True)
        command=extracted/'mojt/test-cmdline';command.write_text(model.cmdline(value))
        (extracted/'mojt/test-release').write_text(source['description']['kernel']['release'])
        args=['chroot',str(extracted),'/usr/bin/python3','-I','-S','-B','/mojt/launch.py','--root','/test-target',
              '--inputs','/mojt/inputs.json','--proof','/mojt/trees.json','--cmdline','/mojt/test-cmdline','--release','/mojt/test-release']
        checked=subprocess.run(args,capture_output=True,text=True,env={'PATH':'/usr/sbin:/usr/bin:/bin','LC_ALL':'C'})
        self.assertEqual(checked.returncode,0,checked.stderr)
        report=json.loads(checked.stdout);self.assertTrue(report['verified']);self.assertFalse(report['handover'] or report['boot_ready'])
        self.assertEqual(report['deployment'],value['id'])
        gates="import sys;sys.path.insert(0,'/mojt/code');from pathlib import Path;import mpm_boot_early as e;import mpm_boot_handover as h;h.check(Path('/test-target'),e.read(Path('/mojt/inputs.json')),e.read(Path('/mojt/trees.json')),e.read(Path('/mojt/handover.json')));print('PASS: isolated System handover gates')"
        gate_args=['chroot',str(extracted),'/usr/bin/python3','-I','-S','-B','-c',gates]
        passed=subprocess.run(gate_args,capture_output=True,text=True);self.assertEqual(passed.returncode,0,passed.stderr)
        layout=extracted/'test-target/state/layout-version';layout.write_text('2\n')
        denied=subprocess.run(gate_args,capture_output=True,text=True);self.assertNotEqual(denied.returncode,0);self.assertIn('state layout',denied.stderr)
        layout.write_text('1\n')
        command.write_text(model.cmdline(value)+' root=UUID=other')
        denied=subprocess.run(args,capture_output=True,text=True);self.assertNotEqual(denied.returncode,0)
        self.assertIn('command line differs',denied.stderr);command.write_text(model.cmdline(value))
        proof=result['proof']['description']['base'];name=next(n for n,r in proof['inventory'].items() if r['type']=='file')
        changed=extracted/'test-target'/proof['path']/name;changed.chmod(0o600);changed.write_bytes(b'tampered Base')
        denied=subprocess.run(args,capture_output=True,text=True);self.assertNotEqual(denied.returncode,0)
        self.assertIn('early base tree differs',denied.stderr)


if __name__=='__main__':unittest.main()
