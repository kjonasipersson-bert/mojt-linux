# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Closed native-v2 boot records and pure GRUB rendering. No selection authority."""
import copy
import hashlib
import json
import re

import mojt_artifact as artifact
import mojt_boot as boot
import mpm_management as management
from mpm_request_plan import reference, identity
from mpm_boot_inventory import MAX_NODES
from mpm_selection import components

INPUTS = 'mojt-boot-inputs-v2'
BINDING = 'mojt-initramfs-binding-v2'
DEPLOYMENT = 'mojt-boot-deployment-v2'
SELECTION = 'mojt-boot-selection-v2'
PROFILE = 'qemu-uefi-virtio-v1'
HEADER = '# Mojt native boot selection v2\n'
MAX_BOOT = 256 * 1024 * 1024
MAX_ENTRIES = 128
require = artifact.require


def canonical(value):
    """Boot evidence permits bounded file maps, independently of Ports wishes.

    The encoding is unchanged: accepted small records keep their exact IDs.
    Inventories have the same node bound as the no-follow tree reader; the
    complete document still fits the existing 16 MiB metadata envelope.
    """
    def check(item, depth=0):
        require(depth <= 64, 'boot metadata nesting limit')
        if type(item) is dict:
            require(len(item) <= MAX_NODES, 'boot metadata object limit: '+str(len(item))+' entries')
            require(all(type(k) is str for k in item), 'boot metadata keys must be strings')
            for k,v in item.items():check(k,depth+1);check(v,depth+1)
        elif type(item) is list:
            require(len(item) <= 4096, 'boot metadata collection limit')
            for v in item:check(v,depth+1)
        elif type(item) is str:
            require(not any(0xD800 <= ord(c) <= 0xDFFF for c in item), 'invalid boot metadata Unicode')
        else:
            require(item is None or type(item) in (bool,int), 'unsupported boot metadata scalar')
            if type(item) is int:require(-(2**63) <= item < 2**63, 'boot metadata integer range')
    check(value)
    raw=json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode('ascii')
    require(len(raw) < artifact.MAX_METADATA, 'boot metadata size limit: '+str(len(raw))+
            ' bytes (must be below '+str(artifact.MAX_METADATA)+')')
    return raw


def record(fmt, description):
    body=dict(format=fmt,description=description)
    try:raw=canonical(body)
    except ValueError as error:raise ValueError('boot record '+fmt+': '+str(error)) from error
    return dict(**body,id='sha256:'+hashlib.sha256(raw).hexdigest())


def envelope(value, fmt):
    artifact.fields(value, ('format', 'id', 'description'))
    require(value['format'] == fmt and value == record(fmt, value['description']), 'unsupported/corrupt ' + fmt)
    require(len(artifact.canonical(value)) < artifact.MAX_METADATA, 'unbounded boot metadata')
    return copy.deepcopy(value['description'])


def hexadecimal(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'invalid boot SHA256')


def installation(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{32}', value), 'invalid installation UUID')


def arguments(values):
    require(type(values) is list and len(values) <= 3 and all(type(v) is str for v in values), 'invalid boot arguments')
    require(all(re.fullmatch(r'(?:quiet|loglevel=[0-7]|panic=[0-9]{1,6})', v) for v in values), 'unsupported/reserved boot argument')
    keys = [v.split('=', 1)[0] for v in values]
    require(keys == sorted(set(keys)), 'boot arguments must have sorted unique keys')


def padded_version(value):
    parts = components(value)
    return parts + (0,) * (3 - len(parts))


def inputs(value):
    d = envelope(value, INPUTS)
    artifact.fields(d, ('installation', 'platform', 'layout', 'base', 'system', 'kernel', 'firmware', 'boot',
                        'constructor', 'state_requirements', 'management_required'))
    installation(d['installation'])
    require(d['platform'] == 'x86_64-linux' and d['layout'] == 'native-v2', 'unsupported native-v2 platform/layout')
    b = d['base'];artifact.fields(b, ('artifact', 'release', 'rootfs_sha256', 'kernel_min', 'kernel_max', 'bounds_evidence'))
    identity(b['artifact']);identity(b['bounds_evidence']);boot.generation(b['release']);hexadecimal(b['rootfs_sha256'])
    for key in ('kernel_min', 'kernel_max'):
        require(len(components(b[key])) in (2, 3), 'Kernel bound must be major.minor[.patch]')
    require(padded_version(b['kernel_min']) <= padded_version(b['kernel_max']), 'inverted Kernel bounds')
    s = d['system'];artifact.fields(s, ('artifact', 'composition', 'manifest', 'generation'))
    for key in ('artifact', 'composition', 'manifest'):identity(s[key])
    boot.generation(s['generation'])
    k = d['kernel'];artifact.fields(k, ('artifact', 'release', 'upstream', 'image_sha256', 'modules_digest'))
    identity(k['artifact']);identity(k['modules_digest']);hexadecimal(k['image_sha256']);boot.generation(k['release'])
    require(len(components(k['upstream'])) in (2, 3), 'Kernel upstream must be numeric metadata')
    # Pad versions so 6.12 and 6.12.0 have the same numerical meaning.
    require(padded_version(b['kernel_min']) <= padded_version(k['upstream']) <= padded_version(b['kernel_max']), 'Kernel outside exact Base bounds')
    require(d['firmware'] == [], 'firmware requirements are unsupported by this first native-v2 profile')
    require(d['state_requirements'] == [], 'state-schema requirements need a supported native-v2 handler')
    policy = d['boot'];artifact.fields(policy, ('root_uuid', 'console', 'profile', 'extra_args'))
    boot.fs_uuid(policy['root_uuid'])
    require(policy['console'] == 'serial' and policy['profile'] == PROFILE, 'unsupported native-v2 boot profile')
    arguments(policy['extra_args']);reference(d['constructor'])
    rows = d['management_required']
    require(type(rows) is list and len(rows) <= MAX_ENTRIES, 'unbounded management requirements')
    names = []
    for row in rows:
        artifact.fields(row, ('family', 'read', 'write', 'capabilities'))
        require(management.token(row['family']), 'invalid management family');names.append(row['family'])
        management.access(row)
        require(row['read'] and row['write'], 'explicit read/write management requirements needed')
        capabilities = row['capabilities']
        require(type(capabilities) is list and len(capabilities) <= MAX_ENTRIES and all(management.token(c) for c in capabilities)
                and capabilities == sorted(set(capabilities)), 'invalid management capability requirements')
    require(names == sorted(set(names)), 'management requirements must be sorted and unique')
    return d


def archive(value):
    artifact.fields(value, ('sha256', 'size'));hexadecimal(value['sha256'])
    require(type(value['size']) is int and 0 < value['size'] <= MAX_BOOT, 'invalid boot-file size')


def binding(value, expected=None):
    d = envelope(value, BINDING);artifact.fields(d, ('inputs', 'archive', 'constructor'))
    identity(d['inputs']);archive(d['archive']);reference(d['constructor'])
    if expected is not None:
        source = inputs(expected)
        require(d['inputs'] == expected['id'] and d['constructor'] == source['constructor'], 'initramfs does not bind exact boot inputs/constructor')
    return d


def deployment(value):
    d = envelope(value, DEPLOYMENT);artifact.fields(d, ('inputs', 'initramfs', 'files'))
    source = inputs(d['inputs']);init = binding(d['initramfs'], d['inputs'])
    require(type(d['files']) is list and len(d['files']) == 2, 'exactly two boot files required')
    names = []
    for row in d['files']:
        artifact.fields(row, ('path', 'sha256', 'size'));archive({k:row[k] for k in ('sha256', 'size')});names.append(row['path'])
    require(names == ['initramfs.cpio.gz', 'vmlinuz'], 'unsupported/unordered boot-file inventory')
    require({k:d['files'][0][k] for k in ('sha256', 'size')} == init['archive'], 'initramfs file differs from binding')
    require(d['files'][1]['sha256'] == source['kernel']['image_sha256'], 'Kernel image differs from inputs')
    return d


def compose(source, initramfs, image_size):
    d = inputs(source);binding(initramfs, source)
    value = record(DEPLOYMENT, dict(inputs=copy.deepcopy(source), initramfs=copy.deepcopy(initramfs), files=[
        dict(path='initramfs.cpio.gz', **initramfs['description']['archive']),
        dict(path='vmlinuz', sha256=d['kernel']['image_sha256'], size=image_size)]))
    deployment(value);return value


def slot(identifier):return 'boot/mojt/deployments/' + identity(identifier).split(':')[1]


def selection(value):
    d = envelope(value, SELECTION);artifact.fields(d, ('installation', 'selected', 'previous', 'requests', 'entries'))
    installation(d['installation']);identity(d['selected'])
    if d['previous'] is not None:identity(d['previous'])
    require(d['previous'] != d['selected'], 'selected and previous must differ')
    require(type(d['requests']) is list and len(d['requests']) == 3, 'exact Base/Kernel/System request roots required')
    areas = []
    for row in d['requests']:
        artifact.fields(row, ('area', 'state'));areas.append(row['area'])
        if row['state'] is not None:identity(row['state'])
    require(areas == ['base', 'kernel', 'system'], 'request areas must be sorted and unique')
    require(type(d['entries']) is list and 0 < len(d['entries']) <= MAX_ENTRIES, 'unbounded boot entries')
    identifiers = []
    for row in d['entries']:
        artifact.fields(row, ('deployment', 'path'));identity(row['deployment']);identifiers.append(row['deployment'])
        require(row['path'] == slot(row['deployment']), 'entry path does not bind its exact deployment')
    require(identifiers == sorted(set(identifiers)) and d['selected'] in identifiers
            and (d['previous'] is None or d['previous'] in identifiers), 'inconsistent boot selection entries')
    return d


def cmdline(value):
    d = deployment(value);i = d['inputs']['description'];policy = i['boot']
    return ('console=ttyS0,115200 rdinit=/init root=UUID=' + policy['root_uuid'] +
            ' mojt.deployment=' + value['id'].split(':')[1] +
            ((' ' + ' '.join(policy['extra_args'])) if policy['extra_args'] else ''))


def render(value, entries):
    """Pure complete menu bytes; caller must not treat rendering as publication."""
    d = selection(value)
    require(type(entries) is dict and set(entries) == {r['deployment'] for r in d['entries']}, 'menu entries differ from selection')
    policy = None
    text = HEADER + '# ' + artifact.canonical(value).decode('ascii') + '\n' + boot.terminal('serial')
    text += "set timeout=10\nset default='mpm-" + d['selected'].split(':')[1] + "'\n"
    for row in d['entries']:
        record = entries[row['deployment']];actual = deployment(record)
        require(record['id'] == row['deployment'], 'menu deployment identity differs')
        i = actual['inputs']['description']
        require(i['installation'] == d['installation'], 'menu contains a foreign installation')
        machine = (i['platform'], i['boot']['root_uuid'], i['boot']['console'], i['boot']['profile'])
        if policy is None:
            policy = machine
            text += 'search --no-floppy --fs-uuid --set=root ' + i['boot']['root_uuid'] + '\n'
        require(machine == policy, 'menu mixes machine boot policies')
        prefix = '/' + row['path']
        text += ("menuentry 'Mojt Base " + i['base']['release'] + ' / System ' + i['system']['generation'] +
                 ' / Linux ' + i['kernel']['release'] + ' / ' + record['id'][7:19] + "' --id 'mpm-" + record['id'][7:] + "' {\n" +
                 '    linux ' + prefix + '/vmlinuz ' + cmdline(record) + '\n' +
                 '    initrd ' + prefix + '/initramfs.cpio.gz\n}\n')
    raw = text.encode('ascii')
    require(len(raw) <= artifact.MAX_METADATA, 'generated boot menu exceeds metadata limit')
    return raw


def parse_menu(raw, entries):
    require(type(raw) is bytes and len(raw) <= artifact.MAX_METADATA, 'invalid native-v2 menu')
    lines = raw.splitlines()
    require(len(lines) >= 2 and lines[0] + b'\n' == HEADER.encode() and lines[1].startswith(b'# '), 'unknown native-v2 menu header')
    value = artifact.parse_json(lines[1][2:]);selection(value)
    require(render(value, entries) == raw, 'menu bytes differ from complete selection record')
    return value
