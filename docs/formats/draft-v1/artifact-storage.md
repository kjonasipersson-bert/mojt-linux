<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native artifact storage and install receipts v1

Base readonly-tree/receipt subset implemented in PR #40; other category and
deployment joins remain drafts. See [Base implementation](../../base-installation.md).
[Marker schema](artifact-store.schema.json),
[receipt schema](install-receipt.schema.json), [common rules](README.md).

## Dedicated new-store layout

New installations may use a dedicated `STORE`, proposed as `DISK/artifacts`:

```text
STORE/store.json
STORE/.lock
STORE/KIND/installed/FULL_ARTIFACT_HEX/artifact.json
STORE/KIND/installed/FULL_ARTIFACT_HEX/archive.tar.zst
STORE/KIND/installed/FULL_ARTIFACT_HEX/installed.json
STORE/KIND/installed/FULL_ARTIFACT_HEX/payload/...
STORE/KIND/installed/FULL_ARTIFACT_HEX/provenance/...
STORE/KIND/installed/.install-RANDOM/...
```

Kinds are exactly `base`, `system`, `kernel`, `port`. Use full digest hex, not
release labels or filename prefixes. Different builds of Base 0.1.3 live beside
each other; a label is not a unique directory name. The archive's `./KIND/`
namespace is stripped only into this private object representation, never `/`.
`store.json` identifies `mojt-artifact-store-v1`, `kind-id-v1` and a generated
32-hex installation identity. Initialization is explicit, not a side effect of
status. New-target clones get their own installation identity; updates retain
it. It is not the Linux machine-id or a filesystem UUID.

Implement this layout on a fresh installation. Do not build an adapter or
migration from experiment Kernel/Base/System stores. Unknown markers and unsafe
nonempty roots fail rather than being adopted. Prototype paths are historical
inputs, not a backward-compatibility obligation. See the
[initial-format policy](../../format-policy.md).

## Installed object versus usable runtime

`artifact.json` remains the original byte-identical canonical native descriptor.
`archive.tar.zst` is the verified original representation. `installed.json` is a
local receipt, not a modified descriptor, publisher signature or boot selection.
The receipt binds installation/kind/artifact, exact retained archive hash/size,
representation, direct dependencies, local trust decision, installer UID/time
and exact manager reference. These fields are all required by the schema.

`dependencies` equals descriptor dependencies, with unique canonical references.
`trust.expected_id` equals `artifact`. The first Base implementation supports `explicit-local-file` and the existing
`registered-native-source` observation. The latter includes the complete cache
verification record and is checked against the exact artifact/encoding. The
initial, previously unimplemented v1 draft schema now specifies that optional
acquisition evidence and requires it for registered-source trust. This is not
remote authentication/D7, nor a migration of experimental Kernel receipts. Provider dependencies remain in their own stores;
reference them exactly rather than relabelling provider objects as native.
Retain their complete closures/roots before publishing the installed object.

| Representation | Meaning |
| --- | --- |
| `archive-only-v1` | Retained descriptor/archive/receipt, no claimed extracted payload; may be installed content but is not itself a usable profile or Base runtime |
| `readonly-tree-v1` | Additionally materialize regular files/directories safely; owner is installer, directories 0555, files 0444 plus original execute bits; no applied setuid/setgid or package numeric ownership |

The initial readonly-tree subset rejects symlinks, hardlinks, special nodes and
unsupported metadata before publication, as current Kernel extraction does.
Descriptor/archive preserve original modes/owners. This generic future policy
does not relabel existing `readonly-kernel-tree-v1` receipts. A Base runtime
requires a separately validated [realization](base-realization.schema.json) of its nested rootfs archive,
preserving appropriate target metadata under a reviewed extractor policy.
Nix runtime paths remain unchanged. Do not claim relocation from storage alone.

Generation-owned runtime realizations may live outside the generic store under
their versioned layout. They bind exact source/representation/assembler inputs
and measured inventory; copying a tree alone is not such evidence. Boot/profiles
must reference the validated realization, not guess executable paths from labels.

## Publication, integrity and concurrency

Validate registry ownership/ancestors and reject symlinked/unsafe store paths.
Use exclusive staging, no-follow reads and bounded streaming archive validation.
Freeze approved input before extraction and verify all hashes again. Prepare
descriptor, archive, receipt and optional materialization completely, fsync files
and child directories, normalize read-only modes, then rename the complete stage
to its final full-ID directory and fsync the containing directory. Source paths
are not retained as authority. Same exact object on repeat is verified and a
no-op preserving its original receipt; damaged content is an error, not overwrite.
Different archive encodings of the same artifact do not replace its first
retained transport/receipt. M1 chooses one verified representation per artifact.

The new store lock is stable and resource-ordered with existing area/boot locks;
all new-store writers and deployment readers must participate. Do not remove
or replace locks. No claim that today's legacy Kernel lock alone coordinates
this future store. Adapter retention roots and the store receipt need not share
an atomic commit: first retain dependencies, then publish the object. Failure
may leave extra roots, not a falsely complete dependency graph. GC is deferred.

Before rename, old installed content and selection remain unchanged. After a
rename followed by failed fsync, preserve possibly published content and report
uncertainty. Read-only status reports `.install-*` as incomplete, never installed;
it does not delete/adopt them. A complete installed receipt claims verification
at installation, not a fresh integrity scrub. Explicit verification checks the
archive, descriptor, materialized inventory and still-retained dependency closure.
Installation never implies readiness, a selected deployment, or a running build.



## First Base implementation boundary

Base uses this store marker and readonly wrapper/receipt representation, with a
separate `realizations/base/FULL_HEX/rootfs` plus `realization.json`. It publishes
complete store initialization atomically under the stable target
`.artifact-store.lock`, then uses that lock and `STORE/.lock` for Base writes.
The realization receipt binds the generic object receipt and a measured inventory,
including target ownership/modes, xattrs and hardlink relations. It also binds the
manager-code reference and exact GNU tar executable used by the reviewed extractor.
The manager provider is `mojt-manager-code` with source-file hashes, not a falsely
claimed native System artifact. Required future manager capability checks still
belong to System/deployment integration.

Only both complete representations count as installed Base. A verified wrapper
without a rootfs is retained content; `.install-*` work is incomplete. The two
publications do not atomically initialize persistent machine state; this path
never runs state initialization, changes current links or selects a deployment.
No generic Port/System installer or migration of the existing Kernel registry is
claimed by adopting the marker/receipt subset here.
