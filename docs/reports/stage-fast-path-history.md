<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Ordinary stage regression and performance history

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

## Validation and owner test

Focused tests cover scope reset, normal/explicit verification dispatch,
replacement and permission invalidation, same-size content changes with restored
mtime, immutable metadata reuse, full-audit refusal of damaged payloads, provider
query/root failures, exact proof reuse and missing-tree refusal. Existing
constructor, admission, bootstrap, rollback and state gates remain regression
checks. The [owner SSD result](../stage-fast-hardware-test.md#recorded-owner-result--2026-11-15)
measured 134.812 s cold and 66.369 s warm, compared with the previous 233.777 s
profile: 71.6% shorter warm elapsed time. Both calls exited 0 with zero
`--verify-path` commands. Warm payload reuse took 0.285 s. Nix metadata queries
still ran 253 times each; the intended query cache did not reduce that count on
this machine, and the summary does not identify the cache guard responsible.
The final performance follow-up replaces that stat-dependent provider cache
with the operation-local query cache above. Regression tests exercise seven
passes with two queries total despite real SQLite WAL writes, a symlinked bin
directory and a full general metadata cache. They also cover missing objects,
root/helper rebinding, changed identities, query errors, scope reset and explicit
audit bypass. The [final SSD measurement](../stage-fast-hardware-test.md#final-nix-query-cache-measurement--2026-11-15)
confirms 36 queries of each type (72 commands, 1.887 s) and warm stage at
55.171 s wall / 54.713 s CPU, compared with 66.369 s before this last fix.
Both measured calls exited 0, with exact warm reuse and unchanged selection
guarded by the helper. This is a 16.9% further reduction; no new installed-tooling
delivery or physical boot is claimed. Further performance work is deferred so
development can return to the roadmap.

The [short SSD test](../stage-fast-hardware-test.md) runs the reviewed new manager
in a private complete code bundle using F's installed interpreter/runtime. It prepares retained alternatives
without installing another System, changing next boot or rebooting. This is an
explicit maintenance test of new code, not a claim that installed F already
contains it. The ordinary installed profiler remains available for final
measurement after the normal tooling update.
The short-test helper now pins the final query-cache follow-up at `47001725`
and writes separate evidence under `/var/lib/mojt/stage-nix-57`. It requires
reduced Nix query counts as well as exact warm reuse and unchanged selection.
Preserve the previous measurement under `/var/lib/mojt/stage-fast-57`.
