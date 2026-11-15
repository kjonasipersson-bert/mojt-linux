# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Boot-only projection; preserve the existing Nix runtime adapter unchanged."""
import os
from pathlib import Path

from mpm_nix_binary import NixBinaryAdapter, store_path
from mpm_ports_profile import require
from mpm_transaction import protected_directory, sync_directory
import mpm_native_io as io
NIX_DATABASE=Path('/nix/var/nix/db')


class NixBootAdapter(NixBinaryAdapter):
    def inspect(self,ref,root):
        """Check retained identity/roots and registered closure; no byte scrub."""
        i=self.identity(ref);paths=[row['path'] for row in i['closure']]
        gcroot=Path(root)/'retained/nix'/store_path(i['output']).name
        def check():
            protected_directory(gcroot.parent,label='Nix retention')
            require(gcroot.is_symlink() and os.readlink(gcroot)==i['output'] and Path(i['output']).is_dir(),
                    'Nix output/root missing')
            require(sorted(self.runner([self.binary,'--query','--requisites',i['output']]).splitlines())==paths,
                    'Nix closure differs from accepted identity')
            require(self.runner([self.binary,'--query','--hash',*paths]).splitlines()==[r['nar_hash'] for r in i['closure']],
                    'Nix registered hashes differ')
            directory=Path(i['output'])/'bin'
            commands=sorted(p.name for p in directory.iterdir() if p.is_file() and os.access(p,os.X_OK)) if directory.is_dir() else []
            require(commands==i['commands'],'Nix command inventory differs')
            return True
        # A symlink is intentionally checked every time; its target belongs to
        # the exact immutable closure. Cache only after rechecking that binding.
        protected_directory(gcroot.parent,label='Nix retention')
        require(gcroot.is_symlink() and os.readlink(gcroot)==i['output'],'Nix retention conflict')
        key=('nix-metadata',str(root),self.binary,tuple((r['path'],r['nar_hash']) for r in i['closure']),tuple(i['commands']),i['output'])
        database=NIX_DATABASE
        require(str(Path(self.binary).resolve())==self.executable,'Nix helper binding changed')
        return io.preparation_cached(key,[Path(self.executable),*map(Path,paths),
            *(Path(path)/'bin' for path in paths),database/'db.sqlite',database/'db.sqlite-wal'],check,cost=1024)

    def install(self,ref,root):
        """Retain System binaries without the optional full provider scrub.

        Keep the inherited ensure/verify protocol used by Ports and preparation
        unchanged. Nix's realise exit status and root publication remain required.
        """
        i = self.identity(ref);directory = Path(root)/'retained/nix'
        protected_directory(directory,write=True,label='Nix retention')
        directory.mkdir(mode=0o700,exist_ok=True)
        gcroot = directory/store_path(i['output']).name
        if os.path.lexists(gcroot):
            require(gcroot.is_symlink() and os.readlink(gcroot) == i['output'],'Nix retention conflict')
        self.runner([self.binary,'--realise',i['output'],'--add-root',str(gcroot),'--indirect',
                     '--option','max-jobs','0','--option','builders','','--option','require-sigs','true'])
        require(gcroot.is_symlink() and os.readlink(gcroot) == i['output'],'Nix did not register the expected root')
        sync_directory(directory);sync_directory(directory.parent)

    def preserves(self,refs,baseline):
        """Project native references; keep the accepted runtime comparison unchanged."""
        if type(baseline) is dict and baseline.get('format') == 'mojt-system-provider-baseline-v1':
            require(set(baseline) == {'format','references'} and type(baseline['references']) is list
                    and 0 < len(baseline['references']) <= 128,'invalid selected Nix references')
            rows = {}
            for ref in baseline['references']:
                for row in self.identity(ref)['closure']:
                    require(row['path'] not in rows or rows[row['path']] == row,'conflicting selected Nix hashes')
                    rows[row['path']] = row
            baseline = dict(objects=list(rows.values()))
        return super().preserves(refs,baseline)

    def boot_mounts(self,ref,root):
        self.boot_paths(ref,root)
        return [dict(source='nix',target='nix')]

    def boot_paths(self,ref,root):
        """Finite verified-output tree export, never an unrelated inspector store."""
        i=self.identity(ref);names=[]
        for row in i['closure']:
            absolute=store_path(row['path']);relative=str(absolute).lstrip('/')
            target=Path(root)/relative
            require(target==target.resolve() and target.is_dir() and target.samefile(absolute),
                    'boot export target is not the accepted live Nix object')
            names.append(relative)
        return sorted(names)

