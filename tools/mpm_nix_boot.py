# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Boot-only projection; preserve the existing Nix runtime adapter unchanged."""
from pathlib import Path

from mpm_nix_binary import NixBinaryAdapter, store_path
from mpm_ports_profile import require


class NixBootAdapter(NixBinaryAdapter):
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

