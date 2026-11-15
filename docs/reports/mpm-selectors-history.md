<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Selector resolver and transaction acceptance

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

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



## Owner acceptance completed (2026-10-27)

The owner ran the isolated real-Nix transaction harness with hello 2.12.1 and
2.12.3. The final checks passed: installed series activation selected the new
artifact, repeat upgrade changed no state/history/profile, and both executable
artifacts remained available. Reaching the final checks also establishes the
preceding preview, later-install, exact-pin and moving-alias assertions in that
fail-fast harness. No live System/Ports state was changed by the isolated lab.

A fresh step-10 VM then completed system-selectors-A / 6.12.107+deb13-amd64 ->
system-selectors-B / 7.2.9+deb13-amd64 -> A, with Base 0.1.3 and the new MPM in
both System profiles. A imported hello 2.12.3 via the native policy, exported a
real local catalog, explicitly adopted hello@2.12 into format 3, and executed
both hello and hello-2.12. Ordinary-user install, activate, upgrade and metadata
mutations were denied on A with the administrator requirement.

B's fail-fast checkpoint script reached its final PASS after verifying A's
complete state/history/profile/aliases and stable identities, explicitly pinning
the exact release, retaining the series alias and verifying an upgrade no-op.
The supplied final A output established complete equality against that B
checkpoint, including format 3 and exact pin, unchanged upgrade history and both
executable aliases. Journal output listed all three boots; /etc, /var, /home
and /root markers survived. The repeated ordinary-user check on B was explicitly
waived by the owner to avoid redundant testing; it is not claimed as performed.
The measured changed-release operation is the Distrobox test, not this VM's
single-release persistence/policy test. Libc/desktop runtime analysis remains
deferred. Retain the tested serial image as the reference.

Future acceptance should exercise changed behavior and relevant automated
regressions, with only necessary VM integration checks; repeat a check when a
new change or unresolved failure justifies it.
