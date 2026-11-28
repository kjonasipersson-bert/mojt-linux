#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare a signed Base catalog; publication uses ordinary Git and gh commands."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import subprocess
import tempfile
import tomllib

import mojt_artifact as artifact
import mpm_https as https
import mpm_sources as sources
from mpm_selection import Catalog


def evidence(raw):return dict(sha256=hashlib.sha256(raw).hexdigest(),size=len(raw))


def prepare(config,output):
    config=Path(config).resolve(strict=True)
    artifact.require(config.stat().st_size<=https.MAX_METADATA,'repository configuration exceeds limit')
    settings=tomllib.loads(config.read_text())
    artifact.fields(settings,('format','name','channel','sequence','key','packages'),('area',))
    artifact.require(settings['format']==1,'unsupported repository configuration')
    area=settings.get('area','base')
    artifact.require(area in ('base','ports'),'unsupported repository area')
    sources.cache.model.token(settings['name']);sources.cache.model.token(settings['channel'])
    sequence=settings['sequence']
    artifact.require(type(sequence) is int and 0<sequence<2**63,'invalid repository sequence')
    packages=settings['packages']
    artifact.require(type(packages) is list and len(packages)<=64,'repository accepts at most 64 packages')
    key=(config.parent/settings['key']).resolve(strict=True);info=key.stat()
    artifact.require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.geteuid()
        and not info.st_mode&0o077,'signing key must be an executor-owned private regular file (0600)')
    output=Path(output).absolute()
    artifact.require(not os.path.lexists(output),'repository output already exists; use a new directory')
    catalog=dict(format='mpm-release-catalog-v1',area=area,name='mojt' if area=='base' else 'ports',channel=settings['channel'],
        platform='x86_64-linux',sources={settings['name']:dict(backend='native',identity=dict(repository=settings['name']))},candidates=[])
    offers=[];descriptors={};assets=[];releases=set()
    for row in packages:
        artifact.fields(row,('archive','url'))
        location=https.url(row['url']);path=(config.parent/row['archive']).resolve(strict=True)
        before=path.stat();artifact.require(stat.S_ISREG(before.st_mode) and 0<before.st_size<=1024**3,'Base archive exceeds repository limit')
        body=artifact.verify(path,max_uncompressed=4*1024**3)
        artifact.require(body['platform']=='x86_64-linux' and
                         (body['kind']=='port' if area=='ports' else (body['kind'],body['name'])==('base','mojt')),
                         'archive belongs to another repository area or platform')
        if area == 'ports':
            from mpm_ports_native import descriptor
            descriptor(body)
        version=body['version'];release=version['release_id']
        key_release=(body['name'],release)
        artifact.require(key_release not in releases,'duplicate release; keep one exact build per release')
        releases.add(key_release)
        with path.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
        after=path.stat()
        artifact.require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'archive changed during repository preparation')
        descriptor=sources.encoded(body);name='descriptors/'+body['id'].split(':')[1]+'.json'
        descriptors[name]=body
        offers.append(dict(reference=dict(provider='native',artifact=body['id']),descriptor=dict(path=name,**evidence(descriptor)),
            archives=[dict(sha256=checksum,size=after.st_size,paths=[location])]))
        catalog['candidates'].append(dict(name=body['name'],release_id=release,upstream_version=version['upstream'],
            version_scheme=version['scheme'],revision_scheme='mojt-r-v1' if version['revision'] is not None else None,
            package_revision=version['revision'],stability='stable',source=settings['name'],artifact=body['id'],
            integrity=dict(sha256=checksum),compatibility='unknown'))
        assets.append(dict(file=str(path),url=location,sha256=checksum,size=after.st_size))
    catalog['candidates'].sort(key=lambda c:c['release_id'])
    Catalog.from_dict(catalog)
    offers.sort(key=lambda o:sources.cache.model.canonical(o['reference']))
    mapping=sources.record('mojt-acquisition-map-v1',dict(catalog_sha256=sources.digest(sources.encoded(catalog)),offers=offers))
    repo=dict(format=https.REPOSITORY,name=settings['name'],channel=settings['channel'],sequence=sequence,
              catalog=catalog,acquisition=mapping,descriptors=descriptors)
    binary=https.openssl()
    # OpenSSL owns key parsing and passphrase interaction. Private key bytes are
    # never copied into output, frozen MBT resources, or publication metadata.
    public=subprocess.run([binary,'pkey','-in',str(key),'-pubout'],check=True,stdout=subprocess.PIPE,env=https.environment()).stdout.decode('ascii')
    https.public_key(public)
    with tempfile.TemporaryDirectory(prefix='mojt-repository-sign-') as tmp:
        work=Path(tmp);(work/'message').write_bytes(https.message(repo))
        subprocess.run([binary,'pkeyutl','-sign','-rawin','-inkey',str(key),'-in',str(work/'message'),
            '-out',str(work/'signature')],check=True,env=https.environment())
        proof=dict(format=https.SIGNED,repository=repo,signature=base64.b64encode((work/'signature').read_bytes()).decode('ascii'))
    https.verify(proof,public)
    raw=sources.encoded(proof);artifact.require(len(raw)<=https.MAX_METADATA,'signed repository exceeds byte limit')
    output.mkdir(mode=0o755,parents=True)
    (output/(settings['channel']+'.json')).write_bytes(raw)
    (output/'public.pem').write_text(public)
    publication=dict(format='mojt-repository-publication-v1',name=settings['name'],channel=settings['channel'],
        sequence=sequence,metadata=evidence(raw),assets=assets,
        public_key_sha256=hashlib.sha256(public.encode('ascii')).hexdigest())
    (output/'publication.json').write_bytes(sources.encoded(publication))
    return dict(output=str(output),metadata=str(output/(settings['channel']+'.json')),publication=publication)


def main(argv=None,*,prog=None):
    parser=argparse.ArgumentParser(prog=prog,description=__doc__)
    actions=parser.add_subparsers(dest='action',required=True)
    command=actions.add_parser('prepare')
    command.add_argument('--config',type=Path,default=Path('repository.toml'))
    command.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        print(json.dumps(prepare(args.config,args.output),indent=2));return 0
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError,artifact.tarfile.TarError) as error:
        print('mbt repo: '+str(error),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
