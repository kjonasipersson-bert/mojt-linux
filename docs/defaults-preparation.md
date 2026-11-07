<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Explicit missing-default preparation

This is an internal, bounded library increment in consolidation steps 2/3.
`tools/mpm_defaults.py` implements one known ensure-file operation, before the
native System installation/deployment join. It is delivered with new System
management runtimes but has **no public MPM/MBT command or automatic caller**.
Existing images are not patched. Base/Kernel import, Base staging and selection
remain content/boot operations; they do not invoke this library or write `/etc`.
The Base staging `existing-defaults-only-v1` gate is unchanged.

## Supported operation and authority

`prepare(root, base_id, paths)` reads an already installed exact native Base and
its verified rootfs realization. The explicit paths must name ordinary files
under that Base's `usr/etc`; the Base manifest has the established add-missing
configuration policy. Every source is bound by exact artifact, realization,
relative path, content SHA256 and numeric mode/ownership. No recursive discovery
or provider executable is an action. Limits: 64 unique paths, 1 MiB per file,
64 KiB per plan/result, 128 attempts per invocation.

The plan also binds installation identity, canonical target path and the actual
root, persistent `/etc` and persistent management-state directory device/inode
pairs, plus the executing manager's exact code reference. A copied plan does
not authorize another target or a changed manager. Plan construction and status
create no default, registry or lock. Source verification may require root access
to the protected Base realization; this is not an ordinary-user CLI promise.

`initialize(root, plan, yes=True)` is for a trusted administrator caller, not a
privileged JSON service. It requires actual effective UID 0 and explicit
consent, rederives the whole plan from retained content/current protected target,
then repeats validation under existing ordered Base/install locks. The root
caller authorizes exactly those literal paths and the preserve-existing policy.
A supplied hash, root-looking UID field or saved JSON alone grants no privilege.
No package scripts, commands, network operations or dynamic hooks execute.

Parents must already exist and be root-owned, protected directories. No-follow
dirfds confine traversal; symlinks, hardlinks, special files, unsafe ownership,
group/world writes and oversized files block the operation. Existing safe local
regular files are preserved byte-for-byte, including their modes. Parent
creation/ownership and service accounts need separate known handlers. Account
databases, machine identity and `os-release` are explicitly outside this handler.

## Durable effects and observation

A complete protected temporary file is written, chowned/chmodded, and fsynced.
An atomic **non-overwriting** hardlink publishes the missing destination; a
concurrent local writer wins. No truncation, replacement rename, overwrite,
removal or inverse operation is used. The temporary link is removed and the
parent is fsynced. Postconditions re-read actual bytes/metadata and flush the
file/parent before completion evidence. Failure after link is publication
uncertainty: retain the visible file, report it and never pretend to undo it.

Protected, versioned evidence lives separately from content and boot selection:

```text
state/var/lib/mojt/lifecycle/defaults-v1/INSTALLATION_HEX/INVOCATION_HEX/
  .lock
  plan.json
  approval.json
  RUN_HEX/000001.json
  RUN_HEX/000002.json
```

Records use the normal `{format, description, id}` envelope. The full ID hashes
canonical `{format, description}`. The narrow supported formats are:

| Format | Description fields |
| --- | --- |
| `mojt-defaults-preparation-v1` | `installation`, exact Base `owner`, `realization`, `target`, `handler`, sorted `actions` |
| `mojt-defaults-approval-v1` | exact `plan`, `installation`, `invocation`, `authority: administrator`, actual `uid: 0`, `scope: missing-default-preparation`, `target` |
| `mojt-defaults-result-v1` | `invocation`, `plan`, `approval`, random `run`, integer `sequence`, `previous`, `status`, diagnostic UTC `recorded_utc`, `checks` |

The invocation hashes `{format: mojt-defaults-invocation-v1, plan: PLAN_ID}`.
It contains no timestamp, random attempt number or live-data digest. Approval is
created by the root caller under protected locks and must exactly match the
revalidated plan/target. It is local authorization evidence, not publisher
signature verification.

Sequence 1 is durable `started` intent, empty checks, `previous: null`. Its file
and new parent directories must be flushed **before** effects. Sequence 2 is
`completed`, linking the exact started ID, with one passed `default-state` check
per declared file. Facts contain only namespace/path, `created` or `preserved`,
SHA256 and actual uid/gid/mode. Evidence IDs use the proposed closed
`mojt-action-check-v1` fact encoding. No file contents or error output are logged.
Final records are never overwritten; incomplete `.result-*` files are diagnostics.
Read-only status scans bounded chains, validates bindings/digests, and observes
current files without declaring a deployment ready. Random UUID/time ordering
is never used to choose a "latest" result.

Exact repetition with satisfied current evidence writes no new event. A local
edit is preserved and reobserved on the next explicitly authorized operation;
a historical completion does not hide it. Missing terminal evidence is reported
as interrupted, without fabricating a stored failure or guessing rollback.
A normal retry refuses it. A root caller may explicitly request
`reconcile=True`: exactly one validated started attempt may resume this known
idempotent ensure-file operation, inspect current files, preserve existing bytes
and append completion to that same intent. This is **resume of one incomplete
attempt**, not replay of arbitrary migrations. Empty attempts, multiple unresolved
attempts, malformed chains and abandoned evidence temps require diagnosis.
Nothing is deleted to conceal incomplete work.

## Boundaries still to implement

These deliberately named narrow formats do **not** claim implementation of the
[general lifecycle](formats/draft-v1/lifecycle-results.md) or
[saved execution-plan/approval](formats/draft-v1/saved-plans.md) wires. In
particular, generic action DAGs, state-owner declarations, complete selected
System lifecycle execution, actual service-schema observation, generic retry runs,
required-service gating and ready status remain unimplemented. A later adapter
must validate those full contracts, not treat the narrow approval ID as generic
execution authority. Unknown format versions are refused; no migration/adoption
of these experimental records is promised.

The next System join must explicitly decide when initialization is authorized
and which required services wait for its postconditions. Installation/staging
still cannot silently apply defaults. A completed action never selects a boot
entry, changes a running deployment, proves compatibility or restores old data.
There is no atomic transaction spanning state files, evidence and boot selection.

## Validation

`tests/test_mpm_defaults.py` uses real native Base archives/rootfs realizations
for root effect tests: missing creation, preserved/edited configuration, exact
no-op, source modes, target binding, unsafe links/conflicts, durable intent,
pre/post-effect interruption, explicit reconciliation, post-link/fsync
uncertainty, concurrent writer, corrupt evidence and bounded reads. The focused
CI job runs both ordinary-user contracts and root effect tests. Existing Base
install/stage tests continue to prove those paths leave persistent defaults
untouched. This increment requires no repeated unchanged owner A/B/A VM matrix;
actual System/boot initialization integration will require focused VM acceptance.

The subsequent [management capability gate](management-capabilities.md) measures
the bundled preparation support and reads known registry metadata independently
of the current handler implementation hash. It blocks unknown/unfinished
registry state before a transition. This is a read-only compatibility join,
not automatic defaults execution or generic schema/service readiness support.
