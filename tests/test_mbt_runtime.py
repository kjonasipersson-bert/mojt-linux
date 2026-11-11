# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real public MBT preparation, Git modes and privileged preflight boundaries.

Package/provider inputs are fixtures. This is not full bootstrap/guest acceptance.
No source preparation, interpreter, namespace or chroot boundary is mocked.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
import mbt_runtime as runtime
import mpm_management as management


HOST_TOOLS=('git','zstd','cpio','busybox','cp','mkfs.ext4','modprobe','du','openssl',
            'sfdisk','mkfs.vfat','mcopy','grub-mkstandalone','grub-script-check',
            'unshare','mount','umount','chroot')


@unittest.skipUnless(shutil.which('git'),'requires a real Git checkout')
class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='mojt-mbt-checkout-')
        self.addCleanup(self.temporary.cleanup)
        self.home=Path(self.temporary.name);self.home.chmod(0o700)
        seed=self.home/'seed';seed.mkdir()
        for name in runtime.resources(REPO):
            point=seed/name;point.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(REPO/name,point)
        def git(*args):
            return subprocess.run(['git',*args],check=True,capture_output=True,text=True)
        git('init','--quiet',str(seed));git('-C',str(seed),'add','.')
        git('-C',str(seed),'-c','user.name=Mojt fixture','-c','user.email=fixture@example.invalid',
            '-c','commit.gpgsign=false','commit','--quiet','-m','Frozen test resources')
        self.checkout=self.home/'source'
        subprocess.run(['git','clone','--quiet','--no-hardlinks',str(seed),str(self.checkout)],
                       check=True,capture_output=True,umask=0o002)
        self.assertEqual((self.checkout/'tools/mojt_native_image.py').stat().st_mode&0o777,0o664)
        self.before=self.snapshot()

    def snapshot(self):
        return {name:((self.checkout/name).stat().st_mode,hashlib.sha256((self.checkout/name).read_bytes()).hexdigest())
                for name in runtime.resources(self.checkout)}

    def call(self,*args,**kwargs):
        env=dict(os.environ,HOME=str(self.home),PYTHONPATH='/untrusted',PYTHONSTARTUP='/untrusted')
        return subprocess.run([sys.executable,'-I','-B',str(self.checkout/'tools/mbt'),*map(str,args)],
                              cwd='/',env=env,capture_output=True,text=True,timeout=60,**kwargs)

    def test_prepared_identity_is_repeatable_and_strict_manager_uses_the_copy(self):
        with self.assertRaisesRegex(ValueError,'unsafe/unbounded manager implementation'):
            management.file_hash(self.checkout/'tools/mojt_native_image.py')
        records=[]
        for unused in range(2):
            with tempfile.TemporaryDirectory(prefix=runtime.PREFIX,dir=runtime.temporary_parent()) as temporary:
                root=Path(temporary);records.append(runtime.freeze(self.checkout,root))
                code='import sys;sys.path.insert(0,sys.argv[1]);import mpm_management;print(mpm_management.current()["id"])'
                result=subprocess.run([sys.executable,'-I','-B','-c',code,str(root/'tools')],
                                      capture_output=True,text=True,check=True)
                self.assertRegex(result.stdout.strip(),r'^sha256:[a-f0-9]{64}$')
                changed=root/'tools/mojt_native_image.py';changed.chmod(0o664)
                with self.assertRaisesRegex(ValueError,'MBT execution file changed'):runtime.verify(root)
                changed.chmod(0o644);runtime.verify(root)
                (root/'extra').write_text('not inventoried')
                with self.assertRaisesRegex(ValueError,'unexpected MBT execution resource'):runtime.verify(root)
        self.assertEqual(records[0]['id'],records[1]['id'])
        self.assertEqual(self.before,self.snapshot())

    @unittest.skipUnless(shutil.which('zstd'),'requires the real archive codec')
    def test_public_package_command_works_from_group_writable_checkout_without_changing_it(self):
        source=self.home/'payload';source.mkdir();(source/'marker').write_text('retained input\n')
        spec=self.home/'spec.json';shutil.copyfile(REPO/'manifests/artifact-port-example.json',spec)
        output=self.home/'package'
        result=self.call('package','pack','--source',source,'--spec',spec,'--output',output)
        self.assertEqual(result.returncode,0,result.stderr)
        packed=json.loads(result.stdout)
        result=self.call('package','verify',output/packed['archive']['file'],'--expected-id',packed['artifact']['id'])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['id'],packed['artifact']['id'])
        self.assertEqual(self.before,self.snapshot());self.assertEqual(self.home.stat().st_mode&0o777,0o700)

    @unittest.skipUnless(all(shutil.which(n) for n in HOST_TOOLS),'requires the actual bootstrap host tools')
    def test_public_bootstrap_preview_prepares_code_and_reports_the_real_privileged_gate(self):
        import test_native_image as fixtures
        import test_system_vm as system_fixtures
        if os.geteuid()==0:
            probe=subprocess.run(['unshare','--pid','--fork','--kill-child','--mount-proc','true'],capture_output=True,text=True)
            if probe.returncode:self.skipTest('namespace permissions unavailable: '+probe.stderr.strip())
        f=fixtures.NativeImageTests();f.setUp();self.addCleanup(f.doCleanups)
        system=system_fixtures.SystemVmTests();system.setUp();self.addCleanup(system.doCleanups)
        system.fixture(10)
        output=self.home/'image'
        args=['bootstrap','--base-package',f.args.base_package,'--base-artifact',f.base['id'],
              '--base-context',f.bounds,'--kernel-registry',f.registry,'--kernel-artifact',f.kernel['id'],
              '--system-payload',system.payload,'--system-generation','runtime-test','--output',output,
              '--busybox',shutil.which('busybox'),'--dry-run']
        before=f.snapshot();result=self.call(*args)
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout);check=value['preflight']
        self.assertFalse(value['image_written']);self.assertFalse(output.exists())
        self.assertEqual(check['privileged'],'passed: private PID/mount namespace and chroot' if os.geteuid()==0
                         else 'not-run: requires administrator')
        self.assertFalse(check['password_requested'] or check['image_written'])
        self.assertRegex(check['manager'],r'^sha256:[a-f0-9]{64}$')
        self.assertEqual(check['host_tools']['chroot'],str(Path(shutil.which('chroot')).absolute()))
        self.assertEqual(before,f.snapshot());self.assertEqual(self.before,self.snapshot())
        self.assertEqual(self.home.stat().st_mode&0o777,0o700)


if __name__=='__main__':unittest.main()
