# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Exact registered native source -> verified cache -> existing Kernel publisher."""
import json
import sys

import mpm_kernel as kernel
import mpm_sources as sources

FORMAT = 'mojt-kernel-source-install-plan-v1'


def targets(root, source_root, cache_root):
    root = kernel.root_path(root, write=True)
    sources.separate_roots(source_root, cache_root)
    for path in (sources.registry(source_root), sources.cache.cache_root(cache_root)):
        sources.require(path != root and path not in root.parents and root not in path.parents,
                        'Kernel, source and cache roots must be separate')
    return root


def prepare(root, source_root, cache_root, name, expected_id, *, archive_sha256, snapshot=None):
    root = targets(root, source_root, cache_root)
    args = sources.acquisition_inputs(source_root, name, expected_id, kind='kernel',
                                     archive_sha256=archive_sha256, snapshot=snapshot)
    _, acquisition, body, _, _ = sources.cache.inputs(cache_root, **args)
    eligibility = kernel.plan_install(root, body)
    return sources.record(FORMAT, dict(root=str(root), sources_root=str(sources.registry(source_root)),
        cache_root=str(sources.cache.cache_root(cache_root)), name=name, artifact=expected_id,
        snapshot=args['snapshot']['id'], acquisition=acquisition, installation=eligibility))


def execute(plan):
    d = sources.cache.envelope(plan, FORMAT)
    root = targets(d['root'], d['sources_root'], d['cache_root'])
    source_root = sources.registry(d['sources_root'], write=True)
    encoding = d['acquisition']['description']['binding']['archive']['sha256']
    with sources.cache.tx.file_lock(source_root / '.lock', shared=True, create=False):
        actual = prepare(root, source_root, d['cache_root'], d['name'], d['artifact'],
                         archive_sha256=encoding, snapshot=d['snapshot'])
        sources.require(actual == plan, 'Kernel source install plan changed')
        if d['installation']['action'] == 'no-change':
            return dict(plan=plan, changed=False, acquisition=None)
        args = sources.acquisition_inputs(source_root, d['name'], d['artifact'], kind='kernel',
                                         archive_sha256=encoding, snapshot=d['snapshot'])
        cached = sources.cache.acquire(d['cache_root'], d['acquisition'], **args)
        origin = dict(source=args['source']['id'], name=d['name'], verification=cached['record'],
                      max_expanded=d['acquisition']['description']['max_expanded'])
        # The existing installer freezes, re-verifies and publishes the archive
        # and matching module tree. Keep source authorization locked until done.
        result = kernel.install(root, cached['archive'], d['artifact'], yes=True, acquisition=origin)
        return dict(plan=plan, changed=result['changed'], acquisition=cached,
                    installation=result)


def install(root, source_root, cache_root, name, expected_id, *, archive_sha256,
            snapshot=None, dry_run=False, yes=False):
    plan = prepare(root, source_root, cache_root, name, expected_id,
                   archive_sha256=archive_sha256, snapshot=snapshot)
    if dry_run:
        return dict(plan=plan, changed=False, dry_run=True)
    if plan['description']['installation']['action'] == 'no-change':
        return execute(plan)
    if not yes:
        print(json.dumps(plan, indent=2), file=sys.stderr)
        print('Acquire and install this exact Kernel? [y/N] ', end='', file=sys.stderr, flush=True)
        if input().strip().lower() not in ('y', 'yes'):
            return dict(plan=plan, changed=False, cancelled=True)
    return execute(plan)
