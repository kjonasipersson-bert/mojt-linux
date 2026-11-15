# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Ordinary stage avoids scrubs while mutable facts and byte copies stay fresh."""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import mojt_artifact as artifact
import mpm_base as base
import mpm_base_transition as common
import mpm_boot_constructor as constructor
import mpm_boot_inventory as inventory
import mpm_boot_v2 as model
import mpm_boot_selection as selection
import mpm_boot_update as update
import mpm_native_io as io
import mpm_nix_boot as nix
import mpm_system as system
from test_mpm_system import Fixture
import test_mpm_boot_payload as fixtures


class PolicyTests(unittest.TestCase):
    def test_persistent_state_is_rechecked_inside_one_preparation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name in ('etc','var','home','root'):(root/'state'/name).mkdir(parents=True,exist_ok=True)
            (root/'state/layout-version').write_text('1\n')
            passwd=root/'state/etc/passwd';passwd.write_text('root:x:0:0:root:/root:/bin/sh\n')
            (root/'state/etc/os-release').symlink_to('../usr/lib/os-release')
            with io.preparation():
                before=common.state_inputs(root)
                passwd.write_text('root:x:0:0:root:/root:/bin/bash\n')
                after=common.state_inputs(root)
                self.assertNotEqual(before['evidence'],after['evidence'])
                self.assertEqual(after['base_shells'],['/bin/bash'])
                (root/'state/layout-version').write_text('2\n')
                with self.assertRaisesRegex(ValueError,'layout'):common.state_inputs(root)
    def test_scope_resets_after_failure_and_other_callers_keep_full_default(self):
        self.assertTrue(io.preparation_verify())
        with self.assertRaisesRegex(ValueError,'stop'):
            with io.preparation():
                self.assertFalse(io.preparation_verify())
                with io.preparation(verify=True):self.assertTrue(io.preparation_verify())
                self.assertFalse(io.preparation_verify());raise ValueError('stop')
        self.assertTrue(io.preparation_verify())

    def test_metadata_reuse_is_private_and_invalidates_replacement_modes_and_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'record.json';path.write_text('{"value":1}');path.chmod(0o444)
            with io.preparation(),mock.patch.object(base,'_read',wraps=base._read) as read:
                value=base.read(path);value['value']=999
                self.assertEqual(base.read(path),{'value':1});self.assertEqual(read.call_count,1)
                replacement=path.with_name('new.json');replacement.write_text('{"value":2}');replacement.chmod(0o444)
                replacement.replace(path)
                self.assertEqual(base.read(path),{'value':2});self.assertEqual(read.call_count,2)
                path.chmod(0o666)
                with self.assertRaisesRegex(ValueError,'unprotected'):base.read(path)
            path.chmod(0o444)
            with mock.patch.object(base,'_read',wraps=base._read) as read:base.read(path);self.assertEqual(read.call_count,1)

    def test_normal_code_hash_reuse_does_not_hide_same_size_edits_or_verify_audits(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'code.py';path.write_bytes(b'first')
            with io.preparation(),mock.patch.object(artifact,'_file_sha',wraps=artifact._file_sha) as read:
                first=artifact.file_sha(path);self.assertEqual(artifact.file_sha(path),first);self.assertEqual(read.call_count,1)
                info=path.stat();path.write_bytes(b'other');os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
                self.assertNotEqual(artifact.file_sha(path),first);self.assertEqual(read.call_count,2)
            with io.preparation(verify=True),mock.patch.object(artifact,'_file_sha',wraps=artifact._file_sha) as read:
                artifact.file_sha(path);artifact.file_sha(path);self.assertEqual(read.call_count,2)

    def test_stage_cli_passes_explicit_verify_and_scopes_both_policies(self):
        for verify in (False,True):
            with mock.patch.object(update,'_stage',side_effect=lambda *a,**k:io.preparation_verify()):
                self.assertIs(update.stage(None,'system','identifier',verify=verify),verify)
            with mock.patch.object(selection,'present',return_value=True), \
                 mock.patch.object(update,'stage',return_value={'changed':False}) as stage, \
                 mock.patch('sys.stdout'),mock.patch.object(update.os,'geteuid',return_value=0):
                args=['stage','--disk-root','/fixture','--artifact','sha256:'+'1'*64,'-y','--json']
                if verify:args+=['--verify']
                self.assertEqual(update.main('system',args),0);self.assertIs(stage.call_args.kwargs['verify'],verify)

    def test_nix_inspection_preserves_metadata_errors_and_never_scrubs_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);output=root/'output';(output/'bin').mkdir(parents=True)
            command=output/'bin/tool';command.write_text('fixture');command.chmod(0o755)
            retained=root/'retained/nix';retained.mkdir(parents=True);(retained/output.name).symlink_to(output)
            database=root/'db';database.mkdir();(database/'db.sqlite').write_bytes(b'initial')
            identity=dict(output=str(output),closure=[dict(path=str(output),nar_hash='hash')],commands=['tool'])
            def run(args):
                self.assertNotIn('--verify-path',args)
                return str(output) if '--requisites' in args else 'hash'
            runner=mock.Mock(side_effect=run);adapter=nix.NixBootAdapter(sys.executable,runner)
            adapter.identity=lambda ref:identity
            with mock.patch.object(nix,'NIX_DATABASE',database),mock.patch.object(nix,'store_path',side_effect=Path),io.preparation():
                adapter.inspect({},root);adapter.inspect({},root);self.assertEqual(runner.call_count,2)
                (database/'db.sqlite').write_bytes(b'changed')
                adapter.inspect({},root);self.assertEqual(runner.call_count,4)
                (database/'db.sqlite').write_bytes(b'force fresh query')
                def checkpoint(args):
                    (database/'db.sqlite').write_bytes(os.urandom(16))
                    return run(args)
                runner.side_effect=checkpoint
                adapter.inspect({},root);adapter.inspect({},root)
                self.assertEqual(runner.call_count,8)  # Changing DB status refuses reuse, not the valid query.
                (database/'db.sqlite').write_bytes(b'changed again')
                runner.side_effect=lambda args:'bad'
                with self.assertRaisesRegex(ValueError,'closure differs'):adapter.inspect({},root)
                (retained/output.name).unlink();(retained/output.name).symlink_to(root/'elsewhere')
                with self.assertRaisesRegex(ValueError,'retention conflict'):adapter.inspect({},root)

    def test_retained_proofs_reuse_exact_artifacts_only_and_full_mode_measures_again(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=fixtures.source();d=source['description']
            paths={area:root/path for area,path in (
                ('base','realizations/base/'+d['base']['artifact'][7:]+'/tree/rootfs'),
                ('system','realizations/system/'+d['system']['artifact'][7:]+'/profile'),
                ('kernel','kernel/installed/'+d['kernel']['artifact'][7:]+'/payload/lib/modules'))}
            for path in paths.values():path.mkdir(parents=True)
            with mock.patch.object(system,'retained_providers',return_value=[]):
                original=constructor.capture(root,source,{})
                entry=dict(record=dict(description=dict(inputs=source)),receipt=dict(description=dict(proof=original)))
                with mock.patch.object(selection,'current',return_value=(None,{'old':entry},None)),io.preparation(), \
                     mock.patch.object(inventory,'measure',side_effect=AssertionError('unexpected full scan')):
                    self.assertEqual(constructor.capture(root,source,{}),original)
                    paths['kernel'].rmdir()
                    with self.assertRaisesRegex(ValueError,'unavailable'):constructor.capture(root,source,{})
                paths['kernel'].mkdir()
                altered=copy.deepcopy(d);altered['system']['artifact']='sha256:'+'6'*64
                changed=model.record(model.INPUTS,altered)
                target=root/'realizations/system'/('6'*64)/'profile';target.mkdir(parents=True)
                with mock.patch.object(selection,'current',return_value=(None,{'old':entry},None)),io.preparation(), \
                     mock.patch.object(inventory,'measure',wraps=inventory.measure) as measure:
                    constructor.capture(root,changed,{})
                    measure.assert_called_once_with(target)
                conflict=copy.deepcopy(original['description']);conflict['base']['measurement']['digest']='sha256:'+'9'*64
                other=copy.deepcopy(entry);other['receipt']['description']['proof']=model.record(original['format'],conflict)
                with mock.patch.object(selection,'current',return_value=(None,{'one':entry,'two':other},None)), \
                     io.preparation(),self.assertRaisesRegex(ValueError,'conflicting retained'):
                    constructor.capture(root,source,{})
                with io.preparation(verify=True),mock.patch.object(inventory,'measure',wraps=inventory.measure) as measure:
                    self.assertEqual(constructor.capture(root,source,{}),original);self.assertEqual(measure.call_count,3)


@unittest.skipUnless(os.geteuid()==0 and shutil.which('zstd'),'numeric-owner native fixtures require root and zstd')
class ObjectTests(Fixture):
    def test_cached_object_metadata_detects_replacement_and_full_audit_detects_payload_damage(self):
        self.install();identifier=self.reference['artifact'];folder=system.object_path(self.root,identifier)
        with io.preparation(),mock.patch.object(system,'_object_record',wraps=system._object_record) as read:
            expected=system.object_record(self.root,identifier)
            self.assertEqual(system.object_record(self.root,identifier),expected);self.assertEqual(read.call_count,1)
            file=folder/'artifact.json';file.chmod(0o644);file.write_text('{}');file.chmod(0o444)
            with self.assertRaises(ValueError):system.object_record(self.root,identifier)
        # Use a separately installed untouched object for the explicit audit.
        generation=self.body['id'];payload=system.object_path(self.root,generation)/'payload/composition.json'
        payload.chmod(0o644);payload.write_bytes(b'corrupted');payload.chmod(0o444)
        with io.preparation():system.object_record(self.root,generation,verify=False)
        with io.preparation(verify=True),self.assertRaisesRegex(ValueError,'bytes differ'):
            system.object_record(self.root,generation,verify=True)


if __name__=='__main__':unittest.main()
