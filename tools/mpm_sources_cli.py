# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Installed source/snapshot management and exact native cache acquisition."""
import argparse
import json
from pathlib import Path
import sys

import mpm_sources as sources


def parser(area):
    p = argparse.ArgumentParser(prog='mpm ' + area, description=__doc__)
    actions = p.add_subparsers(dest='action', required=True)
    for action in (('add', 'update', 'list', 'show') if area == 'source' else ('fetch',)):
        sub = actions.add_parser(action)
        sub.add_argument('--root', type=Path)
        sub.add_argument('--json', action='store_true')
        if action not in ('list', 'show'):
            sub.add_argument('--dry-run', action='store_true')
            sub.add_argument('-y', '--yes', action='store_true')
        if action in ('add', 'update', 'show'):
            sub.add_argument('name')
        if action == 'add':
            sub.add_argument('--from-file', type=Path, required=True)
            sub.add_argument('--policy-file', type=Path, required=True)
            sub.add_argument('--replace', action='store_true')
        if action == 'update':
            sub.add_argument('--snapshot-file', default='snapshot.json', help='relative to registered source root')
            sub.add_argument('--catalog-file', default='catalog.json')
            sub.add_argument('--acquisition-file', default='acquisition-map.json')
        if action in ('show', 'fetch'):
            sub.add_argument('--snapshot', help='retained exact snapshot under the currently authorized source')
        if action == 'fetch':
            sub.add_argument('artifact', help='exact native sha256 artifact identity')
            sub.add_argument('--source', required=True)
            sub.add_argument('--sources-root', type=Path)
            sub.add_argument('--kind', choices=sources.cache.artifact.KINDS, required=True)
            sub.add_argument('--archive-sha256', required=True, help='one approved compressed encoding')
    return p


def protected_json(path):
    path = Path(path).absolute()
    return sources.cache.artifact.parse_json(sources.cache.read_file(path.parent, path.name))


def confirm(args, plan):
    if args.dry_run:
        print(json.dumps(dict(dry_run=True, changed=False, plan=plan), indent=2))
        return False
    if not args.yes:
        print(json.dumps(plan, indent=2), file=sys.stderr)
        print('Apply this metadata/cache plan? [y/N] ', end='', file=sys.stderr, flush=True)
        if input().strip().lower() not in ('y', 'yes'):
            raise ValueError('source/cache operation cancelled')
    return True


def main(area, argv, *, root=None, runtime=None):
    args = parser(area).parse_args(argv)
    if root is not None and args.root is not None:
        raise ValueError('specify --root only once')
    if area == 'source':
        root = args.root or root or (runtime.sources if runtime else Path('/var/lib/mojt/sources'))
        if args.action == 'list':
            rows = sources.list_sources(root)
            print(json.dumps(rows, indent=2) if args.json else '\n'.join(
                row['registration']['description']['name'] + ' ' +
                (row['snapshot']['id'] if row['snapshot'] else 'refresh required') for row in rows))
            return 0
        if args.action == 'show':
            result = sources.inspect(root, args.name, args.snapshot)
        elif args.action == 'add':
            kwargs = dict(source=protected_json(args.from_file), policy_file=args.policy_file, replace=args.replace)
            plan = sources.prepare_add(root, args.name, **kwargs)
            if not confirm(args, plan):
                return 0
            result = sources.add(root, args.name, plan, **kwargs)
        else:
            files = dict(snapshot_file=args.snapshot_file, catalog_file=args.catalog_file,
                         acquisition_file=args.acquisition_file)
            plan = sources.prepare_update(root, args.name, **files)
            if not confirm(args, plan):
                return 0
            result = sources.update(root, args.name, plan, **files)
    else:
        root = args.root or root or (runtime.cache if runtime else Path('/var/lib/mojt/cache'))
        source_root = args.sources_root or (runtime.sources if runtime else Path('/var/lib/mojt/sources'))
        selection = dict(kind=args.kind, archive_sha256=args.archive_sha256, snapshot=args.snapshot)
        plan = sources.prepare_fetch(source_root, root, args.source, args.artifact, **selection)
        if not confirm(args, plan):
            return 0
        result = sources.fetch(source_root, root, args.source, args.artifact, plan, **selection)
    print(json.dumps(result, indent=2))
    return 0
