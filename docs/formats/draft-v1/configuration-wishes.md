<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Configuration, interactive wishes and exact resolution

Review draft, not new MPM syntax or a deployed metadata change. This records
the owner's approved direction: a configuration provides a declarative starting
point; later interactive installations/choices survive its reapplication. All
wire definitions are in [workflow schemas](workflow-formats.schema.json), using
the existing [encoding rules](README.md). MBT command syntax remains deferred.

## Editable input

The filename is illustrative; `name`, not the filename/path, identifies the
configuration source. A [small TOML example](workflow-examples/mojt-configuration.toml):

```toml
format = "mojt-configuration-v1"
name = "workstation"

[ports]
source = "local"
packages = ["hello@2.12"]

[ports.active]
hello = "hello@2.12"
```

Strict TOML 1.0, no includes, environment substitution, code evaluation, datetime
or float values. Unknown keys/tables fail. The `config_document` schema defines
the parsed shape: required format/name, optional base/kernel/system/ports.
Base uses `selector` and optional `source`; System uses `packages` and optional
source; Ports also permits an `active` map. Packages are ordinary selectors,
not backend attribute paths. Bare names mean latest eligible stable, `@3.12`
follows the numeric series, `@=VERSION` is exact release, not necessarily a unique
build. Nonnumeric versions remain exact-only without a supported version adapter.
Ambiguous same-release builds need existing explicit preference or a full-ID
lock; do not guess. Do not broaden catalog/source selection by search ranking.

Kernel uses `policy: pinned|latest-lts|latest-upstream`; pinned specifies exactly
one of `series` or `release`, others specify neither. Selected Base bounds and
all deployment gates constrain it; incompatible pin/no eligible LTS fails.
This is the existing three-policy model, not automatic upstream/RC adoption.
Base is a complete release, System a coherent generation; their package wishes
do not imply live per-file updates. A System role cannot silently select two
conflicting component versions; require a compatible explicit effective choice.

An omitted source must resolve through an explicit configured area default or
existing binding; ambiguity is an error, never automatic Nix/provider lookup.
Plans show chosen named sources/snapshots. `active` names canonical package roles
and must refer to a compatible explicit requested selector for that role. It
does not create another implicit install wish. Two configurations declaring
different active choices require an explicit choice; order of filenames is not
precedence. An existing explicit interactive override is preserved and shown.

Normalize package arrays as sorted unique selectors, active keys by name and
Kernel fields explicitly before computing a semantic configuration revision:
`digest(normalized parsed document)`. Retain that normalized document. Comments,
TOML formatting and package ordering do not change intent. Do not normalize an
already ID-bound saved record while validating its identity. Unsupported syntax,
unreadable/missing file or parse error is not an empty configuration.

## Per-area request state

`mojt-request-state-v1` binds installation/area plus:

| Field | Meaning |
| --- | --- |
| `configurations` | Named adopted semantic revisions and complete normalized documents, sorted by name; retaining the document preserves masked declarative choices |
| `claims` | Independent directly requested wishes with source and origin, sorted by full claim key; no resolved artifact in a floating wish |
| `selections` | Effective active-choice intent per role, sorted by role: follow a claim or pin an exact already installed reference; origin remains explicit |

Claim key is `digest({format: mojt-request-claim-v1, area, origin, role, source,
policy})`. Origin is `{kind: configuration|interactive, name: NAME}`. A
configuration claim names an adopted configuration, an interactive claim names
the interactive channel. Actor UID belongs to transaction/approval evidence,
not an invented package owner. Same normalized origin/wish is one claim; an
explicit interactive install of already configured content adds its independent
claim even if no new bytes are needed. That is a reason change, not a content
upgrade. Never infer an interactive claim merely because a dependency is present.

Configuration packages replace only that named source's claims in the affected
area. Remove its no-longer-present claims, preserve other sources and interactive
claims. A full-file reconciliation includes areas previously owned by this
configuration even if a table was removed; a first-time absent area is untouched.
The plan enumerates all affected areas. Partial-area application is explicit
and records adoption separately per area. Forgetting a missing file's claims
requires an explicit plan, not an I/O error being interpreted as removal.

Dependency reasons are graph edges from retained roots, not a manually maintained
`dependency=true` flag. Running/selected/recovery/build-environment references
protect content independently of current direct claims. Removing the last direct
claim may remove a Port from the current profile/aliases, with normal fallback
among still-installed eligible versions. It never physically deletes shared
dependencies, historical artifacts, user data or selected/running boot content.
An explicit exact selection is itself a retention root, including when the
configuration claim that first installed it disappears.

## Effective choices and interactivity

The configuration's choice applies until an explicit interactive activation.
Installing a further version does not itself change active selection, preserving
existing MPM rules; first-install convenience remains visible in the plan.
Interactive activation changes selection origin and protects the chosen content;
it does not erase the configuration's still-valid package wish. Reapplying or
editing the configuration cannot silently undo that override. Report desired
versus effective differences. Returning to configuration control is explicit;
its command spelling is not added here. Clearing an override with no remaining
configured choice uses the existing installed fallback/conflict rules in a plan.

Following a selector interactively creates/reuses an interactive claim for that
selector; it must not leave an active request pointer owned by a configuration
that can later delete it. An exact interactive selection is an independent
retention root. Merely installing a dependency never creates either override.

Configurations, exact selections and claims do not imply cross-area changes.
For System, combining effective wishes produces a new immutable composition;
current services stay unchanged until the selected boot. Kernel/Base overrides
likewise change only their explicit scope. A rollback does not revert accounts,
interactive wishes or shared data to an old snapshot merely because old code runs.

## Resolution lock

`mojt-resolution-lock-v1` binds target/area, one exact request-state ID, sorted
snapshot IDs and sorted resolutions by claim key. Each resolution names basis,
snapshot/evidence, exact native/provider reference and sorted unique dependencies.
`catalog` basis names an accepted snapshot and its evidence; `installed` basis
has null snapshot and a verified retained install/profile record as evidence.
This permits offline activation from installed content without a live catalog.
Native artifacts never become provider objects because their version looks equal.

Cover every effective claim being resolved exactly once; same target referenced
by two origins can share bytes, not erase either origin. Exact overrides are
validated/retained separately even if not a claim target. No unavailable payload
is called installed. A lock pins actual builds; later metadata refresh leaves
it unchanged. Explicit re-resolution/upgrade may create a new lock under existing
wish policies; an exact pin remains pinned. Changed request/source/target input
requires a new lock, with before/after visible. Locks are data, not shell code.

Publishing requests follows area authority: Ports profile/state/history share
one commit; selected boot metadata carries the relevant Base/System/Kernel
request-state roots. Do not add a global independently updated intent database.
Use an explicitly versioned initial Ports profile/state format binding
request/lock/provider state and history in one commit. Support or migration of
experiment formats 1/2/3 is not required. Refuse unknown versions before writing;
do not add an independently updated loose origin sidecar. See the
[initial-format policy](../../format-policy.md).
