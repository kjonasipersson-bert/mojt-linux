# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real native usability packages and a boot-free owner-flow contract."""
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import test_system_fast_test as original
from test_mpm_system import REPO,tree
import mpm_system as system
import mojt_artifact as artifact

spec=importlib.util.spec_from_file_location('usability_delivery',REPO/'tools/mojt-usability-test.py')
delivery=importlib.util.module_from_spec(spec);spec.loader.exec_module(delivery)


class InputTests(unittest.TestCase):
    def test_pinned_data_driver_and_complete_new_module_inventory(self):
        self.assertEqual(hashlib.sha256((REPO/'tools/mojt-system-fast-test.py').read_bytes()).hexdigest(),delivery.DRIVER_SHA256)
        for name,digest in delivery.FILES.items():
            self.assertEqual(len(digest),64);self.assertTrue((REPO/name).is_file(),name)
        for name in ('tools/mpm_man.py','tools/mpm_ui.py','tools/mpm_system_cli.py'):self.assertIn(name,delivery.FILES)

    def test_new_cohort_handles_new_files_absent_from_old_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);runtime=root/'runtime';(runtime/'tools').mkdir(parents=True)
            (runtime/'tools/old.py').write_bytes(b'old compatible file')
            downloads={'tools/mojt_system.py':b"MPM_FILES=('mojt_system.py','old.py','new.py')\n",'tools/new.py':b'new owned module'}
            files={n:hashlib.sha256(v).hexdigest() for n,v in downloads.items()}
            with mock.patch.object(delivery,'WORK',root),mock.patch.object(delivery,'RUNTIME',runtime),mock.patch.object(delivery,'FILES',files):
                folder,code=delivery.code_cohort(downloads)
                self.assertEqual((folder/'new.py').read_bytes(),b'new owned module');self.assertEqual(len(code),3)

    def test_probe_uses_normal_install_without_separate_stage(self):
        before=dict(status=dict(staged_deployments=[dict(deployment='J-slot')]))
        bridge=mock.Mock();bridge.check.return_value=before;bridge.snapshot.return_value=before
        bridge.install_args.return_value=('system','install','--expected-id','J','-y','--json')
        bridge.run.return_value=dict(result=dict(prepared=True,preparation=dict(deployment='J-slot'),selection_changed=False))
        with mock.patch.object(delivery.subprocess,'run'):
            delivery.install_probe(bridge,dict(probe=dict(artifact='J')))
        bridge.run.assert_called_once_with('install-J','system','install','--expected-id','J','-y','--json',before=before)
        bridge.unchanged.assert_called_once_with(before,before)
        bridge.run.return_value=dict(result=dict(prepared=False))
        with self.assertRaisesRegex(ValueError,'did not finish'):delivery.install_probe(bridge,dict(probe=dict(artifact='J')))


@unittest.skipUnless(os.geteuid()==0 and original.shutil.which('zstd'),'requires numeric-root native archive publication')
class PackageTests(unittest.TestCase):
    def setUp(self):
        self.f=original.DeliveryTests();self.addCleanup(self.f.doCleanups)
        patch=mock.patch.object(original.Provider,'contains',lambda provider,ref,path:path.startswith('/nix/store/'+'0'*32+'-man-db/bin/'),create=True)
        patch.start();self.addCleanup(patch.stop)
        pack=original.pack
        def source_pack(source,*args,**kwargs):
            for name in ('man','manpath'):
                (source/'bin'/name).symlink_to('/nix/store/'+'0'*32+'-man-db/bin/'+name)
            return pack(source,*args,**kwargs)
        with mock.patch.object(original,'pack',side_effect=source_pack):self.f.setUp()
        self.bridge=SimpleNamespace(write_data=original.delivery.write_data,specification=original.delivery.specification)
        self.downloads={n:(REPO/n).read_bytes() for n in delivery.FILES}
        patch=mock.patch.object(delivery,'FILES',{n:hashlib.sha256(v).hexdigest() for n,v in self.downloads.items()})
        patch.start();self.addCleanup(patch.stop)

    def test_owned_wrappers_and_new_tools_are_packaged_without_changing_baseline(self):
        f=self.f;before=tree(f.root)
        row=delivery.package(self.bridge,f.root,f.body['id'],self.downloads,f.work/'I',label='system-ux-I')
        self.assertEqual(tree(f.root),before)
        kit=f.work/'I';part=artifact.verify(kit/row['component'])
        self.assertEqual(part['dependencies'],system.object_record(f.root,f.reference['artifact'])[0]['dependencies'])
        system.install(f.root,kit/row['generation'],row['artifact'],dependency_files=[kit/row['component']],adapters=f.adapters,yes=True)
        profile=system.realization_path(f.root,row['artifact'])/'profile'
        for name in ('man','manpath'):
            target=profile/'bin'/name
            self.assertFalse(target.is_symlink());self.assertIn('mpm_man.py',target.read_text());self.assertTrue(os.access(target,os.X_OK))
        system.realization(f.root,row['artifact'],verify=True)
        for name,digest in delivery.FILES.items():
            target=profile/name if name.startswith('tools/') else profile/'share/man/man1/mpm.1'
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),digest)
        self.assertFalse((f.root/'boot').exists());self.assertFalse(f.marker.exists())


if __name__=='__main__':unittest.main()
