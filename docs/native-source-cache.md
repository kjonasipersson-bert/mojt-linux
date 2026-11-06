<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native local source acquisition and verified cache

Implemented library increment for consolidation steps 1 and 2. This is an
acquisition boundary for native Base, System, Kernel and Port archives, independent
of Nix and of installation. The [governing six-step plan](mpm-consolidation-plan.md)
remains authoritative. This increment does not complete either milestone.

`tools/mpm_native_cache.py` implements `prepare(cache, **inputs)` and
`acquire(cache, accepted_plan, **inputs)`. It ships with the MPM runtime in System.
The [installed source/cache frontend](source-runtime-integration.md) now joins
named registrations, frozen snapshots and exact acquisition. Connections to area
installers remain pending.

## Inputs and authorization

The caller supplies an accepted `mojt-source-v1`, `mojt-source-snapshot-v1`, the
exact catalog and acquisition-map bytes, an exact native artifact reference, its
category and one approved compressed archive SHA256. The existing
[source/cache contracts](formats/draft-v1/sources-cache.md) define these records.
Every envelope ID, catalog/map raw-byte hash and size, source binding, descriptor
and selected release must agree. Unknown versions and fields fail closed.

The first supported transport is an explicitly owner-authorized local directory.
A separate protected local policy file is mandatory. Its envelope is:

```json
{
  "format": "mojt-local-source-policy-v1",
  "id": "sha256:<canonical envelope digest excluding id>",
  "description": {
    "name": "local",
    "provider": "native",
    "channel": "stable",
    "root": "/absolute/repository",
    "max_archive": 1073741824,
    "max_expanded": 4294967296
  }
}
```

This illustrative ID is a placeholder, not a runnable policy. `record()` from
`mpm_request_plan` computes real IDs. The source trust policy must equal this
policy's ID; name, provider, channel and absolute root must match. The policy file,
source root and cache use the same ownership/private-directory protections as
Ports. Files and traversed subdirectories cannot be writable by another user.
Relative source paths are opened beneath the root using no-follow file
descriptors. Symlinks, hardlinked inputs, FIFOs and other special files are refused.

Authority comes from the owner's protected local policy, not from SHA256. A hash
by itself authenticates neither a publisher nor a release. A cached copy of a
policy is evidence only: each operation still reads the authorized policy file.
This low-level API assumes the caller chooses that protected policy deliberately.
The installed frontend permits only an administrator to register/reconfigure a
source. Registration copies the accepted policy to its protected registry, then
fetch selects that registered policy. It never accepts a replacement policy from
an unprivileged fetch request.

Native HTTP(S), signature verification, revocation services and implicit source
refresh are unsupported. Other provider bindings can be retained as metadata;
this API neither executes those providers nor copies their store paths.

## Preparation and acquisition

Preparation reads bounded metadata and the local policy and returns a
`mojt-native-acquisition-plan-v1` envelope. Its description binds the absolute
cache and policy paths, policy raw-byte SHA256, source ID, category, descriptor byte
evidence/path, approved archive paths, expanded-byte limit and cache-record binding.
It writes nothing, does not run a decompressor and does not read the archive body.
It can read the external descriptor from the source before a first acquisition,
or from the verified metadata cache on subsequent runs.

Acquisition recomputes that exact plan before writes and again under the cache
lock. It copies only the selected encoding from the first explicitly listed local
path; a failed path does not trigger an implicit mirror/provider/version change.
Before publication it checks compressed bytes, fully verifies the category-rooted
native archive and embedded descriptor, and rechecks the policy/metadata plan.
The expanded-byte cap includes descriptor, tar/PAX overhead and trailing padding,
not just the sum of declared file sizes. No payload is extracted or executed.
For Base this bounds the outer native package; its retained `rootfs.tar.zst` is
not unpacked here. The Base installer must enforce its own expansion limits.

Publication uses exclusive temporary files, fsync and no-overwrite hardlink
publication. Independent requests serialize on the cache lock. Preparation is
read-only; acquisition requires an owner-writable cache and checks free space.
This reserves the compressed copy plus bounded metadata headroom, not space for
installation or every future concurrent workload.

## Cache layout and failure boundaries

| Relative path | Meaning |
| --- | --- |
| `cache.json` | Exact `{"format":"mojt-native-cache-v1"}` marker |
| `archives/sha256/<raw-sha256>` | Fully verified compressed native archive |
| `metadata/<raw-sha256>` | Exact descriptor, catalog and acquisition-map bytes |
| `objects/<record-id-hex>.json` | Canonical source, snapshot, acquisition-map and policy envelopes |
| `records/<binding-digest-hex>.json` | `mojt-cache-record-v1` observation with verification UTC |
| `.lock` | Shared cache writer lock |

The record filename indexes its binding without the timestamp; the record inside
still has its own complete content ID. A repeat operation fully rechecks the
archive and retains the original successful observation unchanged. A valid cache
can be reused after the source directory is unavailable, using the same accepted
metadata and the still-authorized protected policy. Corrupt cached bytes or
metadata fail closed and are never silently repaired or overwritten.

An interrupted copy removes its temporary file. A failure after the verified blob
is published retains that blob; it does not create a successful observation.
Retry re-verifies it before completing the metadata/observation. Directory flush
failure after publication reports uncertain durability and retains published data.
An interruption during initial directory creation can leave an incomplete cache;
it is refused rather than adopted automatically. Inspect it and use a new empty
cache instead of deleting unknown content. No cache collection is provided here.

A cache observation means verified acquisition, never installed, selected,
compatible or boot-ready. Installation receipts, lifecycle effects, active
profiles and boot deployments remain separate authorities.

## Validation and next integration

`tests/test_mpm_native_cache.py` uses real synthetic tar/zstd packages for all four
categories. It covers repeat no-ops, offline reuse, source/cache corruption,
unsafe paths and special files, stale/revoked policies, decompression limits,
failed verification, post-publication flush failure and retry. Existing native
package and Ports/transaction tests cover the reused boundaries.

Named source/snapshot retention and explicit refresh are now joined to the installed
frontend. Next, pass verified cached native archives into the area publishers.
Remote acquisition needs an explicit authentication extension before enabling a
network transport. Base/System installation, configuration forgetting, retained
artifact pruning and lifecycle/recovery remain separate completion gates.
