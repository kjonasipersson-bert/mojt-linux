#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Opt-in real Nix acceptance for the fresh Ports frontend.

Requires an accepted bundle made from already-local hello outputs. Existing Nix
objects may be reused; this does not prove a new network download. Retains the
new registry, profiles and roots. No System changes or physical collection.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--sources', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        require(os.geteuid() != 0, 'run as an ordinary user, without sudo')
        root = args.root.absolute()
        require(not os.path.lexists(root), 'choose a new registry path; existing labs are never reset')
        bundle = json.loads(args.sources.read_text(encoding='utf-8'))
        mpm = [sys.executable, '-I', '-B', str(REPO / 'tools/mpm'), '--root', str(root), 'ports']

        def call(*arguments):
            return json.loads(subprocess.check_output([*mpm, *arguments], text=True))

        preview = call('install', 'hello@2.12', '--sources', str(args.sources),
                       '--expected-sources', bundle['id'], '--dry-run')
        require(preview['dry_run'] is True and not os.path.lexists(root), 'preview wrote installation state')
        print('PASS: preview created no registry or profile', flush=True)

        print('Importing and verifying through the real Nix adapter...', flush=True)
        result = call('install', 'hello@2.12', '--sources', str(args.sources),
                      '--expected-sources', bundle['id'], '-y')
        require(result['changed'] is True, 'initial installation was not published')
        state = json.loads((root / 'current/state.json').read_text())['description']
        require(len(state['packages']) == 1, 'expected one logical package')
        package = state['packages'][0]
        require(package['role'] == 'hello' and state['active']['hello'] == package['reference'], 'wrong active package')
        require(package['reference']['provider'] == 'nix', 'acceptance requires the real Nix provider')
        require(package['release_id'].startswith('2.12.'), 'unexpected series result')
        fixed = [name for name in state['aliases'] if name.startswith('hello-' + package['release_id'] + '-')]
        require(len(fixed) == 1, 'missing or ambiguous exact alias')
        for name in ('hello', 'hello-2.12', fixed[0]):
            output = subprocess.check_output([str(root / 'current/bin' / name)], text=True,
                                              env=dict(os.environ, LC_ALL='C'))
            require(output.strip() == 'Hello, world!', 'alias executed unexpected content: ' + name)
        print('PASS: default, series and exact aliases execute', flush=True)

        output = package['reference']['identity']['output']
        gcroot = root / 'retained/nix' / Path(output).name
        require(gcroot.is_symlink() and os.readlink(gcroot) == output, 'wrong retained root')
        registered = subprocess.check_output(['nix-store', '--query', '--roots', output], text=True)
        require(str(gcroot) in {line.split(' -> ', 1)[0] for line in registered.splitlines()}, 'Nix GC root is not registered')
        print('PASS: exact output retained with a registered Nix GC root', flush=True)

        before = os.readlink(root / 'current')
        before_state = (root / 'current/state.json').read_bytes()
        history = call('history', '--json')
        require(len(history) == 1, 'expected one transaction')
        repeated = call('install', 'hello@2.12', '-y')
        require(repeated['changed'] is False and os.readlink(root / 'current') == before, 'repeat changed selection')
        require((root / 'current/state.json').read_bytes() == before_state, 'repeat changed state')
        require(call('history', '--json') == history, 'repeat changed history')
        print('PASS: repeat install preserved profile, state and history', flush=True)
        print('PASS: real Nix adapter and fresh Ports frontend acceptance', flush=True)
        print('Lab retained: ' + str(root.parent), flush=True)
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print('Ports acceptance: ' + str(error), file=sys.stderr)
        print('Lab retained; inspect the failed phase before retrying.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
