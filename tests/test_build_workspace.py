# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Private build-VM staging contracts; external image commands are simulated."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import types
import unittest
from unittest import mock

REPO=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('workspace',REPO/'tools/mojt-build-workspace.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)

LAUNCHER='#!/bin/bash\nhere=/private\nexec qemu-system-x86_64 \\\n    -m 1024 -smp 2 \\\n    -drive "file=$here/disk.img,if=virtio,format=raw"\n'


class WorkspaceTests(unittest.TestCase):
    def test_launcher_is_private_explicit_and_refuses_unknown_templates(self):
        patched=w.patch_launcher(LAUNCHER)
        self.assertEqual(patched.count('workspace.img'),1)
        self.assertIn('-m 4096 -smp 2',patched)
        self.assertIn('file=$here/disk.img',patched)
        subprocess.run(['bash','-n'],input=patched,text=True,check=True)
        for text in (patched,'#!/bin/sh\nexec other\n'):
            with self.assertRaises(ValueError):w.patch_launcher(text)

    def test_inventory_does_not_follow_external_links_and_detects_content_and_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);tree=root/'inputs';tree.mkdir();outside=root/'outside';outside.write_text('one')
            (tree/'link').symlink_to(outside);(tree/'data').write_text('one')
            old=w.inventory(tree);outside.write_text('two')
            self.assertEqual(w.inventory(tree),old)
            (tree/'data').write_text('two');self.assertNotEqual(w.inventory(tree),old)
            old=w.inventory(tree);(tree/'data').chmod(0o600);self.assertNotEqual(w.inventory(tree),old)

    def test_complete_staging_and_live_disk_failure_preserve_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'target';payload=root/'payload';source=root/'source';vm=root/'vm';mods=root/'lib/modules/test'
            for p in (target/'base/0.1.3',target/'state',target/'releases',payload,source/'tools',vm,mods):p.mkdir(parents=True,exist_ok=True)
            (target/'.install-lock').touch();(target/'base/0.1.3/data').write_text('base')
            (target/'releases/base-0.1.3.toml').write_text('metadata')
            (payload/'system.json').write_text('{}');(source/'tools/builder.py').write_text('source')
            (vm/'disk.img').write_bytes(b'original disk');(vm/'build.json').write_text('{}');(vm/'run-qemu.sh').write_text(LAUNCHER)
            kernel=root/'vmlinuz-test';kernel.write_bytes(b'kernel');(mods/'modules.dep').write_text('modules')
            args=types.SimpleNamespace(output=root/'new',target=target,payload=payload,source=source,vm=vm,kernel=kernel,modules=mods,base='0.1.3',workspace_gib=32)
            original={str(p):w.inventory(p) for p in (target,payload,source,vm,mods)}
            calls=[]
            def run(*values,**kwargs):
                a=list(map(str,values));calls.append(a)
                if a[0]=='git':
                    if 'status' in a:return types.SimpleNamespace(stdout='')
                    if 'rev-parse' in a:return types.SimpleNamespace(stdout='a'*40+'\n')
                    archive=Path(next(x.split('=',1)[1] for x in a if x.startswith('--output=')))
                    with tarfile.open(archive,'w') as tar:tar.add(source/'tools',arcname='tools')
                elif a[0]=='qemu-img':Path(a[-1]).write_bytes(Path(a[-2]).read_bytes())
                elif a[0]=='cp':
                    src,dest=map(Path,a[-2:])
                    if src.is_dir():shutil.copytree(src,dest,symlinks=True)
                    else:shutil.copy2(src,dest)
                return types.SimpleNamespace(stdout='')
            with mock.patch.object(w.os,'geteuid',return_value=0),mock.patch.object(w.os,'chown'),mock.patch.object(w.shutil,'which',return_value='/tool'),mock.patch.object(w,'run',side_effect=run):
                w.prepare(args)
                self.assertFalse((args.output/'.preparing').exists())
                record=json.loads((args.output/'inputs.json').read_text())
                self.assertEqual(record['inventory'],w.inventory(args.output/'staging/inputs'))
                self.assertEqual(record['revision'],'a'*40)
                w.verify(args.output/'staging')
                marker=args.output/'staging/inputs/source/tools/builder.py'
                marker.write_text('changed')
                with self.assertRaisesRegex(ValueError,'inventory differs'):w.verify(args.output/'staging')
                marker.write_text('source')
                self.assertEqual((args.output/'vm/disk.img').read_bytes(),b'original disk')
                self.assertIn('workspace.img',(args.output/'vm/run-qemu.sh').read_text())
                self.assertTrue(any(a[0]=='mkfs.ext4' and '-d' in a for a in calls))
                with self.assertRaisesRegex(ValueError,'must not exist'):w.prepare(args)
                args.output=root/'failed'
                def fail(*values,**kwargs):
                    if values[0]=='qemu-img':raise subprocess.CalledProcessError(1,values)
                    return run(*values,**kwargs)
                with mock.patch.object(w,'run',side_effect=fail),self.assertRaises(subprocess.CalledProcessError):w.prepare(args)
                self.assertTrue((args.output/'.preparing').exists())
                self.assertFalse((args.output/'vm/run-qemu.sh').exists())
            for p in (target,payload,source,vm,mods):self.assertEqual(w.inventory(p),original[str(p)])


if __name__=='__main__':unittest.main()
