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
| 1 | Establish the baseline and deliver complete MPM in System | Common frontend/runtime is merged. Configuration ownership, exact resolution and a complete Ports publisher/acquisition API are implemented in #36. The installed Ports frontend now joins configuration, accepted finite sources, imports and profiles without a checkout. Completion still needs live provider acceptance, source acquisition/removal/reset and supported Base/System operations. |
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

Filesystem and installed-copy tests exercise this join; Nix subprocess protocols
have simulated tests, not live import acceptance yet. Next gate: one live provider
acceptance, then complete source acquisition/removal/reset and native Port support.
Non-Ports reconciliation and lifecycle/recovery remain explicit work. Preserve the
same provider-independent transaction boundary for Base/System.

Progress reports must name the step, implemented behavior, validation and the
remaining gate. Unit tests, schema checks and prior experiments do not mark a
whole milestone complete. No new public command syntax is implied by this plan.
