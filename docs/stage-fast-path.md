<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Ordinary stage checks and explicit content audits

The [owner phase profile](stage-profiling.md#owner-phase-profile--2026-11-15)
measured 253 full Nix path audits, 52,487 file-hash calls and five complete
planning passes. This increment keeps the planning/current-state gates but
separates full byte audits from normal preparation.

## Policy and scope

`mpm {base,system,kernel} stage --artifact ID` now runs with content scrubs off.
`--verify` explicitly requests the existing full retained-archive, realization,
provider, tree-proof and boot-file checks. `upgrade --verify` passes that request
to its preparation as well as selection. Ordinary activation/selection keeps its
existing fast behavior. Stage reports `verification_requested` in its public
JSON result; this is a requested policy, not an assertion that a dry-run
constructed/audited a new deployment.

The preparation policy is scoped to one call, reset on success/failure, and has
no persistent metadata cache. Standalone constructor/MBT/store library callers
outside that scope retain their existing full-check defaults. Existing boot,
binding, readiness and selection wire formats are unchanged. SHA256 remains
integrity evidence rather than publisher authentication.

Normal preparation still checks exact metadata/receipt/installation identities,
ABI and Kernel bounds, provider preservation, allowed startup changes, account
shells, required paths/links, firmware/profile compatibility, current defaults,
schema/recovery support, the physical target and boot selection. Existing shared
and exclusive lock boundaries and final mutable-state rechecks remain. These
checks are not replaced with a cached approval or a serialized plan.

Required copying/materialization and generated archives retain their byte
checks, size/path limits, external-command exit checks, durable writes and
atomic publication. A full byte audit is not silently claimed by normal stage.

## Operation-local reuse

- The Nix boot adapter adds metadata inspection: protected retention-root binding,
  exact registered closure and NAR hashes, and command inventory. Normal stage
  uses it instead of `--verify-path`. Its base Ports adapter and inherited full
  `verify` implementation are unchanged. Providers lacking inspection retain
  their full verifier as a conservative fallback.
- Unchanged provider metadata checks are reusable for the exact reference,
  helper and installation. Dependencies include the closure roots/bin directories
  and Nix database/WAL status. The GC-root/helper binding is checked on every
  call. Query failures or changed closure/registered hashes remain errors.
- Parsed metadata, metadata-only Base/System/Kernel object checks and repeated
  code hashes are reusable only while their dependency signatures match. Each
  lookup restats files and ancestors, including inode/device, owner, permissions,
  link count, size and nanosecond modification/change times. Replaced or edited
  metadata is re-read and validated. Caller mutations cannot change cached
  values; results are copied. Errors and missing results are not cached.
- The private cache is bounded to 512 entries and 32 MiB of charged metadata per
  preparation call. Alias paths are not cached. Mutable state planning is still
  rerun; a stat-based cache is not a fresh content proof. Explicit full audits
  bypass file-hash reuse.

Tree proofs may reuse **expected** measurements from already admitted entries
when the Base/System/Kernel artifact or complete provider reference and tree path
match exactly. The current canonical directory must still exist. Conflicting
measurements are refused. A new tree without such evidence is measured once to
construct its proof. `--verify` measures/audits the current content instead of
borrowing old measurements. No old receipt is rewritten, and reuse does not
claim that current bytes were freshly scrubbed.

Runtime description, first-time Base scaffolding, a changed payload generator
or other genuine payload inputs can still require construction. Cache input
hashes include the changed producer code, so the first preparation after this
increment can build a new payload. A subsequent compatible preparation is the
warm comparison. Installation/preparation integration remains separate work.

## Validation and owner test

Focused tests cover scope reset, normal/explicit verification dispatch,
replacement and permission invalidation, same-size content changes with restored
mtime, immutable metadata reuse, full-audit refusal of damaged payloads, provider
query/root failures, exact proof reuse and missing-tree refusal. Existing
constructor, admission, bootstrap, rollback and state gates remain regression
checks. New ordinary-stage timing on the owner's SSD is pending; no speedup is
claimed from the old profile alone.

The short delivery will run the reviewed new manager in a private complete code
bundle using F's installed interpreter/runtime. It prepares retained alternatives
without installing another System, changing next boot or rebooting. This is an
explicit maintenance test of new code, not a claim that installed F already
contains it. The ordinary installed profiler remains available for final
measurement after the normal tooling update.
