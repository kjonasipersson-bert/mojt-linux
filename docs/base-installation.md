<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Exact Base installation and status

First implementation of the [owner-agreed Base contract](mpm-base-contract.md),
2026-11-06, in PR #40. Installation means retained exact content **and** a
validated rootfs realization. It changes neither machine configuration nor boot
selection. Existing-disk Base boot staging/selection is the following increment.

## One target and two inputs

In a newly assembled System, `mpm base` defaults to its mounted installation disk.
The checkout frontend requires an existing explicit `--disk-root DIRECTORY`.
The same option on the installed frontend selects an offline target and never
attaches the inspecting machine's running record. Global `--root` is rejected
for Base; it is not silently interpreted as a different kind of directory.

```sh
mpm base install --from-file /packages/base-EXACT.tar.zst \
    --expected-id sha256:FULL_ARTIFACT_ID --dry-run
mpm base install --from-file /packages/base-EXACT.tar.zst \
    --expected-id sha256:FULL_ARTIFACT_ID -y
mpm base install --source local --expected-id sha256:FULL_ARTIFACT_ID \
    --archive-sha256 FULL_ARCHIVE_SHA256 --dry-run
mpm base status
mpm base status --verify --json
```

The IDs above are placeholders, not runnable example values. Source install
also supports `--snapshot`, `--sources-root` and `--cache-root`, with the same
meaning as the existing Kernel source input. It holds the accepted source
binding through cache verification and final installation. Source preview reads
only frozen metadata, not the payload. Local preview freezes/verifies the wrapper
and audits the nested rootfs in temporary scratch space, without target writes.
No implicit refresh, source build, default merge, account setup or boot change.

Successful realization requires root to preserve numeric ownership and reviewed
Unix metadata. Mutation requires administrator authority; read-only status needs
only access to the records it inspects. Required dependencies/requirements beyond
this first self-contained Base subset are rejected before publication.

## Content, representation and publication

The first adopted subset uses the dedicated store marker
`mojt-artifact-store-v1` (`kind-id-v1` layout, new installation UUID). No experimental
store is migrated or silently adopted. Paths under the target are:

| Path | Meaning |
| --- | --- |
| `.artifact-store.lock` | Stable target initialization/Base writer lock |
| `artifacts/store.json`, `artifacts/.lock` | Store identity and shared object writer lock |
| `artifacts/base/installed/FULL_HEX/` | Exact descriptor, original archive, `mojt-install-receipt-v1`, normalized wrapper payload/provenance |
| `realizations/base/FULL_HEX/tree/rootfs/` | Realized rootfs, preserving reviewed ownership, modes, links and xattrs/ACLs |
| `realizations/base/FULL_HEX/realization.json` | `mojt-base-realization-v1` binding installation/artifact/receipt, compressed inner digest, measured inventory, constructor code and GNU tar identity |
| `.install-*` siblings | Incomplete work, not an installed Base |

Receipts use canonical format/description IDs. Their trust is either explicit
local-file input or the existing exact registered-source/cache observation.
`manager` is a `mojt-manager-code` reference to the exact management source files,
not an invented native System artifact. The retained System continues to own its
management Python/helpers. These are versioned implementation records; they do
not claim the entire draft storage/lifecycle/deployment architecture is implemented.

Wrapper publication precedes realization publication. Failure can leave retained
verified content, which status labels **retained, not installed**. A sealed,
verified realization is published by a separate atomic directory rename. A
post-rename flush failure is publication uncertainty; potentially published
content is retained. An exact repeat verifies retained content, preserves receipts
and needs no original archive. Source repeats preserve their original acquisition
observation; the accepted registration/policy binding must still authorize use.
No physical garbage collection or automatic incomplete-stage cleanup is added.

The rootfs's own metadata is preserved. A separate root-owned `tree/` container
with mode 0500 protects it while not booted, including intentionally writable Unix
paths such as `/tmp`. Public realization metadata remains readable for ordinary
status; `--verify` requires access to the protected tree. The future boot path can
bind the exact rootfs read-only while applying the usual runtime state mounts.

The shared native I/O primitives are reused by Kernel import. The Base path
reuses the directory installer's manifest/audit/rootfs validation and sync policy,
not its state-preparation or `base/current` operations. GNU tar performs the
reviewed extraction and comparison. The nested archive has explicit decompression,
header-count and numeric-metadata bounds. Package code is never executed.

New System payload preparation includes GNU tar from the same pinned source.
The closed management runtime retains `tar` beside `zstd`; a missing helper is
a prerequisite error before installation writes. No fallback to a Ports program
or mutable host PATH is used by the installed frontend. Old exported payloads
must be prepared again; publishing this code does not upgrade a running System.

## Status and current limits

Status reports full IDs in JSON and leads human output with Running, Next boot
and Installed. It reads supported native boot metadata without importing a
provider or rehashing Kernel/module payloads. A managed menu must agree with its
exact sidecars; a live fresh-native baseline must match the complete generated
menu. Missing authoritative observations stay unknown. Explicit offline status
never treats the inspector's running Base as the target's identity.

A boot-observed Base that predates the new store is reported as not installed
in this store; it is not silently imported by matching its version. Default
integrity means verified at installation; `--verify` rechecks retained archives,
wrapper and rootfs inventory. Unsupported/corrupt required records fail visibly.
Status creates no store, target, lock or selection and performs no cleanup.

The new Base trees are not yet boot targets. Catalog selectors, persisted Base
upgrade wishes, `base upgrade`, generalized deployment, lifecycle/defaults
preparation and System import remain subsequent roadmap work. MBT public syntax
remains deferred; bootstrap must reuse these installation functions.

## Validation

`test_mpm_base.py` uses real native and nested tar/zstd archives, explicit target
state/boot sentinels, source/cache fixtures and isolated delivered frontend copies.
It covers read-only/offline inspection, malformed paths/archives/identity, bounded
expansion, same-label build coexistence, full content realization, original-byte
independent repeats, corruption, partial publication/retry and publication
uncertainty. Real root ownership/extraction cases run under sudo in focused CI.
This is not a VM boot claim; the next owner boot gate accompanies changed-Base
deployment support.
