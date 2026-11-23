<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Base content inventory from the Void construction path

Source review: 2026-11-23. Reviewed Mojt revision:
`ea033084b8997e980943cc01591ab6f669af4473`.

This report inventories the existing construction path as input to defining
Base's contents. It makes no changes to the bootstrap, installed releases,
package selection or runtime policy. Loader/libc/ABI analysis follows this work.

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

No bootstrap, package installation, source build, target execution or physical
inventory was performed for this report. No new owner-machine test is required
to review this source inventory.

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

## 2. Additional inputs and dependency evidence

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

These declarations explain likely additional package families. They do not
establish the exact resolved binary dependency closure of Base 0.1.3.

### Library families to account for

| Family | Evidence in the reviewed source recipes | Status of the inventory claim |
| --- | --- | --- |
| GMP, ACL/extended-attribute support and capabilities | `coreutils` uses `gmp-devel`, `acl-devel`, `libcap-devel`; `sed` and `tar` use ACL build inputs; ACL uses attr inputs | Runtime-library candidates; inspect binary metadata to establish actual linking and installed packages |
| PCRE2 | `grep` uses `pcre2-devel`; PCRE2 splits its shared libraries into `libpcre2` | Candidate support for the selected grep build; do not infer that the separate PCRE command package is installed |
| XBPS/archive support | `xbps` uses zlib, OpenSSL and libarchive build inputs and splits shared XBPS libraries into `libxbps` | Candidate bootstrap support retained by the current non-pruning packer if present |
| Compression/crypto support behind libarchive | Its recipe enables ACL/xattrs, LZO, LZ4, OpenSSL and Zstd and uses zlib, bzip2 and liblzma inputs | Candidate transitive support; this does not imply installation of each compressor's executable |
| Compiler support libraries | Void maps `libgcc_s.so.1` to the `libgcc` package | Conditional on actual binary requirements; a mapping alone is not evidence that it is installed |

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

For exact historical versions and per-file confirmation, useful additional
inputs are the retained `packages.txt`, `manifest.toml` and a listing of the
specific release's `rootfs.tar.zst` (or its immutable Base tree). They refine this
inventory; they are not prerequisites for discussing the eleven explicit inputs
and the documented packing rules. Do not run a fresh moving-repository bootstrap
solely to claim an inventory of an old release.

The next phase can map loader/library consumers across Base, System and Ports
once the intended Base content is discussed. This report does not select a
glibc version, toolchain, ABI policy or source-build implementation.
