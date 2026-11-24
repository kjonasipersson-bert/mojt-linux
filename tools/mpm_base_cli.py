# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Exact Base content installation and honest installed/selected/running status."""
import argparse
import json
import os
from pathlib import Path
import sys
import subprocess
import tarfile

import mpm_base as base
import mpm_ui as ui


def prepare_installed(root, identifier, *, runtime, bounds=None, verify=False, yes=False):
    """Authorized missing defaults, then the existing native-v2 constructor."""
    import mpm_boot_update as update
    import mpm_defaults as defaults
    from mpm_base_boot import defaults_check
    from mpm_system_cli import ProviderAdapters
    with base.io.preparation(verify=verify):
        tree=base.realization_path(root,identifier)/'tree/rootfs'
        missing=defaults_check(root,tree)['missing']
        if missing:
            # This first normal-flow subset adds ordinary files in existing
            # directories. Account files, symlinks and directory migrations
            # still need their own explicit supported preparation.
            for name in missing:
                defaults.relative(name)
                path=tree/'usr/etc'/name
                base.require(path.is_file() and not path.is_symlink(),
                             'missing Base default needs explicit preparation: '+name)
            print('Missing Base defaults to add: '+', '.join(missing),file=sys.stderr,flush=True)
            plan=defaults.prepare(root,identifier,missing)
            if not yes:base.require(input('Add these missing defaults, preserving existing files? [y/N] ').strip().lower() in ('y','yes'),'default preparation cancelled')
            with ui.phase('Add missing Base defaults'):
                defaults.initialize(root,plan,yes=True)
        with ui.phase('Prepare installed Base for boot'):
            return update.stage(root,'base',identifier,bounds=bounds,adapters=ProviderAdapters(runtime),
                runtime=runtime,tar=str(runtime.helpers/'tar'),yes=True,verify=verify)


def _main(argv,*,runtime=None):
    p=argparse.ArgumentParser(prog='mpm base')
    sub=p.add_subparsers(dest='action',required=True)
    install=sub.add_parser('install');origin=install.add_mutually_exclusive_group(required=True)
    origin.add_argument('--from-file',type=Path);origin.add_argument('--source')
    upgrade=sub.add_parser('upgrade');upgrade_origin=upgrade.add_mutually_exclusive_group(required=True)
    upgrade_origin.add_argument('--from-file',type=Path);upgrade_origin.add_argument('--source')
    upgrade.add_argument('--expected-selected')
    install.add_argument('--content-only',action='store_true',help='retain content without defaults or boot preparation')
    for command in (install,upgrade):
        command.add_argument('--expected-id',help='optional exact native artifact ID')
        command.add_argument('--release',help='source selector, e.g. mojt or mojt@=0.2.1-r1 (default: mojt)')
        command.add_argument('--base-context',type=Path,help='explicit Kernel bounds; default is the exact selected Kernel only')
        command.add_argument('--verify',action='store_true',help='explicitly audit retained content during preparation')
        command.add_argument('--dry-run',action='store_true');command.add_argument('-y','--yes',action='store_true')
        for flag in ('archive-sha256','snapshot'):command.add_argument('--'+flag)
        for flag in ('sources-root','cache-root'):command.add_argument('--'+flag,type=Path)
    stage=sub.add_parser('stage');stage.add_argument('--artifact',required=True)
    stage.add_argument('--base-context',required=True,type=Path)
    stage.add_argument('--baseline');stage.add_argument('--dry-run',action='store_true')
    stage.add_argument('-y','--yes',action='store_true')
    select=sub.add_parser('select');select.add_argument('--deployment',required=True)
    rollback=sub.add_parser('rollback')
    for command in (select,rollback):
        command.add_argument('--expected-selected',required=True);command.add_argument('--baseline')
        command.add_argument('--dry-run',action='store_true');command.add_argument('-y','--yes',action='store_true')
    status=sub.add_parser('status');status.add_argument('--verify',action='store_true')
    for command in (install,upgrade,stage,select,rollback,status):
        command.add_argument('--disk-root',type=Path);command.add_argument('--json',action='store_true')
    args=p.parse_args(argv)
    base.require(args.disk_root is not None or runtime is not None,'specify --disk-root for a checkout/offline target')
    root=args.disk_root or runtime.disk
    if runtime is not None and args.disk_root is None:
        base.require(os.path.ismount(root),'running installation disk is unavailable')
    if args.action=='status':
        from mpm_base_status import status as inspect
        running=None
        if runtime is not None and args.disk_root is None:
            from mpm_boot_status import read_running
            running=read_running(runtime)
        result=inspect(root,verify=args.verify,running_record=running)
    elif args.action in ('stage','select','rollback'):
        baseline=args.baseline
        if baseline is None and runtime is not None and args.disk_root is None:
            from mpm_cli import boot_options
            options=boot_options(['stage'],runtime)
            baseline=options[options.index('--baseline')+1] if '--baseline' in options else None
        if args.action=='stage':
            from mpm_base_boot import stage as construct
            result=construct(root,args.artifact,base.read(args.base_context),baseline=baseline,
                dry_run=args.dry_run,yes=args.yes,tar=str(runtime.helpers/'tar') if runtime else 'tar')
        else:
            from mpm_base_boot import select as choose
            result=choose(root,getattr(args,'deployment',None),expected_selected=args.expected_selected,
                baseline=baseline,dry_run=args.dry_run,yes=args.yes,rollback=args.action=='rollback')
    else:
        import mpm_boot_selection as selection
        live=runtime if runtime is not None and args.disk_root is None and selection.present(root) else None
        preparing=live is not None and not getattr(args,'content_only',False)
        choosing=args.action=='upgrade'
        base.require(not choosing or preparing,'Base upgrade requires a running native-v2 installation; use install --content-only for an offline target')
        bounds=base.read(args.base_context) if args.base_context is not None else None
        selected=selection.selected(root)[0]['description']['selected'] if preparing else None
        if choosing:base.require(args.expected_selected is None or args.expected_selected==selected,'selected deployment changed; repeat preview')
        if preparing:
            print('This command adds missing regular Base defaults and prepares boot; existing /etc files are preserved.',file=sys.stderr)
            print('Next boot '+('is selected after approval' if choosing else 'stays unchanged')+'; no automatic reboot.',file=sys.stderr,flush=True)
        source=getattr(args,'source',None) is not None
        with ui.phase('Install Base content'):
            if source:
                from mpm_base_source import install as acquire,resolve
                source_root=args.sources_root or (runtime.sources if runtime else Path('/var/lib/mojt/sources'))
                identifier,checksum,snapshot=resolve(source_root,args.source,selector=args.release,
                    identifier=args.expected_id,archive_sha256=args.archive_sha256,snapshot=args.snapshot)
                result=acquire(root,source_root,
                    args.cache_root or (runtime.cache if runtime else Path('/var/lib/mojt/cache')),
                    args.source,identifier,archive_sha256=checksum,snapshot=snapshot,
                    dry_run=args.dry_run,yes=args.yes,tar=str(runtime.helpers/'tar') if runtime else 'tar')
            else:
                base.require(not any(getattr(args,name,None) is not None for name in ('release','archive_sha256','snapshot','sources_root','cache_root')),'source/cache flags require --source')
                result=base.install(root,args.from_file,args.expected_id,dry_run=args.dry_run,yes=args.yes,
                                    tar=str(runtime.helpers/'tar') if runtime else 'tar')
        if not args.dry_run and not result.get('cancelled') and preparing:
            identifier=result['plan']['description']['artifact']
            selecting=False
            try:
                base.require(selection.selected(root)[0]['description']['selected']==selected,'selected deployment changed during installation; retry preparation')
                prepared=prepare_installed(root,identifier,runtime=live,bounds=bounds,verify=args.verify,yes=args.yes)
                base.require(prepared['selected']==selected,'selected deployment changed during preparation; repeat preview')
                result=dict(result,content_changed=result['changed'],changed=result['changed'] or prepared['changed'],
                    prepared=True,preparation=prepared,selection_changed=False,running_changed=False)
                if choosing:
                    selecting=True
                    chosen=selection.select(root,prepared['deployment'],area='base',expected_selected=selected,
                        yes=args.yes,verify=args.verify)
                    result.update(selection_changed=chosen['changed'],selection=chosen,changed=result['changed'] or chosen['changed'])
            except (OSError,ValueError,KeyError,TypeError,subprocess.CalledProcessError,tarfile.TarError) as error:
                if selecting and getattr(error,'committed',False):
                    result.update(selection_changed=None,publication_uncertain=True)
                if args.json:print(json.dumps(dict(result,prepared=result.get('prepared',False),error=str(error)),indent=2,sort_keys=True))
                raise ValueError('Base content is installed; added missing defaults are retained. '
                    'Preparation/selection did not complete: '+str(error)+
                    ('; boot publication may have completed, inspect mpm base status' if result.get('publication_uncertain') else '')) from error
        else:result=dict(result,prepared=False,selection_changed=False,
            preparation_skipped='preview/cancelled' if args.dry_run or result.get('cancelled') else 'content-only requested' if getattr(args,'content_only',False) else 'no live native-v2 boot context')
    if args.json or args.action in ('stage','select','rollback') or args.action=='install' and live is None:
        print(json.dumps(result,indent=2,sort_keys=True))
    elif args.action in ('install','upgrade'):
        if result.get('cancelled'):print('Cancelled; next boot unchanged.')
        elif args.dry_run:print('Preview only; no installation, defaults or boot selection changed. Boot compatibility is checked during preparation.')
        elif result.get('prepared'):
            print('Base installed and prepared for boot.')
            print(('Next boot selected; reboot when ready.' if result['selection_changed'] else 'Next boot already selects this Base.')
                  if args.action=='upgrade' else 'Next boot unchanged; use mpm base activate to choose the prepared Base.')
        else:print('Base content installed. Boot preparation skipped: '+result['preparation_skipped']+'.')
    else:
        result['staged_deployments']=ui.prepared_rows(root,'base',result['installed'])
        ui.status('base',result)
    return 0


def main(argv,*,runtime=None):
    try:
        with base.io.preparation():return _main(argv,runtime=runtime)
    except (OSError,ValueError,KeyError,TypeError,RecursionError,EOFError,subprocess.CalledProcessError,tarfile.TarError) as error:
        print('mpm base: '+str(error),file=sys.stderr)
        return 1
