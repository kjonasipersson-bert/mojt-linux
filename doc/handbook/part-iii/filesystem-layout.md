<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# 5. Filesystem layout and persistent state

[Handbook](../README.md) · [Introduction](../part-i/introduction.md)

Mojt separates the files supplied by a release from files belonging to the
machine. A writable `/` lets the administrator create `/data` or an ordinary
mountpoint without changing the installed Base. Base, System and their retained
runtime dependencies remain separate, versioned content.

**Implementation scope:** the writable-root layout is implemented for newly
prepared native-v2 System handovers carrying the new boot code. Existing boot
entries keep their embedded boot code and mount behavior. Selecting an old entry
does not upgrade its layout. Earlier bootstrap and legacy images can still
have read-only `/` until a deployment using the writable-root handover is
prepared and booted. Base changes must satisfy the supported root-projection
and compatibility requirements described below.

## 5.1. The running filesystem

`/` is the filesystem root. `/root` is the root account's home directory; they
are different places with separate backing directories.

| Path | Role and ownership | Writable during normal use? | What happens on a supported generation change? |
| --- | --- | --- | --- |
| `/` and administrator-created paths such as `/data` | Persistent machine filesystem | Yes, subject to Unix permissions | Local files/directories remain |
| `/usr`, excluding `/usr/local` | Selected Base utilities, libraries, release defaults and OS identity | Read-only | Follows the selected Base |
| `/bin`, `/sbin`, `/lib`, `/lib64`, when supplied as Base aliases | Links into the selected Base's immutable layout | Link layout is reserved; target content is read-only | Resolves into the selected Base; incompatible root layouts require explicit migration |
| `/usr/etc` | Release-owned default configuration | Read-only | Defaults follow Base; System also supplies its own defaults |
| `/etc` | Persistent machine configuration and identity | Yes | Existing configuration remains; supported preparation can add missing defaults |
| `/var` | Service databases, logs, caches and package-management state | Yes | Remains; no automatic data/schema rollback |
| `/home` and `/root` | User files and root's home | Yes | Remain |
| `/opt` and `/srv` | Locally managed software and service files | Yes | Remain; not managed as part of Base/System |
| `/usr/local` | Locally installed programs, libraries and other administrator files | Yes, through its own mount under `/usr` | Remains; local programs must still be compatible with the selected runtime |
| `/mnt` and `/media` | Administrator mountpoints | Yes | The directories and any unmounted local contents remain; mounted contents belong to their respective filesystems |
| `/boot` | Persistent local directory in this root layout | Yes | Remains; it is not the boot registry or an automatic ESP mount |
| `/run` | Runtime identity, sockets and other temporary state | Yes, tmpfs | Recreated each boot |
| `/tmp` | Temporary files | Yes, tmpfs | Cleared by reboot |
| `/dev`, `/proc`, `/sys` | Devices and Kernel interfaces | Interface-dependent | Recreated/attached at boot |
| `/run/mojt-system` | Selected System profile and management tools | Read-only | Follows the booted System generation |
| `/lib/modules` (normally `/usr/lib/modules`) | Exact selected Kernel's module tree | Read-only | Follows the selected Kernel, independently of Base/System userspace |
| `/lib/firmware` (normally `/usr/lib/firmware`) on the hardware profile | Firmware supplied by System | Read-only | Follows the selected System firmware |
| `/nix` | Current provider's shared package store and registration data | MPM/provider can import new content; retained System dependency trees are mounted read-only | Installed objects remain; System and Ports choose their versions independently |
| `/run/mojt-disk` | Backing installation, retained artifacts, state and boot registry | Management-owned backing storage | Survives generation changes; the runtime mount is recreated |

Writable root does not make every child mount writable. For example, creating
`/data` is an ordinary local administrative change; replacing a Base executable
under `/usr/bin` is not. A locally installed program under `/usr/local/bin`
belongs to the administrator and is not updated by switching Base.

The real boot records and files remain in the managed installation's backing
`boot/` tree under `/run/mojt-disk`. Use MPM's boot selection commands rather
than treating the visible `/boot` directory as the boot registry.

## 5.2. Persistent backing directories

The native installation uses these backing paths. They explain the mapping;
ordinary work should use the public paths above.

| Backing path, relative to `/run/mojt-disk` | Running path |
| --- | --- |
| `state/rootfs` | `/`, including locally created top-level files/directories |
| `state/etc` | `/etc` |
| `state/var` | `/var` |
| `state/home` | `/home` |
| `state/root` | `/root` |
| `state/local` | `/usr/local` |
| Selected sealed boot Base's `tree/rootfs/usr` | `/usr` |
| Selected System realization's `profile` | `/run/mojt-system` |
| Selected Kernel's retained `payload/lib/modules` | `/lib/modules` |

Component-based System profiles link exact Runtime and optional firmware payloads
under `artifacts/system/installed/` on the backing disk. Handover mounts the
referenced payloads read-only. Firmware follows the selected System when included;
a minimal System can omit it. Older retained generations keep their objects for
return and are not automatically collected.

The persistent root is a small shell of directories and Base aliases, not a
copy of the selected Base and not an overlay over release files. Read-only bind
mounts project the release's immutable top-level trees/files into that shell.
Their runtime mounts stay read-only; providing writable `/` does not modify
the installed release trees.

On first boot of this layout, Mojt publishes a marked root directory atomically
and adds the local-program directory. Preparation alone does not initialize or
modify this machine state. If boot fails later, the marked directories may
remain and can be reused on the next attempt; existing user data is preserved.
An unmarked pre-existing `state/rootfs` is not silently adopted.

`/.mojt-root-layout.json` identifies the installation and supported immutable
root projection. It is boot-owned metadata. Root aliases and mountpoint types
are reserved, even though root can technically change them. A changed alias,
unsafe path, incompatible Base top-level layout, or files placed in an underlying
mountpoint that would be hidden cause a diagnostic refusal. They are not silently
overwritten or deleted. The current layout supports Base releases sharing that
projection; a changed projection needs an explicit future migration.

## 5.3. Generation changes and return

A generation change chooses code and boot inputs. It is not a filesystem
snapshot of the machine's writable data.

| Operation | Changes | Preserves |
| --- | --- | --- |
| Prepare another deployment | Adds the admitted boot files and exact input bindings | Running code, next-boot choice and persistent machine state |
| Select/activate another deployment | Next-boot selection | Currently running code and data |
| Reboot into another System | System profile, services/tools and System-owned firmware | Selected Base/Kernel unless explicitly changed; all persistent paths above |
| Reboot into another Base | Base utilities/libraries/defaults and `/usr/lib/os-release` | System/Kernel choices within compatibility requirements; persistent configuration/data |
| Reboot into another Kernel | Kernel and matching module tree | Base, System userspace, persistent configuration/data |
| Upgrade/activate Ports | Selected application commands and retained versions as requested | Base/System/Kernel boot selection, unrelated exact/project pins and user data |
| Return to an older compatible deployment | Older code and its exact boot combination | Current configuration, databases, local software and user files |

For example, a file under `/data`, a locally installed tool under `/usr/local`,
and edits to `/etc/hostname` remain when changing from one writable-root System
generation to another and when returning. `/tmp` files disappear after reboot.
The version reported by `/etc/os-release` follows the selected Base through the
relative link to `/usr/lib/os-release`; the machine's existing `/etc` is not
replaced by release defaults.

An older program may be unable to read a database written by a newer program.
Keep backups for data recovery; retaining an old boot entry does not restore an
earlier schema, configuration or user file.

An entry predating writable root still mounts its original read-only root.
New `/data`, `/opt`, `/srv` or `/usr/local` content is then retained in the new
backing directories but is not exposed by that old layout. Returning to a
writable-root deployment exposes it again. The established `/etc`, `/var`,
`/home` and `/root` mappings remain shared with those older entries.

[Introduction](../part-i/introduction.md) · [MPM](../part-i/mpm.md)
