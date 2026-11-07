# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Closed System composition reader and explicit supported native-install subset."""
import re
import mojt_artifact as artifact
import mpm_base as base
import mpm_management as management

FORMAT = 'mojt-system-composition-v1'
LIFECYCLE = 'mojt-lifecycle-set-v1'
MAX_ROWS = 128
require = base.require


def reference(value):
    require(type(value) is dict and value.get('provider') == 'native', 'System install currently requires native component references; provider adapter unavailable')
    artifact.fields(value, ('provider', 'artifact'))
    base.io.identifier(value['artifact'])
    return value['artifact']


def rows(value, key):
    require(type(value) is list and len(value) <= MAX_ROWS and all(type(r) is dict for r in value), 'unbounded/invalid System rows')
    try:keys = [key(r) for r in value];valid = keys == sorted(set(keys))
    except (KeyError, TypeError) as error:raise ValueError('invalid System row key') from error
    require(valid, 'System rows must be sorted and unique')


def strings(values):
    require(type(values) is list and len(values) <= MAX_ROWS and all(management.token(x) for x in values)
            and values == sorted(set(values)), 'invalid System capability list')


def validate(value):
    d = base.envelope(value, FORMAT)
    artifact.fields(d, ('label', 'platform', 'components', 'requirements', 'management', 'state', 'profile', 'services', 'runtime', 'lifecycle'))
    require(type(d['label']) is str and 0 < len(d['label']) <= 128 and not any(ord(c) < 32 or ord(c) == 127 for c in d['label']), 'invalid System label')
    require(management.token(d['platform']), 'invalid System platform')
    rows(d['components'], lambda r:r.get('role', ''));require(d['components'], 'System requires components')
    refs = set()
    for row in d['components']:
        artifact.fields(row, ('role', 'reference'));require(management.token(row['role']), 'invalid component role')
        refs.add(reference(row['reference']))
    r = d['requirements'];artifact.fields(r, ('base_abi', 'state_layout', 'kernel_capabilities', 'host_capabilities'))
    rows(r['base_abi'], lambda x:x.get('name', ''))
    for row in r['base_abi']:
        artifact.fields(row, ('name', 'value'))
        require(management.token(row['name']) and type(row['value']) is str and 0 < len(row['value']) <= 256
                and not any(ord(c) < 32 or ord(c) == 127 for c in row['value']), 'invalid declared System ABI')
    require(type(r['state_layout']) is int and r['state_layout'] > 0, 'invalid System state layout')
    strings(r['kernel_capabilities']);strings(r['host_capabilities'])
    rows(d['management'], lambda x:x.get('family', ''));require(d['management'], 'System needs management declarations')
    for row in d['management']:
        artifact.fields(row, ('family', 'read', 'write', 'capabilities'))
        require(management.token(row['family']), 'invalid System management family');management.access(row)
        require(row['read'] and row['write'], 'System composition needs explicit reader and writer versions');strings(row['capabilities'])
    rows(d['state'], management.state_key)
    for row in d['state']:
        artifact.fields(row, ('owner', 'namespace', 'path', 'family', 'read', 'write'))
        management.location(row);management.access(row)
    for n, row in enumerate(d['state']):
        for other in d['state'][n + 1:]:
            require(row['namespace'] != other['namespace'] or not overlap(row['path'], other['path']), 'conflicting System state owners')
    rows(d['profile'], lambda x:x.get('path', ''));require(d['profile'], 'System needs profile mappings')
    paths = []
    for row in d['profile']:
        artifact.fields(row, ('path', 'source'));management.path(row['path'])
        require(row['path'].split('/')[0] not in ('generated', 'management.json', 'manifest.json'), 'reserved System profile output')
        artifact.fields(row['source'], ('reference', 'path'));management.path(row['source']['path'])
        require(reference(row['source']['reference']) in refs, 'undeclared System profile source')
        require(not any(overlap(row['path'], p) for p in paths), 'overlapping System profile mappings');paths.append(row['path'])
    artifact.fields(d['runtime'], ('interpreter', 'frontend', 'module_root'))
    for p in d['runtime'].values():
        management.path(p);require(any(p == root or p.startswith(root + '/') for root in paths), 'unprovided System runtime path')
    rows(d['services'], lambda x:x.get('unit', ''))
    for row in d['services']:
        artifact.fields(row, ('unit', 'enabled'))
        require(type(row['unit']) is str and re.fullmatch(r'[A-Za-z0-9_.@:-]+\.service', row['unit']) and type(row['enabled']) is bool, 'invalid System service declaration')
        path = 'units/' + row['unit'];require(any(path == p or path.startswith(p + '/') for p in paths), 'unprovided System service')
    artifact.fields(d['lifecycle'], ('format', 'id', 'path'))
    require(d['lifecycle']['format'] == LIFECYCLE and d['lifecycle']['path'] == 'payload/lifecycle.json', 'unsupported System lifecycle binding')
    base.io.identifier(d['lifecycle']['id'])
    return d


def overlap(a, b):return a == b or a.startswith(b + '/') or b.startswith(a + '/')


def supported(value, actions):
    d = validate(value)
    lifecycle = base.envelope(actions, LIFECYCLE);artifact.fields(lifecycle, ('platform', 'actions'))
    require(actions['id'] == d['lifecycle']['id'] and lifecycle['platform'] == d['platform'], 'System lifecycle identity/platform differs')
    require(lifecycle['actions'] == [], 'System install does not support required lifecycle actions yet')
    require(d['runtime'] == dict(interpreter='bin/python3', frontend='bin/mpm', module_root='tools'), 'unsupported System runtime layout; requires bin/python3, bin/mpm and tools')
    require(d['requirements']['base_abi'] and d['requirements']['state_layout'] == 1, 'System needs explicit Base ABI and supported state layout')
    require(not d['requirements']['kernel_capabilities'] and not d['requirements']['host_capabilities'] and not d['state'], 'unsupported required System host/kernel/state-schema capability')
    return d
