# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real native acquisition without a provider, extraction, or activation."""
import copy
import hashlib
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import mpm_native_cache as cache
import test_mojt_artifact as fixture


def raw(value):
    return cache.model.canonical(value)+b'\n'


def evidence(value):
    return dict(sha256=hashlib.sha256(value).hexdigest(),size=len(value))


@unittest.skipUnless(shutil.which('zstd'),'requires zstd')
class CacheTests(unittest.TestCase):
    def setUp(self):
        self.package=fixture.PackageTests();self.package.setUp()
        self.addCleanup(self.package.doCleanups)
        self.work=self.package.work

    def setup_kind(self,kind='port'):
        if kind=='base':self.package.base()
        elif kind=='kernel':self.package.kernel()
        else:self.package.file('bin/tool',mode=0o755)
        archive,result=self.package.package(fixture.spec(kind))
        self.repo=archive.parent;self.archive=archive;self.body=result['artifact']
        self.root=self.work/'cache'
        self.policy_file=self.work/'policy.json'
        self.policy=cache.record(cache.POLICY,dict(name='local',provider='native',channel='stable',root=str(self.repo),max_archive=1024**2,max_expanded=1024**2))
        self.policy_file.write_bytes(raw(self.policy))
        source=cache.record('mojt-source-v1',dict(name='local',provider='native',channel='stable',location=dict(kind='local-directory',path=str(self.repo)),trust=dict(kind='explicit-local',policy=self.policy['id'])))
        ref=dict(provider='native',artifact=self.body['id'])
        candidate=dict(name=self.body['name'],release_id='1.2.3',upstream_version='1.2.3',version_scheme='dotted-v1',source='local',artifact=self.body['id'],integrity=dict(sha256=result['archive']['sha256']),stability='stable',compatibility='verified')
        catalog=raw(dict(format='mpm-release-catalog-v1',area='ports' if kind=='port' else kind,name=self.body['name'],platform='x86_64-linux',channel='stable',sources=dict(local=dict(backend='native',identity=dict(repository='test'))),candidates=[candidate]))
        mapping=cache.record('mojt-acquisition-map-v1',dict(catalog_sha256=evidence(catalog)['sha256'],offers=[dict(reference=ref,descriptor=dict(path='artifact.json',**evidence((self.repo/'artifact.json').read_bytes())),archives=[dict(paths=[archive.name],**evidence(archive.read_bytes()))])]))
        mapping_raw=raw(mapping)
        snapshot=cache.record('mojt-source-snapshot-v1',dict(source=source['id'],catalog=dict(format='mpm-release-catalog-v1',**evidence(catalog)),acquisition=dict(id=mapping['id'],**evidence(mapping_raw)),provider_snapshot=None,trust_policy=self.policy['id']))
        self.args=dict(policy_file=self.policy_file,source=source,snapshot=snapshot,catalog_bytes=catalog,acquisition_bytes=mapping_raw,ref=ref,archive_sha256=result['archive']['sha256'],kind=kind)

    def prepare(self):return cache.prepare(self.root,**self.args)
    def acquire(self,plan=None,**kwargs):return cache.acquire(self.root,plan or self.prepare(),**self.args,**kwargs)
    def tree(self):return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_four_categories_real_cache_and_noop(self):
        for kind in fixture.artifact.KINDS:
            with self.subTest(kind=kind):
                # A fresh synthetic payload for each category.
                shutil.rmtree(self.package.source);self.package.source.mkdir()
                self.setup_kind(kind)
                self.root=self.work/('cache-'+kind)
                plan=self.prepare();self.assertFalse(self.root.exists())
                result=self.acquire(plan)
                self.assertTrue(result['changed']);self.assertTrue(result['copied'])
                self.assertEqual(Path(result['archive']).read_bytes(),self.archive.read_bytes())
                self.assertEqual(result['record']['description']['artifact'],self.body['id'])
                before=self.tree();again=self.acquire(plan)
                self.assertFalse(again['changed']);self.assertFalse(again['copied'])
                self.assertEqual(result['record'],again['record']);self.assertEqual(before,self.tree())
                self.assertFalse((self.root/'installed').exists())

    def test_cached_bytes_reverify_with_source_offline(self):
        self.setup_kind();result=self.acquire();shutil.rmtree(self.repo)
        self.assertFalse(self.acquire()['changed'])
        blob=Path(result['archive']);blob.chmod(0o644);blob.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'cached archive'):self.acquire()
        self.assertEqual(blob.read_bytes(),b'corrupt')

    def test_corrupt_source_never_publishes_archive_or_receipt(self):
        self.setup_kind();plan=self.prepare();self.archive.write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'size'):self.acquire(plan)
        self.assertEqual(list((self.root/'archives/sha256').iterdir()),[])
        self.assertEqual(list((self.root/'records').iterdir()),[])
        self.assertEqual(list(self.root.glob('.fetch-*')),[])

    def test_descriptor_corruption_and_raw_catalog_change_fail_before_writes(self):
        self.setup_kind();self.args['catalog_bytes']+=b' '
        with self.assertRaisesRegex(ValueError,'size'):self.prepare()
        self.assertFalse(self.root.exists())
        self.setup_kind();(self.repo/'artifact.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'size'):self.prepare()
        self.assertFalse(self.root.exists())

    def test_changed_owner_policy_invalidates_saved_plan(self):
        self.setup_kind();plan=self.prepare()
        policy=copy.deepcopy(self.policy['description']);policy['max_archive']+=1
        self.policy_file.write_bytes(raw(cache.record(cache.POLICY,policy)))
        with self.assertRaisesRegex(ValueError,'authorized'):self.acquire(plan)
        self.assertFalse(self.root.exists())

    def test_stale_or_modified_plan_is_rejected_before_writes(self):
        self.setup_kind();plan=self.prepare();plan['description']['kind']='kernel'
        with self.assertRaisesRegex(ValueError,'plan inputs changed'):self.acquire(plan)
        self.assertFalse(self.root.exists())

    def test_policy_revocation_during_verification_prevents_publication(self):
        self.setup_kind();plan=self.prepare();verify=cache.artifact.verify
        def revoke(*args,**kwargs):
            result=verify(*args,**kwargs)
            self.policy_file.write_bytes(raw(cache.record('mojt-local-source-policy-v2',self.policy['description'])))
            return result
        with mock.patch.object(cache.artifact,'verify',side_effect=revoke):
            with self.assertRaisesRegex(ValueError,'unsupported'):self.acquire(plan)
        self.assertEqual(list((self.root/'archives/sha256').iterdir()),[])
        self.assertEqual(list((self.root/'records').iterdir()),[])
        self.assertEqual(list(self.root.glob('.fetch-*')),[])

    def test_unsafe_policy_and_source_files_rejected(self):
        self.setup_kind();self.policy_file.chmod(0o666)
        with self.assertRaisesRegex(ValueError,'unsafe'):self.prepare()
        self.policy_file.chmod(0o644);plan=self.prepare()
        outside=self.work/'outside';self.archive.rename(outside);self.archive.symlink_to(outside)
        with self.assertRaises(OSError):self.acquire(plan)
        self.assertEqual(list((self.root/'archives/sha256').iterdir()),[])

    def test_hardlinked_source_and_fifo_do_not_block_or_publish(self):
        self.setup_kind();plan=self.prepare();os.link(self.archive,self.work/'link')
        with self.assertRaisesRegex(ValueError,'unsafe'):self.acquire(plan)
        self.archive.unlink();os.mkfifo(self.archive)
        with self.assertRaisesRegex(ValueError,'unsafe'):self.acquire(plan)

    def test_paths_and_wrong_encoding_are_rejected(self):
        self.setup_kind();self.args['archive_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'not approved'):self.prepare()
        self.assertFalse(self.root.exists())
        for name in ('../outside','/absolute','a/../b','a//b'):
            with self.subTest(path=name),self.assertRaises(ValueError):
                with cache.confined(self.repo,name):pass

    def test_wrong_category(self):
        self.setup_kind();self.args['kind']='kernel'
        with self.assertRaisesRegex(ValueError,'category'):self.prepare()
        self.assertFalse(self.root.exists())

    def test_valid_catalog_with_wrong_artifact_name_is_rejected(self):
        self.setup_kind()
        catalog=cache.artifact.parse_json(self.args['catalog_bytes'])
        catalog['name']=catalog['candidates'][0]['name']='different'
        self.args['catalog_bytes']=raw(catalog)
        mapping=cache.artifact.parse_json(self.args['acquisition_bytes'])['description']
        mapping['catalog_sha256']=evidence(self.args['catalog_bytes'])['sha256']
        mapping=cache.record('mojt-acquisition-map-v1',mapping)
        self.args['acquisition_bytes']=raw(mapping)
        snapshot=copy.deepcopy(self.args['snapshot']['description'])
        snapshot['catalog'].update(evidence(self.args['catalog_bytes']))
        snapshot['acquisition']=dict(id=mapping['id'],**evidence(self.args['acquisition_bytes']))
        self.args['snapshot']=cache.record('mojt-source-snapshot-v1',snapshot)
        with self.assertRaisesRegex(ValueError,'catalog/descriptor'):self.prepare()
        self.assertFalse(self.root.exists())

    def test_decompression_cap_includes_tar_overhead(self):
        self.setup_kind()
        # The payload is tiny, but the whole expanded tar still exceeds this.
        policy=copy.deepcopy(self.policy['description']);policy['max_expanded']=4096
        self.policy=cache.record(cache.POLICY,policy);self.policy_file.write_bytes(raw(self.policy))
        sd=copy.deepcopy(self.args['source']['description']);sd['trust']['policy']=self.policy['id']
        self.args['source']=cache.record('mojt-source-v1',sd)
        snap=copy.deepcopy(self.args['snapshot']['description']);snap.update(source=self.args['source']['id'],trust_policy=self.policy['id'])
        self.args['snapshot']=cache.record('mojt-source-snapshot-v1',snap)
        with self.assertRaisesRegex(ValueError,'decompressed'):self.acquire()
        self.assertEqual(list((self.root/'archives/sha256').iterdir()),[])

    def test_failed_copy_cleanup_and_retry(self):
        self.setup_kind();plan=self.prepare()
        with mock.patch.object(cache.artifact,'verify',side_effect=RuntimeError('interrupted')):
            with self.assertRaisesRegex(RuntimeError,'interrupted'):self.acquire(plan)
        self.assertEqual(list(self.root.glob('.fetch-*')),[])
        self.assertTrue(self.acquire(plan)['changed'])

    def test_flush_failure_keeps_verified_blob_and_retry_reverifies(self):
        self.setup_kind();plan=self.prepare()
        def sync(directory):
            if directory==self.root/'archives/sha256':raise OSError('injected flush')
            cache.tx.sync_directory(directory)
        with self.assertRaises(cache.tx.PublicationUncertain):self.acquire(plan,sync=sync)
        blob=self.root/'archives/sha256'/self.args['archive_sha256']
        self.assertTrue(blob.is_file());self.assertEqual(blob.read_bytes(),self.archive.read_bytes())
        self.assertEqual(list((self.root/'records').iterdir()),[])
        self.assertEqual(list(self.root.glob('.fetch-*')),[])
        result=self.acquire(plan)
        self.assertTrue(result['changed']);self.assertFalse(result['copied'])

    def test_existing_cache_metadata_is_never_silently_repaired(self):
        self.setup_kind();self.acquire()
        descriptor=self.root/'metadata'/evidence((self.repo/'artifact.json').read_bytes())['sha256']
        descriptor.chmod(0o644);descriptor.write_bytes(b'broken')
        with self.assertRaisesRegex(ValueError,'size'):self.prepare()
        self.assertEqual(descriptor.read_bytes(),b'broken')

    def test_unknown_policy_version_and_native_category_fail_closed(self):
        self.setup_kind()
        self.policy_file.write_bytes(raw(cache.record('mojt-local-source-policy-v2',self.policy['description'])))
        with self.assertRaisesRegex(ValueError,'unsupported'):self.prepare()
        self.assertFalse(self.root.exists())

    def test_insufficient_space_and_unmanaged_cache_are_not_modified(self):
        self.setup_kind();plan=self.prepare()
        with mock.patch.object(cache.shutil,'disk_usage',return_value=shutil._ntuple_diskusage(100,100,0)):
            with self.assertRaisesRegex(ValueError,'space'):self.acquire(plan)
        self.assertEqual(list((self.root/'records').iterdir()),[])
        shutil.rmtree(self.root);self.root.mkdir();(self.root/'unrelated').write_text('keep')
        with self.assertRaises(FileNotFoundError):self.prepare()
        self.assertEqual((self.root/'unrelated').read_text(),'keep')


if __name__=='__main__':unittest.main()
