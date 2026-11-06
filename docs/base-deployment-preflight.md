<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Base deployment preflight

This is an internal, read-only integration increment toward changed-Base
staging. `mpm_base_transition.prepare` inspects an existing native disk and a
completely installed Base. No new MPM or MBT command is introduced. Base install
and status keep their agreed meanings; installation alone does not select a boot.

## Verified inputs

The preflight verifies the current published boot selection, its retained System
manifest/content and exact installed Kernel, and the candidate Base wrapper and
realized rootfs. It uses the selected deployment as the baseline, which need not
be the running deployment. The existing System is identified by its measured
manifest and generation; a native System artifact is not invented.

Candidate architecture, explicit ABI declarations and state-layout requirements
come from its retained release manifest. Kernel bounds must explicitly name that
exact candidate Base artifact, including a finite maximum. The selected Kernel's
verified upstream version is checked against those bounds. Neither the old Base's
ABI/bounds nor an automatic Kernel upgrade is substituted.

Persistent state is observed directly: layout marker, passwd account shell paths,
current fresh Ports profile/capabilities and the supported relative os-release
link. System-owned account shells must remain exported by the retained System;
Base-owned shells must exist and be executable within the candidate rootfs.
Guest absolute symlinks are resolved within that rootfs, never on the inspector.
A local regular os-release file or unsupported layout blocks this path without
changing configuration. This is deliberately not a state migration implementation.

## Evidence and limits

The versioned `mojt-base-transition-preflight-v1` record binds the target,
installation UUID, menu digest, baseline deployment, exact candidate receipts and
inventory, System/Kernel identities, observed state and compatibility report.
Existing cooperating locks are held for reads without creating absent locks.
The observed inputs are checked again before returning evidence. `recheck`
recomputes that evidence and refuses stale inputs.

This record is not a saved execution plan, an approval token or permission to
publish. Future writers must initialize/acquire all required locks exclusively
and recheck their inputs through publication. Account/configuration changes by
other tools still require coordination at that later boundary.

`declared_compatible` means only that the implemented declarations and account
shell checks pass. It is not runtime libc compatibility, arbitrary state-schema
compatibility or boot readiness. Candidate code is never executed. Existing
conservative System ABI equality checks remain unchanged.

All records explicitly report `writes=false`, `stage_ready=false` and
`boot_ready=false`. Remaining gates are explicit defaults/lifecycle preparation
and management/state capabilities, a newly bound initramfs and complete deployment
publication, then explicit next-boot selection and owner boot acceptance. The
final generalized deployment format remains a separate contract; this record
does not claim to implement it.

## Validation and next owner test

Focused tests cover candidate ABI/bounds, exact System/Kernel retention, actual
state and shell checks, verified native-disk evidence, stale/corrupt inputs and
absence of target writes. Root archive cases run in CI alongside existing Base
and System delivery regressions. Synthetic declarations do not publish real Base
compatibility bounds.

No additional manual VM matrix is needed for this internal read-only increment.
The next owner VM gate is an actual changed-Base boot retaining System, Kernel,
identities, state and Ports, followed by return to the previous deployment.

## Implemented staging follow-up

The [Base staging subset](base-boot-staging.md) now constructs a complete private
Base boot tree and bound initramfs from this evidence, and publishes them as one
retained slot. The preflight record itself remains read-only and never confers
publication authority. Explicit Base selection/return is now implemented as a separate action. Owner
changed-Base boot acceptance remains pending.
