<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Lifecycle actions, configuration and persistent state

Proposal for review, 2026-11-01; no new action interpreter, hook API, migration
engine or wire schema is implemented by this document. This extends the target
[distribution contract](distribution-contract.md) and preserves current native
packages' prohibition on executable installation hooks. Names below describe
capabilities, not accepted JSON keys or public commands.

The [concrete action-set format](formats/draft-v1/lifecycle-actions.md) and
[result registry](formats/draft-v1/lifecycle-results.md) now provide proposed
field sets, schemas, identities, ordering and interrupted-execution handling.
They use a closed initial vocabulary and preserve the no-arbitrary-hooks rule.
They are proposed wire formats, not an implemented interpreter or migrator.

## 1. Desired state and known operations

A package may need more than immutable files. Describe the requirement and its
scope; MPM/System own execution policy. A descriptor is not permission to run
arbitrary root code. Supported handlers are versioned code supplied by the
management System, with explicit target/runtime compatibility requirements.
Package metadata cannot introduce a handler by naming a shell command.

| Action family | Inputs and ownership | Intended phase |
| --- | --- | --- |
| Kernel derived output | Exact kernel/module tree and deployment composition; generation-owned indices/initramfs/boot files | Private staging, then validated publication |
| Profile caches | Exact profile contributors and cache format; generation/profile-owned output where possible | Staging before selection; user caches only in authorized user scope |
| Service accounts | Stable account name/identity policy; persistent allocation and collision checks | Explicit new-target initialization or selected System initialization before service start |
| Service directories | Owner/mode and declared path namespace; no arbitrary recursive ownership change | Initialization before the associated service starts |
| Configuration defaults | Declared owned paths/default revisions and local override precedence | Planned, recorded state initialization/update |
| Service configuration | Exact unit/config composition and explicit enablement policy | Generation assembly; selected System starts it on boot |
| Data migration | Named data owner, exact migration implementation, input/output schemas and prerequisites | Explicit coordinated maintenance/start gate, never ordinary content import |

Systemd sysusers/tmpfiles/StateDirectory mechanisms are possible implementations,
not automatic authorization to apply every directive from an imported package.
Validate path, ownership, collision and destructive semantics. Shared cache work
SHOULD be coalesced by affected profile/inputs, not invoked repeatedly per file.
Immutable results belong to the staged generation; do not write them into a
different running deployment or another area's profile.

Unknown required action or handler version MUST fail preflight. Optional work
may be omitted only if declared genuinely optional and the omission is visible.
An install cannot claim a usable service if a prerequisite is missing.

## 2. Phases and execution context

| Phase | Allowed effects | Prohibited implicit effects |
| --- | --- | --- |
| Discover/resolve/preview | Validate/read metadata; enumerate exact planned actions and prerequisites | Payload execution, accounts/data changes, roots/registry creation, network payload fetch |
| Acquire/verify | Fetch approved exact bytes, verify, retain complete dependencies | Package hooks, running service changes, live data migrations |
| Stage/install | Private immutable output and installed-content record | Starting services, changing live user data or next-boot selection |
| State preparation | Explicit minimal bootstrap/default-state work required for a target | Hidden overwrite of admin files or claims of rollback-safe data mutation |
| Select | Validate and publish complete profile or next-boot choice | Automatic reboot, live System service restart or arbitrary migration |
| Initialize selected System | Ordered account/directory/configuration actions; approved supported migrations; then dependent services | Running incomplete/unapproved actions or proceeding after failed required initialization |
| Remove/decommission | Remove profile references or explicitly disable an approved service | Deleting accounts, home directories, databases or backups as a side effect |

The legacy Base installer already copies missing defaults into persistent state.
That is a real state-preparation effect: inventory/plan it and preserve existing
files, rather than claiming every existing install path is state-free. The
target staged-content path SHOULD defer state changes until needed. Explicit
new-target bootstrap can initialize state before the first boot. This exception
does not authorize modifying a running installation while preparing an upgrade.

Each executed action MUST identify owning artifact/deployment, target root,
phase, input identities, handler/runtime version, resources, required privilege,
dependencies, retry policy and observable result. Execute against explicit target
paths, not a process's guessed `/etc`/`/var`. Never start the host's services while
preparing an offline image. An offline target cannot run first-boot actions at
build time merely because tools are available in the build environment.

Use a fixed retained tool/runtime closure; do not resolve execution tools from
Ports or a mutable host PATH. If a future migration needs the new component's
runtime, retain and validate that runtime before selection. Require no network
or interactive prompts during activation/boot initialization. Choices/secrets
must be provisioned in advance through the approved channel. Dry-run never
executes a migration to discover what it would do.

## 3. Accounts, configuration and ownership

Service UIDs/GIDs MUST remain stable across compatible generations and rollback.
Check existing passwd/group/shadow identities, reserved ranges and local user
collisions before allocation. Never renumber existing users automatically.
Removing a package leaves its account/data until explicit decommissioning; an
allocation registry must not disagree with the real account database. Account
tools and service/database writers require coordination beyond MPM file locks.

Defaults MUST distinguish absent files, package defaults and administrator-owned
changes. Preserve existing configuration; show proposed replacements/merges and
their unresolved conflicts. Do not silently overwrite or change ownership of
arbitrary local files. A deferred merge mechanism may initially reject a change
requiring a merge and emit a manual action, rather than inventing a safe merge.
Plans/status must mark that prerequisite unsatisfied until resolved and checked.

Every mutable path needs a declared owner/scope and conflict policy. Registration
under Ports does not permit System-owned `/etc` writes. Existing shared state is
not owned by whichever version was installed last. Account/configuration changes
are state effects even if additive and idempotent; they are not undone by a boot
pointer replacement. Support local overrides without editing immutable packages.

## 4. State schemas and migrations

The owner of persistent data MUST declare the formats it can read and write and
the compatibility it can establish. A planned transition includes current state,
target schema, exact migration implementation, prerequisites, affected services,
required quiescence, backup/restore policy and backward-compatibility consequence.
The same checks cover MPM/MBT registries and other management metadata.

This applies to state participating in a Mojt-managed lifecycle: management
registries, configured System services and explicitly integrated applications.
It is not a claim that Mojt understands every home-directory file. A normal
Port with unmanaged user data declares no automatic data migration; installation
may proceed with that limitation visible. Do not execute the application to
inspect its data. A declared required managed-state transition must satisfy its
gates like a System service.

The first integrated release may support only non-destructive initialization and
schema-compatible upgrades. Reject an unsupported migration before selecting a
new deployment. Metadata promising a migration is not an implemented mechanism.

For later code-based migrations, the operation MUST be separately authorized,
identity-bound and constrained to the declared data owner/paths. No generic
archive `postinst` execution is implied. A handler must define its exact runtime,
privilege and isolation requirements; chroot alone is not a security boundary.
It also defines checkpoint/retry semantics, validation and failure behavior.
One-shot non-idempotent migrations require a specific recovery procedure; do
not label them retry-safe merely because an execution marker exists.

Before starting a state writer or changing format, coordinate that service and
other possible writers. MPM's package locks alone cannot quiesce a database.
For next-boot updates, show migration/rollback consequences before approval and
bind approval to the exact deployment/action inputs. Recheck on boot. Normal
records written by the old compatible service do not by themselves invalidate
the plan. Check schema identity, ownership, capabilities and declared action
preconditions, not an implicit hash of all live data. If a relevant prerequisite
changed or cannot be established, stop before mutation, report blocked
initialization and keep the dependent service stopped. A migration requiring
an exact snapshot must declare that snapshot and its quiescence/backup procedure.

Known-incompatible rollback MUST be blocked before next-boot selection; unknown
required compatibility is not permission. In a recovery boot, keep incompatible
writers stopped as well. Report whether a backup exists and whether restoration
is supported/tested; never call a backup created/verified when it is only planned.
Data restoration is separate from code rollback and may lose newer data. It
requires an explicit target/restore point and offline/quiesced validation.

Recheck recovery choices after supported state transitions. "Previous" records
content history, not perpetual data compatibility. For M1, reject transitions
that break compatibility with the retained recovery choice. Enabling such
transitions later requires a supported separate restore/recovery procedure and
explicit revised recovery expectations.

## 5. Failure, retry and action evidence

| Boundary | Required outcome |
| --- | --- |
| Preparation fails before content/selection publication | Old selection remains; identify incomplete output and any prior explicit state-preparation effects |
| Publication may have committed | Preserve possibly selected content; inspect authoritative pointer; report uncertainty |
| Required initialization fails after selection | Deployment can be selected/running but not ready; dependent service remains stopped; no false overall success |
| Migration interrupted | Record incomplete/uncertain action; inspect actual data/checkpoints under the migration's recovery protocol before retry |
| Boot/power loss after data change but before result record | Do not treat missing completion evidence as proof nothing changed; reconcile actual schema/state |
| Retry with same validated inputs | Safe declarative actions converge without repeating destructive work; migrations follow their explicit retry contract |
| Different inputs or baseline | New plan/action identity and compatibility check; never reuse an unrelated success marker |

Action evidence MUST distinguish planned, started, completed, failed and
uncertain outcomes and retain exact input/action identity and diagnostics.
Authoritative content/selection records still decide installed/selected state;
action evidence records effects, not a second competing selection database.
A success marker alone cannot prove data correctness or durable completion.
Validate postconditions and flush critical state/evidence under a documented
ordering/recovery protocol. General distributed or cross-filesystem atomicity
is not promised. Logs MUST omit secrets and provide a noninteractive diagnostic.

## 6. Scope of the first implementation

Specify/version the handler capability and state declaration formats before
coding them. Start with generation-owned derived output and minimal supported
account/directory/default initialization. Include negative tests for unknown
actions and incompatible state, failure injection and retry/no-op behavior.
Do not introduce arbitrary package scripts or destructive migrations to complete
M1. Their absence is an explicit supported-capability limit, enforced in plans.
The [decision register](distribution-decisions.md) records the remaining design
choices and their implementation gates.

## 7. Concrete first-version policy for review (D3/D4)

Recommended initial scope, not an adopted wire schema:

- Support generation-owned Kernel/profile derived output and minimal
  ensure-account, ensure-directory and missing-default initialization only.
- Each supported action type has a versioned System-owned handler, fixed phase,
  permitted owner/path scope, validated parameters, prerequisites and a
  postcondition. Accept no shell text, arbitrary executable/interpreter path,
  network callback or generic "run" action.
- Action identity binds declaration inputs, handler identity, target installation
  and owning generation/profile. Changed inputs mean a new action. Reuse derived
  output only on exact matching inputs; order prerequisites deterministically
  and reject dependency cycles/conflicting owners.
- Preserve persistent account name-to-UID/GID bindings, validate collisions and
  permitted allocation policy, and record first allocation. An older generation's
  numeric guess cannot override existing account data.
- Ensure only the declared directory, without unsafe symlink following or
  recursive rewriting. Existing owner/mode conflicts block unless the approved
  policy explicitly resolves them.
- Create only a missing declared default; preserve existing divergent content.
  A required configuration change beyond this handler remains unresolved.
- M1 supports schema-compatible transitions and minimal initialization only.
  Unknown required schema/handler/managed-state capability blocks selection.
  Unmanaged data is outside that schema gate; no arbitrary migrator/delete/reset
  action is accepted.
- Specify action/state record formats and durable reconciliation before coding.
  Record completion after validated postconditions. Reconcile interrupted or
  uncertain effects instead of blindly marking them complete.

Boot ordering is: persistent mounts/identity available; validate selected
runtime/managed-state requirements; perform supported account/directory/default
initialization; check postconditions; release dependent services. Required
failure keeps dependents stopped and exposes blocked/degraded readiness.
Independent services and authenticated diagnostics/recovery remain available.
This is a dependency graph, not a requirement to stop the entire OS because one
optional service cannot initialize.

Before selection, both the current manager preparing the deployment and its
selected runtime must understand the required plan/registry/action capabilities.
Writing a new format marker cannot make an older reader support it. A refusal
must identify the missing capability and affected runtime.
