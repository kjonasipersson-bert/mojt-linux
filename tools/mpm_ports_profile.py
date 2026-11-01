# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Versioned fresh Ports profiles. One pointer commits requests/aliases/history."""
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import stat
import uuid

import mpm_requests as wishes
import mpm_request_plan as planning
from mpm_selection import Catalog, parse_selector, resolve
import mpm_transaction as transaction

MARKER = 'mojt-ports-store-v1'
PROFILE = 'mojt-ports-profile-v1'
PLAN = 'mojt-ports-publish-plan-v1'
HISTORY = 'mojt-ports-transaction-v1'
RESERVED = {'mpm','mojt-system-check','nix','nix-store','nix-instantiate'}
COMMAND = r'[A-Za-z0-9][A-Za-z0-9._+-]*'
require = planning.require


def safe_root(root, *, write=False):
    root = Path(os.path.abspath(root))
    require(root == root.resolve(), 'Ports root traverses a symlink')
    # Check from the filesystem root: a later 0700 child cannot protect an
    # earlier writable parent from rename/replacement. Once an owned 0700
    # directory is reached, other users cannot traverse its subtree, so mode
    # 0775 descendants do not make a private lab externally writable.
    private = False
    for p in reversed([root, *root.parents]):
        if not p.exists():
            continue
        info = p.stat()
        detail = f'{p} (mode={stat.S_IMODE(info.st_mode):04o}, uid={info.st_uid})'
        require(stat.S_ISDIR(info.st_mode) and info.st_uid in (0,os.geteuid()), 'unsafe Ports ancestor: ' + detail)
        sticky = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        require(private or not info.st_mode & 0o022 or sticky, 'writable Ports ancestor: ' + detail)
        if info.st_uid == os.geteuid() and not info.st_mode & 0o077:
            private = True
    if root.exists():
        require(root.stat().st_uid in (0,os.geteuid()) and not root.stat().st_mode & 0o022, 'Ports root is not protected')
        if write:require(root.stat().st_uid == os.geteuid(),'shared Ports mutation requires its administrator')
    return root


def regular(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid in (0,os.geteuid()) and not info.st_mode & 0o022, 'unsafe Ports metadata')
    require(info.st_size <= 16 * 1024**2, 'Ports metadata too large')
    return path


def read(path):
    def pairs(rows):
        d = {}
        for k,v in rows:
            require(k not in d, 'duplicate JSON key'); d[k] = v
        return d
    value = json.loads(regular(path).read_text(),object_pairs_hook=pairs)
    wishes.canonical(value)
    return value


def write(path,value):
    with path.open('xb') as stream:
        stream.write(wishes.canonical(value)+b'\n');stream.flush();os.fchmod(stream.fileno(),0o444);os.fsync(stream.fileno())


def verify_record(value,fmt):
    wishes.fields(value,('format','id','description'))
    require(value['format'] == fmt and value['id'] == wishes.digest({k:v for k,v in value.items() if k!='id'}), 'invalid Ports record identity/version')
    return value['description']


def marker(root):
    value = read(root/'store.json')
    wishes.fields(value,('format','installation'))
    require(value['format'] == MARKER and re.fullmatch('[0-9a-f]{32}',value['installation']), 'unsupported Ports store')
    for name in ('profiles','retained'):
        require((root/name).is_dir() and not (root/name).is_symlink(), 'incomplete Ports store')
        info=(root/name).stat();require(info.st_uid in (0,os.geteuid()) and not info.st_mode & 0o022,'unsafe Ports directory')
    return value


def current(root):
    root = safe_root(root)
    if not root.exists() or not any(root.iterdir()):
        return None
    if {p.name for p in root.iterdir()} == {'.lock'}:
        transaction.check_lock_file(root/'.lock',shared=True);return None
    m = marker(root)
    pointer = root/'current'
    if not os.path.lexists(pointer):
        return None
    require(pointer.is_symlink(), 'unmanaged current pointer')
    relative = os.readlink(pointer)
    require(re.fullmatch(r'profiles/[0-9a-f]{32}',relative), 'invalid profile path')
    directory = root/relative
    require(directory.is_dir() and not directory.is_symlink(), 'unsafe profile directory')
    state = read(directory/'state.json');d=verify_record(state,PROFILE)
    wishes.fields(d,('installation','platform','requests','lock','sources','packages','objects','acquisition','aliases','active','event_sequence','sequence','parent'))
    require(d['installation'] == m['installation'], 'wrong installation')
    wishes.token(d['platform'])
    wishes.validate(d['requests'])
    require(d['lock']['description']['requests'] == d['requests']['id'], 'profile lock differs')
    verify_record(d['lock'],'mojt-resolution-lock-v1')
    require(type(d['sequence']) is int and d['sequence'] > 0, 'invalid sequence')
    if d['parent'] is not None:require(re.fullmatch(r'profiles/[0-9a-f]{32}',d['parent']), 'invalid history parent')
    row = read(directory/'transaction.json');h=verify_record(row,HISTORY)
    require(h['profile'] == relative and h['after'] == state['id'] and h['sequence'] == d['sequence'] and h['parent'] == d['parent'], 'history/profile differs')
    require((directory/'bin').is_dir() and not (directory/'bin').is_symlink(), 'unsafe bin directory')
    for path in (directory,directory/'bin'):
        info=path.stat();require(info.st_uid in (0,os.geteuid()) and not info.st_mode & 0o022,'unsafe profile permissions')
    require(set((directory/'bin').iterdir()) == {directory/'bin'/k for k in d['aliases']}, 'profile alias inventory differs')
    for name,target in d['aliases'].items():
        command(name);require((directory/'bin'/name).is_symlink() and os.readlink(directory/'bin'/name) == target, 'profile alias changed')
    return dict(record=state,path=relative,transaction=row)


def command(name):
    require(type(name) is str and re.fullmatch(COMMAND,name) and len(name.encode()) <= 255, 'unsupported command alias')


def described(adapters,reference,root):
    provider=reference['provider'];require(provider in adapters,'unsupported provider: '+provider)
    value=adapters[provider].describe(copy.deepcopy(reference),root)
    wishes.fields(value,('reference','commands'))
    require(value['reference'] == reference and type(value['commands']) is dict, 'adapter description differs')
    for name,path in value['commands'].items():
        command(name);require(type(path) is str and Path(path).is_absolute() and '\x00' not in path, 'unsafe export path')
    return copy.deepcopy(value)


def preview(root, desired, sources, adapters, *, platform, executor, target_identity, advance=None, auto_select=True):
    """Read-only: no roots, payload import, command execution or profile creation."""
    root=safe_root(root);old=current(root);requests=wishes.validate(desired)
    installation=requests['description']['installation']
    if root.exists() and (root/'store.json').exists():require(marker(root)['installation']==installation,'wrong installation')
    view=planning.sources_view(sources)
    prior=old['record']['description'] if old else None
    require(prior is None or prior['platform']==platform,'installed Ports target another platform')
    claims={r['key']:r for r in requests['description']['claims']}
    require(advance is None or type(advance) is list and len(set(advance))==len(advance) and set(advance)<=claims.keys(),'invalid upgrade scope')
    require(type(auto_select) is bool,'invalid initial activation policy')
    advance=sorted(advance or [])
    accepted={r['claim']:r for r in prior['lock']['description']['resolutions']} if prior else {}
    frozen=set()
    rows=[]
    for key,claim in claims.items():
        # Accepted targets survive metadata refresh/other installs. Exact release
        # wishes also keep their accepted full build if the catalog changes it.
        if key in accepted and (key not in advance or parse_selector(claim['policy']['selector']).kind=='exact'):
            rows.append(copy.deepcopy(accepted[key]));frozen.add(key)
        else:rows.append(planning.resolve_claim(claim,view,platform=platform))
    def resolution_lock(state):
        return planning.record('mojt-resolution-lock-v1',dict(installation=installation,area='ports',requests=state['id'],
            snapshots=sorted({r['snapshot'] for r in rows}),resolutions=sorted(rows,key=lambda r:r['claim'])))
    lock=resolution_lock(requests)
    prior_packages={planning.key(p['reference']):p for p in prior['packages']} if prior else {}
    event=prior['event_sequence'] if prior else 0
    packages={}
    # Historical versions remain in the logical profile while their claims live.
    for package in prior['packages'] if prior else []:
        p=copy.deepcopy(package);p['claims']=sorted(set(p['claims']) & claims.keys())
        if p['claims']:packages[planning.key(p['reference'])]=p
    resolved={}
    for row in lock['description']['resolutions']:
        claim=claims[row['claim']];ref=row['reference'];k=planning.key(ref)
        if row['claim'] in frozen:
            require(k in prior_packages,'accepted target is not installed')
            package=copy.deepcopy(prior_packages[k]);package['claims']=[]
            require(package['commands']==described(adapters,ref,root)['commands'],'retained exports differ')
        else:
            candidate=resolve(Catalog.from_dict(view[claim['source']]['catalogs'][claim['role']]),claim['policy']['selector'],platform=platform).candidate
            package=dict(reference=ref,role=claim['role'],release_id=candidate.release_id,
                release={name:copy.deepcopy(getattr(candidate,name)) for name in ('upstream_version','version_scheme','revision_scheme','package_revision','stability','compatibility')},
                claims=[],commands=described(adapters,ref,root)['commands'],installed=None,activated=None)
        if k in packages:
            require(all(packages[k][f] == package[f] for f in ('role','release_id','release','commands')), 'conflicting package identity')
            package=packages[k]
        else:
            event+=1;package['installed']=event
        package['claims']=sorted(set(package['claims'])|{claim['key']});packages[k]=package;resolved[row['claim']]=k
    choices=requests['description']['selections']
    for choice in choices:
        if choice['mode']=='exact':
            k=planning.key(choice['reference']);require(k in prior_packages,'exact activation requires an installed package')
            require(prior_packages[k]['role']==choice['role'],'active role differs')
            if k not in packages:
                p=copy.deepcopy(prior_packages[k]);p['claims']=[];packages[k]=p
    # First installation convenience, never advancement of an existing default.
    roles={p['role'] for p in prior_packages.values()}
    for role in sorted(({p['role'] for p in packages.values()}-roles-{c['role'] for c in choices}) if auto_select else set()):
        role_rows=[r for r in lock['description']['resolutions'] if claims[r['claim']]['role']==role]
        require(len({planning.key(r['reference']) for r in role_rows})==1,'multiple first-install versions require an explicit active choice')
        chosen=sorted(role_rows,key=lambda r:(claims[r['claim']]['origin']['kind']!='configuration',r['claim']))[0]
        claim=claims[chosen['claim']];choices.append(dict(role=role,origin=claim['origin'],mode='request',claim=claim['key']))
    requests=wishes.seal(requests['description']);wishes.validate(requests)
    lock=resolution_lock(requests)
    active={}
    for choice in requests['description']['selections']:
        k=resolved[choice['claim']] if choice['mode']=='request' else planning.key(choice['reference'])
        require(k in packages,'active package not retained');active[choice['role']]=k
    # Preserve the effective previous version on reapply; if removed, use committed
    # activation/install ordering from retained profile ancestry (not wall time).
    prior_active={role:planning.key(ref) for role,ref in prior['active'].items()} if prior else {}
    for role in ({p['role'] for p in packages.values()} & prior_active.keys())-active.keys():
        targets=[k for k,p in packages.items() if p['role']==role]
        if prior_active.get(role) in targets:active[role]=prior_active[role]
        else:
            activated=[k for k in targets if packages[k]['activated'] is not None]
            active[role]=max(activated,key=lambda k:packages[k]['activated']) if activated else max(targets,key=lambda k:packages[k]['installed'])
    for role,k in sorted(active.items()):
        if prior_active.get(role)!=k:
            event+=1;packages[k]['activated']=event
    objects={};bindings={}
    def visit(ref,source_name,stack):
        k=planning.key(ref);require(k not in stack and len(stack)<64,'dependency cycle/depth')
        source=view[source_name];offers=[o for o in source['offers'] if planning.key(o['reference'])==k]
        require(len(offers)==1,'missing exact dependency offer')
        require(k not in bindings or bindings[k]==offers[0],'shared reference has conflicting acquisition bindings')
        if k in bindings:return
        bindings[k]=copy.deepcopy(offers[0])
        for dep in offers[0]['dependencies']:visit(dep,source_name,stack|{k})
        objects[k]=described(adapters,ref,root)
    for row in lock['description']['resolutions']:
        if row['claim'] in frozen:
            for ref in prior['acquisition']:
                obj_=next(o for o in prior['objects'] if o['reference']==ref)
                objects.setdefault(planning.key(ref),copy.deepcopy(obj_))
        else:visit(row['reference'],claims[row['claim']]['source'],set())
    # Old versions/overrides already have retained receipts, not new catalog wishes.
    for k,p in packages.items():
        if k not in objects:
            require(prior is not None,'missing retained object')
            for obj_ in prior['objects']:objects.setdefault(planning.key(obj_['reference']),copy.deepcopy(obj_))
    aliases={}
    def alias(name,target):
        command(name);require(name not in RESERVED,'reserved management alias: '+name)
        require(name not in aliases or aliases[name]==target,'command alias conflict: '+name)
        aliases[name]=target
    for k,p in packages.items():
        suffix=p['release_id']+'-'+wishes.digest(p['reference']).split(':')[1]
        for name,target in p['commands'].items():alias(name+'-'+suffix,target)
    for role,k in active.items():
        for name,target in packages[k]['commands'].items():alias(name,target)
    for row in lock['description']['resolutions']:
        parsed=parse_selector(claims[row['claim']]['policy']['selector'])
        if parsed.kind=='series':
            for name,target in packages[planning.key(row['reference'])]['commands'].items():alias(name+'-'+'.'.join(map(str,parsed.value)),target)
    state=dict(installation=installation,platform=platform,requests=requests,lock=lock,sources=copy.deepcopy(view),packages=sorted(packages.values(),key=lambda p:planning.key(p['reference'])),objects=sorted(objects.values(),key=lambda p:planning.key(p['reference'])),acquisition=([ref for ref in prior['acquisition'] if planning.key(ref) in objects] if prior else [])+[objects[k]['reference'] for k in objects if not prior or k not in {planning.key(ref) for ref in prior['acquisition']}],aliases=dict(sorted(aliases.items())),active={role:packages[k]['reference'] for role,k in sorted(active.items())},event_sequence=event)
    if prior:unchanged=all(prior[k]==v for k,v in state.items())
    else:unchanged=False
    return planning.record(PLAN,dict(root=str(root),baseline=old['record']['id'] if old else None,platform=platform,executor=planning.reference(executor),target_identity=planning.identity(target_identity),candidate=state,no_op=unchanged,advance=advance,auto_select=auto_select))


def apply(root, plan, sources, adapters, *, platform, executor, target_identity, action='apply', sync=transaction.sync_directory):
    """Execute an approved plan in the caller's authorized fresh store."""
    pd=verify_record(plan,PLAN);root=safe_root(root,write=True)
    require(pd['root']==str(root),'plan target path changed')
    # Preview/preflight before initializing a new registry or importing anything.
    require(preview(root,pd['candidate']['requests'],sources,adapters,platform=platform,executor=executor,target_identity=target_identity,advance=pd['advance'],auto_select=pd['auto_select'])==plan,'plan inputs/baseline changed')
    fresh=not root.exists();root.mkdir(mode=0o755 if os.geteuid()==0 else 0o700,exist_ok=True)
    safe_root(root,write=True)
    if fresh:root.chmod(0o755 if os.geteuid()==0 else 0o700)
    with transaction.file_lock(root/'.lock'):
        if not (root/'store.json').exists():
            require({p.name for p in root.iterdir()} <= {'.lock'},'unmanaged Ports root')
            (root/'profiles').mkdir(mode=0o755);(root/'retained').mkdir(mode=0o755)
            (root/'profiles').chmod(0o755);(root/'retained').chmod(0o755)
            write(root/'store.json',dict(format=MARKER,installation=pd['candidate']['installation']))
            sync(root/'profiles');sync(root/'retained');sync(root);sync(root.parent)
        require(preview(root,pd['candidate']['requests'],sources,adapters,platform=platform,executor=executor,target_identity=target_identity,advance=pd['advance'],auto_select=pd['auto_select'])==plan,'late plan baseline changed')
        old=current(root);candidate=pd['candidate']
        if not pd['no_op']:
            previous={planning.key(o['reference']) for o in old['record']['description']['objects']} if old else set()
            for ref in candidate['acquisition']:
                if planning.key(ref) not in previous:adapters[ref['provider']].ensure(copy.deepcopy(ref),root)
        for obj_ in candidate['objects']:
            adapter=adapters[obj_['reference']['provider']]
            require(described(adapters,obj_['reference'],root)==obj_,'exports changed after acquisition')
            adapter.verify(copy.deepcopy(obj_['reference']),root)
            for path in obj_['commands'].values():require(Path(path).is_file() and os.access(path,os.X_OK),'exported executable missing')
        if pd['no_op']:return dict(changed=False,profile=old['path'])
        require((current(root)['record']['id'] if current(root) else None)==pd['baseline'],'selection changed during import')
        relative='profiles/'+uuid.uuid4().hex;directory=root/relative;directory.mkdir(mode=0o755)
        temp=root/('.current-'+uuid.uuid4().hex);published=False
        try:
            (directory/'bin').mkdir(mode=0o755)
            d=copy.deepcopy(candidate);d.update(sequence=old['record']['description']['sequence']+1 if old else 1,parent=old['path'] if old else None)
            state=planning.record(PROFILE,d)
            oldrefs={wishes.digest(p['reference']) for p in old['record']['description']['packages']} if old else set()
            newrefs={wishes.digest(p['reference']) for p in d['packages']}
            history=planning.record(HISTORY,dict(profile=relative,parent=d['parent'],sequence=d['sequence'],action=action,uid=os.geteuid(),utc=datetime.now(timezone.utc).isoformat(),before=old['record']['id'] if old else None,after=state['id'],requests_before=old['record']['description']['requests']['id'] if old else None,requests_after=d['requests']['id'],added=sorted(newrefs-oldrefs),removed=sorted(oldrefs-newrefs),aliases_before=old['record']['description']['aliases'] if old else {},aliases_after=d['aliases']))
            write(directory/'state.json',state);write(directory/'transaction.json',history)
            for name,target in d['aliases'].items():(directory/'bin'/name).symlink_to(target)
            (directory/'bin').chmod(0o755);directory.chmod(0o755)
            sync(directory/'bin');sync(directory);sync(root/'profiles')
            temp.symlink_to(relative)
            try:transaction.publish(temp,root/'current',sync=sync)
            except transaction.PublicationUncertain:published=True;raise
            published=True
            return dict(changed=True,profile=relative,transaction=history)
        finally:
            temp.unlink(missing_ok=True)
            if not published:shutil.rmtree(directory)


def history(root, limit=20):
    require(type(limit) is int and 1<=limit<=1000,'invalid history limit')
    root=safe_root(root);selected=current(root)
    relative=selected['path'] if selected else None;rows=[];seen=set();expected=None;expected_id=None
    while relative is not None and len(rows)<limit:
        require(relative not in seen and re.fullmatch(r'profiles/[0-9a-f]{32}',relative),'invalid history ancestry');seen.add(relative)
        directory=root/relative;require(not directory.is_symlink(),'unsafe history directory')
        row=read(directory/'transaction.json');d=verify_record(row,HISTORY)
        state=read(directory/'state.json');sd=verify_record(state,PROFILE)
        require(d['after']==state['id'] and sd['sequence']==d['sequence'] and sd['parent']==d['parent'],'history state differs')
        require(d['profile']==relative and (expected is None or d['sequence']==expected),'invalid history sequence')
        require(expected_id is None or state['id']==expected_id,'history parent identity differs')
        require((d['parent'] is None)==(d['sequence']==1) and (d['before'] is None)==(d['parent'] is None),'invalid history origin')
        rows.append(row);expected=d['sequence']-1;expected_id=d['before'];relative=d['parent']
    return rows
