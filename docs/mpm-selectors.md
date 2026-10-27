<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Ports selector and catalog contract — proposal 1

Updated 2026-10-27. Sections 8–9 describe the implemented selector branch:
pure resolution, Nix-backed transaction integration, series aliases and explicit
format-3 metadata adoption. Earlier sections retain design context; where a
future policy is broader than this increment, section 9 states the boundary.
Libc integration remains deferred; dependency records stay opaque in the core.

## 1. Three identities

| Concept | Example | What it fixes |
| --- | --- | --- |
| Request | `gimp@3.0` | Eligible release line and future upgrade policy |
| Release | `3.0.8-r2` | Canonical package release, including a declared packaging revision |
| Artifact | Existing exact installed ID plus backend output/NAR/closure records | Concrete build and its dependencies, including libc |

One release can have several builds, including builds against different glibc
objects. A version string alone is neither a build identity nor a reproducible
lock. Nix output path hashes are opaque identifiers, not necessarily hashes of
output bytes; retain NAR hashes and exact reference graphs as well.

## 2. Initial selector grammar

```text
request  = name | name "@" series | name "@=" release
name     = existing MPM attribute-style name
series   = component ("." component)*
component = "0" | nonzero-digit digit*
release  = ASCII-alphanumeric (ASCII-alphanumeric | "." | "_" | "+" | "-")*
```

Names retain the current pattern
`[A-Za-z_][A-Za-z0-9_+-]*(\.[A-Za-z_][A-Za-z0-9_+-]*)*`.
The catalog maps a logical name to attributes; an attribute is not a version.
MPM performs no shell expansion and accepts no whitespace, empty suffix,
wildcards, inequalities or implicit ranges. Epoch-bearing syntaxes require a later explicit adapter/grammar
extension, not silent punctuation stripping.

| Input | Meaning |
| --- | --- |
| `gimp` | Newest eligible stable release in the selected catalog view |
| `gimp@3.0` | Newest eligible stable release with upstream component prefix [3, 0] |
| `gimp@3.0.8` | The same rule with prefix [3, 0, 8], including declared package revisions |
| `gimp@=3.0` | Exact canonical release ID `3.0`, not `3.0.0` |
| `sudo@=1.9.17p2` | Exact ID; does not assert that dotted-numeric comparison understands it |
| `gimp@`, `gimp@03.0`, `gimp@>=3.0` | Invalid |

An exact installed artifact ID from today's `list --exact` remains a literal
selection accepted by activate/remove; look it up before parsing a new selector.
The legacy Nix CLI bridge reserves its terminal `-nix-<32-character-store-hash>`
form for artifact references, so its release selector cannot be confused with
one. This compatibility rule belongs to that adapter, not the pure parser. Do not infer a
request or extract a release by splitting that installed ID.

The selector-mode grammar applies to install/info and activation. Upgrade still
filters recorded requests by logical name; it does not replace their policy.
Remove retains exact artifact IDs or unambiguous installed names until series
removal scope is separately specified. Section 9 describes the implemented selector-mode commands; removal scope remains unchanged.

## 3. Matching and ordering

The first version adapter is named `dotted-v1`. Upstream components use the
series component grammar above. Match whole components: 3.0 includes 3.0,
3.0.1 and 3.0.10, but not 3.00, 3.1, 13.0 or 3.0rc1.
A version such as 3.00 remains usable as an opaque exact release, not as a
silently normalized dotted version.

Compare numeric components numerically, then an explicitly declared integer
packaging revision. Missing trailing upstream components compare as zero;
different exact release IDs remain distinct even when their ordering keys tie.
Such a tie between different release IDs is ambiguous and needs an exact choice
or an adapter-defined ordering, not a lexical tie-break. Thus exact equality
never pads, trims zeros or removes suffixes.

A producer with explicit packaging revisions renders
`<upstream>-r<revision>`; an ordinary Nixpkgs record without such a scheme
preserves its version string as release ID and records revision as null.
Do not manufacture an `-r1` from a Nix hash, snapshot date or commit count.
Do not split an upstream `-r2` suffix unless a declared adapter establishes
that meaning. Revisions from unrelated schemes are not comparable.

Other versions use `opaque-v1` (exact equality only) until a named, versioned
adapter defines their ordering and series extraction. Do not silently apply
SemVer, Debian, apk or Nix's generic comparison to every upstream version.

Candidate stability is explicit producer metadata: stable, preview or unknown.
An unstable Nixpkgs channel does not by itself make every package a prerelease.
Default/latest and ordinary series accept stable candidates only. An exact
selector can deliberately choose a preview/opaque release. Channel-specific
preview tracking is a later extension; unknown classification is reported,
not guessed from a convenient suffix.

## 4. Catalog view and deterministic build selection

The new catalog is a finite, immutable local view, with independent selection
for Ports and System. Record its digest, ordered allowed pinned sources,
channel, platform, logical package-to-attribute mappings, and adapter versions.
Each release lists its stability, comparison metadata and concrete artifact
candidates. A Nix source identity includes the pinned revision, source NAR hash,
evaluation configuration/overlay identity, platform, attribute and output.

Resolution:
1. Filter the selected view by package, platform, channel and request.
2. Exclude known incompatible candidates; expose unknown host requirements.
3. Select the newest comparable eligible release/revision, or the exact ID.
4. Resolve that release's build using an explicit preferred artifact in the
   catalog, or a unique candidate. Source preference can break a build tie only
   when it chooses a unique source/artifact. Otherwise report ambiguity.

Upgrade rejects a candidate older than its recorded target; an unknown
comparison also stops the plan. Explicit install/activation of an older exact
release is a separate operation. A replacement build's hash or newer source
snapshot does not prove that its dependencies are more secure.

Version ordering takes precedence over build preference. A hash, directory
listing order or download timestamp never establishes which build is newer.
The producer may explicitly prefer a replacement build of the same release in
a new view; show its full dependency difference before approval.
A same-key artifact repeated through sources is deduplicated with provenance
retained. Conflicting integrity metadata for one store object is an error.
An exact release ID resolving to contradictory release metadata is ambiguous.

Historical versions must be backed by actual entries from explicitly pinned
sources, not invented by assigning another `version` to today's expression.
A source set can index both of the snapshots used in the hello acceptance test.
An unavailable exact/series selection fails clearly. Install/upgrade never
refresh the view, search Git history, mutate channels or build from source
as a hidden fallback. Cache availability is separate from release eligibility;
missing substitutes fail before profile publication.

## 5. Requests, activation and dependency rebuilds

Persist typed selectors separately from resolved target artifacts. Distinct
series/exact requests for one name remain distinct. Request IDs are stable
opaque state keys; do not use human CLI text as an implicit mutable schema.
An explicit source/variant constraint is part of request policy. Changing that
policy requires a displayed transaction, not automatic reinterpretation.

- First install establishes defaults following the requested series/latest,
  or pinned to the exact artifact resolved from an exact release request.
- Later install retains another build without moving accepted request targets,
  series aliases or the unqualified command.
- Approved upgrade advances eligible latest/series targets and following defaults.
  It can propose a catalog-preferred replacement build of the same release,
  including a changed glibc closure. It retains the old build.
- An exact request, once resolved, keeps its artifact and closure on ordinary
  upgrade, even if another build has the same release ID. A later explicit
  re-resolution may change that lock only in a separate visible plan.
- Explicit exact activation pins its artifact without deleting other requests.
  Series activation chooses the newest eligible installed member, records that
  accepted series target, and downloads nothing. Ambiguous builds require an
  exact artifact choice. Today's `--follow` remains the explicit way to follow
  an installed recorded target; it cannot turn an exact request into latest.

Keep fixed aliases containing the existing version and full output hash.
Add a moving series alias only for an explicitly tracked series, across all
exported commands. A collision with any default, fixed/series alias or reserved
management name aborts the whole plan; never overwrite another owner.
If a series alias and a fixed alias would have the same spelling, require an
explicit disambiguated alias policy before publication; no heuristic renaming.

Plans/history show old/new request, release, artifact, accepted aliases, source
view and exact closure delta. Unavailable required planning metadata is an
explicit adapter limitation, not a promise of a complete dependency preview.
Dry-run retains its existing no-payload/no-roots/no-state-write behavior.
No-op creates no profile or transaction. All changes publish atomically.

The [glibc policy](mpm-libc-policy.md) applies to these dependency decisions:
installing a standalone glibc object does not update applications linked to
another object. Security repairs need replacement consumer closures.

### Proposed logical record shape

Conceptual record shape; use section 9 for the implemented snapshot fields. Artifact keys below are placeholders, not real Nix paths.

```json
{
  "request": {
    "id": "request-1",
    "name": "gimp",
    "selector": {"kind": "series", "components": [3, 0]},
    "source_policy": {"catalog": "ports-main", "channel": "stable"},
    "target_artifact": "artifact-A"
  },
  "selection": {"kind": "request", "request_id": "request-1"},
  "release": {
    "id": "3.0.8-r2",
    "upstream_version": "3.0.8",
    "version_scheme": "dotted-v1",
    "revision_scheme": "mojt-r-v1",
    "package_revision": 2,
    "stability": "stable"
  }
}
```

An exact selector instead stores `{"kind":"exact","release_id":"3.0.8-r2"}`.
An exact active selection instead stores
`{"kind":"artifact","artifact_id":"artifact-A"}`.
The request's source policy names a logical catalog; each resolution separately
records the immutable view digest and source/build/closure identities it used.
The artifact table owns those backend records. Historical transaction records
refer to exact identities; do not rewrite them on conversion.

## 6. State and System compatibility

Do not reinterpret format-2 `policy=attribute` as series or stable-latest.
Preserve its native attribute identity, target, exact/following selection and
legacy version behavior until an explicit conversion plan adopts a release
catalog. Request IDs may change only with a recorded old-to-new mapping.
Read-only inspection and no-op operations do not migrate state.

A future request/catalog schema is a new format, with minimum reader/writer
capabilities. It must preserve immutable old artifact/closure records and stop
older writers from dropping unfamiliar policies. Section 9 assigns format 3 and documents its explicit transition.

Reuse typed identities and catalog concepts for future System planning, but
keep its request set/view separate. Plan from the selected deployment; show
running content separately. Publish changed System content as a new immutable
generation for next boot, preserving Base, Kernel and Ports choices.
A newer libc does not justify silently changing those other areas.
Booting an older generation does not roll back persistent MPM/account data.

## 7. Implementation gates

Before claiming selector support:
- Parser fixtures cover valid/invalid input, opaque exact IDs, exact zero
  distinctions, legacy artifact references and reserved artifact suffixes.
- Resolver fixtures cover 3.0.9/3.0.10, revisions, preview/unknown exclusion,
  ambiguous equal-order releases/builds, two pinned sources, missing substitutes,
  two series for one name and explicit request conversion.
- Transaction tests preserve exact pins and old closures on same-release libc
  rebuilds, leave unrelated areas/project references intact, and retain no-op,
  dry-run and failure-before/after-commit behavior.
- Real Nix acceptance executes both versions after upgrade and checks ordinary-user
  permissions. Additional mixed-libc/ELF runtime investigation is deferred by owner direction.
- Only then extend `mpm(1)` as implemented behavior and run fresh VM A/B/A
  metadata compatibility tests. A documentation proposal is not such evidence.

The parser/resolver and explicit transaction integration are now present (sections
8–9). Real mutation and fresh-image acceptance remain required before merging
this increment. Project locks and retention/GC follow these semantics.

## 8. Implemented slice: backend-independent resolution

`tools/mpm_selection.py` implements parsing, finite catalog validation, numeric
series/revision selection, exact matching, explicit build preference and a pure
upgrade plan. It imports no backend package/command, reads no files and writes
no state. Source identities, artifact IDs and integrity metadata are opaque JSON;
there is no Nix path, hash grammar, attribute lookup or version inference from
backend object names in this module. A future backend maps its records to the
same model. Unknown version schemes still require explicit adapter support;
changing backend must not silently change MPM's public selector semantics.

The current CLI supplies file I/O and presentation through the existing launcher.
Its new policy is in the pure module, not in the Nix command adapter. Legacy
attribute-upgrade comparison deliberately remains unchanged until explicit state
conversion; that compatibility path is not the new selector implementation.

Read-only examples:

```sh
python3 tools/mpm ports resolve paint@3.0 \
  --catalog manifests/mpm-release-example.json
python3 tools/mpm ports resolve paint@=3.0.9 \
  --catalog manifests/mpm-release-example.json --json
```

The example uses synthetic archive/alternate-backend records and is not an
installable package catalog. It resolves 3.0.10 for the series while excluding
3.1; its explicit exact choice resolves 3.0.9. These commands need no Nix,
network, managed MPM root or elevated privilege. New System builds also include
the same fixture at /run/mojt-system/tests/mpm-release-example.json. The account-enabled System
allows ordinary-user resolution; filesystem permissions control catalog reads.
Resolution does not adopt this catalog for existing package operations.

### Catalog JSON and adapter boundary

`mpm-release-catalog-v1` is a standalone input format, not a new installed-state
format. Required fields: `format`, `area`, `name`, `channel`, `platform`, `sources`
and `candidates`. Optional `source_preference` is an ordered list of source IDs.
Each source has a backend identifier and opaque identity object. Candidates
require name, release_id, upstream_version, version_scheme, stability, source,
artifact and a nonempty opaque integrity object. Optional revision_scheme /
package_revision must be a supported pair; preferred is boolean; compatibility
is a declared verified/unknown/incompatible status, default unknown.

The supplied example is the complete minimal shape. Validation rejects unknown
fields, conflicting release/integrity/compatibility metadata and nonfinite JSON.
Numeric spelling is not a stability audit. The producer classifies stability
explicitly; exact requests can inspect unknown/preview releases. Declared
compatibility is not runtime verification or a new libc/host capability checker.
The area/catalog/channel/platform binding prevents a pure upgrade plan from
silently changing resolution scope.

Core `plan_upgrade` returns data only. Exact requests preserve their original
artifact/closure evidence even if the catalog withdraws that release. Following
requests can propose a preferred replacement build of the same release; changing
opaque dependency references is sufficient, without any libc-specific solver.
Numerical downgrades, unknown order and integrity drift of a retained object fail.
An unchanged artifact/release preserves its original provenance; a new release
can intentionally reference an unchanged backing object without losing its
new release identity. This API does not import, activate, audit runtime ABI,
create project locks or collect objects.

### Nix adapter for an existing isolated lab

After the earlier two-snapshot hello test has explicitly imported both outputs:

```sh
python3 tools/mpm-nix-catalog.py \
  --source old=/path/to/from.toml \
  --source new=/path/to/to.toml \
  --name hello --stability stable --output /new/path/hello-releases.json
python3 tools/mpm ports resolve hello@2.12 \
  --catalog /new/path/hello-releases.json
```

The producer explicitly declares those known GNU Hello releases stable. Without
`--stability`, classification is unknown and only exact requests are eligible.
Nonnumeric upstream versions are opaque/exact-only until another adapter exists.
Use `--prefer-source ID` only when deliberately preferring one build of an equal
release; it does not cause an older version to outrank a newer eligible release.

The exporter evaluates each explicitly pinned source with config={} and no
overlays, using lib.getBin, then reads output closures and NAR hashes from the
local Nix database. Missing local outputs fail; nothing is realized, rooted,
built or channel-refreshed. Evaluation can populate Nix evaluation caches.
The new catalog file is created exclusively; existing files/symlinks are refused.
The JSON is a snapshot of recorded evidence, not a GC root, signature audit or
promise that its objects remain available. Preserve the isolated labs/roots.

Libc coexistence/integration work is deferred. Its analysis remains in the
companion document; neither catalog resolution nor this exporter solves it.
Actual selector installation/activation and explicit state conversion are the
next integration stage, with the acceptance gates above still applicable then.

### Agent validation for this increment (2026-10-27)

26 backend-independent tests cover selector syntax/equality, numeric series and
revision order, opaque exact versions, stability, build ambiguity/preferences,
source provenance, area/platform binding, integrity drift, downgrade rejection,
exact pins and same-release dependency replacements. An actual subprocess runs
the CLI under isolated Python with no backend executable on PATH and proves
that its supplied catalog is the only filesystem entry afterwards.

52 simulated Nix orchestration tests pass, including no state/history change on
resolution and no realization/GC roots from catalog export. 59 System assembly
tests pass (one skipped), including the shipped pure module, exporter and example.
The broader available suite passed 234 tests with eight environment/tool skips;
the separate Base archive ownership test is excluded locally because this
runtime rejects its chown-to-UID-1000 setup. It remains enabled in CI.
These are agent tests; real local-Nix exporter and new-VM resolution acceptance
are not yet owner-reported. The earlier hello upgrade test is separate evidence.


## 9. Implemented transaction integration (2026-10-27)

The same pure resolver now drives Ports installation, installed-only activation
and upgrade. `tools/mpm_selector_ports.py` owns request/selection/series-alias
policy without I/O or package-manager commands. It treats installed IDs and
backend records as opaque data. `mpm-nix-prototype` adapts these plans to the
existing Nix import, GC-root, command-export and atomic profile publisher.
Alternative backends can supply resolved records without changing version or
request policy. The Nix transaction adapter currently accepts upstream-only
releases from its exporter; it has no packaging-revision mapping. Declared
revision ordering remains supported and tested in the pure core. Nix path syntax, source verification and closure acquisition
remain in the Nix adapter; this is not a generic dependency solver.

### Explicit catalog and metadata adoption

```sh
mpm ports metadata --catalog hello-releases.json --dry-run
mpm ports metadata --catalog hello-releases.json -y
# Optional: explicitly replace native requests whose target is already installed.
mpm ports metadata --catalog hello-releases.json --adopt hello@2.12 --dry-run
mpm ports metadata --catalog hello-releases.json --adopt hello@2.12 -y
```

`metadata` validates the neutral catalog and Nix source/closure evidence. It
writes format 3 with reader/writer capability `mpm-ports-selectors-v1` only after
approval. Dry-run, cancellation and inspection do not convert state. Repeating
an identical plan creates no profile/history transaction. A fresh root can opt
in directly. The immutable JSON view is copied into `release_catalog`; later
operations need no original JSON file. `update` continues managing the native
attribute catalog; only `metadata` replaces the selector release view.

Existing native requests retain `policy=attribute`, their targets and original
behavior. No stable/latest/series meaning is guessed. `--adopt` explicitly maps
native request IDs to a digest-derived opaque selector request ID and records
`metadata_mapping` in the snapshot/history. The resolved adoption target must
already be installed and equal the old native request target. Adoption never
imports an artifact or moves defaults. An existing exact default remains exact;
explicit series activation is needed to make it follow. Multiple explicit
`--adopt` arguments are allowed. Re-adopting an already installed selector build
is also an explicit way to accept a changed same-release build lock.

Format 3 adds `capabilities`, `release_catalog` and selector requests to the
existing snapshot. Selector requests contain `name`, `policy=selector`, `target`,
the typed `selector`, and complete resolved `selection` evidence. Installed
records additionally retain their accepted `release` evidence. Exact pins are
still represented by a null active `selection_policy`; native and selector
request IDs can coexist in that map. Validation checks request/target evidence,
binding, alias ownership and capabilities before publication.

Older System generations with format-1/2 MPM cannot read or write format 3;
they fail explicitly. Published program links remain usable. Do not use an
older writer against the converted shared state. A future `system upgrade`
must verify the selected generation's metadata capabilities before scheduling
it; boot rollback does not roll back persistent Ports metadata. There is no
automatic reverse conversion or general metadata rollback command.

### Installation, activation, aliases and upgrade

```sh
mpm ports install hello@2.12 -y
mpm ports install hello@=2.12.1 -y
mpm ports info hello@2.12 --json
mpm ports activate hello@2.12 -y
mpm ports activate hello@=2.12.1 -y
mpm ports upgrade hello --dry-run
```

Selector mode requires explicit install selectors (bare names mean stable
latest); `--attribute` is a native-mode option. Each distinct typed selector
and catalog area/name/channel/platform binding identifies a request. Multiple
series and exact requests may coexist for a logical name. First installation
claims defaults unless `--no-activate`; series/latest follow that request,
exact requests pin the concrete artifact. Later installations retain new
artifacts without moving existing defaults or accepted request targets.

Activation resolves against **installed release evidence only**, not today's
available builds. It can select a withdrawn installed release, downloads
nothing and adds no payload/GC roots. Bare/latest and series choose the newest
eligible installed release; multiple same-release builds require a literal
artifact ID. Historical producer build preferences do not silently choose one.
Exact release activation also needs a unique installed build. Literal IDs from
`list --exact` take precedence over selector parsing and pin defaults. `--follow`
on a literal ID requires exactly one moving request already targeting it;
`--follow` never turns an exact-release request into a moving request. Native
artifacts without release evidence keep their original activation rules.

An explicitly tracked series creates `COMMAND-SERIES` for every exported
command, e.g. `hello-2.12`, independently of the unqualified command. Fixed
aliases retain their original version/full-output-hash spelling. All aliases
share one collision/reserved-name check; publication never overwrites another
owner or invents a renamed alias. Unknown exports are checked after import,
before the atomic switch. Removing a selector request's target removes that
request and its series aliases; it does not invent a new eligible target.
Other retained requests/artifacts remain. Default fallback retains the existing
recency rule and is pinned unless it equals a retained followed request target.

Upgrade calls the shared pure planner for selector requests and preserves the
native policy for unadopted requests. Exact requests retain the original build
and closure even if withdrawn. Series/latest may advance to a newer eligible
release or explicitly preferred same-release rebuild, retaining older builds.
Only following defaults move; series aliases follow their own accepted targets.
No source refresh is implicit. Downgrades, ambiguous versions/builds and changed
integrity for a retained object stop the plan. Dependency evidence is opaque:
there is no libc-specific comparison, loader modification or compatibility fix.

Plans display format/capability changes, request mappings, old/new resolution
and exact closure additions/removals plus accepted series aliases. Publication
verifies actual local Nix closures/NAR hashes against accepted catalog evidence;
mismatches preserve the old current profile. Failed imports can leave retained
objects, as before. State, aliases and history switch atomically. History now
includes format/capabilities, both catalog scopes and metadata mappings, without
rewriting old transactions. Other MPM areas/project references are not modified.

### Measured and pending acceptance

Owner acceptance of the preceding resolver slice passed on Debian without Nix
and inside the existing Distrobox lab with real hello 2.12.1/2.12.3. It verified
latest/series/exact choices, whole-component exclusion, pinned source revisions,
recorded closure/NAR evidence and provenance. Those tests did not mutate Ports.

The new integration is covered by pure non-Nix request-policy tests and mocked
Nix transactions, including pins, multiple series, installed-only ambiguity,
explicit adoption, dry-runs, no-ops, collisions, integrity mismatches and failure
before/after the profile switch. Real transaction acceptance is still pending:

```sh
python3 tests/run-mpm-selectors.py --root /NEW/LAB/state \
  --catalog /EXISTING/hello-releases.json
```

This harness requires the already-exported two-version catalog, retains its new
isolated lab and tests installation, exact pins, moving aliases, upgrade,
activation, no-op history and execution of both hello artifacts. It changes no
live Ports/System state. Fresh VM acceptance must use an MPM-capable image on
both A and B before converting shared metadata, then test A/B/A persistence and
ordinary-user mutation denial. The old format-2 reference VM remains a useful
unchanged reference. Runtime libc/desktop and System deployment compatibility
work remains deferred; no mixed-libc safety claim follows from these tests.
