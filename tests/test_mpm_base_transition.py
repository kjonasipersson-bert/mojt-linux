# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Base preflight: declared gates plus real retained native-disk evidence."""
import copy
import os
from pathlib import Path
import shutil
import tempfile
import sys
import unittest
from unittest import mock

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
import mojt_artifact as artifact
import mpm_base as base
import mpm_base_transition as transition
import mpm_catalog as catalog
import mpm_deployment as deployment
import mpm_kernel as kernel
import test_mpm_base as base_fixture
import test_mpm_deployment as selected_fixture
import test_kernel_boot as boot_fixture


class AccountShellTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.tree=self.root/'candidate';self.tree.mkdir()
        self.login='/nix/store/'+'0'*32+'-util-linux-login'
        self.other='/nix/store/'+'1'*32+'-shell-dependency'
        for name in (self.login,self.other):
            path=self.root/name.lstrip('/');(path/'bin').mkdir(parents=True)
        self.shell=self.login+'/bin/nologin'
        self.file=self.root/self.shell.lstrip('/');self.file.write_text('#!/bin/sh\nexit 1\n');self.file.chmod(0o755)
        self.rows=[]
        self.refresh()

    def refresh(self):
        self.rows=[dict(path=p,tree_sha256=transition.system.tree_hash(self.root/p.lstrip('/'))) for p in (self.login,self.other)]
        self.manifest=transition.manifests.create(dict(label='shell-fixture',architecture=os.uname().machine,
            requirements=dict(base_abi={'libc':'glibc'},state_layout=1),
            support=dict(ports=dict(read=[],write=[],capabilities=[])),provides=[],
            artifacts=dict(nix=dict(objects=self.rows,packages={})),provenance={'fixture':True},profile={}))

    def check(self,shell=None):
        return transition.account_shell_check(self.root,self.tree,dict(base_shells=[shell or self.shell]),self.manifest)

    def test_indirect_retained_system_nologin_is_not_required_in_base(self):
        result=self.check();self.assertTrue(result['compatible'],result['errors'])
        proof,=result['retained_system_provider_paths']
        self.assertEqual(proof['path'],self.shell);self.assertEqual(proof['objects'],{self.login:self.rows[0]['tree_sha256']})
        self.assertFalse((self.tree/self.shell.lstrip('/')).exists())

    def test_unknown_and_prefix_collision_store_objects_are_not_exempt(self):
        for shell in ('/nix/store/'+'2'*32+'-unrelated/bin/nologin',self.login+'-extra/bin/nologin'):
            path=self.root/shell.lstrip('/');path.parent.mkdir(parents=True);path.write_text('unrelated');path.chmod(0o755)
            result=self.check(shell);self.assertFalse(result['compatible']);self.assertEqual(result['retained_system_provider_paths'],[])

    def test_symlink_may_resolve_only_inside_exact_retained_closure(self):
        target=self.root/self.other.lstrip('/')/'bin/nologin';target.write_text('fixture');target.chmod(0o755)
        self.file.unlink();self.file.symlink_to(self.other+'/bin/nologin');self.refresh()
        result=self.check();self.assertTrue(result['compatible'],result['errors'])
        self.assertEqual(set(result['retained_system_provider_paths'][0]['objects']),{self.login,self.other})

    def test_symlink_to_unretained_store_or_inspector_host_is_rejected(self):
        self.file.unlink();self.file.symlink_to('/bin/sh');self.refresh()
        result=self.check();self.assertFalse(result['compatible'])
        self.assertTrue(any('outside selected System closure' in error for error in result['errors']))

    def test_changed_system_dependency_blocks_instead_of_inheriting_a_label(self):
        self.file.write_text('changed after measurement')
        result=self.check();self.assertFalse(result['compatible'])
        self.assertTrue(any('provider object changed' in error for error in result['errors']))

    def test_missing_or_nonexecutable_provider_shell_is_not_accepted(self):
        self.file.chmod(0o644);self.refresh()
        self.assertFalse(self.check()['compatible'])
        self.file.unlink();self.refresh()
        self.assertFalse(self.check()['compatible'])

    def test_ordinary_base_shell_still_has_to_exist_in_candidate(self):
        result=self.check('/bin/sh');self.assertFalse(result['compatible'])
        (self.tree/'bin').mkdir();file=self.tree/'bin/sh';file.write_text('candidate');file.chmod(0o755)
        self.assertTrue(self.check('/bin/sh')['compatible'])

    def test_linked_provider_root_does_not_escape_guest_tree(self):
        source=self.root/self.login.lstrip('/')
        shutil.rmtree(source);source.symlink_to('/tmp')
        # Keep the old measured metadata. No inspector-host object is trusted.
        self.assertFalse(self.check()['compatible'])


@unittest.skipUnless(shutil.which('zstd'),'requires real packages')
class DeclaredGateTests(unittest.TestCase):
    def setUp(self):
        self.b=base_fixture.PreviewTests();self.b.setUp();self.addCleanup(self.b.doCleanups)
        self.f=selected_fixture.DeploymentTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        d=copy.deepcopy(self.f.selected['description']);d['kernel']=deployment.kernel_identity(self.f.body)
        self.selected=deployment.create(d)
        self.release=dict(format=1,base=dict(name='mojt',version='0.1.3',architecture=os.uname().machine),
                          abi=copy.deepcopy(self.f.manifest['description']['requirements']['base_abi']),state=dict(layout_version=1))
        self.bounds=dict(format=catalog.BASE_FORMAT,base=dict(artifact=self.b.body['id'],release='0.1.3'),
                         platform=self.b.body['platform'],kernel_min='6.12',kernel_max='6.12.999')
        self.facts=copy.deepcopy(self.f.context['facts'])

    def check(self):
        return transition.candidate_checks(self.b.body,self.release,self.selected,self.f.manifest,self.f.body,self.bounds,self.facts)

    def test_compatible_new_base_preserves_exact_system_and_kernel_without_input_mutation(self):
        old=copy.deepcopy((self.release,self.selected,self.bounds,self.facts))
        report=self.check();self.assertTrue(report['declared_compatible'])
        self.assertEqual(report['candidate_base']['artifact'],self.b.body['id'])
        self.assertEqual(report['system'],self.selected['description']['system'])
        self.assertEqual(report['kernel'],self.selected['description']['kernel'])
        self.assertEqual(old,(self.release,self.selected,self.bounds,self.facts))

    def test_changed_libc_declaration_is_not_inherited_from_selected_base(self):
        self.release['abi']={'libc':'glibc','libc_version':'99.0'}
        report=self.check();self.assertFalse(report['declared_compatible'])
        self.assertTrue(any('ABI' in e for e in report['errors']))
        self.assertEqual(report['candidate_facts']['base_abi'],self.release['abi'])

    def test_missing_abi_declarations_are_unknown_not_compatible(self):
        self.release.pop('abi')
        with self.assertRaisesRegex(ValueError,'explicit ABI'):self.check()

    def test_bounds_for_another_same_label_build_are_rejected(self):
        self.bounds['base']['artifact']='sha256:'+'a'*64
        with self.assertRaisesRegex(ValueError,'exact candidate'):self.check()

    def test_selected_kernel_outside_new_base_range_blocks_without_upgrading_it(self):
        before=copy.deepcopy(self.selected['description']['kernel'])
        self.bounds['kernel_min']='7.0';self.bounds['kernel_max']='7.9'
        report=self.check();self.assertFalse(report['declared_compatible'])
        self.assertIn('no implicit Kernel upgrade',report['errors'][-1]);self.assertEqual(report['kernel'],before)

    def test_current_state_layout_not_replaced_by_candidate_declaration(self):
        self.facts['state_layout']=2
        report=self.check();self.assertFalse(report['declared_compatible'])
        self.assertEqual(report['candidate_facts']['state_layout'],2)

    def test_unknown_candidate_layout_is_refused(self):
        self.release['state']['layout_version']=2
        with self.assertRaisesRegex(ValueError,'unsupported candidate state'):self.check()

    def test_old_system_writer_or_missing_account_shell_is_not_ignored(self):
        self.facts['ports']['format']=99
        self.assertFalse(self.check()['declared_compatible'])
        self.facts['ports']=None;self.facts['required_system_paths']=['/run/mojt-system/bin/missing']
        self.assertFalse(self.check()['declared_compatible'])

    def test_other_system_and_kernel_are_rejected_not_substituted(self):
        original=self.selected
        for field in ('system','kernel'):
            d=copy.deepcopy(original['description'])
            d[field]['manifest' if field=='system' else 'artifact']='sha256:'+'0'*64
            self.selected=deployment.create(d)
            with self.subTest(field=field),self.assertRaises(ValueError):self.check()


@unittest.skipUnless(os.geteuid()==0 and shutil.which('cpio') and shutil.which('zstd') and shutil.which('tar'),
                     'requires root and real archive tools')
class NativePreflightTests(unittest.TestCase):
    def setUp(self):
        self.f=boot_fixture.KernelBootTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.b=base_fixture.PreviewTests();self.b.setUp();self.addCleanup(self.b.doCleanups)
        archive,self.body=self.b.package(version='0.1.4',abi={'libc':'glibc','libc_version':'2.41'},
            extra=[base_fixture.entry('usr/bin/sh',b'#!/bin/sh\n# synthetic candidate shell\n')])
        self.root=self.f.root
        manifest=base.read(self.root/'system/native-fixture/manifest.json')
        provider=manifest['description']['artifacts']['nix']['packages']['util-linux']['output']+'/bin/nologin'
        with (self.root/'state/etc/passwd').open('a') as stream:
            stream.write('service-fixture:x:65534:65534:Service fixture:/:'+provider+'\n')
        base.install(self.root,archive,self.body['id'],yes=True)
        self.bounds=dict(format=catalog.BASE_FORMAT,base=dict(artifact=self.body['id'],release='0.1.4'),
                         platform=self.body['platform'],kernel_min='6.12',kernel_max='6.12.999')

    def prepare(self):return transition.prepare(self.root,self.body['id'],self.bounds,baseline=self.f.baseline)

    def test_real_base_system_kernel_and_state_bound_without_any_target_writes(self):
        before=self.f.snapshot();value=self.prepare();d=base.envelope(value,transition.FORMAT)
        self.assertEqual(self.f.snapshot(),before)
        self.assertTrue(d['checks']['declared_compatible'],d['checks']['errors'])
        self.assertEqual(d['candidate_base']['release'],'0.1.4')
        self.assertEqual(d['retained_system'],self.f.entries[self.f.old_id]['record']['description']['system'])
        self.assertEqual(d['retained_kernel'],self.f.entries[self.f.old_id]['record']['description']['kernel'])
        self.assertFalse(d['writes']);self.assertFalse(d['boot_ready']);self.assertFalse(d['stage_ready'])
        self.assertEqual(transition.recheck(self.root,value),value)
        self.assertEqual(self.f.snapshot(),before)

    def test_passwd_change_invalidates_snapshot_even_if_shell_is_still_supported(self):
        value=self.prepare();passwd=self.root/'state/etc/passwd'
        passwd.write_text(passwd.read_text().replace('root:x:0:0:root:', 'root:x:0:0:changed label:'))
        with self.assertRaisesRegex(ValueError,'inputs changed'):transition.recheck(self.root,value)

    def test_base_owned_account_shell_must_exist_in_candidate_not_inspector_host(self):
        passwd=self.root/'state/etc/passwd';passwd.write_text(passwd.read_text().replace('/bin/sh','/bin/bash'))
        report=self.prepare()['description']['checks']
        self.assertFalse(report['declared_compatible'])
        self.assertTrue(any('/bin/bash' in error for error in report['errors']))

    def test_corrupt_candidate_or_system_is_blocked_without_menu_change(self):
        before=(self.root/'boot/mojt/grub.cfg').read_bytes()
        (base.realization_path(self.root,self.body['id'])/'tree/rootfs/usr/bin/tool').write_text('damaged')
        with self.assertRaisesRegex(ValueError,'rootfs'):self.prepare()
        self.assertEqual((self.root/'boot/mojt/grub.cfg').read_bytes(),before)

    def test_unknown_state_and_regular_os_release_are_not_silently_prepared(self):
        marker=self.root/'state/layout-version';marker.write_text('2\n')
        with self.assertRaisesRegex(ValueError,'state layout'):self.prepare()
        marker.write_text('1\n');path=self.root/'state/etc/os-release';path.unlink();path.write_text('local file')
        with self.assertRaisesRegex(ValueError,'local configuration'):self.prepare()
        self.assertEqual(path.read_text(),'local file')

    def test_candidate_change_during_inspection_cannot_produce_accepted_evidence(self):
        original=transition.state_inputs;calls=0
        def mutate(root):
            nonlocal calls
            result=original(root);calls+=1
            if calls==1:(base.realization_path(root,self.body['id'])/'tree/rootfs/usr/bin/tool').write_text('late damage')
            return result
        with mock.patch.object(transition,'state_inputs',side_effect=mutate),self.assertRaisesRegex(ValueError,'rootfs'):self.prepare()


if __name__=='__main__':unittest.main()
