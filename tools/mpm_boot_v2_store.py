# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Retain byte-bound native-v2 slots. Never install a menu or authorize boot."""
import os
from pathlib import Path
import stat
import tempfile

import mojt_artifact as artifact
import mpm_base as base
import mpm_boot_v2 as model
import mpm_catalog as catalog
import mpm_deployment as deployment
import mpm_kernel as kernel
import mpm_management as management
import mpm_native_io as io
import mpm_system as system
import mpm_transaction as tx

require = artifact.require
FILES = {'vmlinuz', 'initramfs.cpio.gz', 'inputs.json', 'binding.json', 'deployment.json'}


def target(value, *, write=False):
    root = system.target(value, write=write)
    require(root.is_dir(), 'native-v2 target must already exist')
    for name in ('boot', 'boot/mojt', 'boot/mojt/deployments', 'boot/mpm', 'kernel', 'kernel/installed'):
        tx.protected_directory(root / name, write=write, label='native-v2 storage')
    require(base.store_info(root) is not None, 'native installation store required')
    return root


def audit_inputs(root, value, bounds, *, adapters=None):
    """Audit exact installed content, not startup compatibility or constructor code."""
    require(os.geteuid() == 0, 'native-v2 retained content audit requires an administrator')
    d = model.inputs(value);info = base.store_info(root)
    require(info is not None and info['installation'] == d['installation'], 'foreign boot inputs')
    context = catalog.base_context(bounds)
    require(context['base'] == {k:d['base'][k] for k in ('artifact', 'release')}
            and context['platform'] == d['platform'] and artifact.digest(context) == d['base']['bounds_evidence']
            and all(context[k] == d['base'][k] for k in ('kernel_min', 'kernel_max')), 'Base bounds evidence differs')
    body, receipt = base.object_record(root, d['base']['artifact'], verify=True)
    realized = base.realization(root, body['id'], receipt, verify=True)
    require(realized is not None and realized['description']['rootfs_sha256'] == d['base']['rootfs_sha256']
            and body['version']['upstream'] == d['base']['release'] and body['platform'] == d['platform'], 'Base content differs')
    body, unused = system.object_record(root, d['system']['artifact'])
    realized = system.realization(root, body['id'], verify=True)
    require(realized is not None and body['platform'] == d['platform'], 'System generation is not installed for this platform')
    require(all(realized['description'][k] == d['system'][k] for k in ('composition', 'manifest')), 'System composition/manifest differs')
    profile = system.realization_path(root, body['id']) / 'profile'
    manifest = base.read(profile / 'manifest.json')
    require(manifest['description']['label'] == d['system']['generation'], 'System generation label differs')
    refs = system.retained_providers(root, body['id'])
    system.providers(root, refs, adapters, effect='verify')
    system.verify_links(profile, refs, adapters, manifest['description']['provenance'].get('runtime_outputs', []))
    if d['management_required']:
        runtimes = (management.current(), management.retained(profile, manifest))
        for runtime in runtimes:
            require(runtime is not None, 'missing measured management support')
            supported = {r['family']:r for r in runtime['description']['management']}
            for row in d['management_required']:
                actual = supported.get(row['family'])
                require(actual is not None and all(set(row[k]) <= set(actual[k]) for k in ('read', 'write', 'capabilities')),
                        'unsupported boot management requirement: ' + row['family'])
    kernel_path = root / 'kernel/installed' / io.identifier(d['kernel']['artifact'])
    tx.protected_directory(kernel_path, label='native Kernel content')
    body, unused = kernel.object_record(kernel_path, d['kernel']['artifact'], verify=True)
    expected = deployment.kernel_identity(body)
    require(expected == {k:v for k,v in d['kernel'].items() if k != 'upstream'}
            and body['version']['scheme'] == 'dotted-v1' and body['version']['upstream'] == d['kernel']['upstream']
            and body['platform'] == d['platform'], 'Kernel content/upstream differs')


def checked_file(path, maximum):
    info = io.regular(path)
    require(info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o444 and info.st_size <= maximum,
            'unsafe/unbounded retained boot file: ' + str(path))
    return info


def inspect(root, identifier, *, expected_inputs=None, verify=True):
    """Read-only slot integrity. This never reports selected, running or boot-ready."""
    root = target(root);destination = root / model.slot(identifier)
    tx.protected_directory(destination, label='native-v2 slot')
    info = io.directory(destination)
    require(info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o555
            and {p.name for p in destination.iterdir()} == FILES, 'incomplete/unsealed native-v2 slot')
    values = {}
    for name in ('inputs', 'binding', 'deployment'):
        path = destination / (name + '.json');checked_file(path, artifact.MAX_METADATA)
        raw = path.read_bytes();values[name] = artifact.parse_json(raw)
        require(raw == artifact.canonical(values[name]) + b'\n', 'noncanonical boot sidecar')
    d = model.deployment(values['deployment'])
    require(values['deployment']['id'] == identifier and d['inputs'] == values['inputs'] and d['initramfs'] == values['binding'], 'slot sidecars differ')
    require(d['inputs']['description']['installation'] == base.store_info(root)['installation'], 'foreign retained slot')
    require(expected_inputs is None or values['inputs']['id'] == expected_inputs, 'unexpected boot inputs')
    for row in d['files']:
        path = destination / row['path'];info = checked_file(path, model.MAX_BOOT)
        require(info.st_size == row['size'] and (not verify or artifact.file_sha(path) == row['sha256']), 'retained boot bytes damaged')
    return values['deployment']


def result(value, changed, dry_run):
    return dict(deployment=value['id'], inputs=value['description']['inputs']['id'],
                path=model.slot(value['id']), changed=changed, dry_run=dry_run, boot_ready=False,
                selection_changed=False, scope='Byte-bound retained content only; constructor, early reader and startup acceptance remain required.')


def retain(root, value, image, initramfs, *, bounds, adapters=None, dry_run=False):
    """Administrator-only immutable publication; no menu, requests or state effects."""
    d = model.deployment(value);root = target(root, write=not dry_run)
    require(os.geteuid() == 0, 'native-v2 slot retention requires an administrator')
    destination = root / model.slot(value['id'])
    def existing():
        actual = inspect(root, value['id'], expected_inputs=d['inputs']['id'])
        require(actual == value, 'existing deployment differs')
        audit_inputs(root, d['inputs'], bounds, adapters=adapters)
        if not dry_run:
            io.sync_directory(destination);io.sync_directory(destination.parent)
        return result(value, False, dry_run)
    if dry_run:
        from mpm_base_transition import read_locks
        with read_locks(root):
            if management.present(destination):return existing()
            audit_inputs(root, d['inputs'], bounds, adapters=adapters)
            with tempfile.TemporaryDirectory(prefix='mojt-v2-preview-') as temporary:
                freeze(d, image, initramfs, Path(temporary))
        return result(value, False, True)
    for name in ('boot', 'boot/mpm', 'boot/mojt', 'boot/mojt/deployments'):
        path = root / name;path.mkdir(mode=0o755, exist_ok=True)
        tx.protected_directory(path, write=True, label='native-v2 storage')
        io.sync_directory(path.parent)
    locks = {root/'.artifact-store.lock', root/'artifacts/.lock', root/'.install-lock', root/'kernel/.lock', root/'boot/mpm/.lock'}
    with tx.resource_locks(locks, modes={root/'.install-lock':0o644}):
        if management.present(destination):return existing()
        audit_inputs(root, d['inputs'], bounds, adapters=adapters)
        stage = Path(tempfile.mkdtemp(prefix='.retain-', dir=destination.parent))
        try:
            freeze(d, image, initramfs, stage)
            io.write_json(stage/'inputs.json', d['inputs']);io.write_json(stage/'binding.json', d['initramfs'])
            io.write_json(stage/'deployment.json', value)
            stage.chmod(0o555);io.sync_directory(stage)
            require(not management.present(destination), 'refuse to replace a boot slot')
            tx.publish(stage, destination)
        finally:io.clean_stage(stage)
        return result(value, True, False)


def freeze(description, image, initramfs, stage):
    for row in description['files']:
        source = Path(image if row['path'] == 'vmlinuz' else initramfs)
        io.regular(source)
        checksum, size = io.frozen_copy(source, stage/row['path'], maximum=model.MAX_BOOT)
        require((checksum, size) == (row['sha256'], row['size']), 'boot input bytes changed/differ')
