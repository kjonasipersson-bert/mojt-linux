# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Local Base install/upgrade with real storage/defaults/selection; simulated initramfs."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import test_system_install_transaction as transactions
import mojt_artifact as artifact
import mpm_base as base
import mpm_base_cli as cli
import mpm_boot_constructor as constructor
import mpm_boot_selection as selection
import mpm_boot_update as update

REPO=Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.geteuid()==0 and all(shutil.which(c) for c in ('tar','zstd','cpio')),
                     'requires root and native archive tools')
class BaseUpdateFlow(unittest.TestCase):
    def setUp(self):
        self.f=transactions.InstallationTransaction();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root
        self.before=selection.selected(self.root)[0]['description']['selected']
        selected=selection.ready(self.root,self.before)['record']['description']['inputs']['description']
        source=base.realization_path(self.root,selected['base']['artifact'])/'tree/rootfs'
        tree=self.f.work/'next-base';shutil.copytree(source,tree,symlinks=True)
        for path in [tree,*tree.rglob('*')]:
            if not path.is_symlink():path.chmod(path.stat().st_mode|0o700 if path.is_dir() else path.stat().st_mode|0o200)
        for name,content in [('services','https 443/tcp\n'),('protocols','tcp 6 TCP\n')]:
            (tree/'usr/etc'/name).write_text(content);(tree/'usr/etc'/name).chmod(0o644)
        config=self.f.work/'next-base.toml'
        config.write_text('format=1\n[base]\nname="mojt"\nversion="0.2.1"\narchitecture="x86_64"\n'
            '[abi]\nlibc="glibc"\nlibc_version="2.44"\n[build]\nbackend="source"\n')
        subprocess.run([sys.executable,'-I','-B',str(REPO/'tools/mojt-base-pack'),str(tree),str(config),
            str(self.f.work/'releases'),'--normalize-owner'],check=True,capture_output=True)
        release=self.f.work/'releases/base-0.2.1-x86_64';spec,attachments=artifact.base_input(release,1)
        package=self.f.work/'package';result=artifact.pack(release,spec,package,attachments)
        self.archive=package/result['archive']['file'];self.identifier=result['artifact']['id']
        self.runtime=SimpleNamespace(disk=self.root,helpers=Path(shutil.which('tar')).parent)
        services=self.root/'state/etc/services';services.write_text('custom 12345/tcp\n');services.chmod(0o600)
        self.services=(services.read_bytes(),services.stat().st_ino)
        self.actual_stage=update.stage

    def run_cli(self,*args,failed=False):
        stdout=io.StringIO();stderr=io.StringIO()
        def stage(root,area,identifier,**kwargs):
            kwargs.update(runtime_directory=self.f.bundle,busybox=self.f.busybox,adapters=self.f.f.f.adapters)
            return self.actual_stage(root,area,identifier,**kwargs)
        with mock.patch.object(cli.os.path,'ismount',return_value=True), \
             mock.patch.object(constructor,'_build_locked',side_effect=self.f.build), \
             mock.patch.object(update,'stage',side_effect=ValueError('constructor failed') if failed else stage), \
             contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
            code=cli.main(list(args),runtime=self.runtime)
        return code,stdout.getvalue(),stderr.getvalue()

    def test_install_and_upgrade_preserve_local_config_and_other_boot_inputs(self):
        original=selection.ready(self.root,self.before)['record']['description']['inputs']['description']
        code,out,err=self.run_cli('install','--from-file',str(self.archive),'-y','--json')
        self.assertEqual(code,0,err);installed=json.loads(out)
        self.assertTrue(installed['prepared']);self.assertFalse(installed['selection_changed'])
        self.assertEqual(selection.selected(self.root)[0]['description']['selected'],self.before)
        services=self.root/'state/etc/services'
        self.assertEqual((services.read_bytes(),services.stat().st_ino),self.services)
        self.assertEqual((self.root/'state/etc/protocols').read_text(),'tcp 6 TCP\n')
        candidate=selection.ready(self.root,installed['preparation']['deployment'])['record']['description']['inputs']['description']
        for field in ('system','kernel','boot','firmware','state_requirements'):self.assertEqual(original[field],candidate[field])
        self.assertEqual(candidate['base']['kernel_min'],original['kernel']['upstream'])
        self.assertEqual(candidate['base']['kernel_max'],original['kernel']['upstream'])
        code,out,err=self.run_cli('upgrade','--from-file',str(self.archive),'-y','--json')
        self.assertEqual(code,0,err);chosen=json.loads(out)
        self.assertTrue(chosen['selection_changed'])
        self.assertEqual(selection.selected(self.root)[0]['description']['selected'],installed['preparation']['deployment'])
        self.assertEqual((services.read_bytes(),services.stat().st_ino),self.services)

    def test_preview_content_only_wrong_id_and_preparation_failure_leave_selection(self):
        code,out,err=self.run_cli('install','--from-file',str(self.archive),'--dry-run','--json')
        self.assertEqual(code,0,err);self.assertFalse(json.loads(out)['prepared'])
        self.assertFalse(base.object_path(self.root,self.identifier).exists())
        self.assertFalse((self.root/'state/etc/protocols').exists())
        code,out,err=self.run_cli('install','--from-file',str(self.archive),'--expected-id','sha256:'+'f'*64,'-y')
        self.assertEqual(code,1);self.assertIn('unexpected artifact',err)
        code,out,err=self.run_cli('install','--from-file',str(self.archive),'--content-only','-y','--json')
        self.assertEqual(code,0,err);self.assertFalse(json.loads(out)['prepared'])
        self.assertFalse((self.root/'state/etc/protocols').exists())
        code,out,err=self.run_cli('install','--from-file',str(self.archive),'-y','--json',failed=True)
        self.assertEqual(code,1);self.assertIn('content is installed',err)
        self.assertEqual(selection.selected(self.root)[0]['description']['selected'],self.before)
        self.assertEqual((self.root/'state/etc/protocols').read_text(),'tcp 6 TCP\n')
        code,out,err=self.run_cli('install','--from-file',str(self.archive),'-y','--json')
        self.assertEqual(code,0,err);self.assertTrue(json.loads(out)['prepared'])

    def test_stale_selection_and_declined_choice_do_not_select_new_base(self):
        code,out,err=self.run_cli('upgrade','--from-file',str(self.archive),'--expected-selected','sha256:'+'f'*64,'-y')
        self.assertEqual(code,1);self.assertFalse(base.object_path(self.root,self.identifier).exists())
        with mock.patch('builtins.input',side_effect=['y','y','n']):
            code,out,err=self.run_cli('upgrade','--from-file',str(self.archive))
        self.assertEqual(code,1,err)
        self.assertEqual(selection.selected(self.root)[0]['description']['selected'],self.before)

    def test_post_publication_flush_failure_reports_unknown_selection_and_retains_the_new_entry(self):
        import mpm_transaction as transaction
        choose=selection.select
        def uncertain(*args,**kwargs):
            choose(*args,**kwargs)
            raise transaction.PublicationUncertain('final directory flush failed')
        with mock.patch.object(selection,'select',side_effect=uncertain):
            code,out,err=self.run_cli('upgrade','--from-file',str(self.archive),'-y','--json')
        self.assertEqual(code,1);result=json.loads(out)
        self.assertIsNone(result['selection_changed']);self.assertTrue(result['publication_uncertain'])
        self.assertTrue(result['prepared']);self.assertIn('inspect mpm base status',err)
        self.assertNotEqual(selection.selected(self.root)[0]['description']['selected'],self.before)


if __name__=='__main__':unittest.main()
