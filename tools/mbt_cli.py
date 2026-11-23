# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Thin experimental interface over the existing build and packaging tools."""
import importlib.util
from pathlib import Path
import sys

# Files are selected by manager-owned constants, never user paths or PATH.
HELPERS = {'env':'mojt-build-env.py','kernel':'mojt-kernel-build.py','base':'mojt-base-build.py',
           'package':'mojt-artifact-pack.py','bootstrap':'mojt_bootstrap.py'}


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
          '  build base      build and package a complete source Base (plain host GCC)\n'
          '  package         package kernel/base/system inputs, or verify an archive\n'
          '  bootstrap       create a native-v2 image or install to prepared mounted partitions\n'
          'Use mbt COMMAND --help for options; build accepts kernel or base.\n'
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
            print('usage: mbt build {kernel,base} ...\nUse --dry-run to preview; kernel --resume reuses a verified incomplete workspace.')
            return 0
        if rest[0] not in ('kernel','base'):raise ValueError('build supports kernel or base')
        name,rest = rest[0],rest[1:];prog = 'mbt build '+name
    else:raise ValueError('unknown command; use mbt --help')
    from mbt_runtime import enter
    prepared=enter(args)
    if prepared is not None:return prepared
    result = helper(name).main(rest,prog=prog)
    return 0 if result is None else result


def main(argv=None):
    try:return dispatch(list(sys.argv[1:] if argv is None else argv))
    except (OSError,ValueError,KeyError,TypeError,EOFError) as error:
        print('mbt: '+str(error),file=sys.stderr)
        return 1
