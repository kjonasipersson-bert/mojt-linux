<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# First configuration/request implementation

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
requires the later installed-profile planner. Conflicting declarative defaults
fail, including identical selectors bound to different sources.

Public Python entry points: `parse_configuration`, `empty_state`,
`reconcile_configuration`, `request_interactively`, `select_interactively` and
`validate`. They return copies and content identities; failure leaves the input
unchanged. Exact selection records intent only: the caller must verify the
artifact is installed and provides the requested role before publication.
No availability or ABI claim follows from a structurally valid reference.

Remaining: non-Ports state reconciliation, source/catalog resolution and locks,
installed-role/alias validation, removal/fallback planning, state publication,
frontend/System runtime integration and public configuration apply/reset syntax.
The normal imperative prototype still uses its existing path until explicitly
connected; no backward-compatible migration path is needed.

Validation: `python3 -B -m unittest discover -s tests -p test_mpm_requests.py -v`.
Tests cover parsing/version errors, normalization/idempotence, independent reasons,
removal, override precedence, first-install default preservation, multi-source
conflicts, source binding and unchanged inputs on failure. No manual VM test is
needed for these pure functions; the joined installed-machine flow remains later.
