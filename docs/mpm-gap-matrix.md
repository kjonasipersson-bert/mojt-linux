<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MPM: gaps to a complete user workflow

Updated 2026-11-06. Baseline: the functionality through merged PR #39.
This matrix distinguishes working implementation, acceptance evidence and the
remaining user-facing joins. It is not a claim that all roadmap commands exist.

The [complete distribution behavior draft](distribution-contract.md) defines
the target journeys and requirement/acceptance IDs. The
[lifecycle/state proposal](mpm-lifecycle.md) adds installation effects and
migration boundaries; the [decision register](distribution-decisions.md) lists
unsettled interfaces and implementation gates. New requirements are proposals
for review, not claims of accepted schemas or implemented hooks.

The [first consistency review](distribution-review.md) clarifies live-data
changes, unmanaged Ports data and recovery compatibility. A
[concrete MBT interface](mbt-interface-proposal.md) is now proposed; D1 remains
open for discussion, with no new runtime commands implemented.

The [D2-D4 concrete format draft](formats/draft-v1/README.md) now specifies
composition, storage/receipts, action sets and result records, with schemas and
linked examples. This narrows the design gaps in G3/G4/G8/G9/G14-G16; it does
not close their runtime implementation or acceptance gaps. MBT syntax is deferred.

The [request-to-boot workflow formats](formats/draft-v1/workflows.md) now add
configuration/interactive claims, exact locks, source/acquisition/cache records,
saved plans/approval and native boot v2. These are concrete review proposals;
G1/G5/G6/G7 and new G19 still require implementation and acceptance.

The owner is satisfied with the existing MPM command language. Preserve it.
The requested new-tool syntax discussion concerns **MBT: Mojt Build/Bootstrap
Tool**, not an MPM rename or a replacement command language. MPM manages content
and selections; MBT creates installation targets, build environments, builds and
packages using the shared libraries. Kernel remains a System component with a
separate update scope; environments and persistent state are not new layers.


The [initial-format policy](./format-policy.md) supersedes earlier transition requirements: fresh installations only, no legacy migration/support obligation. Keep explicit format versions and refuse unknown required versions before mutation. Current-state integrity and safe recovery remain required.

## Current review gate

The [shared MPM/MBT workflow](management-workflow.md) and
[Base install/status proposal](mpm-base-contract.md) are the immediate owner
review. The owner agreed on 2026-11-06; exact Base import/realization/status is
merged in PR #40, with validation recorded separately. Exact local source/
cache acquisition and source-installed Kernel boot have real installed-System
evidence. Exact Base staging/selection/return is implemented in draft PR #41;
its bounded owner VM boot/return acceptance passed on 2026-11-07. Moving Base upgrades, System
mutation and the remaining joins below are still gaps; public MBT syntax remains deferred.

## Milestone and priority

The controlled complete workflow is: bootstrap an installation, install/inspect
Base/System/Kernel/Ports, install compatible Base/System updates on the same
disk, retain exact content and recovery choices, acquire a pinned toolchain,
create a private environment, compile/package a Kernel, install/select it with
the installed MPM, boot it and return to the retained deployment if necessary.

- **P1:** needed for that controlled installed-machine workflow. Start with a
  trusted local native repository/installation kit and the existing Nix adapter.
- **P2:** required before general remote native distribution or physical Kernel
  rollout, or to extend supported backends/hardware beyond the first workflow.
- **P3:** later functionality; do not make it a prerequisite for the milestone.

This first workflow is **M1** in the behavior contract. The full distribution
goal also includes **M2** source builds of Base and Mojt-owned System code,
**M3** any explicitly claimed full external source coverage, and **M4** remote
publication plus supported physical rollout. Later priority does not remove a
requirement from that larger goal. State/handler contracts and refusal of
unsupported migrations are P1; enabling destructive migrations is not.

Code delivery in a new System is not evidence that the owner's retained running
VM has been upgraded. PR #34 has automated delivered-runtime acceptance; one
real Mojt acceptance belongs with the complete workflow, not another account
or generation test matrix after every helper change.

## Gap matrix

| ID / workflow | Working implementation and evidence | Missing join or capability | Completion criterion | Priority |
| --- | --- | --- | --- | --- |
| G0: Installed MPM | Common frontend, pinned Python/modules/helpers and ordinary-user read/admin-write classification are delivered in new System assemblies. Isolated delivered-copy tests cover native install/stage/select/status and provider-free discovery/resolution; owner #38/#39 evidence also covers source install and actual exact Kernel boot through delivered MPM. | Exercise the installed frontend in the real combined Mojt journey; retained images are not rewritten. | No source checkout, copied acceptance frontend or ad hoc PATH fix is needed to administer the resulting machine. | P1 acceptance |
| G1: Catalog to installation | Literal local search/show/versions, pure selectors and Base-bounded Kernel policies work. Ports has saved source/catalog state; native Kernel import now accepts an exact local archive or named-source acquisition with retained origin. | A configured common catalog/source binding, persisted native requests and one resolve/acquire/install plan. Local catalog knowledge is not a payload fetch. | A name/selector resolves from a recorded snapshot, acquires the approved exact content and installs it without choosing another provider or changing unrelated selections. | P1 |
| G2: Acquisition/cache/trust | Named owner-trusted local native sources, frozen snapshots, verified cache fetch for all categories and a source-to-Kernel installer join are implemented; owner installed-System acquisition and exact boot passed through #39. Nix retains its existing signature/import path. | Base install now joins these same acquisition rules through #40; join System next. General remote-native authentication/publication remains D7; local acceptance is not publisher authentication. | First workflow works from an explicitly trusted local kit and cached provider inputs. Remote native distribution additionally authenticates publisher/snapshot bindings; HTTPS/hash alone is not publisher trust. | Local path P1; remote trust P2 |
| G3: Base install/status | Merged PR #40 delivers exact local/source import, full-ID object/validated rootfs coexistence, retained origin and read-only status, including same-label different builds; prior packer and fresh-image inputs remain. | PR #41 Base deployment boot/return is merged and owner-accepted; join explicit lifecycle preparation later; old experimental `base/VERSION` trees are not automatically adopted. | Install a whole exact Base beside the old one, keep persistent state and distinguish release labels from artifact IDs; do not overwrite another build with the same label. | P1 |
| G4: System install/upgrade/status | System payload export, profile/unit assembly, manifests, exact dependency inventory and declared compatibility work in image builders. Native System format has fixtures. | A distributable immutable System composition plus install/upgrade/status on an existing disk. Persist System requests separately from historical retained generations. | Import native/provider dependencies, publish one coherent new generation, preserve Base/Kernel choices and leave running services unchanged until the planned activation. | P1 |
| G5: Complete activation/rollback | Kernel stage/select/rollback on the managed serial UEFI/VirtIO layout is owner-accepted, including a source-installed exact candidate with origin retained through the actual reboot (#39). Complete bindings and conservative compatibility checks exist. | PR #41 implements exact Base slots, scoped selection/return and subsequent Kernel staging against the exact Base boot tree. Owner changed-Base boot/return acceptance passed on 2026-11-07; System deployment remains separate. The first subset refuses missing defaults. | Each area changes only its agreed scope; stage a complete validated boot deployment, atomically select it for next boot and retain a compatible previous choice. | P1 |
| G6: Kernel requests | Native package/import/status and next-boot choice work; catalog policies cover pin/latest-LTS/latest-upstream constrained by explicit Base bounds. | Connect resolver to acquisition/upgrade and persist the requested policy separately from the selected exact artifact. Publisher compatibility/maintenance declarations must be real inputs. | A metadata refresh changes no installation. An approved upgrade resolves only eligible compatible content and retains old artifacts; no inferred Base upgrade or policy fallback. | P1 |
| G7: Ports | Real Nix import, upgrade/history, following/exact selectors, aliases and compatible-image persistence are accepted. Common frontend integration is automatically tested. | Use the common source/configuration route and include a real import through the installed frontend in the final journey. General native Port installation is still absent. | Normal Ports install/upgrade works without changing System/Kernel or global compilers. Nix-backed Ports are sufficient for the first milestone; a second provider is an extension. | Integration P1; native Ports P2 |
| G8: Inspect/failure/recovery | Area records distinguish installation/selection/running identity; shared writer locks and pre/post-publication failure rules work. Ports history, Kernel receipts, selected/previous boot records and incomplete-stage reports exist. | Coherent Base/System inspection and diagnostics after partial failure; define safe offline repair entry points. There is no global transaction history or general replay/repair protocol. | Explain what committed, what is selected/running, what incomplete content remains and how to retain/reselect a known-good compatible deployment. Keep authoritative records; a new database is not required. | P1 diagnostics; general recovery P2 |
| G9: MPM's own lifecycle | MPM/Python are bound to a System generation; Ports metadata compatibility is checked before composing System. Unknown native formats are refused by their readers. | Advertise/check management capabilities for all persistent registries/deployment formats before a System change or return to an older System. | The selected System's MPM can read/write the shared state it will encounter; incompatible writers/rollback plans fail before selection. No separate self-modifying MPM updater is needed. | P1 with System upgrades |
| G10: Toolchain/environment | Pinned image/Kernel environments, runtime library probes, retained closures, compilation and package provenance are accepted through separate tools. | Join acquisition/retention of exact tools to an MBT-managed named environment/workspace. Make inputs and retention inspectable without manual path files. | Fetch binaries explicitly, preserve exact dependencies, build as an ordinary user in a private environment, produce a native package and pass it through the normal MPM install path. | P1; shared MPM/MBT boundary |
| G11: Initial machine creation | Directory, VM/native image and older hardware image builders exist; an image was assembled inside Mojt and booted. | One MBT bootstrap plan/locked inventory and consistent target adapters reusing MPM installation/deployment libraries. | Produce a usable installation from declared Base/System/Kernel/Ports inputs without experiment-specific staging scripts. Disk formatting belongs to an explicit bootstrap target, not ordinary package installation. | P1; MBT responsibility |
| G12: Physical Kernel change | Earlier physical boot exists; the new native Kernel updater is accepted on serial UEFI/VirtIO VMs. | Wire native deployment to the physical hardware profile, local console, storage/input/network modules and exact firmware requirements. | Install/select/boot/return on a separate supported physical Mojt disk with a known-good boot choice, without external boot payloads or unrelated disk changes. | P2 before physical rollout |
| G13: End-to-end acceptance | The constituent generation, package, build and Kernel boot experiments have passed; new integration has automated coverage. | One bounded real-Mojt run through installed commands and MBT interfaces, including existing-disk Base/System changes and lifecycle failures. | AC1-AC5: retain identities/state/Ports, run the actual newly compiled Kernel and demonstrate compatible recovery; reuse prior component acceptance rather than a full cross-product. AC6/AC7 cover later milestones separately. | P1 final acceptance |
| G14: Lifecycle actions | Kernel derived-output preparation and ad hoc System/default/account setup exist; a bounded internal root-authorized missing-default handler now has exact plans, no-overwrite file publication and result evidence. It is not called by install/stage/select; package hooks are not authorized. | Common declared actions, versioned handler capabilities, explicit phases/targets/privileges, ordering and profile cache aggregation. | Unknown required actions fail before selection; import/preview executes no package code; supported initialization completes before dependent services. See STATE and D3. | P1 contract/minimal handlers |
| G15: Configuration and state compatibility | Persistent state and accounts survive tested compatible generation changes; legacy Base fills missing defaults. | State ownership, stable service identities, configuration conflict rules, schema read/write capabilities and explicit migration/restore prerequisites. | Preserve local changes; block unsupported/known-incompatible transitions, including older MPM; declare effects in the plan. See STATE, D4 and D6. | P1 gates; migration families later |
| G16: Lifecycle failure and recovery | Pointer publication rules distinguish pre-commit failure and publication uncertainty. The bounded defaults library retains durable intent/completion, reobserves local edits and requires explicit reconciliation of an interrupted ensure-file attempt. | Persistent effect evidence, postconditions, required-service gating, state-aware retry and recovery runtime retention. | AC4-AC5 distinguish selected/running from ready; an interrupted effect is not blindly retried or called undone by code rollback. No claim of atomic state plus selection. | P1 for supported effects; advanced restore later |
| G17: Native self-hosting coverage | Kernel compilation and full image assembly from prebuilt Base/System inputs passed on Mojt. | Source recipes, exact build locks/seed policy and coverage for Base and owned System code; imported dependencies remain visible. | AC6/M2 builds, packages, installs and boots native outputs; M3 requires an explicit complete source inventory, not relabelled binary imports. See BUILD, SELF and D5. | M2; not a prerequisite for M1 |
| G18: MBT behavior and interface decisions | Separate build/bootstrap tools and workspaces provide implementation inputs. | Public MBT object/command model, locked-plan schemas, inspect/run/resume/reporting interfaces and adapters reusing MPM. | Close D1/D5; implementation maps each supported operation to TARGET/BUILD requirements without a second installer or changing MPM syntax. | P1 design gate before public MBT CLI |
| G19: Declarative plus interactive wishes | Fresh Ports TOML apply, independent configuration/interactive reasons, explicit overrides, remove/reset and complete profile publication are implemented through #36/#37. | Extend request origins/locks and configuration application to supported Base/System/Kernel operations; multi-area input must not be silently partially applied. | Reapply/edit a named configuration without erasing interactive wishes/overrides; release configuration-only roots while retaining dependencies/recovery/data; publish complete per-area state atomically and reject old writers. | P1; request-to-boot integration |

## Recommended implementation order

1. Transaction/runtime consolidation is merged. Review the behavior/lifecycle
   proposals and close the relevant decision gates; retain current MPM syntax.
2. Join common source/catalog resolution and exact local acquisition to native
   installation. Add Base identity/registry/status and System composition/import
   using existing installers/assemblers, without a new universal solver.
3. Extend deployment staging/selection to Base/System; add management-format,
   state/handler compatibility, minimal declared lifecycle actions and failure
   diagnostics. Refuse unsupported migrations before selecting a deployment.
4. Define the MBT interface, named build environment and bootstrap plan. Reuse
   MPM acquisition, dependency retention and deployment engines.
5. Run AC1-AC5 for M1. Develop Base/owned-System source coverage for M2/AC6;
   extend trust and the physical profile for M4/AC7. Do not claim M3 from M1/M2.

Authenticated remote native channels can be developed alongside this order but
must be in place before ordinary untrusted-network native installation is
claimed. The first local-kit workflow must still record its explicit trust
decision and full artifact/dependency evidence.

## Deliberately outside the first milestone

These exclusions apply to M1, not to the larger source-self-hosting and rollout
requirements above. Minimal lifecycle/state compatibility and refusal rules are
inside M1; arbitrary package hooks and destructive migrations are not required.

No MPM language rewrite, global libc replacement, arbitrary desktop/PAM/NSS
compatibility solver, complete source rebuild of every System package, generic
native Port backend, automatic failed-boot fallback, data-format rollback or
physical GC is required for the controlled first workflow. They remain real
separate work. Until GC is implemented, retain protected content; do not equate
catalog withdrawal, profile removal or package absence with permission to delete
dependencies, running content, build environments or recovery references.




