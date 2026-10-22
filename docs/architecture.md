<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt Architecture (experimental)

This document records **current decisions and open questions**, not stable promises. For the enduring design goals, see [the manifesto](manifesto.md).

## Layers

| Layer | Purpose | Intended lifecycle |
| --- | --- | --- |
| Base | Minimal glibc-based Unix userspace; shell, core tools, standard system files | Whole-image releases, versioned and rollback-capable |
| System | Kernel, init, firmware, networking, drivers, services and deployment profiles | Independent, but tested for Base ABI compatibility |
| Ports | Applications, libraries, developer toolchains and profiles | Independent versions, pinned environments, optional sandbox execution |
| State | Local configuration, service data and user data | Persists across Base upgrades and rollbacks |

The current Base prototype has no kernel, init, or desktop. The choice of a future System init implementation is not yet frozen. Standardizing on a single supported init system is preferable to maintaining multiple init stacks by default.

## Existing prototype pipeline

```text
bootstrap/void.sh
       |
       v
rootfs (from selected Void packages)
       |
       v
tools/mojt-base-pack + manifests/base-0.1.1.toml
       |
       v
versioned release (rootfs.tar.zst, manifest.toml, optional packages.txt)
       |
       v
tools/mojt-base-install
       |
       +--> base/<version>/
       +--> base/current -> <version>
       +--> state/etc/
       +--> state/var/
```

The prototype bootstrap currently selects eleven Void packages and uses a pinned static XBPS utility as a host-side construction tool. The assembled runtime image strips XBPS executables and package databases. The release is **not yet a bootable OS**.

## Configuration and state

The Base image carries package defaults in `/usr/etc`. During installation, missing defaults are added to a persistent `state/etc` tree. Existing entries are preserved. `/etc/os-release` is a relative symlink to `/usr/lib/os-release`, which the Base packer generates from its version manifest.

Persistent `state/var` is kept across Base generations. For testing, the two state directories are bind-mounted over `/etc` and `/var` in the selected rootfs inside a separate mount namespace. A future boot process must implement this arrangement before starting services.

Rollback does **not** revert persistent state or database formats. Future compatibility checks and explicit state migrations will be necessary.

## MPM front-end contract (design only)

The proposed user-facing package interface is documented in
[the MPM contract](mpm.md). It specifies `mpm <area> <action>`,
metadata-only `update`, explicit installation versus activation,
independent Base/System/Kernel/Ports transactions, and versioned Ports
selectors. The candidate meaning of `gimp@3.0` as a release-line selector
is explicitly **under review**, not yet implemented or finalized.

The contract deliberately does not select a package backend, a System
release format, a Ports store implementation, or a deployment format.
These decisions require separate evaluation.

## Ports direction

Ports should support:

- multiple installed versions and version-specific dependencies;
- profiles that activate selected versions via links or a similarly simple mechanism;
- project lockfiles that protect compilers and build dependencies from ordinary updates;
- native execution by default for ordinary command-line tools;
- optional security sandboxes for programs or build processes where useful.

This remains a design direction, not an implemented Mojt Ports manager. We should evaluate mature components before creating our own resolver or content-addressed store.

## Explicitly unresolved

- Source-based/self-hosted Base build and verifiable reproducibility
- Signature verification and trusted release channels
- Crash-safe activation and `fsync` durability guarantees
- Boot integration, state mounts, and kernel/module versioning
- ABI policy between Base, System, and Ports
- State migration/rollback guarantees for system services
- Alternative bootstrap backends and platform support

## System scope and larger component groups (open)

The first QEMU boot uses a host-provided kernel and minimal initramfs;
it does **not** establish a permanent System package format. System may
eventually include desktop environments such as GNOME, rather than limiting
System to the kernel, firmware and low-level services. That choice remains
open for reconsideration. A substantial System desktop/profile would likely
need explicit, versioned dependencies and compatibility checks; a lightweight
component dependency resolver or use of existing tooling may be appropriate.
Do not assume that all desktop components must belong to Ports.

The VM prototype intentionally postpones package dependency resolution,
System-versus-Ports desktop placement, and the mechanism that exposes
independently installed System files inside the active Base filesystem.

## Experimental VM PID 1 (System, not Base)

The first boot prototype now uses a **System-owned static BusyBox init**,
provided by the image builder in `system/prototype-init` and made available
under `/run/mojt-system` at boot. BusyBox init supervises the serial console
and provides a minimal poweroff path. This is **development-only**: BusyBox
is suitable for the prototype, rescue media and embedded contexts, but it is
**not** the planned permanent init for the Mojt distribution. The production
init remains an open choice (systemd is a pragmatic candidate).

Account databases (`/etc/passwd`, `/etc/group`, `/etc/shadow`) are persistent
machine state. The source VM currently has a root account expecting shadow
but no shadow file; the experimental serial root console bypasses login
entirely. A later, separate System feature must establish authenticated
console login and safe initial credential provisioning. Never install a
universal default password or overwrite existing machine credentials.

## Experimental System console login (not production authentication)

The VM prototype may use a static BusyBox `getty` and `login` from
`system/prototype-init`, separate from Base, to authenticate the local
serial-console root account. Password creation happens during **host-side
VM staging** from an interactive terminal. The salted password hash and
account files are placed only in the VM copy of persistent `/etc`.

This is not an architecture commitment to BusyBox login, or a replacement
for the eventual installer and System authentication stack. A production
System may use PAM and other established account-management packages.
Root should normally be locked when a configured administrative user is
available. Persistent home directories and UID/GID handling remain open.

The development VM console is deliberately unauthenticated; enabling a
root password without changing the console's login process does not secure
it. The builder's authenticated mode refuses a conflicting existing
`inittab`, leaves pre-existing shadow credentials unchanged and avoids
embedding plaintext credentials in code, manifests or process arguments.

## Identity, issue, MOTD, and independent version numbers

Mojt keeps **Base version** separate from **System version**. A login banner
may show `Mojt Linux 0.1/0.1.3`: System `0.1`, Base `0.1.3`. These are
independent lifecycles, not a single combined release version.

The Base packer generates a neutral fallback `/usr/etc/issue`
(`Mojt Linux Base <base-version>`) for **newly packed** Base releases,
including Base-only containers. It replaces the bootstrap backend's Void
branding **inside the staged release only**. Installed `/etc/issue` remains
persistent administrator state; the installer adds defaults only if missing.
The raw Base filesystem's `/etc` remains empty by design.

A System boot is responsible for constructing the **combined** identity
from System release metadata and the currently selected Base. In the
initial VM prototype, the System component declares `version = 0.1`
using a simple text metadata file and records the **VM assembly time**
in UTC. This is not yet a versioned System release format. Early boot
writes volatile `/run/mojt/issue` and `/run/mojt/motd`; authenticated
`getty` uses the former with `-f`. Base does not have to be rebuilt
on every System upgrade, nor System on every Base upgrade.

Existing machine-local `/etc/issue`, `/etc/motd`, and `/etc/hostname`
are never silently overwritten. The VM image builder places a missing
hostname default `mojt` into **copied VM state**, sets the kernel
hostname at boot, and links a **missing** `/etc/motd` to the generated
runtime file. An existing local MOTD always takes precedence; runtime
information remains available explicitly at `/run/mojt/motd`.
No change is made to existing Base generations or the source installation.
