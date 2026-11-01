#!/usr/bin/env python3
"""Check documentation drafts/fixtures, NOT a runtime or filesystem validator.

Mojt Linux. Copyright (C) 2026 Jonas Persson.
SPDX-License-Identifier: GPL-2.0-only
Requires jsonschema (validation here used 4.26.0); no network or target writes.
"""
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent


def need(condition, message):
    if not condition:
        raise ValueError(message)


def pairs(rows):
    result = {}
    for key, value in rows:
        need(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def scalar_gate(value, depth=0):
    need(depth <= 64, 'metadata depth')
    if isinstance(value, dict):
        need(len(value) <= 4096, 'object size')
        for key, item in value.items():
            scalar_gate(key, depth + 1)
            scalar_gate(item, depth + 1)
    elif isinstance(value, list):
        need(len(value) <= 4096, 'array size')
        for item in value:
            scalar_gate(item, depth + 1)
    elif isinstance(value, str):
        need(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), 'unpaired surrogate')
    else:
        need(value is None or type(value) in (bool, int), 'unsupported JSON scalar')
        if type(value) is int:
            need(-(2**63) <= value < 2**63, 'integer range')


def read(path):
    raw = path.read_bytes()
    need(len(raw) <= 16 * 1024**2, 'metadata size')
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)
    scalar_gate(value)
    return value


def digest(value):
    scalar_gate(value)
    data = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def seal(value):
    value['id'] = digest({k: v for k, v in value.items() if k != 'id'})
    return value


SCHEMAS = {path.name: read(path) for path in ROOT.glob('*.schema.json')}
REGISTRY = Registry().with_resources((s['$id'], Resource.from_contents(s)) for s in SCHEMAS.values())
for schema in SCHEMAS.values():
    Draft202012Validator.check_schema(schema)
FORMATS = {
    'mojt-system-composition-v1': 'system-composition',
    'mojt-artifact-store-v1': 'artifact-store',
    'mojt-install-receipt-v1': 'install-receipt',
    'mojt-lifecycle-set-v1': 'lifecycle-set',
    'mojt-lifecycle-result-v1': 'lifecycle-result',
}


def sorted_unique(rows, key=lambda x: x):
    keys = [key(row) for row in rows]
    need(keys == sorted(keys) and len(keys) == len(set(keys)), 'unsorted/duplicate entries')


def reference_key(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def path_gate(path, absolute=False):
    text = path[1:] if absolute and path.startswith('/') else path
    need(not absolute or path.startswith('/'), 'absolute path required')
    need(len(path.encode('utf-8')) <= 4096 and len(text.split('/')) <= 64, 'path limits')
    need(all(part not in ('', '.', '..') for part in text.split('/')), 'path traversal/empty component')
    need(not any(ord(c) < 32 or ord(c) == 127 or c in '\\:' for c in text), 'unsafe path')


def validate_facts(handler, check):
    facts = check['facts']
    if not facts and check['result'] != 'passed':
        return
    shapes = {
        'ensure-account': ('account-binding', {'name','group','uid','gid'}),
        'ensure-directory': ('directory-state', {'namespace','path','uid','gid','mode','type'}),
        'missing-default': ('default-state', {'namespace','path','outcome','sha256','uid','gid','mode'}),
        'kernel-derived': ('kernel-derived', {'inventory','binding'}),
        'manual-index': ('manual-index', {'input_profile','output_index'}),
    }
    need(handler in shapes, 'unsupported fact handler')
    name, fields = shapes[handler]
    need(check['name'] == name and set(facts) == fields, 'unknown fact shape')
    for key in fields & {'uid','gid','mode'}:
        need(type(facts[key]) is int and 0 <= facts[key] <= (511 if key == 'mode' else 2**32-1), 'invalid numeric facts')
    if 'namespace' in fields:
        need(facts['namespace'] in ('etc','var'), 'unknown fact namespace')
        path_gate(facts['path'])
    if handler == 'ensure-account':
        import re
        need(all(re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', facts[k]) for k in ('name','group')), 'invalid account facts')
    elif handler == 'ensure-directory':
        need(facts['type'] == 'directory', 'wrong observed file type')
    elif handler == 'missing-default':
        import re
        need(facts['namespace'] == 'etc' and facts['outcome'] in ('created','preserved'), 'invalid default outcome')
        need(re.fullmatch('[0-9a-f]{64}', facts['sha256']), 'invalid default digest')
    else:
        import re
        need(all(re.fullmatch('sha256:[0-9a-f]{64}', facts[k]) for k in fields), 'invalid derived-output facts')


def validate(value):
    scalar_gate(value)
    name = FORMATS[value['format']]
    Draft202012Validator(SCHEMAS[name + '.schema.json'], registry=REGISTRY).validate(value)
    need(value['id'] == digest({k: v for k, v in value.items() if k != 'id'}), 'identity mismatch')
    d = value['description']
    if name == 'system-composition':
        sorted_unique(d['components'], lambda r: r['role'])
        refs = {reference_key(r['reference']) for r in d['components']}
        sorted_unique(d['profile'], lambda r: r['path'])
        paths = [row['path'] for row in d['profile']]
        for row in d['profile']:
            path_gate(row['path']); path_gate(row['source']['path'])
            need(row['path'] != 'generated' and not row['path'].startswith('generated/'), 'reserved generated output')
            need(reference_key(row['source']['reference']) in refs, 'undeclared profile source')
            need(not any(other != row['path'] and row['path'].startswith(other + '/') for other in paths), 'overlapping profile mapping')
        for path in d['runtime'].values():
            path_gate(path)
            need(any(path == root or path.startswith(root + '/') for root in paths), 'unprovided runtime path')
        sorted_unique(d['services'], lambda r: r['unit'])
        for service in d['services']:
            path = 'units/' + service['unit']
            need(any(path == root or path.startswith(root + '/') for root in paths), 'unprovided unit')
        sorted_unique(d['management'], lambda r: r['family'])
        for row in d['management'] + d['state']:
            sorted_unique(row['read']); sorted_unique(row['write'])
            need(set(row['write']) <= set(row['read']), 'writer cannot read supported format')
        for row in d['management']:
            sorted_unique(row['capabilities'])
        sorted_unique(d['state'], lambda r: (r['namespace'], r['path'], r['owner']))
        need(len({(r['namespace'], r['path']) for r in d['state']}) == len(d['state']), 'conflicting state owners')
        for row in d['state']:
            path_gate(row['path'])
        sorted_unique(d['requirements']['base_abi'], lambda r: r['name'])
        for key in ('kernel_capabilities', 'host_capabilities'):
            sorted_unique(d['requirements'][key])
        need(d['lifecycle']['path'] == 'payload/lifecycle.json', 'unexpected lifecycle location')
    elif name == 'install-receipt':
        datetime.fromisoformat(d['installed_utc'].replace('Z','+00:00'))
        need(d['artifact'] == d['trust']['expected_id'], 'trust/installed identity mismatch')
        sorted_unique(d['dependencies'], reference_key)
    elif name == 'lifecycle-set':
        sorted_unique(d['actions'], lambda r: r['key'])
        actions = {r['key']: r for r in d['actions']}
        visiting, done = set(), set()
        def visit(key):
            need(key in actions and key not in visiting, 'missing dependency/cycle')
            if key in done:
                return
            visiting.add(key)
            row = actions[key]
            sorted_unique(row['after'])
            for before in row['after']:
                need(before != key, 'self dependency')
                need(before in actions, 'missing dependency')
                need(not (row['phase'] == 'stage' and actions[before]['phase'] == 'initialize'), 'phase inversion')
                visit(before)
            visiting.remove(key); done.add(key)
        for key in actions:
            visit(key)
        for row in actions.values():
            p = row['parameters']
            if row['type'] == 'kernel-derived':
                need(p['module_index'] or p['initramfs'], 'empty derived action')
            if row['type'] == 'ensure-account':
                path_gate(p['home'], True); path_gate(p['shell'], True)
            if row['type'] in ('ensure-directory', 'missing-default'):
                path_gate(p['path'])
            if row['type'] == 'missing-default':
                path_gate(p['source']['path'])
            if row['type'] == 'manual-index':
                sorted_unique(p['profile_paths'])
                for path in p['profile_paths']:
                    path_gate(path)
    elif name == 'lifecycle-result':
        datetime.fromisoformat(d['recorded_utc'].replace('Z','+00:00'))
        body = {key: d[key] for key in ('context', 'action_set', 'action_key', 'handler')}
        need(d['invocation'] == digest(dict(format='mojt-lifecycle-invocation-v1', **body)), 'invocation mismatch')
        sorted_unique(d['bindings'], lambda r: r['name'])
        sorted_unique(d['checks'], lambda r: r['name'])
        sorted_unique(d['observed_state'], lambda r:(r['namespace'],r['path'],r['owner']))
        for observation in d['observed_state']:
            path_gate(observation['path'])
        for check in d['checks']:
            validate_facts(d['handler']['type'], check)
            if check['evidence'] is not None:
                need(check['evidence'] == digest(dict(format='mojt-action-check-v1', **{k: check[k] for k in ('name', 'result', 'facts')})), 'check evidence mismatch')
            if check['result'] == 'passed':
                need(check['evidence'] is not None and check['facts'], 'missing successful check evidence')
        if d['status'] in ('started', 'blocked'):
            need(d['sequence'] == 1 and d['previous'] is None, 'invalid initial result')
        else:
            need(d['sequence'] == 2 and d['previous'] is not None, 'invalid terminal result')
        if d['status'] == 'started':
            need(d['error'] is None and not d['checks'], 'started is not completion')
        elif d['status'] == 'completed':
            need(d['error'] is None and d['checks'] and all(c['result'] == 'passed' for c in d['checks']), 'false completion')
            if d['handler']['type'] == 'ensure-account':
                f = d['checks'][0]['facts']
                need(dict(name=f['name'],uid=f['uid'],gid=f['gid']) in d['bindings'], 'fact/binding mismatch')
        else:
            need(d['error'] is not None, 'missing failure diagnostic')
    return value


def check_chain(records):
    previous = None
    for number, value in enumerate(records, 1):
        validate(value)
        d = value['description']
        need(d['sequence'] == number and d['previous'] == (previous['id'] if previous else None), 'chain gap/hash mismatch')
        if previous:
            p = previous['description']
            need(p['status'] == 'started' and d['status'] in ('completed','failed','uncertain'), 'illegal terminal transition')
            for key in ('invocation','context','action_set','action_key','handler','approval','run'):
                need(d[key] == p[key], 'attempt binding changed')
        previous = value


def main():
    examples = {path.stem: validate(read(path)) for path in (ROOT/'examples').glob('*.json')}
    comp, actions = examples['system-composition']['description'], examples['lifecycle-set']
    receipt, store = examples['install-receipt']['description'], examples['artifact-store']['description']
    need(comp['lifecycle']['id'] == actions['id'], 'composition/set mismatch')
    need(receipt['installation'] == store['installation'], 'store/receipt mismatch')
    need(receipt['dependencies'] == [r['reference'] for r in comp['components']], 'component/dependency mismatch')
    start, end = examples['lifecycle-result-started'], examples['lifecycle-result-completed']
    check_chain([start, end])
    need(start['description']['context']['installation'] == store['installation'], 'result target mismatch')
    need(start['description']['context']['owner'] == receipt['artifact'], 'result owner mismatch')
    need(start['description']['action_set'] == actions['id'], 'result set mismatch')
    action = next(a for a in actions['description']['actions'] if a['key'] == start['description']['action_key'])
    need(action['type'] == start['description']['handler']['type'], 'handler/action mismatch')
    tests = []
    def reject(label, value, mutate, chain=False):
        bad = copy.deepcopy(value)
        mutate(bad)
        if chain:
            for record in bad:
                seal(record)
        else:
            seal(bad)
        try:
            check_chain(bad) if chain else validate(bad)
        except (ValueError, KeyError, TypeError, ValidationError):
            tests.append(label)
        else:
            raise AssertionError('accepted invalid fixture: '+label)
    reject('unknown format', actions, lambda x:x.update(format='mojt-lifecycle-set-v2'))
    reject('unknown field', actions, lambda x:x.update(script='sh -c true'))
    reject('arbitrary hook', actions, lambda x:x['description']['actions'][0].update(type='run-shell'))
    reject('unknown handler version', actions, lambda x:x['description']['actions'][0].update(version=2))
    reject('cycle', actions, lambda x:x['description']['actions'][0]['after'].append('directory-demo'))
    reject('path traversal', actions, lambda x:x['description']['actions'][1]['parameters'].update(path='../shadow'))
    reject('absolute state path', actions, lambda x:x['description']['actions'][1]['parameters'].update(path='/etc/shadow'))
    reject('duplicate action', actions, lambda x:x['description']['actions'].append(copy.deepcopy(x['description']['actions'][0])))
    reject('unknown provider fallback', examples['system-composition'], lambda x:x['description']['profile'][0]['source']['reference'].update(artifact=digest('another-component')))
    reject('overlapping profile', examples['system-composition'], lambda x:x['description']['profile'].append(dict(path='lib/mpm/extra',source=copy.deepcopy(x['description']['profile'][0]['source']))))
    reject('unsupported runtime path', examples['system-composition'], lambda x:x['description']['runtime'].update(frontend='bin/missing'))
    reject('reserved generated mapping', examples['system-composition'], lambda x:x['description']['profile'][2].update(path='generated/manual-index'))
    reject('duplicate version', examples['system-composition'], lambda x:x['description']['management'][0]['read'].append(3))
    reject('trust mismatch', examples['install-receipt'], lambda x:x['description']['trust'].update(expected_id=digest('other-artifact')))
    reject('invalid calendar date', examples['install-receipt'], lambda x:x['description'].update(installed_utc='2026-99-99T00:00:00Z'))
    reject('newline in exact native ID', examples['install-receipt'], lambda x:x['description']['manager'].update(artifact=x['description']['manager']['artifact']+'\n'))
    reject('false completion', end, lambda x:x['description'].update(checks=[]))
    reject('unknown postcondition', end, lambda x:x['description']['checks'][0].update(result='unknown'))
    reject('forged evidence', end, lambda x:x['description']['checks'][0].update(evidence=digest('forged')))
    reject('unknown fact', end, lambda x:x['description']['checks'][0]['facts'].update(command='sh'))
    reject('false UID binding', end, lambda x:x['description']['bindings'][0].update(uid=0))
    reject('missing prior result', end, lambda x:x['description'].update(previous=None))
    reject('forked run', [start,end], lambda x:x[1]['description'].update(run='a'*32), True)
    reject('changed owner', [start,end], lambda x:x[1]['description']['context'].update(owner=digest('other-owner')), True)
    try:
        json.loads('{"a":1,"a":2}', object_pairs_hook=pairs)
    except ValueError:
        tests.append('duplicate JSON keys')
    else:
        raise AssertionError('accepted duplicate JSON keys')
    for bad in (1.5, float('nan'), 2**63, '\ud800'):
        try:
            scalar_gate(bad)
        except ValueError:
            tests.append('forbidden scalar')
        else:
            raise AssertionError('accepted forbidden scalar')
    print(f'PASS: {len(SCHEMAS)} schema definitions, {len(examples)} linked examples, {len(tests)} rejected invalid cases')
    print('Documentation validation only; no archive, installation, action or boot executed.')


if __name__ == '__main__':
    main()
