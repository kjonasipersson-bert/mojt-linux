# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only Base content and authoritative boot observations; no provider import."""
import os
from pathlib import Path
import re

import mpm_base as base
import mojt_artifact as artifact


def unknown(reason):return dict(state='unknown',artifact=None,release=None,deployment=None,reason=reason)


def observation(value):
    import mpm_deployment as deployment
    d=deployment.validate_deployment(value)
    return dict(state='known',artifact=d['base']['artifact'],release=d['base']['release'],deployment=value['id'])


def selected(root, running_record):
    path=root/'boot/mojt/grub.cfg'
    if not os.path.lexists(path):return unknown('no boot selection record')
    # This is metadata inspection, not a Kernel/module integrity scrub.
    import mpm_kernel_boot as boot
    import mpm_deployment as deployment
    raw=boot.checked_file(path)
    marker=root/'boot/mpm/format'
    if os.path.lexists(marker):
        base.require(boot.checked_file(marker)==(boot.FORMAT+'\n').encode() and raw.startswith(boot.HEADER.encode()),
                     'unsupported/inconsistent managed boot selection')
    if raw.startswith(boot.HEADER.encode()):
        lines=raw.decode('ascii').splitlines()
        base.require(len(lines)>1 and lines[1].startswith('# '),'missing selected deployment metadata')
        state=artifact.parse_json(lines[1][2:].encode())
        artifact.fields(state,('format','selected','previous','entries'))
        base.require(type(state['entries']) is dict and 0<len(state['entries'])<=128,'invalid selected deployment entries')
        entries={}
        for identifier,relative in state['entries'].items():
            folder=boot.entry_path(root,relative);record=base.read(folder/'deployment.json')
            deployment.validate_deployment(record)
            base.require(record['id']==identifier,'selected deployment identity differs')
            entries[identifier]=dict(record=record,relative=relative)
        base.require(boot.menu(state,entries)==raw,'boot menu differs from its selected-state records')
        return observation(entries[state['selected']]['record'])
    if running_record is None:return unknown('unmanaged boot menu; exact next boot is not known')
    d=deployment.validate_deployment(running_record)
    relative='boot/mojt/'+d['system']['generation']+'/'+d['base']['release']
    folder=boot.entry_path(root,relative)
    base.require(base.read(folder/'deployment.json')==running_record,'native baseline differs from running evidence')
    expected=boot.boot.terminal('serial')+'set timeout=10\nset default=0\n'
    expected+=(f"menuentry 'Mojt Base {d['base']['release']} / System {d['system']['generation']} "
               f"(Linux {d['kernel']['release']})' {{\n"
               f"    linux /{relative}/vmlinuz {d['boot']['cmdline']}\n"
               f"    initrd /{relative}/initramfs.cpio.gz\n}}\n")
    base.require(raw==expected.encode('ascii'),'native baseline menu differs; next boot cannot be inferred')
    return observation(running_record)


def status(root, *, verify=False, running_record=None):
    root=base.target(root)
    running=observation(running_record) if running_record is not None else unknown('offline target or missing authoritative running record')
    choice=selected(root,running_record) if root.exists() else unknown('target does not exist')
    info=base.store_info(root)
    installed=[];retained=[];incomplete=[];ids=set()
    if root.exists():
        for path in sorted(root.glob('.artifacts-init-*')):
            base.io.directory(path);incomplete.append(path.name)
    if info:
        directory=root/'artifacts/base/installed'
        for path in sorted(directory.iterdir()) if directory.exists() else ():
            if path.name.startswith('.install-'):
                base.io.directory(path);incomplete.append(str(path.relative_to(root)));continue
            base.require(re.fullmatch('[0-9a-f]{64}',path.name),'unmanaged Base object entry')
            identifier='sha256:'+path.name;ids.add(identifier)
            body,receipt=base.object_record(root,identifier,verify=verify)
            realized=base.realization(root,identifier,receipt,verify=verify)
            row=dict(artifact=identifier,version=body['version'],platform=body['platform'],
                path=str(path),realization=str(base.realization_path(root,identifier)/'tree/rootfs') if realized else None,
                integrity='verified-now' if verify else 'verified-at-installation',
                trust=receipt['description']['trust'],acquisition=receipt['description'].get('acquisition'),
                running=running['artifact']==identifier,next_boot=choice['artifact']==identifier)
            (installed if realized else retained).append(row)
    real=root/'realizations/base'
    if real.exists():
        for path in sorted(real.iterdir()):
            if path.name.startswith('.install-'):
                base.io.directory(path);incomplete.append(str(path.relative_to(root)));continue
            base.require(re.fullmatch('[0-9a-f]{64}',path.name) and 'sha256:'+path.name in ids,'orphaned/unmanaged Base realization')
    complete={r['artifact'] for r in installed}
    for value in (running,choice):
        if value['state']=='known':value['retention']='installed' if value['artifact'] in complete else 'not-in-this-store'
    return dict(format='mpm-base-status-v1',target=str(root),installation=info['installation'] if info else None,
        installed=installed,retained=retained,incomplete=incomplete,running=running,selected=choice,
        running_is_selected=(running['deployment']==choice['deployment']) if running['state']==choice['state']=='known' else None,
        compatibility='installation is not deployment compatibility or boot readiness')
