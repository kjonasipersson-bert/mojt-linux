# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Bounded unchanged-startup System handover; no boot selection or package hooks."""
import copy
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tomllib

import mojt_artifact as artifact
import mojt_system as paths
import mojt_system_manifest as manifests
import mpm_base as base
import mpm_base_boot as base_boot
import mpm_base_transition as common
import mpm_boot_base as boot_base
import mpm_boot_early as early
import mpm_boot_inventory as inventory
import mpm_boot_v2 as model
import mpm_management as management
import mpm_system_transition as transition
import mpm_transaction as tx
from mpm_request_plan import record

FORMAT = 'mojt-system-handover-v1'
require = artifact.require


def validate(value, source):
    d = model.envelope(value,FORMAT);i = model.inputs(source)
    artifact.fields(d,('inputs','preflight','baseline_manifest','baseline_support','base_facts','boot_base','mounts'))
    require(d['inputs'] == source['id'],'handover inputs differ')
    plan = base.envelope(d['preflight'],transition.FORMAT)
    require(plan['operation'] == 'system' and plan['checks']['compatible'] and
            plan['installation'] == i['installation'] and plan['root_uuid'] == i['boot']['root_uuid'], 'handover preflight is incompatible/foreign')
    require(all(plan['retained_base'][k] == i['base'][k] for k in ('artifact','release')) and
            all(plan['retained_kernel'][k] == i['kernel'][k] for k in plan['retained_kernel']) and
            all(plan['candidate_system'][k] == i['system'][k] for k in ('artifact','composition','manifest','generation')), 'handover differs from planned exact scope')
    baseline = manifests.validate(d['baseline_manifest'])
    require(baseline['id'] == plan['checks']['startup']['description']['selected'],'handover baseline differs')
    if d['baseline_support'] is not None:management.validate(d['baseline_support'])
    facts = d['base_facts'];artifact.fields(facts,('architecture','base_abi','state_layout'))
    require(facts['architecture']+'-linux' == i['platform'] and type(facts['state_layout']) is int and facts['state_layout'] == 1
            and type(facts['base_abi']) is dict and facts['base_abi'],'invalid handover Base ABI/layout')
    b = model.envelope(d['boot_base'],boot_base.FORMAT)
    require(b['base'] == i['base']['artifact'] and b['installation'] == i['installation']
            and b['source_realization'] == plan['retained_base']['realization'],'boot Base does not realize planned Base')
    require(type(d['mounts']) is list and len(d['mounts']) <= 64,'unbounded provider mounts')
    names = []
    for mount in d['mounts']:
        artifact.fields(mount,('source','target'))
        require(type(mount['source']) is str and re.fullmatch('[a-z][a-z0-9_-]{0,63}',mount['source'])
                and mount['source'] == mount['target'] and mount['target'] not in
                ('bin','sbin','usr','lib','lib64','etc','var','home','root','dev','proc','sys','run','tmp','boot'), 'unsupported provider mount namespace')
        names.append(mount['target'])
    require(names == sorted(set(names)), 'provider mounts must be sorted and unique')
    return d


def recheck_locked(root, value, source, adapters):
    d = validate(value,source);saved = d['preflight'];p = saved['description']
    require(str(root) == p['target'],'handover plan belongs to another target')
    require(transition._prepare(root,p['candidate_system']['artifact'],p['baseline'],adapters) == saved,
            'System handover inputs changed; prepare again')
    boot_base.inspect(root,d['boot_base'])


def prepare(root, source, plan, *, adapters, tar='tar'):
    """Join the existing preflight to a new immutable boot-only Base realization."""
    require(os.geteuid() == 0,'System handover preparation requires an administrator')
    root = base.target(root,write=True);p = base.envelope(plan,transition.FORMAT)
    require(p['checks']['compatible'],'System preflight blocks handover')
    # Check exact scope before any coordination directory or realization write.
    i = model.inputs(source)
    require(str(root) == p['target'] and p['installation'] == i['installation'] and p['root_uuid'] == i['boot']['root_uuid']
            and all(p['candidate_system'][k] == i['system'][k] for k in ('artifact','composition','manifest','generation'))
            and all(p['retained_base'][k] == i['base'][k] for k in ('artifact','release'))
            and all(p['retained_kernel'][k] == i['kernel'][k] for k in p['retained_kernel']), 'handover scope differs')
    for name in ('boot','boot/mpm'):
        tx.protected_directory(root/name,write=True);(root/name).mkdir(mode=0o755,exist_ok=True)
    locks = {root/'.artifact-store.lock',root/'artifacts/.lock',*tx.boot_lock_paths(root)}
    # Do not initialize a Ports profile just to acquire a lock. Existing writers
    # already share the installation lock; include its Ports lock when present.
    locks = {p for p in locks if p.parent.exists()}
    with tx.resource_locks(locks,modes={root/'.install-lock':0o644}):
        require(transition._prepare(root,p['candidate_system']['artifact'],p['baseline'],adapters) == plan,'System plan changed before preparation')
        state,entries,menu = transition.boot.current(root,p['baseline'])
        old,unused,unused = transition.boot.live_context(root,entries[state['selected']])
        profile = root/'system'/old['description']['label']
        support = management.retained(profile,old)
        release = tomllib.loads(common.checked_bytes(base.object_path(root,i['base']['artifact'])/'payload/manifest.toml').decode())
        mounts = {};provider_roots = set()
        import mpm_system as system
        from mpm_boot_constructor import provider_paths
        for ref in system.retained_providers(root,i['system']['artifact']):
            adapter = adapters[ref['provider']]
            provider_roots.update(provider_paths(root,ref,adapters))
            require(hasattr(adapter,'boot_mounts'),'provider has no boot mount contract')
            for row in adapter.boot_mounts(ref,root):
                require(type(row) is dict and type(row.get('target')) is str,'invalid provider mount projection')
                require(row['target'] not in mounts or mounts[row['target']] == row,'conflicting provider mounts')
                mounts[row['target']] = copy.deepcopy(row)
        value = record(FORMAT,dict(inputs=source['id'],preflight=plan,baseline_manifest=old,baseline_support=support,
            base_facts=dict(architecture=release['base']['architecture'],base_abi=release['abi'],state_layout=release['state']['layout_version']),
            boot_base=boot_base.prepare_locked(root,i['base']['artifact'],tar=tar),mounts=[mounts[k] for k in sorted(mounts)]))
        validate(value,source);check(root,source,None,value,provider_roots=sorted(provider_roots))
        return value


def guest_file(root, tree, profile, provider_roots, mounts, guest):
    """Resolve account/start paths in the future mount namespace, never the host."""
    require(type(guest) is str and guest.startswith('/'),'absolute guest executable required')
    maps = [('/run/mojt-system',profile,True)]
    maps += [('/'+m['target'],root/m['source'],False) for m in mounts]
    maps += [('/'+p,root/p,True) for p in provider_roots]
    maps += [('/'+p,root/'state'/p,False) for p in ('etc','var','home','root')]
    pending = guest.split('/')[1:];done = [];links = 0;allowed = False
    while pending:
        part = pending.pop(0)
        if part in ('','.'):continue
        if part == '..':require(done,'guest link escapes root');done.pop();continue
        name = '/'+('/'.join([*done,part]));choices = [r for r in maps if name == r[0] or name.startswith(r[0]+'/')]
        if choices:
            prefix,actual,allowed = max(choices,key=lambda r:len(r[0]));actual = actual/name[len(prefix):].lstrip('/')
        else:actual = tree/name.lstrip('/');allowed = True
        info = actual.lstat()
        if stat.S_ISLNK(info.st_mode):
            links += 1;require(links <= 40,'guest link loop');target = os.readlink(actual)
            if target.startswith('/'):done = []
            pending = target.split('/')+pending
        else:
            require(not pending or stat.S_ISDIR(info.st_mode),'guest path traverses a nondirectory');done.append(part)
    require(done and allowed and stat.S_ISREG(actual.lstat().st_mode) and actual.stat().st_mode & 0o001,
            'guest executable is not supplied by verified immutable content: '+guest)
    return actual


def check(root, source, trees, value, *, provider_roots=None):
    """Re-evaluate current state before writable mounts; never run a provider."""
    d = validate(value,source);i = source['description'];tree = boot_base.inspect(root,d['boot_base'])
    profile = inventory.path(root,'realizations/system/'+i['system']['artifact'][7:]+'/profile')
    candidate = manifests.validate(base.read(profile/'manifest.json'))
    require(candidate['id'] == i['system']['manifest'],'handover System manifest differs')
    review = transition.tooling_review(d['baseline_manifest'],candidate)
    require(review == d['preflight']['description']['checks']['startup'] and review['description']['compatible'],'startup review changed')
    persistent = common.state_inputs(root)
    facts = dict(format=manifests.CONTEXT,**d['base_facts'],ports=persistent['ports'],required_system_paths=persistent['system_shells'])
    require(persistent['layout'] == facts['state_layout'],'persistent state layout differs')
    compatibility = manifests.check(candidate,facts);require(compatibility['compatible'],'System current-state compatibility: '+'; '.join(compatibility['errors']))
    observed = management.observe_target(root)
    for support in (management.current(),management.retained(profile,candidate),d['baseline_support']):
        report = management.check(support,observed);require(report['compatible'],'management/recovery compatibility: '+'; '.join(report['errors']))
    require(not transition.defaults(root,profile)['missing'] and not base_boot.defaults_check(root,tree)['missing'],
            'missing defaults require explicit preparation')
    if trees is None:
        # Only prepare() passes roots projected by its freshly verified adapter.
        require(type(provider_roots) is list,'verified provider roots required')
    else:
        proof = early.proof(trees,source)
        provider_roots = [p for row in proof['providers'] for p in row['trees']]
    require(all(any(p.startswith(m['source']+'/') for m in d['mounts']) for p in provider_roots),'provider tree has no declared mount')
    for name in ('dev','proc','sys','etc','var','home','root','run','tmp','lib/modules',*[m['target'] for m in d['mounts']]):
        point = paths.virtual_file(tree,'/'+name)
        require(point.is_dir() and not any(point.iterdir()),'boot mountpoint must be an empty directory: '+name)
    for mount in d['mounts']:require(inventory.path(root,mount['source']).is_dir(),'provider mount source missing')
    for name in ('etc','var','home','root'):inventory.path(root,'state/'+name)
    for shell in [*persistent['base_shells'],*persistent['system_shells']]:guest_file(root,tree,profile,provider_roots,d['mounts'],shell)
    guest_file(root,tree,profile,provider_roots,d['mounts'],'/run/mojt-system/start')
    hostname = common.checked_bytes(root/'state/etc/hostname').decode().strip()
    require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9.-]{0,252}',hostname),'invalid persistent hostname')
    return dict(tree=tree,profile=profile,modules=inventory.path(root,'kernel/installed/'+i['kernel']['artifact'][7:]+'/payload/lib/modules'),
                provider_roots=provider_roots,mounts=d['mounts'],hostname=hostname,source=source)


def unit_name(path):
    raw = path.strip('/').encode();result = ''
    for byte in raw:
        result += '-' if byte == 47 else chr(byte) if chr(byte).isascii() and (chr(byte).isalnum() or byte in b':_.') else '\\x%02x'%byte
    if result.startswith('.'):result = '\\x2e'+result[1:]
    return (result or '-')+'.mount'


def enter(root, source, trees, value, cmdline, release, *, runner=None, execute=None):
    verified = early.verify(root,source,trees,cmdline,release)
    context = check(Path(root),source,trees,value)
    context['deployment'] = early.read(Path(root)/model.slot(verified['deployment'])/'deployment.json')
    require(context['deployment']['id'] == verified['deployment'],'deployment changed before handover')
    return _enter(Path(root),context,verified,runner=runner,execute=execute)


def _enter(root, context, verified, *, runner=None, execute=None, newroot=Path('/newroot'), runtime=Path('/')):
    """Only enter() authorizes this operation. Injected functions support CI."""
    runner = runner or (lambda args:subprocess.run(['/bin/busybox',*map(str,args)],check=True))
    execute = execute or os.execv
    newroot = Path(newroot);require(newroot == newroot.resolve() and newroot.is_dir() and not any(newroot.iterdir()),'newroot must be an empty canonical mountpoint')
    mounted = [];moved = [];backing_writable = False
    def bind(source,target,readonly=False):
        runner(['mount','--bind',source,target]);mounted.append(target)
        if readonly:runner(['mount','-o','remount,bind,ro',source,target])
    try:
        runner(['mount','-o','remount,rw',root]);backing_writable = True
        bind(context['tree'],newroot,True)
        runner(['mount','-t','tmpfs','-o','mode=0755,nodev,nosuid,strictatime','tmpfs',newroot/'run']);mounted.append(newroot/'run')
        for path in ('mojt-system','mojt','initramfs/bin','systemd/system'):(newroot/'run'/path).mkdir(parents=True,exist_ok=True)
        bind(context['profile'],newroot/'run/mojt-system',True)
        for name in ('etc','var','home','root'):bind(root/'state'/name,newroot/name)
        for mount in context['mounts']:bind(root/mount['source'],newroot/mount['target'])
        immutable = []
        for name in context['provider_roots']:
            destination = newroot/name;bind(root/name,destination,True);immutable.append('/'+name)
        module_point = paths.virtual_file(context['tree'],'/lib/modules').relative_to(context['tree'])
        bind(context['modules'],newroot/module_point,True)
        runner(['mount','-t','tmpfs','-o','mode=1777,nodev,nosuid','tmpfs',newroot/'tmp']);mounted.append(newroot/'tmp')
        shutil.copyfile(runtime/'bin/busybox',newroot/'run/initramfs/bin/busybox');(newroot/'run/initramfs/bin/busybox').chmod(0o755)
        (newroot/'run/initramfs/bin/sh').symlink_to('busybox')
        shutil.copyfile(runtime/'shutdown',newroot/'run/initramfs/shutdown');(newroot/'run/initramfs/shutdown').chmod(0o755)
        protected = ['/etc','/var','/home','/root','/run/mojt-system','/run/mojt-disk','/'+str(module_point),
                     *['/'+m['target'] for m in context['mounts']],*immutable]
        for path in protected:
            directory = newroot/'run/systemd/system'/(unit_name(path)+'.d');directory.mkdir(parents=True,exist_ok=True)
            (directory/'10-mojt-exitrd.conf').write_text('[Unit]\nDefaultDependencies=no\n')
        i = context['source']['description'];identity = newroot/'run/mojt'
        # A separate v2 runtime record until the authoritative selector/status
        # join lands. Never synthesize a v1 deployment from these exact inputs.
        running = dict(format='mojt-running-native-v2',deployment=context['deployment'],inputs=context['source']['id'],
                       installation=i['installation'])
        (identity/'native-v2.json').write_bytes(artifact.canonical(running)+b'\n')
        for name,key in (('native-kernel-artifact','kernel'),('native-base-artifact','base'),('native-system-artifact','system')):
            (identity/name).write_text(i[key]['artifact']+'\n')
        (identity/'issue').write_text('Mojt Linux '+i['system']['generation']+'/'+i['base']['release']+' (x86_64)\n\n')
        (identity/'motd').write_text('Welcome to Mojt Linux\n\nSystem: '+i['system']['generation']+'\nBase: '+i['base']['release']+'\nKernel: '+i['kernel']['release']+'\n')
        runner(['hostname',context['hostname']])
        for name in ('dev','proc','sys'):
            runner(['mount','--move',runtime/name,newroot/name]);moved.append((runtime/name,newroot/name))
        (newroot/'run/mojt-disk').mkdir()
        runner(['mount','--move',root,newroot/'run/mojt-disk']);moved.append((root,newroot/'run/mojt-disk'))
        execute('/bin/busybox',['busybox','switch_root','-c','/dev/console',str(newroot),'/run/mojt-system/start'])
        raise RuntimeError('switch_root unexpectedly returned')
    except BaseException:
        # Keep /dev,/proc,/sys and the backing root available to diagnostics.
        for source,target in reversed(moved):
            try:runner(['mount','--move',target,source])
            except (OSError,subprocess.CalledProcessError):pass
        for target in reversed(mounted):
            try:runner(['umount',target])
            except (OSError,subprocess.CalledProcessError):pass
        if backing_writable:
            try:runner(['mount','-o','remount,ro',root])
            except (OSError,subprocess.CalledProcessError):pass
        raise
