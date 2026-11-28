<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Using MPM for Ports

Ports installs applications independently of Base, System and Kernel. It retains
parallel versions and selects active commands through an atomic profile. Shared
mutations require an administrator; inspection and program execution do not.

## Install and inspect

```sh
mpm ports install neovim --dry-run
mpm ports install neovim
mpm ports list
mpm ports list --exact
mpm ports status
mpm ports history
```

The installed System supplies a pinned provider source. Discovery evaluates
explicitly requested attributes; local search is not a remote package index.
Binary substitutes are imported without a hidden source-build fallback.
An explicit finite `--sources FILE` bundle supplies its own metadata/dependencies.

Native metapackages come from a configured [Mojt Ports repository](ports-repository.md).
Install them using the same command. MPM records their declared Nixpkgs package
wishes with their own origin, and lists the metapackage and installed packages.

First unambiguous installation can establish an active default. Adding another
version preserves an existing default; `--no-activate` suppresses that initial
convenience. A preview can describe acquisition before exact command exports
have been discovered, so it is not evidence of a completed installation.

## Wishes and active versions

A name requests the latest eligible stable release in the accepted view;
`name@SERIES` follows an eligible series and `name@=RELEASE` requests an exact
release. Use `list --exact` to distinguish multiple builds of the same release.
Metadata update leaves accepted targets alone. Explicit upgrade advances its
requested moving wishes, while exact active pins remain fixed. Activation
changes new program starts; existing processes can keep using earlier content.

Configuration and interactive wishes are independent. Removing one reason does
not silently remove another reason or rebind unrelated choices. See the
[Handbook selector, upgrade and removal examples](../doc/handbook/part-i/mpm.md#34-choose-a-version-policy)
and [request/profile contract](ports-profile-implementation.md).

## Manuals

```sh
man git
man nvim
man neovim
man ncdu
manpath
```

Manuals follow the active exact package versions, including separate provider
manual outputs when supplied. The System wrappers compute the search path each
time; no new login is required after installation/activation. Direct active
outputs take precedence over incidental dependency manuals. The role `neovim`
is an alias for `nvim` in simple manual queries when package metadata declares
that main program. Other upstream manual names need not match package names.
An explicit `man -M DIRECTORY` retains man-db's override behavior.

Repeat an existing pinned-provider install wish to complete missing manuals from
an older installation. This preserves the accepted binary, wishes and active
choice and refuses a changed binary rather than silently upgrading. Explicit
catalog producers must include the manual dependencies themselves. Packages
without a manual may provide `--help` or HTML documentation instead.

## Fonts

MPM links the `share/fonts` directories of active Nix and native Port
outputs under `/var/lib/mojt/ports/current/share/fonts/`. Each package role
gets its own directory. Installing another version keeps the currently
selected fonts. Activation or removal updates the font view with the same
profile switch as command aliases.

The `mojt-sway` launcher sets `FONTCONFIG_FILE` to the profile's
`share/fonts.conf` by default. To use the same configuration in another
session, export it before starting Fontconfig applications. With the
`fontconfig.bin` Port installed, `fc-match` shows the font family and file:

```sh
export FONTCONFIG_FILE=/var/lib/mojt/ports/current/share/fonts.conf
fc-match -f '%{family}\n%{file}\n' 'DejaVu Sans Mono'
```

The generated configuration adds the profile fonts to the system and user
font paths available through Fontconfig. New processes use the newly selected
profile. Restart applications that keep their font list in memory.
The first successful Ports mutation with the updated MPM publishes the font
view for an existing profile, including when the wishes and selections are
unchanged.

## Recovery and limits

Retained versions can be selected explicitly. Profile publication preserves the
old choice on acquisition/verification failure. Returning to older application
code does not restore application data or its schema. A general transaction undo,
native Port publisher and garbage collection remain separate work.

The ordinary frontend uses request-origin state and complete profiles. Older
format-1/2/3 workflows belong to the separately invoked `mpm-nix-prototype` and
must not be applied to the current registry as an implicit migration. For full
commands see [the Handbook](../doc/handbook/part-i/mpm.md) and
[frontend reference](ports-cli-integration.md).
