# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Native System content commands; selection and service activation are separate."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import mpm_base as base
import mpm_system as system
import mpm_ui as ui


class ProviderAdapters(dict):
    """Load only the selected System's helper, and never import into a host store for an offline target."""
    def __init__(self, runtime):
        super().__init__();self.runtime = runtime

    def __missing__(self, name):
        base.require(name == 'nix', 'unsupported System provider: ' + name)
        base.require(self.runtime is not None, 'System provider operations require the running installation; offline provider import/verification is unavailable')
        try:from mpm_nix_boot import NixBootAdapter
        except ImportError as error:raise ValueError('selected System has no Nix binary adapter') from error
        binary = self.runtime.system_bin / 'nix-store'
        base.require(binary.is_file() and os.access(binary, os.X_OK), 'selected System has no retained nix-store helper')
        adapter = NixBootAdapter(binary)
        self[name] = adapter
        return adapter


def main(argv, *, runtime=None):
    try:
        parser = argparse.ArgumentParser(prog='mpm system')
        sub = parser.add_subparsers(dest='action', required=True)
        install = sub.add_parser('install');origin = install.add_mutually_exclusive_group(required=True)
        origin.add_argument('--from-file', type=Path);origin.add_argument('--source')
        install.add_argument('--expected-id', required=True)
        for name in ('archive-sha256', 'snapshot'):install.add_argument('--' + name)
        for name in ('sources-root', 'cache-root'):install.add_argument('--' + name, type=Path)
        install.add_argument('--dependency-file', type=Path, action='append', default=[])
        install.add_argument('--verify',action='store_true',help='explicitly audit archive payloads, retained objects and provider closures')
        install.add_argument('--content-only',action='store_true',help='install content without preparing a boot deployment')
        install.add_argument('--dry-run', action='store_true');install.add_argument('-y', '--yes', action='store_true')
        status = sub.add_parser('status');status.add_argument('--verify', action='store_true')
        select = sub.add_parser('select');select.add_argument('--deployment',required=True)
        rollback = sub.add_parser('rollback')
        for command in (select,rollback):
            command.add_argument('--verify',action='store_true');command.add_argument('--expected-selected',required=True);command.add_argument('--dry-run',action='store_true')
            command.add_argument('-y','--yes',action='store_true')
        for command in (install, status, select, rollback):
            command.add_argument('--disk-root', type=Path);command.add_argument('--json', action='store_true')
        args = parser.parse_args(argv)
        base.require(args.disk_root is not None or runtime is not None, 'specify --disk-root for a checkout/offline target')
        root = args.disk_root or runtime.disk
        adapters = ProviderAdapters(runtime if args.disk_root is None else None)
        if runtime is not None and args.disk_root is None:base.require(os.path.ismount(root), 'running installation disk is unavailable')
        if args.action in ('select','rollback'):
            from mpm_boot_selection import select as choose
            result = choose(root,getattr(args,'deployment',None),expected_selected=args.expected_selected,
                            rollback=args.action=='rollback',dry_run=args.dry_run,yes=args.yes,verify=args.verify)
        elif args.action == 'install':
            from mpm_boot_selection import present
            live=runtime is not None and args.disk_root is None and present(root)
            if live and not args.content_only:
                print('Installation includes boot preparation. Next boot stays unchanged; no automatic reboot.',file=sys.stderr,flush=True)
            with ui.phase('Install System content'):
                if args.source is not None:
                    base.require(args.archive_sha256 is not None and not args.dependency_file, '--source requires --archive-sha256 and obtains components from the same snapshot')
                    from mpm_system_source import install as acquire
                    result = acquire(root, args.sources_root or (runtime.sources if runtime else Path('/var/lib/mojt/sources')),
                        args.cache_root or (runtime.cache if runtime else Path('/var/lib/mojt/cache')), args.source, args.expected_id,
                        archive_sha256=args.archive_sha256, snapshot=args.snapshot, dry_run=args.dry_run, yes=args.yes, adapters=adapters, verify=args.verify)
                else:
                    base.require(not any(v is not None for v in (args.archive_sha256, args.snapshot, args.sources_root, args.cache_root)), 'source/cache flags require --source')
                    result = system.install(root, args.from_file, args.expected_id, dependency_files=args.dependency_file, dry_run=args.dry_run, yes=args.yes, adapters=adapters, verify=args.verify)
            if not args.dry_run and not result.get('cancelled'):
                if live and not args.content_only:
                    from mpm_boot_update import stage
                    try:
                        with ui.phase('Prepare installed System for boot'):
                            prepared=stage(root,'system',args.expected_id,adapters=adapters,runtime=runtime,
                                tar=str(runtime.helpers/'tar'),yes=True,verify=args.verify)
                        result=dict(result,content_changed=result['changed'],changed=result['changed'] or prepared['changed'],
                                    preparation=prepared,prepared=True,selection_changed=False,running_changed=False)
                    except (OSError,ValueError,KeyError,TypeError,subprocess.CalledProcessError,tarfile.TarError) as error:
                        if args.json:print(json.dumps(dict(result,prepared=False,preparation_error=str(error),selection_changed=False),indent=2,sort_keys=True))
                        raise ValueError('Content is installed; next boot unchanged. Boot preparation failed: '+str(error)) from error
                else:result=dict(result,prepared=False,preparation_skipped='content-only requested' if args.content_only else 'no live native-v2 boot context')
        else:
            from mpm_boot_status import read_running
            running = read_running(runtime) if runtime is not None and args.disk_root is None else None
            result = system.status(root, verify=args.verify, running_record=running, adapters=adapters)
        if args.json or args.action in ('select','rollback'):print(json.dumps(result, indent=2, sort_keys=True))
        elif args.action=='install':
            if result.get('cancelled'):print('Cancelled; next boot unchanged.')
            elif args.dry_run:print('Preview only; no installation or boot preparation performed.')
            elif result.get('prepared'):
                print('System content installed and prepared for boot.' if result.get('content_changed') else 'Installed System is prepared for boot.')
                print('Next boot is unchanged; use mpm system activate to choose it.')
            else:print(('System content installed. ' if result.get('changed') else 'System content already installed. ')+'Boot preparation skipped: '+result['preparation_skipped']+'.')
        else:ui.status('system',result)
        return 0
    except (OSError, ValueError, KeyError, TypeError, RecursionError, EOFError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print('mpm system: ' + str(error), file=sys.stderr)
        return 1
