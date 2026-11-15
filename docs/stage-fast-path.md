<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Ordinary stage checks and explicit content audits

Ordinary preparation preserves planning/current-state gates while separating
full byte audits from required metadata and compatibility checks. Explicit
`--verify` requests the retained-content audit path.

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
- Successful Nix closure/hash queries are reusable for the exact reference,
  helper and installation during one ordinary stage. A separate bounded cache
  (512 entries / 32 MiB charged identity data) is independent of general metadata
  cache occupancy, symlink aliases and database/WAL file status. A database write
  does not itself invalidate the already checked immutable provider identity.
  The retention-root/helper bindings, existence of every closure directory and
  current command inventory are checked on every call, including cache hits.
  Query failures are not cached. New or changed identities query again; the
  cache is discarded on return or failure. Outside stage, or under `--verify`,
  queries are not reused; the full verifier remains unchanged. This deliberately
  reuses a check from earlier in the same operation, without claiming a fresh
  database read or content audit at every phase.
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

## Profiling

The installed diagnostic profiler records actual phase and provider costs.
Profiling is an explicit diagnostic operation and does not change normal
verification or next-boot selection policy. Measured timings belong to
[test reports](reports/README.md), not latency guarantees.
