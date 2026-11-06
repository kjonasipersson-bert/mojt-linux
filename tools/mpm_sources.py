# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Named owner-authorized sources, frozen snapshots and native cache acquisition."""
import hashlib
import os
from pathlib import Path
import uuid

import mpm_native_cache as cache
from mpm_request_plan import identity, record

FORMAT = 'mojt-source-registry-v1'
REGISTRATION = 'mojt-source-registration-v1'
PLAN = 'mojt-source-change-plan-v1'
MAX_FROZEN = 4 * cache.MAX_META
require = cache.require


def encoded(value):
    return cache.model.canonical(value) + b'\n'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def registry(path, *, write=False):
    root = cache.tx.protected_directory(path, write=write, label='Sources')
    if root.exists() and set(p.name for p in root.iterdir()) - {'.lock'}:
        require(cache.artifact.parse_json(cache.read_file(root, 'registry.json')) ==
                dict(format=FORMAT), 'unsupported source registry')
        for name in ('objects', 'metadata', 'names'):
            require((root / name).is_dir(), 'incomplete source registry')
            cache.tx.protected_directory(root / name, label='Sources')
    return root


def object_path(identifier):
    return 'objects/' + identity(identifier).split(':')[1] + '.json'


def read_object(root, identifier, fmt):
    value = cache.artifact.parse_json(cache.read_file(root, object_path(identifier)))
    cache.envelope(value, fmt)
    require(value['id'] == identifier, 'retained source object identity differs')
    return value


def current(root, name):
    cache.model.token(name)
    root = registry(root)
    directory = root / 'names' / name
    cache.tx.protected_directory(directory, label='Source name')
    pointer = directory / 'current'
    if not os.path.lexists(pointer):
        return None
    require(pointer.is_symlink(), 'source current is not a pointer')
    target = os.readlink(pointer)
    prefix = '../../objects/'
    require(target.startswith(prefix) and target.endswith('.json'), 'invalid source pointer')
    identifier = 'sha256:' + target[len(prefix):-5]
    value = read_object(root, identifier, REGISTRATION)
    d = value['description']
    cache.fields(d, ('name', 'source', 'policy', 'snapshot'))
    require(d['name'] == name, 'source registration name differs')
    identity(d['source']); identity(d['policy'])
    if d['snapshot'] is not None:
        identity(d['snapshot'])
    return value


def configuration(root, registration):
    d = registration['description']
    source = read_object(root, d['source'], 'mojt-source-v1')
    policy_file = root / object_path(d['policy'])
    cache.local_source(policy_file, source)
    require(source['description']['name'] == d['name'] and
            source['description']['trust']['policy'] == d['policy'], 'registration/source binding differs')
    return source, policy_file


def load(root, name, snapshot=None):
    root = registry(root)
    registration = current(root, name)
    require(registration is not None, 'source is not registered')
    source, policy_file = configuration(root, registration)
    selected = snapshot or registration['description']['snapshot']
    require(selected is not None, 'source requires an explicit metadata update')
    snap = read_object(root, selected, 'mojt-source-snapshot-v1')
    d = snap['description']
    catalog_raw = cache.read_file(root, 'metadata/' + cache.hex_sha(d['catalog']['sha256']))
    mapping_raw = cache.read_file(root, 'metadata/' + cache.hex_sha(d['acquisition']['sha256']))
    args = dict(policy_file=policy_file, source=source, snapshot=snap,
                catalog_bytes=catalog_raw, acquisition_bytes=mapping_raw)
    cache.metadata(**args)
    return args


def inspect(root, name, snapshot=None):
    root = registry(root)
    registration = current(root, name)
    require(registration is not None, 'source is not registered')
    source, _ = configuration(root, registration)
    args = load(root, name, snapshot) if snapshot or registration['description']['snapshot'] else None
    return dict(format='mojt-source-status-v1', registration=registration,
                source=source, snapshot=args['snapshot'] if args else None,
                catalog=cache.artifact.parse_json(args['catalog_bytes']) if args else None,
                refresh_required=args is None, snapshot_age='unknown',
                local_directory_available=Path(source['description']['location']['path']).is_dir())


def list_sources(root):
    root = registry(root)
    names = root / 'names'
    if not names.exists():
        return []
    result = []
    for directory in sorted(names.iterdir()):
        if current(root, directory.name) is not None:
            result.append(inspect(root, directory.name))
    return result


def change_plan(root, name, before, after, raw=()):
    return record(PLAN, dict(root=str(root), name=name,
                  before=before['id'] if before else None, after=after,
                  metadata_sha256=sorted({digest(value) for value in raw})))


def prepare_add(root, name, *, source, policy_file, replace=False):
    root = registry(root)
    _, _, policy = cache.local_source(policy_file, source)
    require(source['description']['name'] == name, 'source name differs')
    before = current(root, name)
    d = dict(name=name, source=source['id'], policy=policy['id'], snapshot=None)
    if before:
        old = before['description']
        if (old['source'], old['policy']) == (d['source'], d['policy']):
            d = old
        else:
            require(replace, 'source exists; reconfiguration requires --replace')
    return change_plan(root, name, before, d)


def frozen_update(root, name, *, snapshot_file='snapshot.json', catalog_file='catalog.json',
                  acquisition_file='acquisition-map.json'):
    root = registry(root)
    before = current(root, name)
    require(before is not None, 'source is not registered')
    source, policy_file = configuration(root, before)
    directory = source['description']['location']['path']
    snapshot_raw = cache.read_file(directory, snapshot_file)
    catalog_raw = cache.read_file(directory, catalog_file)
    mapping_raw = cache.read_file(directory, acquisition_file)
    snapshot = cache.artifact.parse_json(snapshot_raw)
    args = dict(policy_file=policy_file, source=source, snapshot=snapshot,
                catalog_bytes=catalog_raw, acquisition_bytes=mapping_raw)
    _, _, policy, catalog, mapping = cache.metadata(**args)
    raw = [catalog_raw, mapping_raw]
    total = len(snapshot_raw) + sum(map(len, raw))
    require(total <= MAX_FROZEN, 'source metadata exceeds frozen byte limit')
    kind = 'port' if catalog.area == 'ports' else catalog.area
    require(kind in cache.artifact.KINDS, 'unsupported native catalog area')
    refs = set()
    for offer in mapping['description']['offers']:
        require(offer['reference']['provider'] == 'native', 'source update needs an adapter for non-native offers')
        evidence = offer['descriptor']
        total += evidence['size']
        require(total <= MAX_FROZEN, 'source metadata exceeds frozen byte limit')
        descriptor = cache.read_file(directory, evidence['path'])
        cache.descriptor_binding(descriptor, offer, catalog, policy['description'], kind)
        for encoding in offer['archives']:
            cache.size(encoding['size'], policy['description']['max_archive'])
        refs.add(offer['reference']['artifact'])
        raw.append(descriptor)
    require(all(c.backend == 'native' and c.artifact in refs for c in catalog.candidates),
            'catalog candidate has no validated native offer')
    after = dict(before['description'], snapshot=snapshot['id'])
    return change_plan(root, name, before, after, raw), [snapshot, mapping], raw


def prepare_update(root, name, **files):
    return frozen_update(root, name, **files)[0]


def publish(root, plan, objects, raws, *, sync=cache.tx.sync_directory):
    """Caller holds the registry lock. Immutable evidence precedes one pointer."""
    d = cache.envelope(plan, PLAN)
    before = current(root, d['name'])
    require((before['id'] if before else None) == d['before'], 'source baseline changed')
    after = record(REGISTRATION, d['after'])
    if before == after:
        return dict(changed=False, registration=before)
    for value in objects + [after]:
        cache.retain_bytes(root, object_path(value['id']), encoded(value), sync=sync)
    for raw in raws:
        cache.retain_bytes(root, 'metadata/' + digest(raw), raw, sync=sync)
    directory = root / 'names' / d['name']
    directory.mkdir(mode=0o755, exist_ok=True)
    sync(root / 'names')
    temporary = directory / ('.current-' + uuid.uuid4().hex)
    temporary.symlink_to('../../' + object_path(after['id']))
    try:
        cache.tx.publish(temporary, directory / 'current', sync=sync)
    finally:
        temporary.unlink(missing_ok=True)
    return dict(changed=True, registration=after)


def initialize(root, *, sync):
    if (root / 'registry.json').exists():
        return
    require(set(p.name for p in root.iterdir()) <= {'.lock'}, 'unmanaged source directory')
    for name in ('objects', 'metadata', 'names'):
        (root / name).mkdir(mode=0o755)
    cache.retain_bytes(root, 'registry.json', encoded(dict(format=FORMAT)), sync=sync)
    sync(root); sync(root.parent)


def add(root, name, plan, *, source, policy_file, replace=False, sync=cache.tx.sync_directory):
    require(prepare_add(root, name, source=source, policy_file=policy_file, replace=replace) == plan,
            'source registration plan changed')
    root = registry(root, write=True); root.mkdir(mode=0o755, exist_ok=True)
    with cache.tx.file_lock(root / '.lock', mode=0o644):
        initialize(root, sync=sync)
        require(prepare_add(root, name, source=source, policy_file=policy_file, replace=replace) == plan,
                'source registration plan changed')
        _, _, policy = cache.local_source(policy_file, source)
        return publish(root, plan, [source, policy], [], sync=sync)


def update(root, name, plan, *, sync=cache.tx.sync_directory, **files):
    require(prepare_update(root, name, **files) == plan, 'source update plan changed')
    root = registry(root, write=True)
    with cache.tx.file_lock(root / '.lock', mode=0o644):
        actual, objects, raws = frozen_update(root, name, **files)
        require(actual == plan, 'source update plan changed')
        return publish(root, plan, objects, raws, sync=sync)


def acquisition_inputs(root, name, artifact, *, kind, archive_sha256, snapshot=None):
    root = registry(root)
    args = load(root, name, snapshot)
    mapping = cache.artifact.parse_json(args['acquisition_bytes'])
    ref = dict(provider='native', artifact=identity(artifact))
    offers = [o for o in mapping['description']['offers'] if o['reference'] == ref]
    require(len(offers) == 1, 'artifact absent from accepted snapshot')
    raw = cache.read_file(root, 'metadata/' + offers[0]['descriptor']['sha256'])
    return dict(args, ref=ref, kind=kind, archive_sha256=archive_sha256, descriptor_bytes=raw)


def prepare_fetch(root, cache_root, name, artifact, **selection):
    separate_roots(root, cache_root)
    return cache.prepare(cache_root, **acquisition_inputs(root, name, artifact, **selection))


def separate_roots(root, target):
    root = registry(root)
    target = cache.cache_root(target)
    require(root != target and root not in target.parents and target not in root.parents,
            'source registry and cache roots must be separate')


def fetch(root, cache_root, name, artifact, plan, **selection):
    separate_roots(root, cache_root)
    root = registry(root, write=True)
    # Hold authorization stable across the slow cache operation. A newer snapshot
    # of the same source does not revoke an explicitly selected retained snapshot.
    with cache.tx.file_lock(root / '.lock', shared=True, create=False):
        args = acquisition_inputs(root, name, artifact, **selection)
        return cache.acquire(cache_root, plan, **args)
