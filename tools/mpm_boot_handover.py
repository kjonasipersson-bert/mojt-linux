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
import tempfile
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
    boot_base.inspect(root,d['boot_base'],verify=base.io.preparation_verify())


def prepare(root, source, plan, *, adapters, tar='tar'):
    """Standalone saved-plan entry: acquire locks and validate before writing."""
    require(os.geteuid() == 0,'System handover preparation requires an administrator')
    root = base.target(root,write=True)
    for name in ('boot','boot/mpm'):
        tx.protected_directory(root/name,write=True);(root/name).mkdir(mode=0o755,exist_ok=True)
    locks = {root/'.artifact-store.lock',root/'artifacts/.lock',*tx.boot_lock_paths(root)}
    locks = {p for p in locks if p.parent.exists()}
    with tx.resource_locks(locks,modes={root/'.install-lock':0o644}):
        require(transition.repeat(root,plan,adapters) == plan,'boot inputs changed before preparation')
        context = transition.selected_context(root,plan['description']['baseline'])
        value = prepare_locked(root,source,plan,context,adapters=adapters,tar=tar)
        import mpm_system as system
        from mpm_boot_constructor import provider_paths
        roots = sorted({p for ref in system.retained_providers(root,source['description']['system']['artifact'])
                        for p in provider_paths(root,ref,adapters)})
        check(root,source,None,value,provider_roots=roots,verify_content=base.io.preparation_verify())
        unchanged(root,plan)
        return value


def unchanged(root, plan):
    """Recheck mutable machine/selection inputs, not immutable compatibility work."""
    from mpm_boot_selection import checked, MENU, HOOK, present
    import mpm_system as system
    p = plan['description']
    if present(root):
        require(checked(root/'boot/mojt/grub.cfg') == HOOK,'native-v2 bootloader hook changed')
        menu = checked(root/MENU)
    else:menu = common.checked_bytes(root/'boot/mojt/grub.cfg')
    require(hashlib.sha256(menu).hexdigest() == p['selection_sha256']
            and common.state_inputs(root)['evidence'] == p['state']
            and system.target_identity(root) == p['target_identity'],
            'selection, state or target changed during preparation')


class PreparedHandover(dict):
    """Checked in-process contract; serialization carries no admission authority."""
    def __init__(self,value,system_value,plan,systems):
        super().__init__(value);self.system=system_value;self.plan=plan;self.systems=systems
        self.checked=value['description']


def prepare_locked(root, source, plan, context, *, adapters, tar='tar'):
    """Construct from a plan/context checked under caller-held transaction locks."""
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
    old = context['manifest']
    profile = (root/'realizations/system'/context['old']['system'].get('artifact')[7:]/'profile' if context['native']
               else root/'system'/old['description']['label'])
    previous=context.get('systems',{}).get(context['old']['system'].get('artifact'))
    support=previous.support if previous is not None else management.retained(profile,old)
    release = tomllib.loads(common.checked_bytes(base.object_path(root,i['base']['artifact'])/'payload/manifest.toml').decode())
    mounts = {}
    import mpm_system as system
    candidate_value=context.get('candidate')
    for ref in (candidate_value.references if candidate_value is not None else system.retained_providers(root,i['system']['artifact'])):
        adapter = adapters[ref['provider']]
        require(hasattr(adapter,'boot_mounts'),'provider has no boot mount contract')
        for row in adapter.boot_mounts(ref,root):
            require(type(row) is dict and type(row.get('target')) is str,'invalid provider mount projection')
            require(row['target'] not in mounts or mounts[row['target']] == row,'conflicting provider mounts')
            mounts[row['target']] = copy.deepcopy(row)
    value = record(FORMAT,dict(inputs=source['id'],preflight=plan,baseline_manifest=old,baseline_support=support,
        base_facts=dict(architecture=release['base']['architecture'],base_abi=release['abi'],state_layout=release['state']['layout_version']),
        boot_base=boot_base.prepare_locked(root,i['base']['artifact'],tar=tar),mounts=[mounts[k] for k in sorted(mounts)]))
    validate(value,source)
    return PreparedHandover(value,candidate_value,plan,tuple(context['systems'].values())) if candidate_value is not None else value


def guest_file(root, tree, profile, provider_roots, mounts, guest, *, components=()):
    """Resolve account/start paths in the future mount namespace, never the host."""
    require(type(guest) is str and guest.startswith('/'),'absolute guest executable required')
    maps = [('/run/mojt-system',profile,True)]
    if components:maps.append(('/run/mojt-disk',root,False))
    maps += [('/run/mojt-disk/'+r['path'],root/r['path'],True) for r in components]
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


def check(root, source, trees, value, *, provider_roots=None, cache=None, verify_content=True, system_value=None):
    """Re-evaluate current state before writable mounts; never run a provider."""
    internal=isinstance(value,PreparedHandover)
    if internal:
        for item in value.systems:item.unchanged()
    d=value.checked if internal else validate(value,source)
    require(d['inputs']==source['id'],'handover inputs differ')
    i=source['description'];tree=boot_base.inspect(root,d['boot_base'],cache=cache,verify=verify_content)
    import mpm_system as system
    accepted=value.system if internal else system_value if system_value is not None else system.CheckedSystem(root,i['system']['artifact'])
    # Boot audits use the tree proof; original archive codecs belong to the
    # running install/audit command, not the isolated initramfs reader.
    profile,candidate=accepted.profile,accepted.manifest
    require(candidate['id']==i['system']['manifest'] and accepted.realization['description']['composition']==i['system']['composition'],
            'handover System manifest differs')
    # Startup acceptance was bound to this exact manifest before admission.
    # Normal boot checks current state, not the immutable baseline comparison.
    if verify_content:
        review=transition.profile_review(d['baseline_manifest'],candidate,profile,candidate_system=accepted)
        require(review==d['preflight']['description']['checks']['startup'] and review['description']['compatible'],'startup review changed')
    else:require(d['preflight']['description']['checks']['startup']['description']['compatible'],'startup preflight blocks boot')
    persistent = common.state_inputs(root)
    facts = dict(format=manifests.CONTEXT,**d['base_facts'],ports=persistent['ports'],required_system_paths=persistent['system_shells'])
    require(persistent['layout'] == facts['state_layout'],'persistent state layout differs')
    compatibility = manifests.check(candidate,facts);require(compatibility['compatible'],'System current-state compatibility: '+'; '.join(compatibility['errors']))
    observed=(management.observe_target(root) if verify_content else management.schemas(root,systems=(accepted,)))
    supports=(management.current(),management.retained(profile,candidate),d['baseline_support']) if verify_content else (accepted.support,d['baseline_support'])
    for support in supports:
        report = management.check(support,observed);require(report['compatible'],'management/recovery compatibility: '+'; '.join(report['errors']))
    require(not transition.defaults(root,profile)['missing'] and not base_boot.defaults_check(root,tree)['missing'],
            'missing defaults require explicit preparation')
    if trees is None:
        # Only prepare() passes roots projected by its freshly verified adapter.
        require(type(provider_roots) is list,'verified provider roots required')
    else:
        proof = early.proof(trees,source)
        provider_roots = [p for row in proof['providers'] if row['reference']['provider'] != 'mojt-system-component' for p in row['trees']]
    import mpm_system as system
    components=accepted.components
    if trees is not None:
        supplied={p:row['reference']['identity']['artifact'] for row in proof['providers']
                  if row['reference']['provider']=='mojt-system-component' for p in row['trees']}
        require(supplied == {r['path']:r['reference']['artifact'] for r in components},'native component proof differs from System')
    require(all(any(p.startswith(m['source']+'/') for m in d['mounts']) for p in provider_roots),'provider tree has no declared mount')
    for name in ('dev','proc','sys','etc','var','home','root','run','tmp','lib/modules',*[m['target'] for m in d['mounts']]):
        point = paths.virtual_file(tree,'/'+name)
        require(point.is_dir() and not any(point.iterdir()),'boot mountpoint must be an empty directory: '+name)
    firmware = None
    if i['boot']['profile'] in model.HARDWARE_PROFILES:
        firmware = hardware.native_firmware(profile,i['boot']['profile'])
        point = paths.virtual_file(tree,'/lib/firmware')
        require(point.is_dir() and not any(point.iterdir()),'boot firmware mountpoint must be empty')
    else:require(not (profile/'hardware.json').exists(),'hardware System requires its native boot profile')
    for mount in d['mounts']:require(inventory.path(root,mount['source']).is_dir(),'provider mount source missing')
    for name in ('etc','var','home','root'):inventory.path(root,'state/'+name)
    writable_root(root,tree,d['mounts'])  # Inspect only; stage never initializes machine state.
    for shell in [*persistent['base_shells'],*persistent['system_shells']]:guest_file(root,tree,profile,provider_roots,d['mounts'],shell,components=components)
    guest_file(root,tree,profile,provider_roots,d['mounts'],'/run/mojt-system/start',components=components)
    hostname = common.checked_bytes(root/'state/etc/hostname').decode().strip()
    require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9.-]{0,252}',hostname),'invalid persistent hostname')
    return dict(tree=tree,profile=profile,modules=inventory.path(root,'kernel/installed/'+i['kernel']['artifact'][7:]+'/payload/lib/modules'),
                provider_roots=provider_roots,components=components,mounts=d['mounts'],hostname=hostname,source=source,firmware=firmware)


def unit_name(path):
    raw = path.strip('/').encode();result = ''
    for byte in raw:
        result += '-' if byte == 47 else chr(byte) if chr(byte).isascii() and (chr(byte).isalnum() or byte in b':_.') else '\\x%02x'%byte
    if result.startswith('.'):result = '\\x2e'+result[1:]
    return (result or '-')+'.mount'


ROOT_MARKER = '.mojt-root-layout.json'
ROOT_DIRECTORIES = ('boot','dev','etc','home','media','mnt','opt','proc','root','run','srv','sys','tmp','var')


def writable_root(root, tree, mounts, *, create=False):
    """Persistent shell of directories; release content is mounted read-only.

    No overlay, mutable Base copy or generation-specific state. Existing roots
    must have our installation/layout marker; never adopt arbitrary contents.
    Only early boot creates this additive state, after current-state checks.
    """
    root=Path(root);tree=Path(tree)
    mutable=set(ROOT_DIRECTORIES)|{row['target'] for row in mounts}
    directories={name:(0o700 if name=='root' else 0o1777 if name=='tmp' else 0o755) for name in mutable}
    projection={};bindings=[]
    require((tree/'usr').is_dir() and not (tree/'usr').is_symlink(),'writable root requires a real Base /usr')
    for source in sorted(tree.iterdir()):
        name=source.name;info=source.lstat()
        require(name!=ROOT_MARKER,'Base conflicts with writable-root marker')
        if name in mutable:
            require(stat.S_ISDIR(info.st_mode) and not any(source.iterdir()),'Base content conflicts with persistent/runtime root path: '+name)
        elif stat.S_ISLNK(info.st_mode):
            target=paths.virtual_file(tree,'/'+name).relative_to(tree).as_posix()
            require(target.split('/')[0] not in mutable and target!=name,'Base root link targets mutable content: '+name)
            projection[name]=dict(type='symlink',target=target)
        else:
            require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode),'unsupported Base root entry: '+name)
            projection[name]=dict(type='directory' if stat.S_ISDIR(info.st_mode) else 'file')
            if stat.S_ISDIR(info.st_mode):directories[name]=0o755
            bindings.append((source,name))
    local=paths.virtual_file(tree,'/usr/local')
    require(local==tree/'usr/local' and local.is_dir() and not any(local.iterdir()),'Base /usr/local must be an empty real mountpoint')
    state=root/'state';folder=state/'rootfs';local_state=state/'local'
    for directory in (state,folder,local_state):
        tx.protected_directory(directory,label='Writable root')
        if os.path.lexists(directory):require(directory.is_dir(),'writable root storage is not a directory')
    expected=dict(format='mojt-writable-root-v1',installation=base.store_info(root)['installation'],projection=projection)
    def inspect(folder):
        require(os.path.lexists(folder/ROOT_MARKER),'unmanaged writable root; explicit migration required')
        require(base.read(folder/ROOT_MARKER)==expected,'writable root layout/installation differs; explicit migration required')
        for name,mode in directories.items():
            point=folder/name;info=point.lstat()
            if name in ('opt','srv','mnt','media','boot'):
                require(stat.S_ISDIR(info.st_mode),'persistent root directory changed type: '+name)
                continue
            require(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==mode,
                    'writable root mountpoint changed: '+name)
            require(not any(point.iterdir()),'writable root mountpoint hides local files: '+name)
        for name,row in projection.items():
            point=folder/name
            if row['type']=='symlink':
                require(point.is_symlink() and os.readlink(point)==row['target'],'writable root Base link changed: '+name)
            elif row['type']=='file':
                info=point.lstat()
                require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1 and info.st_size==0 and stat.S_IMODE(info.st_mode)==0o444,
                        'writable root Base file mountpoint changed: '+name)
    if os.path.lexists(folder):inspect(folder)
    elif create:
        stage=Path(tempfile.mkdtemp(prefix='.rootfs-',dir=state))
        try:
            for name,mode in directories.items():
                (stage/name).mkdir(mode=mode);(stage/name).chmod(mode);tx.sync_directory(stage/name)
            for name,row in projection.items():
                if row['type']=='symlink':(stage/name).symlink_to(row['target'])
                elif row['type']=='file':
                    with (stage/name).open('xb') as stream:os.fchmod(stream.fileno(),0o444);os.fsync(stream.fileno())
            base.io.write_json(stage/ROOT_MARKER,expected);stage.chmod(0o755)
            tx.sync_directory(stage);tx.publish(stage,folder)
        finally:base.io.clean_stage(stage)
        inspect(folder)
    if create:
        if not local_state.exists():local_state.mkdir(mode=0o755);local_state.chmod(0o755)
        tx.sync_directory(local_state);tx.sync_directory(state)
    return dict(root=folder,local=local_state,bindings=bindings)


def enter(root, source, trees, value, cmdline, release, *, runner=None, execute=None, verify_content=False):
    start = time.monotonic()
    checked = (early.verify if verify_content else early.inspect)(root,source,trees,cmdline,release)
    after_reader = time.monotonic()
    context = check(Path(root),source,trees,value,verify_content=verify_content,system_value=getattr(checked,'system',None))
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
        layout=writable_root(root,context['tree'],context['mounts'],create=True)
        bind(layout['root'],newroot)
        for source,name in layout['bindings']:bind(source,newroot/name,True)
        bind(layout['local'],newroot/'usr/local')
        runner(['mount','-t','tmpfs','-o','mode=0755,nodev,nosuid,strictatime','tmpfs',newroot/'run']);mounted.append(newroot/'run')
        for path in ('mojt-system','mojt','initramfs/bin','systemd/system'):(newroot/'run'/path).mkdir(parents=True,exist_ok=True)
        bind(context['profile'],newroot/'run/mojt-system',True)
        for name in ('etc','var','home','root'):bind(root/'state'/name,newroot/name)
        for mount in context['mounts']:bind(root/mount['source'],newroot/mount['target'])
        immutable = []
        for component in context.get('components',[]):
            point=root/component['path'];bind(point,point,True)
            immutable.append('/run/mojt-disk/'+component['path'])
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
        protected = ['/etc','/var','/home','/root','/usr/local','/run/mojt-system','/run/mojt-disk','/'+str(module_point),
                     *['/'+name for unused,name in layout['bindings']],
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
