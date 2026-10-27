<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt development priorities

Updated 2026-10-27. This records the agreed order and measured progress;
future commands and policies are not claims of implemented functionality.
The [architecture](architecture.md) defines the layer boundaries and the
[MPM contract](mpm.md) records the accepted update semantics.

## Completed foundation

- Whole-image Base packaging, side-by-side installation and return to an
  earlier Base, with persistent configuration/state preservation.
- A bootable System with systemd, networking and usable Nix-backed Ports.
- A full Mojt VM generation sequence A/A → A/B → B/B → A/A, with explicit
  Base/System boot selections and shared persistent markers. Base B was
  intentionally ABI-compatible; both System labels used the same Debian
  kernel and upstream System payload.
- A second full Mojt VM experiment completed kernel/module switching
  `6.12.107+deb13-amd64` → `7.2.9+deb13-amd64` → `6.12.107+deb13-amd64`,
  keeping Base 0.1.3 and System userspace fixed, with persistent markers,
  networking and the same installed Ports hello artifact. B identity/marker/HTTPS
  checks were owner-confirmed; see the evidence distinction in the acceptance log.
- System step 7 diagnostics passed on both retained kernels, including the
  corrected udev hardware database, network checks and the same Ports artifact.
- A clean step 8 VM completed A → B → A with automatic persistent machine-ID
  commitment, retained journals across all three boots, confirmed NTP, quiet
  login consoles and an explicit working terminal-size query.
- Authenticated full-Mojt serial console in the SSH terminal, retaining the
  tested VM's credentials and state.
- Controlled interruption of a fresh image build at password entry, successful
  return to the completed VM, and a repeated probe confirming no published
  interrupted output and an unchanged completed VM disk checksum.
- Accepted update policy: Base is one complete release; a content-changing
  System upgrade creates a new immutable generation; Ports recovery uses
  individual versions/activation and readable history without requiring
  user-managed whole-Ports generations.

See [generation acceptance](boot-generations.md) and
[serial/interruption acceptance](vm-serial-console.md) for evidence and limits.
Fresh-image assembly and controlled abort checks do not establish durable
updates to an existing boot disk or power-loss recovery.

## Work order

| Priority | Track | Next work |
| --- | --- | --- |
| 1 | Base/System generations | VM Base/System and different-kernel return experiments completed. Retain the reference images; production boot-disk updates, compatibility and automatic fallback remain future work. |
| 2 | More complete System | Diagnostics and console/time/journal acceptance completed. Timezone/UTF-8/manual checks accepted on System A; separate A/B checks deferred to the next stage. The account A/B/A run now preserves new users, identity and home data, with working PAM/sudo, session cleanup and shared Ports. Superseded-password rejection is owner-confirmed. Account integration merged; retain its reference image. |
| 3 | MPM development | PR #23 merged after real two-snapshot Nix upgrade/recovery and Mojt VM A/B/A acceptance. Next increment: backend-independent selector parser/resolver and read-only catalog inspection, followed by installation/alias integration with explicit state conversion. Libc integration is deferred; preserve opaque dependency identities. System deployment compatibility follows; project locks precede pruning/GC. |
| 4 | Build System on Mojt | Run the existing build tools inside Mojt with pinned inputs and a controlled build environment, producing a new Mojt image. |
| 5 | Own-built Linux kernel | Establish a documented kernel build/configuration and package matching modules as a versioned Kernel input; start near the working Debian configuration. |

MPM work continues alongside System integration where needed. The current
working Debian kernel remains the reference while the build/deployment chain
is developed; an own-built kernel follows the earlier generation and
self-building milestones.

## Next concrete work: MPM selectors and runtime identity

The Ports upgrade/history/manual block is merged. The owner verified real Nix
hello 2.12.1 -> 2.12.3, following and exact selections, recovery and a fresh
Mojt A/B/A run retaining state/history, users and the same artifact.
See [the measured acceptance log](mpm-ports.md).

The next proposals are [selectors and catalogs](mpm-selectors.md) and
[mixed Nix libc closures](mpm-libc-policy.md). The selector branch
implements a pure parser/resolver and read-only CLI. The remaining proposals
cover installation/activation integration, explicit state conversion and same-release build changes. Libc work is deferred.
A new libc object is a dependency of a concrete consumer build, not a
machine-wide activation choice. Known gaps and the required real-runtime evidence are explicit. No installed-state
migration, selector installation/activation, libc replacement or System-upgrade
command is implemented in this resolver increment.

Keep the latest tested reference VM. Optional SSH, personal Ports, running
the build on Mojt and an own-built kernel remain later tracks.

## Implementation boundaries

The current MPM CLI implements a subset of Ports commands. It does not yet
provide Base/System/Kernel operations, selector-based installation/activation,
general undo,
production project locks or GC. The first Ports upgrade/history implementation
uses saved Nix attributes, numeric version ordering and format-2 request/policy
metadata. Its real Distrobox/VM acceptance passed; full series/version
adapters and mixed-runtime compatibility checks remain future work. The current
selector implementation is read-only resolution plus a pure upgrade plan.
System release/deployment schemas, independent Kernel selection, compatibility
enforcement and production boot publication/fallback remain work to specify
and implement. Future status/plans must show installed, selected and running
content, directly selected components, dependencies and exact changes.
