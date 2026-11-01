#!/usr/bin/env python3
"""Validate documentation workflow proposals, not execute a package manager.

Mojt Linux. Copyright (C) 2026 Jonas Persson.
SPDX-License-Identifier: GPL-2.0-only
"""
import copy
from datetime import datetime
import hashlib
import re
import sys
import tomllib

sys.dont_write_bytecode = True
import check_examples as core
sys.path.insert(0, str(core.ROOT.parents[2] / 'tools'))
from mpm_selection import parse_selector, components, Catalog, resolve
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

P = core.ROOT
W = P / 'workflow-examples'
S = core.SCHEMAS['workflow-formats.schema.json']
need, digest, seal = core.need, core.digest, core.seal
canon = lambda v: core.json.dumps(v,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode('ascii')
keyref = core.reference_key
validator = Draft202012Validator(S, registry=core.REGISTRY)


def normalized_config(value):
    schema = dict(S)
    schema.pop('oneOf')
    schema['$ref'] = '#/$defs/config_document'
    Draft202012Validator(schema, registry=core.REGISTRY).validate(value)
    core.scalar_gate(value)
    v = copy.deepcopy(value)
    for area in ('system','ports'):
        if area not in v:
            continue
        a = v[area]
        a['packages'].sort()
        selectors = [parse_selector(s) for s in a['packages']]
        if area == 'system':
            need(len({s.name for s in selectors}) == len(selectors), 'conflicting System roles')
        for name, text in a.get('active', {}).items():
            parsed = parse_selector(text)
            need(name == parsed.name and text in a['packages'], 'active selection without matching wish')
    if 'base' in v:
        parse_selector(v['base']['selector'])
    if 'kernel' in v:
        k = v['kernel']
        pins = [n for n in ('series','release') if n in k]
        need((len(pins) == 1) if k['policy'] == 'pinned' else not pins, 'invalid Kernel policy fields')
        if 'series' in k:
            need(len(components(k['series'])) == 2, 'Kernel series must be major.minor')
        if 'release' in k:
            parse_selector('linux@=' + k['release'])
    return v


def dag(rows):
    core.sorted_unique(rows, lambda r:r['key'])
    index = {r['key']:r for r in rows}
    pending, done = set(), set()
    def visit(key):
        need(key in index and key not in pending, 'missing dependency/cycle')
        if key in done:
            return
        pending.add(key)
        core.sorted_unique(index[key]['after'])
        for before in index[key]['after']:
            visit(before)
        pending.remove(key); done.add(key)
    for key in index:
        visit(key)


def validate(value):
    if value['format'] in core.FORMATS:
        return core.validate(value)
    core.scalar_gate(value)
    validator.validate(value)
    need(value['id'] == digest({k:v for k,v in value.items() if k != 'id'}), 'workflow identity mismatch')
    fmt, d = value['format'], value['description']
    if fmt == 'mojt-request-state-v1':
        core.sorted_unique(d['configurations'], lambda r:r['name'])
        configs = {r['name']:r for r in d['configurations']}
        for row in configs.values():
            doc = normalized_config(row['document'])
            need(doc == row['document'] and doc['name'] == row['name'] and digest(doc) == row['revision'], 'configuration revision mismatch')
        core.sorted_unique(d['claims'], lambda r:r['key'])
        claims = {r['key']:r for r in d['claims']}
        for row in claims.values():
            need(row['key'] == digest(dict(format='mojt-request-claim-v1',area=d['area'],**{k:v for k,v in row.items() if k != 'key'})), 'claim identity mismatch')
            origin, policy = row['origin'], row['policy']
            if policy['type'] == 'package':
                need(d['area'] != 'kernel' and parse_selector(policy['selector']).name == row['role'], 'wrong package role/area')
            else:
                need(d['area'] == 'kernel' and row['role'] == 'linux', 'wrong Kernel area/role')
                fields = {k:policy[k] for k in ('series','release') if policy[k] is not None}
                normalized_config(dict(format='mojt-configuration-v1',name='check',kernel=dict(policy=policy['mode'],**fields)))
            if origin['kind'] == 'configuration':
                need(origin['name'] in configs, 'orphan configuration claim')
                area_doc = configs[origin['name']]['document'].get(d['area'])
                need(area_doc is not None, 'claim from omitted configuration area')
                if 'source' in area_doc:
                    need(row['source'] == area_doc['source'], 'changed source binding')
                if policy['type'] == 'package':
                    expected = area_doc.get('packages',[area_doc.get('selector')])
                    need(policy['selector'] in expected, 'claim not in configuration')
                else:
                    need(policy['mode'] == area_doc['policy'] and policy['series'] == area_doc.get('series') and policy['release'] == area_doc.get('release'), 'Kernel claim differs from configuration')
        core.sorted_unique(d['selections'], lambda r:r['role'])
        for selection in d['selections']:
            if selection['mode'] == 'request':
                need(selection['claim'] in claims, 'dangling active request')
                claim = claims[selection['claim']]
                need(selection['origin'] == claim['origin'] and selection['role'] == claim['role'], 'active request owner mismatch')
            if selection['origin']['kind'] == 'configuration':
                need(selection['origin']['name'] in configs, 'orphan active configuration')
        for name, configuration in configs.items():
            area_doc = configuration['document'].get(d['area'], {})
            own = [r for r in claims.values() if r['origin'] == dict(kind='configuration',name=name)]
            if d['area'] in ('system','ports'):
                need(sorted(r['policy']['selector'] for r in own) == sorted(area_doc.get('packages',[])), 'incomplete adopted configuration')
            elif d['area'] == 'base':
                need([r['policy']['selector'] for r in own] == ([area_doc['selector']] if area_doc else []), 'incomplete Base configuration')
            else:
                need(len(own) == (1 if area_doc else 0), 'incomplete Kernel configuration')
    elif fmt == 'mojt-source-v1':
        if d['provider'] == 'native':
            core.path_gate(d['location']['path'], True)
    elif fmt == 'mojt-acquisition-map-v1':
        core.sorted_unique(d['offers'], lambda r:keyref(r['reference']))
        for offer in d['offers']:
            if offer['reference']['provider'] != 'native':
                continue
            core.path_gate(offer['descriptor']['path'])
            core.sorted_unique(offer['archives'], lambda r:r['sha256'])
            for archive in offer['archives']:
                core.sorted_unique(archive['paths'])
                for path in archive['paths']:
                    core.path_gate(path)
    elif fmt == 'mojt-cache-record-v1':
        need(d['artifact'] == d['descriptor'], 'cached wrong native descriptor')
        datetime.fromisoformat(d['verified_utc'].replace('Z','+00:00'))
    elif fmt == 'mojt-resolution-lock-v1':
        core.sorted_unique(d['snapshots'])
        core.sorted_unique(d['resolutions'], lambda r:r['claim'])
        for row in d['resolutions']:
            core.sorted_unique(row['dependencies'], keyref)
            if row['basis'] == 'catalog':
                need(row['snapshot'] in d['snapshots'] and row['evidence'] == row['snapshot'], 'unbound catalog resolution')
            else:
                need(row['snapshot'] is None, 'installed resolution requires no catalog')
    elif fmt == 'mojt-execution-plan-v1':
        core.sorted_unique(d['scope'])
        core.sorted_unique(d['baselines'], lambda r:r['area'])
        need([r['area'] for r in d['baselines']] == d['scope'], 'baseline/scope mismatch')
        for field in ('requests_after','locks','snapshots','required_capabilities','recovery'):
            core.sorted_unique(d[field])
        dag(d['steps'])
        if d['outcome'] == 'no-op':
            need(not d['steps'] and not d['blockers'], 'false no-op')
        elif d['outcome'] == 'ready':
            need(not d['blockers'], 'blocked ready plan')
        else:
            need(d['blockers'], 'blocked plan lacks explanation')
        for step in d['steps']:
            need(step['area'] in d['scope'], 'step expands scope')
            if step['type'] in ('acquire','install'):
                need(step['subject'] is not None and step['record'] is None and step['snapshot'] in d['snapshots'], 'unbound acquisition/install')
                if step['type'] == 'acquire' and step['subject']['provider'] == 'native':
                    need(step['transport_sha256'] is not None, 'native transport not frozen')
                else:
                    need(step['transport_sha256'] is None, 'unexpected transport')
            else:
                need(step['subject'] is None and step['record'] is not None and step['snapshot'] is None and step['transport_sha256'] is None, 'unexpected publication inputs')
                need(step['type'] != 'select-boot' or step['area'] != 'ports', 'Ports cannot select boot')
                need(step['type'] != 'publish-profile' or step['area'] == 'ports', 'boot areas publish through menu')
    elif fmt == 'mojt-execution-approval-v1':
        core.sorted_unique(d['scope'])
        datetime.fromisoformat(d['approved_utc'].replace('Z','+00:00'))
    elif fmt == 'mojt-boot-inputs-v2':
        need(d['boot']['profile'] == 'uefi-qemu-virtio-v1' and d['boot']['console'] == 'serial', 'unsupported initial boot profile')
        minimum, maximum = components(d['base']['kernel_min']), components(d['base']['kernel_max'])
        actual = components(d['kernel']['upstream'])
        need(minimum <= actual <= maximum, 'Kernel outside explicit Base bounds')
        core.sorted_unique(d['firmware'], keyref)
        args = d['boot']['extra_args']
        core.sorted_unique(args, lambda s:s.split('=')[0])
        need(all(re.fullmatch(r'quiet|loglevel=[0-7]|panic=(0|[1-9][0-9]*)',a) for a in args), 'reserved/unsupported cmdline')
        core.sorted_unique(d['management_required'],lambda r:r['family'])
        for row in d['management_required'] + d['state_requirements']:
            core.sorted_unique(row['read']);core.sorted_unique(row['write'])
            need(set(row['write']) <= set(row['read']), 'unsupported writer')
    elif fmt == 'mojt-boot-deployment-v2':
        validate(d['inputs']);validate(d['initramfs'])
        inputs, binding = d['inputs']['description'],d['initramfs']['description']
        need(binding['inputs'] == d['inputs']['id'] and binding['constructor'] == inputs['constructor'], 'wrong initramfs binding')
        core.sorted_unique(d['files'],lambda r:r['path'])
        files = {r['path']:r for r in d['files']}
        need(set(files) == {'initramfs.cpio.gz','vmlinuz'}, 'unexpected boot-slot file')
        need({k:v for k,v in files['initramfs.cpio.gz'].items() if k != 'path'} == binding['archive'], 'initramfs bytes differ')
        need(files['vmlinuz']['sha256'] == inputs['kernel']['image_sha256'], 'Kernel bytes differ')
    elif fmt == 'mojt-boot-selection-v2':
        core.sorted_unique(d['entries'],lambda r:r['deployment'])
        entries = {r['deployment'] for r in d['entries']}
        need(d['selected'] in entries and (d['previous'] is None or d['previous'] in entries), 'dangling boot choice')
        core.sorted_unique(d['requests'],lambda r:r['area'])
        need([r['area'] for r in d['requests']] == ['base','kernel','system'], 'incomplete boot request roots')
        for row in d['entries']:
            core.path_gate(row['path'])
            need(row['path'] == 'boot/mojt/deployments/'+row['deployment'].split(':')[1], 'slot/identity mismatch')
    return value


def bindings(ex):
    src, snap = ex['source']['description'],ex['source-snapshot']['description']
    acq, cache = ex['acquisition-map']['description'],ex['cache-record']['description']
    need(snap['source'] == ex['source']['id'] and snap['trust_policy'] == src['trust']['policy'], 'snapshot source/policy mismatch')
    need((src['provider'] == 'native' and snap['provider_snapshot'] is None) or (snap['provider_snapshot'] is not None and snap['provider_snapshot']['provider'] == src['provider']), 'snapshot provider changed')
    raw = (W/'catalog.fixture').read_bytes()
    need(hashlib.sha256(raw).hexdigest() == snap['catalog']['sha256'] == acq['catalog_sha256'] and len(raw) == snap['catalog']['size'], 'catalog bytes changed')
    catalog = Catalog.from_dict(core.json.loads(raw))
    map_bytes = canon(ex['acquisition-map'])+b'\n'
    need(snap['acquisition'] == dict(id=ex['acquisition-map']['id'],sha256=hashlib.sha256(map_bytes).hexdigest(),size=len(map_bytes)), 'acquisition metadata changed')
    need(cache['source_snapshot'] == ex['source-snapshot']['id'] and cache['acquisition_map'] == ex['acquisition-map']['id'] and cache['trust_policy'] == snap['trust_policy'], 'cache acceptance changed')
    offer = next(r for r in acq['offers'] if r['reference'] == dict(provider='native',artifact=cache['artifact']))
    need(any(cache['archive'] == {k:v for k,v in a.items() if k != 'paths'} for a in offer['archives']), 'wrong cached encoding')
    state, lock = ex['request-state']['description'],ex['resolution-lock']['description']
    need(lock['requests'] == ex['request-state']['id'] and lock['installation'] == state['installation'], 'lock/request mismatch')
    need(lock['area'] == state['area'], 'lock area changed')
    claims = {r['key']:r for r in state['claims']}
    need(set(claims) == {r['claim'] for r in lock['resolutions']}, 'incomplete claimed resolution')
    for row in lock['resolutions']:
        claim = claims[row['claim']]
        need(claim['source'] == src['name'], 'claim source changed')
        need(row['snapshot'] == ex['source-snapshot']['id'], 'wrong source snapshot')
        need(row['reference'] in [r['reference'] for r in acq['offers']], 'unoffered exact reference')
        need(catalog.name == claim['role'], 'catalog role mismatch')
        selected = resolve(catalog,claim['policy']['selector'],platform='x86_64-linux')
        need(selected.candidate.backend == row['reference']['provider'] and selected.candidate.artifact == row['reference'].get('artifact'), 'lock does not resolve the requested selector')
    p, a = ex['execution-plan']['description'],ex['execution-approval']['description']
    need(a['plan'] == ex['execution-plan']['id'] and a['scope'] == p['scope'] and a['installation'] == p['target']['installation'], 'approval scope/target/plan mismatch')
    need(state['installation'] == p['target']['installation'] and state['area'] in p['scope'], 'requests for another target/area')
    need(p['requests_after'] == [ex['request-state']['id']] and p['locks'] == [ex['resolution-lock']['id']], 'plan content changed')
    for step in p['steps']:
        if step['type'] == 'acquire':
            need(step['subject'] == offer['reference'] and step['transport_sha256'] == cache['archive']['sha256'], 'plan bytes changed')
    b, selection = ex['boot-inputs']['description'],ex['boot-selection']['description']
    need(selection['installation'] == b['installation'] and selection['selected'] == ex['boot-deployment']['id'], 'boot target/selection mismatch')
    need(ex['boot-deployment']['description']['inputs'] == ex['boot-inputs'] and ex['boot-deployment']['description']['initramfs'] == ex['initramfs-binding'], 'boot sidecars changed')
    composition = ex['system-composition']['description']
    need(b['system']['composition'] == ex['system-composition']['id'], 'wrong System composition')
    caps = {r['family']:r for r in composition['management']}
    for required in b['management_required']:
        need(required['family'] in caps, 'missing manager family')
        actual = caps[required['family']]
        need(set(required['read']) <= set(actual['read']) and set(required['write']) <= set(actual['write']) and set(required['capabilities']) <= set(actual['capabilities']), 'old manager cannot handle boot state')


def reconcile_example(original, document):
    d = copy.deepcopy(original['description'])
    name = document['name']
    d['configurations'] = [r for r in d['configurations'] if r['name'] != name] + [dict(name=name,revision=digest(document),document=document)]
    d['configurations'].sort(key=lambda r:r['name'])
    d['claims'] = [r for r in d['claims'] if r['origin'] != dict(kind='configuration',name=name)]
    d['selections'] = [r for r in d['selections'] if r['origin'] != dict(kind='configuration',name=name)]
    return seal(dict(format=original['format'],description=d))


def main():
    core.main()
    ex = {p.stem:validate(core.read(p)) for p in W.glob('*.json')}
    doc = normalized_config(tomllib.loads((W/'mojt-configuration.toml').read_text()))
    need(doc == ex['request-state']['description']['configurations'][0]['document'], 'TOML adoption differs')
    bindings(ex)
    removed_doc = ex['request-state-config-removed']['description']['configurations'][0]['document']
    need(reconcile_example(ex['request-state'],removed_doc) == ex['request-state-config-removed'], 'configuration removal erased interactive wishes/choice')
    configured = copy.deepcopy(ex['request-state'])
    configured['description']['claims'] = [r for r in configured['description']['claims'] if r['origin']['kind'] == 'configuration']
    claim = configured['description']['claims'][0]
    configured['description']['selections'] = [dict(role='hello',origin=claim['origin'],mode='request',claim=claim['key'])]
    seal(configured);validate(configured)
    need(reconcile_example(configured,removed_doc) == ex['request-state-empty'], 'configuration-only package remained directly requested')
    need(ex['request-state']['description']['selections'] == ex['request-state-config-removed']['description']['selections'], 'lost interactive precedence')
    offline = copy.deepcopy(ex['resolution-lock'])
    offline['description']['snapshots'] = []
    for row in offline['description']['resolutions']:
        row.update(basis='installed',snapshot=None,evidence=digest('retained verified installation receipt'))
    seal(offline);validate(offline)
    rejected = []
    def reject(label,name,mutate,cross=False):
        values = copy.deepcopy(ex)
        value = values[name]
        mutate(value)
        seal(value)
        try:
            validate(value)
            if cross:
                bindings(values)
        except (ValueError,KeyError,TypeError,StopIteration,ValidationError):
            rejected.append(label)
        else:
            raise AssertionError('invalid workflow accepted: '+label)
    reject('unknown workflow version','source',lambda v:v.update(format='mojt-source-v999'))
    reject('native source escapes','source',lambda v:v['description']['location'].update(path='/srv/../etc'))
    reject('unapproved native network','source',lambda v:v['description']['location'].update(kind='https',path='https://example.invalid'))
    reject('source policy rebound','source-snapshot',lambda v:v['description'].update(trust_policy=digest('different')),True)
    reject('source provider fallback','source-snapshot',lambda v:v['description'].update(provider_snapshot=dict(provider='nix',identity=dict(path='other'))),True)
    reject('catalog bytes changed','acquisition-map',lambda v:v['description'].update(catalog_sha256='0'*64),True)
    reject('map bytes changed','source-snapshot',lambda v:v['description']['acquisition'].update(sha256='0'*64),True)
    reject('archive path escape','acquisition-map',lambda v:v['description']['offers'][0]['archives'][0].update(paths=['../secret']))
    reject('cache wrong artifact','cache-record',lambda v:v['description'].update(descriptor=digest('other')))
    reject('cache unlisted archive','cache-record',lambda v:v['description']['archive'].update(sha256='0'*64),True)
    reject('cache policy changed','cache-record',lambda v:v['description'].update(trust_policy=digest('other')),True)
    reject('orphan origin','request-state',lambda v:v['description']['claims'][0]['origin'].update(name='unadopted'))
    reject('config revision forged','request-state',lambda v:v['description']['configurations'][0].update(revision=digest('forged')))
    reject('active missing claim','request-state',lambda v:v['description']['selections'][0].update(mode='request',claim=digest('absent')))
    reject('lock different request snapshot','resolution-lock',lambda v:v['description'].update(requests=digest('other')),True)
    reject('lock omits claim','resolution-lock',lambda v:v['description']['resolutions'].pop(),True)
    reject('configuration wish silently dropped','request-state',lambda v:v['description'].update(claims=[r for r in v['description']['claims'] if r['origin']['kind']=='interactive']))
    reject('catalog basis lacks snapshot','resolution-lock',lambda v:v['description']['resolutions'][0].update(snapshot=None))
    reject('plan step expands scope','execution-plan',lambda v:v['description']['steps'][0].update(area='system'))
    reject('plan accepts arbitrary script','execution-plan',lambda v:v['description']['steps'][0].update(command='sh -c true'))
    reject('plan cycle','execution-plan',lambda v:v['description']['steps'][0].update(after=['select-profile']))
    reject('plan baseline omitted','execution-plan',lambda v:v['description'].update(baselines=[]))
    reject('plan transport changed','execution-plan',lambda v:v['description']['steps'][0].update(transport_sha256='0'*64),True)
    reject('unapproved executor changed','execution-plan',lambda v:v['description'].update(executor=dict(provider='native',artifact=digest('other manager'))),True)
    reject('ready but blocked','execution-plan',lambda v:v['description'].update(blockers=[dict(code='unknown',message='missing data')]))
    reject('false no-op','execution-plan',lambda v:v['description'].update(outcome='no-op'))
    reject('approval expands scope','execution-approval',lambda v:v['description'].update(scope=['ports','system']),True)
    reject('approval other target','execution-approval',lambda v:v['description'].update(installation='f'*32),True)
    reject('approval for other plan','execution-approval',lambda v:v['description'].update(plan=digest('other')),True)
    reject('Kernel above Base max','boot-inputs',lambda v:v['description']['kernel'].update(upstream='7.2.9'))
    reject('reserved root argument','boot-inputs',lambda v:v['description']['boot'].update(extra_args=['root=/dev/other']))
    reject('unsupported boot profile','boot-inputs',lambda v:v['description']['boot'].update(profile='unknown'))
    reject('unsupported local console','boot-inputs',lambda v:v['description']['boot'].update(console='local'))
    reject('unsupported profile data','boot-inputs',lambda v:v['description']['boot'].update(command='grub-install'))
    reject('binding wrong inputs','boot-deployment',lambda v:v['description']['initramfs']['description'].update(inputs=digest('other')))
    reject('wrong initramfs hash','boot-deployment',lambda v:v['description']['files'][0].update(sha256='0'*64))
    reject('wrong Kernel hash','boot-deployment',lambda v:v['description']['files'][1].update(sha256='0'*64))
    reject('extra boot file','boot-deployment',lambda v:v['description']['files'].append(dict(path='evil',sha256='0'*64,size=0)))
    reject('selected unretained deployment','boot-selection',lambda v:v['description'].update(selected=digest('absent')))
    reject('previous unretained deployment','boot-selection',lambda v:v['description'].update(previous=digest('absent')))
    reject('slot mismatches ID','boot-selection',lambda v:v['description']['entries'][0].update(path='boot/mojt/deployments/wrong'))
    reject('request roots omitted','boot-selection',lambda v:v['description']['requests'].pop())
    reject('old System manager','system-composition',lambda v:v['description']['management'].pop(0),True)
    for invalid in [dict(format='mojt-configuration-v1',name='bad',ports=dict(packages=['hello@2.*'])),
                    dict(format='mojt-configuration-v1',name='bad',ports=dict(packages=['hello'],active=dict(hello='hello@3.0'))),
                    dict(format='mojt-configuration-v1',name='bad',kernel=dict(policy='latest-lts',series='6.12')),
                    dict(format='mojt-configuration-v1',name='bad',kernel=dict(policy='pinned')),
                    dict(format='mojt-configuration-v1',name='bad',system=dict(packages=['hello@2.1','hello@2.2']))]:
        try:
            normalized_config(invalid)
        except (ValueError,KeyError,TypeError,ValidationError):
            rejected.append('invalid configuration policy')
        else:
            raise AssertionError('invalid configuration accepted')
    print(f'PASS: 13 workflow record definitions, {len(ex)} linked JSON examples, TOML normalization, 3 origin/reconciliation scenarios, offline installed lock, {len(rejected)} rejected workflow cases')
    print('Synthetic documentation validation only; no network, import, installation, handler execution or boot.')


if __name__ == '__main__':
    main()
