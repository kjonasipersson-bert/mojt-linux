<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt development priorities

Updated 2026-10-26. This records the agreed order and measured progress;
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
- System step 7 diagnostics passed on both retained kernels, including the\n  corrected udev hardware database, network checks and the same Ports artifact.\n- A clean step 8 VM completed A → B → A with automatic persistent machine-ID\n  commitment, retained journals across all three boots, confirmed NTP, quiet\n  login consoles and an explicit working terminal-size query.\n- Authenticated full-Mojt serial console in the SSH terminal, retaining the
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
| 2 | More complete System | Diagnostics and console/time/journal acceptance completed. Next: persistent timezone, locale/UTF-8 checks and man/manual-page integration, then decide and implement the account stage from the [System proposal](system-completeness-proposal.md). |
| 3 | MPM development | Implement the accepted upgrade policies, explicit request/selection state and readable history; develop project locks, then retention/pruning and physical collection. |
| 4 | Build System on Mojt | Run the existing build tools inside Mojt with pinned inputs and a controlled build environment, producing a new Mojt image. |
| 5 | Own-built Linux kernel | Establish a documented kernel build/configuration and package matching modules as a versioned Kernel input; start near the working Debian configuration. |

MPM work continues alongside System integration where needed. The current
working Debian kernel remains the reference while the build/deployment chain
is developed; an own-built kernel follows the earlier generation and
self-building milestones.

## Next concrete work: System completeness

The different-kernel experiment is now recorded in
[owner acceptance](boot-generations.md#owner-different-kernel-acceptance-2026-10-26).
Keep its two boot choices and the earlier completed VM as reference inputs.

The [System completeness proposal](system-completeness-proposal.md) recommends
the now-completed diagnostic and console/time additions, small remaining\ntimezone/locale/manual-page improvements, and a separate coherent account stage. It covers local Unix users, persistent homes,
PAM/session integration, sudo, service identities and initial administrator-managed
shared Ports. Personal Ports and optional SSH are later steps. These are
recommendations for discussion, not accepted policy or implemented capabilities.

## Implementation boundaries

The current MPM CLI implements a subset of Ports commands. It does not yet
provide `upgrade`, Base/System/Kernel operations, release-series selectors,
readable transaction history, general undo, production project locks or GC.
System release/deployment schemas, independent Kernel selection, compatibility
enforcement and production boot publication/fallback remain work to specify
and implement. Future status/plans must show installed, selected and running
content, directly selected components, dependencies and exact changes.

