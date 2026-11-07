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


class ProviderAdapters(dict):
    """Load only the selected System's helper, and never import into a host store for an offline target."""
    def __init__(self, runtime):
        super().__init__();self.runtime = runtime

    def __missing__(self, name):
        base.require(name == 'nix', 'unsupported System provider: ' + name)
        base.require(self.runtime is not None, 'System provider operations require the running installation; offline provider import/verification is unavailable')
        try:from mpm_nix_binary import NixBinaryAdapter
        except ImportError as error:raise ValueError('selected System has no Nix binary adapter') from error
        binary = self.runtime.system_bin / 'nix-store'
        base.require(binary.is_file() and os.access(binary, os.X_OK), 'selected System has no retained nix-store helper')
        adapter = NixBinaryAdapter(binary)
        self[name] = adapter
        return adapter


def main(argv, *, runtime=None):
    try:
        parser = argparse.ArgumentParser(prog='mpm system')
        sub = parser.add_subparsers(dest='action', required=True)
        install = sub.add_parser('install');install.add_argument('--from-file', type=Path, required=True)
        install.add_argument('--expected-id', required=True)
        install.add_argument('--dependency-file', type=Path, action='append', default=[])
        install.add_argument('--dry-run', action='store_true');install.add_argument('-y', '--yes', action='store_true')
        status = sub.add_parser('status');status.add_argument('--verify', action='store_true')
        for command in (install, status):
            command.add_argument('--disk-root', type=Path);command.add_argument('--json', action='store_true')
        args = parser.parse_args(argv)
        base.require(args.disk_root is not None or runtime is not None, 'specify --disk-root for a checkout/offline target')
        root = args.disk_root or runtime.disk
        adapters = ProviderAdapters(runtime if args.disk_root is None else None)
        if runtime is not None and args.disk_root is None:base.require(os.path.ismount(root), 'running installation disk is unavailable')
        if args.action == 'install':
            result = system.install(root, args.from_file, args.expected_id, dependency_files=args.dependency_file, dry_run=args.dry_run, yes=args.yes, adapters=adapters)
        else:
            running = base.read(runtime.running) if runtime is not None and args.disk_root is None and runtime.running.is_file() else None
            result = system.status(root, verify=args.verify, running_record=running, adapters=adapters)
        if args.json or args.action == 'install':print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print('System on:', result['target'])
            for title, key in (('Running', 'running'), ('Next boot', 'selected')):
                row = result[key]
                print(title + ':', (row['label'] + ' / ' + row['manifest'] + ' / artifact ' + (row['artifact'] or 'unknown')) if row['state'] == 'known' else 'unknown (' + row['reason'] + ')')
            print('Installed:')
            for row in result['installed']:print(' ', row['label'], '/', row['version']['release_id'], '/', row['artifact'])
            if not result['installed']:print('  none')
            if result['retained']:print('Retained, not installed:', ', '.join(r['artifact'] for r in result['retained']))
            if result['incomplete']:print('Incomplete:', ', '.join(result['incomplete']))
            print(result['compatibility'])
        return 0
    except (OSError, ValueError, KeyError, TypeError, RecursionError, EOFError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print('mpm system: ' + str(error), file=sys.stderr)
        return 1
