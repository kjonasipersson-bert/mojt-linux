<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Local discovery catalog prototype

Status: read-only repository prototype in PR #28. It implements the search and
Kernel-policy portion of the [artifact architecture](mpm-artifact-architecture.md).
It does not fetch payloads, verify native packages, adopt installed metadata,
persist policies or implement Kernel install/status/boot activation. Existing
Ports state and resolver catalogs keep their formats and source bindings.

## Running the example

From the repository root, with Python 3.11 or later:

```sh
python3 -B tools/mpm catalog search neovim --catalog manifests/mpm-discovery-example.json
python3 -B tools/mpm ports search nvim --catalog manifests/mpm-discovery-example.json
python3 -B tools/mpm ports search --description Lua --catalog manifests/mpm-discovery-example.json
python3 -B tools/mpm ports show neovim --catalog manifests/mpm-discovery-example.json
python3 -B tools/mpm ports versions neovim --catalog manifests/mpm-discovery-example.json

python3 -B tools/mpm kernel resolve --policy pinned --series 6.12 \
  --catalog manifests/mpm-discovery-example.json \
  --base-context manifests/mpm-kernel-base-example.json

python3 -B tools/mpm kernel resolve --policy latest-lts \
  --catalog manifests/mpm-discovery-example.json \
  --base-context manifests/mpm-kernel-base-example.json

python3 -B tools/mpm kernel resolve --policy latest-upstream \
  --catalog manifests/mpm-discovery-example.json \
  --base-context manifests/mpm-kernel-base-example.json
```

All example versions, LTS labels, Base bounds and integrity references are
**synthetic fixtures**. They are not a list of actual supported upstream series,
verified Mojt builds or Base 0.1.3 kernel limits. No example payload exists.
The accepted `6.12.107-mojt1` build has not yet been exported as a native package.

The fixture's Base maximum constrains all three example policies to the
`6.12` series. Raising the maximum in a private copy demonstrates that
latest-LTS and latest-upstream can choose different series. Exact version pins
use `--policy pinned --release 6.12.100`; an incompatible exact pin fails.

`catalog search` searches across areas, optionally restricted with `--area`.
Area-scoped search/show/versions require an explicit discovery `--catalog`.
The area in the command cannot be overridden. `show` requires the canonical
package name; search aliases are not resolver/install aliases. `--json` selects
structured search output; inspection, versions and Kernel plans already emit
JSON. No matches is a successful empty search; missing/incomplete metadata or
an impossible resolution returns nonzero.

Plain search treats punctuation literally, casefolds normalized Unicode and
ANDs multiple terms. Default fields are canonical name and declared aliases.
`--exact` takes one complete name/alias. `--description` additionally includes
the summary and description. Match ranking is canonical exact, alias exact,
prefix, substring, description-only; lexical tie-breaking is deterministic.
No regexp, glob, fuzzy search or automatic broadening is implemented.

The existing `mpm ports search NAME` without discovery `--catalog` still uses
the existing pinned Nix source. Existing global-option/provider commands still
delegate unchanged. This explicit prototype does not migrate those semantics
or route old installation requests to new sources. The installed System launcher
still invokes the Nix prototype directly; run these commands from the checkout.
Bundling/adopting the new frontend in System is a later explicit change.

## Experimental discovery envelope

`mpm-discovery-catalog-v1` is an independent strict JSON wrapper around the
unchanged `mpm-release-catalog-v1` resolver schema. Required top-level fields:

| Field | Meaning |
| --- | --- |
| `format` | `mpm-discovery-catalog-v1` |
| `publisher` | Declared authority label, not authenticated by this prototype |
| `revision` | Declared snapshot revision, not an ordered anti-rollback counter |
| `complete` | Boolean completeness declaration; false is rejected for local discovery |
| `packages` | Package records, unique by area and canonical name |

Each package has `name`, `aliases` (text list), `summary`, `description`,
`category` and `releases`. The latter is a complete validated v1 release view:
area, catalog name, channel, platform, named sources, candidate records and
optional source preference. Every candidate belongs to that one package.
Combine alternative sources in its release view; never pick a source by search
ranking. This first envelope has one channel/platform view per package and does
not implement multi-platform merging, sharding or pagination.

Search outputs one row per package with all named sources. Versions outputs
each exact candidate with opaque provider reference/integrity and source.
Installed status and live payload availability are explicitly uninspected.
The canonical envelope digest and contained release-view digests are reported;
the selected plan retains the original unfiltered release-view digest.

A `kernel` package is named `linux` in this prototype and additionally contains
`kernel.releases`, a mapping from every offered `release_id` to booleans
`active_lts` and `upstream_stable`. These classifications are declared by the
catalog maintainer. Kernel numeric versions use the existing dotted adapter;
RC/opaque Kernel versions are deliberately unsupported here. Active LTS implies
upstream stable, which must also agree with the candidate's stable classification.
Provider/build IDs remain opaque. This wrapper does not normalize the accepted
kernel build's `-mojt1` suffix into a different release identifier.

## Selected Base and Kernel planning

`mpm-kernel-base-context-v1` requires `format`, `base` (exact declared `release`
and `artifact`), `platform`, `kernel_min` and `kernel_max`. The numeric bounds
are inclusive. Missing/inverted bounds or a platform mismatch fail. This is an
explicit caller-supplied selected-Base context; it is not auto-detected from
the running kernel, trusted merely because its filename says Base, or yet
integrated with the existing System manifest/preflight format.

Pinned requests require either a major.minor `--series` or exact `--release`.
Latest-LTS requires an active-LTS classification; latest-upstream requires
upstream stable. All paths apply the selected Base bounds and reject candidates
declared incompatible, then reuse the existing resolver's release/build/source
ordering and ambiguity checks. The plan includes the policy, original snapshot
evidence, exact result, Base-context digest and excluded candidate reasons.
No policy fallback, automatic Base change, install or activation occurs.
Additional System/hardware/firmware requirements and runtime acceptance are
outside this preliminary range check. Future deployment integration must supply
the selected Base's authenticated requirements and intersect all required gates.

## Data and trust boundary

Only the explicitly named local metadata files are read. There are no backend
imports, network calls, payload reads or installed-state writes. Use `-B` to
avoid Python bytecode caches when requiring a byte-for-byte unchanged checkout.
The loader bounds each file to 8 MiB and rejects duplicate keys, unknown schema
fields, incomplete snapshots and non-finite JSON. This is a prototype input
boundary, not a full adversarial publisher/trust implementation.

Snapshot digests identify data; they authenticate neither the publisher nor the
truth of LTS/compatibility declarations. Signing, expiry, revocation, anti-rollback,
atomic metadata refresh, native descriptor verification and safe archive import
must be specified and implemented before production repository/install claims.
A derived search index can be added without making it authoritative.

## Focused checks

```sh
python3 -m unittest discover -s tests -p 'test_mpm_catalog.py' -v
```

Tests exercise literal names/punctuation, ranking, grouping, explicit descriptions,
strict/incomplete metadata, three Kernel policies and Base limits, exact pins,
source ambiguity and unchanged local files. The isolated CLI test copies only
the frontend, discovery module and pure resolver, with no provider implementation
and an empty executable PATH. Existing selector/Ports/Nix orchestration tests
remain applicable. A new kernel build or another VM account/generation cycle is
not needed to validate this read-only increment.
