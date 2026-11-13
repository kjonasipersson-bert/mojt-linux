# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Closed local bootstrap inputs, carried as data on an installer image."""
import json
import os
from pathlib import Path
import shutil

import mojt_artifact as artifact
import mojt_hardware as hardware
import mojt_system as paths

FORMAT = 'mojt-bootstrap-inputs-v1'
LOCATION = 'state/var/lib/mojt/installer-inputs'
REQUIRED = {'base.tar.zst', 'base-context.json', 'kernel-registry', 'system-payload', 'busybox'}
BOUND = {'--base-package', '--base-artifact', '--base-context', '--kernel-registry',
         '--kernel-artifact', '--system-payload', '--busybox', '--firmware-root', '--hardware-profile'}
require = artifact.require


def resource_hash(directory, name):
    path = directory/name
    tree = name in ('kernel-registry','system-payload','firmware')
    require(not path.is_symlink() and (path.is_dir() if tree else path.is_file()),
            'invalid installer resource type: '+name)
    if tree and name != 'system-payload':hardware.checked_tree(path)
    # A System export contains guest-rooted links, including /nix/store links.
    # Inventory their literal text without resolving against the host. The
    # System reader interprets guest paths when verifying/constructing inputs.
    # tree_hash also rejects special files and never follows directory links.
    return paths.tree_hash(path)


def write(destination, *, archive, bounds, registry, payload, busybox, firmware, args):
    """Only frozen artifacts/provider inputs are copied; never host account state."""
    destination.mkdir(mode=0o755)
    shutil.copyfile(archive, destination/'base.tar.zst')
    (destination/'base-context.json').write_bytes(artifact.canonical(bounds)+b'\n')
    shutil.copytree(registry, destination/'kernel-registry', symlinks=True)
    shutil.copytree(payload, destination/'system-payload', symlinks=True)
    shutil.copyfile(busybox, destination/'busybox'); (destination/'busybox').chmod(0o755)
    if firmware is not None:shutil.copytree(firmware, destination/'firmware', symlinks=True)
    names = REQUIRED | ({'firmware'} if firmware is not None else set())
    body = dict(format=FORMAT, resources={name:resource_hash(destination,name) for name in sorted(names)},
                base=args.base_artifact, kernel=args.kernel_artifact,
                defaults=dict(system_generation=args.system_generation, system_version=args.system_version,
                              system_revision=args.system_revision, with_build_tools=args.with_build_tools,
                              hardware_profile=args.hardware_profile))
    body['id'] = artifact.digest(body)
    (destination/'inputs.json').write_bytes(artifact.canonical(body)+b'\n')
    (destination/'inputs.json').chmod(0o444)
    return body


def read(directory):
    directory = Path(os.path.abspath(directory))
    require(directory == directory.resolve() and directory.is_dir(), 'canonical installer input directory required')
    metadata = directory/'inputs.json'
    require(not metadata.is_symlink() and metadata.is_file() and metadata.stat().st_size <= 65536,
            'bounded regular installer input record required')
    value = artifact.parse_json(metadata.read_bytes())
    artifact.fields(value, ('format','resources','base','kernel','defaults','id'))
    body = {k:v for k,v in value.items() if k != 'id'}
    require(value['format'] == FORMAT and value['id'] == artifact.digest(body), 'installer input identity differs')
    require(type(value['resources']) is dict and set(value['resources']) in (REQUIRED, REQUIRED|{'firmware'}),
            'unsupported installer resources')
    require({p.name for p in directory.iterdir()} == set(value['resources'])|{'inputs.json'},
            'unexpected or missing installer input')
    for name, expected in value['resources'].items():
        require(type(expected) is str and resource_hash(directory,name) == expected,
                'installer input changed: ' + name)
    defaults = value['defaults']
    artifact.fields(defaults, ('system_generation','system_version','system_revision','with_build_tools','hardware_profile'))
    require(type(defaults['with_build_tools']) is bool and defaults['hardware_profile'] in (None,hardware.PROFILE),
            'unsupported installer defaults')
    require(('firmware' in value['resources']) == (defaults['hardware_profile'] is not None), 'installer firmware policy differs')
    for name in ('base','kernel'):
        require(type(value[name]) is str and len(value[name]) == 71 and value[name].startswith('sha256:') and
                all(c in '0123456789abcdef' for c in value[name][7:]), 'full installer artifact identity required')
    return directory, value


def expand(argv, *, details=None):
    """Expand only fixed data options. No shell, hooks or candidate Python code."""
    if any(a in ('-h','--help') for a in argv):return argv
    positions = [i for i,a in enumerate(argv) if a == '--inputs' or a.startswith('--inputs=')]
    if not positions:return argv
    require(len(positions) == 1, 'specify --inputs once')
    index = positions[0]; argument = argv[index]
    if argument == '--inputs':
        require(index+1 < len(argv) and not argv[index+1].startswith('--'), '--inputs requires a directory')
        name = argv[index+1]; rest = argv[:index]+argv[index+2:]
    else:name = argument.split('=',1)[1]; rest = argv[:index]+argv[index+1:]
    require(not any(a.split('=',1)[0] in BOUND for a in rest), 'do not mix --inputs with bound artifact/provider input options')
    directory, value = read(name)
    if details is not None:details.update(id=value['id'], directory=str(directory))
    pairs = {'--base-package':directory/'base.tar.zst', '--base-artifact':value['base'],
             '--base-context':directory/'base-context.json', '--kernel-registry':directory/'kernel-registry',
             '--kernel-artifact':value['kernel'], '--system-payload':directory/'system-payload',
             '--busybox':directory/'busybox'}
    defaults = value['defaults']
    if defaults['hardware_profile'] is not None:
        pairs.update({'--hardware-profile':defaults['hardware_profile'], '--firmware-root':directory/'firmware'})
    for name in ('system_generation','system_version','system_revision'):
        flag = '--'+name.replace('_','-')
        if not any(a == flag or a.startswith(flag+'=') for a in rest):pairs[flag] = defaults[name]
    result = [part for name,v in pairs.items() for part in (name,str(v))]
    if defaults['with_build_tools']:result.append('--with-build-tools')
    return result+rest
