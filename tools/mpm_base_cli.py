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


def _main(argv,*,runtime=None):
    p=argparse.ArgumentParser(prog='mpm base')
    sub=p.add_subparsers(dest='action',required=True)
    install=sub.add_parser('install');origin=install.add_mutually_exclusive_group(required=True)
    origin.add_argument('--from-file',type=Path);origin.add_argument('--source')
    install.add_argument('--expected-id',required=True)
    for flag in ('archive-sha256','snapshot'):install.add_argument('--'+flag)
    for flag in ('sources-root','cache-root'):install.add_argument('--'+flag,type=Path)
    install.add_argument('--dry-run',action='store_true');install.add_argument('-y','--yes',action='store_true')
    status=sub.add_parser('status');status.add_argument('--verify',action='store_true')
    for command in (install,status):
        command.add_argument('--disk-root',type=Path);command.add_argument('--json',action='store_true')
    args=p.parse_args(argv)
    base.require(args.disk_root is not None or runtime is not None,'specify --disk-root for a checkout/offline target')
    root=args.disk_root or runtime.disk
    if runtime is not None and args.disk_root is None:
        base.require(os.path.ismount(root),'running installation disk is unavailable')
    if args.action=='status':
        from mpm_base_status import status as inspect
        running=None
        if runtime is not None and args.disk_root is None and runtime.running.is_file():running=base.read(runtime.running)
        result=inspect(root,verify=args.verify,running_record=running)
    else:
        base.io.identifier(args.expected_id)
        source=args.source is not None
        if source:
            base.require(args.archive_sha256 is not None,'--source requires --archive-sha256')
            from mpm_base_source import install as acquire
            result=acquire(root,args.sources_root or (runtime.sources if runtime else Path('/var/lib/mojt/sources')),
                args.cache_root or (runtime.cache if runtime else Path('/var/lib/mojt/cache')),
                args.source,args.expected_id,archive_sha256=args.archive_sha256,snapshot=args.snapshot,
                dry_run=args.dry_run,yes=args.yes,tar=str(runtime.helpers/'tar') if runtime else 'tar')
        else:
            base.require(not any(v is not None for v in (args.archive_sha256,args.snapshot,args.sources_root,args.cache_root)),'source/cache flags require --source')
            result=base.install(root,args.from_file,args.expected_id,dry_run=args.dry_run,yes=args.yes,
                                tar=str(runtime.helpers/'tar') if runtime else 'tar')
    if args.json or args.action=='install':print(json.dumps(result,indent=2,sort_keys=True))
    else:
        print('Base on:',result['target'])
        for label,key in (('Running','running'),('Next boot','selected')):
            row=result[key]
            print(label+':',f"{row['release']} / {row['artifact']} / deployment {row['deployment']}" if row['state']=='known' else 'unknown ('+row['reason']+')')
            if row.get('retention')=='not-in-this-store':print('  Retention: not installed in this Base store')
        print('Installed:')
        for row in result['installed']:
            print(' ',row['version']['release_id'],'/',row['artifact'],
                  ', '.join(label for label in ('running','next_boot') if row[label]) or 'not selected')
        if not result['installed']:print('  none')
        if result['retained']:print('Retained, not installed:',', '.join(r['artifact'] for r in result['retained']))
        if result['incomplete']:print('Incomplete:',', '.join(result['incomplete']))
        print('Integrity:', 'verified now' if args.verify else 'verified at installation; --verify rechecks content')
        print(result['compatibility'])
    return 0


def main(argv,*,runtime=None):
    try:return _main(argv,runtime=runtime)
    except (OSError,ValueError,KeyError,TypeError,EOFError,subprocess.CalledProcessError,tarfile.TarError) as error:
        print('mpm base: '+str(error),file=sys.stderr)
        return 1
