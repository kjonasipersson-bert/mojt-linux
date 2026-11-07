# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Frozen named source -> exact native System bundle -> existing content installer."""
import json
import os
import sys

import mpm_base as base
import mpm_sources as sources
import mpm_system as system

FORMAT = 'mojt-system-source-install-plan-v1'


def targets(root, source_root, cache_root):
    root = system.target(root, write=True);sources.separate_roots(source_root, cache_root)
    for path in (sources.registry(source_root), sources.cache.cache_root(cache_root)):
        for mutable in (root / 'artifacts', root / 'realizations', root / 'retained'):
            base.require(path != mutable and path not in mutable.parents and mutable not in path.parents,
                         'System content, sources and cache must be separate')
    return root


def inputs(source_root, cache_root, name, identifier, checksum, snapshot):
    args = sources.acquisition_inputs(source_root, name, identifier, kind='system', archive_sha256=checksum, snapshot=snapshot)
    unused, acquisition, body, _, _ = sources.cache.inputs(cache_root, **args)
    return args, acquisition, body


def prepare(root, source_root, cache_root, name, identifier, *, archive_sha256, snapshot=None):
    root = targets(root, source_root, cache_root)
    args, acquisition, body = inputs(source_root, cache_root, name, identifier, archive_sha256, snapshot)
    system.acceptable(body, 'generation')
    base.require(len(body['dependencies']) <= 128 and all(r['provider'] == 'native' for r in body['dependencies']), 'System source requires exact direct native components')
    components = [];parts = {}
    mapping = sources.cache.artifact.parse_json(args['acquisition_bytes'])['description']['offers']
    for ref in sorted(body['dependencies'], key=lambda r:r['artifact']):
        dep = ref['artifact']
        if system.registry(root) is not None and system.management.present(system.object_path(root, dep)):
            component, receipt = system.object_record(root, dep);system.acceptable(component, 'component')
            parts[dep] = (component, None)
            components.append(dict(artifact=dep, retained=receipt['id']));continue
        offers = [offer for offer in mapping if offer['reference'] == ref]
        base.require(len(offers) == 1 and len(offers[0]['archives']) == 1, 'missing or ambiguous exact System component encoding in snapshot')
        checksum = offers[0]['archives'][0]['sha256']
        _, planned, component = inputs(source_root, cache_root, name, dep, checksum, args['snapshot']['id'])
        system.acceptable(component, 'component');components.append(dict(artifact=dep, acquisition=planned))
        parts[dep] = (component, None)
    completed = system.realization(root, identifier) if system.registry(root) is not None and system.management.present(system.object_path(root, identifier)) else None
    info = base.store_info(root)
    return base.record(FORMAT, dict(target=str(root), target_identity=system.target_identity(root), installation=info['installation'] if info else None,
        sources_root=str(sources.registry(source_root)), cache_root=str(sources.cache.cache_root(cache_root)), name=name,
        artifact=identifier, snapshot=args['snapshot']['id'], acquisition=acquisition, components=components,
        providers=system.provider_references(parts), completed=completed['id'] if completed else None,
        archive_verified=False, profile_validated=False))


def execute(plan, *, adapters=None):
    d = sources.cache.envelope(plan, FORMAT);root = targets(d['target'], d['sources_root'], d['cache_root'])
    base.require(os.geteuid() == 0, 'System realization requires an administrator')
    source = sources.registry(d['sources_root'], write=True)
    checksum = d['acquisition']['description']['binding']['archive']['sha256']
    with sources.cache.tx.file_lock(source / '.lock', shared=True, create=False):
        actual = prepare(root, source, d['cache_root'], d['name'], d['artifact'], archive_sha256=checksum, snapshot=d['snapshot'])
        base.require(actual == plan, 'System source install plan changed')
        system.providers(root, d['providers'], adapters)
        if d['completed']:
            return dict(plan=plan, changed=False, installation=system.install(root, None, d['artifact'], yes=True, adapters=adapters))
        archives, origins = [], {}
        for row in d['components']:
            if 'retained' in row:continue
            planned = row['acquisition'];encoding = planned['description']['binding']['archive']['sha256']
            args, _, _ = inputs(source, d['cache_root'], d['name'], row['artifact'], encoding, d['snapshot'])
            cached = sources.cache.acquire(d['cache_root'], planned, **args)
            archives.append(cached['archive']);origins[row['artifact']] = origin(args, cached, planned)
        args, _, _ = inputs(source, d['cache_root'], d['name'], d['artifact'], checksum, d['snapshot'])
        cached = sources.cache.acquire(d['cache_root'], d['acquisition'], **args)
        info = base.store_info(root)
        base.require(system.target_identity(root) == d['target_identity'] and (info['installation'] if info else None) == d['installation'], 'System target changed during acquisition')
        result = system.install(root, cached['archive'], d['artifact'], dependency_files=archives,
            acquisition=origin(args, cached, d['acquisition']), dependency_acquisition=origins, adapters=adapters, yes=True)
        return dict(plan=plan, changed=result['changed'], installation=result)


def origin(args, cached, planned):
    return dict(source=args['source']['id'], name=args['source']['description']['name'], verification=cached['record'],
                max_expanded=planned['description']['max_expanded'])


def install(root, source_root, cache_root, name, identifier, *, archive_sha256, snapshot=None, dry_run=False, yes=False, adapters=None):
    plan = prepare(root, source_root, cache_root, name, identifier, archive_sha256=archive_sha256, snapshot=snapshot)
    if dry_run:return dict(plan=plan, changed=False, dry_run=True)
    if not plan['description']['completed'] and not yes:
        print(json.dumps(plan, indent=2), file=sys.stderr)
        if input('Acquire this exact System bundle without changing configuration or boot? [y/N] ').strip().lower() not in ('y', 'yes'):
            return dict(plan=plan, changed=False, cancelled=True)
    return execute(plan, adapters=adapters)
