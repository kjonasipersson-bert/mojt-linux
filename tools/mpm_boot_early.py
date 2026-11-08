# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Trusted initramfs reader. Verification produces paths, never executes target code."""
import json
from pathlib import Path
import stat

import mojt_artifact as artifact
import mpm_base as base
import mpm_boot_inventory as inventory
import mpm_boot_v2 as model
import mpm_boot_v2_store as store
from mpm_request_plan import reference

PROOF = 'mojt-boot-tree-proof-v1'
RUNTIME = 'mojt-boot-python-runtime-v1'
require = artifact.require


def roots(value):
    require(type(value) is list and 0 < len(value) <= 256 and all(type(v) is str for v in value)
            and value == sorted(set(value)), 'invalid boot provider roots')
    for name in value:artifact.relative(name)
    require(all(not any(other != name and name.startswith(other+'/') for other in value) for name in value), 'overlapping boot provider roots')


def read(path):
    info = path.lstat()
    require(path == path.resolve() and stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and info.st_size <= artifact.MAX_METADATA, 'unsafe/unbounded early metadata')
    raw = path.read_bytes();value = artifact.parse_json(raw)
    require(raw == artifact.canonical(value)+b'\n', 'noncanonical early metadata')
    return value


def runtime(value):
    d = model.envelope(value,RUNTIME);artifact.fields(d,('reference','interpreter','trees'))
    reference(d['reference']);require(type(d['interpreter']) is str and d['interpreter'].startswith('/'), 'absolute bootstrap interpreter required')
    artifact.relative(d['interpreter'][1:]);require(type(d['trees']) is dict, 'runtime tree evidence missing');roots(sorted(d['trees']))
    require(any(d['interpreter'][1:] == p or d['interpreter'][1:].startswith(p+'/') for p in d['trees']), 'interpreter outside runtime trees')
    require(all(type(rows) is dict and rows and all(type(r) is dict for r in rows.values()) for rows in d['trees'].values()), 'invalid runtime tree inventory')
    require(sum(r.get('size',0) for rows in d['trees'].values() for r in rows.values()) <= model.MAX_BOOT, 'bootstrap runtime content limit')
    return d


def proof(value, source):
    d = model.envelope(value,PROOF);artifact.fields(d,('inputs','constructor','base','system','modules','providers'))
    i = model.inputs(source)
    require(d['inputs'] == source['id'] and d['constructor'] == i['constructor'], 'boot tree proof differs from embedded inputs')
    expected = dict(base='realizations/base/'+i['base']['artifact'][7:]+'/tree/rootfs',
                    system='realizations/system/'+i['system']['artifact'][7:]+'/profile',
                    modules='kernel/installed/'+i['kernel']['artifact'][7:]+'/payload/lib/modules')
    for key,path in expected.items():
        artifact.fields(d[key],('path','inventory'));require(d[key]['path'] == path and type(d[key]['inventory']) is dict, 'foreign boot tree path/evidence')
    require(type(d['providers']) is list and len(d['providers']) <= 128, 'unbounded boot provider evidence')
    names = []
    for row in d['providers']:
        artifact.fields(row,('reference','trees'));reference(row['reference']);require(type(row['trees']) is dict, 'missing provider trees')
        roots(sorted(row['trees']));names.extend(row['trees'])
    if names:roots(sorted(names))
    return d


def command_line(raw, candidate):
    require(type(raw) is str and len(raw) <= 8192 and '\x00' not in raw, 'invalid Kernel command line')
    parts = raw.split();image = 'BOOT_IMAGE=/'+model.slot(candidate['id'])+'/vmlinuz'
    if parts and parts[0].startswith('BOOT_IMAGE='):
        require(parts.pop(0) == image, 'unexpected bootloader image path')
    require(parts == model.cmdline(candidate).split(), 'Kernel command line differs from exact deployment')


def verify_content(root, source, trees, *, cache=None):
    """Installed tree proof only; does not pretend to observe a running Kernel."""
    d = proof(trees,source)
    for key in ('base','system','modules'):
        try:inventory.verify(inventory.path(root,d[key]['path']),d[key]['inventory'],cache)
        except ValueError as error:raise ValueError('early '+key+' tree differs: '+str(error)) from error
    for provider in d['providers']:
        for path,expected in provider['trees'].items():inventory.verify(inventory.path(root,path),expected,cache)


def verify(root, source, trees, raw_cmdline, running_release):
    """Use embedded input/proof identities before selecting any on-disk tree."""
    root = Path(root).absolute();require(root == root.resolve() and root.is_dir(), 'unsafe early disk root')
    i = model.inputs(source);d = proof(trees,source)
    require(type(raw_cmdline) is str and len(raw_cmdline) <= 8192, 'unbounded Kernel command line')
    selectors = [v for v in raw_cmdline.split() if v.startswith('mojt.deployment=')]
    require(len(selectors) == 1, 'exactly one deployment selector required')
    identifier = 'sha256:'+selectors[0].split('=',1)[1];model.identity(identifier)
    candidate = store.inspect(root,identifier,expected_inputs=source['id'])
    require(candidate['description']['inputs'] == source, 'slot does not bind embedded input record')
    command_line(raw_cmdline,candidate)
    require(running_release == i['kernel']['release'], 'running Kernel release differs from bound inputs')
    verify_content(root,source,trees)
    # This receipt is diagnostic input for the later handover, not runtime status.
    return dict(format='mojt-early-verification-v1',inputs=source['id'],deployment=candidate['id'],
                installation=i['installation'],base=d['base']['path'],system=d['system']['path'],modules=d['modules']['path'],
                providers=[p for row in d['providers'] for p in row['trees']],verified=True,boot_ready=False,
                handover=False,scope='Exact retained content verified; initialization/mount/handover gates remain.')


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True);parser.add_argument('--inputs',required=True)
    parser.add_argument('--proof',required=True);parser.add_argument('--cmdline',default='/proc/cmdline')
    parser.add_argument('--release',default='/proc/sys/kernel/osrelease')
    parser.add_argument('--handover',help='trusted embedded System handover contract')
    args = parser.parse_args()
    if args.handover is not None:
        import os
        import mpm_boot_handover as transfer
        try:
            transfer.enter(args.root,read(Path(args.inputs)),read(Path(args.proof)),read(Path(args.handover)),
                           Path(args.cmdline).read_text(),Path(args.release).read_text().strip())
        except Exception as error:
            print('Mojt native-v2 handover: '+str(error),file=__import__('sys').stderr,flush=True)
            os.execv('/bin/busybox',['busybox','sh'])
        return
    result = verify(args.root,read(Path(args.inputs)),read(Path(args.proof)),
                    Path(args.cmdline).read_text(),Path(args.release).read_text().strip())
    print(json.dumps(result,sort_keys=True))


if __name__ == '__main__':main()
