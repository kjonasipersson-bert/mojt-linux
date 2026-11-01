<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Distribution specification: decisions and implementation gates

2026-11-01. The [behavior contract](distribution-contract.md) describes the target
and [lifecycle proposal](mpm-lifecycle.md) fills the installation-effects gap.
This register prevents a comprehensive behavior draft from being mistaken for
a completely settled API, wire format or implemented distribution.


The [initial-format policy](./format-policy.md) supersedes earlier transition requirements: fresh installations only, no legacy migration/support obligation. Keep explicit format versions and refuse unknown required versions before mutation. Current-state integrity and safe recovery remain required.

## Established constraints to preserve

- Existing MPM syntax and area boundaries; no MPM rename or command redesign.
- Whole Base, immutable System generations, separately scoped System-owned Kernel,
  parallel Ports versions, explicit wishes and independent activation.
- Exact identities/provenance/dependencies, retained history and shared immutable
  storage without cross-area selection changes.
- Selected versus running content, next-boot System activation, persistent state
  and no automatic claim that code rollback restores data.
- Provider-independent core, optional Nix adapter, Python in the System management
  runtime, no global libc substitution.
- Package verification does not execute archive installation hooks. MBT must
  reuse MPM's installation and deployment primitives.

## Proposed requirements requiring review

Approve the detailed lifecycle/initialization ordering, required-action handling,
state ownership, incompatibility blocking, effect evidence and self-hosting
milestones as behavior requirements. Their documents use normative words for
the target; that does not silently adopt new schemas or authorize implementation
of an arbitrary script runner. Documentation CI cannot approve policy choices.

The [first consistency review](distribution-review.md) resolves six ambiguities
and separates review completion from owner adoption and implementation. The
[concrete MBT interface](mbt-interface-proposal.md) is ready for discussion;
the lifecycle document now includes a closed first-version handler recommendation.
D1/D3/D4/D5 have concrete proposals, but are not fully closed: command and
format decisions below remain explicit gates.

## Concrete format proposals, 2026-11-01

The owner deferred exact MBT syntax and requested the next data-format slice.
[D2-D4 format drafts](formats/draft-v1/README.md) introduced six closed JSON
schemas; the workflow slice below adds a seventh with further definitions,
linked synthetic examples and a documentation validator. This progress
does not mark the decisions adopted or the runtime implemented.

| Gate | Newly specified | Still required before the broader gate is closed |
| --- | --- | --- |
| [D2](#open-decisions-and-gates) | Immutable composition/store/receipts; workflow wishes, sources/acquisition/cache, locks and boot v2 records | Owner review; new Ports origin-state embedding; fresh native-v2 runtime/layout and realization implementation; large-catalog indexing |
| [D3](#open-decisions-and-gates) | Fixed action types/versions/phases/parameters; dependency validation; handler/owner binding and first-version limits | Owner review; actual advertised handler implementations and integration/failure tests |
| [D4](#open-decisions-and-gates) | Invocation/result chain, factual checks, state observations, saved plan/approval binding and publication ordering | Owner review; family-specific state readers/coordination; actual authorization/recovery/failure integration tests |
| [D5](#open-decisions-and-gates) | Exact resolution locks and target/executor/scope-bound execution plans/local approvals | Build recipe/workspace/environment wire, provenance and M2 source coverage; MBT interface discussion remains separate |

The first acquisition trust kind is explicit local-file trust. D7 remote trust
is not implied by these receipts. D6 destructive migrations remain unsupported.
D1 syntax is intentionally deferred; do not implement new MBT verbs while
reviewing data formats.

## Request-to-boot format proposals

The owner approved continuing the independent-reasons model: configuration and
interactive wishes coexist; a configuration releases only its own roots;
explicit interactive choices persist. MBT syntax remains deferred. The
[workflow format slice](formats/draft-v1/workflows.md) specifies thirteen new
record shapes, one strict parsed TOML shape and linked fixtures:

- D2: sources/snapshots, acquisition maps, native cache observations, named
  configuration origins, per-area claims/selections and exact resolution locks.
- D4/D5: immutable target/executor/scope/baseline-bound execution plans and
  protected local approvals, with per-area commit and uncertainty semantics.
- D2/D4: generalized boot inputs/binding/deployment/selection v2, including
  request roots and explicit compatibility/transition gates.

These replace the formerly unspecified wire proposals in those portions of the
backlog, not implementation or review gates. Remaining work includes new Ports
origin-state embedding/refusal by old writers; native-v2 realization/reader/layout
transition; build recipe/workspace/provenance wire; supported handler/family-reader
implementation; remote trust/large-catalog indexing and physical acceptance.
Do not call D2/D5 wholly closed or silently add fields to existing formats 1/2/3.

## Open decisions and gates

| ID | Decision / required deliverable | Gate |
| --- | --- | --- |
| D1 | MBT public command grammar, delivery in a builder profile and object model: target, composition, locked plan, environment, workspace, build, package and bootstrap; errors/exit classes and versioned machine interfaces for MPM/MBT | Discuss before implementing public MBT verbs; keep existing MPM verbs |
| D2 | Versioned native source/request/cache and immutable System composition schemas; same-release Base storage identity; descriptor extensions and unsupported-format refusal | Before catalog-to-install and existing-disk Base/System implementation |
| D3 | Versioned lifecycle action capability registry, supported initial handlers, path/account ownership conflict rules and dependency ordering; expose supported handlers in inspection | Before accepting package action declarations |
| D4 | State-schema declarations and management compatibility, read/write capabilities, state-preparation/action evidence durability and retry protocol | Before System changes shared metadata or executes persistent effects |
| D5 | Source recipe/lock/provenance formats and environment pin/retention interfaces, bootstrap toolchain policy and M2 source coverage list | Before MBT integration/M2 self-hosting claims |
| D6 | Backup/restore and service quiescence procedures per migration family, recovery access/runtime, unsupported/unknown state behavior | Before enabling a migration family; first release can reject it |
| D7 | Native remote authentication/publication: trust roots, signature binding, rotation/revocation, expiry/offline/stale policy and catalog rollback protection | Before general remote-native install or publishing an official update channel |
| D8 | Supported physical target profiles, device safety checks, firmware/storage/input/network/console requirements and recovery medium | Before physical installation/update acceptance |
| D9 | Close remaining MPM contract details within existing syntax: request-policy editing, supported version adapters, multi-command/exact alias escaping, profile namespaces, collision policy and user/project overrides | Before claiming those policies/backends or production project locking; keep the current supported subset explicit |
| D10 | Advisory/withdrawal and direct-provider-operation policy: when selected content may be used, how externally changed records are detected, and what requires an explicit repair plan | Before claiming production update/security reconciliation; never silently adopt foreign state |

Each deliverable needs a concrete format/interface proposal and focused failure
tests. Do not hide these decisions inside unrelated integration code. Wire
details may be split into implementation PRs once behavior is reviewed, but must
be settled before that mechanism accepts real state or user input.

## Completion checklist

- [x] Perform a first consistency review of lifecycle/state and milestone behavior.
- [ ] Settle/adopt the remaining lifecycle/interface proposals; review completion
  is not an implementation claim or approval of every schema/command detail.
- [ ] Decide D1 before the MBT CLI is implemented; do not delay independent MPM work.
- [ ] Close the relevant D2-D6 gates with versioned formats and compatibility rules.
- [ ] Complete M1 gaps, then AC1-AC5 from the behavior contract on installed Mojt.
- [ ] Complete M2 native source coverage and AC6; keep imports visibly distinct.
- [ ] Close D7-D8 and AC7 before claiming a supported remotely updated physical distribution.
- [ ] Claim M3 full-source coverage only against an explicit complete inventory.

The [gap matrix](mpm-gap-matrix.md) is the implementation backlog, this register
is the design backlog, and the AC requirements are the acceptance backlog.
Keeping those separate makes the meaning of "complete" inspectable.


