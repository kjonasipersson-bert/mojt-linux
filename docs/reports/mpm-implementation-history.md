<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MPM implementation-status history

Historical excerpts from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
These status and acceptance notes are not the current operation contract.

<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt Package Management Contract

**Status:** accepted design contract with a partial experimental implementation.
The repository frontend implements a subset of Ports operations, named local
sources/cache, exact local/source Kernel installation, native Kernel boot
management and read-only catalog discovery;
the commands below
are design examples unless identified as implemented in section 6. This
document records the update model accepted on 2026-10-26 and the previously
accepted high-level selector semantics:
`@3.0` selects the newest eligible stable release in the 3.0 line, while
`@=3.0` matches an exact package-release identifier. The selector branch specifies and implements the initial grammar and
dotted-numeric adapter; other version schemes remain exact-only. Nix is selected for Ports and, for early Mojt
versions, for System package acquisition and shared dependency storage.
System release/deployment formats and the full command grammar remain open.
The current Ports frontend uses independent configuration/interactive wishes
and complete profiles; older format-3 adoption belongs to the separately invoked
prototype. The [selector/catalog contract](../mpm-selectors.md) records the original
grammar and integration history. See section 6 for the current delivered path.
The [mixed-libc analysis](libc-policy-proposal-2026-10.md) is deferred reference work. Linking
a proposal here does not make its remaining details accepted or implemented.

The guiding rule is that Mojt can update **Base, System, Kernel, and Ports
independently**, without silently updating applications or pinned project
toolchains during an operating-system update. `mpm` is the stable user-facing
front-end; it need not implement its own general dependency solver or use the
same backend for every area.

See [the manifesto](../manifesto.md), [architecture](../architecture.md), and
[Base release format](../base-format.md) for the established layer boundaries.

For a shorter user model, start with [MPM and MBT](../management-workflow.md).
The [Base install/status contract](../mpm-base-contract.md) specifies content-only
installation and honest state inspection, agreed on 2026-11-06. The first
[exact import/status implementation](../base-installation.md) merged in PR #40.
[Base staging/selection/return](../base-boot-staging.md) is implemented in PR #41;
[owner changed-Base boot/return acceptance](../base-boot-acceptance.md#recorded-owner-acceptance-2026-11-07)
passed on 2026-11-07.
Moving upgrades and general lifecycle preparation remain subsequent work.

The proposed [complete distribution behavior contract](../distribution-contract.md)
connects this accepted area model to MBT, bootstrap and source self-hosting.
The [lifecycle/state proposal](../mpm-lifecycle.md) specifies declared installation
effects, configuration, initialization and migration gates; it does not authorize
arbitrary package hooks. See the [decision register](../distribution-decisions.md)
for unsettled interfaces. These are review drafts, not implemented capabilities
or an automatic amendment of the accepted command contract.

The user-directed [artifact architecture manifesto](../mpm-artifact-architecture.md)
(2026-10-28) adds the independent distribution model: Mojt-owned catalogs list
offered builds before installation; native artifacts and local repositories
must work without Nix or a live external service. Nix remains the current
experimental provider. Publication/trust formats and migration details in that
document are proposals, not implemented commands or an automatic change to
existing catalog/source bindings. The [local discovery prototype](../mpm-catalog.md)
adds explicit read-only search/inspection and Base-constrained Kernel policy
plans; it does not implement Kernel installation or adopt Ports metadata.

## 6. Implementation status

PR #50 joins exact installed Base/System/Kernel candidates to native-v2 through
`activate --artifact ID` and `upgrade --artifact ID`, with `--dry-run` preview.
Install remains content-only. The updater reuses handover/construction/admission
and atomic selection; status separates selected and running. Base candidates
need exact Kernel bounds; System currently permits unchanged-startup/tooling
changes. Moving-policy boot-area upgrades remain unimplemented. There is no
public System `plan` operation. See [the joined workflow](../system-transition.md).
The table below retains the earlier component milestone history.


Current as of 2026-11-07: merged PR #40 plus Base deployment integration in PR #41 (bounded owner boot/return acceptance passed; final review/CI remains). The ordinary System frontend
and the separately invoked earlier prototypes must not be confused.

| Area | Delivered/implemented behavior | Remaining user-flow boundary |
| --- | --- | --- |
| Sources/cache | Named owner-trusted local source registration, frozen metadata update, list/show and exact verified native fetch for all four artifact categories | General authenticated remote native distribution, common configured discovery and all area-install joins |
| Ports | Fresh request-origin/resolver/profile frontend; install, activate, upgrade, update, apply, remove/reset, status/list/history and discovery; Nix binary-output adapter | Native Port publisher, pruning/configuration forgetting and the final joined installed-machine journey |
| Kernel | Exact local-file or named-source install, retained matching modules/origin, status/verification, plan/stage/select/rollback on the managed native serial UEFI/VirtIO layout | Persistent Kernel upgrade policies joined to resolution/acquisition, generalized deployment and physical rollout |
| Base | Whole-release packer/directory installer, native packages, fresh-image inputs; PR #40 delivers exact local/source install and validated full-ID realizations; PR #41 implements exact Base staging/selection/return and joined status | Final review/CI, moving upgrades and configuration/lifecycle transitions |
| System | Pinned binary payload export, coherent userspace/manifest assembly and delivered MPM/Python/helpers | Distributable System composition import/install/status/upgrade on an existing disk and state/management compatibility gates |
| MBT | Separate image, build-environment, Kernel build and packaging tools provide working inputs | Public MBT grammar, named environments, bootstrap/build integration through the ordinary MPM path |

The fresh [Ports frontend](../ports-cli-integration.md) accepts explicit finite
source bundles and publishes complete profiles with independent configuration
and interactive wishes. Metadata update preserves accepted targets; explicit
upgrade advances only its requested moving wishes; exact active pins survive.
The real Nix adapter/frontend acceptance is recorded in
[Ports acceptance](../ports-profile-acceptance.md). Older format-1/2/3 metadata
adoption remains in `mpm-nix-prototype`, not the ordinary fresh-store frontend.

The [named-source integration](../source-runtime-integration.md) and
[Kernel source install](../kernel-source-install.md) use the same existing native
Kernel publisher. The owner accepted source installation through the delivered
System frontend on 2026-11-06. The [source-to-boot follow-up](../kernel-source-boot.md)
also passed one real reboot: retained source origin/install evidence, exact
selected/running deployment agreement, read-only modules, preserved Base/System
and machine identity, and no failed units. The two package revisions used the
same compiled Kernel release; exact IDs, not uname, distinguish this acceptance.
Kernel boot recovery and corrected shutdown have earlier separate evidence.

The [System runtime](../mpm-system-runtime.md) delivers the frontend's closed Python
module/helper set in new assemblies. Retained running Systems are not edited by
publishing new repository code. A local file import/source snapshot is explicit
owner trust; hashes do not authenticate a publisher.

The [agreed Base contract](../mpm-base-contract.md) requires a validated rootfs,
not just a cached archive; installation changes neither persistent machine
configuration nor next boot. The [first implementation](../base-installation.md)
merged in PR #40. Exact [Base deployment](../base-boot-staging.md) is implemented
in PR #41, with the [owner VM boot/return test](../base-boot-acceptance.md#recorded-owner-acceptance-2026-11-07)
passed on 2026-11-07.

**Not implemented:** Moving Base upgrades, missing-default lifecycle preparation and System mutations/status,
generalized boot deployments, catalog-backed persistent Kernel upgrades,
public MBT bootstrap/build integration, generic native Ports publication,
pruning/GC, signed remote-native distribution and the proposed lifecycle/state
engine. A successful Kernel source boot does not complete the six-step plan.
See the [gap matrix](../mpm-gap-matrix.md) and [governing plan](../mpm-consolidation-plan.md).
