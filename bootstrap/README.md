<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Base producers

- `void.sh`: historical static-XBPS bootstrap. Retained for existing recipes;
  the source producer does not invoke it.
- `base-sources.json`: source versions, upstream archive hashes and locations
  used by `../tools/mojt-base-build.py`. See the [build guide](../docs/base-source-build.md).
- `tar-acl-2.4.patch`: GNU tar name-conflict fix from
  [Nixpkgs at the recorded revision](https://github.com/NixOS/nixpkgs/blob/804068b712dc9794d8d25d7af3912c5f45d14d9d/pkgs/by-name/gn/gnutar/acl-2.4.0-name-conflicts.patch),
  matching the approach discussed in the
  [GNU tar upstream report](https://lists.gnu.org/archive/html/bug-tar/2026-06/msg00013.html).
  Upstream GNU tar remains GPL-3.0-or-later; the patch is retained as upstream
  material, not relicensed as Mojt-owned code. Upstream license texts are
  included in the assembled Base.
- `licenses/gcc-runtime-exception.txt`: verbatim GCC Runtime Library Exception
  3.1, from [GCC 14.2.0](https://github.com/gcc-mirror/gcc/blob/releases/gcc-14.2.0/COPYING.RUNTIME).
  The bootstrap compiler runtime is accompanied by this notice and GPLv3 text.
