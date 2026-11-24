# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Bounded HTTPS transport and OpenSSL Ed25519 repository authentication."""
import base64
import hashlib
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import urllib.parse
import urllib.request

import mojt_artifact as artifact
import mpm_native_io as io

POLICY='mojt-https-source-policy-v1'
SIGNED='mojt-signed-repository-v1'
REPOSITORY='mojt-native-repository-v1'
DOMAIN=b'Mojt native repository v1\n'
MAX_METADATA=artifact.MAX_METADATA
# RFC 8410 SubjectPublicKeyInfo: Ed25519 OID and one 32-byte public key.
ED25519_SPKI=bytes.fromhex('302a300506032b6570032100')
require=artifact.require


def url(value):
    require(type(value) is str and 0<len(value)<=4096 and value.isascii()
        and not any(c.isspace() or ord(c)<32 or ord(c)==127 for c in value)
        and '\\' not in value,'invalid repository HTTPS URL')
    parsed=urllib.parse.urlsplit(value)
    require(parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password
        and not parsed.query and not parsed.fragment and parsed.path.startswith('/')
        and '%' not in parsed.path and all(p not in ('.','..') for p in parsed.path.split('/')),
        'repository locations require plain HTTPS URLs without credentials, query or traversal')
    require(parsed.port is None or 1<=parsed.port<=65535,'invalid HTTPS port')
    return value


class Redirect(urllib.request.HTTPRedirectHandler):
    max_redirections=5
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        # CDN signed query strings are allowed only on HTTPS redirects. They
        # are not persisted as source identities or accepted as initial URLs.
        parsed=urllib.parse.urlsplit(newurl)
        require(parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password
            and not parsed.fragment and '\\' not in newurl,'unsafe HTTPS redirect')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def chunks(location, maximum):
    url(location)
    opener=urllib.request.build_opener(Redirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    request=urllib.request.Request(location,headers={'User-Agent':'Mojt-MPM/1','Accept-Encoding':'identity'})
    with opener.open(request,timeout=30) as response:
        require(response.status==200,'unexpected HTTPS response')
        require(response.headers.get('Content-Encoding','identity')=='identity','encoded repository response refused')
        length=response.headers.get('Content-Length')
        if length is not None:require(0<=int(length)<=maximum,'HTTPS response exceeds byte limit')
        count=0
        while data:=response.read(min(128*1024,maximum-count+1)):
            count+=len(data);require(count<=maximum,'HTTPS response exceeds byte limit')
            yield data
        if length is not None:require(count==int(length),'truncated HTTPS response')


def read(location, maximum=MAX_METADATA):return b''.join(chunks(location,maximum))


def public_key(value):
    require(type(value) is str and len(value)<=512,'bounded Ed25519 public PEM key required')
    lines=value.strip().splitlines()
    require(len(lines)>=3 and lines[0]=='-----BEGIN PUBLIC KEY-----'
        and lines[-1]=='-----END PUBLIC KEY-----','public PEM key required')
    try:der=base64.b64decode(''.join(lines[1:-1]),validate=True)
    except ValueError as error:raise ValueError('invalid public key encoding') from error
    require(len(der)==44 and der.startswith(ED25519_SPKI),'repository key must be Ed25519')
    return value


def openssl():
    profile=Path(__file__).resolve().parents[1]
    if (profile/'mpm-runtime.json').is_file():
        binary=profile/'libexec/mpm/bin/openssl'
        require(binary.is_file() and os.access(binary,os.X_OK),
            'selected System has no retained OpenSSL helper; use a repository-enabled System')
        return str(binary)
    binary=shutil.which('openssl')
    require(binary is not None,'OpenSSL 3+ is required for repository signatures')
    return binary


def environment():
    result={key:value for key,value in os.environ.items()
        if not key.startswith(('LD_','DYLD_','OPENSSL_'))}
    result['LC_ALL']='C';result['OPENSSL_CONF']=os.devnull
    return result


def policy(source,record):
    d=record['description'];artifact.fields(d,('name','provider','channel','url','public_key','max_archive','max_expanded'))
    s=source['description'];artifact.fields(s,('name','provider','channel','location','trust'))
    require(d['provider']==s['provider']=='native' and s['location']==dict(kind='https-repository',url=url(d['url']))
        and s['trust']==dict(kind='ed25519',policy=record['id'])
        and (s['name'],s['channel'])==(d['name'],d['channel']),'HTTPS source/policy binding differs')
    public_key(d['public_key'])
    for key in ('max_archive','max_expanded'):
        require(type(d[key]) is int and 0<d[key]<=2*artifact.MAX_CONTENT,'invalid HTTPS acquisition limit')
    return d['url']


def message(repository):return DOMAIN+artifact.canonical(repository)


def verify(proof,key):
    artifact.fields(proof,('format','repository','signature'))
    require(proof['format']==SIGNED,'unsupported signed repository')
    public_key(key)
    try:signature=base64.b64decode(proof['signature'],validate=True)
    except (ValueError,TypeError) as error:raise ValueError('invalid repository signature encoding') from error
    require(len(signature)==64,'Ed25519 signature must contain 64 bytes')
    raw=message(proof['repository']);require(len(raw)<=MAX_METADATA,'repository metadata exceeds limit')
    binary=openssl()
    def check():
        with tempfile.TemporaryDirectory(prefix='mojt-repository-verify-') as tmp:
            work=Path(tmp);(work/'key.pem').write_text(key);(work/'message').write_bytes(raw);(work/'signature').write_bytes(signature)
            try:
                result=subprocess.run([binary,'pkeyutl','-verify','-rawin','-pubin','-inkey',str(work/'key.pem'),
                    '-in',str(work/'message'),'-sigfile',str(work/'signature')],stdin=subprocess.DEVNULL,
                    capture_output=True,env=environment(),timeout=15)
            except subprocess.SubprocessError as error:
                raise ValueError('OpenSSL repository verification did not complete') from error
            require(result.returncode==0,'repository signature verification failed')
        return True
    # Reuse a checked signature only inside an existing operation context;
    # independently supplied metadata still crosses the authentication boundary.
    io.preparation_cached(('repository-signature',hashlib.sha256(raw).hexdigest(),key,proof['signature']),
        [Path(binary).resolve()],check)
    return proof['repository']


def repository(proof,source,policy_record):
    d=verify(proof,policy_record['description']['public_key'])
    artifact.fields(d,('format','name','channel','sequence','catalog','acquisition','descriptors'))
    require(d['format']==REPOSITORY and (d['name'],d['channel'])==
        (source['description']['name'],source['description']['channel']),'repository source/channel differs')
    require(type(d['sequence']) is int and 0<d['sequence']<2**63,'invalid repository sequence')
    require(type(d['descriptors']) is dict and len(d['descriptors'])<=64,'repository descriptor limit')
    return d
