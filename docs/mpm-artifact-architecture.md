<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Architecture manifesto: Mojt-owned artifacts and catalogs

Started 2026-10-28. **Status: architecture draft with a read-only local catalog
and native package-format prototype plus local Kernel installation, not a
production repository/deployment updater.**
The user-directed requirements below guide the next increments; package/trust
formats, storage paths and mutation commands still need review. The [MPM contract](mpm.md)
continues to define area boundaries, selectors and installation/activation
semantics. The implemented boundaries are documented in [the catalog guide](mpm-catalog.md)
and [native artifact format](native-artifact-format.md).

## 1. Mojt owns its distribution model

Mojt must be able to define, publish, discover, install and retain its own Base,
System components and Kernel builds. MPM's core must function without Nix,
nixpkgs, another distribution's package database or a mandatory remote service.
External providers are optional integrations with explicit provenance and scope.
They do not define Mojt's public names, release policy or transaction semantics.

This is independence of architecture and release authority, not a claim that
today's System or build toolchain has been rebuilt without external packages.
The current System contains retained Nix closures, Base was bootstrapped using
Void packages, and the accepted kernel build uses Nix-supplied tools. These are
recorded inputs, not permanent requirements on every future provider.

Normal boot, installed program execution, inspection and selection of retained
compatible content must not require a live catalog server. A configured local
repository, installation medium or mirror can provide both metadata and payloads.
Any operation needing missing bytes reports that need explicitly. Architecture
independence does not imply the existence of an offline copy of every package.

## 2. Separate production, publication, acquisition and activation

| Responsibility | Input | Output |
| --- | --- | --- |
| Build | Pinned sources, recipe, configuration and toolchain | Immutable payload and build provenance |
| Publish | Validated artifacts and release policy | Immutable descriptors and a catalog snapshot |
| Acquire | Exact descriptor/provider reference and integrity evidence | Verified locally retained content, or a precise availability error |
| Install | Verified content plus an approved area-specific plan | Installed references and transaction history |
| Activate | Installed compatible content | A profile selection or a complete next-boot deployment |

A local build can be imported directly without first being uploaded anywhere.
A remote publisher can distribute the same artifact to other machines. Install
must not silently compile a replacement when a requested binary is unavailable;
building is a separate explicit operation. No new build command is specified here.

Build provenance and distribution origin are distinct. A payload published by
Mojt may have been built from upstream Linux, assembled from third-party binary
inputs, or built with a toolchain originally acquired through Nix. Record each
relationship instead of deriving provenance from its download URL.

## 3. The catalog is the master list of offered content

Mojt needs a catalog of artifacts that can be selected **before they are on the
machine**. Installed state cannot serve as this catalog. The authoritative
catalog is a versioned document published under an identified authority, not a
mandatory central database queried during each install.

There may be an official Mojt catalog, administrator-managed catalogs and
explicitly enabled external-provider catalogs. "Master list" means the
authoritative offered set for a particular publisher/channel/platform, not an
omniscient list of all software or a single globally required endpoint.

A catalog snapshot binds logical names/releases to exact build candidates and
their immutable descriptors. It records its publisher, format, revision,
platform, area/channel views and integrity/trust evidence. A larger catalog can
be split into digest-addressed indexes; every transaction still records one
exact consistent snapshot/view. A mirror can serve the same metadata and bytes
without becoming a new publisher or changing artifact identity.

A resolution view must include the index shards needed to answer the request.
If those metadata bytes are not cached, report an incomplete local view, not
that the package does not exist. Read-only local discovery does not silently
fetch missing indexes; a metadata refresh/acquisition is explicit.

The initial transport can be ordinary files plus static HTTPS hosting. It must
also support a complete local repository. No application server, account, online
API, build farm or remote dependency solver is required for a native repository.

The catalog lists a finite offered set, including the historical releases the
publisher actually advertises. It does not promise every upstream version or
permanent remote retention. A known descriptor can remain useful even when its
payload is temporarily unreachable; report advertised availability separately
from observed reachability and locally verified possession.

### Search is a user-facing catalog contract

Default search treats every query term as **literal text**, with Unicode
normalization and case-insensitive comparison. A dot, plus sign, bracket or
asterisk has no pattern meaning. Search canonical names and explicitly declared
alternative names by default; include summaries/descriptions only with an
explicit option. Multiple terms are ANDed. Exact-name matching is available.
Do not automatically broaden to fuzzy matches, descriptions, other catalogs or
network-backed provider discovery when the local query has no matches.

Rank canonical exact names, exact aliases, prefixes, then other substrings;
description-only matches follow when requested. Use deterministic lexical
tie-breaking for display, never to choose an installation source or artifact.
One package row groups its releases/builds, and lists its named sources.
Different CLI areas remain distinguishable. An alternative search name is not
an installation alias and must not change the resolver's request grammar.
Inspecting the package and enumerating its releases are separate actions.

Package records need canonical name, aliases, summary, description, category and
area, with explicit channel/platform/source bindings in their release view.
Show source evidence and explain the match. Installed state is an independent
overlay: until it is integrated, say it was not inspected rather than marking
everything uninstalled. A catalog-known artifact need not exist on the machine.
Do not claim a live availability check merely because a locator is advertised.

Search reads the explicitly chosen local snapshot and reports its identity.
Metadata acquisition/update is separate. An incomplete view is an error, not a
negative package result. Show freshness information when an authenticated
publication/update model supplies it; a revision or content digest alone proves
neither currency nor publisher authenticity.

Keep searchable package metadata separate from release/build records so adding
a version does not multiply ordinary search hits. Search indexes are derived,
rebuildable data. Start with versioned files and linear local search; neither a
database nor a remote search service is a prerequisite. Explicit pattern search
can be added later; the prototype has no regexp or glob mode.

## 4. Keep the state dimensions separate

| Dimension | Meaning |
| --- | --- |
| Catalog-known | An accepted snapshot describes a release/build and its acquisition references |
| Cached | Metadata or payload bytes are present locally; bytes may still need verification |
| Retained/verified | Exact content and required provider references are locally protected and verified |
| Installed | An area/profile has committed installation references to that artifact |
| Selected | A profile or next-boot deployment selects installed content under a recorded policy |
| Running | The booted deployment or an existing process is using specific content |

These are dimensions, not a mandatory linear progression: installed artifacts
can outlive catalog entries, and retained dependencies need not be direct user
installations. A catalog refresh cannot uninstall, activate or physically collect
anything. A transport failure cannot silently select another build or provider.
Trust/security status is also separate from presence or selection.

Read-only discovery uses accepted local metadata and makes freshness visible.
An explicit update refreshes the configured catalog view. Install resolves a
pinned snapshot first and acquires exactly the approved content. A cache entry
alone never counts as a completed installation or verified dependency closure.

## 5. Names, identities and acquisition references

Preserve the selector contract's request/release/artifact distinction:

| Record | Purpose |
| --- | --- |
| Request and policy | What the user follows or pins, including its catalog/channel/platform binding |
| Release identity | A publisher-declared version/revision with a named comparison scheme |
| Artifact/build identity | The exact immutable build, payload and runtime dependency references |
| Descriptor | Content/integrity, architecture, kind, requirements, provided capabilities and provenance |
| Locator/provider reference | Where or through which adapter the exact artifact can be acquired |
| Catalog snapshot identity | The exact offered set and policy evidence used for resolution |
| Deployment identity | The exact Base/System/Kernel/boot-artifact combination |

Mutable mirror locations, download success and channel promotion do not change
payload identity. Native artifacts need a digest of a versioned immutable content
descriptor; its file inventory/content digests and exact dependency references
are part of the binding. Transport metadata separately binds the archive digest.
Exclude self-referential IDs, signatures and mutable locators
from that digest. The serialization/canonicalization rules must be specified
with the writer. The [native package prototype](native-artifact-format.md)
specifies an initial canonical descriptor and namespaced tar.zst, including an
embedded descriptor and identical external metadata copy. Its archive digest
lives outside the archive to avoid a self-reference. An archive digest and an
extracted-tree digest are different evidence and must not be interchanged.

Provider identities stay explicit. Existing Nix output identities and NAR/closure
evidence remain opaque provider records; a Nix store-path hash is not relabeled
as a native payload hash. A shared payload can have several declared locators,
but cross-provider equivalence requires verified evidence, not matching names
or version strings. Source preference and ambiguity handling follow the existing
[selector contract](mpm-selectors.md).

Mojt public names are catalog mappings. An unqualified name resolves within the
chosen trusted catalog view. Conflicting providers require an explicit recorded
preference or an ambiguity error. Provider qualification syntax remains open;
do not add an implicit "try every backend until something installs" policy.

For example, a Mojt catalog may advertise a native Linux kernel and a Nix-backed
Neovim candidate. Both are discoverable before installation. Selecting the
kernel requires only the native provider; selecting Neovim uses its recorded
Nix reference. An absent Neovim entry is reported as absent from that catalog.
Broader external discovery requires an explicit provider/catalog operation,
with its provenance visible, rather than an invisible fallback during install.

## 6. Artifact contents and dependencies

The descriptor model applies across all areas, while preserving their units:

| Artifact kind | Installation unit |
| --- | --- |
| Base | A complete immutable Base release, retaining its existing release manifest/provenance |
| System component | A service, program, firmware collection or other System-owned component |
| System generation | A coherent immutable composition of exact component/dependency references |
| Kernel | One exact kernel build with its matching module tree and build/configuration metadata |
| Port | An application/tool and its exact declared runtime references |

System generations may refer to Mojt-native and optional external-provider
objects together. They do not have to copy those objects into one new archive.
Kernel remains a System-owned component with a separately selectable MPM scope.
An initramfs belongs to a particular boot deployment when it binds Base/System,
root identity and early-boot inputs; do not treat it as universally reusable.

Build inputs and runtime dependencies are separate edges. The kernel toolchain's
glibc is a build dependency. An own-built userspace executable linked to a Nix
library must retain that actual runtime closure; publishing it in a Mojt catalog
does not remove the dependency. Base/Kernel external capabilities, firmware
requirements, exact-build external modules and persistent-state compatibility
remain explicit constraints, not guesses from generic version strings.

The core tracks exact dependency references and delegates provider-specific
closure verification/import to an adapter. Start with publisher-resolved exact
dependency graphs and explicit external capability checks; a new universal
package solver is not a prerequisite. "Locally available" for installation
means all required runtime references are verified and retained, not just the
top-level archive. Content verification does not establish runtime ABI compatibility.

### Kernel tracking policy and selected Base compatibility

Kernel is a System-owned component with its own CLI/update scope. Support three
standard request policies, independently of the artifact's acquisition backend:

| Policy | Eligible releases before compatibility filtering |
| --- | --- |
| Pinned | A chosen major.minor series, following its stable patches; alternatively an exact release/build pin that does not advance |
| Latest LTS | Stable releases in catalog-declared currently maintained upstream LTS series |
| Latest upstream | The newest catalog-offered upstream stable release, including non-LTS series |

Pinning the series `6.12` means accepting newer `6.12.x` patch releases, not
moving to a newer series. Exact release/build pinning remains available within
the pinned policy. These are two explicit forms of a pin, not a silent
interpretation change. Moving an exact build is always explicit. RC/development
versions are outside these three standard policies; they need an explicit future
preview workflow. An explicitly pinned, no-longer-maintained series may remain
usable, with its maintenance status visible; it is not a latest-LTS candidate.

All policies intersect with the **selected Base's declared kernel bounds** and
platform requirements before choosing a release. A Base maximum is a hard limit,
including for a newer LTS. Select the highest eligible compatible version from
the pinned snapshot, and explain excluded versions. An exact incompatible pin
fails; it does not float down to an older release. If no LTS is eligible, do not
switch to non-LTS or upgrade Base automatically. Additional declared System,
hardware, firmware and module constraints may further restrict the complete
deployment. Bounds are declarations, not a claim that every in-range combination
has passed runtime acceptance; missing required compatibility evidence must be
reported rather than guessed from Base or kernel version numbers.

"Latest" means latest in the explicitly selected complete catalog, not a live
kernel.org query. LTS/stable classifications come from maintained publisher
metadata, not a heuristic based on version numbers or the builder's host. Keep
the policy, resolved exact identity and snapshot evidence separately. Refreshing
metadata changes none of the installed, selected or running kernel content.
A Kernel upgrade preserves selected Base/System userspace; activation is a
separate complete deployment decision. The read-only prototype requires an
explicit Base-context document; automatic selected-deployment lookup and
persistent Kernel policies are future installer work.

## 7. MPM core and optional adapters

The core owns catalog bindings, selectors, policy, exact references, plans,
area boundaries, transaction state and history. A native provider owns native
descriptor/payload acquisition and staging. A Nix adapter owns Nix evaluation,
binary substitution, closure/NAR verification, registration and retention.

The core must start, inspect native catalogs and install native artifacts with
no Nix executables or daemon available. It must not import an optional adapter
merely to run native/read-only operations. A selected external candidate may
require its declared adapter; a missing adapter is a clear prerequisite error,
not a reason to change the candidate.

This is a common metadata/control model, not a requirement to force all bytes
into one physical store. Native content belongs in a Mojt-managed immutable
area. Nix-backed runtime content retains the layout its binaries require.
References can share already retained provider objects without duplicate
installation ownership or silent changes to another area's selections.

## 8. Publication and trust

Publisher authority and allowed catalogs/areas are administrator-controlled.
Trust roots and the initial catalog snapshot can be supplied on installation
media; mirrors and transport endpoints do not automatically become authorities.
Installing a catalog entry does not authorize embedded shell hooks or a new
publisher key. Local build import records an explicit local trust/provenance
decision rather than claiming an official publisher signature.

Remote publication needs authenticated catalog/descriptor bindings and payload
digests. A digest detects changed bytes; it does not authenticate a publisher.
Catalogs, descriptors and archives are untrusted inputs until validated, with
bounded parsing, version checks and safe staging/extraction.

The implementation must define key rotation/revocation, snapshot rollback and
expiry policy before claiming production repository trust. Retain the last
accepted sequence/digest per catalog binding; an ordinary update cannot silently
replay older metadata. Intentional historical selection is distinct from a
catalog refresh. Expose uncertain clock/freshness conditions when offline;
do not invent current security freshness or silently disable verification.
Use an existing reviewed signing/update mechanism rather than designing custom
cryptography. This document does not specify that mechanism or declare it working.

## 9. Retention and local data

Keep catalogs/descriptors and installed state inspectable as versioned records.
Use immutable snapshot files, atomic publication of complete local metadata and
existing transaction locking patterns initially. A small database is optional
for derived search/index acceleration later; it is not the release authority or
a prerequisite for the first native repository. A remote database is unnecessary.

Retain the descriptor/provenance required to understand installed artifacts even
after a newer catalog drops them. Keep the accepted catalog snapshot/digest used
by a transaction. Payload GC must protect installed dependencies, selected and
running deployments, recovery references and project pins. Catalog absence and
package removal are not sufficient evidence that bytes can be deleted.

Offline recovery relies on retained content and trust records, not a promise
that an upstream URL will survive. For rebuild independence, retain recipes,
configuration, source identities and sufficient source/toolchain inputs where
redistribution permits; any remaining external acquisition requirement stays
visible. Serving a Mojt catalog alone does not make every referenced dependency
self-hosted or self-contained.

## 10. Current implementation and migration

The [entry point](../tools/mpm) now supports explicit local discovery commands;
existing Ports commands still dispatch to the experimental
[Nix prototype](../tools/mpm-nix-prototype). In native-attribute Ports mode,
`install neovim` uses the locally recorded pinned nixpkgs source: it resolves
the requested name/attribute there when not already in its local package map.
It is not a search across Mojt-native and arbitrary other repositories.
Its `update` refreshes metadata from its configured source pin; it is not yet
the repository-snapshot updater proposed above.

The existing [pure resolver](../tools/mpm_selection.py) already accepts finite
`mpm-release-catalog-v1` candidate lists with named sources, opaque backend
identities, integrity evidence and catalog digests. Format-3 selector mode
installs from its explicitly adopted catalog. A Nix catalog exporter can feed
that model without making Nix the core authority.

Build on that contract: add publication envelopes/descriptors and a native
acquisition adapter, keeping release selection independent. Dependency, trust
and descriptor references need explicit versioned extensions; they cannot be
silently inserted into today's strict v1 catalog schema. Preserve format-2
native Nix requests and format-3 source/policy bindings. Migration or catalog
adoption must be explicit; the same name cannot silently switch providers.
Older writers must refuse metadata capabilities they cannot preserve.

Existing Base release manifests, System manifests and `mojt-kernel-input-v1`
are inputs to native descriptor adapters. Do not claim these are already one
portable distribution format or reinterpret their recorded content IDs.
Existing fresh-image tests do not establish existing-disk boot publication.

## 11. First implementation slices and acceptance

1. Implement a read-only local discovery envelope with search/show/versions,
   wrapping the unchanged strict v1 release catalog. Reuse the resolver for
   Kernel policy plans constrained by an explicit selected-Base context.
   This is the bounded prototype in PR #28; no installed state is adopted.
2. Specify a native descriptor and exact references. PR #28 now prototypes a
   common container for Base/System/Kernel/Port, category-rooted members and an
   embedded descriptor, with a matching-build Kernel export adapter. Four-kind
   fixtures and source/configuration evidence checks pass. The owner's
   [real Kernel package acceptance](native-artifact-format.md#owner-native-package-acceptance-2026-10-29)
   also passed on 2026-10-29: Mojt export and independent Debian verification of
   the same exact artifact preserved existing build/configuration evidence,
   without recompilation. This does not implement installation or activation.
3. Implement native verification and install/status planning
   without Nix installed or a network connection. Installing a kernel does not
   change the selected deployment. Preserve the first-install Ports exception
   and all other [MPM operation semantics](mpm.md). The first
   [local Kernel install/status prototype](mpm-kernel.md) now retains an exact
   archive and private read-only tree with an atomic installation record. It
   rejects unsupported requirements/dependencies and does not select a boot
   deployment. PR #29 passed owner real import/status/no-op acceptance and merged.
   The next [read-only complete deployment planner](kernel-deployment-plan.md)
   ties the installed Kernel/image/modules to explicit selected Base/System and
   initramfs declarations, with compatibility gates and no boot writes. It
   verifies Kernel bytes but not Base/System payloads or actual initramfs logic;
   successful output explicitly does not establish boot readiness.
   Base/System/Port native installation remains separate work.
   The next [fresh native image builder](native-image-build.md) exercises complete
   native Base and installed Kernel inputs with the current optional System
   payload adapter, independent module mounts and generated/inspected initramfs.
   It bootstraps only a new image; it is not an existing-disk mutation command.
4. Add repository publication/update and interchangeable local/HTTPS transports
   with an explicitly specified trust mechanism. Metadata refresh does not fetch
   payloads, compile anything or change installed/selected content.
5. Reuse the descriptor/acquisition contract for complete Base releases and
   Mojt-owned System components. Introduce existing-disk boot activation as a
   separate increment with complete deployment validation and recovery behavior.

Focused acceptance must cover a catalog-known but absent artifact; discovery
without acquisition; an offline cache hit and missing dependency; bad integrity,
unknown schema/untrusted source and ambiguous name rejection; an idempotent
install; a failed refresh preserving the previous snapshot; installed content
surviving catalog withdrawal; and unchanged Base/System/Kernel/Ports selections
outside the requested action. Verify native operations with Nix unavailable.
Exercise exact opaque references with a fake external adapter before reusing
the real Nix bridge. Installation/update criteria remain future acceptance work.
The prototype's focused tests cover literal search/ranking, opt-in descriptions,
snapshot/schema failures, the three Kernel policies and Base limits, ambiguous
build rejection, unchanged input files and operation without provider files or
executables. No repeated VM account/network/generation loop is required.

The immediate deliverable is this architecture plus the local read-only
catalog, native packer/verifier, local Kernel install/status and read-only complete
deployment planning prototypes. They create no repository service, package
migration, signing system, automatic
catalog acquisition or Kernel deployment activation. The experimental native canonicalization is specified; storage
paths, publisher key policy and mutation grammar remain open decisions. The
discovery envelope is a separately versioned experimental format, not a silent
extension of the existing v1 resolver.
