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
    from mpm_boot_status import description,unwrap
    value=unwrap(value);d=description(value)
    return dict(state='known',artifact=d['base']['artifact'],release=d['base']['release'],deployment=value['id'])


def selected(root, running_record):
    from mpm_boot_status import selected as inspect
    result = inspect(root, running_record)
    return observation(result['record']) if result['state'] == 'known' else unknown(result['reason'])


def status(root, *, verify=False, running_record=None):
    root=base.target(root)
    from mpm_boot_status import running as validate_running
    running_record=validate_running(root,running_record)
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
