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
| 1 | Base/System generations | Extend the successful experiment to a genuinely different kernel and its matching modules, then return to the retained working combination. |
| 2 | More complete System | Add small missing administration/network tools, including ping. Treat ordinary users as a separate design step covering home persistence, administrative privileges and shared/personal Ports use. |
| 3 | MPM development | Implement the accepted upgrade policies, explicit request/selection state and readable history; develop project locks, then retention/pruning and physical collection. |
| 4 | Build System on Mojt | Run the existing build tools inside Mojt with pinned inputs and a controlled build environment, producing a new Mojt image. |
| 5 | Own-built Linux kernel | Establish a documented kernel build/configuration and package matching modules as a versioned Kernel input; start near the working Debian configuration. |

MPM work continues alongside System integration where needed. The current
working Debian kernel remains the reference while the build/deployment chain
is developed; an own-built kernel follows the earlier generation and
self-building milestones.

## Next concrete experiment: a different kernel

Retain the completed VM as the recovery reference. Prepare a second, exact
kernel input with its matching modules and appropriate firmware, keeping
Base and System userspace inputs unchanged so the kernel change is clear.
Compose a fresh image with retained old and new boot choices. The current
builder may use separate System labels to bind those different kernel inputs;
this does not finalize the future public Kernel/deployment identity format.

Use the serial console to verify each selected combination's Base, System,
kernel release, exact recorded boot inputs, login and persistent markers,
then return to the earlier combination. Separately verify networking and an
installed Ports command across the transitions; those checks were not
established by the earlier generation run. Preserve the original USB and
completed VM images during this experiment.

## Implementation boundaries

The current MPM CLI implements a subset of Ports commands. It does not yet
provide `upgrade`, Base/System/Kernel operations, release-series selectors,
readable transaction history, general undo, production project locks or GC.
System release/deployment schemas, independent Kernel selection, compatibility
enforcement and production boot publication/fallback remain work to specify
and implement. Future status/plans must show installed, selected and running
content, directly selected components, dependencies and exact changes.
