<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native System content installation and status

This implements the first native System installation unit in consolidation step
3. It imports exact ordinary-file native components, validates a generation's
resolved composition and materializes an immutable profile. It does not change
persistent configuration/accounts/data, existing System profiles, services,
Base/Kernel selection, the boot menu or the running System. No package code,
frontend, interpreter or lifecycle handler from the candidate is executed.

## User flow

```sh
mpm system install --from-file /KIT/system-generation.tar.zst \
  --expected-id sha256:FULL_GENERATION_ID \
  --dependency-file /KIT/native-runtime-component.tar.zst --dry-run

mpm system install --from-file /KIT/system-generation.tar.zst \
  --expected-id sha256:FULL_GENERATION_ID \
  --dependency-file /KIT/native-runtime-component.tar.zst -y

mpm system status
mpm system status --verify --json
```

The installed frontend targets its mounted installation disk. Checkout/offline
commands require explicit `--disk-root /TARGET`; `--root` is not an alias for a
different kind of System target. The target must already exist; formatting or
creating an installation belongs to bootstrap. Real numeric-owner installation
requires an administrator. Plain status creates no directories/locks and needs
no archive codec; `--verify` audits retained archives/profile content and may
need administrator access to private files. Explicit offline status does not
attach the inspector host's running identity.

`--dependency-file` is repeatable. A supplied archive must exactly match one
native dependency of the generation and have role `component`. Unrelated,
duplicate or missing components are refused. Already installed exact components
are verified/reused, including on retries. No implicit source/provider lookup,
network fetch, evaluation, build or package-name substitution occurs. Exact
repeat installation verifies retained bytes and writes no new receipt/profile;
the original input archive may have disappeared.

This first join accepts local native files only. Named-source acquisition,
Nix/other provider components, transitive component import, symlink/hardlink
payloads and general lifecycle execution remain explicit later joins. They fail
with a blocker; there is no fallback to another package manager. A distributable
current Nix-backed System needs that adapter join before its owner VM test.

## Package and runtime contracts

The generation is existing native kind `system`, role `generation`, with
`payload/composition.json` and `payload/lifecycle.json`. The composition binding
is the existing metadata format/ID/path reference; descriptor dependencies must
equal its unique exact component references. Original package version, revision,
artifact identity and provenance are retained unchanged. Labels never identify
storage or cause replacement of another build with the same label.

The supported subset of the proposed
[composition wire](formats/draft-v1/system-composition.md) uses native leaf
System components, role `component`, with no unresolved dependencies or outer
requirements. Only root-owned ordinary protected files/directories are accepted.
Their data/modes are verified and write bits removed in storage; private source
files remain private. No mode normalization makes private files world-readable.

Profile mappings must reference listed exact components and safe payload-relative
paths. Destination overlaps, undeclared sources and reserved generated outputs
are refused. Runtime layout currently matches the delivered System contract:
`bin/python3`, `bin/mpm` and `tools`. The interpreter/frontend must be public
executables and the complete declared MPM module set readable. This is a file/
content check, not execution or proof of dynamic-library/ELF compatibility.

Measured `management.json` and the existing System manifest bind the actual
assembled profile and source dependencies. Literal manager support is extracted
without importing candidate Python; the composition cannot overstate it. The
candidate must support its own native System representation. Explicit Base ABI
facts and state layout 1 are mandatory; required host/Kernel capabilities,
managed service schemas and nonempty lifecycle action sets are unsupported in
this first subset. Service/unit declarations are retained/checked as data, not
started or enabled on the host. No readiness or compatibility with a selected
Base/Kernel is inferred from installation.

## Storage and transaction boundaries

All storage uses the common installation UUID and stable locks:

```text
artifacts/store.json
artifacts/system/registry.json
artifacts/system/installed/FULL_ID_HEX/
  artifact.json
  archive.tar.zst
  installed.json
  payload/...
realizations/system/FULL_ID_HEX/
  realization.json
  profile/...
```

The registry is `mojt-system-registry-v1`, layout `system-objects-v1`. Both
component and generation objects use the shared `mojt-install-receipt-v1`, kind
`system`, representation `system-object-v1`. A
`mojt-system-realization-v1` binds installation, artifact, receipt, composition,
measured manifest and dependency receipt IDs. These are independently versioned
records; unknown versions/layouts fail rather than being adopted or migrated.

All incoming bytes are frozen/verified and a temporary profile validated before
target mutation. The writer then reuses the common artifact-store locking and
ordered installation lock, revalidates retained components, publishes complete
immutable objects and finally the complete realization. A failure can retain
complete imported components or a generation object without its realization;
status reports that generation as **retained, not installed**. Retry can finish
from retained inputs. It does not reassign defaults or delete state as an undo.

A post-publication fsync error is uncertainty: retain possibly committed content
and inspect it. Complete receipts/profiles are never overwritten. Abandoned
staging directories and orphan/unrecognized content are diagnosed. Observation
currently bounds the System registry to 256 objects. Profile entry/content and
archive/metadata limits also apply. Physical GC/retention release remains future
work.

## Status and remaining gates

Status lists installed generations separately from retained generation wrappers,
components and incomplete work. Running and next-boot observations come from
explicit runtime evidence/the authoritative boot menu through the same shared
reader as Base. Only an exact installed manifest match identifies a native
artifact. A matching label alone leaves its native identity unknown.

The System registry is also observed by management compatibility checks. An old
candidate without native System format support cannot silently ignore it; an
incomplete import must be completed/diagnosed before a transition. This does not
select the most recently installed generation or write an upgrade wish.

Next: connect supported provider acquisition/retention and current System
payloads, then System-scoped deployment and authorized initialization/service
gating. Generalized boot v2 and the final joined MBT/bootstrap/build flow remain
separate roadmap steps. No new manual A/B/A run is required for native
content-only installation; focused VM acceptance is needed when an actual new
System can be selected and booted.
