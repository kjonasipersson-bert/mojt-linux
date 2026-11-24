# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""One explicit Base update wish, reusing Ports selectors and release ordering."""
import uuid

import mpm_base as base
import mpm_sources as repos
from mpm_selection import Catalog,Selection,resolve,plan_upgrade,render_selector

FORMAT='mojt-base-update-request-v1'
FILE='base-request.json'
require=base.require


def read(root):
    root=repos.registry(root)
    if not (root/FILE).exists():return None
    value=repos.cache.artifact.parse_json(repos.cache.read_file(root,FILE))
    d=repos.cache.envelope(value,FORMAT)
    repos.cache.fields(d,('repo','source','snapshot','selection','installation'))
    repos.cache.model.token(d['repo'])
    base.io.identifier(d['source']);base.io.identifier(d['snapshot'])
    require(type(d['installation']) is str and len(d['installation'])==32
            and all(c in '0123456789abcdef' for c in d['installation']),'invalid request installation')
    choice=Selection.from_dict(d['selection'])
    require(choice.area=='base' and choice.candidate.backend=='native','request is not for native Base')
    return value


def choose(root,*,selector=None,repo=None,snapshot=None,installation=None):
    """Use accepted metadata only; explicit selectors change the wish, not the resolver."""
    before=read(root)
    old=before['description'] if before else None
    if selector is None:
        require(old is not None,'choose a Base update series first, e.g. mpm base upgrade mojt@0.2')
        require(installation is None or old['installation']==installation,
                'saved Base request belongs to another installation; choose a selector explicitly')
    name=repos.choose(root,repo or (old['repo'] if old else None))
    args=repos.load(root,name,snapshot)
    catalog=Catalog.from_dict(repos.cache.artifact.parse_json(args['catalog_bytes']))
    require(catalog.area=='base' and catalog.platform=='x86_64-linux','repository is not for Base x86_64')
    if selector is None and name==old['repo']:
        require(old['source']==args['source']['id'],'repository was reconfigured; choose a selector explicitly')
        previous=Selection.from_dict(old['selection'])
        choice=plan_upgrade(catalog,previous).after
        pinned=previous.selector.kind=='exact'
        accepted=old['snapshot'] if pinned else args['snapshot']['id']
        if pinned:
            # A withdrawn exact release keeps its accepted snapshot, while
            # authorization still comes from the current registered key/policy.
            args=repos.load(root,name,accepted)
    else:
        choice=resolve(catalog,selector or render_selector(Selection.from_dict(old['selection']).selector))
        accepted=args['snapshot']['id']
    require(choice.candidate.backend=='native','Base requires a native archive')
    return dict(repo=name,source=args['source']['id'],snapshot=accepted,selection=choice.to_dict()),before


def save(root,request,previous,installation):
    """Save the accepted content request; boot selection remains a separate commit."""
    root=repos.registry(root,write=True)
    value=repos.record(FORMAT,dict(request,installation=installation))
    with repos.cache.tx.file_lock(root/'.lock',mode=0o644):
        require(read(root)==previous,'Base update request changed during installation; repeat explicitly')
        current=repos.current(root,request['repo'])
        require(current is not None and current['description']['source']==request['source'],
                'repository was reconfigured; Base content retained but update request not saved')
        if value==previous:return False
        temporary=root/('.base-request-'+uuid.uuid4().hex)
        try:
            base.io.write_json(temporary,value)
            repos.cache.tx.publish(temporary,root/FILE)
        finally:temporary.unlink(missing_ok=True)
    return True
