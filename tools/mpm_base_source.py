# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Accepted local source -> shared verified cache -> content-only Base installer."""
import json
import os
import sys

import mpm_base as base
import mpm_sources as sources

FORMAT='mojt-base-source-install-plan-v1'


def targets(root,source_root,cache_root):
    root=base.target(root,write=True);sources.separate_roots(source_root,cache_root)
    for path in (sources.registry(source_root),sources.cache.cache_root(cache_root)):
        for mutable in (root/'artifacts',root/'realizations'):
            base.require(path!=mutable and path not in mutable.parents and mutable not in path.parents,'Base content, source and cache roots must be separate')
    return root


def prepare(root,source_root,cache_root,name,identifier,*,archive_sha256,snapshot=None):
    root=targets(root,source_root,cache_root)
    args=sources.acquisition_inputs(source_root,name,identifier,kind='base',archive_sha256=archive_sha256,snapshot=snapshot)
    _,acquisition,body,_,_=sources.cache.inputs(cache_root,**args)
    installation=base.prepare(root,body,verify_installed=False)
    return sources.record(FORMAT,dict(target=str(root),sources_root=str(sources.registry(source_root)),
        cache_root=str(sources.cache.cache_root(cache_root)),name=name,artifact=identifier,
        snapshot=args['snapshot']['id'],acquisition=acquisition,installation=installation,
        archive_verified=False,rootfs_audited=False))


def execute(plan,*,tar='tar'):
    d=sources.cache.envelope(plan,FORMAT)
    root=targets(d['target'],d['sources_root'],d['cache_root'])
    source=sources.registry(d['sources_root'],write=True)
    checksum=d['acquisition']['description']['binding']['archive']['sha256']
    with sources.cache.tx.file_lock(source/'.lock',shared=True,create=False):
        actual=prepare(root,source,d['cache_root'],d['name'],d['artifact'],archive_sha256=checksum,snapshot=d['snapshot'])
        base.require(actual==plan,'Base source install plan changed')
        if d['installation']['description']['action']=='no-change':
            result=base.install(root,None,d['artifact'],yes=True,tar=tar)
            return dict(plan=plan,changed=False,acquisition=None,installation=result)
        base.require(os.geteuid()==0, 'Base realization requires an administrator')
        args=sources.acquisition_inputs(source,d['name'],d['artifact'],kind='base',archive_sha256=checksum,snapshot=d['snapshot'])
        cached=sources.cache.acquire(d['cache_root'],d['acquisition'],**args)
        origin=dict(source=args['source']['id'],name=d['name'],verification=cached['record'],max_expanded=d['acquisition']['description']['max_expanded'])
        result=base.install(root,cached['archive'],d['artifact'],yes=True,acquisition=origin,tar=tar)
        return dict(plan=plan,changed=result['changed'],acquisition=cached,installation=result)


def install(root,source_root,cache_root,name,identifier,*,archive_sha256,snapshot=None,dry_run=False,yes=False,tar='tar'):
    plan=prepare(root,source_root,cache_root,name,identifier,archive_sha256=archive_sha256,snapshot=snapshot)
    if dry_run:return dict(plan=plan,changed=False,dry_run=True)
    if plan['description']['installation']['description']['action']!='no-change' and not yes:
        print(json.dumps(plan,indent=2),file=sys.stderr)
        if input('Acquire and install this exact Base without changing configuration or boot? [y/N] ').strip().lower() not in ('y','yes'):
            return dict(plan=plan,changed=False,cancelled=True)
    return execute(plan,tar=tar)
