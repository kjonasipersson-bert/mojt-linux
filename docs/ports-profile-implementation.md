<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Ports acquisition and profile publication

This increment advances steps 1–2 of the [six-step consolidation plan](mpm-consolidation-plan.md).
The callable Python core now joins wish reconciliation, exact resolution, actual
provider acquisition, verification and one complete published Ports profile.
It is now wired to installed `mpm` dispatch and shipped in the closed System
runtime; see [ordinary commands and limits](ports-cli-integration.md).
The joined Ports commands use explicit finite source inputs. No MBT syntax or
existing-store migration is introduced.

`mpm_ports_profile.preview` is read-only and returns an exact
`mojt-ports-publish-plan-v1` record bound to root, installation, platform, executor,
target identity, source snapshots and current profile identity. `apply` recomputes
that plan before initialization and again under the stable resource lock. It
imports dependencies before dependents, verifies retained objects and executable
exports, then assembles the next profile. It publishes through the existing
`mpm_transaction.publish` primitive. `current` and `history` provide read-only
inspection. Callers supply already accepted source metadata, a trusted adapter
mapping and operation authorization; the record is not itself permission.

Fresh store layout:

| Path | Meaning |
| --- | --- |
| `store.json` | `mojt-ports-store-v1`, installation identity |
| `.lock` | Stable cooperating writer lock |
| `retained/` | Provider-owned durable retention, outside temporary profiles |
| `profiles/<id>/state.json` | Content-identified `mojt-ports-profile-v1` |
| `profiles/<id>/transaction.json` | `mojt-ports-transaction-v1` |
| `profiles/<id>/bin/` | Complete executable alias set |
| `current` | The single atomic selection pointer |

State binds its target platform and embeds normalized wishes, exact lock/source views, logical installed
versions, declared release/stability evidence and owning claims, dependency receipts, acquisition order, effective
active versions, aliases and monotonic install/activation events. Its parent and
sequence bind history ancestry. History also records before/after identities,
request revisions, added/removed logical references, aliases, actor UID and UTC.
The history reader checks parent content identities, not only sequence numbers.
No separate mutable history append is needed to commit the operation.

An upgrade retains older versions while their owning wish remains. Removing a
configuration releases its claims; independent interactive claims and exact
selections retain their versions. Removal from the logical profile does not
delete bytes, old profiles or provider roots. Historical dependency receipts are
conservatively retained. Collection and reachability compaction remain separate.
A surviving effective default stays selected; fallback chooses a retained
version by committed activation order, then installation order. Wall time does
not decide ordering. Initial unambiguous installation records the chosen wish
as its default; ambiguous versions require an explicit choice.

The complete bin directory has active command names, requested numeric-series
aliases and exact `COMMAND-RELEASE-FULL_REFERENCE_HASH` aliases for retained
logical versions. The full reference hash disambiguates equal versions from
different providers. Conflicting exports, oversized names and management-command
shadowing fail before import. No implicit PATH-wide selection is performed.

Adapter contract: `describe(reference, root)` returns deterministic exports
without fetching/writing; `ensure` acquires and retains an exact object;
`verify` checks retained physical content and identity. Adapter code is explicitly
registered by the trusted caller; catalog entries cannot load executable hooks.
The core depends on this contract, not Nix identity syntax.

`mpm_nix_binary.NixBinaryAdapter` is the first production adapter. Its explicit
`mojt-nix-output-v1` identity binds output, sorted complete closure paths/NAR hashes
and command inventory. It uses a retained absolute `nix-store` helper, realizes
only output paths with local/distributed builds disabled and signature checking
enabled, and creates stable indirect GC roots. Verification compares the exact
closure and registered hashes, runs content verification, and checks exports stay
inside that closure. Neither evaluation nor global activation is involved.
Metadata authenticity and compatible runtime behavior are still separate checks;
multiple retained libc versions do not establish ABI compatibility.

A failed acquisition can leave verified retained objects but cannot select a
partial profile. Pre-publication failure preserves the old pointer; post-rename
flush failure reports `PublicationUncertain` and retains both generations.
Accepted targets advance only for an explicit `advance` claim set; by default
metadata changes preserve them. Exact wishes retain their accepted builds.
Repeated unchanged plans create no profile/history event and fetch no objects,
but still verify retained content. Interrupted fresh-store initialization may
require inspection; no automatic recovery or journal replay is claimed.

Validation runs the request suites, `test_mpm_ports_profile.py`,
`test_mpm_nix_binary.py` and shared `test_mpm_transaction.py`. Profile tests copy
real files and execute the resulting default/series/exact aliases. They cover
upgrade retention, reason removal, explicit overrides, first-install ambiguity,
corruption, stale plans, history tampering and both publication failure phases.
Nix adapter tests simulate its subprocess protocol; **a live Nix import with this
new adapter remains acceptance work**, as do native Port archives, reason/version removal and reset, joined bootstrap/
build flows and hardware acceptance. Frontend/System delivery is now connected. These limits do
not mark steps 1–2 complete or change the order of the six-step plan.
