# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Native-v2 stage admission and one authoritative atomic next-boot menu."""
from contextlib import contextmanager
import copy
import hashlib
import os
from pathlib import Path
import tempfile

import mojt_artifact as artifact
import mojt_system as paths
import mojt_system_manifest as manifests
import mpm_base as base
import mpm_boot_constructor as constructor
import mpm_boot_early as early
import mpm_boot_handover as handover
import mpm_boot_v2 as model
import mpm_boot_v2_store as store
import mpm_management as management
import mpm_native_io as io
import mpm_transaction as tx
from mpm_boot_v2 import record

READY = 'mojt-boot-stage-receipt-v1'
HOOK = b'# Mojt native-v2 boot hook v1\nconfigfile /boot/mpm/grub.cfg\n'
MENU = 'boot/mpm/grub.cfg'
MANAGEMENT_SUPPORT = [{'family':'mpm-boot-v2','read':[1],'write':[1],'capabilities':['exact-system-selection']}]
require = artifact.require


def present(root):
    path = Path(root)/'boot/mojt/grub.cfg'
    if os.path.lexists(Path(root)/MENU):return True
    if not path.exists():return False
    with path.open('rb') as stream:return stream.read(len(HOOK)) == HOOK


def checked(path):
    tx.protected_directory(path.parent,label='native-v2 boot metadata')
    store.checked_file(path,artifact.MAX_METADATA)
    return path.read_bytes()


def _read(path):
    raw = checked(path);value = artifact.parse_json(raw)
    require(raw == artifact.canonical(value)+b'\n','noncanonical stage receipt')
    return value


@contextmanager
def locked(root):
    require(os.geteuid() == 0,'boot publication requires an administrator')
    root = store.target(root,write=True)
    for name in ('boot','boot/mpm'):
        tx.protected_directory(root/name,write=True);(root/name).mkdir(mode=0o755,exist_ok=True)
    locks = {root/'.artifact-store.lock',root/'artifacts/.lock',root/'.install-lock',root/'kernel/.lock',root/'boot/mpm/.lock'}
    ports = root/'state/var/lib/mojt/ports/.lock'
    if ports.parent.exists():locks.add(ports)
    with tx.resource_locks(locks,modes={root/'.install-lock':0o644}):yield root


def ready(root, identifier, *, verify=False, cache=None):
    value = _read(root/'boot/mpm/ready'/(model.identity(identifier)[7:]+'.json'))
    d = model.envelope(value,READY);artifact.fields(d,('installation','deployment','inputs','archive','proof','handover'))
    item = store.inspect(root,identifier,verify=verify);i = item['description']['inputs']
    require(d['deployment'] == identifier and d['inputs'] == i['id'] and d['installation'] == i['description']['installation']
            and d['archive'] == item['description']['initramfs']['description']['archive'],'stage receipt differs from exact slot')
    producer = i['description']['constructor']
    require(producer.get('provider') == 'mojt' and producer.get('identity',{}).get('format') == 'mojt-system-initramfs-constructor-v1',
            'diagnostic or unknown constructor cannot be selected')
    early.proof(d['proof'],i);handover.validate(d['handover'],i)
    if verify:
        early.verify_content(root,i,d['proof'],cache=cache)
        handover.check(root,i,d['proof'],d['handover'],cache=cache)
    return dict(record=item,receipt=value)


def _admit(root, item, built, *, adapters):
    """Private manager join: only an in-process constructor result, never JSON."""
    require(isinstance(built,constructor.CompletedBuild) and built.get('handover_enabled') is True and built.handover is not None,
            'stage admission requires a completed manager-owned System constructor')
    source = item['description']['inputs'];model.deployment(item)
    require(built['binding'] == item['description']['initramfs'] and hashlib.sha256(built['archive']).hexdigest() == built['binding']['description']['archive']['sha256'],
            'completed build differs from slot')
    require(source['description']['constructor']['identity']['code'] ==
            {name:artifact.file_sha(Path(__file__).with_name(name)) for name in paths.MPM_FILES},'constructor code changed before stage admission')
    with locked(root) as root:
        require(store.inspect(root,item['id']) == item,'retained slot changed')
        handover.recheck_locked(root,built.handover,source,adapters)
        cache = {};early.verify_content(root,source,built['proof'],cache=cache)
        handover.check(root,source,built['proof'],built.handover,cache=cache)
        value = record(READY,dict(installation=source['description']['installation'],deployment=item['id'],inputs=source['id'],
            archive=built['binding']['description']['archive'],proof=built['proof'],handover=built.handover))
        model.envelope(value,READY)
        parent = root/'boot/mpm/ready';tx.protected_directory(parent,write=True);parent.mkdir(mode=0o755,exist_ok=True)
        destination = parent/(item['id'][7:]+'.json')
        if os.path.lexists(destination):
            require(_read(destination) == value,'refuse to replace a stage receipt')
            io.sync_directory(parent);return value
        fd,name = tempfile.mkstemp(prefix='.admit-',dir=parent);os.close(fd);temporary = Path(name);temporary.unlink()
        try:io.write_json(temporary,value);tx.publish(temporary,destination)
        finally:
            if temporary.exists():temporary.unlink()
        return value


def stage(root, source, runtime_directory, busybox, work, *, bounds, adapters, contract):
    """MBT/image preparation API: construct, retain and admit; never select."""
    built = constructor.build(root,source,runtime_directory,busybox,work,bounds=bounds,adapters=adapters,handover=contract)
    root = store.target(root);i = model.inputs(source)
    image = root/'kernel/installed'/i['kernel']['artifact'][7:]/'payload/boot'/('vmlinuz-'+i['kernel']['release'])
    item = model.compose(source,built['binding'],image.stat().st_size)
    archive = Path(work)/'completed-initramfs.cpio.gz'
    with archive.open('xb') as stream:stream.write(built['archive']);os.fchmod(stream.fileno(),0o444);os.fsync(stream.fileno())
    store.retain(root,item,image,archive,bounds=bounds,adapters=adapters)
    receipt = _admit(root,item,built,adapters=adapters)
    return dict(deployment=item['id'],stage_receipt=receipt['id'],selection_changed=False,boot_ready=False,
                scope='Complete handover staged; next-boot selection and owner boot acceptance are separate.')


def current(root, *, verify=False, cache=None):
    root = store.target(root)
    require(checked(root/'boot/mojt/grub.cfg') == HOOK,'native-v2 menu has no exact bootloader hook')
    path = root/MENU
    if not os.path.lexists(path):return None,{},None
    raw = checked(path);lines = raw.splitlines()
    require(len(lines)>1 and lines[0]+b'\n' == model.HEADER.encode() and lines[1].startswith(b'# '),'unknown native-v2 selection header')
    value = artifact.parse_json(lines[1][2:]);d = model.selection(value)
    require(d['installation'] == base.store_info(root)['installation'],'foreign native-v2 selection')
    entries = {r['deployment']:ready(root,r['deployment'],verify=verify,cache=cache) for r in d['entries']}
    require(model.parse_menu(raw,{k:v['record'] for k,v in entries.items()}) == value,'selection menu differs')
    return value,entries,raw


def _gates(root, entries):
    cache = {}
    required = management.context(registries=[dict(family='mpm-boot-v2',version=1,capabilities=['exact-system-selection'],evidence='sha256:'+'0'*64)])
    for identifier in entries:
        item = ready(root,identifier,verify=True,cache=cache);source = item['record']['description']['inputs']
        d = item['receipt']['description']['handover']['description']
        profile = root/'realizations/system'/source['description']['system']['artifact'][7:]/'profile'
        candidate = manifests.validate(base.read(profile/'manifest.json'))
        for support in (management.current(),management.retained(profile,candidate),d['baseline_support']):
            report = management.check(support,required)
            require(report['compatible'],'boot registry/recovery compatibility: '+'; '.join(report['errors']))


def _publish(root, value, entries, old_raw):
    require((checked(root/MENU) if os.path.lexists(root/MENU) else None) == old_raw,'boot selection changed before publication')
    raw = model.render(value,{k:v['record'] for k,v in entries.items()})
    if raw == old_raw:
        io.sync_directory((root/MENU).parent);return False
    fd,name = tempfile.mkstemp(prefix='.select-',dir=(root/MENU).parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);os.fchmod(stream.fileno(),0o444);os.fsync(stream.fileno())
        tx.publish(temporary,root/MENU)
    finally:
        if temporary.exists():temporary.unlink()
    return True


def initialize(root, identifier):
    """Fresh unpublished-image API; caller already installed the exact hook."""
    with locked(root) as root:
        require(not os.path.lexists(root/'boot/mpm/format'),'v1 boot registry is not a fresh native-v2 target')
        old,entries,raw = current(root)
        require(old is None,'initial boot choice already exists; use select')
        entries = {identifier:ready(root,identifier)};_gates(root,entries)
        value = record(model.SELECTION,dict(installation=base.store_info(root)['installation'],selected=identifier,previous=None,
            requests=[dict(area=a,state=None) for a in ('base','kernel','system')],entries=[dict(deployment=identifier,path=model.slot(identifier))]))
        _publish(root,value,entries,raw);return value


def select(root, identifier=None, *, expected_selected, rollback=False, dry_run=False, yes=False, area='system'):
    require(os.geteuid() == 0,'boot selection requires an administrator');model.identity(expected_selected)
    require(area in ('base','system','kernel'),'unsupported boot selection area')
    root = store.target(root)
    from mpm_base_transition import read_locks
    def prepare():
        old,entries,raw = current(root);require(old is not None,'native-v2 initial boot selection is missing')
        d = old['description'];require(d['selected'] == expected_selected,'selected deployment changed; repeat preview')
        wanted = d['previous'] if rollback else identifier;require(wanted is not None,'no previous deployment');model.identity(wanted)
        entries[wanted] = ready(root,wanted)
        before = entries[d['selected']]['record']['description']['inputs']['description']
        after = entries[wanted]['record']['description']['inputs']['description']
        preserved = [k for k in ('base','system','kernel','platform','boot','firmware','state_requirements') if k != area]
        require(all(before[k] == after[k] for k in preserved),area+'-only selection must preserve other areas and boot policy')
        _gates(root,entries)
        if wanted == d['selected']:return old,entries,raw
        next_d = copy.deepcopy(d);next_d.update(selected=wanted,previous=d['selected'],entries=[dict(deployment=k,path=model.slot(k)) for k in sorted(entries)])
        return record(model.SELECTION,next_d),entries,raw
    with read_locks(root):value,entries,raw = prepare()
    changed = value['description']['selected'] != expected_selected
    report = dict(selected=value['description']['selected'],previous=value['description']['previous'],changed=changed and not dry_run,
                  dry_run=dry_run,running_changed=False,requests_changed=False,owner_boot_acceptance='pending')
    if dry_run:return report
    if changed and not yes:require(input('Select this exact '+area+' deployment for next boot? [y/N] ').strip().lower() in ('y','yes'),'selection cancelled')
    with locked(root):
        fresh,entries,actual = prepare();require(fresh == value and actual == raw,'selection inputs changed; repeat preview')
        _publish(root,value,entries,raw)
    return report


def observation(root):
    if not present(root) or not os.path.lexists(root/MENU):return None
    value,entries,raw = current(root)
    return dict(family='mpm-boot-v2',version=1,capabilities=['exact-system-selection'],evidence=value['id'])


def status(root, *, running_record=None, verify=False):
    from mpm_boot_status import running as validate_running, description
    import mpm_kernel as kernel
    root = store.target(root)
    value,entries,raw = current(root,verify=verify,cache={} if verify else None)
    running = validate_running(root,running_record,release=os.uname().release) if running_record is not None else None
    active = dict(release=os.uname().release,artifact=None,deployment=None,evidence='unknown')
    if running is not None:
        d = description(running);active.update(artifact=d['kernel']['artifact'],deployment=running['id'],evidence='explicit-runtime-record')
    selected = value['description']['selected'] if value else None
    staged,incomplete = available(root)
    return dict(format='mpm-native-v2-status-v1',selected=selected,
        selected_kernel=description(entries[selected]['record'])['kernel'] if selected else None,
        previous=value['description']['previous'] if value else None,running=active,
        staged=sorted(staged),incomplete=incomplete+([] if value else ['initial selection missing']),
        installed=kernel.status(root/'kernel',verify=verify)['installed'],
        running_is_selected=(running['id'] == selected) if running is not None and selected else None,
        integrity='verified-now' if verify else 'metadata-only',
        compatibility='selection is next boot, never live activation; owner boot acceptance remains separate')


def available(root):
    parent = root/'boot/mpm/ready';entries = {};incomplete = []
    if not parent.exists():return entries,incomplete
    tx.protected_directory(parent,label='native-v2 stage receipts')
    for number,path in enumerate(sorted(parent.iterdir())):
        require(number < model.MAX_ENTRIES,'native-v2 stage inventory limit')
        if path.name.startswith('.admit-'):incomplete.append(path.name);continue
        require(path.name.endswith('.json'),'unknown stage receipt file')
        key = path.name[:-5];model.hexadecimal(key);identifier = 'sha256:'+key
        entries[identifier] = ready(root,identifier)
    return entries,incomplete
