<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MPM: gaps to a complete user workflow

Updated 2026-10-31. Baseline: the functionality through PRs #32, #33 and #34.
This matrix distinguishes working implementation, acceptance evidence and the
remaining user-facing joins. It is not a claim that all roadmap commands exist.

The owner is satisfied with the existing MPM command language. Preserve it.
The requested new-tool syntax discussion concerns **MBT: Mojt Build/Bootstrap
Tool**, not an MPM rename or a replacement command language. MPM manages content
and selections; MBT creates installation targets, build environments, builds and
packages using the shared libraries. Kernel remains a System component with a
separate update scope; environments and persistent state are not new layers.

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

Code delivery in a new System is not evidence that the owner's retained running
VM has been upgraded. PR #34 has automated delivered-runtime acceptance; one
real Mojt acceptance belongs with the complete workflow, not another account
or generation test matrix after every helper change.

## Gap matrix

| ID / workflow | Working implementation and evidence | Missing join or capability | Completion criterion | Priority |
| --- | --- | --- | --- | --- |
| G0: Installed MPM | Common frontend, pinned Python/modules/helpers and ordinary-user read/admin-write classification are delivered in new System assemblies. Isolated delivered-copy tests cover native install/stage/select/status and provider-free discovery/resolution. | Exercise the installed frontend in the real combined Mojt journey; retained images are not rewritten. | No source checkout, copied acceptance frontend or ad hoc PATH fix is needed to administer the resulting machine. | P1 acceptance |
| G1: Catalog to installation | Literal local search/show/versions, pure selectors and Base-bounded Kernel policies work. Ports has saved source/catalog state; native Kernel import takes an exact local archive. | A configured common catalog/source binding, persisted native requests and one resolve/acquire/install plan. Local catalog knowledge is not a payload fetch. | A name/selector resolves from a recorded snapshot, acquires the approved exact content and installs it without choosing another provider or changing unrelated selections. | P1 |
| G2: Acquisition/cache/trust | Local native archives are hash/descriptor verified; Nix substitutions use their existing signature/import path. | Shared native source/cache handling, explicit missing-byte errors and metadata refresh that preserves the last accepted view. Authenticated remote native publication/update remains unspecified. | First workflow works from an explicitly trusted local kit and cached provider inputs. Remote native distribution additionally authenticates publisher/snapshot bindings; HTTPS/hash alone is not publisher trust. | Local path P1; remote trust P2 |
| G3: Base install/status | Complete Base packaging and directory installation, defaults/state handling and multiple distinct release labels work. Native image assembly consumes a wrapped Base artifact. | MPM Base installation/status on an existing installation, full native identity/retention and handling of different builds/revisions under the same upstream label. Existing `base/VERSION` paths alone cannot identify every build. | Install a whole exact Base beside the old one, keep persistent state and distinguish release labels from artifact IDs; do not overwrite another build with the same label. | P1 |
| G4: System install/upgrade/status | System payload export, profile/unit assembly, manifests, exact dependency inventory and declared compatibility work in image builders. Native System format has fixtures. | A distributable immutable System composition plus install/upgrade/status on an existing disk. Persist System requests separately from historical retained generations. | Import native/provider dependencies, publish one coherent new generation, preserve Base/Kernel choices and leave running services unchanged until the planned activation. | P1 |
| G5: Complete activation/rollback | Kernel stage/select/rollback on the managed serial UEFI/VirtIO layout is owner-accepted. Complete bindings and conservative compatibility checks exist. | Generalize the deployment engine to a changed Base or System as well as Kernel. Current Kernel menus deliberately require fixed Base/System. | Each area changes only its agreed scope; stage a complete validated boot deployment, atomically select it for next boot and retain a compatible previous choice. | P1 |
| G6: Kernel requests | Native package/import/status and next-boot choice work; catalog policies cover pin/latest-LTS/latest-upstream constrained by explicit Base bounds. | Connect resolver to acquisition/upgrade and persist the requested policy separately from the selected exact artifact. Publisher compatibility/maintenance declarations must be real inputs. | A metadata refresh changes no installation. An approved upgrade resolves only eligible compatible content and retains old artifacts; no inferred Base upgrade or policy fallback. | P1 |
| G7: Ports | Real Nix import, upgrade/history, following/exact selectors, aliases and compatible-image persistence are accepted. Common frontend integration is automatically tested. | Use the common source/configuration route and include a real import through the installed frontend in the final journey. General native Port installation is still absent. | Normal Ports install/upgrade works without changing System/Kernel or global compilers. Nix-backed Ports are sufficient for the first milestone; a second provider is an extension. | Integration P1; native Ports P2 |
| G8: Inspect/failure/recovery | Area records distinguish installation/selection/running identity; shared writer locks and pre/post-publication failure rules work. Ports history, Kernel receipts, selected/previous boot records and incomplete-stage reports exist. | Coherent Base/System inspection and diagnostics after partial failure; define safe offline repair entry points. There is no global transaction history or general replay/repair protocol. | Explain what committed, what is selected/running, what incomplete content remains and how to retain/reselect a known-good compatible deployment. Keep authoritative records; a new database is not required. | P1 diagnostics; general recovery P2 |
| G9: MPM's own lifecycle | MPM/Python are bound to a System generation; Ports metadata compatibility is checked before composing System. Unknown native formats are refused by their readers. | Advertise/check management capabilities for all persistent registries/deployment formats before a System change or return to an older System. | The selected System's MPM can read/write the shared state it will encounter; incompatible writers/rollback plans fail before selection. No separate self-modifying MPM updater is needed. | P1 with System upgrades |
| G10: Toolchain/environment | Pinned image/Kernel environments, runtime library probes, retained closures, compilation and package provenance are accepted through separate tools. | Join acquisition/retention of exact tools to an MBT-managed named environment/workspace. Make inputs and retention inspectable without manual path files. | Fetch binaries explicitly, preserve exact dependencies, build as an ordinary user in a private environment, produce a native package and pass it through the normal MPM install path. | P1; shared MPM/MBT boundary |
| G11: Initial machine creation | Directory, VM/native image and older hardware image builders exist; an image was assembled inside Mojt and booted. | One MBT bootstrap plan/locked inventory and consistent target adapters reusing MPM installation/deployment libraries. | Produce a usable installation from declared Base/System/Kernel/Ports inputs without experiment-specific staging scripts. Disk formatting belongs to an explicit bootstrap target, not ordinary package installation. | P1; MBT responsibility |
| G12: Physical Kernel change | Earlier physical boot exists; the new native Kernel updater is accepted on serial UEFI/VirtIO VMs. | Wire native deployment to the physical hardware profile, local console, storage/input/network modules and exact firmware requirements. | Install/select/boot/return on a separate supported physical Mojt disk with a known-good boot choice, without external boot payloads or unrelated disk changes. | P2 before physical rollout |
| G13: End-to-end acceptance | The constituent generation, package, build and Kernel boot experiments have passed; new integration has automated coverage. | One bounded real-Mojt run through installed commands and MBT interfaces, including existing-disk Base/System changes. | Reach the milestone above with retained identities/state/Ports and the actual newly compiled Kernel running, then demonstrate the recovery choice. Reuse prior component acceptance rather than a full cross-product. | P1 final acceptance |

## Recommended implementation order

1. Land the tested transaction/runtime consolidation; retain current MPM syntax.
2. Join common source/catalog resolution and exact local acquisition to native
   installation. Add Base identity/registry/status and System composition/import
   using existing installers/assemblers, without a new universal solver.
3. Extend deployment staging/selection to Base/System; add management-format
   compatibility and failure diagnostics at the same publication boundary.
4. Define the MBT interface, named build environment and bootstrap plan. Reuse
   MPM acquisition, dependency retention and deployment engines.
5. Run one complete Mojt workflow, then extend and accept the physical profile.

Authenticated remote native channels can be developed alongside this order but
must be in place before ordinary untrusted-network native installation is
claimed. The first local-kit workflow must still record its explicit trust
decision and full artifact/dependency evidence.

## Deliberately outside the first milestone

No MPM language rewrite, global libc replacement, arbitrary desktop/PAM/NSS
compatibility solver, complete source rebuild of every System package, generic
native Port backend, automatic failed-boot fallback, data-format rollback or
physical GC is required for the controlled first workflow. They remain real
separate work. Until GC is implemented, retain protected content; do not equate
catalog withdrawal, profile removal or package absence with permission to delete
dependencies, running content, build environments or recovery references.
