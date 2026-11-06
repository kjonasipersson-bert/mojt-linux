<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Sources, frozen metadata, acquisition and cache

Review draft, [workflow schema](workflow-formats.schema.json). It wraps existing
catalog formats; it does not change search/selector semantics or implement D7
native remote signatures. First native workflow is an explicitly trusted local
repository; existing provider trust remains adapter-owned.

## Records and binding direction

| Format | Description fields and responsibility |
| --- | --- |
| `mojt-source-v1` | Stable human name, provider/channel, native local-directory or opaque provider configuration, explicit trust-policy ID |
| `mojt-acquisition-map-v1` | Exact raw catalog SHA256 and sorted offers: native descriptor/transport bytes and confined relative locations, or adapter-validated provider identity/source binding |
| `mojt-source-snapshot-v1` | Source ID, catalog format/raw hash/size, acquisition map ID/raw hash/size, exact provider snapshot or null, trust-policy ID |
| `mojt-cache-record-v1` | Verified native artifact/descriptor ID, exact archive hash/size, snapshot/map/policy IDs and verification time; a local observation, not installation or publisher signature |

Map references the raw catalog hash, not its future snapshot ID. Snapshot binds
both catalog and map bytes. Thus no ID/hash cycle. Distinguish canonical record
ID from SHA256 of its complete stored bytes including newline. For provider
sources, identity/configuration is opaque to the core but mandatory validation
is not optional: the declared adapter must bind it to the source/snapshot before
resolution/acquisition. No provider fallback or dynamic adapter execution in
read-only discovery. Missing adapter is a precise unsupported-provider outcome.

The source's `provider` describes how metadata is obtained. An offer's
`reference.provider` describes who owns/acquires its payload. A Mojt-owned local
catalog can explicitly offer both native and Nix-backed content; the source is
not a promise to convert every package to the metadata provider. Each payload
reference binds its named adapter/source identity/trust policy independently.
`provider_snapshot` is metadata-provider provenance, not a replacement for those
per-offer bindings. This distinction preserves Mojt's own catalog authority.

Native source locations are canonical absolute trusted directory paths, not URLs
or arbitrary relative paths. Verify ownership/symlink containment on read and
freeze accepted metadata bytes. Source identity includes channel/location/policy;
a change is explicit source reconfiguration, not a hidden locator substitution.
The policy ID must identify protected retained local trust configuration; a
caller-supplied hash alone is not authorization. Policy evidence contains no
passwords/tokens. Native network sources need a reviewed extension/authentication
policy; this draft does not accept arbitrary URLs because hashes exist.

Offers are unique and sorted by canonical exact reference. A native offer binds
its descriptor byte hash/size/path and sorted permitted archive encodings. Parse
the descriptor, verify its native artifact ID and category, and check that
dependencies/candidate identity match the accepted catalog before import. Each
archive has exact byte hash/size and sorted unique relative mirror paths. Reads
stay confined to the trusted source root; reject escapes, unsafe links and
nonregular inputs. Paths/filenames never determine identity. A different
compression representation may carry the same artifact but must be separately
listed; a saved plan binds one approved archive hash. Mirroring those same bytes
does not authorize a different build/source. Provider offers delegate acquisition
only for the exact validated identity and snapshot, never a broad channel query.

## Refresh and retention

Suggested local metadata layout is `state/var/lib/mojt/sources/NAME/`, with
immutable source/snapshot/map objects, raw catalog/descriptor bytes by SHA256
and a stable lock. Publish complete accepted metadata first, then atomically
replace one `current` snapshot pointer and fsync. Last good snapshot survives
failure; incomplete metadata is not current. Report age/stale/offline facts.
An update changes metadata only, not wishes, installed packages or active choices.

After explicit source reconfiguration, an old snapshot remains retained but is
not automatically accepted as a snapshot of the new source/policy. Show pending
refresh/rebinding. A later metadata-only refresh under the same accepted source
does not itself invalidate a saved plan that deliberately pins an older still
permitted snapshot; trust-policy/source-identity changes are separate gates.
No accepting publisher maintenance/LTS declarations without the declared trust
policy. For the local experiment this is explicit owner trust, not authentication
of an upstream publisher or an ordered anti-rollback counter.

Retain source configurations, snapshots/maps and evidence referenced by locks,
plans, installed content and recovery. Changing/removing a configured source
does not erase those objects or authorize deleting installed content. A missing
catalog version is not a command to uninstall. Expiry/revocation handling for
remote native distribution remains a D7 gate and must not be invented by a cache.

## Native cache

Suggested paths: `cache/archives/sha256/FULL_BYTE_HEX` for complete regular byte
blobs, `cache/records/FULL_RECORD_HEX.json` for immutable verification records,
and private incomplete `.fetch-*` files. Roots are explicitly configured and
checked for target ownership; do not trust arbitrary user-writable bytes as root.
Provider objects stay in the provider's own store/cache with exact retained roots.

Acquire only the plan's bytes/identity; enforce size/decompression limits and
free-space checks. Copy through a bounded no-follow descriptor, verify bytes and
native descriptor/archive fully, fsync then publish without replacing an existing
different blob. Failed/partial data never becomes a complete cache entry. Safe
resume/range fetching is not implied by a partial file; initial native support
restarts the bounded copy. Recheck content at privileged use even when a record
says it was verified earlier. Timestamp is diagnostic, not a freshness guarantee.

A native cache record's artifact equals descriptor ID; archive exactly matches
the accepted map and source/policy/snapshot bindings. Multiple observations may
refer to the same blob under different accepted metadata/policies. None makes it
installed, active, bootable or a retention wish. Stage/import uses the existing
native store receipt protocol only after dependency closure retention. A cache
miss is availability failure, not permission to build from source or try another
provider. No physical cache GC is introduced; future collection must honor all
retention roots and cannot classify every uninstalled blob as dispensable.
