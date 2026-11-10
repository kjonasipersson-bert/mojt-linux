# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Bounded unchanged-startup System handover; no boot selection or package hooks."""
import copy
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
import tomllib

import mojt_artifact as artifact
import mojt_system as paths
import mojt_hardware as hardware
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
from mpm_boot_v2 import record

FORMAT = 'mojt-system-handover-v1'
require = artifact.require


def validate(value, source):
    d = model.envelope(value,FORMAT);i = model.inputs(source)
    artifact.fields(d,('inputs','preflight','baseline_manifest','baseline_support','base_facts','boot_base','mounts'))
    require(d['inputs'] == source['id'],'handover inputs differ')
    candidate = transition.boot_fields(d['preflight']);plan = d['preflight']['description']
    require(plan['checks']['compatible'] and
            plan['installation'] == i['installation'] and plan['root_uuid'] == i['boot']['root_uuid'], 'handover preflight is incompatible/foreign')
    require(all(candidate['base'][k] == i['base'][k] for k in ('artifact','release')) and
            all(candidate['kernel'][k] == i['kernel'][k] for k in candidate['kernel']) and
            all(candidate['system'][k] == i['system'][k] for k in ('artifact','composition','manifest','generation')), 'handover differs from planned exact scope')
    baseline = manifests.validate(d['baseline_manifest'])
    require(baseline['id'] == plan['checks']['startup']['description']['selected'],'handover baseline differs')
    if d['baseline_support'] is not None:management.validate(d['baseline_support'])
    facts = d['base_facts'];artifact.fields(facts,('architecture','base_abi','state_layout'))
    require(facts['architecture']+'-linux' == i['platform'] and type(facts['state_layout']) is int and facts['state_layout'] == 1
            and type(facts['base_abi']) is dict and facts['base_abi'],'invalid handover Base ABI/layout')
    b = model.envelope(d['boot_base'],boot_base.FORMAT)
    require(b['base'] == i['base']['artifact'] and b['installation'] == i['installation']
            and b['source_realization'] == candidate['base']['realization'],'boot Base does not realize planned Base')
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
    require(transition.repeat(root,saved,adapters) == saved,
            'System handover inputs changed; prepare again')
    boot_base.inspect(root,d['boot_base'])


def prepare(root, source, plan, *, adapters, tar='tar'):
    """Join the existing preflight to a new immutable boot-only Base realization."""
    require(os.geteuid() == 0,'System handover preparation requires an administrator')
    root = base.target(root,write=True);candidate = transition.boot_fields(plan);p = plan['description']
    require(p['checks']['compatible'],'System preflight blocks handover')
    # Check exact scope before any coordination directory or realization write.
    i = model.inputs(source)
    require(str(root) == p['target'] and p['installation'] == i['installation'] and p['root_uuid'] == i['boot']['root_uuid']
            and all(candidate['system'][k] == i['system'][k] for k in ('artifact','composition','manifest','generation'))
            and all(candidate['base'][k] == i['base'][k] for k in ('artifact','release'))
            and all(candidate['kernel'][k] == i['kernel'][k] for k in candidate['kernel']), 'handover scope differs')
    for name in ('boot','boot/mpm'):
        tx.protected_directory(root/name,write=True);(root/name).mkdir(mode=0o755,exist_ok=True)
    locks = {root/'.artifact-store.lock',root/'artifacts/.lock',*tx.boot_lock_paths(root)}
    # Do not initialize a Ports profile just to acquire a lock. Existing writers
    # are observed again by the constructor and at boot; lock existing Ports state.
    locks = {p for p in locks if p.parent.exists()}
    with tx.resource_locks(locks,modes={root/'.install-lock':0o644}):
        require(transition.repeat(root,plan,adapters) == plan,'boot inputs changed before preparation')
        context = transition.selected_context(root,p['baseline']);old = context['manifest']
        profile = (root/'realizations/system'/context['old']['system']['artifact'][7:]/'profile' if context['native']
                   else root/'system'/old['description']['label'])
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
        from mpm_boot_selection import current
        menu = current(root)[2] if context['native'] else transition.boot.checked_file(root/'boot/mojt/grub.cfg')
        require(hashlib.sha256(menu).hexdigest() == p['selection_sha256']
                and common.state_inputs(root)['evidence'] == p['state'] and system.target_identity(root) == p['target_identity'],
                'selection, state or target changed during preparation')
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
            'guest executable is not supplied by retained immutable content: '+guest)
    return actual


def check(root, source, trees, value, *, provider_roots=None, cache=None, verify_content=True):
    """Re-evaluate current state before writable mounts; never run a provider."""
    d = validate(value,source);i = source['description'];tree = boot_base.inspect(root,d['boot_base'],cache=cache,verify=verify_content)
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
    firmware = None
    if i['boot']['profile'] == model.HARDWARE_PROFILE:
        firmware = hardware.native_firmware(profile)
        point = paths.virtual_file(tree,'/lib/firmware')
        require(point.is_dir() and not any(point.iterdir()),'boot firmware mountpoint must be empty')
    else:require(not (profile/'hardware.json').exists(),'hardware System requires its native boot profile')
    for mount in d['mounts']:require(inventory.path(root,mount['source']).is_dir(),'provider mount source missing')
    for name in ('etc','var','home','root'):inventory.path(root,'state/'+name)
    for shell in [*persistent['base_shells'],*persistent['system_shells']]:guest_file(root,tree,profile,provider_roots,d['mounts'],shell)
    guest_file(root,tree,profile,provider_roots,d['mounts'],'/run/mojt-system/start')
    hostname = common.checked_bytes(root/'state/etc/hostname').decode().strip()
    require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9.-]{0,252}',hostname),'invalid persistent hostname')
    return dict(tree=tree,profile=profile,modules=inventory.path(root,'kernel/installed/'+i['kernel']['artifact'][7:]+'/payload/lib/modules'),
                provider_roots=provider_roots,mounts=d['mounts'],hostname=hostname,source=source,firmware=firmware)


def unit_name(path):
    raw = path.strip('/').encode();result = ''
    for byte in raw:
        result += '-' if byte == 47 else chr(byte) if chr(byte).isascii() and (chr(byte).isalnum() or byte in b':_.') else '\\x%02x'%byte
    if result.startswith('.'):result = '\\x2e'+result[1:]
    return (result or '-')+'.mount'


def enter(root, source, trees, value, cmdline, release, *, runner=None, execute=None, verify_content=False):
    start = time.monotonic()
    checked = (early.verify if verify_content else early.inspect)(root,source,trees,cmdline,release)
    after_reader = time.monotonic()
    context = check(Path(root),source,trees,value,verify_content=verify_content)
    context['deployment'] = early.read(Path(root)/model.slot(checked['deployment'])/'deployment.json')
    require(context['deployment']['id'] == checked['deployment'],'deployment changed before handover')
    context['boot_checks'] = dict(format='mojt-boot-checks-v1',deployment=checked['deployment'],
        mode='full-audit' if verify_content else 'normal',content_verified=verify_content,
        reader_ms=round((after_reader-start)*1000),state_gates_ms=round((time.monotonic()-after_reader)*1000))
    return _enter(Path(root),context,checked,runner=runner,execute=execute)


def login_motd(source):
    """Keep the established Mojt greeting with exact native-v2 identities."""
    i = model.inputs(source)
    logo = (
        "\033[1;36m       |  |  |\n"
        "\033[1;37m   +---+--+--+---+\n"
        "\033[1;30m --\033[1;37m|             |\033[1;30m--\n"
        "\033[1;30m --\033[1;37m|   .-----.   |\033[1;30m--\n"
        "\033[1;30m --\033[1;37m|  (  \033[38;5;214m@@@\033[1;37m  )  |\033[1;30m--\n"
        "\033[1;37m   |   '-----'   |\n"
        "\033[1;37m   |   \033[1;36m|||||||\033[1;37m   |\n"
        "\033[1;37m   +---+--+--+---+\n"
        "\033[1;36m       |  |  |\n\033[0m\n")
    return (logo+'Welcome to Mojt Linux\n\nSystem:       '+i['system']['generation']+
            '\nBase:         '+i['base']['release']+'\nKernel:       '+i['kernel']['release']+
            '\n\nMojt Linux is an experimental distribution.\n')


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
        firmware_point = None
        if context.get('firmware') is not None:
            firmware_point = paths.virtual_file(context['tree'],'/lib/firmware').relative_to(context['tree'])
            bind(context['firmware'],newroot/firmware_point,True)
        runner(['mount','-t','tmpfs','-o','mode=1777,nodev,nosuid','tmpfs',newroot/'tmp']);mounted.append(newroot/'tmp')
        shutil.copyfile(runtime/'bin/busybox',newroot/'run/initramfs/bin/busybox');(newroot/'run/initramfs/bin/busybox').chmod(0o755)
        (newroot/'run/initramfs/bin/sh').symlink_to('busybox')
        shutil.copyfile(runtime/'shutdown',newroot/'run/initramfs/shutdown');(newroot/'run/initramfs/shutdown').chmod(0o755)
        protected = ['/etc','/var','/home','/root','/run/mojt-system','/run/mojt-disk','/'+str(module_point),
                     *['/'+m['target'] for m in context['mounts']],*immutable]
        if firmware_point is not None:protected.append('/'+str(firmware_point))
        for path in protected:
            directory = newroot/'run/systemd/system'/(unit_name(path)+'.d');directory.mkdir(parents=True,exist_ok=True)
            (directory/'10-mojt-exitrd.conf').write_text('[Unit]\nDefaultDependencies=no\n')
        i = context['source']['description'];identity = newroot/'run/mojt'
        # A separate v2 runtime record until the authoritative selector/status
        # join lands. Never synthesize a v1 deployment from these exact inputs.
        running = dict(format='mojt-running-native-v2',deployment=context['deployment'],inputs=context['source']['id'],
                       installation=i['installation'])
        (identity/'native-v2.json').write_bytes(artifact.canonical(running)+b'\n')
        if 'boot_checks' in context:
            (identity/'boot-checks.json').write_bytes(artifact.canonical(context['boot_checks'])+b'\n')
        for name,key in (('native-kernel-artifact','kernel'),('native-base-artifact','base'),('native-system-artifact','system')):
            (identity/name).write_text(i[key]['artifact']+'\n')
        (identity/'issue').write_text('Mojt Linux '+i['system']['generation']+'/'+i['base']['release']+' (x86_64)\n\n')
        (identity/'motd').write_text(login_motd(context['source']))
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
