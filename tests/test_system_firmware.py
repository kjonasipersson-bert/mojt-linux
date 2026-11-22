# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Narrow firmware/guest-service transitions, real native packaging, no network."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

from test_mpm_system import Fixture, REPO, pack, spec, tree
import mojt_artifact as artifact
import mojt_system as paths
import mojt_system_manifest as manifests
import mpm_base as base
import mpm_system as system
import mpm_system_model as model
import mpm_system_transition as transition

loader=importlib.util.spec_from_file_location('firmware_delivery',REPO/'tools/mojt-system-firmware-test.py')
delivery=importlib.util.module_from_spec(loader);loader.loader.exec_module(delivery)


def hardware():
    return dict(format=2,profile='thinkpad-x1-carbon-3',kernel_release='6.12-test',modules_location='native-kernel',
        early_modules=['virtio_pci','virtio_blk','ext4'],runtime_modules=['i915','e1000e'],
        firmware_tree_sha256='a'*64,licenses_tree_sha256='b'*64,modules_tree_sha256='c'*64)


def raw(value):return json.dumps(value,indent=2)+'\n'


def file_row(value,mode=0o444):return dict(sha256=hashlib.sha256(value.encode()).hexdigest(),mode=mode)


def example(with_agent=False):
    hw=hardware()
    before={'hardware.json':file_row(raw(hw)), 'version':file_row('old\n'),
        'kernel/lib/firmware':dict(directory=True,mode=0o555),
        'kernel/lib/firmware/old.bin':file_row('old firmware'),
        'kernel/lib/firmware/regulatory.db':file_row('database'),
        'kernel/lib/firmware/regulatory.db.p7s':file_row('signature'),
        'kernel/licenses':dict(directory=True,mode=0o555),
        'setup':file_row('startup',0o555)}
    description=dict(label='old',architecture='x86_64',requirements=dict(base_abi={'libc':'glibc'},state_layout=1),
        support=dict(ports=dict(read=[],write=[],capabilities=[])),provides=[],artifacts={'fixture':True},provenance={'fixture':True},profile=before)
    selected=manifests.create(description);candidate=copy.deepcopy(description)
    candidate['label']='new';candidate['profile']['version']=file_row('new\n')
    after=dict(hw,firmware_tree_sha256='d'*64,licenses_tree_sha256='e'*64)
    candidate['profile'].update({'hardware.json':file_row(raw(after)),
        'kernel/lib/firmware/added.bin':file_row('new firmware'),
        'kernel/licenses/linux-firmware/WHENCE':file_row('upstream attributions'),
        'kernel/licenses/linux-firmware/LICENCE.test':file_row('upstream license')})
    if with_agent:
        candidate['profile'].update({'bin/qemu-ga':dict(link='/nix/store/agent/bin/qemu-ga'),
            'units/qemu-guest-agent.service':file_row(transition.QEMU_AGENT_UNIT),
            'units/mojt.target.wants/qemu-guest-agent.service':dict(link='../qemu-guest-agent.service')})
    proof=dict(format=transition.FIRMWARE_FORMAT,baseline=selected['id'],hardware_before=raw(hw),hardware_after=raw(after),
        inventory_before=artifact.digest(transition.firmware_inventory(before)),
        inventory_after=artifact.digest(transition.firmware_inventory(candidate['profile'])),source={'firmware':'exact-test-input'})
    candidate['profile'][transition.FIRMWARE_PROOF]=file_row(artifact.canonical(proof).decode()+'\n')
    return selected,manifests.create(candidate),proof


class PolicyTests(unittest.TestCase):
    def test_firmware_requires_a_bound_contract_and_optional_guest_service_is_exact(self):
        for agent in (False,True):
            before,after,proof=example(agent)
            self.assertFalse(transition.tooling_review(before,after)['description']['compatible'])
            report=transition.tooling_review(before,after,firmware=proof)['description']
            self.assertTrue(report['compatible'],report)
            self.assertEqual(report['policy'],'firmware-data-and-guest-agent-v1' if agent else 'firmware-data-only-v1')

    def test_other_services_and_kernel_modules_are_still_blocked(self):
        before,after,proof=example(True)
        for path in ('setup','units/NetworkManager.service','kernel/lib/modules/test/module.ko'):
            changed=copy.deepcopy(after['description']);changed['profile'][path]=file_row('unrelated change',0o555)
            report=transition.tooling_review(before,manifests.create(changed),firmware=proof)['description']
            self.assertFalse(report['compatible']);self.assertIn(path,report['blockers'])

    def test_hardware_policy_and_forged_inventory_or_baseline_are_refused(self):
        before,after,proof=example()
        for key in ('baseline','inventory_before','inventory_after'):
            changed=copy.deepcopy(proof);changed[key]='sha256:'+'0'*64
            with self.assertRaises(ValueError):transition.tooling_review(before,after,firmware=changed)
        for key,value in (('runtime_modules',[]),('early_modules',['nvme']),('profile','pc-x86_64'),('kernel_release','other')):
            changed=copy.deepcopy(proof);hw=json.loads(changed['hardware_after']);hw[key]=value;changed['hardware_after']=raw(hw)
            candidate=copy.deepcopy(after['description']);candidate['profile']['hardware.json']=file_row(raw(hw))
            with self.assertRaisesRegex(ValueError,'startup policy'):
                transition.tooling_review(before,manifests.create(candidate),firmware=changed)

    def test_firmware_executable_escape_and_missing_licenses_are_refused(self):
        before,after,proof=example()
        cases=(('kernel/lib/firmware/added.bin',file_row('new',0o555)),
               ('kernel/lib/firmware/escape',dict(link='/etc/shadow')),
               ('kernel/licenses/linux-image-test/copyright',file_row('unrelated license')),
               ('kernel/licenses/linux-firmware/WHENCE',None))
        for path,row in cases:
            candidate=copy.deepcopy(after['description']);changed=copy.deepcopy(proof)
            if row is None:candidate['profile'].pop(path)
            else:candidate['profile'][path]=row
            changed['inventory_after']=artifact.digest(transition.firmware_inventory(candidate['profile']))
            with self.assertRaises(ValueError):transition.tooling_review(before,manifests.create(candidate),firmware=changed)

    def test_altered_guest_service_and_existing_service_replacement_are_refused(self):
        before,after,proof=example(True)
        changed=copy.deepcopy(after['description']);changed['profile']['units/qemu-guest-agent.service']=file_row('ExecStart=/bin/not-agent\n')
        with self.assertRaisesRegex(ValueError,'guest service'):
            transition.tooling_review(before,manifests.create(changed),firmware=proof)


class DriverTests(unittest.TestCase):
    def test_license_directory_and_legacy_files_preserve_relative_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            paths.write(root/'WHENCE','See LICENSES/GPL-2.0 and LICENCE.vendor')
            paths.write(root/'LICENSES/GPL-2.0','upstream GPL text')
            paths.write(root/'LICENSES/vendor/terms','vendor terms')
            paths.write(root/'LICENCE.vendor','legacy vendor terms')
            paths.write(root/'not-a-license.bin','do not copy')
            self.assertEqual(delivery.license_texts(root),{
                'WHENCE':b'See LICENSES/GPL-2.0 and LICENCE.vendor',
                'LICENSES/GPL-2.0':b'upstream GPL text','LICENSES/vendor/terms':b'vendor terms',
                'LICENCE.vendor':b'legacy vendor terms'})

    def test_license_escape_special_file_and_linked_directory_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'source';paths.write(root/'WHENCE','test');(root/'LICENSES').mkdir()
            outside=Path(folder)/'outside';outside.write_text('unrelated')
            point=root/'LICENSES/vendor'
            point.symlink_to(outside)
            with self.assertRaisesRegex(ValueError,'unsafe upstream license'):delivery.license_texts(root)
            point.unlink();os.mkfifo(point)
            with self.assertRaisesRegex(ValueError,'unsafe upstream license'):delivery.license_texts(root)
            point.unlink();point.symlink_to(root/'LICENSES',target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'linked upstream license directory'):delivery.license_texts(root)

    def test_overlay_replaces_a_filename_without_writing_through_its_old_alias(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';destination=root/'destination';source.mkdir();destination.mkdir()
            (source/'alias').write_text('new firmware');(destination/'retained').write_text('old firmware')
            (destination/'alias').symlink_to('retained')
            delivery.overlay(source,destination)
            self.assertFalse((destination/'alias').is_symlink())
            self.assertEqual((destination/'alias').read_text(),'new firmware')
            self.assertEqual((destination/'retained').read_text(),'old firmware')

    def test_source_fetch_refuses_to_build_compiler_or_other_dependencies(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'ports.toml').write_text('[nixpkgs]\n')
            drv='/nix/store/'+'a'*32+'-source.drv'
            backend=types.ModuleType('test_firmware_provider')
            backend.source_from_fields=lambda *args:{'revision':'a'*40}
            backend.evaluate=lambda *args,**kwargs:dict(firmware=dict(version='test',output=str(root/'firmware'),
                source=str(root/'absent-source'),source_drv=drv,fixed='fixed-hash'),agent=None)
            backend.store_path=Path;backend.STORE_NAME=r'[0-9a-z]{32}-[A-Za-z0-9._-]+'
            plan=subprocess.CompletedProcess([],0,stdout='',stderr='these derivations will be built:\n  '+drv+'\n  /nix/store/'+'b'*32+'-compiler.drv\n')
            with mock.patch.object(delivery,'RUNTIME',root),mock.patch.object(delivery,'WORK',root),\
                 mock.patch.object(delivery.importlib.util,'module_from_spec',return_value=backend),\
                 mock.patch.object(delivery.importlib.machinery.SourceFileLoader,'exec_module'),\
                 mock.patch.object(delivery,'import_binary') as imported,\
                 mock.patch.object(delivery.subprocess,'run',return_value=plan) as run:
                with self.assertRaisesRegex(ValueError,'build dependencies'):delivery.acquire(REPO,False)
                self.assertEqual(imported.call_count,1)
                self.assertEqual(run.call_count,1);self.assertIn('--dry-run',run.call_args.args[0])

    def test_acquired_agent_reference_passes_the_real_nix_adapter_schema(self):
        from mpm_nix_binary import NixBinaryAdapter
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'ports.toml').write_text('[nixpkgs]\n')
            licenses=root/'licenses';paths.write(licenses/'WHENCE','upstream')
            output='/nix/store/'+'a'*32+'-qemu-ga'
            backend=types.ModuleType('test_firmware_provider')
            backend.source_from_fields=lambda *args:{'revision':'a'*40}
            backend.evaluate=lambda *args,**kwargs:dict(firmware=dict(version='test',output=str(root/'firmware'),
                source=str(licenses),source_drv='/nix/store/'+'b'*32+'-source.drv',fixed='hash'),
                agent=dict(version='test',output=output))
            backend.store_path=Path;backend.STORE_NAME=r'[0-9a-z]{32}-[A-Za-z0-9._-]+'
            backend.discover_commands=mock.Mock(return_value=['qemu-ga'])
            def query(adapter,args):
                if '--requisites' in args:return output
                if '--hash' in args:return 'sha256:abc123'
                self.fail('unexpected Nix query: '+str(args))
            with mock.patch.object(delivery,'RUNTIME',root),mock.patch.object(delivery,'WORK',root),\
                 mock.patch.object(delivery.importlib.util,'module_from_spec',return_value=backend),\
                 mock.patch.object(delivery.importlib.machinery.SourceFileLoader,'exec_module'),\
                 mock.patch.object(delivery,'import_binary') as imported,\
                 mock.patch.object(NixBinaryAdapter,'_run',query):
                unused,unused,agent,unused=delivery.acquire(REPO,True)
            adapter=NixBinaryAdapter('/nonexistent/nix-store')
            self.assertEqual(adapter.describe(agent,root)['commands'],{'qemu-ga':output+'/bin/qemu-ga'})
            backend.discover_commands.assert_called_once_with(dict(output=output,attribute='qemu_kvm.ga'))
            self.assertEqual(imported.call_count,3)
            broken=copy.deepcopy(agent);broken['identity'].pop('commands')
            with self.assertRaisesRegex(ValueError,'invalid fields'):adapter.identity(broken)


@unittest.skipUnless(os.geteuid()==0,'requires root-mapped private execution')
class PreparationTests(unittest.TestCase):
    def test_main_prepare_freezes_resources_and_retry_keeps_the_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)/'work';before=dict(running='sha256:'+'a'*64,selected='sha256:'+'b'*64)
            with mock.patch.object(delivery,'WORK',work),mock.patch.object(delivery.os.path,'ismount',return_value=True),\
                 mock.patch.dict(os.environ,dict(os.environ)),mock.patch.object(sys,'path',list(sys.path)),\
                 mock.patch.object(delivery,'snapshot',return_value=before),\
                 mock.patch.object(delivery,'mpm',return_value={'running':{'deployment':before['selected']}}),\
                 mock.patch.object(delivery.os,'execv',side_effect=RuntimeError('isolated handoff')) as execute:
                with self.assertRaisesRegex(RuntimeError,'isolated handoff'):delivery.main(['prepare'])
                value=delivery.state();self.assertEqual(value['phase'],'preparing')
                frozen=Path(value['code']);self.assertEqual((frozen/'tools/mpm_system_transition.py').read_bytes(),(REPO/'tools/mpm_system_transition.py').read_bytes())
                saved=(work/'state.json').read_bytes()
                with self.assertRaisesRegex(RuntimeError,'isolated handoff'):delivery.main(['prepare'])
                self.assertEqual((work/'state.json').read_bytes(),saved)
                self.assertEqual(execute.call_count,2)
                self.assertEqual(execute.call_args.args[1][-1],'_prepare')

    def test_refresh_replaces_only_unfinished_code_and_retains_downloads_and_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)/'work';before=dict(running='sha256:'+'a'*64,selected='sha256:'+'b'*64)
            with mock.patch.object(delivery,'WORK',work),mock.patch.object(delivery.os.path,'ismount',return_value=True),\
                 mock.patch.dict(os.environ,dict(os.environ)),mock.patch.object(sys,'path',list(sys.path)),\
                 mock.patch.object(delivery,'snapshot',return_value=before),\
                 mock.patch.object(delivery,'mpm',return_value={'running':{'deployment':before['selected']}}),\
                 mock.patch.object(delivery.os,'execv',side_effect=RuntimeError('isolated handoff')):
                with self.assertRaisesRegex(RuntimeError,'isolated handoff'):delivery.main(['prepare'])
                previous=delivery.state();old=Path(previous['code']);old_bytes=(old/'mbt-execution.json').read_bytes()
                (work/'firmware-root').symlink_to('/nix/store/retained-firmware')
                previous['script']='0'*64;delivery.save(previous)
                with self.assertRaisesRegex(ValueError,'script/checkpoint'):delivery.main(['prepare'])
                with mock.patch.object(delivery,'snapshot',return_value=dict(before,selected='changed')):
                    with self.assertRaisesRegex(ValueError,'next boot'):delivery.main(['prepare','--refresh-code'])
                with self.assertRaisesRegex(RuntimeError,'isolated handoff'):delivery.main(['prepare','--refresh-code'])
                refreshed=delivery.state();self.assertNotEqual(refreshed['code'],str(old))
                self.assertEqual(refreshed['baseline'],before)
                self.assertEqual((old/'mbt-execution.json').read_bytes(),old_bytes)
                self.assertEqual(os.readlink(work/'firmware-root'),'/nix/store/retained-firmware')
                refreshed['phase']='installed';delivery.save(refreshed)
                with self.assertRaisesRegex(ValueError,'already complete'):delivery.main(['prepare','--refresh-code'])
                refreshed['phase']='preparing';delivery.save(refreshed);(work/'package').mkdir()
                with self.assertRaisesRegex(ValueError,'package already exists'):delivery.main(['prepare','--refresh-code'])

    def test_refresh_repackages_prepared_content_without_overwriting_the_previous_kit(self):
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)/'work';before=dict(running='sha256:'+'a'*64,selected='sha256:'+'b'*64)
            with mock.patch.object(delivery,'WORK',work),mock.patch.object(delivery.os.path,'ismount',return_value=True),\
                 mock.patch.dict(os.environ,dict(os.environ)),mock.patch.object(sys,'path',list(sys.path)),\
                 mock.patch.object(delivery,'snapshot',return_value=before),\
                 mock.patch.object(delivery,'mpm',return_value={'running':{'deployment':before['selected']}}),\
                 mock.patch.object(delivery.os,'execv',side_effect=RuntimeError('isolated handoff')):
                with self.assertRaisesRegex(RuntimeError,'isolated handoff'):delivery.main(['prepare'])
                previous=delivery.state();previous.update(phase='prepared',candidate={'artifact':'sha256:'+'c'*64},script='0'*64)
                paths.write(work/'package/component/original.tar.zst','retained old archive')
                delivery.save(previous)
                with self.assertRaisesRegex(RuntimeError,'isolated handoff'):delivery.main(['prepare','--refresh-code'])
                current=delivery.state();replacement=delivery.package_directory(current)
                self.assertEqual(current['phase'],'preparing');self.assertNotIn('candidate',current)
                self.assertNotEqual(replacement,work/'package');self.assertFalse(replacement.exists())
                self.assertEqual((work/'package/component/original.tar.zst').read_text(),'retained old archive')
                self.assertEqual(json.loads((replacement.parent/'previous-state.json').read_text()),previous)
                with self.assertRaisesRegex(RuntimeError,'isolated handoff'):delivery.main(['prepare'])
                self.assertEqual(delivery.state(),current)

    def test_install_uses_the_repackaged_kit_and_disk_temporary_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)/'work';before=dict(running='sha256:'+'a'*64,selected='sha256:'+'b'*64)
            with mock.patch.object(delivery,'WORK',work),mock.patch.object(delivery.os.path,'ismount',return_value=True),\
                 mock.patch.dict(os.environ,dict(os.environ)),mock.patch.object(sys,'path',list(sys.path)),\
                 mock.patch.object(delivery,'snapshot',return_value=before),\
                 mock.patch.object(delivery,'mpm',return_value={'running':{'deployment':before['selected']}}) as mpm,\
                 mock.patch.object(delivery.os,'execv',side_effect=RuntimeError('isolated handoff')):
                with self.assertRaisesRegex(RuntimeError,'isolated handoff'):delivery.main(['prepare'])
                current=delivery.state();directory=work/'repackage-test/package'
                paths.write(directory/'component/new.tar.zst','new kit')
                candidate=dict(artifact='sha256:'+'c'*64,generation='generation/new.tar.zst',component='component/new.tar.zst')
                current.update(phase='prepared',candidate=candidate,package=str(directory));delivery.save(current)
                os.environ.pop('TMPDIR',None)
                result=subprocess.CompletedProcess([],0,stdout=json.dumps({'deployment':'sha256:'+'d'*64}))
                with mock.patch.object(delivery.subprocess,'run',return_value=result):
                    self.assertEqual(delivery.main(['install']),0)
                self.assertEqual(os.environ['TMPDIR'],str(work/'tmp'))
                mpm.assert_called_with('system','install','--from-file',directory/candidate['generation'],
                    '--expected-id',candidate['artifact'],'--dependency-file',directory/candidate['component'],
                    '--content-only','-y','--json')
                self.assertEqual(delivery.state()['phase'],'installed')
                self.assertEqual(delivery.state()['baseline'],before)
                with self.assertRaisesRegex(ValueError,'already complete'):delivery.main(['prepare','--refresh-code'])


class Provider:
    def describe(self,reference,root):return dict(reference=reference,commands={})
    def ensure(self,reference,root):pass
    def verify(self,reference,root):pass
    def contains(self,reference,path):return path.startswith(reference['identity']['output']+'/')
    def verify_path(self,reference,path,**kwargs):return Path(path)


@unittest.skipUnless(os.geteuid()==0 and shutil.which('zstd'),'requires root-mapped native archives')
class PackageTests(Fixture):
    def setUp(self):
        super().setUp();content=self.work/'component-source'
        paths.write(content/'version','system-native-test\n')
        paths.write(content/'hardware.json',raw(hardware()))
        for name in ('old.bin','regulatory.db','regulatory.db.p7s'):paths.write(content/'kernel/lib/firmware'/name,'old '+name)
        for name in ('firmware-iwlwifi','firmware-intel-graphics','wireless-regdb'):
            paths.write(content/'kernel/licenses'/name/'copyright','original upstream license')
        (content/'units/mojt.target.wants').mkdir(parents=True)
        part=pack(content,spec('component'),self.work/'hardware-original');self.reference=dict(provider='native',artifact=part['artifact']['id'])
        self.component_archive=self.work/'hardware-original'/part['archive']['file']
        description=copy.deepcopy(self.composition['description']);description['components'][0]['reference']=self.reference
        for row in description['profile']:row['source']['reference']=self.reference
        for name in ('hardware.json','kernel','units','version'):
            description['profile'].append(dict(path=name,source=dict(reference=self.reference,path=name)))
        description['profile'].sort(key=lambda r:r['path']);self.composition=base.record(model.FORMAT,description)
        self.archive,self.body=self.package(self.composition,self.actions);self.install()
        self.firmware=self.work/'firmware';self.licenses=self.work/'licenses'
        paths.write(self.firmware/'old.bin','replacement firmware');paths.write(self.firmware/'new.bin','additional firmware')
        paths.write(self.licenses/'WHENCE','original firmware attributions');paths.write(self.licenses/'LICENSES/GPL-2.0','redistribution terms')

    def test_generation_packages_and_installs_without_mutating_old_release_or_running_programs(self):
        before=tree(self.root)
        result=delivery.package(self.root,self.body['id'],REPO,self.firmware,self.licenses,None,{'source':'exact-test'},self.work/'firmware-package')
        self.assertEqual(tree(self.root),before);self.assertFalse(self.marker.exists())
        system.install(self.root,self.work/'firmware-package'/result['generation'],result['artifact'],
            dependency_files=[self.work/'firmware-package'/result['component']],yes=True)
        old=system.realization_path(self.root,self.body['id'])/'profile';new=system.realization_path(self.root,result['artifact'])/'profile'
        self.assertEqual((old/'kernel/lib/firmware/old.bin').read_text(),'old old.bin')
        self.assertEqual((new/'kernel/lib/firmware/old.bin').read_text(),'replacement firmware')
        self.assertEqual((new/'kernel/lib/firmware/regulatory.db').read_text(),'old regulatory.db')
        self.assertEqual((new/'kernel/licenses/linux-firmware/LICENSES/GPL-2.0').read_text(),'redistribution terms')
        report=transition.profile_review(base.read(old/'manifest.json'),base.read(new/'manifest.json'),new)
        self.assertTrue(report['description']['compatible'],report)
        self.assertFalse((new/'private.conf').exists());self.assertFalse((self.root/'boot').exists())

    def test_guest_agent_is_a_retained_binary_with_conditional_standard_unit(self):
        output=self.work/'agent-output';paths.write(output/'bin/qemu-ga','#!/bin/sh\nexit 0\n',0o755)
        ref=dict(provider='fixture',identity={'output':str(output)})
        result=delivery.package(self.root,self.body['id'],REPO,self.firmware,self.licenses,ref,{'source':'exact-test'},self.work/'agent-package')
        system.install(self.root,self.work/'agent-package'/result['generation'],result['artifact'],
            dependency_files=[self.work/'agent-package'/result['component']],yes=True,adapters={'fixture':Provider()})
        new=system.realization_path(self.root,result['artifact'])/'profile'
        self.assertEqual((new/'units/qemu-guest-agent.service').read_text(),transition.QEMU_AGENT_UNIT)
        self.assertIn('ExecCondition=',transition.QEMU_AGENT_UNIT)
        self.assertEqual(os.readlink(new/'bin/qemu-ga'),str(output/'bin/qemu-ga'))


@unittest.skipUnless(os.geteuid()==0 and all(shutil.which(n) for n in ('zstd','cpio','tar')),'requires root/native construction tools')
class HandoverTests(unittest.TestCase):
    def test_firmware_preparation_and_handover_recheck_preserve_the_selected_deployment(self):
        import test_mbt_bootstrap as bootstrap_fixture
        import mpm_boot_handover as handover
        import mpm_boot_constructor as constructor
        import mpm_boot_selection as selection
        import mpm_boot_v2 as boot
        lookup=shutil.which
        suite=bootstrap_fixture.ConstructionTests();self.addCleanup(suite.doCleanups)
        def inspect(root,description,adapter):
            before=selection.current(root)[0]
            inputs=copy.deepcopy(description['deployment']['description']['inputs']['description'])
            with tempfile.TemporaryDirectory() as folder:
                work=Path(folder);firmware=work/'firmware';licenses=work/'licenses'
                paths.write(firmware/'additional.bin','new firmware')
                paths.write(licenses/'WHENCE','upstream attributions');paths.write(licenses/'LICENCE.test','upstream terms')
                result=delivery.package(root,description['system'],REPO,firmware,licenses,None,{'source':'exact fixture'},work/'package')
                adapters={'nix':adapter}
                system.install(root,work/'package'/result['generation'],result['artifact'],
                    dependency_files=[work/'package'/result['component']],yes=True,adapters=adapters)
                plan=transition.prepare(root,result['artifact'],adapters=adapters)
                self.assertTrue(plan['description']['checks']['compatible'],plan['description']['checks']['errors'])
                realized=system.realization(root,result['artifact'])['description']
                inputs['system'].update(artifact=result['artifact'],composition=realized['composition'],
                    manifest=realized['manifest'],generation=result['label'])
                source=boot.record(boot.INPUTS,inputs)
                with mock.patch.object(shutil,'which',side_effect=lookup):
                    contract=handover.prepare(root,source,plan,adapters=adapters,tar=lookup('tar'))
                    captured=constructor.capture(root,source,adapters)
                    handover.check(root,source,captured,contract,verify_content=False)
                self.assertEqual(selection.current(root)[0],before)
                self.assertEqual(inputs['kernel'],description['deployment']['description']['inputs']['description']['kernel'])
        suite.hardware_construction(mounted=False,after_construct=inspect)


if __name__=='__main__':unittest.main()
