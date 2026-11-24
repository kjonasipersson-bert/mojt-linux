# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real TLS, Ed25519, delivered MPM and native cache; no public release needed."""
import base64
import contextlib
import copy
import functools
import http.server
import io
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import threading
import unittest
from unittest import mock

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
import mbt_cli
import mpm_https as https
import mpm_sources as sources
import mpm_base_source as base_source
import mpm_sources_cli as cli
import test_mpm_base as fixture


@unittest.skipUnless(shutil.which('openssl') and shutil.which('zstd'),'requires OpenSSL 3+ and zstd')
class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.Fixture();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.work=self.f.work;self.web=self.work/'web';self.web.mkdir()
        self.root=self.work/'sources';self.cache=self.work/'cache'
        self.key=self.work/'publisher.key'
        self.command(['openssl','genpkey','-algorithm','ED25519','-out',str(self.key)])
        self.key.chmod(0o600)
        self.cert=self.work/'localhost.pem';tls_key=self.work/'localhost.key'
        self.command(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
            '-keyout',str(tls_key),'-out',str(self.cert),'-subj','/CN=localhost',
            '-addext','subjectAltName=DNS:localhost'])
        owner=self
        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                owner.requests.append(self.path)
                if self.path=='/redirect':
                    self.send_response(302);self.send_header('Location','http://localhost/unsafe');self.end_headers();return
                super().do_GET()
        self.requests=[]
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(self.web)))
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(self.cert,tls_key)
        self.server.socket=context.wrap_socket(self.server.socket,server_side=True)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        def stop():self.server.shutdown();self.server.server_close();thread.join()
        self.addCleanup(stop)
        self.url='https://localhost:'+str(self.server.server_port)
        patch=mock.patch.dict(os.environ,SSL_CERT_FILE=str(self.cert));patch.start();self.addCleanup(patch.stop)
        self.publisher=mbt_cli.helper('repo')
        self.proof,self.public=self.publish(sequence=1)

    def command(self,args):
        r=subprocess.run(args,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr);return r.stdout

    def publish(self,sequence,version='0.2.1'):
        archive,body=self.f.package(version=version)
        shutil.copyfile(archive,self.web/archive.name)
        config=self.work/('repo-'+str(sequence)+'.toml')
        config.write_text('format = 1\nname = "mojt-base"\nchannel = "stable"\nsequence = '+str(sequence)+
            '\nkey = '+json.dumps(str(self.key))+'\n[[packages]]\narchive = '+json.dumps(str(archive))+
            '\nurl = '+json.dumps(self.url+'/'+archive.name)+'\n')
        output=self.work/('publication-'+str(sequence))
        result=self.publisher.prepare(config,output)
        proof=json.loads((output/'stable.json').read_bytes())
        (self.web/'stable.json').write_bytes((output/'stable.json').read_bytes())
        self.body=body;self.archive=archive;self.config=config
        return proof,(output/'public.pem').read_text()

    def run_cli(self,*args):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main('source',list(args)+['--root',str(self.root),'-y']),0)
        return json.loads(out.getvalue())

    def add(self):
        key=self.work/'public.pem';key.write_text(self.public)
        return self.run_cli('add','mojt-base','--url',self.url+'/stable.json','--key-file',str(key))

    def update(self):return self.run_cli('update','mojt-base')

    def fetch(self):
        identifier,checksum,snapshot=base_source.resolve(self.root,'mojt-base')
        args=dict(kind='base',archive_sha256=checksum,snapshot=snapshot)
        plan=sources.prepare_fetch(self.root,self.cache,'mojt-base',identifier,**args)
        return sources.fetch(self.root,self.cache,'mojt-base',identifier,plan,**args)

    def test_joined_publisher_refresh_resolve_fetch_and_offline_reuse(self):
        previous=os.umask(0o002)
        try:self.assertTrue(self.add()['changed'])
        finally:os.umask(previous)
        self.assertEqual(self.requests,[])
        self.assertTrue(self.update()['changed']);self.assertEqual(self.requests,['/stable.json'])
        self.assertEqual(base_source.resolve(self.root,'mojt-base')[0],self.body['id'])
        with self.assertRaises(ValueError):base_source.resolve(self.root,'mojt-base',selector='mojt@=99.0-r1')
        result=self.fetch();self.assertTrue(result['copied'])
        self.assertEqual(Path(result['archive']).read_bytes(),self.archive.read_bytes())
        before=list(self.requests)
        with mock.patch.object(https,'chunks',side_effect=AssertionError('offline must use cache')):
            self.assertFalse(self.fetch()['changed'])
            self.assertEqual(sources.inspect(self.root,'mojt-base')['catalog']['area'],'base')
        self.assertEqual(self.requests,before)
        self.assertNotIn('PRIVATE KEY',json.dumps(self.proof))
        self.assertFalse((self.work/'publication-1'/'publisher.key').exists())

    def test_real_mbt_entrypoint_keeps_signing_key_outside_frozen_resources(self):
        output=self.work/'via-mbt'
        self.command([sys.executable,'-I','-B',str(REPO/'tools/mbt'),'repo','prepare',
            '--config',str(self.config),'--output',str(output)])
        proof=json.loads((output/'stable.json').read_bytes())
        self.assertEqual(https.verify(proof,self.public),self.proof['repository'])
        self.assertEqual(set(p.name for p in output.iterdir()),{'stable.json','public.pem','publication.json'})

    def test_tamper_wrong_key_and_bad_archive_preserve_accepted_state(self):
        self.add();self.update();before=sources.current(self.root,'mojt-base')
        bad=copy.deepcopy(self.proof);bad['repository']['sequence']=2
        (self.web/'stable.json').write_bytes(sources.encoded(bad))
        with self.assertRaisesRegex(ValueError,'signature'):self.update()
        self.assertEqual(sources.current(self.root,'mojt-base'),before)
        other=self.work/'other.key';self.command(['openssl','genpkey','-algorithm','ED25519','-out',str(other)])
        other_public=self.command(['openssl','pkey','-in',str(other),'-pubout'])
        with self.assertRaisesRegex(ValueError,'signature'):https.verify(self.proof,other_public)
        (self.web/self.archive.name).write_bytes(b'bad')
        with self.assertRaises(ValueError):self.fetch()
        self.assertEqual(list((self.cache/'archives/sha256').iterdir()),[])

    def test_rollback_same_sequence_and_cross_channel_refused(self):
        self.add();self.update();old=sources.current(self.root,'mojt-base')['description']['snapshot']
        newer,_=self.publish(2,version='0.2.2');self.update()
        (self.web/'stable.json').write_bytes(sources.encoded(self.proof))
        with self.assertRaisesRegex(ValueError,'rollback'):self.update()
        modified=copy.deepcopy(newer);modified['signature']=self.proof['signature']
        # A valid prior proof with a changed sequence must fail authentication.
        with self.assertRaisesRegex(ValueError,'signature'):https.verify(modified,self.public)
        self.assertEqual(base_source.resolve(self.root,'mojt-base',snapshot=old)[0],self.proof['repository']['catalog']['candidates'][0]['artifact'])
        source,policy=sources.https_source('mojt-base',self.url+'/stable.json',self.public,channel='preview')
        with self.assertRaisesRegex(ValueError,'channel'):https.repository(self.proof,source,policy)

    def test_signed_withdrawal_retains_deliberately_pinned_snapshot(self):
        self.add();self.update();old=sources.current(self.root,'mojt-base')['description']['snapshot']
        config=self.work/'withdraw.toml'
        config.write_text('format=1\nname="mojt-base"\nchannel="stable"\nsequence=2\nkey='+json.dumps(str(self.key))+'\npackages=[]\n')
        output=self.work/'withdraw';self.publisher.prepare(config,output)
        (self.web/'stable.json').write_bytes((output/'stable.json').read_bytes());self.update()
        with self.assertRaisesRegex(ValueError,'no eligible'):base_source.resolve(self.root,'mojt-base')
        self.assertEqual(base_source.resolve(self.root,'mojt-base',snapshot=old)[0],self.body['id'])

    def test_tls_url_redirect_and_response_bounds(self):
        for url in ('http://example/a','https://user:pass@example/a','https://example/a/../b','https://example/%2e/a'):
            with self.subTest(url=url),self.assertRaises(ValueError):https.read(url)
        with self.assertRaisesRegex(ValueError,'redirect'):https.read(self.url+'/redirect')
        with self.assertRaisesRegex(ValueError,'limit'):https.read(self.url+'/stable.json',1)
        with mock.patch.dict(os.environ,SSL_CERT_FILE='/absent'):
            with self.assertRaises(Exception) as caught:https.read(self.url+'/stable.json')
            self.assertIn('CERTIFICATE_VERIFY_FAILED',str(caught.exception))

    def test_valid_same_sequence_replacement_and_key_reconfiguration(self):
        self.add();self.update();old=sources.current(self.root,'mojt-base')['description']['snapshot']
        repo=copy.deepcopy(self.proof['repository']);repo['catalog']['candidates'][0]['stability']='preview'
        message=self.work/'message';signature=self.work/'signature'
        message.write_bytes(https.message(repo))
        self.command(['openssl','pkeyutl','-sign','-rawin','-inkey',str(self.key),'-in',str(message),'-out',str(signature)])
        changed=dict(format=https.SIGNED,repository=repo,signature=base64.b64encode(signature.read_bytes()).decode('ascii'))
        (self.web/'stable.json').write_bytes(sources.encoded(changed))
        with self.assertRaisesRegex(ValueError,'sequence'):self.update()
        source,policy=sources.https_source('mojt-base',self.url+'/different.json',self.public)
        path=self.work/'replacement.json';path.write_bytes(sources.encoded(policy))
        args=dict(source=source,policy_file=path,replace=True)
        sources.add(self.root,'mojt-base',sources.prepare_add(self.root,'mojt-base',**args),**args)
        with self.assertRaisesRegex(ValueError,'binding'):base_source.resolve(self.root,'mojt-base',snapshot=old)

    @unittest.skipUnless(os.geteuid()==0,'real Base import requires administrator')
    def test_base_cli_resolves_and_imports_into_offline_target(self):
        from mpm_base_cli import main
        self.add();self.update()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['install','mojt@0.2','--repo','mojt-base','--disk-root',str(self.f.root),
                '--sources-root',str(self.root),'--cache-root',str(self.cache),'--content-only','-y']),0)
        self.assertTrue(fixture.base.realization_path(self.f.root,self.body['id']).is_dir())

    def test_installed_crypto_helper_never_falls_back_to_path(self):
        profile=self.work/'installed';(profile/'tools').mkdir(parents=True)
        (profile/'mpm-runtime.json').write_text('{}')
        with mock.patch.object(https,'__file__',str(profile/'tools/mpm_https.py')):
            with self.assertRaisesRegex(ValueError,'retained OpenSSL'):https.verify(self.proof,self.public)
            (profile/'libexec/mpm/bin').mkdir(parents=True)
            (profile/'libexec/mpm/bin/openssl').symlink_to(shutil.which('openssl'))
            self.assertEqual(https.verify(self.proof,self.public),self.proof['repository'])

    def test_saved_series_stays_within_major_and_exact_pin_survives_withdrawal(self):
        import mpm_base_request as requests
        self.add();self.update()
        request,before=requests.choose(self.root,selector='mojt@0')
        self.assertIsNone(before)
        self.assertTrue(requests.save(self.root,request,before,'a'*32))
        self.publish(2,'1.0.0');self.update()
        with self.assertRaisesRegex(ValueError,'no eligible'):
            requests.choose(self.root,installation='a'*32)
        # Restore a catalog containing a newer release within the saved series.
        self.publish(3,'0.3.0');self.update()
        updated,previous=requests.choose(self.root,installation='a'*32)
        self.assertEqual(updated['selection']['candidate']['upstream_version'],'0.3.0')
        self.assertTrue(requests.save(self.root,updated,previous,'a'*32))
        self.publish(4,'0.2.2');self.update()
        with self.assertRaisesRegex(ValueError,'downgrade'):
            requests.choose(self.root,installation='a'*32)
        pinned,previous=requests.choose(self.root,selector='mojt@=0.2.2-r1')
        requests.save(self.root,pinned,previous,'a'*32)
        self.publish(5,'1.0.0');self.update()
        kept,_=requests.choose(self.root,installation='a'*32)
        self.assertEqual(kept,pinned)
        self.assertEqual(requests.read(self.root)['description']['selection'],pinned['selection'])

    def test_missing_wish_explicit_latest_and_lost_update_guard(self):
        import mpm_base_request as requests
        self.add();self.update()
        with self.assertRaisesRegex(ValueError,'choose a Base update series'):
            requests.choose(self.root)
        latest,previous=requests.choose(self.root,selector='mojt')
        requests.save(self.root,latest,previous,'a'*32)
        self.publish(2,'1.0.0');self.update()
        updated,previous=requests.choose(self.root,installation='a'*32)
        self.assertEqual(updated['selection']['candidate']['upstream_version'],'1.0.0')
        with self.assertRaisesRegex(ValueError,'another installation'):
            requests.choose(self.root,installation='b'*32)
        requests.save(self.root,updated,previous,'a'*32)
        with self.assertRaisesRegex(ValueError,'changed during'):
            requests.save(self.root,latest,previous,'a'*32)

    def test_area_frontend_rejects_wrong_catalog_and_old_global_commands(self):
        import mpm_cli
        self.add()
        with contextlib.redirect_stderr(io.StringIO()),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mpm_cli.main(['kernel','update','--root',str(self.root),'-y']),1)
            for area in ('source','cache','catalog'):
                self.assertEqual(mpm_cli.main([area,'--help']),1)
        self.assertIsNone(sources.current(self.root,'mojt-base')['description']['snapshot'])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mpm_cli.main(['base','update','--root',str(self.root),'-y']),0)
        self.assertIsNotNone(sources.current(self.root,'mojt-base')['description']['snapshot'])


if __name__=='__main__':unittest.main()
