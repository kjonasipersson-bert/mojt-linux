# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Content-only exact Base installation; never state preparation or boot selection."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import stat
import subprocess
import tarfile
import tempfile
import uuid

import mojt_artifact as artifact
import mpm_native_io as io
import mpm_transaction as tx

STORE = 'mojt-artifact-store-v1'
RECEIPT = 'mojt-install-receipt-v1'
REALIZATION = 'mojt-base-realization-v1'
PLAN = 'mojt-base-install-plan-v1'
MAX_ROOTFS = artifact.MAX_CONTENT
MANAGER_FILES=('mpm_base.py','mpm_native_io.py','mojt-base-install','mojt_native_image.py','mojt_artifact.py','mpm_transaction.py')
require = io.require


def record(fmt, description):
    value = dict(format=fmt, description=description)
    return dict(value, id=artifact.digest(value))


def envelope(value, fmt):
    artifact.fields(value, ('format','id','description'))
    require(value == record(fmt, value['description']), 'unsupported/corrupt '+fmt)
    return value['description']


def read(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= artifact.MAX_METADATA,
                'unsafe/unbounded Base metadata')
        require(info.st_uid in (0,os.geteuid()) and not info.st_mode & 0o022, 'unprotected Base metadata')
        data = stream.read(artifact.MAX_METADATA+1)
    require(not path.is_symlink() and len(data) <= artifact.MAX_METADATA, 'linked/unbounded Base metadata')
    return artifact.parse_json(data)


def target(value, *, write=False):
    root = tx.protected_directory(value, write=write, label='Base target')
    if write:require(root.is_dir(), 'Base target must already exist; target creation belongs to bootstrap')
    for relative in ('artifacts','artifacts/base','artifacts/base/installed','realizations','realizations/base'):
        path = root/relative
        tx.protected_directory(path, write=write, label='Base storage')
    return root


def store_info(root):
    store = root/'artifacts'
    if not store.exists():return None
    require(set(p.name for p in store.iterdir()) <= {'store.json','.lock',*artifact.KINDS}, 'unknown artifact store entries')
    require((store/'store.json').is_file(), 'incomplete artifact store; inspect before retry')
    d = envelope(read(store/'store.json'), STORE)
    artifact.fields(d, ('installation','layout'))
    require(type(d['installation']) is str and re.fullmatch('[0-9a-f]{32}',d['installation'])
            and d['layout']=='kind-id-v1', 'unsupported artifact store identity/layout')
    for path in (store/'.lock',):
        tx.check_lock_file(path,shared=True)
    if (store/'base').exists():
        require({p.name for p in (store/'base').iterdir()}=={'installed'}, 'incomplete/unmanaged Base store')
        io.directory(store/'base/installed')
    return d


@contextmanager
def locked(root):
    target(root,write=True)
    with tx.file_lock(root/'.artifact-store.lock'):
        with _locked_store(root) as info:yield info


@contextmanager
def _locked_store(root):
    target(root, write=True)
    store=root/'artifacts'
    if store.exists():store_info(root)
    else:
        stage=Path(tempfile.mkdtemp(prefix='.artifacts-init-',dir=root))
        try:
            io.write_json(stage/'store.json',record(STORE,dict(installation=uuid.uuid4().hex,layout='kind-id-v1')))
            with (stage/'.lock').open('xb') as stream:
                os.fchmod(stream.fileno(),0o600);os.fsync(stream.fileno())
            (stage/'base').mkdir(mode=0o755);(stage/'base/installed').mkdir(mode=0o755)
            io.sync_directory(stage/'base/installed');io.sync_directory(stage/'base')
            stage.chmod(0o755);io.sync_directory(stage)
            require(not os.path.lexists(store), "artifact store appeared during initialization")
            tx.publish(stage,store)
        finally:io.clean_stage(stage)
    with tx.file_lock(store/'.lock',create=False):
        info=store_info(root)
        (store/'base').mkdir(exist_ok=True,mode=0o755)
        (store/'base/installed').mkdir(exist_ok=True,mode=0o755)
        (root/'realizations').mkdir(exist_ok=True,mode=0o755)
        (root/'realizations/base').mkdir(exist_ok=True,mode=0o755)
        target(root,write=True)
        io.sync_directory(store/'base');io.sync_directory(store)
        io.sync_directory(root/'realizations');io.sync_directory(root)
        yield info


def acceptable(body):
    artifact.validate_descriptor(body)
    require(body['kind']=='base' and body['name']=='mojt', 'requires a complete Mojt Base artifact')
    require(body['platform']==os.uname().machine+'-linux', 'Base platform differs from target architecture')
    require(not body['dependencies'] and not body['requirements'], 'unsupported Base dependencies/requirements')
    require(all(r['type'] in ('file','directory') for r in body['files']), 'Base wrapper must contain only regular files/directories')
    require(all(len(r['path'].split('/'))<=64 and len(os.fsencode(r['path']))<=4096 for r in body['files']), 'Base wrapper path exceeds limits')
    require(body['metadata'].get('base_release')==body['version']['upstream'], 'Base release metadata differs')


def manager():
    return dict(provider='mojt-manager-code',identity=dict(files={name:artifact.file_sha(Path(__file__).with_name(name)) for name in MANAGER_FILES}))


def validate_manager(value):
    artifact.fields(value, ('provider','identity'))
    artifact.fields(value['identity'], ('files',))
    require(value['provider']=='mojt-manager-code' and set(value['identity']['files'])==set(MANAGER_FILES), 'unsupported Base manager reference')
    for checksum in value['identity']['files'].values():
        require(type(checksum) is str and re.fullmatch('[0-9a-f]{64}',checksum), 'invalid manager code digest')


def object_path(root, identifier):return root/'artifacts/base/installed'/io.identifier(identifier)

def realization_path(root, identifier):return root/'realizations/base'/io.identifier(identifier)


def object_record(root, identifier, *, verify=False):
    info=store_info(root);require(info is not None, 'missing Base store')
    path=object_path(root,identifier)
    tx.protected_directory(path,label='Base object')
    require(stat.S_IMODE(io.directory(path).st_mode)==0o555, 'Base object must be sealed')
    body=read(path/'artifact.json');acceptable(body)
    require(body['id']==identifier, 'stored Base artifact differs')
    receipt=read(path/'installed.json');d=envelope(receipt, RECEIPT)
    artifact.fields(d,('installation','kind','artifact','archive','representation','dependencies','trust','installed_utc','uid','manager'),('acquisition',))
    require(d['installation']==info['installation'] and d['kind']=='base' and d['artifact']==identifier
            and d['representation']=='readonly-tree-v1' and d['dependencies']==body['dependencies'], 'Base install receipt differs')
    artifact.fields(d['archive'],('sha256','size'))
    require(type(d['archive']['sha256']) is str and re.fullmatch('[0-9a-f]{64}',d['archive']['sha256'])
            and type(d['archive']['size']) is int and 0<=d['archive']['size']<=io.MAX_ARCHIVE, 'invalid Base archive evidence')
    require(type(d['uid']) is int and d['uid']==path.stat().st_uid and type(d['installed_utc']) is str
            and datetime.fromisoformat(d['installed_utc'].replace('Z','+00:00')).utcoffset()==timezone.utc.utcoffset(None), 'invalid Base installer/time')
    require(d['trust']==io.acquisition_trust(d.get('acquisition'),identifier,d['archive']['sha256'],d['archive']['size']), 'Base trust/origin mismatch')
    validate_manager(d['manager'])
    for name in ('artifact.json','installed.json','archive.tar.zst'):
        file=io.regular(path/name)
        require(file.st_uid==path.stat().st_uid and stat.S_IMODE(file.st_mode)==0o444, 'unsafe Base object metadata')
    if verify:
        require(artifact.file_sha(path/'archive.tar.zst')==d['archive']['sha256'] and (path/'archive.tar.zst').stat().st_size==d['archive']['size'], 'retained Base archive damaged')
        require(artifact.verify(path/'archive.tar.zst',identifier)==body, 'retained Base descriptor damaged')
        expected={'artifact.json','installed.json','archive.tar.zst',*(r['path'] for r in body['files'])}
        found={p.relative_to(path).as_posix() for p in path.rglob('*')}
        require(found==expected, 'Base wrapper inventory differs')
        for row in body['files']:
            entry=path/row['path'];file=io.directory(entry) if row['type']=='directory' else io.regular(entry)
            require(not entry.is_symlink() and file.st_uid==path.stat().st_uid and stat.S_IMODE(file.st_mode)==io.stored_mode(row), 'Base wrapper metadata differs')
            if row['type']=='file':require(file.st_size==row['size'] and artifact.file_sha(entry)==row['sha256'], 'Base wrapper content damaged')
    return body,receipt


def rootfs_inventory(root):
    # Reuse the already reviewed Base inventory, including links, numeric owners,
    # modes, xattrs/ACLs and exact hardlink relationships. It never follows links.
    from mojt_native_image import base_inventory
    return artifact.digest(base_inventory(root))


def realization(root, identifier, receipt, *, verify=False):
    path=realization_path(root,identifier)
    if not os.path.lexists(path):return None
    tx.protected_directory(path,label='Base realization')
    require(set(p.name for p in path.iterdir())=={'rootfs','realization.json'}, 'incomplete/unmanaged Base realization')
    require(stat.S_IMODE(io.directory(path).st_mode)==0o555,'Base realization must be sealed')
    io.directory(path/'rootfs')
    meta=io.regular(path/'realization.json')
    require(meta.st_uid==path.stat().st_uid and stat.S_IMODE(meta.st_mode)==0o444,'unsafe Base realization metadata')
    value=read(path/'realization.json');d=envelope(value,REALIZATION)
    artifact.fields(d,('installation','artifact','receipt','layout','rootfs_sha256','inventory','constructor','extractor'))
    require(d['installation']==receipt['description']['installation'] and d['artifact']==identifier and d['receipt']==receipt['id']
            and d['layout']=='base-rootfs-v1', 'Base realization binding differs')
    io.identifier(d['inventory']);validate_manager(d['constructor'])
    require(type(d['rootfs_sha256']) is str and re.fullmatch('[0-9a-f]{64}',d['rootfs_sha256']), 'invalid inner Base digest')
    body=read(object_path(root,identifier)/'artifact.json')
    inner=[r for r in body['files'] if r['path']=='payload/rootfs.tar.zst']
    require(len(inner)==1 and d['rootfs_sha256']==inner[0]['sha256'], 'Base realization inner archive differs')
    artifact.fields(d['extractor'],('program','sha256'))
    require(type(d['extractor']['program']) is str and d['extractor']['program'].startswith('/')
            and len(os.fsencode(d['extractor']['program']))<=4096 and all(ord(c)>=32 and ord(c)!=127 for c in d['extractor']['program'])
            and type(d['extractor']['sha256']) is str and re.fullmatch('[0-9a-f]{64}',d['extractor']['sha256']), 'invalid Base extractor identity')
    if verify:require(rootfs_inventory(path/'rootfs')==d['inventory'], 'Base rootfs content/metadata damaged')
    return value


def extractor():
    return runpy.run_path(str(Path(__file__).with_name('mojt-base-install')))


def inner_tar(wrapper, body, work):
    old=extractor()
    try:release,checksum,layout=old['validate_manifest'](wrapper/'payload')
    except old['InstallError'] as error:raise ValueError(str(error)) from error
    require(release==body['version']['upstream'] and layout==1, 'Base wrapper/release identity differs')
    compressed=wrapper/'payload/rootfs.tar.zst'
    require(artifact.file_sha(compressed)==checksum, 'inner Base archive differs')
    output=work/'rootfs.tar'
    with tempfile.TemporaryFile() as errors:
        process=subprocess.Popen(['zstd','-q','-d','-c','--',str(compressed)],stdout=subprocess.PIPE,stderr=errors)
        try:
            total=0
            with output.open('xb') as target:
                while chunk:=process.stdout.read(128*1024):
                    total+=len(chunk);require(total<=MAX_ROOTFS, 'Base rootfs decompression exceeds limit')
                    target.write(chunk)
            require(process.wait()==0, 'inner Base decompression failed')
        finally:
            process.stdout.close()
            if process.poll() is None:process.terminate();process.wait()
    # Bound header count and target metadata before invoking GNU tar. The original
    # auditor remains the authority for traversal, links and special-node policy.
    with tarfile.open(output,'r:') as archive:
        count=0
        for member in archive:
            count+=1;require(count<=artifact.MAX_ENTRIES, 'too many Base rootfs entries')
            require(0<=member.uid<2**32-1 and 0<=member.gid<2**32-1 and 0<=member.mode<=0o7777, 'unsupported Base owner/mode')
    try:old['audit_tar'](output)
    except old['InstallError'] as error:raise ValueError(str(error)) from error
    # Read identity from archive members, not through guest absolute symlinks on
    # the host. Audit has already excluded descendants beneath any link.
    with tarfile.open(output,'r:') as archive:
        members={str(Path(m.name)):m for m in archive}
        osrel=members.get('usr/lib/os-release')
        require(osrel is not None and osrel.isfile() and osrel.size<=artifact.MAX_METADATA, 'Base needs regular os-release')
        text=archive.extractfile(osrel).read().decode('utf-8')
        require('ID=mojt\n' in text and f'IMAGE_VERSION="{release}"' in text, 'Base os-release identity differs')
        require('usr/etc' in members and members['usr/etc'].isdir(), 'Base defaults directory missing')
        for name in ('etc','var','home','root'):
            require(name in members and members[name].isdir() and not any(p.startswith(name+'/') for p in members), 'Base state mountpoint must be empty: '+name)
    return output,checksum,old


def prepare(root, body, *, verify_installed=True):
    root=target(root,write=True);acceptable(body);info=store_info(root)
    installed=False
    if info and os.path.lexists(object_path(root,body['id'])):
        saved,receipt=object_record(root,body['id'],verify=verify_installed)
        require(saved==body, 'same-ID Base descriptor differs')
        installed=realization(root,body['id'],receipt,verify=verify_installed) is not None
    if not info or not os.path.lexists(object_path(root,body['id'])):
        require(not os.path.lexists(realization_path(root,body['id'])), 'orphaned Base realization; inspect before installation')
    return record(PLAN,dict(target=str(root),baseline=info['installation'] if info else None,artifact=body['id'],
        version=body['version'],action='no-change' if installed else 'install',selected='unchanged',running='unchanged',
        machine_configuration='unchanged',compatibility='not-evaluated-for-a-deployment'))


def install(root, archive, identifier, *, dry_run=False, yes=False, acquisition=None, tar='tar'):
    io.identifier(identifier);root=target(root,write=True);info=store_info(root)
    acquisition=artifact.parse_json(artifact.canonical(acquisition)) if acquisition is not None else None
    # Exact repeats consume retained bytes, not a vanished original locator.
    if info and os.path.lexists(object_path(root,identifier)):
        body,receipt=object_record(root,identifier,verify=True)
        plan=prepare(root,body)
        if plan['description']['action']=='no-change':
            plan=record(PLAN,dict(plan['description'],archive=receipt['description']['archive'],required_storage_bytes=None))
            return dict(plan=plan,changed=False,dry_run=dry_run)
        archive=object_path(root,identifier)/'archive.tar.zst'
        acquisition=receipt['description'].get('acquisition')
    with tempfile.TemporaryDirectory(prefix='mojt-base-preview-') as temporary:
        work=Path(temporary);wrapper=work/'wrapper';wrapper.mkdir()
        try:
            checksum,size=io.frozen_copy(archive,work/'archive.tar.zst')
            frozen_encoding=dict(sha256=checksum,size=size)
            body=artifact.verify(work/'archive.tar.zst',identifier,max_uncompressed=acquisition['max_expanded'] if acquisition else None)
            acceptable(body);io.unpack_regular(work/'archive.tar.zst',body,wrapper)
            io.acquisition_trust(acquisition,identifier,artifact.file_sha(work/'archive.tar.zst'),(work/'archive.tar.zst').stat().st_size)
            inner,_,_=inner_tar(wrapper,body,work)
            plan=record(PLAN,dict(prepare(root,body)['description'],archive=frozen_encoding,
                rootfs_tar_bytes=inner.stat().st_size,required_storage_bytes=None))
        finally:io.clean_stage(wrapper)
        if dry_run:return dict(plan=plan,changed=False,dry_run=True,archive_verified=True,rootfs_audited=True)
        require(os.geteuid()==0, 'Base realization preserving numeric ownership requires an administrator')
        if not yes:
            print(json.dumps(plan,indent=2),file=__import__('sys').stderr)
            if input('Install this exact Base without changing configuration or boot? [y/N] ').strip().lower() not in ('y','yes'):
                return dict(plan=plan,changed=False,cancelled=True)
        tool=shutil.which(str(tar))
        require(tool is not None, 'retained GNU tar helper is unavailable')
        tool=Path(tool).resolve()
        require('GNU tar' in subprocess.check_output([str(tool),'--version'],text=True), 'Base extraction requires GNU tar')
        tool_evidence=dict(program=str(tool),sha256=artifact.file_sha(tool))
        with locked(root) as state:
            current=prepare(root,body)
            require(current['description']['baseline']==plan['description']['baseline'] or plan['description']['baseline'] is None,
                    'Base target changed since preview')
            if current['description']['action']=='no-change':return dict(plan=current,changed=False)
            obj=object_path(root,identifier)
            if not obj.exists():
                stage=Path(tempfile.mkdtemp(prefix='.install-',dir=obj.parent))
                try:
                    checksum,size=io.frozen_copy(work/'archive.tar.zst',stage/'archive.tar.zst')
                    require(dict(sha256=checksum,size=size)==frozen_encoding,'Base encoding changed after preview')
                    require(artifact.verify(stage/'archive.tar.zst',identifier,
                        max_uncompressed=acquisition['max_expanded'] if acquisition else None)==body,'Base input changed during import')
                    io.unpack_regular(stage/'archive.tar.zst',body,stage)
                    d=dict(installation=state['installation'],kind='base',artifact=identifier,
                        archive=dict(sha256=checksum,size=size),representation='readonly-tree-v1',dependencies=[],
                        trust=io.acquisition_trust(acquisition,identifier,checksum,size),
                        installed_utc=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),uid=os.geteuid(),manager=manager())
                    if acquisition is not None:d['acquisition']=acquisition
                    io.write_json(stage/'artifact.json',body);io.write_json(stage/'installed.json',record(RECEIPT,d))
                    stage.chmod(0o555);io.sync_directory(stage);tx.publish(stage,obj)
                finally:io.clean_stage(stage)
            _,receipt=object_record(root,identifier,verify=True)
            dest=realization_path(root,identifier)
            require(not os.path.lexists(dest), 'refuse to replace an existing Base realization')
            stage=Path(tempfile.mkdtemp(prefix='.install-',dir=dest.parent))
            try:
                inner,checksum,old=inner_tar(obj,body,stage)
                tree=stage/'rootfs';tree.mkdir()
                command=[str(tool),'--numeric-owner','--acls','--xattrs','--xattrs-include=*','--same-owner','--same-permissions']
                subprocess.run([*command,'-xf',str(inner),'-C',str(tree)],check=True)
                try:old['check_rootfs'](tree,body['version']['upstream'])
                except old['InstallError'] as error:raise ValueError(str(error)) from error
                subprocess.run([*command,'--compare','-f',str(inner),'-C',str(tree)],check=True)
                inner.unlink()
                old['sync_tree'](tree)
                evidence=record(REALIZATION,dict(installation=state['installation'],artifact=identifier,receipt=receipt['id'],
                    layout='base-rootfs-v1',rootfs_sha256=checksum,inventory=rootfs_inventory(tree),constructor=manager(),extractor=tool_evidence))
                io.write_json(stage/'realization.json',evidence);stage.chmod(0o555);io.sync_directory(stage)
                # Recheck retained object immediately before publishing the realization.
                require(object_record(root,identifier,verify=True)[1]==receipt,'Base receipt changed during realization')
                require(artifact.file_sha(tool)==tool_evidence['sha256'], 'Base extractor changed during realization')
                tx.publish(stage,dest)
            finally:io.clean_stage(stage)
    return dict(plan=plan,changed=True,installed_path=str(dest),next_boot='unchanged',running='unchanged')
