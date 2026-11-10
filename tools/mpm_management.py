# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Declared management/state/handler compatibility, with measured runtime evidence.

Pure record/check functions do not execute providers or handlers. Target readers
are deliberately limited to the implemented defaults registry and fail closed.
"""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat

FORMAT = 'mojt-management-capabilities-v1'
CONTEXT = 'mojt-management-context-v1'
FILENAME = 'management.json'
LIMIT = 128
MAX_METADATA = 1024 * 1024
# Required output protocol of the one implemented action, even on an empty target.
# Complete code closure for the advertised native defaults protocol. Optional
# provider adapters are inventoried by System separately, not required here.
CAPABILITY_FILES = (
    'mpm_cli.py', 'mpm_system_cli.py', 'mpm_system_transition.py',
    'mpm_boot_base.py', 'mpm_boot_constructor.py', 'mpm_boot_early.py', 'mpm_boot_handover.py',
    'mpm_boot_inventory.py', 'mpm_boot_v2.py', 'mpm_boot_v2_store.py', 'mpm_boot_selection.py',
    'mpm_boot_update.py', 'mpm_boot_status.py', 'mpm_request_plan.py', 'mpm_requests.py', 'mpm_ports_profile.py',
    'mojt-base-install', 'mojt_accounts.py', 'mojt_artifact.py', 'mojt_boot.py',
    'mojt_native_image.py', 'mojt_system.py', 'mojt_system_manifest.py', 'mpm_base.py',
    'mpm_catalog.py', 'mpm_defaults.py', 'mpm_deployment.py', 'mpm_kernel.py',
    'mpm_management.py', 'mpm_native_io.py', 'mpm_selection.py', 'mpm_transaction.py',
    'mpm_system.py', 'mpm_system_model.py',
)
ACTION_REGISTRIES = {
    ('missing-default', 1, 'initialize', 'mojt-defaults-preparation-v1'): ('mpm-defaults', 1),
}


def require(ok, message):
    if not ok:raise ValueError(message)


def fields(value, names):
    require(type(value) is dict and set(value) == set(names.split()), 'invalid management fields: ' + names)


def token(value):return type(value) is str and re.fullmatch('[a-z0-9][a-z0-9_.-]{0,63}', value) is not None


def identifier(value):
    require(type(value) is str and re.fullmatch('sha256:[0-9a-f]{64}', value), 'invalid management evidence identity')


def path(value):
    require(type(value) is str and 0 < len(value.encode()) <= 4096 and len(value.split('/')) <= 64
            and all(p not in ('', '.', '..') for p in value.split('/'))
            and not any(ord(c) < 32 or ord(c) == 127 or c in '\\:' for c in value), 'unsafe managed path')


def canonical(value):return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):return 'sha256:' + hashlib.sha256(canonical(value)).hexdigest()


def record(fmt, description):
    body = dict(format=fmt, description=copy.deepcopy(description))
    return dict(body, id=digest(body))


def envelope(value, fmt):
    fields(value, 'format id description')
    require(value == record(fmt, value['description']), 'unsupported/corrupt management record: ' + fmt)
    require(len(canonical(value)) <= MAX_METADATA, 'unbounded management record')
    return value['description']


def rows(value, key):
    require(type(value) is list and len(value) <= LIMIT and all(type(r) is dict for r in value), 'invalid management list')
    try:
        keys = [key(row) for row in value]
        ordered = keys == sorted(keys) and len(set(keys)) == len(keys)
    except (TypeError, KeyError) as error:
        raise ValueError('invalid management row keys') from error
    require(ordered, 'management rows must be sorted and unique')


def versions(value):
    require(type(value) is list and len(value) <= 64 and all(type(n) is int and 0 < n < 2**31 for n in value)
            and value == sorted(set(value)), 'invalid managed format versions')


def access(row):
    versions(row['read']);versions(row['write'])
    require(set(row['write']) <= set(row['read']), 'write versions must be readable')


def location(row):
    require(token(row['owner']) and token(row['family']) and row['namespace'] in ('etc', 'var'), 'invalid managed state location')
    path(row['path'])


def action(row):
    fields(row, 'type version phase contract')
    require(token(row['type']) and type(row['version']) is int and 0 < row['version'] < 2**31
            and row['phase'] in ('stage', 'initialize') and token(row['contract']), 'invalid required handler contract')


def action_key(row):return (row.get('type', ''), row.get('version', 0), row.get('phase', ''), row.get('contract', ''))


def state_key(row):return (row.get('namespace', ''), row.get('path', ''), row.get('owner', ''))


def validate(value):
    d = envelope(value, FORMAT)
    fields(d, 'management state handlers implementation')
    rows(d['management'], lambda r:r.get('family', ''))
    for row in d['management']:
        fields(row, 'family read write capabilities');require(token(row['family']), 'invalid management family');access(row)
        require(type(row['capabilities']) is list and len(row['capabilities']) <= LIMIT
                and all(token(x) for x in row['capabilities']) and row['capabilities'] == sorted(set(row['capabilities'])),
                'invalid management capabilities')
    rows(d['state'], state_key)
    for row in d['state']:
        fields(row, 'owner namespace path family read write');location(row);access(row)
    for number, row in enumerate(d['state']):
        for other in d['state'][number + 1:]:
            if row['namespace'] == other['namespace']:
                require(row['path'] != other['path'] and not row['path'].startswith(other['path'] + '/')
                        and not other['path'].startswith(row['path'] + '/'), 'overlapping managed state ownership')
    rows(d['handlers'], action_key)
    for row in d['handlers']:action(row)
    fields(d['implementation'], 'provider identity')
    require(d['implementation']['provider'] == 'mojt-manager-code', 'unsupported management implementation provider')
    fields(d['implementation']['identity'], 'files')
    files = d['implementation']['identity']['files']
    require(type(files) is dict and 0 < len(files) <= LIMIT, 'invalid management implementation files')
    for name, checksum in files.items():
        path(name)
        require('/' not in name and type(checksum) is str and re.fullmatch('[0-9a-f]{64}', checksum), 'invalid manager code digest')
    return copy.deepcopy(value)


def create(description):return validate(record(FORMAT, description))


def context(registries=(), state=(), actions=()):
    return validate_context(record(CONTEXT, dict(registries=list(registries), state=list(state), actions=list(actions))))


def validate_context(value):
    d = envelope(value, CONTEXT);fields(d, 'registries state actions')
    rows(d['registries'], lambda r:r.get('family', ''))
    for row in d['registries']:
        fields(row, 'family version capabilities evidence')
        require(token(row['family']) and type(row['version']) is int and 0 < row['version'] < 2**31, 'invalid observed registry')
        require(type(row['capabilities']) is list and len(row['capabilities']) <= LIMIT
                and all(token(x) for x in row['capabilities']) and row['capabilities'] == sorted(set(row['capabilities'])),
                'invalid required registry capabilities')
        identifier(row['evidence'])
    rows(d['state'], state_key)
    for row in d['state']:
        fields(row, 'owner namespace path family version evidence');location(row);identifier(row['evidence'])
        require(type(row['version']) is int and 0 < row['version'] < 2**31, 'invalid observed schema version')
    rows(d['actions'], action_key)
    for row in d['actions']:action(row)
    return copy.deepcopy(value)


def check(capabilities, observed):
    """Declared metadata only; neither authorizes effects nor establishes readiness."""
    facts = validate_context(observed)['description']
    if capabilities is None:
        return dict(compatible=not any(facts.values()), errors=['System lacks management capability evidence'] if any(facts.values()) else [])
    d = validate(capabilities)['description'];errors = []
    supported = {r['family']:r for r in d['management']}
    for actual in facts['registries']:
        row = supported.get(actual['family'])
        for operation in ('read', 'write'):
            if row is None or actual['version'] not in row[operation]:
                errors.append(f"registry {actual['family']} version {actual['version']} unsupported for {operation}")
        for capability in actual['capabilities']:
            if row is None or capability not in row['capabilities']:errors.append('registry capability unsupported: ' + capability)
    owned = {(r['owner'], r['namespace'], r['path'], r['family']):r for r in d['state']}
    for actual in facts['state']:
        key = tuple(actual[k] for k in ('owner', 'namespace', 'path', 'family'))
        row = owned.get(key)
        for operation in ('read', 'write'):
            if row is None or actual['version'] not in row[operation]:
                errors.append(f"state {actual['owner']}:{actual['namespace']}/{actual['path']} {actual['family']} version {actual['version']} unsupported for {operation}")
    for required in facts['actions']:
        if required not in d['handlers']:
            errors.append(f"required handler unsupported: {required['type']} version {required['version']} / {required['phase']} / {required['contract']}")
        dependency = ACTION_REGISTRIES.get(action_key(required))
        if dependency is not None:
            family, version = dependency
            row = supported.get(family)
            for operation in ('read', 'write'):
                if row is None or version not in row[operation]:
                    errors.append(f"required handler output registry {family} version {version} unsupported for {operation}")
    return dict(compatible=not errors, errors=errors)


def check_transition(preparing, candidate, observed):
    reports = dict(preparing=check(preparing, observed), candidate=check(candidate, observed))
    errors = [role + ': ' + error for role, report in reports.items() for error in report['errors']]
    return dict(compatible=not errors, errors=errors, runtimes=reports,
                scope='Declared management/state/handler compatibility; no action execution, data migration or boot readiness.')


def literal(file, name):
    file_hash(file)
    definitions = []
    try:body = ast.parse(file.read_text()).body
    except (SyntaxError, RecursionError) as error:raise ValueError('invalid bundled manager source: ' + file.name) from error
    for node in body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name:
            definitions.append(ast.literal_eval(node.value))
    require(len(definitions) == 1, 'missing/duplicate literal manager declaration: ' + name)
    return definitions[0]


def file_hash(file):
    info = file.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not info.st_mode & 0o022
            and info.st_size <= 4 * MAX_METADATA,
            f'unsafe/unbounded manager implementation: {file} '
            f'(mode={stat.S_IMODE(info.st_mode):04o}, links={info.st_nlink}, bytes={info.st_size}; '
            'require a regular single-link file without group/other write access, at most 4 MiB)')
    with file.open('rb') as stream:return hashlib.file_digest(stream, 'sha256').hexdigest()


def produce(tools, names):
    """Measure bundled code/literal support. Never import candidate Python code."""
    require(type(names) in (list, tuple) and 0 < len(names) <= LIMIT and len(set(names)) == len(names), 'invalid bundled runtime list')
    require(set(CAPABILITY_FILES) <= set(names), 'incomplete native management runtime')
    for name in names:path(name);require('/' not in name, 'invalid bundled manager path')
    hashes = {name:file_hash(tools / name) for name in CAPABILITY_FILES}
    supported = literal(tools / 'mpm_defaults.py', 'MANAGEMENT_SUPPORT') + literal(tools / 'mpm_system.py', 'MANAGEMENT_SUPPORT') + literal(tools / 'mpm_boot_selection.py', 'MANAGEMENT_SUPPORT')
    supported.sort(key=lambda row:row['family'])
    description = dict(management=supported, state=[],
        handlers=literal(tools / 'mpm_defaults.py', 'HANDLER_SUPPORT'),
        implementation=dict(provider='mojt-manager-code', identity=dict(files=hashes)))
    result = create(description)
    require({name:file_hash(tools / name) for name in CAPABILITY_FILES} == hashes, 'bundled manager changed during measurement')
    return result


def current():
    tools = Path(__file__).parent
    return produce(tools, CAPABILITY_FILES)


def present(file):
    # Only ENOENT establishes absence. Permission/type errors remain unknown.
    try:file.lstat()
    except FileNotFoundError:return False
    return True


def retained(profile, manifest):
    """Bind declared support to the measured immutable System inventory/code."""
    from mojt_system_manifest import validate as validate_manifest
    import mpm_base as base
    validate_manifest(manifest)
    import mpm_transaction as tx
    tx.protected_directory(profile, label='System management profile')
    inventory = manifest['description']['profile'];file = profile / FILENAME
    if FILENAME not in inventory:
        require(not present(file), 'unmeasured management capability file')
        return None
    tx.protected_directory(profile / 'tools', label='System management code')
    row = inventory[FILENAME]
    require(type(row) is dict and set(row) == {'sha256', 'mode'} and type(row['mode']) is int and file_hash(file) == row['sha256']
            and stat.S_IMODE(file.lstat().st_mode) == row['mode'], 'management capability evidence differs')
    value = validate(base.read(file))
    files = value['description']['implementation']['identity']['files']
    names = literal(profile / 'tools/mojt_system.py', 'MPM_FILES')
    require(type(names) in (list, tuple) and len(names) <= LIMIT and all(type(n) is str for n in names), 'invalid retained runtime list')
    require(set(files) == set(CAPABILITY_FILES) and set(files) <= set(names),
            'management implementation is not the complete native capability runtime')
    for name, checksum in files.items():
        row = inventory.get('tools/' + name)
        require(type(row) is dict and set(row) == {'sha256', 'mode'} and type(row['mode']) is int and row['sha256'] == checksum
                and file_hash(profile / 'tools' / name) == checksum
                and stat.S_IMODE((profile / 'tools' / name).lstat().st_mode) == row['mode'], 'retained management code differs: ' + name)
    require(produce(profile / 'tools', names) == value, 'management declarations differ from bundled implementation')
    return value


def observe_target(root):
    """Only the implemented lifecycle registry is observed; absence is explicit."""
    import mpm_defaults as defaults
    observation = defaults.inspect_registry(root)
    if observation is not None:
        require(not observation['description']['interrupted'] and not observation['description']['incomplete'],
                'incomplete defaults preparation; reconcile explicitly before transition')
    registries = [] if observation is None else [dict(family='mpm-defaults', version=1, capabilities=[], evidence=observation['id'])]
    import mpm_system as system
    system_state = system.registry_observation(root)
    if system_state is not None:
        registries.append(dict(family='mpm-system', version=1,
            capabilities=system.required_capabilities(root), evidence=system_state['id']))
    import mpm_boot_selection as boot
    selected = boot.observation(root)
    if selected is not None:registries.append(selected)
    return context(registries=sorted(registries,key=lambda row:row['family']))


def _check_target(root, profile, manifest, *, required=None):
    observed = observe_target(root)
    if required is not None:
        supplied = validate_context(required)['description']
        require(not supplied['registries'] and not supplied['state'], 'target state observations cannot be replaced by supplied facts')
        observed = context(registries=observed['description']['registries'], actions=supplied['actions'])
    candidate = retained(profile, manifest)
    preparing = current() if candidate is not None or any(observed['description'].values()) else None
    result = check_transition(preparing, candidate, observed)
    return dict(result, observed=observed, candidate=candidate['id'] if candidate else None,
                preparing=preparing['id'] if preparing else None)


def check_target(root, profile, manifest, *, required=None):
    # Current trusted helper directory, never the candidate's code or host PATH.
    # Image builders also load this module by filename without installing it.
    import sys
    previous = sys.path[:]
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        return _check_target(root, profile, manifest, required=required)
    finally:
        sys.path[:] = previous
