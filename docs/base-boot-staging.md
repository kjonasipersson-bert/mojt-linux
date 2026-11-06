<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Exact Base boot staging and selection

Implemented experimental subset, extending the accepted serial native-disk
Kernel constructor. This does not implement the draft generalized v2 deployment
protocol or native System installation. It retains the selected measured System
manifest/generation and exact Kernel. Native System artifact composition remains
a later integration gate; no substitute identity is invented.

```
mpm base stage --artifact sha256:FULL_BASE_ID \
  --base-context candidate-base-context.json --dry-run
mpm base stage --artifact sha256:FULL_BASE_ID \
  --base-context candidate-base-context.json -y
```

Use an already installed and verified Base. The explicit context must bind its
full artifact ID/release and inclusive numeric Kernel bounds. Checkout/offline
use requires `--disk-root DIR` and, for an original unmanaged native image,
`--baseline boot/mojt/SYSTEM/BASE`. The installed frontend derives only its own
mounted installation and exact original baseline; an explicit offline target
never borrows that runtime evidence. The retained System must contain the matching
closed management/constructor code, static BusyBox and retained GNU tar helper.
Prepare a fresh System payload to test this code; an older System is not upgraded
silently by a checkout invocation.

## Supported state/defaults boundary

Staging performs no persistent configuration or schema changes. This first
subset requires every candidate default to have an existing destination already.
Existing local content and type conflicts are preserved; state symlinks are not
followed. A missing default blocks with its relative path. No package hooks are
executed. Durable add-missing lifecycle preparation remains an explicit follow-up,
not a partially hidden installer action. Candidate ABI, state, Ports and account
shell checks remain those of the preflight; runtime libc compatibility is not
proven or repaired.

## Immutable construction and publication

The installed Base realization is never modified. A private directory is extracted
from its retained audited archive, preserving Unix ownership, modes, links,
xattrs/ACLs and hardlink topology, then compared with the complete installed
inventory. Only the previously reviewed empty mountpoint scaffolding may be added.
The boot copy lives at `boot/mpm/slots/SLOT_HEX/tree/rootfs`, behind a root-owned
0500 container so ordinary users cannot alter writable Unix directories before
boot. Early boot binds that exact slot tree read-only, independently binds the
exact native Kernel modules read-only, and mounts persistent state separately.
No version-label Base alias or `base/current` lookup chooses the runtime tree.

The versioned `mojt-base-boot-inputs-v1` sidecar binds the installation's Base
receipt/realization, original/assembled inventories, preflight, exact retained
System/Kernel, constructor files, BusyBox, extractor and generated initramfs
inventory/early modules. Existing deployment/binding v1 identities still bind
Base/System/Kernel and actual archive bytes. These are measured content identities,
not signatures or an implementation of the draft native-v2 loader.

Acquire the union of existing Base/store/Kernel/Ports/boot locks in deterministic
order and revalidate inputs immediately before publication. Complete and flush
the tree/sidecars/images, then rename the slot as one unit. Failure before that
rename removes only the private staging directory. A flush failure after rename
retains the possibly published complete slot and reports uncertainty. Exact
repeats verify and reuse retained output; concurrent repeats recheck under locks.

Staging does not change the GRUB menu, next boot or running deployment. Empty
cooperating boot/Ports lock infrastructure may be initialized. It creates no
requests, active Ports profile, configuration defaults or Base current pointer.
The result is ready for a future selection operation, with boot acceptance still
pending. Existing `mpm kernel select` refuses to use a Base-changing candidate as
a Kernel-only update.

## Validation and next gate

Focused tests cover real archive construction and frontend preview, exact
Base/System/Kernel binding, generated read-only mount logic, preserved state and
next boot, no-op repeats, missing defaults/management, corruption, late input
changes and publication uncertainty. Real root cases run in CI. Synthetic guest
files are not a successful VM boot.

Base next-boot selection/return and joined installed/next/running status are now
implemented. Run the [focused owner acceptance](base-boot-acceptance.md) on a
fresh disposable native image, then retain its evidence before merge. No repeated
Kernel/hardware matrix is requested.


## Exact Base selection and return

```
mpm base select --deployment sha256:FULL_DEPLOYMENT_ID \
  --expected-selected sha256:CURRENT_DEPLOYMENT_ID --dry-run
mpm base select --deployment sha256:FULL_DEPLOYMENT_ID \
  --expected-selected sha256:CURRENT_DEPLOYMENT_ID -y
mpm base rollback --expected-selected sha256:CURRENT_DEPLOYMENT_ID -y
mpm base status --json
```

Both selected recovery and candidate content, management/state capabilities and
account shell paths are rechecked before publication. A Base-only selection must
retain exact System, Kernel, platform, root filesystem UUID and console policy.
The expected selected deployment is mandatory, so a stale preview cannot replace
a later choice. A repeated choice verifies the same inputs and publishes nothing.
Rollback selects the previous deployment only when it has the same System/Kernel;
a history entry changing another layer needs that layer's explicit scope.
Neither action reboots or changes the running deployment.

The new `mpm-base-boot-selection-v1` menu has a distinct recognized header. It
retains exact entries from different Bases/Kernels with the same System and disk,
and commits the full metadata and generated loader entries through one atomic
menu replacement. The original Kernel-only menu format keeps its exact-Base
constraint. The existing boot registry marker still describes the retained slot
layout; it does not cause an unrecognized menu to be adopted. Unknown formats or
mismatched generated content fail closed. This is a bounded v1 extension, not the
draft generalized v2 System-composition protocol.

A Kernel update after a Base-slot deployment reuses its exact measured Base boot
tree via the explicit `base_tree` dependency in the retained input receipt. Its
new initramfs loads that tree rather than `base/RELEASE`. The dependency is retained
alongside the slot and must be honored by any future collection implementation;
no physical collection is performed here. Kernel-only selection still preserves
Base/System, and Base-only selection still refuses a Kernel change.
