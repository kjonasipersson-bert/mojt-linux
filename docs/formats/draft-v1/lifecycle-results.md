<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Lifecycle invocation and result registry v1

Review draft. [Schema](lifecycle-result.schema.json),
[started example](examples/lifecycle-result-started.json),
[completed example](examples/lifecycle-result-completed.json).
Common encoding/limits are in [README](README.md).

## Authority and identities

Content/selection records remain authoritative for installed/selected/running
state. This registry records action attempts and evidence only; a completion
event cannot select a profile or override the boot menu. No global transaction
database or independently maintained success index is required.

`context` contains stable installation identity, `scope`, exact `subject` and
`owner`. Owner is the native owning artifact ID, never an executable path.
Scopes are `preparation` (subject hashes frozen construction inputs excluding
generated outputs), `deployment` (complete already-published boot deployment),
or `profile` (complete already-published profile). Definitions and output
inventories must not contain result IDs that would create a hash cycle.

`handler` contains type/version and an exact native/provider implementation
reference from the trusted executing System. It must match the declared action
and that runtime's supported capability. The invocation ID is SHA256 of canonical:

```text
{format: mojt-lifecycle-invocation-v1, context: CONTEXT,
 action_set: SET_ID, action_key: KEY, handler: HANDLER}
```

This binds exact declaration inputs via the set ID without including wall clock,
attempt number or a live-data digest. Changed owner/subject/set/handler changes
invocation identity. `approval` identifies retained authorized execution-plan
evidence bound to those inputs and scope. A hash supplied by an untrusted caller
does not itself authorize root execution; use the manager's protected approval
boundary. The proposed [saved plan/approval wire](saved-plans.md) now defines
those records. Its scope/target/plan/context validation must actually be
implemented; a matching reference alone is still not authorization.

## Storage and order

Proposed target state path, separate from immutable artifacts:

```text
state/var/lib/mojt/lifecycle/v1/INSTALLATION_HEX/
  INVOCATION_HEX/.lock
  INVOCATION_HEX/RUN_HEX/000001.json
  INVOCATION_HEX/RUN_HEX/000002.json
```

Run is a fresh random 32-hex attempt identifier, not an event counter. Each
record is immutable and its `sequence` equals the six-digit filename. The first
has `sequence: 1, previous: null`; each later record references the immediately
previous full result ID and increments sequence by one. No gaps, forks or
reused run identifiers. `recorded_utc` is diagnostic UTC with Z, not ordering
authority. A clock adjustment cannot reorder effects. No mutable latest pointer
is needed: scan/validate the bounded run directory. Refuse invalid/oversized
chains; report them without deleting or guessing a terminal state.

Serialize writers by the stable per-invocation lock, ordered with other required
resource locks. Root-managed state is protected from ordinary users/unsafe
ancestors. Extra account/service writers need their own coordination. Random
run order cannot tell which of two attempts happened last: under lock inspect
all unresolved attempts, reconcile them and current postconditions before
retrying. Multiple unresolved attempts or inconsistent bindings require explicit
diagnosis; never choose the lexically largest UUID as "latest".

## Fields and result semantics

All fields in the schema are mandatory. `observed_state` records actual managed
owner/path/family/version observations and evidence identities. `bindings`
records actual account UID/GID bindings, sorted by name; it cannot reset passwd.
`checks` holds named postconditions, result and sanitized factual evidence.
Unknown/incomplete checks cannot satisfy required postconditions.

Each check includes handler-validated `facts`. Its `evidence` ID is SHA256 of
canonical `{format: mojt-action-check-v1, name, result, facts}`; retain those facts
in the record, not just a dangling success hash. Null evidence is allowed only
for failed/unknown checks with no established facts, never required success.
Initial handler facts are closed per handler:

| Handler / check name | Exact fact fields |
| --- | --- |
| `ensure-account` / `account-binding` | `name`, `group`, `uid`, `gid`; numeric values match recorded bindings |
| `ensure-directory` / `directory-state` | `namespace`, `path`, `uid`, `gid`, `mode`, `type: directory` |
| `missing-default` / `default-state` | `namespace: etc`, `path`, `outcome` is `created` or `preserved`, `sha256`, `uid`, `gid`, `mode` |
| `kernel-derived` / `kernel-derived` | `inventory`, `binding` full content IDs |
| `manual-index` / `manual-index` | `input_profile`, `output_index` full content IDs |

Fact paths/integers follow the common path/UID/mode rules; a default hash is
raw SHA256. Empty facts are allowed only for failed/unknown checks. All other
unknown fact shapes are invalid, not arbitrary trusted probe output. A handler
must compare observed facts with the declared action before claiming success;
the check digest alone does not establish that comparison or an actual probe.

| Status | Permitted transition / interpretation |
| --- | --- |
| `started` | First record, before effect; empty checks/error; durable intent, not proof any mutation occurred |
| `completed` | From started only, sequence 2; nonempty all-passed required checks, verified bindings/postconditions and null error |
| `failed` | From started only; non-null error; effect may have partly occurred, so inspect before retry |
| `uncertain` | From started only; non-null error; cannot establish whether effect/postconditions committed |
| `blocked` | First record only, before effects, non-null error explaining failed prerequisite |

Terminals are immutable; a retry creates a new run, not a contradictory event
after completion. Plans write no result records. "Planned" exists in plan output,
not as a persisted claim of execution. Status reading never fabricates a stored
`uncertain` record; a durable started record without a terminal is displayed as
interrupted/uncertain and requires reconciliation by an authorized writer.

## Durable publication and recovery protocol

1. Under lock, validate installation/context/action/handler/approval and actual
   prerequisites. Check prior attempts/current postconditions before new effects.
2. Publish started intent through exclusive temp creation, canonical write,
   file fsync, non-overwriting final publication and run-directory fsync. Flush
   newly created parent/run directories to their parents too. If this fails or
   may have committed, do not start the effect; preserve/report uncertain intent.
3. Execute the known handler. Validate postconditions and flush critical state
   through that handler's protocol. Account-family operations require consistent
   passwd/group/shadow handling and locks; a generic JSON rename cannot provide it.
4. Publish terminal evidence with the same ordered durable protocol. A terminal
   fsync error is publication uncertainty, not a guaranteed action rollback.
   Do not remove selected content or assume data did not change.

Use no-overwrite publication under the lock and refuse an existing sequence
slot; do not replace an old event. Abandoned `.result-*` temps are incomplete
diagnostics, never successful records. Failure after state mutation but before
terminal publication leaves uncertain execution: a retry inspects actual state
and postconditions. For safe ensure-actions it may converge under the same
invocation in a new run, recording what it observed. This is not permission to
repeat arbitrary non-idempotent migrations. A prior completion must be checked
against relevant present state before treating a later request as satisfied;
manual edits cannot be hidden by an old success marker.

Ready status for a deployment is derived from the selected/runtime context and
all required supported action postconditions. Selected, running and ready stay
separate; timestamps/receipts alone prove none of those independently. A required
failure keeps dependent services stopped but diagnostics available. Protect prior
recovery content, and validate live managed-state compatibility before reselect.
No password/secret material, raw shadow data or unbounded command output may be
written into facts/errors. Hash chains detect corruption, not malicious root
tampering or publisher authority. No across-filesystem atomicity is promised.

