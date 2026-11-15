#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Read active Ports metadata at invocation; delegate to the retained man-db."""
import os
from pathlib import Path
import sys

if __name__=='__main__':sys.path.insert(0,str(Path(__file__).resolve().parent))

def require(ok,message):
    if not ok:raise ValueError(message)


def manual_paths(root):
    import mpm_ports_profile as profiles
    from mpm_nix_binary import NixBinaryAdapter
    selected=profiles.current(root)
    if selected is None:return [],{}
    d=selected['record']['description'];paths=[];aliases={}
    objects={profiles.planning.key(row['reference']):row['reference'] for row in d['objects']}
    parser=NixBinaryAdapter('/nonexecuted/nix-store')
    for role,ref in sorted(d['active'].items()):
        package=next(p for p in d['packages'] if p['reference']==ref)
        main=package.get('manual_program')
        if main in package['commands'] and role not in package['commands']:aliases[role]=main
        for reference in [ref,*package.get('manuals',[])]:
            require(profiles.planning.key(reference) in objects,'manual reference is not retained by the selected profile')
            if reference.get('provider')!='nix':continue
            i=parser.identity(reference);roots=[i['output'],*[r['path'] for r in i['closure'] if r['path']!=i['output']]]
            allowed={r['path'] for r in i['closure']}
            for name in roots:
                point=Path(name)/'share/man'
                if not point.is_dir():continue
                resolved=point.resolve();require(any(str(resolved)==p or str(resolved).startswith(p+'/') for p in allowed),'manual directory escapes its exact closure')
                if str(point) not in paths:paths.append(str(point))
    return paths,aliases


def environment(root, inherited):
    paths,aliases=manual_paths(root)
    current=inherited.get('MANPATH','')
    # Keep the empty component: man-db uses it for its normal default search.
    return dict(inherited,MANPATH=':'.join(dict.fromkeys([*paths,*current.split(':')]))),aliases


def wrapper(program):
    path=Path(program)
    require(path.is_absolute() and path.parts[1:3]==('nix','store') and path.parent.name=='bin'
                     and path.name in ('man','manpath'),'expected a retained man-db program')
    import shlex
    return '#!/bin/sh\nexec /run/mojt-system/bin/python3 -I -B /run/mojt-system/tools/mpm_man.py '+shlex.quote(str(path))+' "$@"\n'


def main(argv=None, *, root=Path('/var/lib/mojt/ports'), execute=os.execve):
    args=list(sys.argv[1:] if argv is None else argv)
    require(args,'missing retained man-db program')
    program=args.pop(0);wrapper(program)  # Validate the immutable wrapper's operand.
    env,aliases=environment(root,os.environ)
    # Package-role convenience: Neovim's upstream page is nvim(1). Leave complex
    # man command lines untouched; man-db owns all option/section parsing.
    if Path(program).name=='man':
        indexes=[n for n,a in enumerate(args) if not a.startswith('-')]
        if all(a in ('-w','--where','--path','-a','--all') or not a.startswith('-') for a in args):
            if len(indexes)==1 or len(indexes)==2 and args[indexes[0]].isdigit():
                index=indexes[-1];args[index]=aliases.get(args[index],args[index])
    execute(program,[program,*args],env)
    raise RuntimeError('man-db exec unexpectedly returned')


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,TypeError) as error:
        print('man: '+str(error),file=sys.stderr);raise SystemExit(1)
