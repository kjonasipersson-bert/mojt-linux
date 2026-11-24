# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Explicit Nix binary-output adapter; no evaluation, build or global activation."""
import os
from pathlib import Path
import re
import subprocess

import mpm_requests as wishes
from mpm_transaction import sync_directory, protected_directory
from mpm_ports_profile import require


def store_path(value):
    require(type(value) is str and re.fullmatch(r'/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._?=-]+',value) and not value.endswith('.drv'),'not an exact Nix output path')
    return Path(value)


def executable_name(value):
    """An inventoried provider basename, not a requested public Ports alias."""
    require(type(value) is str and value not in ('','.','..') and '/' not in value
            and len(value.encode()) <= 255 and not any(ord(c) < 32 or ord(c) == 127 for c in value),
            'invalid Nix executable basename: '+repr(value))


class NixBinaryAdapter:
    def __init__(self, nix_store, runner=None):
        self.binary=str(nix_store)
        require(Path(self.binary).is_absolute(),'Nix helper must be a retained absolute path')
        # Pin the executable separately from argv[0]. Nix's legacy tools may
        # be symlinks to the multicall 'nix' binary; resolving argv[0] would
        # change 'nix-store --realise' into an unrelated 'nix --realise'.
        self.executable=str(Path(self.binary).resolve())
        self.runner=runner or self._run

    def _run(self,args):
        result=subprocess.run(args,executable=self.executable,text=True,stdout=subprocess.PIPE,check=False)
        require(result.returncode==0,'Nix binary import/verification failed: '+args[1])
        return result.stdout.strip()

    def identity(self,ref):
        wishes.fields(ref,('provider','identity'));require(ref['provider']=='nix','wrong adapter')
        i=ref['identity'];wishes.fields(i,('format','output','closure','commands'))
        require(i['format']=='mojt-nix-output-v1','unsupported Nix identity')
        store_path(i['output']);require(type(i['closure']) is list and i['closure'],'missing Nix closure')
        paths=[]
        for row in i['closure']:
            wishes.fields(row,('path','nar_hash'));store_path(row['path'])
            require(type(row['nar_hash']) is str and re.fullmatch(r'sha256[:\-][A-Za-z0-9+/=]+',row['nar_hash']),'invalid NAR hash')
            paths.append(row['path'])
        require(paths==sorted(set(paths)) and i['output'] in paths,'invalid closure inventory')
        require(type(i['commands']) is list and i['commands']==sorted(set(i['commands'])),'invalid command list')
        for name in i['commands']:executable_name(name)
        return i

    def describe(self,ref,root):
        i=self.identity(ref)
        return dict(reference=ref,commands={name:str(store_path(i['output'])/'bin'/name) for name in i['commands']})

    def contains(self,ref,path):
        """Pure authorization of a profile link into an accepted exact closure."""
        i=self.identity(ref)
        require(type(path) is str and path.startswith('/') and str(Path(path))==path
                and '..' not in Path(path).parts, 'noncanonical provider link')
        return any(path==r['path'] or path.startswith(r['path']+'/') for r in i['closure'])

    def verify_path(self,ref,path,*,executable=False):
        require(self.contains(ref,path), 'unbound provider path')
        resolved=Path(path).resolve(strict=True)
        require(self.contains(ref,str(resolved)) and (resolved.is_file() or resolved.is_dir()),
                'provider path escapes closure or has an unsupported type')
        require(not executable or resolved.is_file() and resolved.stat().st_mode & 0o001, 'provider export is not a public executable')

    def preserves(self,refs,baseline):
        """Pure exact closure comparison for the unchanged-startup System subset."""
        require(type(baseline) is dict and type(baseline.get('objects')) is list, 'missing selected Nix closure facts')
        accepted={}
        for ref in refs:
            for row in self.identity(ref)['closure']:
                require(row['path'] not in accepted or accepted[row['path']]==row['nar_hash'], 'conflicting accepted Nix hashes')
                accepted[row['path']]=row['nar_hash']
        expected={}
        for row in baseline['objects']:
            store_path(row['path'])
            require(type(row.get('nar_hash')) is str and row['nar_hash'], 'selected Nix closure lacks NAR hashes')
            require(row['path'] not in expected, 'duplicate selected Nix object')
            expected[row['path']]=row['nar_hash']
        require(expected, 'empty selected Nix closure')
        missing=sorted(path for path,value in expected.items() if accepted.get(path)!=value)
        return dict(policy='preserve-exact-startup-closure-v1', compatible=not missing, missing_or_changed=missing,
                    runtime_files=['tools/mpm_nix_binary.py'])

    def ensure(self,ref,root):
        i=self.identity(ref);directory=Path(root)/'retained/nix'
        protected_directory(directory, write=True, label='Nix retention')
        directory.mkdir(mode=0o700,exist_ok=True)
        require(not directory.is_symlink(),'unsafe Nix retention directory')
        gcroot=directory/store_path(i['output']).name
        if os.path.lexists(gcroot):require(gcroot.is_symlink() and os.readlink(gcroot)==i['output'],'Nix retention conflict')
        self.runner([self.binary,'--realise',i['output'],'--add-root',str(gcroot),'--indirect',
                     '--option','max-jobs','0','--option','builders','','--option','require-sigs','true'])
        require(gcroot.is_symlink() and os.readlink(gcroot)==i['output'],'Nix did not register the expected root')
        self.verify(ref,root)
        sync_directory(directory)
        sync_directory(directory.parent)

    def verify(self,ref,root):
        i=self.identity(ref);paths=[r['path'] for r in i['closure']]
        protected_directory(Path(root)/'retained/nix', label='Nix retention')
        gcroot=Path(root)/'retained/nix'/store_path(i['output']).name
        require(gcroot.is_symlink() and os.readlink(gcroot)==i['output'] and Path(i['output']).is_dir(),'Nix output/root missing')
        actual=sorted(self.runner([self.binary,'--query','--requisites',i['output']]).splitlines())
        require(actual==paths,'Nix closure differs from accepted identity')
        hashes=self.runner([self.binary,'--query','--hash',*paths]).splitlines()
        require(hashes==[r['nar_hash'] for r in i['closure']],'Nix registered hashes differ')
        self.runner([self.binary,'--verify-path',*paths])
        directory=Path(i['output'])/'bin'
        actual=sorted(p.name for p in directory.iterdir() if p.is_file() and os.access(p,os.X_OK)) if directory.is_dir() else []
        require(actual==i['commands'],'Nix command inventory differs')
        for name in i['commands']:
            resolved=(directory/name).resolve()
            require(any(resolved==Path(p) or Path(p) in resolved.parents for p in paths),'command escapes verified closure')
