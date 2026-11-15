# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Persistent root projection, refusal boundaries and a private real-mount probe."""
import errno
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import mpm_boot_handover as handover
import test_mpm_boot_v2 as fixtures


def base_tree(tree):
    for name in ('usr/bin','usr/lib/modules','usr/lib/firmware','usr/local',*handover.ROOT_DIRECTORIES,'nix'):
        (tree/name).mkdir(parents=True,exist_ok=True)
    (tree/'usr/bin/tool').write_text('Base release A')
    (tree/'bin').symlink_to('usr/bin');(tree/'lib').symlink_to('/usr/lib')


@unittest.skipUnless(os.geteuid()==0,'persistent root requires numeric root ownership')
class RootTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'disk';(self.root/'state').mkdir(parents=True)
        self.tree=self.root/'base';base_tree(self.tree)
        self.mounts=[dict(source='nix',target='nix')]
        patch=mock.patch.object(handover.base,'store_info',return_value=dict(installation='1'*32))
        patch.start();self.addCleanup(patch.stop)

    def layout(self,**options):return handover.writable_root(self.root,self.tree,self.mounts,**options)

    def test_inspection_does_not_write_and_creation_preserves_state_across_base_return(self):
        before={p.relative_to(self.root):p.lstat().st_mode for p in self.root.rglob('*')}
        layout=self.layout();self.assertFalse(layout['root'].exists());self.assertFalse(layout['local'].exists())
        self.assertEqual(before,{p.relative_to(self.root):p.lstat().st_mode for p in self.root.rglob('*')})
        layout=self.layout(create=True);root=layout['root']
        for name in ('data','opt','srv'):
            (root/name).mkdir(exist_ok=True);(root/name/'keep').write_text('machine data')
        (layout['local']/'keep').write_text('local program')
        (root/'opt').chmod(0o2775)
        changed=self.root/'base-B';shutil.copytree(self.tree,changed,symlinks=True)
        (changed/'usr/bin/tool').write_text('Base release B')
        for tree in (changed,self.tree):
            result=handover.writable_root(self.root,tree,self.mounts,create=True)
            self.assertEqual(result['root'],root)
            self.assertIn((tree/'usr','usr'),result['bindings'])
            self.assertEqual((root/'data/keep').read_text(),'machine data')
            self.assertEqual((result['local']/'keep').read_text(),'local program')
        self.assertEqual((self.tree/'usr/bin/tool').read_text(),'Base release A')
        self.assertEqual(os.readlink(root/'lib'),'usr/lib')
        self.assertFalse((self.tree/'data').exists())

    def test_unmanaged_storage_conflicts_links_and_nonempty_mountpoints_are_refused(self):
        folder=self.root/'state/rootfs';folder.mkdir();(folder/'mine').write_text('do not adopt')
        with self.assertRaisesRegex(ValueError,'unmanaged'):self.layout(create=True)
        self.assertEqual((folder/'mine').read_text(),'do not adopt')
        shutil.rmtree(folder);layout=self.layout(create=True)
        for name in ('usr','etc','run','nix'):
            point=folder/name;point.rmdir();point.symlink_to(layout['local'])
            with self.assertRaisesRegex(ValueError,'mountpoint'):self.layout(create=True)
            point.unlink();point.mkdir()
        (folder/'usr/hidden').write_text('must not disappear behind Base')
        with self.assertRaisesRegex(ValueError,'hides local'):self.layout(create=True)
        (folder/'usr/hidden').unlink()
        (folder/'bin').unlink();(folder/'bin').symlink_to('/tmp')
        with self.assertRaisesRegex(ValueError,'Base link'):self.layout(create=True)

    def test_foreign_layout_new_reserved_base_paths_and_changed_root_identity_are_refused(self):
        self.layout(create=True)
        with mock.patch.object(handover.base,'store_info',return_value=dict(installation='2'*32)):
            with self.assertRaisesRegex(ValueError,'layout/installation'):self.layout()
        (self.tree/'extra').write_text('new Base-owned path')
        with self.assertRaisesRegex(ValueError,'explicit migration'):self.layout(create=True)
        (self.tree/'extra').unlink()
        (self.root/'state/local').rmdir();(self.root/'state/local').symlink_to('/tmp')
        with self.assertRaisesRegex(ValueError,'symlink|linked'):self.layout(create=True)

    def test_failed_publication_does_not_touch_base_or_adopt_partial_root(self):
        with mock.patch.object(handover.tx,'publish',side_effect=OSError('injected publication failure')):
            with self.assertRaisesRegex(OSError,'publication'):self.layout(create=True)
        self.assertFalse((self.root/'state/rootfs').exists())
        self.assertFalse(any(p.name.startswith('.rootfs-') for p in (self.root/'state').iterdir()))
        self.assertEqual((self.tree/'usr/bin/tool').read_text(),'Base release A')
        self.layout(create=True)

    def test_base_payload_in_mutable_paths_is_not_hidden(self):
        (self.tree/'opt/vendor').write_text('release-owned data')
        with self.assertRaisesRegex(ValueError,'conflicts with persistent'):self.layout(create=True)
        self.assertFalse((self.root/'state/rootfs').exists())


@unittest.skipUnless(os.geteuid()==0 and shutil.which('unshare') and shutil.which('mount'),'private mount namespace requires root and mount tools')
class MountTests(unittest.TestCase):
    def test_real_mounts_keep_root_and_local_writable_and_release_content_readonly(self):
        result=subprocess.run(['unshare','--mount','--propagation','private',sys.executable,str(Path(__file__).resolve()),'--mount-probe'],
                              capture_output=True,text=True)
        if result.returncode and 'unshare failed: Operation not permitted' in result.stderr:self.skipTest('mount namespaces unavailable')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


def mount_probe():
    def run(args):
        # util-linux can reparse host uid options while remounting a user-namespace
        # tmpfs fixture. The real handover uses BusyBox on the installation disk.
        if args[:3]==['mount','-o','remount,rw'] or args[:3]==['mount','-o','remount,ro']:
            args=['mount','-t','tmpfs','-o',args[2]+',uid=0,gid=0','tmpfs',args[-1]]
        subprocess.run(list(map(str,args)),check=True,stdout=subprocess.DEVNULL)
    class Booted(Exception):pass
    with tempfile.TemporaryDirectory() as temporary:
        work=Path(temporary);disk=work/'disk';disk.mkdir()
        run(['mount','-t','tmpfs','tmpfs',disk])
        try:
            tree=disk/'base';base_tree(tree)
            for name in ('etc','var','home','root'):(disk/'state'/name).mkdir(parents=True)
            profile=disk/'profile';profile.mkdir();(profile/'start').write_text('System start')
            dependency=disk/'nix/store/object';dependency.mkdir(parents=True);(dependency/'keep').write_text('provider')
            modules=disk/'modules';modules.mkdir()
            newroot=work/'newroot';newroot.mkdir()
            runtime=work/'runtime';(runtime/'bin').mkdir(parents=True)
            (runtime/'bin/busybox').write_text('fixture');(runtime/'shutdown').write_text('fixture')
            for name in ('dev','proc','sys'):
                point=runtime/name;point.mkdir();run(['mount','--bind',point,point])
            context=dict(tree=tree,profile=profile,modules=modules,mounts=[dict(source='nix',target='nix')],
                         provider_roots=['nix/store/object'],hostname='fixture',source=fixtures.fixture(),deployment=dict(id='sha256:'+'0'*64))
            def runner(args):
                if args[0]!='hostname':run(args)
            def execute(*unused):
                for name in ('data','opt','srv'):
                    (newroot/name).mkdir(exist_ok=True);(newroot/name/'keep').write_text('persistent')
                (newroot/'usr/local/keep').write_text('local')
                for name in ('usr/bin/tool','run/mojt-system/start','nix/store/object/keep'):
                    try:(newroot/name).write_text('must fail')
                    except OSError as error:assert error.errno==errno.EROFS,(name,error)
                    else:raise AssertionError('release content writable: '+name)
                assert 'DefaultDependencies=no' in (newroot/'run/systemd/system/usr.mount.d/10-mojt-exitrd.conf').read_text()
                assert 'DefaultDependencies=no' in (newroot/'run/systemd/system/usr-local.mount.d/10-mojt-exitrd.conf').read_text()
                raise Booted()
            with mock.patch.object(handover.base,'store_info',return_value=dict(installation='1'*32)):
                try:handover._enter(disk,context,{},runner=runner,execute=execute,newroot=newroot,runtime=runtime)
                except Booted:pass
                else:raise AssertionError('handover did not reach switch_root')
            for name in ('data','opt','srv'):assert (disk/'state/rootfs'/name/'keep').read_text()=='persistent'
            assert (disk/'state/local/keep').read_text()=='local'
            assert (tree/'usr/bin/tool').read_text()=='Base release A'
            assert (profile/'start').read_text()=='System start'
        finally:
            run(['mount','-o','remount,rw',disk])
            for name in ('sys','proc','dev'):
                point=work/'runtime'/name
                if point.exists():run(['umount',point])
            run(['umount',disk])


if __name__=='__main__':
    if sys.argv[1:]==['--mount-probe']:mount_probe()
    else:unittest.main()
