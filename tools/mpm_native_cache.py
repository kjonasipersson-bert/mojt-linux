# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Explicitly owner-trusted local native acquisition; cache, never installation."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import uuid

import mojt_artifact as artifact
import mpm_requests as model
import mpm_transaction as tx
from mpm_request_plan import record, reference
from mpm_selection import Catalog

MARKER = 'mojt-native-cache-v1'
POLICY = 'mojt-local-source-policy-v1'
PLAN = 'mojt-native-acquisition-plan-v1'
RECORD = 'mojt-cache-record-v1'
MAX_META = artifact.MAX_METADATA
require = model.require
fields = model.fields


def envelope(value, fmt):
    fields(value, ('format','id','description'))
    require(value['format'] == fmt and value == record(fmt,value['description']), 'unsupported/corrupt ' + fmt)
    return value['description']


def hex_sha(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}',value), 'invalid SHA256')
    return value


def size(value, maximum=2**63-1):
    require(type(value) is int and 0 <= value <= maximum, 'invalid byte bound')
    return value


def bound(raw, evidence, maximum=MAX_META):
    require(type(raw) is bytes and len(raw) == size(evidence['size'],maximum), 'input byte size differs')
    require(hashlib.sha256(raw).hexdigest() == hex_sha(evidence['sha256']), 'input SHA256 differs')
    return raw


@contextmanager
def confined(root, relative):
    """Walk an opened source root with no-follow descriptors, never symlink paths."""
    artifact.relative(relative)
    root = tx.protected_directory(root,label='Source')
    fd = os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        parts=relative.split('/')
        for part in parts[:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
            require(os.fstat(fd).st_uid in (0,os.geteuid()) and not os.fstat(fd).st_mode & 0o022,'unsafe source subdirectory')
        file_fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            info=os.fstat(file_fd)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid in (0,os.geteuid()) and not info.st_mode & 0o022,'unsafe source/cache file')
            with os.fdopen(file_fd,'rb',closefd=False) as stream:yield stream,info.st_size
        finally:os.close(file_fd)
    finally:os.close(fd)


def read_file(root, relative, maximum=MAX_META):
    with confined(root,relative) as (stream,length):
        require(length <= maximum,'metadata exceeds bound')
        raw=stream.read(maximum+1)
        require(len(raw)==length,'metadata changed while reading')
        return raw


def cache_root(path, *, write=False):
    root=tx.protected_directory(path,write=write,label='Cache')
    if root.exists() and set(p.name for p in root.iterdir()) - {'.lock'}:
        marker=artifact.parse_json(read_file(root,'cache.json'))
        require(marker==dict(format=MARKER),'unsupported cache format')
        for name in ('archives','archives/sha256','records','metadata','objects'):
            require((root/name).is_dir(),'incomplete cache')
            tx.protected_directory(root/name,label='Cache')
    return root


def inputs(cache, *, policy_file, source, snapshot, catalog_bytes, acquisition_bytes, ref, archive_sha256, kind):
    root=cache_root(cache)
    policy_file=Path(os.path.abspath(policy_file))
    policy_raw=read_file(policy_file.parent,policy_file.name)
    policy_record=artifact.parse_json(policy_raw);policy=envelope(policy_record,POLICY)
    fields(policy,('name','provider','channel','root','max_archive','max_expanded'))
    require(policy['provider']=='native','unsupported local policy provider')
    for key in ('name','channel'):model.token(policy[key])
    size(policy['max_archive'],artifact.MAX_CONTENT);size(policy['max_expanded'],2*artifact.MAX_CONTENT)
    require(policy['max_archive']>0 and policy['max_expanded']>0,'empty acquisition limits')
    src=envelope(source,'mojt-source-v1');fields(src,('name','provider','channel','location','trust'))
    fields(src['location'],('kind','path'));fields(src['trust'],('kind','policy'))
    require(src['provider']=='native' and src['location']['kind']=='local-directory' and src['trust']==dict(kind='explicit-local',policy=policy_record['id']),'source is not authorized by this protected local policy')
    require((src['name'],src['channel'],src['location']['path'])==(policy['name'],policy['channel'],policy['root']),'local source/policy binding differs')
    directory=Path(policy['root'])
    require(directory.is_absolute() and str(directory)==policy['root'],'noncanonical local source path')
    tx.protected_directory(directory,label='Source')
    snap=envelope(snapshot,'mojt-source-snapshot-v1')
    fields(snap,('source','catalog','acquisition','provider_snapshot','trust_policy'))
    require(snap['source']==source['id'] and snap['trust_policy']==policy_record['id'] and snap['provider_snapshot'] is None,'source snapshot binding differs')
    fields(snap['catalog'],('format','sha256','size'));fields(snap['acquisition'],('id','sha256','size'))
    bound(catalog_bytes,snap['catalog']);bound(acquisition_bytes,snap['acquisition'])
    require(snap['catalog']['format']=='mpm-release-catalog-v1','unsupported catalog acquisition format')
    catalog=Catalog.from_dict(artifact.parse_json(catalog_bytes))
    require(catalog.channel==src['channel'],'catalog/source channel differs')
    mapping=artifact.parse_json(acquisition_bytes);md=envelope(mapping,'mojt-acquisition-map-v1')
    fields(md,('catalog_sha256','offers'))
    require(mapping['id']==snap['acquisition']['id'] and md['catalog_sha256']==snap['catalog']['sha256'],'acquisition map binding differs')
    require(type(md['offers']) is list,'invalid offers')
    keys=[]
    for offer in md['offers']:
        reference(offer['reference']);keys.append(model.canonical(offer['reference']))
        if offer['reference']['provider']!='native':
            fields(offer,('reference','source_identity'));require(type(offer['source_identity']) is dict and offer['source_identity'],'missing provider binding');continue
        fields(offer,('reference','descriptor','archives'));fields(offer['descriptor'],('path','sha256','size'))
        artifact.relative(offer['descriptor']['path']);hex_sha(offer['descriptor']['sha256']);size(offer['descriptor']['size'],MAX_META)
        require(type(offer['archives']) is list and offer['archives'],'missing archive encodings')
        encodings=[]
        for encoding in offer['archives']:
            fields(encoding,('sha256','size','paths'));encodings.append(hex_sha(encoding['sha256']));size(encoding['size'])
            require(type(encoding['paths']) is list and encoding['paths'] and encoding['paths']==sorted(set(encoding['paths'])),'invalid mirror paths')
            for name in encoding['paths']:artifact.relative(name)
        require(encodings==sorted(set(encodings)),'duplicate/unordered encodings')
    require(keys==sorted(set(keys)),'duplicate/unordered offers')
    require(reference(ref)['provider']=='native' and kind in artifact.KINDS,'unsupported native acquisition target')
    offers=[o for o in md['offers'] if o['reference']==ref];require(len(offers)==1,'missing exact acquisition offer')
    offer=offers[0];encodings=[e for e in offer['archives'] if e['sha256']==archive_sha256]
    require(len(encodings)==1,'archive encoding not approved');encoding=encodings[0]
    size(encoding['size'],policy['max_archive'])
    cached_descriptor='metadata/'+offer['descriptor']['sha256']
    descriptor_raw=read_file(root,cached_descriptor) if os.path.lexists(root/cached_descriptor) else read_file(directory,offer['descriptor']['path'])
    bound(descriptor_raw,offer['descriptor']);body=artifact.parse_json(descriptor_raw);artifact.validate_descriptor(body)
    require(body['id']==ref['artifact'] and body['kind']==kind and catalog.area==('ports' if kind=='port' else kind),'artifact/category binding differs')
    candidates=[c for c in catalog.candidates if c.backend=='native' and c.artifact==body['id']]
    require(candidates,'artifact absent from accepted catalog')
    for c in candidates:
        require((c.name,c.release_id,c.upstream_version,c.version_scheme,c.package_revision,catalog.platform)==
                (body['name'],body['version']['release_id'],body['version']['upstream'],body['version']['scheme'],body['version']['revision'],body['platform']),'catalog/descriptor release differs')
        require(c.integrity==dict(sha256=c.integrity.get('sha256')) and c.integrity['sha256'] in {e['sha256'] for e in offer['archives']},'native catalog transport binding differs')
    require(sum(row.get('size',0) for row in body['files'])<=policy['max_expanded'],'declared content exceeds policy')
    binding=dict(artifact=body['id'],archive={k:encoding[k] for k in ('sha256','size')},source_snapshot=snapshot['id'],acquisition_map=mapping['id'],descriptor=body['id'],trust_policy=policy_record['id'])
    plan=record(PLAN,dict(cache=str(root),policy_file=str(policy_file),policy_raw_sha256=hashlib.sha256(policy_raw).hexdigest(),source=source['id'],kind=kind,binding=binding,descriptor_bytes=offer['descriptor'],archive_paths=encoding['paths'],max_expanded=policy['max_expanded']))
    objects=[source,snapshot,mapping,policy_record]
    raw=[descriptor_raw,catalog_bytes,acquisition_bytes]
    return root,plan,body,objects,raw


def prepare(cache, **kwargs):
    """Read metadata and a protected local trust policy; no cache writes/commands."""
    return inputs(cache,**kwargs)[1]


def stage_bytes(root, chunks, evidence):
    temporary=root/('.fetch-'+uuid.uuid4().hex)
    try:
        with temporary.open('xb') as out:
            digest=hashlib.sha256();count=0
            for chunk in chunks:
                count+=len(chunk);require(count<=evidence['size'],'copy exceeds approved size')
                digest.update(chunk);out.write(chunk)
            require(count==evidence['size'] and digest.hexdigest()==evidence['sha256'],'copied bytes differ')
            out.flush();os.fchmod(out.fileno(),0o444);os.fsync(out.fileno())
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True);raise


def retain_file(root, temporary, destination, *, sync=tx.sync_directory):
    try:
        os.link(temporary,destination,follow_symlinks=False)
        try:sync(destination.parent)
        except BaseException as error:raise tx.PublicationUncertain('verified cache bytes published; inspect '+str(destination)) from error
    finally:temporary.unlink(missing_ok=True)


def retain_bytes(root, relative, raw, *, sync=tx.sync_directory):
    evidence=dict(sha256=hashlib.sha256(raw).hexdigest(),size=len(raw));destination=root/relative
    if os.path.lexists(destination):bound(read_file(root,relative),evidence);return
    temporary=stage_bytes(root,[raw],evidence)
    retain_file(root,temporary,destination,sync=sync)


def acquire(cache, plan, *, sync=tx.sync_directory, **kwargs):
    """Verify exact metadata/policy again, acquire approved bytes and retain evidence."""
    expected=prepare(cache,**kwargs);require(plan==expected,'acquisition plan inputs changed')
    root=cache_root(cache,write=True);root.mkdir(mode=0o700,exist_ok=True)
    with tx.file_lock(root/'.lock'):
        if not (root/'cache.json').exists():
            require(set(p.name for p in root.iterdir())<={'.lock'},'unmanaged cache directory')
            for name in ('archives','archives/sha256','records','metadata','objects'):(root/name).mkdir(mode=0o755)
            raw=model.canonical(dict(format=MARKER))+b'\n'
            retain_bytes(root,'cache.json',raw,sync=sync);sync(root);sync(root.parent)
        root,current,body,objects,raws=inputs(root,**kwargs)
        require(current==plan,'late acquisition plan changed')
        d=envelope(plan,PLAN);binding=d['binding'];encoding=binding['archive']
        blob=root/'archives/sha256'/encoding['sha256']
        needed=(0 if os.path.lexists(blob) else encoding['size'])+sum(len(raw) for raw in raws)+MAX_META
        require(shutil.disk_usage(root).free>=needed,'insufficient cache space')
        temporary=None;copied=False
        try:
            if os.path.lexists(blob):
                with confined(root,str(blob.relative_to(root))) as (stream,length):
                    require(length==encoding['size'] and hashlib.file_digest(stream,'sha256').hexdigest()==encoding['sha256'],'cached archive bytes differ')
                verify_path=blob
            else:
                # Explicit first listed local mirror. A failed/unsafe input is
                # not permission to silently select a different transport.
                with confined(kwargs['source']['description']['location']['path'],d['archive_paths'][0]) as (stream,length):
                    require(length==encoding['size'],'archive size differs')
                    temporary=stage_bytes(root,iter(lambda:stream.read(128*1024),b''),encoding)
                verify_path=temporary
            verified=artifact.verify(verify_path,binding['artifact'],max_uncompressed=d['max_expanded'])
            require(verified==body,'embedded/external descriptor differs')
            require(prepare(root,**kwargs)==plan,'acquisition policy/metadata changed during verification')
            if temporary is not None:
                retain_file(root,temporary,blob,sync=sync);temporary=None;copied=True
            for raw in raws:retain_bytes(root,'metadata/'+hashlib.sha256(raw).hexdigest(),raw,sync=sync)
            for obj in objects:retain_bytes(root,'objects/'+obj['id'].split(':')[1]+'.json',model.canonical(obj)+b'\n',sync=sync)
            relative='records/'+model.digest(binding).split(':')[1]+'.json'
            if os.path.lexists(root/relative):
                receipt=artifact.parse_json(read_file(root,relative));rd=envelope(receipt,RECORD)
                fields(rd,tuple(binding)+('verified_utc',))
                require({k:rd[k] for k in binding}==binding,'cache observation binding differs')
                require(type(rd['verified_utc']) is str and datetime.fromisoformat(rd['verified_utc']).utcoffset()==timezone.utc.utcoffset(None),'invalid verification timestamp')
                changed=False
            else:
                receipt=record(RECORD,dict(binding,verified_utc=datetime.now(timezone.utc).isoformat()))
                retain_bytes(root,relative,model.canonical(receipt)+b'\n',sync=sync);changed=True
            return dict(changed=changed,copied=copied,archive=str(blob),record=receipt)
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
