# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Immutable boot-only Base scaffolding, using the reviewed native extractor."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

import mojt_artifact as artifact
import mpm_base as base
import mpm_base_boot as existing
import mpm_boot_inventory as inventory
import mpm_boot_v2 as model
import mpm_native_io as io
import mpm_transaction as tx
from mpm_request_plan import record

FORMAT = 'mojt-boot-base-realization-v1'
require = artifact.require


def inspect(root, value, *, cache=None):
    d = model.envelope(value,FORMAT)
    artifact.fields(d,('installation','base','source_realization','inventory','scaffold','extractor','code'))
    model.installation(d['installation'])
    for key in ('base','source_realization','inventory','code'):model.identity(d[key])
    require(d['installation'] == base.store_info(root)['installation'], 'foreign boot Base')
    folder = inventory.path(root,'realizations/boot-base/'+value['id'][7:])
    require(stat.S_IMODE(io.directory(folder).st_mode) == 0o555 and folder.stat().st_uid == 0
            and {p.name for p in folder.iterdir()} == {'realization.json','tree'}, 'unsealed/incomplete boot Base')
    require(base.read(folder/'realization.json') == value, 'boot Base realization record differs')
    private = io.directory(folder/'tree')
    require(stat.S_IMODE(private.st_mode) == 0o500 and private.st_uid == 0, 'unprotected boot Base tree')
    tree = folder/'tree/rootfs'
    key = str(tree)
    if cache is None or key not in cache:
        require(artifact.digest(inventory.snapshot(tree)) == d['inventory'], 'boot Base content damaged')
        if cache is not None:cache[key] = d['inventory']
    else:require(cache[key] == d['inventory'],'conflicting boot Base proofs')
    return tree


def prepare_locked(root, identifier, *, tar='tar'):
    """Caller holds the existing store/install locks. No state/default effects."""
    require(os.geteuid() == 0,'boot Base preparation requires an administrator')
    root = base.target(root,write=True);body,receipt = base.object_record(root,identifier,verify=True)
    realized = base.realization(root,identifier,receipt,verify=True)
    require(realized is not None,'native Base realization required')
    executable = shutil.which(str(tar));require(executable is not None,'trusted GNU tar is unavailable')
    executable = Path(executable).resolve()
    require('GNU tar' in subprocess.check_output([str(executable),'--version'],text=True),'boot Base requires GNU tar')
    extractor = dict(path=str(executable),sha256=artifact.file_sha(executable))
    code = artifact.digest({n:artifact.file_sha(Path(__file__).with_name(n)) for n in
        ('mpm_boot_base.py','mpm_base_boot.py','mpm_base.py','mpm_boot_inventory.py','mojt_native_image.py')})
    parent = root/'realizations/boot-base';tx.protected_directory(parent,write=True,label='boot Base storage')
    parent.mkdir(mode=0o755,exist_ok=True);io.sync_directory(parent.parent)
    for number,path in enumerate(sorted(parent.iterdir())):
        require(number < 128,'boot Base realization limit')
        if path.name.startswith('.prepare-'):continue
        model.hexadecimal(path.name);value = base.read(path/'realization.json');d = model.envelope(value,FORMAT)
        if all(d.get(k) == v for k,v in dict(base=identifier,source_realization=realized['id'],extractor=extractor,code=code).items()):
            inspect(root,value);io.sync_directory(path);io.sync_directory(parent);return value
    stage = Path(tempfile.mkdtemp(prefix='.prepare-',dir=parent))
    try:
        scaffold = existing.boot_tree(root,identifier,stage,str(executable))
        value = record(FORMAT,dict(installation=base.store_info(root)['installation'],base=identifier,
            source_realization=realized['id'],inventory=artifact.digest(inventory.snapshot(stage/'tree/rootfs')),
            scaffold=scaffold,extractor=extractor,code=code))
        io.write_json(stage/'realization.json',value);stage.chmod(0o555);io.sync_directory(stage)
        destination = parent/value['id'][7:]
        require(not os.path.lexists(destination),'refuse to replace a boot Base realization')
        tx.publish(stage,destination)
        return value
    finally:io.clean_stage(stage)
