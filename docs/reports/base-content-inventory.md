<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Base content inventory from the Void construction path

Source review: 2026-11-23. Reviewed Mojt revision:
`ea033084b8997e980943cc01591ab6f669af4473`.

This report inventories the existing construction path and a saved 29-package
bootstrap inventory as input to defining Base's contents. It makes no changes
to the bootstrap, installed releases, package selection or runtime policy.
Loader/libc/ABI analysis follows this work.

## Evidence and limits

The authoritative Mojt inputs are:

- [`bootstrap/void.sh`](../../bootstrap/void.sh): requested packages, repository,
  construction tools and package-list capture.
- [`tools/mojt-base-pack`](../../tools/mojt-base-pack): transformation of the
  supplied rootfs into a Base release.
- [`manifests/base-0.1.1.toml`](../../manifests/base-0.1.1.toml) and
  [`base-0.1.2.toml`](../../manifests/base-0.1.2.toml): example release inputs,
  not inventories of the physical Base 0.1.3 installation.

For package contents and dependency clues, this review also reads Void's source
recipes at exact revision
[`2004b86d9c55f9a553cf88a30cce01a8c9960d97`](https://github.com/void-linux/void-packages/tree/2004b86d9c55f9a553cf88a30cce01a8c9960d97).
That is a separate source snapshot, not an asserted pin of the binary repository
used to produce Base 0.1.3. References to its recipes below describe that snapshot.

The bootstrap selects the moving `https://repo-default.voidlinux.org/current`
repository and does not pin the eleven package versions or complete dependency
closure. It pins only its external static XBPS archive. Consequently, the script
establishes the direct package selection exactly, but cannot recover historical
resolved versions or a byte/file inventory of Base 0.1.3 by itself. A fresh
bootstrap today would be another build, not a reconstruction of that release.

The saved `base-0.1-packages.txt` now supplies observed package names and
versions; section 2 transcribes all its entries. It does not identify a Base
release artifact or supply the post-packing file inventory. No new bootstrap,
package installation, source build or target execution was performed for this
report.

## 1. Directly selected packages

The XBPS install invocation requests exactly these eleven packages. They are
construction inputs; they are not eleven independently managed Mojt packages.
Examples describe their roles, not a complete command/file manifest.

| Explicit input | Contribution to the construction rootfs | Treatment by the Mojt packer |
| --- | --- | --- |
| `base-files` | Directory layout, compatibility links, default configuration, identity files and assorted Void helpers/policy files | Layout and most files survive; configuration/identity changes are listed below |
| `glibc` | C runtime, dynamic loader, associated runtime tools/data | Retained; no loader/libc replacement by the packer |
| `dash` | POSIX shell implementation and `/bin/sh` alternative | Retained with the links produced during bootstrap |
| `coreutils` | Basic file/text/account-information commands, such as `cp`, `mv`, `ls`, `cat`, `id` and `chmod` | Retained |
| `grep` | GNU text searching | Retained |
| `sed` | GNU stream editing | Retained |
| `findutils` | GNU file searching and argument-list handling | Retained |
| `tar` | GNU archive handling | Retained |
| `gzip` | Gzip compression/decompression and accompanying utilities | Retained |
| `xbps` | Package installation/query tools inside the bootstrap rootfs | `usr/bin/xbps-*`, `usr/sbin/xbps-*` and selected configuration are removed; this is not dependency garbage collection |
| `ca-certificates` | CA certificate inputs, trust-store configuration and maintenance script | Retained subject to the general `/etc` relocation |

Sources: Mojt's install invocation and the corresponding Void
[`srcpkgs`](https://github.com/void-linux/void-packages/tree/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs)
templates. Bootstrap requests `XBPS_ARCH=x86_64`, using Void's glibc repository.

The pinned external construction archive is
`xbps-static-static-0.60.4_1.x86_64-musl.tar.xz`, with SHA256
`603b3c55e9cabd5af79b461b929b14e1556a443c97b5714d188681c2172d9e28`.
It is unpacked into the host-side `$MOJT_LAB/tools` area. The `musl` in this
tool archive's name does not select musl for the Base rootfs. This external
static tool and the `xbps` package requested inside the rootfs are distinct.

## 2. Observed bootstrap package inventory

Evidence: the supplied `base-0.1-packages.txt`, SHA256
`baf54bc46516128e5427f97da956ace5b1c533e9215734cbbf99e2c8e4aa1bad`. It contains
29 unique `ii` (installed) entries. All eleven package names requested by
`bootstrap/void.sh` occur in the list; the other eighteen are additional to
that explicit selection. The file does not record dependency edges, installation
time, the bootstrap source revision or a final Base image identity.

Versions below include Void's packaging revision suffix (`_N`). This is the
saved build's observed inventory, not a reconstruction using today's repository.

| Package | Observed version/revision | Relation to the bootstrap request |
| --- | --- | --- |
| `acl` | `2.4.0_1` | Additional |
| `attr` | `2.6.0_1` | Additional |
| `base-files` | `0.146_1` | Explicit |
| `bzip2` | `1.0.8_2` | Additional |
| `ca-certificates` | `20250419+3.131.1_2` | Explicit |
| `coreutils` | `9.4_3` | Explicit |
| `dash` | `0.5.12_3` | Explicit |
| `findutils` | `4.10.0_1` | Explicit |
| `glibc` | `2.41_1` | Explicit |
| `gmp` | `6.3.0_1` | Additional |
| `grep` | `3.12_1` | Explicit |
| `gzip` | `1.14_1` | Explicit |
| `libarchive` | `3.8.9_1` | Additional |
| `libcap` | `2.78_1` | Additional |
| `libcrypto3` | `3.6.5_1` | Additional |
| `liblz4` | `1.10.0_1` | Additional |
| `liblzma` | `5.8.3_1` | Additional |
| `libpcre2` | `10.49_1` | Additional |
| `libssl3` | `3.6.5_1` | Additional |
| `libxbps` | `0.60.7_1` | Additional |
| `libxcrypt-compat` | `4.4.38_1` | Additional |
| `libzstd` | `1.5.7_1` | Additional |
| `openssl` | `3.6.5_1` | Additional |
| `run-parts` | `5.23.2_1` | Additional |
| `sed` | `4.10_1` | Explicit |
| `tar` | `1.35_1` | Explicit |
| `xbps` | `0.60.7_1` | Explicit |
| `xbps-triggers` | `0.131_1` | Additional |
| `zlib` | `1.3.2_1` | Additional |

The eighteen additional packages can be grouped by function without claiming
that this table establishes their precise dependency graph:

| Function | Additional packages in the saved inventory |
| --- | --- |
| ACLs, extended attributes and capabilities | `acl`, `attr`, `libcap` |
| Arithmetic and regular expressions | `gmp`, `libpcre2` |
| Archive/compression support | `libarchive`, `bzip2`, `liblz4`, `liblzma`, `libzstd`, `zlib` |
| TLS/crypto and certificate maintenance | `openssl`, `libcrypto3`, `libssl3`, `run-parts` |
| XBPS support | `libxbps`, `xbps-triggers` |
| Legacy password-hashing compatibility | `libxcrypt-compat` |

`libxbps` and `xbps-triggers` are therefore observed installed packages, rather
than just candidates suggested by current recipes. The packer has no general
removal rule for their library/script payloads. Which other support libraries
remain necessary after removing the XBPS commands still requires consumer/file
analysis; their presence is not evidence that they are all removable.

There are no `bash`, `python3`, compiler, `libgcc` or LZO-package entries in this
list. This establishes the absence of those package entries, not a per-file
executable/library absence proof. In particular, a library package entry such
as `libzstd` does not establish that a `zstd` command is shipped.

The saved inventory and the separately reviewed Void recipe snapshot are not
identical versions: for example, observed `gzip` is `1.14_1`, `libarchive` is
`3.8.9_1` and `ca-certificates` is `20250419+3.131.1_2`, while the recipe snapshot
has `1.15_1`, `3.8.11_1` and `20250419+3.134_1`, respectively. Use the saved list
for observed versions and the source snapshot only for the explicitly scoped
recipe evidence below.

### Dependency evidence from the separate source snapshot

Eleven requested names do not imply eleven installed packages. XBPS resolves
runtime dependencies. Source-recipe build dependencies are not an installed
runtime list: Void's
[`04-generate-runtime-deps.sh`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/common/hooks/pre-pkg/04-generate-runtime-deps.sh)
also derives dependencies from built ELF `NEEDED` entries and its
[`common/shlibs`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/common/shlibs)
mapping. Subpackage splitting matters too.

### Explicit runtime declarations in the reviewed Void snapshot

| Recipe | Explicit runtime dependency evidence | Inventory implication |
| --- | --- | --- |
| [`base-files`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/base-files/template) | `xbps-triggers` | Distribution maintenance scripts can enter through the layout/defaults package |
| [`xbps`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/xbps/template) | `ca-certificates`, `xbps-triggers` | The bootstrap tool's support content is broader than its command names |
| [`ca-certificates`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/ca-certificates/template) | `openssl`, `run-parts` | Certificate selection can bring command-line utilities as well as certificate data |
| [`glibc`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/glibc/template) | `libxcrypt-compat` under `CHROOT_READY` | Compatibility content is conditional recipe evidence, not a recovered historical installation record |

These declarations help explain the observed additional package families. The
saved inventory establishes package presence; neither it nor these separate
recipes alone establish every dependency edge or bind the inventory to a
specific Base 0.1.3 archive.

### Recipe clues for library consumers

The package list establishes presence; these recipes suggest consumer
relationships to investigate without establishing the historical ELF graph.

| Family | Evidence in the reviewed source recipes | Scope of inference |
| --- | --- | --- |
| GMP, ACL/extended-attribute support and capabilities | `coreutils` uses `gmp-devel`, `acl-devel`, `libcap-devel`; `sed` and `tar` use ACL build inputs; ACL uses attr inputs | `gmp`, `acl`, `attr` and `libcap` are observed; actual per-binary linking needs ELF evidence |
| PCRE2 | `grep` uses `pcre2-devel`; PCRE2 splits its shared libraries into `libpcre2` | `libpcre2` is observed; the separate `pcre2` command package is not listed |
| XBPS/archive support | `xbps` uses zlib, OpenSSL and libarchive build inputs and splits shared XBPS libraries into `libxbps` | These runtime families are observed; the packer retains their unfiltered files, but does not establish which remain needed |
| Compression/crypto support behind libarchive | Its recipe enables ACL/xattrs, LZO, LZ4, OpenSSL and Zstd and uses zlib, bzip2 and liblzma inputs | Several matching families are observed; no LZO-package entry is listed. Do not equate this separate recipe's enabled features with the historical build |
| Compiler support libraries | Void maps `libgcc_s.so.1` to the `libgcc` package | `libgcc` is not listed; the mapping is not installation evidence |

The additional recipe sources are
[`coreutils`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/coreutils/template),
[`sed`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/sed/template),
[`tar`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/tar/template),
[`acl`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/acl/template),
[`grep`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/grep/template),
[`pcre2`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/pcre2/template) and
[`libarchive`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/libarchive/template).
No dependency analysis has been used to delete or replace any files.

## 3. What the packer changes

The packer starts with `cp -a ROOTFS/. STAGE`. Its policy is mostly preservation,
with the explicit transformations below, rather than a final-file allowlist.

| Input or path | Released result |
| --- | --- |
| Filesystem root metadata | Root owner/group 0:0 and mode 0755 in the staged copy |
| `/etc/*` | Moved to `/usr/etc`, except the removed/replaced entries below; conflicting pre-existing defaults are refused |
| `/etc/os-release`, `/etc/xbps.d`, `/usr/etc/os-release`, `/usr/etc/xbps.d` | Removed from vendor defaults |
| `/usr/etc/issue` | Generated Mojt Base/version banner |
| `/usr/etc/{machine-id,hostname,resolv.conf,mtab}` | Removed so machine identity/runtime state are not distributed as defaults |
| `/var`, `/home`, `/root`, `/srv`, `/run`, `/tmp`, `/boot`, `/dev`, `/proc`, `/sys`, `/opt`, `/usr/local` | Contents cleared; real directories and their modes are retained |
| `/usr/bin/xbps-*`, `/usr/sbin/xbps-*` | Removed |
| `/usr/share/xbps.d` | Removed |
| Shared libraries and other unlisted files | Retained; no dependency garbage collection, generic documentation pruning or library minimization |
| `/usr/lib/os-release` | Replaced by generated Mojt release identity |

The raw Base image has an empty `/etc`; installation/state initialization supplies
the persistent configuration, including `/etc/os-release` pointing to the chosen
Base identity. Files moved to `/usr/etc` are release defaults, not a copy of the
machine's current configuration.

The construction package list is written as `$MOJT_LAB/base-0.1-packages.txt`.
Only an explicit packer `--packages FILE` copies it to the release's `packages.txt`
and names it in `manifest.toml`. It is a pre-packing package list; it does not
claim that all of each package's files remain after the transformations.

## 4. Less obvious contents revealed by the recipes

These are source findings from the pinned Void snapshot. The corresponding
files survive Mojt's packer if present in its input; their presence in the
historical 0.1.3 archive has not been measured here.

- `base-files` supplies `/usr/bin/vkpurge`, a Void Kernel cleanup helper using
  `xbps-query` and Void Kernel hook paths. Removing `xbps-*` does not remove it.
- Its `/usr/bin/lsb_release` script hardcodes `VoidLinux`, `Void Linux`, `rolling`
  and `void`. Replacing `os-release` and `issue` does not rewrite this script.
- It installs Void sysctl defaults, modprobe configuration, udev rules and a
  dracut configuration file under `/usr/lib`. The packer does not filter them.
  Presence of these files does not establish that their consumers exist or use
  them in the composed Mojt System.
- It supplies shell/profile/skel defaults, common license texts, color data,
  `/etc/ld.so.conf.d` content and compatibility directory links. These need to be
  inventoried as files/data rather than reduced to the package label
  "filesystem skeleton".
- `xbps-triggers` installs scripts below `/usr/libexec/xbps-triggers`. The packer
  clears the `/var/db/xbps` registration but has no removal rule for that script
  directory.
- `ca-certificates` includes `update-ca-certificates` and requests `openssl` and
  `run-parts`. Its install action generates the certificate store before packing;
  `/etc` content is subsequently moved with the other defaults.
- The reviewed `findutils` recipe disables `locate` and exposes GNU `gfind` and
  `gxargs` through `find`/`xargs` alternatives. The reviewed `coreutils` recipe
  omits `kill` and `uptime` and registers `hostname-coreutils` as an alternative.
  Package names alone do not establish the complete command interface.

Relevant sources include the
[`base-files` template](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/base-files/template),
[`vkpurge`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/base-files/files/vkpurge),
[`lsb_release`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/base-files/files/lsb_release),
[`xbps-triggers`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/xbps-triggers/template),
[`ca-certificates` install action](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/ca-certificates/INSTALL) and
[`findutils`](https://github.com/void-linux/void-packages/blob/2004b86d9c55f9a553cf88a30cce01a8c9960d97/srcpkgs/findutils/template).

## 5. Input to the content-definition discussion

The inventory supports these groups for review, without deciding their final
membership or changing an existing release:

| Group | Contents to discuss |
| --- | --- |
| Existing useful Unix foundation | Shell, core utilities, grep, sed, find/xargs, tar and gzip |
| Runtime support | C runtime/loader and the actual library/data dependencies of the retained programs |
| Mojt-owned release structure | Directory/link layout, identity and appropriate release defaults |
| Explicit content choices | CA data versus maintenance utilities, locales, documentation, licenses and optional library-backed command features |
| Distribution-specific carryover | XBPS maintenance scripts/libraries, Void identity helpers, Kernel helpers and device/initramfs policy files |

The script does not directly request a Kernel, PID 1, Python, compiler, SSH
server, network manager or desktop. It does not establish a separate Base
requirement for tools merely visible in a composed System's interactive PATH.
Indirect packages and script interpreters require the same evidence distinction
as shared libraries; "not directly requested" is not a complete absence proof.

The historical bootstrap package names and versions are now captured above.
For binding them to a particular Base release and confirming final files, useful
additional inputs are that release's `manifest.toml`, retained `packages.txt`
and a listing of its `rootfs.tar.zst` (or immutable Base tree). These refine the
post-packing inventory; they are not prerequisites for discussing the observed
29-package input and the documented packing rules. Do not run a fresh
moving-repository bootstrap solely to claim an inventory of an old release.

The next phase can map loader/library consumers across Base, System and Ports
once the intended Base content is discussed. This report does not select a
glibc version, toolchain, ABI policy or source-build implementation.
