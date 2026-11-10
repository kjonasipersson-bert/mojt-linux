# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Thin experimental interface over the existing build and packaging tools."""
import importlib.util
import os
from pathlib import Path
import sys

# Files are selected by manager-owned constants, never user paths or PATH.
HELPERS = {'env':'mojt-build-env.py','kernel':'mojt-kernel-build.py','package':'mojt-artifact-pack.py','bootstrap':'mojt_bootstrap.py'}


def helper(name):
    path = Path(__file__).resolve().with_name(HELPERS[name])
    if path.is_symlink() or not path.is_file():raise ValueError('missing regular bundled build helper: '+path.name)
    spec = importlib.util.spec_from_file_location('mojt_mbt_'+name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def usage():
    print('usage: mbt {env,build,package,bootstrap} ...\n'
          '  env             create a private pinned image/kernel tool environment\n'
          '  build kernel    compile a separate Kernel and matching modules\n'
          '  package         package kernel/base/system inputs, or verify an archive\n'
          '  bootstrap       create a NEW UEFI native-v2 image (VM or ThinkPad profile)\n'
          'Use mbt COMMAND --help for options; build accepts mbt build kernel --help.\n'
          'Experimental syntax. Builds/packages do not install or select next boot.\n'
          'Writing an image to a physical disk is a separate explicit operation.')


def dispatch(args):
    if not args or args in (['--help'],['-h']):usage();return 0
    command,rest = args[0],args[1:]
    if command == 'env':name,prog = 'env','mbt env'
    elif command == 'package':name,prog = 'package','mbt package'
    elif command == 'bootstrap':name,prog = 'bootstrap','mbt bootstrap'
    elif command == 'build':
        if not rest or rest in (['--help'],['-h']):
            print('usage: mbt build kernel ...\nUse --dry-run to preview; --resume reuses a verified incomplete workspace.')
            return 0
        if rest[0] != 'kernel':raise ValueError('only build kernel is supported')
        rest = rest[1:];name,prog = 'kernel','mbt build kernel'
        if os.geteuid() == 0 and not any(arg in rest for arg in ('--help','-h','--dry-run')):
            raise ValueError('compile as an ordinary user in a private workspace; installation is a separate MPM operation')
    else:raise ValueError('unknown command; use mbt --help')
    result = helper(name).main(rest,prog=prog)
    return 0 if result is None else result


def main(argv=None):
    try:return dispatch(list(sys.argv[1:] if argv is None else argv))
    except (OSError,ValueError,KeyError,TypeError,EOFError) as error:
        print('mbt: '+str(error),file=sys.stderr)
        return 1
