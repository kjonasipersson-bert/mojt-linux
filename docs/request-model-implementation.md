<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# First configuration/request implementation

This increment supports steps 1 and 2 of the
[governing six-step plan](mpm-consolidation-plan.md); it does not complete the
installed MPM workflow or supersede Base/System, bootstrap and build integration.

`tools/mpm_requests.py` implements a provider-independent, standard-library-only
configuration parser and pure Ports request ownership model. It executes no
commands, resolves no catalogs, installs no payload and writes no state. This
is implementation of the next core boundary, not a new public CLI or an
existing-disk updater. [Initial format policy](format-policy.md): fresh installs,
versioned records, no legacy format conversion.

Implemented: strict versioned TOML for all four areas, numeric-series/exact/latest
selectors via the existing pure parser, Kernel policy validation, normalized
semantic revisions, and versioned Ports claim/selection records. Reconciliation
releases only a named configuration's claims and owned explicit defaults.
Other configurations, interactive claims and exact overrides persist. Adding an
interactive wish does not activate an additional version. Existing still-owned
first-install defaults can be preserved; actually deciding first-install/fallback
is now handled by the [installed-profile publisher](ports-profile-implementation.md). Conflicting declarative defaults
fail, including identical selectors bound to different sources.

Public Python entry points: `parse_configuration`, `empty_state`,
`reconcile_configuration`, `request_interactively`, `select_interactively` and
`validate`. They return copies and content identities; failure leaves the input
unchanged. Exact selection records intent only: the caller must verify the
artifact is installed and provides the requested role before publication.
No availability or ABI claim follows from a structurally valid reference.

`mpm_request_plan.py` now resolves Ports claims through the shared pure selector
against explicit finite source snapshots and adapter offers. It returns versioned
exact locks and preparation plans for acquisition/import and retaining candidate
wishes. It never publishes a profile or boot choice. Full references identify
shared objects; two origins can share import while retaining separate claims.
Exact active overrides require caller-verified installed references.

Native offers bind archive hashes; provider identities/integrity remain explicit
adapter-owned data. These functions do not authenticate metadata, prove runtime
ABI or inspect physical content. Missing sources/bindings, stale locks, conflicting
offers, unsupported target platform and missing/cyclic dependencies fail rather
than fallback or build. Initial dependency closure stays within each explicitly
named source's finite offers, with depth bounded to 64; cross-source acquisition
requires a later explicit source binding rather than guessing.

`revalidate_preparation` compares target/installation/executor and the actual
request/selected baseline. Running state is informational. The caller must hold
existing cooperating resource locks, freshly verify content and authorize the
operation; the pure guard neither acquires locks nor grants permission. Final
profile assembly/publication is separate because its exact result does not yet
exist. Metadata-only wish removal prepares candidate data, never physical GC.

The [Ports profile increment](ports-profile-implementation.md) now adds actual
adapter acquisition, verification, alias/fallback planning and atomic publication
of requests, effective selection and history. It is an explicit fresh-store Python
API. Remaining: authenticated source acquisition, non-Ports reconciliation, native
Port archive import, imperative removal and public configuration reset. The fresh
Ports frontend/System runtime and Ports-only apply are now [connected](ports-cli-integration.md).
The ordinary frontend uses the fresh publisher; the old imperative prototype
remains a separate experiment. No backward-compatible migration path is needed.

Validation: `python3 -B -m unittest discover -s tests -p test_mpm_requests.py -v`.
Tests cover parsing/version errors, normalization/idempotence, independent reasons,
removal, override precedence, first-install default preservation, multi-source
conflicts, source binding and unchanged inputs on failure. No manual VM test is
needed for these pure functions; the joined installed-machine flow remains later.

Run both modules with `python3 -B -m unittest discover -s tests -p 'test_mpm_request*.py' -v`.
Planner tests also exercise exact source/provenance bindings, shared imports,
provider independence, no-op/removal plans, dependency order/cycles and stale
baseline refusal. No package import or public CLI behavior is claimed by them.
