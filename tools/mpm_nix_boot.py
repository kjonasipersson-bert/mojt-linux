# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Boot-only projection; preserve the existing Nix runtime adapter unchanged."""
from pathlib import Path

from mpm_nix_binary import NixBinaryAdapter, store_path
from mpm_ports_profile import require


class NixBootAdapter(NixBinaryAdapter):
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

