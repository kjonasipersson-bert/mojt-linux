#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only readiness probe, not acceptance of a new System or hardware family."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
import mojt_hardware as hardware


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--modules-dir', type=Path, help='default: running Kernel module tree')
    parser.add_argument('--firmware-root', type=Path, help='optional extracted PC firmware/license input')
    args = parser.parse_args(argv)
    modules = args.modules_dir or Path('/lib/modules') / os.uname().release
    modules = modules.resolve(strict=True)
    spec = importlib.util.spec_from_file_location('pc_probe_vm', REPO / 'tools/mojt-vm-build.py')
    vm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vm)
    names = hardware.early_modules(hardware.PC_PROFILE)
    print('Checking planned early drivers for ' + modules.name + '...', flush=True)
    paths = vm.module_paths(modules.name, modules, names=names)
    print(f'PASS: {len(names)} early driver requests resolve ({len(paths)} module files; built-ins need no copy).')
    print('Checking udev device enumeration (dry run)...', flush=True)
    result = subprocess.run(['udevadm', 'trigger', '--dry-run', '--action=add', '--type=devices'],
                            check=True, capture_output=True, text=True)
    print(f'PASS: udev dry run enumerated {len(result.stdout.splitlines())} device paths.')
    if args.firmware_root:
        hardware.firmware_inputs(args.firmware_root, hardware.PC_PROFILE)
        print('PASS: all PC firmware families, regulatory files and required licenses are present.')
    else:
        print('NOT TESTED: new firmware inputs (no --firmware-root supplied).')
    print('Readiness only: no modules loaded, no events triggered, no install or boot choice changed.')
    print('NOT TESTED: booting a new System or firmware loading on physical devices.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr.strip(), file=sys.stderr)
        raise SystemExit(1)
