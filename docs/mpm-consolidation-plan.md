<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MPM consolidation: governing six-step plan

Owner-confirmed 2026-11-01. This is the governing implementation order.
The detailed [gap matrix](mpm-gap-matrix.md) and format specifications support
these milestones; neither separate experiments nor new format documents replace
the full installed-machine goal. Target fresh installations with explicit format
versions, not backward migration of experimental installations.

| Step | Goal | Current evidence and remaining completion gate |
| --- | --- | --- |
| 1 | Establish the baseline and deliver complete MPM in System | Common frontend/runtime is merged. Configuration ownership, exact resolution and a complete Ports publisher/acquisition API are implemented in #36. The installed Ports frontend now joins configuration, accepted finite sources, imports and profiles without a checkout. A bounded real Nix adapter/frontend acceptance passed. Interactive reason removal and active-choice reset are implemented in the bounded follow-up. Completion still needs supported Base/System operations, remaining request/configuration joins and honest diagnostics. Local native source/cache acquisition is implemented; general authenticated remote publication remains the separate P2 gate. |
| 2 | Consolidate installation and transaction rules | Shared locks/publication primitives are merged; late baseline guards and the fresh Ports profile publisher are added here. Complete other area publishers, lifecycle effects and failure recovery; planning alone is not a transaction commit. |
| 3 | Make Base and System actual MPM installation units | Package/composition/storage/deployment contracts exist; implement verified import, complete realizations, scope-preserving publication and next-boot selection on the same disk. |
| 4 | Build bootstrap on those functions | Reuse the same MPM acquisition/install/deploy libraries for explicit new targets; no second installer or experimental-script-only path. MBT syntax remains a separate discussion. |
| 5 | Integrate environment, Kernel build and packaging | Prior real builds/boot experiments exist. Join exact environment retention, ordinary-user builds, native packaging and normal MPM install/select without global compiler/libc changes. |
| 6 | One joined acceptance flow, then hardware | Prove the delivered tools administer the installation, update Base/System, build/install/boot a Kernel and recover with state retained. Then accept a supported physical profile; do not repeat unchanged component cross-products. |

## Current bounded increment: Ports resolution through publication

PR #36 belongs to steps 1 and 2. `mpm_requests.py` owns versioned declarative
and interactive wishes; `mpm_request_plan.py` joins them to the shared resolver
and explicit adapter bindings. `mpm_ports_profile.py` now joins exact acquisition,
physical verification, complete profile/alias assembly and request/history
publication through one atomic pointer. `mpm_nix_binary.py` is its first production
binary-output adapter. See [implementation and limits](ports-profile-implementation.md).

The fresh APIs are now [connected to the installed frontend and System delivery](ports-cli-integration.md).
`update` preserves accepted targets, `upgrade` advances only its explicit moving
wish scope, and exact full-build pins survive catalog withdrawal. Ports-only
configuration apply, installed-evidence activation and linked history use the same
publisher. Source inputs are explicit content-identified finite bundles; no implicit
remote refresh or experimental-store migration is provided.

Filesystem and installed-copy tests exercise this join. The
[owner-run real Nix adapter/frontend acceptance](ports-profile-acceptance.md) passed
on 2026-11-01 at code revision `40ee0f2`, including registered roots and unchanged
repeat installation/history. The bounded [remove/reset follow-up](ports-remove-reset.md) releases interactive
reasons and returns active control to adopted configuration without acquisition.
Next gate: remote source acquisition, artifact-only pruning/configuration forgetting
and native Port support.
Non-Ports reconciliation and lifecycle/recovery remain explicit work. Preserve the
same provider-independent transaction boundary for Base/System.

## Next bounded increment: native source acquisition and cache

The [local native source/cache library](native-source-cache.md) adds actual verified
archive acquisition for Base, System, Kernel and Port without a provider dependency.
It joins accepted source/snapshot/catalog/acquisition records to a separately
protected owner policy, a read-only exact plan and no-overwrite cache publication.
Real synthetic tar/zstd tests exercise all categories and failure/retry boundaries.
The library and source/cache commands ship in System. Named registrations, explicit
metadata refresh and exact fetch now use frozen snapshots. The first
[source-to-install join](kernel-source-install.md) connects them to the existing
Kernel publisher, with shared eligibility, retained origin evidence and separate
boot selection. The bounded owner VM acceptance passed on 2026-11-06 at
source revision `386b204`, using the installed runtime and a real package; see the
[recorded evidence](kernel-source-install.md#owner-installed-system-vm-acceptance-2026-11-06).
PR #38 passed full CI and merged. Base/System and native Ports installation integration
remain pending. See [source runtime integration](source-runtime-integration.md).
Local owner trust does not implement
remote authentication or signing. This advances steps 1 and 2; it does not mark
MPM complete or displace actual Base/System installation in step 3.

## Following bounded gate: source-installed Kernel to native boot

PR #38 passed full CI and owner installation acceptance, then merged. The
[native boot follow-up](kernel-source-boot.md) retains acquisition origin during
fresh-image copying and candidate staging, with mandatory v2 input-receipt binding.
It also makes the fresh MPM state parent part of System assembly. The owner
accepted one exact source-installed deployment boot on 2026-11-06 in a separate
native image at `0dd0b40`, retaining source origin, read-only modules, Base/System
and machine identity, with selected/running IDs agreeing and no failed units.
Existing build/package inputs were reused. Installation, staging, selection and
reboot remain separate actions. This continues steps 1–2 and supports the later joined
acceptance milestone; it does not complete Base/System installation or bootstrap.

## Immediate review gate: Base installation and inspection

Following merged #39 and its accepted source-installed Kernel reboot, the owner
requested review of MPM/MBT documentation before Base implementation. The
[shared user model](management-workflow.md) and
[Base install/status proposal](mpm-base-contract.md) are that review surface.
They propose complete exact Base retention plus a validated runtime tree, no
implicit defaults/state/boot changes, and separate installed/next-boot/running
inspection. The owner agreed to these meanings on 2026-11-06. The first
[exact import/realization/status implementation](base-installation.md) is in PR #40;
Base boot selection and System integration remain later gates.
MBT's final spelling remains deferred and it must reuse this installation model.

Complete review/CI for content-only Base import/realization/status, then
generalize deployment to a changed Base, followed by System integration.
The next owner VM gate is an actual changed-Base boot. Do not add another manual
Kernel matrix or move bootstrap/build work ahead of the six-step order.

Progress reports must name the step, implemented behavior, validation and the
remaining gate. Unit tests, schema checks and prior experiments do not mark a
whole milestone complete. No new public command syntax is implied by this plan.

