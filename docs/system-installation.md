<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native System content installation and status

Native System installation imports exact components with controlled profile
links, validates a generation's resolved composition and publishes an immutable profile. It does not change
persistent configuration/accounts/data, existing System profiles, services,
Base/Kernel selection, the boot menu or the running System. No package code,
frontend, interpreter or lifecycle handler from the candidate is executed.

Component-based generations project retained payloads through controlled links;
materialized generations remain supported. See [component profiles and optional
firmware](system-components.md) for the storage and input-validation contract.

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
are reused through their protected metadata, including on retries. No implicit source/provider lookup,
network fetch, evaluation, build or package-name substitution occurs. Exact
repeat installation reads retained metadata and writes no new receipt/profile;
the original input archive may have disappeared.

The generation and its direct components are local native packages. A native
component may now declare exact provider runtime dependencies in its descriptor.
The core retains opaque provider identities. The installed Nix adapter realises
binary outputs with builds disabled, signature enforcement enabled and roots
under `retained/nix/`. Its normal System install path propagates helper errors
without querying/hashing the whole closure or running `--verify-path`. Ports'
existing adapter protocol and verification behavior remain unchanged. Expected
hashes do not authenticate a publisher.

Provider descriptions are checked before approval. Required binary acquisition
and root registration happen under installation locks after approval. An
interrupted provider import leaves complete native inputs retained, and an
explicit retry can finish from them. Repeating a completed install neither
acquires nor scrubs provider content. `install --verify` explicitly audits
payloads, retained objects, profile content and provider closures. Plain status
needs no provider; `status --verify` also audits dependencies.

The CLI currently permits provider operations only for the running installation,
using its retained `nix-store` helper. An explicit offline target cannot silently
import into or inspect the host's unrelated Nix store. Native-only offline
install/verification is unchanged. Other providers need an explicitly supplied
adapter; no fallback to another package manager occurs.

The [System packager and source/cache join](system-packaging.md) now preserve
profile symlinks and package a completed current profile with exact dependencies.
Named-source installation acquires the complete native bundle from one accepted
snapshot. Direct provider profile mappings, transitive native component import,
hardlinks and lifecycle execution remain later joins. Packaging/import does not
prove ELF/libc compatibility or boot readiness.

## Normal transaction and verification

A normal live installation consists of content installation followed by automatic
boot preparation. These are separate publication boundaries: if preparation
fails, installed content remains available for an explicit retry, and the next
boot choice stays unchanged. `--content-only` stops after content installation.

Mutating content installation creates scratch space through the target disk's own path, rather than
`TMPDIR`. This allows completed private imports/profiles to be renamed into their
publication stages, including when `/var` is a bind mount of the same disk.
Required archives and independent profile files are still written and synced.
The private workspace is anchored to an open target directory through cleanup;
a replaced target is refused without cleaning an unrelated replacement tree.
Read-only previews use external temporary space and do not require target writes.

Boot preparation acquires the cooperating store, installation, Kernel, boot and
existing Ports locks once. It reads the selected context and creates one
compatibility plan, validates the exact boot inputs, then constructs, retains and
admits the prepared entry under those locks. Internal construction/storage steps
consume the checked inputs; they do not rebuild the transition plan. An
interactive preview is outside the write transaction and its approved identity
must still match when the transaction starts.

| Boundary | Checks |
| --- | --- |
| Incoming content | Archive identity, bounded safe paths/types/links, composition and dependencies |
| Locked boot planning | Base/Kernel/System identity and compatibility, providers, startup/state/default and management requirements |
| Construction and retention | Exact constructor/runtime inputs and generated boot bytes; durable immutable publication |
| Final admission | Current persistent startup requirements, unchanged selection/state/target, completed manager-owned build and retained slot binding |
| Explicit `--verify` | Additional archive, retained profile/tree and provider content audits |

The locks prevent cooperating MPM writers from changing the planned resources.
Persistent configuration can also be edited independently, so admission checks
current state and brackets that check with selection/state/target guards. Saved
plans passed to standalone builder APIs are revalidated at their own entry
boundary. Normal installation neither selects the prepared entry nor reboots.

## Package and runtime contracts

The generation is existing native kind `system`, role `generation`, with
`payload/composition.json` and `payload/lifecycle.json`. The composition binding
is the existing metadata format/ID/path reference; descriptor dependencies must
equal its unique exact component references. Original package version, revision,
artifact identity and provenance are retained unchanged. Labels never identify
storage or cause replacement of another build with the same label.

The supported subset of the proposed
[composition wire](formats/draft-v1/system-composition.md) uses native leaf
System components, role `component`, with no transitive native components or outer
requirements. Provider dependencies must have supported exact identities. Root-owned protected files/directories and controlled component symbolic links
are accepted; archive links are never followed during extraction.
Their types/modes/paths are checked and write bits removed in storage; private source
files remain private. No mode normalization makes private files world-readable.

Profile mappings must reference listed exact components and safe payload-relative
paths. Destination overlaps, undeclared sources and reserved generated outputs
are refused. Runtime layout currently matches the delivered System contract:
`bin/python3`, `bin/mpm` and `tools`. The interpreter/frontend must be public
executables and the complete declared MPM module set readable. This is a file/
content check, not execution or proof of dynamic-library/ELF compatibility.

Generated `management.json` and the existing System manifest bind the assembled
profile layout, declared payload hashes and source dependencies. Full payload hash
comparison requires `--verify`. Literal manager support is extracted
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

New archives are privately copied and safely unpacked once; payload hashing is
optional through `--verify`. One temporary profile is composed before
target mutation. The plan binds the physical target directory and existing
installation identity, which are rechecked after approval. The writer then reuses the common artifact-store locking and
ordered installation lock, rechecks retained component metadata, publishes complete
immutable objects and places that prepared profile in a private realization
stage without composing it again. On the same filesystem it renames the already
synced profile and syncs both parent directories, avoiding another full content
copy and per-file sync. A cross-filesystem workspace uses the durable copy path.
Only the completed realization is published; existing releases are never linked
to mutable staging files or replaced. The same-filesystem object writer also
promotes the complete, already synced private archive/extraction tree rather
than copying it again. It checks the exact entry set/types/sizes/links, seals
ownership/modes, syncs any changed metadata and writes the normal receipt before
publication. Cross-filesystem workspaces retain the durable object copy path.
Caller-owned input archives are copied/validated, never moved. Archive structure/link confinement, decompressor exit status,
copy failures and atomic publication errors are checked in both modes. A failure can retain
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

The System registry is also observed by management compatibility checks. Provider
dependencies require the measured `exact-provider-dependencies` capability from
both the preparing and candidate managers. An old
candidate without native System format support cannot silently ignore it; an
incomplete import must be completed/diagnosed before a transition. This does not
select the most recently installed generation or write an upgrade wish.

Profile packaging and named-source/cache installation use the same native
content path. The [verified System plan](system-transition.md) binds exact inputs
and reviews tooling, bounded firmware data and the fixed optional QEMU guest
service without effects or boot publication. Normal live installation then
prepares a native-v2 deployment; selection and actual boot remain separate.
General service/state migrations and broader MBT source builds remain roadmap
work.
