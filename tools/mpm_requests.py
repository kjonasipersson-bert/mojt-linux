# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pure versioned configuration and Ports request ownership. No IO/provider calls."""
import copy
import hashlib
import json
import re
import tomllib

from mpm_selection import parse_selector as _parse_selector, components

CONFIG = 'mojt-configuration-v1'
STATE = 'mojt-request-state-v1'
TOKEN = r'[a-z0-9][a-z0-9_.-]{0,63}'
ID = r'sha256:[0-9a-f]{64}'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fields(value, required, optional=()):
    require(type(value) is dict and set(required) <= set(value) <= set(required) | set(optional), 'invalid fields')


def token(value):
    require(type(value) is str and re.fullmatch(TOKEN, value), 'invalid source/origin name')


def parse_selector(value):
    require(type(value) is str and 0 < len(value) <= 4096, 'invalid selector size')
    result = _parse_selector(value)
    require(len(result.name) <= 256, 'package name size limit')
    return result


def canonical(value):
    def check(item, depth=0):
        require(depth <= 64, 'metadata nesting limit')
        if type(item) is dict:
            require(len(item) <= 4096 and all(type(k) is str for k in item), 'invalid object')
            for k, v in item.items():
                check(k, depth + 1); check(v, depth + 1)
        elif type(item) is list:
            require(len(item) <= 4096, 'metadata collection limit')
            for v in item:
                check(v, depth + 1)
        elif type(item) is str:
            require(not any(0xD800 <= ord(c) <= 0xDFFF for c in item), 'invalid Unicode')
        else:
            require(item is None or type(item) in (bool, int), 'unsupported metadata scalar')
            if type(item) is int:
                require(-(2**63) <= item < 2**63, 'integer range')
    check(value)
    raw = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('ascii')
    require(len(raw) <= 16 * 1024**2, 'metadata size limit')
    return raw


def digest(value):
    return 'sha256:' + hashlib.sha256(canonical(value)).hexdigest()


def configuration(value):
    canonical(value)
    fields(value, ('format', 'name'), ('base', 'kernel', 'system', 'ports'))
    require(value['format'] == CONFIG, 'unsupported configuration format')
    token(value['name'])
    result = copy.deepcopy(value)
    for area in ('base', 'kernel', 'system', 'ports'):
        if area not in result:
            continue
        row = result[area]
        required = ('selector',) if area == 'base' else ('policy',) if area == 'kernel' else ('packages',)
        optional = ('source', 'active') if area == 'ports' else ('source', 'series', 'release') if area == 'kernel' else ('source',)
        fields(row, required, optional)
        if 'source' in row:
            token(row['source'])
        if area == 'base':
            parse_selector(row['selector'])
        elif area == 'kernel':
            require(row['policy'] in ('pinned', 'latest-lts', 'latest-upstream'), 'unknown Kernel policy')
            pins = [k for k in ('series', 'release') if k in row]
            require(len(pins) == (1 if row['policy'] == 'pinned' else 0), 'invalid Kernel pin fields')
            if 'series' in row:
                require(len(components(row['series'])) == 2, 'Kernel series requires major.minor')
            if 'release' in row:
                require(type(row['release']) is str, 'invalid Kernel release')
                parse_selector('linux@=' + row['release'])
        else:
            packages = row['packages']
            require(type(packages) is list and all(type(s) is str for s in packages), 'invalid package list')
            require(len(packages) == len(set(packages)), 'duplicate package selector')
            parsed = [parse_selector(s) for s in packages]
            if area == 'system':
                require(len({s.name for s in parsed}) == len(parsed), 'conflicting System roles')
            row['packages'] = sorted(packages)
            active = row.get('active', {})
            require(type(active) is dict, 'invalid active choices')
            for name, selector in active.items():
                require(selector in packages and parse_selector(selector).name == name, 'active choice lacks matching wish')
    return result


def parse_configuration(raw):
    require(type(raw) is bytes and len(raw) <= 16 * 1024**2, 'invalid configuration input/size')
    return configuration(tomllib.loads(raw.decode('utf-8')))


def claim(origin, selector, source):
    fields(origin, ('kind', 'name'))
    require(origin['kind'] in ('configuration', 'interactive'), 'invalid origin')
    token(origin['name']); token(source)
    row = dict(origin=copy.deepcopy(origin), role=parse_selector(selector).name,
               source=source, policy=dict(type='package', selector=selector))
    return dict(key=digest(dict(format='mojt-request-claim-v1', area='ports', **row)), **row)


def seal(description):
    d = copy.deepcopy(description)
    for key, field in (('configurations', 'name'), ('claims', 'key'), ('selections', 'role')):
        d[key].sort(key=lambda row: row[field])
    body = dict(format=STATE, description=d)
    return dict(**body, id=digest(body))


def empty_state(installation):
    require(type(installation) is str and re.fullmatch('[0-9a-f]{32}', installation), 'invalid installation identity')
    return seal(dict(installation=installation, area='ports', configurations=[], claims=[], selections=[]))


def _validate(state):
    canonical(state)
    fields(state, ('format', 'id', 'description'))
    require(state['format'] == STATE, 'unsupported request state')
    d = state['description']
    fields(d, ('installation', 'area', 'configurations', 'claims', 'selections'))
    require(d['area'] == 'ports', 'this increment supports Ports request state only')
    empty_state(d['installation'])
    for group, key in (('configurations','name'), ('claims','key'), ('selections','role')):
        require(type(d[group]) is list, 'invalid state collection')
        keys = [r[key] for r in d[group]]
        require(keys == sorted(keys) and len(keys) == len(set(keys)), 'unordered/duplicate state entries')
    require(state == seal(d), 'request state identity differs')
    configs = {}
    for row in d['configurations']:
        fields(row, ('name', 'revision', 'document'))
        doc = configuration(row['document'])
        require(doc == row['document'] and doc['name'] == row['name'] and digest(doc) == row['revision'], 'configuration revision differs')
        configs[row['name']] = doc
    claims = {}
    for row in d['claims']:
        fields(row, ('key', 'origin', 'role', 'source', 'policy'))
        fields(row['policy'], ('type', 'selector'))
        require(row['policy']['type'] == 'package' and row == claim(row['origin'], row['policy']['selector'], row['source']), 'invalid claim')
        claims[row['key']] = row
        if row['origin']['kind'] == 'configuration':
            name = row['origin']['name']
            require(name in configs, 'orphan configuration claim')
            area = configs[name].get('ports', {})
            require(row['policy']['selector'] in area.get('packages', []), 'claim absent from configuration')
            require('source' not in area or area['source'] == row['source'], 'configuration source mismatch')
    for name, doc in configs.items():
        own = [r['policy']['selector'] for r in claims.values() if r['origin'] == dict(kind='configuration', name=name)]
        require(sorted(own) == sorted(doc.get('ports', {}).get('packages', [])), 'incomplete configuration claims')
    for row in d['selections']:
        fields(row, ('role', 'origin', 'mode'), ('claim', 'reference'))
        fields(row['origin'], ('kind', 'name')); token(row['origin']['name'])
        require(row['origin']['kind'] in ('configuration','interactive'), 'unknown selection origin')
        require(parse_selector(row['role']).name == row['role'], 'invalid selection role')
        if row['mode'] == 'request':
            require(set(row) == {'role','origin','mode','claim'} and row['claim'] in claims, 'dangling active wish')
            c = claims[row['claim']]
            require(c['role'] == row['role'] and c['origin'] == row['origin'], 'active wish owner differs')
        else:
            require(row['mode'] == 'exact' and set(row) == {'role','origin','mode','reference'}, 'invalid selection mode')
            ref = row['reference']; require(type(ref) is dict, 'invalid reference')
            if ref.get('provider') == 'native':
                fields(ref, ('provider','artifact'))
                require(type(ref['artifact']) is str and re.fullmatch(ID, ref['artifact']), 'invalid exact artifact')
            else:
                fields(ref, ('provider','identity')); token(ref['provider'])
                require(type(ref['identity']) is dict and ref['identity'], 'missing opaque provider identity')
        if row['origin']['kind'] == 'configuration':
            require(row['origin']['name'] in configs, 'orphan active configuration')
    return copy.deepcopy(state)


def validate(state):
    try:
        return _validate(state)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('invalid request state structure') from error


def _declared_choices(d, choices, *, roles=None):
    """Resolve only adopted declarative defaults, with no file/provider access."""
    proposed = {}
    for config in sorted(d['configurations'], key=lambda r:r['name']):
        o = dict(kind='configuration', name=config['name'])
        for role, selector in config['document'].get('ports', {}).get('active', {}).items():
            if role in choices or roles is not None and role not in roles:
                continue
            matches = [r for r in d['claims'] if r['origin'] == o and r['policy']['selector'] == selector]
            require(len(matches) == 1, 'active configuration wish missing')
            if role in proposed:
                require(proposed[role][0] == (selector, matches[0]['source']), 'conflicting configuration defaults')
            else:
                proposed[role] = ((selector, matches[0]['source']), dict(role=role, origin=o, mode='request', claim=matches[0]['key']))
    return proposed


def reconcile_configuration(state, document, *, default_source=None):
    d = validate(state)['description']; doc = configuration(document)
    prior_choices = copy.deepcopy(d['selections'])
    prior_configs = {r['name']:r['document'] for r in d['configurations']}
    origin = dict(kind='configuration', name=doc['name'])
    previous_sources = {r['source'] for r in d['claims'] if r['origin'] == origin}
    area = doc.get('ports', {})
    source = area.get('source')
    if source is None:
        require(len(previous_sources) <= 1, 'ambiguous prior source binding')
        source = next(iter(previous_sources), default_source)
    if area.get('packages'):
        token(source)
    d['claims'] = [r for r in d['claims'] if r['origin'] != origin]
    d['claims'] += [claim(origin, s, source) for s in area.get('packages', [])]
    d['configurations'] = [r for r in d['configurations'] if r['name'] != doc['name']]
    d['configurations'].append(dict(name=doc['name'], revision=digest(doc), document=doc))
    # Recompute declarative defaults; interactive overrides mask, but do not erase them.
    choices = {r['role']:r for r in d['selections'] if r['origin']['kind'] == 'interactive'}
    proposed = _declared_choices(d, choices)
    # Preserve a still-owned first-install default supplied by the installer,
    # but not a formerly explicit file choice removed from the document.
    current_claims = {r['key'] for r in d['claims']}
    for old in prior_choices:
        role, o = old['role'], old['origin']
        if role in choices or role in proposed or o['kind'] != 'configuration' or old['mode'] != 'request':
            continue
        if old['claim'] in current_claims and role not in prior_configs[o['name']].get('ports', {}).get('active', {}):
            choices[role] = old
    d['selections'] = list(choices.values()) + [row for _, row in proposed.values()]
    return validate(seal(d))


def request_interactively(state, selector, source):
    d = validate(state)['description']
    row = claim(dict(kind='interactive', name='interactive'), selector, source)
    if not any(r['key'] == row['key'] for r in d['claims']):
        d['claims'].append(row)
    return validate(seal(d))


def select_interactively(state, role, reference):
    """Record intent only. Caller must separately verify installation and role."""
    d = validate(state)['description']
    d['selections'] = [r for r in d['selections'] if r['role'] != role]
    d['selections'].append(dict(role=role,origin=dict(kind='interactive',name='interactive'),mode='exact',reference=copy.deepcopy(reference)))
    return validate(seal(d))


def _restore_defaults(d, roles):
    choices = {r['role']:r for r in d['selections']}
    proposed = _declared_choices(d, choices, roles=roles)
    d['selections'] = list(choices.values()) + [row for _,row in proposed.values()]
    return validate(seal(d))


def remove_interactive(state, selectors, *, source=None):
    """Release interactive wishes only; bare roles also release their overrides.

    A selector-qualified release leaves independent exact overrides intact.
    A source-qualified release never clears an exact override's separate root.
    No configuration document/claim, dependency object or file is deleted.
    """
    d = validate(state)['description']
    require(type(selectors) is list and selectors, 'provide at least one wish selector')
    parsed = [(s,parse_selector(s)) for s in selectors]
    if source is not None:token(source)
    bare = {p.name for _,p in parsed if p.kind == 'latest'}
    def matches(c):
        return c['origin']['kind'] == 'interactive' and (source is None or c['source'] == source) and any(
            c['role'] == p.name and (p.kind == 'latest' or c['policy']['selector'] == text) for text,p in parsed)
    removed = {c['key'] for c in d['claims'] if matches(c)}
    d['claims'] = [c for c in d['claims'] if c['key'] not in removed]
    kept, cleared = [], set()
    for choice in d['selections']:
        drop = choice['origin']['kind'] == 'interactive' and (
            choice['mode'] == 'request' and choice['claim'] in removed or
            source is None and choice['role'] in bare)
        if drop:cleared.add(choice['role'])
        else:kept.append(choice)
    d['selections'] = kept
    return _restore_defaults(d, cleared)


def reset_selection(state, roles):
    """Release interactive active overrides; retain all installed wishes."""
    d = validate(state)['description']
    require(type(roles) is list and roles, 'provide at least one package role')
    for role in roles:
        parsed = parse_selector(role)
        require(parsed.kind == 'latest' and parsed.name == role, 'reset takes bare package roles')
    selected = set(roles)
    d['selections'] = [r for r in d['selections'] if not (r['role'] in selected and r['origin']['kind'] == 'interactive')]
    return _restore_defaults(d, selected)
