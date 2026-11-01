# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Fresh Ports frontend over accepted finite sources; no implicit catalog refresh."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

import mpm_ports_profile as profiles
import mpm_request_plan as planning
import mpm_requests as wishes
from mpm_selection import Catalog, parse_selector, resolve

SOURCES = 'mojt-ports-sources-v1'
SUPPORTED_STATE_FORMATS = ('mojt-ports-profile-v1',)
SUPPORTED_CAPABILITIES = ('mpm-request-origins-v1',)
READ_ONLY = {'status', 'list', 'history', 'search', 'info'}
ACTIONS = READ_ONLY | {'update', 'install', 'activate', 'upgrade', 'apply'}
require = wishes.require


def source_bundle(value, platform):
    """An explicit local operator input, not proof of metadata authenticity."""
    d = profiles.verify_record(value, SOURCES)
    wishes.fields(d, ('platform', 'sources'))
    require(d['platform'] == platform, 'sources target another platform')
    return planning.sources_view(d['sources'])


def executor_identity(runtime):
    files = ('mpm_cli.py', 'mpm_ports_cli.py', 'mpm_requests.py',
             'mpm_request_plan.py', 'mpm_ports_profile.py', 'mpm_nix_binary.py',
             'mpm_selection.py', 'mpm_transaction.py')
    directory = Path(__file__).parent
    return dict(provider='mpm-runtime', identity=dict(format='mojt-mpm-executor-v1',
        files={name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in files},
        python=str(Path(sys.executable).resolve()),
        helpers=str(runtime.system_bin) if runtime else 'explicit-caller-path'))


def adapters_for(sources, previous, runtime):
    refs = [o['reference'] for s in sources.values() for o in s['offers']]
    if previous:
        refs += [o['reference'] for o in previous['record']['description']['objects']]
    providers = {r['provider'] for r in refs}
    require(providers <= {'nix'}, 'unsupported Ports provider: ' + ', '.join(sorted(providers - {'nix'})))
    if not providers:
        return {}
    from mpm_nix_binary import NixBinaryAdapter
    binary = runtime.system_bin / 'nix-store' if runtime else Path(shutil.which('nix-store') or '/nonexistent/nix-store')
    return {'nix': NixBinaryAdapter(binary.absolute())}


def installed_choice(state, request, platform):
    packages = state['packages']
    if request.startswith('sha256:'):
        found = [p for p in packages if wishes.digest(p['reference']) == request]
        require(len(found) == 1, 'exact installed reference is missing or ambiguous')
        return found[0]
    parsed = parse_selector(request)
    candidates, sources = [], {}
    for p in packages:
        if p['role'] != parsed.name:
            continue
        ref = p['reference']; provider = ref['provider']; artifact = wishes.digest(ref)
        sources[provider] = dict(backend=provider, identity=dict(basis='installed'))
        candidates.append(dict(name=p['role'], release_id=p['release_id'], **copy.deepcopy(p['release']),
            source=provider, artifact=artifact, integrity=dict(reference=ref)))
    require(candidates, 'package is not installed')
    catalog = Catalog.from_dict(dict(format='mpm-release-catalog-v1', area='ports', name=parsed.name,
        channel='installed', platform=platform, sources=sources, candidates=candidates))
    chosen = resolve(catalog, request, platform=platform).candidate.artifact
    return next(p for p in packages if wishes.digest(p['reference']) == chosen)


def parser():
    p = argparse.ArgumentParser(prog='mpm ports', description=__doc__)
    actions = p.add_subparsers(dest='action', required=True)
    for action in sorted(ACTIONS):
        sub = actions.add_parser(action)
        sub.add_argument('--root', type=Path)
        if action not in READ_ONLY:
            sub.add_argument('--sources', type=Path, help='explicit mojt-ports-sources-v1 snapshot bundle')
            sub.add_argument('--expected-sources', help='required content identity of the supplied bundle')
            sub.add_argument('--dry-run', action='store_true')
            sub.add_argument('-y', '--yes', action='store_true')
        if action == 'install':
            sub.add_argument('names', nargs='+')
            sub.add_argument('--source', help='named accepted source; mandatory if more than one exists')
            sub.add_argument('--no-activate', action='store_true')
        if action == 'activate':
            sub.add_argument('request', help='installed selector or full exact reference ID from list --exact')
            sub.add_argument('--follow', action='store_true')
        if action == 'upgrade':
            sub.add_argument('names', nargs='*')
        if action == 'apply':
            sub.add_argument('--configuration', type=Path, required=True)
        if action == 'history':
            sub.add_argument('--limit', type=int, default=20)
        if action == 'list':
            sub.add_argument('--exact', action='store_true')
        if action == 'search':
            sub.add_argument('query'); sub.add_argument('--limit', type=int, default=50)
        if action == 'info':
            sub.add_argument('name')
        sub.add_argument('--json', action='store_true')
    return p


def inspect(root, args, previous, platform):
    state = previous['record']['description'] if previous else None
    if args.action == 'history':
        rows = profiles.history(root, args.limit)
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for row in rows:
                d = row['description']
                print(f"{d['sequence']} {d['utc']} {d['action']} uid={d['uid']} {d['after']}")
            if not rows:
                print('No recorded transactions.')
    elif args.action == 'status':
        print(json.dumps(dict(format=profiles.MARKER, root=str(root),
            profile=previous['record']['id'] if previous else None,
            installed=state['packages'] if state else [], requests=state['requests'] if state else None,
            active=state['active'] if state else {}, aliases=state['aliases'] if state else {},
            sources=state['sources'] if state else {}), indent=2))
    elif args.action == 'list':
        packages = state['packages'] if state else []
        if args.json:
            print(json.dumps(packages, indent=2))
        else:
            for p in packages:
                active = state['active'].get(p['role']) == p['reference']
                print(('* ' if active else '  ') + p['role'] + '@=' + p['release_id'] +
                      (' ' + wishes.digest(p['reference']) if args.exact else ''))
    elif args.action == 'search':
        require(1 <= args.limit <= 200 and args.query and not any(ord(c) < 32 for c in args.query), 'invalid literal search/limit')
        names = sorted({name for s in state['sources'].values() for name in s['catalogs']
                        if args.query.casefold() in name.casefold()}) if state else []
        rows = names[:args.limit]
        print(json.dumps(dict(matches=rows, total=len(names)), indent=2) if args.json else '\n'.join(rows))
    else:
        require(state is not None, 'no installed Ports profile')
        print(json.dumps(installed_choice(state, args.name, platform), indent=2))
    return 0


def main(argv, *, root=None, runtime=None, adapters=None):
    args = parser().parse_args(argv)
    if root is not None and args.root is not None:
        raise ValueError('specify --root only once')
    root = profiles.safe_root(args.root or root or (runtime.ports if runtime else Path('/var/lib/mojt/ports')))
    previous = profiles.current(root)
    platform = os.uname().machine + '-linux'
    if args.action in READ_ONLY:
        return inspect(root, args, previous, platform)
    if runtime is not None:
        require(os.geteuid() == 0, 'shared installation changes require an administrator')
    # Writer permission is checked before reading operator inputs or provider work.
    profiles.safe_root(root, write=True)
    old = previous['record']['description'] if previous else None
    installation = old['installation'] if old else (profiles.marker(root)['installation']
        if (root / 'store.json').exists() else uuid.uuid4().hex)
    state = copy.deepcopy(old['requests']) if old else wishes.empty_state(installation)
    if args.sources:
        bundle = profiles.read(args.sources)
        if args.expected_sources:
            require(bundle['id'] == args.expected_sources, 'source bundle identity differs')
        sources = source_bundle(bundle, platform)
    else:
        require(not args.expected_sources, '--expected-sources requires --sources')
        sources = copy.deepcopy(old['sources']) if old else {}
    require(args.action != 'update' or args.sources is not None, 'update needs an explicit --sources snapshot bundle')
    require(args.action == 'update' or old is not None or args.sources is not None, 'initial operation needs --sources FILE')
    before_keys = {c['key'] for c in state['description']['claims']}
    advance = []
    if args.action == 'install':
        source = args.source or (next(iter(sources)) if len(sources) == 1 else None)
        require(source in sources, 'specify one accepted --source NAME')
        for selector in args.names:
            state = wishes.request_interactively(state, selector, source)
        # New wishes resolve now; accepted existing wishes do not advance here.
    elif args.action == 'apply':
        document = wishes.parse_configuration(args.configuration.read_bytes())
        require(not (set(document) & {'base', 'system', 'kernel'}), 'ports apply supports only Ports; other areas require their own implementation')
        default = next(iter(sources)) if len(sources) == 1 else None
        state = wishes.reconcile_configuration(state, document, default_source=default)
        advance = [c['key'] for c in state['description']['claims']
                   if c['origin'] == dict(kind='configuration', name=document['name'])]
    elif args.action == 'upgrade':
        names = set(args.names)
        roles = {c['role'] for c in state['description']['claims']}
        require(not names - roles, 'upgrade names must have recorded wishes')
        advance = [c['key'] for c in state['description']['claims']
                   if (not names or c['role'] in names) and parse_selector(c['policy']['selector']).kind != 'exact']
    elif args.action == 'activate':
        require(old is not None, 'activation needs an installed profile')
        package = installed_choice(old, args.request, platform)
        parsed = None if args.request.startswith('sha256:') else parse_selector(args.request)
        follows = [c for c in state['description']['claims'] if c['origin']['kind'] == 'interactive' and c['role'] == package['role'] and
                   parse_selector(c['policy']['selector']).kind != 'exact' and
                   any(r['claim'] == c['key'] and r['reference'] == package['reference'] for r in old['lock']['description']['resolutions'])]
        if args.follow or parsed is not None and parsed.kind != 'exact':
            if parsed is not None:
                follows = [c for c in follows if c['policy']['selector'] == args.request]
            require(len(follows) == 1, 'activation needs one matching accepted following wish; use an exact reference or install that selector first')
            claim = follows[0]
            # A user's following choice must remain interactive even if the
            # matching target originally came from configuration.
            state = wishes.request_interactively(state, claim['policy']['selector'], claim['source'])
            c = next(c for c in state['description']['claims'] if c['origin']['kind'] == 'interactive'
                     and c['policy'] == claim['policy'] and c['source'] == claim['source'])
            # Do not resolve a new interactive claim through fresher metadata.
            # The binding is installed and must be accepted before following.
            require(c['key'] in before_keys, 'install the matching interactive wish before following it')
            d = state['description'];d['selections'] = [s for s in d['selections'] if s['role'] != package['role']]
            d['selections'].append(dict(role=package['role'], origin=c['origin'], mode='request', claim=c['key']))
            state = wishes.validate(wishes.seal(d))
        else:
            state = wishes.select_interactively(state, package['role'], package['reference'])
    if adapters is None:
        adapters = adapters_for(sources, previous, runtime)
    options = dict(platform=platform, executor=executor_identity(runtime),
        target_identity=wishes.digest(dict(root=str(root), installation=installation)))
    plan = profiles.preview(root, state, sources, adapters, **options, advance=advance,
                            auto_select=not getattr(args, 'no_activate', False))
    if args.dry_run:
        print(json.dumps(dict(dry_run=True, changed=False, plan=plan), indent=2)); return 0
    if not args.yes:
        candidate = plan['description']['candidate']
        print(json.dumps(dict(root=str(root), action=args.action, plan=plan['id'],
            unchanged=plan['description']['no_op'],
            packages=[dict(name=p['role'], release=p['release_id'], reference=wishes.digest(p['reference']))
                      for p in candidate['packages']],
            active={name:wishes.digest(ref) for name,ref in candidate['active'].items()},
            requests_before=old['requests']['id'] if old else None,
            requests_after=candidate['requests']['id'],
            sources={name:view['snapshot'] for name,view in sources.items()}), indent=2))
        if input('Apply this Ports plan? [y/N] ').strip().lower() != 'y':
            print('Cancelled.'); return 0
    result = profiles.apply(root, plan, sources, adapters, **options, action=args.action)
    print(json.dumps(result, indent=2))
    return 0
