# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Native Ports archives and their declared package wishes."""
import hashlib
import os
from pathlib import Path
import shutil
import stat
import tempfile

import mojt_artifact as artifact
import mpm_native_io as io
from mpm_request_plan import reference
import mpm_requests as wishes
import mpm_sources as repositories
from mpm_ports_profile import command, read, write
from mpm_selection import Catalog, parse_selector, resolve
from mpm_transaction import protected_directory, sync_directory

PREFIX = 'meta-'
LIMIT = 16 * 1024**2
require = wishes.require


def descriptor(body):
    artifact.validate_descriptor(body)
    require(body['kind'] == 'port' and not body['dependencies'], 'unsupported native Ports dependencies')
    wishes.fields(body['metadata'], ('ports',))
    selectors = body['metadata']['ports']
    require(type(selectors) is list and selectors and len(selectors) <= 64, 'invalid native Ports wishes')
    require(len({parse_selector(value).name for value in selectors}) == len(selectors), 'repeated native Ports role')
    require(body['name'] not in {parse_selector(value).name for value in selectors}, 'native Port depends on itself')
    wishes.fields(body['provides'], ('commands',))
    names = body['provides']['commands']
    require(type(names) is list and len(names) == len(set(names)), 'invalid native Ports command exports')
    files = {row['path']: row for row in body['files']}
    require(sum(row.get('size', 0) for row in files.values()) <= LIMIT, 'native Port exceeds content limit')
    for name in names:
        command(name)
        row = files.get('payload/bin/' + name)
        require(row and row['type'] == 'file' and row['mode'] & 0o111 == 0o111, 'invalid command target')
    require(all(row['type'] in ('file', 'directory') and row['uid'] == row['gid'] == 0
                and not row['mode'] & 0o7022 for row in files.values()), 'unsafe native Ports payload')
    return body


def discover(runtime):
    views, bindings = {}, {}
    if runtime is None:
        return views, bindings
    root = repositories.area_root('ports', runtime)
    for name in repositories.names(root):
        require(name != 'nixpkgs', 'native repository cannot be named nixpkgs')
        registration = repositories.current(root, name)['description']
        snapshot = registration['snapshot']
        if snapshot is None:
            continue
        loaded = repositories.load(root, name, snapshot)
        catalog = artifact.parse_json(loaded['catalog_bytes'])
        require(catalog['area'] == 'ports', 'repository catalog belongs to another area')
        catalogs, offers = {}, {}
        for row in catalog['candidates']:
            require(catalog['sources'][row['source']]['backend'] == 'native', 'expected a native Port')
            ref = dict(provider='native', artifact=row['artifact'])
            digest = row['integrity']['sha256']
            selection = dict(kind='port', archive_sha256=digest, snapshot=snapshot)
            args = repositories.acquisition_inputs(root, name, row['artifact'], **selection)
            body = descriptor(artifact.parse_json(args['descriptor_bytes']))
            require(body['id'] == row['artifact'], 'native Ports descriptor differs')
            entry = catalogs.setdefault(row['name'], dict(catalog, name=row['name'], candidates=[]))
            entry['candidates'].append(row)
            offers[row['artifact']] = dict(backend='native', artifact=row['artifact'], integrity=row['integrity'],
                reference=ref, dependencies=[], transport_sha256=digest)
            prior = bindings.get(row['artifact'])
            require(prior is None or prior[1]['archive_sha256'] == digest, 'conflicting native Port archive encodings')
            bindings.setdefault(row['artifact'], (name, selection, body))
        views[name] = dict(snapshot=snapshot, catalogs=catalogs, offers=list(offers.values()))
    return views, bindings


class NativePortsAdapter:
    def __init__(self, runtime, bindings):
        self.runtime = runtime
        self.bindings = bindings

    def directory(self, ref, root):
        return Path(root) / 'retained/native' / reference(ref)['artifact'].split(':')[1]

    def body(self, ref, root):
        directory = self.directory(ref, root)
        if os.path.lexists(directory):
            protected_directory(directory, label='Native Port')
            body = descriptor(read(directory / 'artifact.json'))
        else:
            require(ref['artifact'] in self.bindings, 'native Port absent from registered repositories')
            body = self.bindings[ref['artifact']][2]
        require(body['id'] == ref['artifact'], 'native Ports identity differs')
        return body

    def describe(self, ref, root):
        directory = self.directory(ref, root) / 'payload/bin'
        return dict(reference=ref, commands={name: str(directory / name)
            for name in self.body(ref, root)['provides']['commands']})

    def ensure(self, ref, root):
        directory = self.directory(ref, root)
        if os.path.lexists(directory):
            self.verify(ref, root)
            return
        name, selection, body = self.bindings[ref['artifact']]
        repos = repositories.area_root('ports', self.runtime)
        plan = repositories.prepare_fetch(repos, self.runtime.cache, name, ref['artifact'], **selection)
        fetched = repositories.fetch(repos, self.runtime.cache, name, ref['artifact'], plan, **selection)
        protected_directory(directory.parent, write=True, label='Native Ports')
        directory.parent.mkdir(mode=0o755, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix='.install-', dir=directory.parent))
        try:
            io.unpack_regular(fetched['archive'], body, work, budget=LIMIT)
            write(work / 'artifact.json', body)
            work.chmod(0o755)
            sync_directory(work)
            work.rename(directory)
            sync_directory(directory.parent)
            sync_directory(directory.parent.parent)
        finally:
            if work.exists():
                shutil.rmtree(work)

    def verify(self, ref, root):
        directory = protected_directory(self.directory(ref, root), label='Native Port')
        body = self.body(ref, root)
        require({str(p.relative_to(directory)) for p in directory.rglob('*')} ==
                {'artifact.json', *(row['path'] for row in body['files'])}, 'native Ports payload inventory differs')
        for row in body['files']:
            path = directory / row['path']
            status = path.lstat()
            require(status.st_uid in (0, os.geteuid()) and stat.S_IMODE(status.st_mode) == io.stored_mode(row),
                    'native Ports payload mode/owner differs')
            if row['type'] == 'directory':
                require(stat.S_ISDIR(status.st_mode), 'native Ports directory changed')
            else:
                require(stat.S_ISREG(status.st_mode) and status.st_nlink == 1 and status.st_size == row['size'],
                        'native Ports file changed')
                with path.open('rb') as stream:
                    require(hashlib.file_digest(stream, 'sha256').hexdigest() == row['sha256'],
                            'native Ports file content differs')


def dependency_wishes(state, previous, views, adapter, root, platform, advance=()):
    """Use the existing configuration ownership model for each native wish."""
    claims = state['description']['claims']
    known = {row['claim']: row['reference'] for row in previous['lock']['description']['resolutions']} if previous else {}
    managed = {PREFIX + row['key'][7:63]: row for row in claims if row['source'] in views
               or known.get(row['key'], {}).get('provider') == 'native'}
    old = {PREFIX + key[7:63] for key, ref in known.items() if ref['provider'] == 'native'}
    configurations = {row['name'] for row in state['description']['configurations']}
    for name in sorted((old & configurations) - set(managed)):
        state = wishes.reconcile_configuration(state, dict(format=wishes.CONFIG, name=name))
        state['description']['configurations'] = [row for row in state['description']['configurations'] if row['name'] != name]
        state = wishes.validate(wishes.seal(state['description']))
    required = set()
    for name, row in managed.items():
        require(name not in configurations or name in old, 'metapackage configuration already exists')
        ref = known.get(row['key'])
        selector = row['policy']['selector']
        if ref is None or row['key'] in advance and parse_selector(selector).kind != 'exact':
            catalog = Catalog.from_dict(views[row['source']]['catalogs'][row['role']])
            ref = dict(provider='native', artifact=resolve(catalog, selector, platform=platform).candidate.artifact)
        document = dict(format=wishes.CONFIG, name=name,
            ports=dict(source='nixpkgs', packages=adapter.body(ref, root)['metadata']['ports']))
        state = wishes.reconcile_configuration(state, document)
        required.update(document['ports']['packages'])
    return state, sorted(required)
