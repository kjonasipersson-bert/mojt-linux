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
| 1 | Establish the baseline and deliver complete MPM in System | Common frontend/runtime is merged. Configuration ownership, exact resolution and a complete Ports publisher/acquisition API are implemented in #36. Completion still needs the actual installed frontend to join configuration, sources, planning, imports and supported area operations without a checkout. |
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

The Python core has real filesystem/executable publication tests; Nix subprocess
protocols have simulated tests, not live import acceptance yet. Next join: connect
these fresh-store APIs to the existing installed frontend and System delivery,
accepted sources and ordinary operations, then run one live provider acceptance.
Native Port archive acquisition and non-Ports reconciliation remain explicit
work. No legacy conversion or invented public command syntax is required.
Preserve the same provider-independent transaction boundary for Base/System.

Progress reports must name the step, implemented behavior, validation and the
remaining gate. Unit tests, schema checks and prior experiments do not mark a
whole milestone complete. No new public command syntax is implied by this plan.
