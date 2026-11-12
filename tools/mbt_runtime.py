# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare fixed MBT resources before importing manager code; stdlib only."""
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

FORMAT = 'mojt-mbt-execution-v1'
MARKER = 'mbt-execution.json'
PREFIX = '.mojt-mbt-runtime-'
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
# These are also delivered at these paths by the existing System installer.
EXTRA = ('tests/run-mpm-nix-python.py','tests/run-mpm-nix-ports.py',
         'tests/run-mpm-selectors.py','tests/run-mpm-nix-upgrade.py')


def require(ok, message):
    if not ok:raise ValueError(message)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()


def read_file(path):
    require(path == path.resolve(),'linked MBT source/resource: '+str(path))
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= MAX_FILE,
                'unsafe/unbounded MBT source/resource: '+str(path))
        data=stream.read(MAX_FILE+1);after=os.fstat(stream.fileno());current=path.lstat()
    require(len(data) == before.st_size and (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns) ==
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) and
            (current.st_dev,current.st_ino) == (before.st_dev,before.st_ino),'MBT source changed while reading: '+str(path))
    return data


def resources(source):
    data=read_file(source/'tools/mojt_system.py');definitions={}
    for node in ast.parse(data).body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            key=node.targets[0].id
            if key in ('MPM_FILES','MBT_FILES','MBT_SOURCE_FILES'):
                require(key not in definitions,'duplicate MBT resource declaration')
                value=ast.literal_eval(node.value)
                require(type(value) is tuple and value and all(type(p) is str for p in value),'invalid MBT resource declaration')
                definitions[key]=value
    require(set(definitions)=={'MPM_FILES','MBT_FILES','MBT_SOURCE_FILES'},'missing MBT resource declaration')
    names={*('tools/'+n for key in ('MPM_FILES','MBT_FILES') for n in definitions[key]),
           *definitions['MBT_SOURCE_FILES'],*EXTRA}
    require(0 < len(names) <= 128,'unbounded MBT resource inventory')
    for name in names:
        require(not name.startswith('/') and all(p not in ('','.','..') for p in name.split('/'))
                and '\\' not in name,'invalid MBT resource path')
    return sorted(names)


def protected_parent(parent):
    require(parent == parent.resolve() and parent.is_dir(),'canonical MBT temporary parent required')
    for point in reversed([parent,*parent.parents]):
        info=point.stat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid in (0,os.geteuid()) and
                (not info.st_mode & 0o022 or info.st_uid == 0 and info.st_mode & stat.S_ISVTX),
                'unsafe MBT runtime ancestor: '+str(point))
    return parent


def temporary_parent():
    if os.geteuid() != 0:return protected_parent(Path(tempfile.gettempdir()).resolve(strict=True))
    parent=Path('/var/tmp')
    if not os.path.lexists(parent):
        protected_parent(parent.parent.resolve(strict=True));parent.mkdir(mode=0o1777);parent.chmod(0o1777)
    return protected_parent(parent.resolve(strict=True))


def freeze(source, destination):
    """Checkout permissions are input metadata, never installed-runtime modes."""
    names=resources(source);files=[];total=0
    for name in names:
        data=read_file(source/name);total+=len(data)
        require(total <= MAX_TOTAL,'MBT execution resource limit')
        target=destination/name;target.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
        for parent in target.parents:
            if parent == destination:break
            parent.chmod(0o755)
        with target.open('xb') as stream:
            stream.write(data);os.fchmod(stream.fileno(),0o644)
        files.append(dict(path=name,sha256=hashlib.sha256(data).hexdigest(),mode=0o644))
    require(resources(source)==names and all(hashlib.sha256(read_file(source/r['path'])).hexdigest()==r['sha256'] for r in files),
            'MBT sources changed during preparation')
    body=dict(format=FORMAT,files=files)
    record=dict(body,id='sha256:'+hashlib.sha256(canonical(body)).hexdigest(),source=str(source))
    with (destination/MARKER).open('xb') as stream:
        stream.write(canonical(record)+b'\n');os.fchmod(stream.fileno(),0o444)
    verify(destination)
    return record


def verify(root):
    require(root.name.startswith(PREFIX) and root == root.resolve(),'invalid MBT runtime location')
    protected_parent(root.parent)
    info=root.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode)==0o700,
            'MBT execution directory must be private and owned by its executor')
    value=json.loads(read_file(root/MARKER))
    require(type(value) is dict and set(value)=={'format','files','id','source'} and value['format']==FORMAT,
            'unsupported MBT execution record')
    require(type(value['source']) is str and Path(value['source']).is_absolute(),'invalid MBT source provenance')
    body={key:value[key] for key in ('format','files')}
    require(value['id']=='sha256:'+hashlib.sha256(canonical(body)).hexdigest(),'MBT execution identity differs')
    require(type(value['files']) is list and [r['path'] for r in value['files']]==resources(root),'MBT execution inventory differs')
    expected={r['path'] for r in value['files']}|{MARKER}
    directories={str(p) for name in expected for p in Path(name).parents if str(p) != '.'}
    actual={str(p.relative_to(root)) for p in root.rglob('*')}
    require(actual==expected|directories,'unexpected MBT execution resource')
    for name in directories:
        info=(root/name).lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o755,
                'unprotected MBT execution directory')
    for row in value['files']:
        require(set(row)=={'path','sha256','mode'} and row['mode']==0o644,'invalid MBT execution file')
        point=root/row['path'];info=point.lstat()
        require(info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==row['mode'] and
                hashlib.sha256(read_file(point)).hexdigest()==row['sha256'],'MBT execution file changed: '+row['path'])
    marker=(root/MARKER).lstat()
    require(marker.st_uid==os.geteuid() and stat.S_IMODE(marker.st_mode)==0o444,'unprotected MBT execution record')
    return value


def enter(args):
    """Return child status, or None in a verified prepared execution process."""
    source=Path(__file__).resolve().parents[1]
    if os.path.lexists(source/MARKER):verify(source);return None
    with tempfile.TemporaryDirectory(prefix=PREFIX,dir=temporary_parent()) as temporary:
        root=Path(temporary);freeze(source,root)
        # -I ignores user Python configuration; -B keeps measured code unchanged.
        # Keep the selected host tool PATH and sudo caller identity for handoff.
        environment=os.environ.copy()
        for key in tuple(environment):
            if key.startswith(('PYTHON','LD_')):environment.pop(key,None)
        result=subprocess.run([sys.executable,'-I','-B',str(root/'tools/mbt'),*args],env=environment)
        return result.returncode
