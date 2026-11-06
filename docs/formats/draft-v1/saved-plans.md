<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Saved exact execution plans and local approval

Review draft. `mojt-execution-plan-v1` and `mojt-execution-approval-v1` are in
the [workflow schema](workflow-formats.schema.json). They define data/contracts,
not a new public MPM/MBT command grammar, an arbitrary script runner or a global
transaction database. Read-only preview may print a plan; explicitly saving it
is a separate caller-authorized output, not implicit target initialization.

## Plan fields

| Field | Meaning |
| --- | --- |
| `target` | Installation identity, exact platform/layout and retained target-identity evidence; do not infer an offline target from the running machine |
| `executor` | Exact retained trusted management runtime/implementation reference; not a caller-supplied arbitrary executable |
| `scope` | Sorted unique affected areas; confirmation cannot enlarge it |
| `baselines` | One exact request-state and authoritative selection ID per affected area; null means verified absence, not unknown/unreadable state |
| `running` | Explicit observed deployment ID or null/unknown; not the mutation baseline |
| `requests_after`, `locks`, `snapshots` | Sorted IDs of complete retained proposed request snapshots, resolution locks and accepted metadata snapshots |
| `steps` | Closed typed operations with exact subjects/records, source/transport binding and dependency keys; no executable text |
| `required_capabilities`, `effects`, `recovery` | Exact handler/format prerequisites, action-set/key/context bindings and retained recovery IDs |
| `outcome`, `blockers` | `ready`, `no-op` or `blocked`; a blocked proposal may explain missing inputs but cannot be approved/executed |

All referenced documents must exist as verified immutable inputs before saved
plan execution. Pointer observations are checked under cooperating resource
locks. A missing/unreadable authoritative baseline is not converted to null.
The target identity evidence includes actual root filesystem/layout binding and,
where relevant, device identity; copying the plan to another root does not grant
authority there. No secrets or host-supplied executable paths belong in a plan.

Request-state origin choices, installed exact overrides, compatibility facts and
state schema/ownership prerequisites are part of preflight. Do not freeze the
entire live database's bytes unless a specific supported action requires that
snapshot. A changed schema/target/baseline/source/policy invalidates authorization
and needs a new plan; normal compatible data writes do not automatically do so.

Refreshing a catalog pointer under an unchanged source/trust policy does not
invalidate a deliberately frozen still-permitted snapshot. Changing the executing
manager/runtime reference requires revalidation/replanning, not silent use of
whichever helper is newest on PATH. Provider adapters stay bound to that runtime.

## Closed step vocabulary

Steps have unique sorted keys and a validated acyclic `after` graph. Execution
uses deterministic topological order, never filename or timestamp order.

| Type | Subject / record / source contract |
| --- | --- |
| `acquire` | Exact reference and accepted snapshot; native reference also binds one archive SHA256, provider acquisition leaves transport null and uses its exact adapter identity |
| `install` | Exact acquired/already verified reference and source snapshot; no activation; all runtime dependencies retained first |
| `prepare-boot` | Exact `mojt-boot-inputs-v2` record, no executable subject/source; produces complete immutable derived boot content, not next-boot selection |
| `retain-requests` | Exact proposed request snapshot, no subject/source; retain immutable candidate data without advancing an authoritative request/selection pointer |
| `publish-profile` | Exact complete profile record, no subject/source; request state/installed choices/aliases/history publish together |
| `select-boot` | Exact complete `mojt-boot-selection-v2`, no subject/source; publish one complete menu/metadata selection |

Unused fields are explicitly null, not ignored. A source-requiring step must
reference a listed snapshot and a compatible locked resolution/offer. Native
hash mismatch cannot trigger automatic alternate encoding/provider. Repeated
references can share acquisition without changing ownership/origin claims.
Dependencies and expected result records must be compatible with the step's
area; a System step cannot silently select a Kernel or Ports profile.

Retaining candidate requests is not committing their adoption. For Ports, the
request roots and history publish inside `publish-profile`. Boot-area roots publish through
the final boot selection record; never publish independent request pointers
that conflict with it. High-level mixed-area plans may have multiple commit
points, with affected areas shown and unchanged fields preserved. They are not
one atomic filesystem/database transaction. A failure may leave a committed
prefix; retain content and report actual authoritative outcomes per area.

An exact selection plan references already complete deployment/profile IDs.
If initramfs/profile output does not exist yet, first create a preparation plan,
then validate a separate finalized selection plan once exact results are known.
Do not insert a placeholder output digest into a supposedly executable plan.
A higher-level operation may orchestrate both, but must expose/authorize their
actual scope and final identities under the established approval policy.

## Approval and execution

Approval binds plan ID, installation, exactly matching scope, actor UID,
authority (`administrator` or `private-owner`) and diagnostic UTC time. Store
it in protected target/owner-managed plan evidence, not an untrusted input file
passed to a privileged helper. A hash/UID field is not proof of authorization;
the trusted manager must create and validate the record under its actual
authorization boundary. Readable plan output alone grants no privilege.

On execution, re-read/verify plan, all referenced bytes, adapter retention and
approval; validate target, exact before pointers, current state/capability and
resource ownership under the existing ordered locks. `-y` cannot override a
pin, blocked plan, new scope or unsupported action. Reusing a stale approval
after anything relevant changed is refused. No new public plan/run flags are
specified here. State-initialization approval binds the exact action context;
this record can satisfy the lifecycle result's `approval` reference only after
that protected validation, not simply because IDs match.

No-op has no steps/blockers and changes no history. Ready plans have no blockers.
Blocked plans have blockers and cannot execute, even if some preparation steps
would have been safe alone. Preparation/import must not claim activation success.

## Storage, interruption and observation

Suggested immutable storage: `state/var/lib/mojt/plans/FULL_ID.json` plus protected
approval objects by full ID. Publish with validated ownership, bounded reads,
canonical write, fsync and non-overwriting publication. Plans/approvals are
retention roots for their exact inputs; expiry/release and physical GC are
future policy. Do not write mutable `executed=true` into the ID-bound plan.

Existing authoritative area records, receipts and lifecycle attempt/result
evidence report progress. On interruption inspect before/after pointers and
state. A matching expected after-state shows that state is visible, not that
this plan necessarily created it. Before-state remaining does not prove no
state effect occurred. Any other state is drift, not an automatic replay target.
Resume/replan requires explicit supported reconciliation; never blindly repeat
uncertain lifecycle effects. Post-rename flush errors preserve possibly committed
content and expose uncertainty. No cross-area automatic undo or data rollback.
