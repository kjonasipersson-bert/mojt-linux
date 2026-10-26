<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt Architecture (experimental)

## Explicit boot generations (2026-10-25 experiment)

New UEFI builds pin both Base and System in each boot pair, independently of
their `current` links. The builder can compose multiple pairs in a fresh image;
each pair has its own initramfs and a GRUB entry naming both selections. The
same `/etc`, `/var` and Nix store are used by every pair. This does not roll
back state, introduce a System release format or update existing boot disks.
See [the generation experiment](boot-generations.md) for the conservative ABI
gate, filesystem layout, build recipe and acceptance boundaries.

This document records **current decisions and open questions**, not stable promises. For the enduring design goals, see [the manifesto](manifesto.md).

The [roadmap](roadmap.md) records completed Base/System and different-kernel
VM experiments and the next System/MPM work. The
[System completeness and account proposal](system-completeness-proposal.md)
is a discussion document; its home, authentication and privilege policies
are not yet architecture decisions or implemented capabilities.

## Layers

| Layer | Purpose | Intended lifecycle |
| --- | --- | --- |
| Base | Minimal glibc-based Unix userspace; shell, core tools, standard system files | Whole-image releases, versioned and rollback-capable |
| System | Kernel, init, firmware, networking, drivers, services and deployment profiles | Independent, but tested for Base ABI compatibility |
| Ports | Applications, libraries, developer toolchains and profiles | Independent versions, pinned environments, optional sandbox execution |
| State | Local configuration, service data and user data | Persists across Base upgrades and rollbacks |

The current Base prototype has no kernel, init, or desktop. The experimental
System implementation uses systemd. BusyBox remains an early-boot/rescue component and
a temporary console-login tool in the VM experiment.

## Accepted update units and activation model (2026-10-26)

Each layer uses the unit appropriate to its responsibility:

- **Base:** one complete, immutable, versioned release. It may be built from
  packages or sources; individual runtime Base package upgrades are outside
  the model. A new installation retains the previous Base release.
- **System:** a content-changing upgrade publishes a new coherent generation
  with exact component/dependency references. Old generations remain historical
  snapshots, rather than independent requests to upgrade. A no-op need not
  create a new content generation.
- **Ports:** parallel application versions, explicit active choices and
  upgrade policies, with readable transaction history. A per-program upgrade
  does not require a user-managed generation of the entire Ports collection.
  Atomic internal profile snapshots remain an implementation option.

A boot deployment binds exact Base, System userspace and Kernel build
identities to matching modules and boot artifacts. Kernel is architecturally
part of System, but has a separate MPM upgrade scope. A System upgrade
preserves Base/Kernel selections; a Kernel upgrade preserves Base/System
userspace selections. Any required cross-area changes need an explicit plan.
These are accepted semantics; the independent Kernel/deployment formats are
not implemented by the current fresh-image builder.

Boot-area activation selects the next boot, without automatically restarting
the machine or changing its running services. Further changes start from the
selected deployment, even if an older one is still running. Status and plans
must distinguish installed, selected and running content. Users must be able
to inspect explicit System choices, dependencies and changes between
generations, rather than relying on opaque generation numbers.

Ports selection affects new program starts; existing processes can continue
using earlier content. Returning to an installed application version uses
explicit activation. Additional installation preserves the existing active
choice; the accepted first-install convenience exception still applies.
A general Ports transaction-undo command and retention/GC policy remain
future work. Persistent configuration and application/service data are not
automatically restored by any content selection change.

The [MPM contract](mpm.md#2-operations) defines the shared verbs, pins, preview
requirements and the boundary between accepted policy and working commands.

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
       +--> state/home/
       +--> state/root/
```

The prototype bootstrap currently selects eleven Void packages and uses a pinned static XBPS utility as a host-side construction tool. The assembled runtime image strips XBPS executables and package databases. Base alone has no boot stack; the tested System VM composes it with a kernel, initramfs and services.

## Configuration and state

The Base image carries package defaults in `/usr/etc`. During installation, missing defaults are added to a persistent `state/etc` tree. Existing entries are preserved. `/etc/os-release` is a relative symlink to `/usr/lib/os-release`, which the Base packer generates from its version manifest.

Persistent `state/var` is kept across Base generations. Host-side tests bind
the state directories over `/etc` and `/var` in a separate mount namespace.
The System VM implements these mounts before starting services, and the owner
has verified both state directories across guest boots.

The accepted home extension gives `/home` and `/root` their own persistent
`state/home` and `state/root` directories, rather than placing homes under `/var`.
New VM images mount them before starting login or services. The storage method
is an implementation choice and may later use other filesystems or subvolumes;
the stable user-facing paths and state-preservation policy remain the same.
See [state layout and migration limits](state-layout.md). Owner VM acceptance
of the new home mounts is pending.

Rollback does **not** revert persistent state or database formats. Future compatibility checks and explicit state migrations will be necessary.

## MPM front-end contract (partial implementation)

The accepted user-facing package model is documented in
[the MPM contract](mpm.md). It specifies `mpm <area> <action>`,
metadata-only `update`, explicit installation versus activation,
independent Base/System/Kernel/Ports transactions, and versioned Ports
selectors. The CLI meaning of `gimp@3.0` as the latest eligible stable
release in the 3.0 line and `gimp@=3.0` as an exact release identifier
has been **accepted as the design contract**, but is not yet implemented.
Detailed version ordering and backend adapters remain open.

Nix is now the selected Ports backend after the binary-import and pacman
comparisons. The full selector/project-lock policies remain design requirements. For early Mojt versions, Nix is
also selected for System package acquisition and dependency storage, using a
shared store. The current CLI implements Ports installation, activation,
removal, inspection, recorded attribute upgrades and committed transaction
history. Exact active selections remain pinned while following selections may
advance. Format-2 metadata and its compatibility limits are documented in the
[Ports guide](mpm-ports.md); `mpm(1)` is maintained in the repository and bundled
with manual-enabled System builds. Base/System/Kernel areas remain unimplemented.
System release and deployment formats require separate evaluation, including
compatibility between the selected System's MPM and persistent metadata.

## Accepted early Nix/System policy (2026-10-23)

The owner approved the following policy after the three-step System VM run:

- Keep the Nix CLI exposed in early Mojt versions for direct administration
  and experimentation.
- Use Nix for System packages for now, with System and Ports sharing the Nix
  store and its object/reference database.
- Keep System generation selection, service configuration and activation
  under Mojt control. A direct Nix profile change is not a Mojt System update.
- Describe host-service requirements separately in MPM, for example a
  requirement for a compatible logind service on the system D-Bus.

The shared database records exact store objects and references; it is not the
authority for the active System generation or MPM's area policies. System and
Ports retain separate manifests/catalog choices and activation state. One
immutable object may satisfy references from both areas. A different build
identity remains a different object even if its package name/version matches.

File dependencies and host capabilities are distinct. Nix supplies a port's
exact library closure, reusing already registered System objects when their
identities match. A library from systemd does not by itself establish that
logind is available, and installing a service's files does not configure or
activate that service. Mojt must describe and verify the capabilities required
by the port; it must not claim a host capability from a package name alone.

This is an interim backend choice, not adoption of NixOS or a final System
release format. The current experiment already shares registered objects,
roots System content and uses Mojt-owned activation. Host-capability metadata
and enforcement, supported direct-Nix operation boundaries, and reconciliation
of changes outside MPM remain implementation/design work. Root can bypass
ordinary file protections; the exposed CLI is not an MPM authorization boundary.

## Ports direction

Ports should support:

- multiple installed versions and version-specific dependencies;
- profiles that activate selected versions via links or a similarly simple mechanism;
- project lockfiles that protect compilers and build dependencies from ordinary updates;
- native execution by default for ordinary command-line tools;
- optional security sandboxes for programs or build processes where useful.

Nix supplies the Ports store and dependency objects; MPM owns Mojt's user-facing
selection and activation policy. The narrow adapter has passed real Distrobox
imports and parallel-version tests, followed by hello and parallel-Python
acceptance inside the booted Mojt VM.
See [the Nix experiment](mpm-nix-experiment.md).

## First System implementation

The owner approved three incremental steps: systemd boot with persistent state,
NetworkManager/D-Bus networking, and MPM/Nix imports inside the booted VM.
All three initial steps passed on the owner's Mojt VM. See
[the System experiment](system-nix-vm.md) for preparation/build support,
recorded real acceptance and remaining integration limits.

The experiment obtains System binaries from the same pinned Nixpkgs source
and keeps them separate from Base. A System profile supplies unit files and
runtime tools; persistent machine configuration retains precedence. Nix/MPM
and their management runtime belong to System. The initial root-operated
binary-import test is not a production package-manager service/permission model.

## Accepted interactive System shell (2026-10-24)

After successfully installing interactive Bash through MPM in the running VM,
the owner approved including it in System. Step 5 uses `bashInteractive` from
the same pinned Nixpkgs source. Bash supplies the interactive console shell;
Base's `/bin/sh` retains its POSIX script role and recovery use.

The VM builder can explicitly select `/run/mojt-system/bin/bash` in the new
VM's copied root account. It does not silently rewrite an existing account
choice or modify the source installation. Mojt supplies an interactive prompt,
editing/history defaults and private root history in persistent `/var`.
Existing local startup files retain precedence. See [System Bash](system-bash.md)
for the build recipe, validation and serial-terminal limitations.

## Accepted initial disk boot (2026-10-24)

The owner approved UEFI/GPT/GRUB, keeping the first image simple with one boot
entry and the already tested kernel source. Opt-in `--boot-mode uefi` now
builds a regular GPT image with a FAT32 EFI partition and the Mojt ext4
partition. A standalone GRUB EFI loader lives at the fallback path; the build
does not run host `grub-install`, change NVRAM or use loop devices/mounts.

The disk owns a versioned kernel/initramfs pair and an input-hash record.
Early init locates ext4 by UUID and pins the exact System generation named by
that boot pair, including System identity reads. It does not follow a changed
`system/current`. QEMU supplies firmware and a private variable file, without
external kernel/initramfs arguments. Direct-kernel mode remains a diagnostic
path. See [disk boot](uefi-disk-boot.md) for construction and acceptance.

A real synthetic static-guest probe passed firmware boot, repeat boot with
persistent state and disk-only transfer to fresh firmware variables. On
2026-10-24 the owner also reported the final Mojt disk-copy boot test working
after creating the copy in their home directory. Individual UEFI service,
network, Ports and history-check logs were not supplied. This first image
build does not implement a System updater, automatic fallback or state rollback.

## Explicitly unresolved

- Source-based/self-hosted Base build and verifiable reproducibility
- Signature verification and trusted release channels
- Crash-safe activation and `fsync` durability guarantees
- Production boot selection/deployment, complete shutdown storage detachment,
  and kernel/module release/versioning policy
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

The earlier boot prototype uses a **System-owned static BusyBox init**,
provided by the image builder in `system/prototype-init` and made available
under `/run/mojt-system` at boot. BusyBox init supervises the serial console
and provides a minimal poweroff path. This is **development-only**: BusyBox
is suitable for the prototype, rescue media and embedded contexts, but it is
**not** the planned permanent init for the Mojt distribution. The current
System experiment has verified systemd as PID 1; BusyBox remains an early-boot/rescue tool.

Account databases (`/etc/passwd`, `/etc/group`, `/etc/shadow`) are persistent
machine state. The earlier development console bypasses login entirely.
The builder also supplies authenticated password mode and host-side credential
provisioning, described below and used in the accepted System VM runs.
Production installer/account policy remains open. Never install a universal
default password or overwrite existing machine credentials.

## Experimental System console login (not production authentication)

The VM prototype may use a static BusyBox `getty` and `login` from
`system/prototype-init` (legacy) or the selected versioned System profile,
separate from Base, to authenticate the local
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
