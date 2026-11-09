# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Focused namespace/gate tests; injected mount runner is not owner VM acceptance."""
import copy
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import test_mpm_boot_v2 as fixtures
import mojt_artifact as artifact
import mpm_boot_constructor as constructor
import mpm_boot_handover as handover
from mpm_request_plan import record


class NamespaceTests(unittest.TestCase):
    def test_mount_unit_escaping_and_guest_resolution_do_not_read_host_paths(self):
        self.assertEqual(handover.unit_name('/run/mojt-system'),'run-mojt\\x2dsystem.mount')
        self.assertEqual(handover.unit_name('/nix/store/hash-a+b'),'nix-store-hash\\x2da\\x2bb.mount')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);tree=root/'base';profile=root/'profile'
            (tree/'usr/bin').mkdir(parents=True);(tree/'run').mkdir();(tree/'bin').symlink_to('usr/bin')
            (tree/'usr/bin/sh').write_text('verified fixture');(tree/'usr/bin/sh').chmod(0o755)
            (profile/'bin').mkdir(parents=True);(profile/'bin/sh').symlink_to('/bin/sh')
            self.assertEqual(handover.guest_file(root,tree,profile,[],[],'/run/mojt-system/bin/sh'),tree/'usr/bin/sh')
            (profile/'bin/sh').unlink();(profile/'bin/sh').symlink_to('/etc/passwd')
            (root/'state/etc').mkdir(parents=True);(root/'state/etc/passwd').write_text('untrusted state executable')
            (root/'state/etc/passwd').chmod(0o755)
            with self.assertRaisesRegex(ValueError,'verified immutable'):handover.guest_file(root,tree,profile,[],[],'/run/mojt-system/bin/sh')


@unittest.skipUnless(os.geteuid()==0 and all(shutil.which(c) for c in ('zstd','cpio','tar')),'requires root and archive tools')
class PreparationTests(unittest.TestCase):
    def test_boot_base_preparation_current_state_gates_and_failed_mount_cleanup_preserve_the_installation(self):
        f=fixtures.Retention();f.setUp();self.addCleanup(f.doCleanups);root=f.root
        f.f.adapter.boot_paths=lambda ref,target:sorted(r['path'].lstrip('/') for r in ref['identity']['objects'])
        f.f.adapter.boot_mounts=lambda ref,target:[dict(source='nix',target='nix')]
        plan=f.f.plan();source=copy.deepcopy(f.source['description']);source['boot']['root_uuid']=plan['description']['root_uuid']
        source=record('mojt-boot-inputs-v2',source);before=f.f.f.snapshot()
        contract=handover.prepare(root,source,plan,adapters=f.f.adapters)
        after=f.f.f.snapshot();self.assertEqual(before,{k:after.get(k) for k in before})
        snapshot=f.f.f.snapshot();self.assertEqual(handover.prepare(root,source,plan,adapters=f.f.adapters),contract)
        self.assertEqual(snapshot,f.f.f.snapshot())
        proof=constructor.capture(root,source,f.f.adapters);context=handover.check(root,source,proof,contract)
        layout=root/'state/layout-version';original=layout.read_bytes();layout.write_bytes(b'2\n')
        with self.assertRaisesRegex(ValueError,'state layout'):handover.check(root,source,proof,contract)
        layout.write_bytes(original)
        work=f.f.f.fixture.work;newroot=work/'failure-newroot';newroot.mkdir()
        runtime=work/'fake-exitrd';(runtime/'bin').mkdir(parents=True)
        (runtime/'bin/busybox').write_bytes(b'fixture');(runtime/'shutdown').write_text('fixture')
        for name in ('dev','proc','sys'):(runtime/name).mkdir()
        calls=[];executed=[]
        def runner(args):
            args=list(map(str,args));calls.append(args)
            if args[:2]==['mount','--bind']:
                src,dst=map(Path,args[-2:])
                if dst==newroot:shutil.copytree(src,dst,symlinks=True,dirs_exist_ok=True)
                elif not dst.exists():dst.mkdir(parents=True)
            if args==['mount','--move',str(runtime/'sys'),str(newroot/'sys')]:raise OSError('injected late mount failure')
        context['deployment']={'fixture':'not published'}
        with self.assertRaisesRegex(OSError,'late mount'):
            handover._enter(root,context,{'deployment':'sha256:'+'0'*64},runner=runner,
                            execute=lambda *args:executed.append(args),newroot=newroot,runtime=runtime)
        self.assertFalse(executed)
        self.assertIn(['mount','--move',str(newroot/'proc'),str(runtime/'proc')],calls)
        self.assertIn(['mount','--move',str(newroot/'dev'),str(runtime/'dev')],calls)
        self.assertEqual(calls[-1],['mount','-o','remount,ro',str(root)])
        readonly=[c for c in calls if c[:3]==['mount','-o','remount,bind,ro']]
        self.assertTrue(any(c[-1]==str(newroot/'run/mojt-system') for c in readonly))
        self.assertTrue(any('/nix/store/' in c[-1] for c in readonly))
        self.assertTrue((newroot/'run/initramfs/shutdown').is_file())
        after=f.f.f.snapshot();self.assertEqual(snapshot,after)


if __name__=='__main__':unittest.main()
