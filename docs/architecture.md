<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt architecture

Mojt separates release-owned code from machine-owned state. Base, System and
Ports have independent lifecycles; Kernel has its own MPM selection scope within
the operating system. The [manifesto](manifesto.md) describes the design goals.

## Layers

| Area | Responsibility | Update unit |
| --- | --- | --- |
| Base | Small glibc-based Unix userspace, utilities, libraries and release defaults | Whole immutable release |
| System | systemd, networking, accounts, services, administration and management tools, firmware and retained runtime dependencies | Coherent immutable generation |
| Kernel | Kernel image and matching version-specific modules | Exact build |
| Ports | Applications, libraries and toolchains | Parallel installed versions and active command choices |
| State | Configuration, databases, homes and local files | Persistent machine data |

Base contains no Kernel, init, desktop or Python requirement. System supplies
MPM's Python runtime and uses systemd as PID 1. Static BusyBox supplies early boot,
recovery and final shutdown, independently of the interactive System shell.

## Base and System compatibility

Base and System should normally combine within their actual ABI/capability
requirements, rather than being released as compulsory matched pairs. A System
binary using Base's libc can require a newer ABI than an older Base provides.
A retained provider closure with its own libc does not acquire that Base-libc
dependency merely by belonging to System. Kernel capabilities, modules and
supported persistent-state formats can impose additional requirements.

The [libc runtime map](mpm-libc-policy.md) describes Base and retained provider
ownership, the distinction between compiler and target runtimes, and shared
configuration/module boundaries.
The [version 1 runtime contract](libc-contract.md) defines the decided ownership,
locale/data and retention requirements, with pending implementation marked.
The [integration resource map](libc-integration.md) distinguishes machine-owned
configuration, System services, runtime-owned modules/data and future SDK/GC
requirements.

Exact boot references record repeatable **choices**, not a dependency on exactly
those release versions. Preparation constructs a requested supported combination;
it does not build every possible cross-product of retained releases. Unsatisfied
requirements are reported rather than silently replacing another area.

## Installed, prepared, selected and running

Installed content is retained on disk. A prepared deployment includes an admitted
Kernel/initramfs slot and exact Base/System/Kernel bindings. Next boot is an
atomic selection of a completed deployment. Running identifies what actually
booted, independently of a pending next-boot choice.

On a live native-v2 installation, normal public System and Base installation
also prepare an entry using the selected context. They leave next boot unchanged.
`--content-only`, explicit offline targets and low-level import APIs keep content
import separate. Kernel installation still requires explicit preparation.
`stage` remains an advanced operation and internal API, not a mandatory extra
command after normal live System or Base installation.

Activation selects prepared content, with a concrete change/reboot preview. It
does not construct initramfs, scrub payloads, switch running services or reboot.
Explicit `--verify` requests full audits. A content-changing System update retains
previous generations for recovery. Retained generations are not upgrade wishes.
Moving-policy boot-area upgrades and general service/schema migrations remain
unimplemented. The current System transition gate permits reviewed tooling
changes while preserving startup/services and provider dependencies.

See [MPM operations](mpm.md#2-operations), [boot update behavior](system-transition.md)
and [native-v2 selection](native-system-selection.md).

## Ports and providers

Ports keeps independent configuration and interactive wishes, exact accepted
references, active choices and transaction history. Additional versions preserve
an existing active default. Following choices may advance with their upgrade
wish; exact pins remain fixed. Activation affects new program starts, not
already-running processes. Atomic internal profiles are implementation records,
not a user requirement to manage a generation of every application together.

Nix currently supplies System/Ports binaries and dependency objects in a shared
store. MPM owns the logical area model, requests and selection policy. Provider
closures used by retained System profiles remain immutable during normal use.
Core native Base/System/Kernel artifact operations do not require Nix unless
the particular content declares a Nix dependency.

Ports manuals follow active exact application versions, including separate
provider manual outputs. The System's `man`/`manpath` wrappers compute the search
path at invocation. [The Ports guide](mpm-ports.md) covers usage.

## Configuration and persistent filesystems

Native-v2 handover mounts persistent `state/rootfs` as writable `/` and projects
selected Base trees/files read-only. `/usr/local` has a separate persistent
`state/local` bind. `/etc`, `/var`, `/home` and `/root` retain their own machine
state. Local `/opt`, `/srv` and administrator-created root paths survive
compatible generation changes. `/run` and `/tmp` are temporary filesystems.

Initialization happens on first boot of this layout, not during preparation.
An installation/projection marker prevents silent adoption of an unknown root,
reserved-alias changes, unsafe mountpoints or incompatible Base top-level
layouts. Existing entries retain their embedded boot code: older read-only-root
entries do not gain the new mount behavior just by being selected.

Release defaults live under `/usr/etc`; existing persistent configuration is not
silently overwritten or removed. `/etc/os-release` is a relative link to Base's
`/usr/lib/os-release`. Returning to older code does not revert databases, machine
configuration, local software or user files. Read the
[filesystem/persistence tables](../doc/handbook/part-iii/filesystem-layout.md)
and [handover contract](native-system-handover.md).

## Building and distribution

MPM handles installed content and choices. MBT coordinates explicit build
workspaces, tool environments, Kernel builds, packaging and fresh native-v2 image
bootstrap. Void with static XBPS is a Base bootstrap backend; it is not a runtime
package-manager commitment. Provider recipes and binaries are construction inputs,
not the definition of Mojt's release format.

Native artifacts describe content, dependencies, platform, version and integrity.
Local source policies and hashes do not authenticate a remote publisher. Signed
release distribution, alternative bootstrap backends, complete native source
self-hosting, generalized migrations and wider hardware coverage remain open.
See the [artifact format](native-artifact-format.md), [MBT chapter](../doc/handbook/part-i/mbt.md)
and [roadmap](roadmap.md).
