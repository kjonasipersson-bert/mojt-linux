# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pure Ports wish resolution and preparation plans. No IO or provider execution."""
import copy
import re

import mpm_requests as requests
from mpm_selection import Catalog, resolve


def require(ok, message):
    if not ok:
        raise ValueError(message)


def reference(value):
    requests.canonical(value)
    require(type(value) is dict, 'invalid reference')
    if value.get('provider') == 'native':
        requests.fields(value, ('provider','artifact'))
        require(type(value['artifact']) is str and re.fullmatch(requests.ID,value['artifact']), 'invalid native reference')
    else:
        requests.fields(value, ('provider','identity')); requests.token(value['provider'])
        require(type(value['identity']) is dict and value['identity'], 'missing provider identity')
    return copy.deepcopy(value)


def key(value):
    return requests.canonical(reference(value))


def identity(value):
    require(type(value) is str and re.fullmatch(requests.ID,value), 'invalid content identity')
    return value


def record(fmt, description):
    body = dict(format=fmt,description=description)
    return dict(**body,id=requests.digest(body))


def sources_view(sources):
    requests.canonical(sources)
    require(type(sources) is dict, 'invalid source view')
    result = copy.deepcopy(sources)
    for name, source in result.items():
        requests.token(name); requests.fields(source, ('snapshot','catalogs','offers'))
        identity(source['snapshot'])
        require(type(source['catalogs']) is dict and type(source['offers']) is list, 'invalid finite source view')
        seen = set()
        for offer in source['offers']:
            requests.fields(offer, ('backend','artifact','integrity','reference','dependencies','transport_sha256'))
            ref = reference(offer['reference']); requests.token(offer['backend'])
            require(offer['backend'] == ref['provider'] and type(offer['artifact']) is str and offer['artifact'], 'offer backend differs')
            require(type(offer['integrity']) is dict and offer['integrity'], 'missing provider integrity evidence')
            require(type(offer['dependencies']) is list, 'invalid dependencies')
            deps = [key(r) for r in offer['dependencies']]
            require(len(set(deps)) == len(deps), 'duplicate dependency')
            k = key(ref); require(k not in seen, 'ambiguous offer'); seen.add(k)
            if ref['provider'] == 'native':
                require(offer['artifact'] == ref['artifact'] and type(offer['transport_sha256']) is str and re.fullmatch('[0-9a-f]{64}',offer['transport_sha256']), 'native offer needs exact archive binding')
            else:
                require(offer['transport_sha256'] is None, 'provider transport belongs to its adapter')
        for name_, raw in source['catalogs'].items():
            catalog = Catalog.from_dict(raw)
            require(catalog.area == 'ports' and catalog.name == name_, 'wrong catalog area/name')
    return result


def resolve_claim(claim, sources, *, platform):
    require(claim['source'] in sources, 'missing named source; refresh/bind it explicitly')
    source = sources[claim['source']]
    require(claim['role'] in source['catalogs'], 'missing package metadata')
    chosen = resolve(Catalog.from_dict(source['catalogs'][claim['role']]), claim['policy']['selector'], platform=platform).candidate
    offers = [o for o in source['offers'] if o['backend'] == chosen.backend and o['artifact'] == chosen.artifact]
    require(len(offers) == 1 and offers[0]['integrity'] == chosen.integrity, 'missing/contradictory exact adapter binding')
    offer = offers[0]
    return dict(claim=claim['key'], basis='catalog', snapshot=source['snapshot'], evidence=source['snapshot'],
                reference=offer['reference'], dependencies=sorted(offer['dependencies'], key=key))


def resolve_requests(state, sources, *, platform):
    """Bind each wish using its named accepted snapshot and explicit adapter offers.

    Offers are caller-validated metadata, not proof of availability, trust or ABI.
    This first resolver uses catalog basis; installed-only activation stays separate.
    """
    requests.token(platform)
    d = requests.validate(state)['description']; sources = sources_view(sources)
    rows, snapshots = [], set()
    for claim in d['claims']:
        row = resolve_claim(claim, sources, platform=platform)
        snapshots.add(row['snapshot']); rows.append(row)
    return record('mojt-resolution-lock-v1',dict(installation=d['installation'],area='ports',requests=state['id'],
                  snapshots=sorted(snapshots),resolutions=sorted(rows,key=lambda r:r['claim'])))


def prepare_requests(before, after, lock, sources, *, platform, target_identity, executor, installed=(), selected=None, running=None):
    """Prepare acquisitions/imports and retain candidate wishes; never publish a profile.

    installed contains exact references freshly verified by the caller. Dependency
    closure must be finite within each explicitly bound source in this increment.
    """
    d = requests.validate(after)['description']; old = requests.validate(before)['description'] if before is not None else None
    require(old is None or old['installation'] == d['installation'], 'different installation baseline')
    identity(target_identity); reference(executor)
    for v in (selected,running):
        if v is not None: identity(v)
    sources = sources_view(sources)
    expected = resolve_requests(after,sources,platform=platform)
    require(lock == expected, 'resolution lock is stale or differs from exact inputs')
    present = {key(r) for r in installed}
    for choice in d['selections']:
        if choice['mode'] == 'exact':
            require(key(choice['reference']) in present, 'exact active override is not verified installed content')
    claims = {r['key']:r for r in d['claims']}
    steps, generated = {}, {}
    def retain(ref, source_name, visiting):
        k = key(ref)
        if k in present: return None
        require(k not in visiting, 'dependency cycle')
        require(len(visiting) < 64, 'dependency depth limit')
        source = sources[source_name]
        candidates = [o for o in source['offers'] if key(o['reference']) == k]
        require(len(candidates) == 1, 'dependency requires an explicit exact offer in its named source')
        offer = candidates[0]
        signature = (source['snapshot'],offer)
        if k in generated:
            require(generated[k][0] == signature, 'shared reference has conflicting acquisition bindings')
            return generated[k][1]
        acquire = requests.digest(dict(operation='acquire',reference=ref)).split(':')[1]
        install = requests.digest(dict(operation='install',reference=ref)).split(':')[1]
        deps = [retain(dep,source_name,visiting|{k}) for dep in sorted(offer['dependencies'],key=key)]
        steps[acquire] = dict(key=acquire,area='ports',type='acquire',after=[],subject=copy.deepcopy(ref),record=None,
                              snapshot=source['snapshot'],transport_sha256=offer['transport_sha256'])
        steps[install] = dict(key=install,area='ports',type='install',after=sorted({acquire,*[v for v in deps if v]}),subject=copy.deepcopy(ref),record=None,
                              snapshot=source['snapshot'],transport_sha256=None)
        generated[k] = (signature,install)
        return install
    for row in lock['description']['resolutions']:
        retain(row['reference'],claims[row['claim']]['source'],set())
    if before is None or before != after:
        steps['retain-requests'] = dict(key='retain-requests',area='ports',type='retain-requests',after=sorted(k for k in steps if steps[k]['type']=='install'),
                                        subject=None,record=after['id'],snapshot=None,transport_sha256=None)
    return record('mojt-execution-plan-v1',dict(target=dict(installation=d['installation'],platform=platform,layout='kind-id-v1',identity=target_identity),
        executor=copy.deepcopy(executor),scope=['ports'],baselines=[dict(area='ports',requests=before['id'] if before else None,selection=selected)],running=running,
        requests_after=[after['id']],locks=[lock['id']],snapshots=lock['description']['snapshots'],steps=[steps[k] for k in sorted(steps)],
        required_capabilities=['mpm-request-origins-v1'],recovery=[],effects=[],outcome='ready' if steps else 'no-op',blockers=[]))


def revalidate_preparation(plan, *, installation, current, selected, target_identity, executor):
    """Pure late baseline guard. Caller must hold resource locks and verify content."""
    requests.fields(plan, ('format','id','description'))
    require(plan['format'] == 'mojt-execution-plan-v1' and plan['id'] == requests.digest({k:v for k,v in plan.items() if k!='id'}), 'invalid plan')
    d = plan['description']
    requests.fields(d, ('target','executor','scope','baselines','running','requests_after','locks','snapshots','steps','required_capabilities','recovery','effects','outcome','blockers'))
    requests.fields(d['target'], ('installation','platform','layout','identity'))
    for step in d['steps']:
        requests.fields(step, ('key','area','type','after','subject','record','snapshot','transport_sha256'))
        require(step['area'] == 'ports' and step['type'] in ('acquire','install','retain-requests'), 'not a preparation step')
    require(len(d['baselines']) == 1 and d['baselines'][0]['area'] == 'ports', 'unsupported plan baseline')
    baseline = d['baselines'][0]
    requests.fields(baseline, ('area','requests','selection'))
    require(d['scope'] == ['ports'] and d['outcome'] in ('ready','no-op'), 'unsupported/blocked plan')
    require(not d['blockers'] and not d['effects'], 'not a pure preparation plan')
    require(d['outcome'] != 'no-op' or not d['steps'], 'invalid no-op plan')
    state = requests.validate(current) if current is not None else None
    require((state['id'] if state else None) == baseline['requests'] and selected == baseline['selection'], 'baseline changed; prepare a new plan')
    require(installation == d['target']['installation'] and target_identity == d['target']['identity'] and executor == d['executor'], 'target/executor changed')
    return True
