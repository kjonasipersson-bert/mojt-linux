<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MPM and MBT: complete distribution behavior contract

Draft 2, 2026-11-01. This is the target behavior specification for review,
not an implementation or an assertion that every decision is settled. MUST,
SHOULD and MAY describe the proposed target. Previously accepted area semantics
remain binding; new lifecycle mechanisms and MBT interfaces remain proposals
until reviewed. Existing MPM syntax is retained. No new MBT command spelling is
approved here. The [gap matrix](mpm-gap-matrix.md) records implementation evidence.

This document connects the [MPM contract](mpm.md),
[artifact architecture](mpm-artifact-architecture.md),
[transaction rules](mpm-transactions.md) and proposed
[lifecycle/state contract](mpm-lifecycle.md). Those documents describe detail;
this document defines the complete user journeys and their completion criteria.
Where an older experiment's implementation falls short, record a gap rather
than treating the old experiment as the specification.

The [concrete format draft](formats/draft-v1/README.md) now defines System
compositions, exact-ID native storage/install receipts, lifecycle action sets
and per-action result chains with schemas and linked examples. These are D2-D4
review proposals, not activated layouts or accepted wire migrations. MBT syntax
is parked for later discussion and does not block review of these data formats.

The [request-to-boot formats](formats/draft-v1/workflows.md) add the approved
declarative-plus-interactive direction: named configurations own their wishes,
interactive wishes coexist, and explicit active overrides persist. Independent
claims and graph/retention references replace a single package-origin flag.
Exact wire fields are review proposals; existing MPM metadata is not rewritten.

## 1. Responsibilities and invariants (OWN)

| Owner | Responsibility | Boundary |
| --- | --- | --- |
| MPM | Discover, resolve, acquire, verify, install, inspect, retain and select content; coordinate declared lifecycle effects | Does not silently compile, format disks or change another area's selections |
| MBT | Prepare explicit targets/workspaces, acquire a pinned build environment through MPM, build, package and bootstrap | Reuses MPM libraries; no second package registry, resolver, installer or boot publisher |
| Provider adapter | Translate exact upstream references and acquire/retain dependencies using the provider's declared protocol | No authority to choose Mojt's Base/System/Kernel/Ports policy or start host services |
| System runtime | Supply MPM/Python, supported lifecycle handlers, boot/service integration and a recovery path | Immutable generation; an update does not edit an older generation in place |
| Administrator / local configuration | Approve scope, trust and persistent-state policy | Approval of one plan does not authorize unrelated effects or an implicit provider change |

Base remains a complete image. System is an immutable composition. Kernel is a
System component with separate update scope. Ports supports parallel versions,
active selections and tracked wishes. Persistent state and build environments
are not additional OS layers. Installation, selection and execution are distinct.
Nix is a supported adapter, not the identity or schema of the core model.

## 2. Identities, records and inspection (ID)

Every journey MUST distinguish offered, requested, resolved, installed, selected,
running and incomplete content. Version labels are for people; full artifact
IDs distinguish revisions/builds with the same upstream version. A kernel release
string, System label or generation number alone is not exact identity.

Records MUST retain catalog snapshot/provider provenance, exact dependency
references, requested policy, selected outputs and compatibility evidence.
System generations retain immutable compositions; historical generations are
not additional upgrade requests. Build environments retain their dependencies
without installing global compiler defaults. Area-owned authoritative records
remain authoritative; a new database or global event log is not required.

A readable configuration expresses wishes, an exact resolution lock records
builds/snapshots, and per-area state records independent origins plus effective
choices. Removing one configuration releases only its claims and owned choices;
interactive overrides and other origins remain. Installing additional versions
still preserves the active default. Dependency/running/recovery/build references
remain retention roots; withdrawal of a wish is not physical deletion.

Status MUST show selected and running identities separately, the baseline a
pending plan will change, any incomplete action and the available recovery
choice. Unknown identity/compatibility MUST be reported as unknown, not inferred
from a matching name. Inspection of a healthy absent registry creates nothing.
Recovery evidence MUST distinguish read errors, partial records and absence.

Human output MUST explain scope, blockers and the next safe action. Machine
output needs versioned records and distinguishable no-op, blocked, failed and
publication-uncertain outcomes. Exact command options/exit codes are interface
decisions, not new spellings implied by this document. Ordinary users may inspect
shared state; shared mutations require administrator authorization. Owned build
workspaces/private experiments must not grant authority over the machine.

## 3. Sources, resolution and trust (SRC)

MPM MUST resolve from an explicitly selected, recorded catalog snapshot.
Metadata refresh MUST NOT install/activate content, run hooks or perform hidden
provider changes. Install/upgrade MUST NOT hide a metadata refresh or source
build. Literal search, selectors and Kernel policies follow the existing
[catalog contract](mpm-catalog.md). Requests and exact resolutions are separate.

Plans MUST bind the source/trust decision, exact artifacts, transport digests
and provider dependency references. Verification precedes publication. Corrupt,
missing, conflicting, withdrawn or unauthenticated content is an explicit error;
do not substitute another build/provider. A previously retained artifact may
remain usable under its recorded trust/revocation policy, not merely because a
download locator still exists. Metadata refresh preserves the last accepted
snapshot on failure and reports its age. Offline operation uses verified retained
inputs and reports precisely what is absent.

An explicitly trusted local installation kit supports the first milestone.
Remote native publication MUST authenticate catalog-to-artifact bindings and
define key rotation, revocation and stale/rollback handling before general
network-native installation is claimed. HTTPS and payload hashes alone do not
establish publisher authority. Existing provider trust is explicit and retained.

## 4. Plans and execution (PLAN)

Read-only planning MUST show target identity, selected/running baseline,
affected area, wishes/pins, exact old/new content, dependencies and sources,
known download/storage requirements, compatibility evidence, lifecycle effects,
privileges, next-boot/restart implications and recovery limits. Unknown sizes
are labelled. It MUST NOT acquire payloads, execute effects, create registries,
locks or roots, or select content. Static descriptor reading is allowed.

Execution freezes that plan, acquires/verifies content, prepares private output,
rechecks the authoritative baseline under shared ordered locks, then publishes
using the relevant commit point. A changed baseline requires a fresh plan and
authorization under the original approval policy; `-y` never expands scope.
Preflight includes installed management-format and lifecycle-handler support.
Use [transaction rules](mpm-transactions.md); do not claim one atomic transaction
across independent pointers, service starts and shared state writes.

A no-op changes no selection or history. A successful content publication is
reported separately from later activation/initialization success. Failures after
publication preserve possibly committed content and expose uncertainty. No
compilation runs under installation locks. General destructive GC is deferred;
retention protects installed, running, selected, pinned-build and recovery inputs.

## 5. Initial installation and bootstrap (TARGET)

MBT MUST accept a declared composition and produce a locked inventory of exact
Base/System/Kernel/Ports, tool/source references, hardware/console profile and
state-initialization policy. It MUST use the same MPM acquisition, installation
and deployment rules as a later update. Target preparation is a separate step:

| Target | Required behavior |
| --- | --- |
| Directory | Populate an explicitly owned new target; report that it is not bootable until a boot adapter completes it |
| Regular disk image | Build/publish a complete image in a new output path; interrupted work cannot replace the prior complete image |
| Physical disk | Show stable device identity, existing layout and destructive boundaries; require explicit approval bound to that target; refuse active/in-use targets |

An ordinary MPM install MUST NOT partition/format a disk. Updating an existing
Mojt disk MUST NOT use a fresh-image operation that replaces persistent state.
Credentials use an interactive protected channel or a separately designed secure
provisioning mechanism, never command-line secrets or plaintext build logs.
Copies MUST follow an explicit machine-identity policy; a new installation gets
its own persistent identity, an update preserves it. Root/admin/user access,
homes, networking, clock, UTF-8, manuals and recovery prerequisites belong to
the chosen composition profile, not undocumented experiment scripts.

## 6. Installed machine updates (BOOT and PORTS)

Base installation retains one complete exact release beside existing releases.
System installation imports exact components and publishes a coherent immutable
generation. Kernel installation retains the kernel and matching modules together.
Installing any of these alone MUST NOT change next boot or running services.
Only the accepted Ports first-install convenience also selects a default, with
that effect in the plan. Further Ports installations preserve the active choice.

Upgrade uses tracked wishes, not every installed historical artifact. Base,
System and Kernel upgrades preserve the other two choices unless a cross-area
plan is explicitly approved. Kernel pin/LTS/upstream policy and Base bounds are
checked separately from exact build identity. Ports upgrade changes only the
requested wishes/allowed selections; project/toolchain pins are protected.

Boot staging MUST validate the complete Base/System/Kernel/modules/initramfs,
firmware, management-format, state and hardware combination. Only complete
deployments can be selected. Selection atomically publishes the next boot
choice, retains a compatible previous choice and does not reboot or live-switch
services. Further plans start from selected content, showing if running differs.
Runtime evidence identifies the actual boot deployment and module tree.

Rollback is an explicit validated selection, not a promise to restore data.
Known-incompatible state or management formats block ordinary selection.
Unknown required compatibility also blocks it; warn-only handling is insufficient
for a prerequisite the operation cannot establish. Separate offline data restore
requires a reviewed procedure. Automatic failed-boot fallback remains deferred.

Check declared managed-state prerequisites, not a universal schema for every
user file. Unmanaged application data remains outside automatic migration and
data-rollback guarantees; show that boundary rather than refusing every Ports
operation. A previous deployment's compatibility is rechecked against current
state at selection/start; retaining its files is not permanent proof it is safe
to run. See [the specification review](distribution-review.md).

Ports activation affects new starts, not existing processes. Aliases/conflicts,
following/exact policy, history and fallback after removal follow the existing
MPM contract. Port installation cannot create/start a host service implicitly;
host capabilities are verified requirements or an approved System change.
Removal never implies permission to delete application/user data or shared
dependencies. Active services and retained recovery choices need explicit
decommissioning before future physical collection.

## 7. Build, package and self-host (BUILD and SELF)

MBT MUST use a pinned environment with inspectable exact tools, runtime libraries,
source identities, recipe revision, configuration, patches and target platform.
MPM acquires/retains binaries; builds run as an ordinary user in a private owned
workspace, without changing global compiler, Ports or boot selections. Workspace
ownership and writable/output boundaries are checked before execution. Default
build execution is not a claim of a security sandbox; untrusted recipes require
a separate isolation policy. Recipe execution is distinct from package import.

The declared builder profile MUST deliver a versioned MBT and its exact runtime;
it cannot depend on an unrecorded checkout or whichever Python happens to be
active. Its packaging location and public interface are D1 decisions. MPM/MBT
and any helper they invoke MUST advertise/check the plan, artifact, registry and
lifecycle capabilities they share before a System update or older-tool use.

Source fetching and dependency acquisition MUST be explicit. A locked build
must not resolve moving tags/channels silently. Resume verifies frozen inputs
and recipe/config identity, reports incomplete outputs and never treats them as
installable. Outputs carry native descriptors, provenance and exact dependencies;
a compiler update does not rewrite previously published packages. Reproducible
input capture is mandatory; bit-identical output is claimed only when measured.

Building is not installation. The produced package MUST pass the same verifier
and installation/deployment route as a downloaded package; local build origin
does not grant automatic root execution or trust. Publishing an offered catalog
entry is separate from selecting it on the build host.

| Milestone | Required evidence | Existing boundary |
| --- | --- | --- |
| M1: integrated administration | Installed MPM manages all areas on the same disk; MBT bootstraps a new image and builds/packages a Kernel, then normal MPM installs/selects it | Constituent experiments exist; the joined journey and Base/System updater do not |
| M2: native self-hosting | Mojt builds its Base and Mojt-owned System components from pinned sources/recipes, composes a new System/image, installs and boots the results | Current Base is externally bootstrapped; current full-image test assembles prebuilt inputs |
| M3: full source coverage | Explicit source-build coverage for every component claimed to be rebuilt, including external-provider inputs and a recorded bootstrap toolchain/trust seed | Not established by Kernel compilation or M2; importing binaries must remain visible |
| M4: supported distribution rollout | Authenticated publication/acquisition and supported physical-target update/recovery evidence | Local-kit/VM acceptance alone is insufficient |

External providers may remain useful at every milestone. Independence means
Mojt owns its contracts and can retain/use declared local inputs; it does not
mean a compiler is built without a bootstrap seed or every upstream source is
maintained by Mojt. MBT MUST report built-from-source, imported and externally
bootstrapped components separately. It MUST NOT label image assembly as a full
source rebuild. Minimum M2 coverage is Base plus all declared Mojt-owned System
code; the inventory makes any remaining externally imported dependencies clear.

Libc remains an exact runtime dependency, not a global version switch. Record
tool and product interpreter/library identities. New userspace built against a
Nix libc retains that closure; it must not be claimed to run on Base libc unless
actually built/validated for it. No automatic interpreter rewriting or Base libc
replacement. In-process modules and state/host-service boundaries remain real
compatibility gates; no universal desktop/libc solver is implied.

## 8. Lifecycle, failure and recovery (STATE and REC)

The [lifecycle/state contract](mpm-lifecycle.md) defines declarative actions,
first-boot initialization, migration prerequisites and separate action evidence.
It applies to both MBT-created installations and MPM updates. Missing handler or
unsupported required migration blocks the plan before selection. No arbitrary
archive hook runs during discovery, verification or installation.

Recovery MUST be possible with retained local content and a compatible management
runtime; an online catalog or working normal network is not a prerequisite.
The recovery environment/toolchain is an explicitly retained composition with
access to the target's authoritative records. It must not confuse its own
running deployment with the offline target. It inspects interrupted publications
and effects, then permits only validated continuation, selection or separately
approved data restoration. Authentication bypass and destructive automatic
repair are not implied by booting a recovery environment.

## 9. Acceptance requirements (AC)

| ID | Bounded acceptance | Requirements exercised |
| --- | --- | --- |
| AC1 | From installed Mojt, bootstrap a new image from a declared local kit and boot it; inspect exact inventory and distinct machine identity | OWN, ID, SRC, TARGET |
| AC2 | On that same disk, install/inspect and activate a new Base and System separately, preserving other choices, users/homes/state and exact Ports; inspect selected versus running | ID, PLAN, BOOT, PORTS |
| AC3 | Acquire an exact toolchain, create an MBT workspace, compile/package a Kernel; install/stage/select with delivered MPM, boot it and return to a compatible retained deployment | BUILD, SELF M1, BOOT, REC |
| AC4 | Inject failure before publication, after rename and during a supported lifecycle action; report distinct outcomes, recover without deleting possibly committed content; repeat no-op changes nothing | PLAN, STATE, REC |
| AC5 | Reject unknown required action, unsupported state/schema, unsafe target, incompatible older MPM and unauthorized mutation; preview executes no payload/action | OWN, TARGET, STATE, PLAN |
| AC6 | Build/package Base and owned System code on Mojt, install/boot outputs; report all imported/source-built inputs and bootstrap seed | SELF M2; M3 only for explicitly complete source coverage |
| AC7 | Authenticate remote native updates and reject bad/stale/revoked metadata under the selected policy; separately install/boot/return on a supported physical disk | SRC, TARGET, SELF M4 |

Automate component/failure tests. Reuse existing owner acceptance for unchanged
components; run one bounded combined real-Mojt journey per milestone instead of
repeating account/kernel/version cross-products. Documentation alone establishes
none of these execution results. See [decision gates](distribution-decisions.md)
before calling this draft implementation-ready.

