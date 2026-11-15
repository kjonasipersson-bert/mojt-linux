<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native-v2 boot verification and profiling

Normal boot checks exact deployment/input bindings, readiness receipts, metadata,
required paths and current-state compatibility. It does not repeat complete
retained-content/provider byte audits. Explicit diagnostic/full-audit mode
retains those checks; skipping a full audit is not a new integrity attestation.

The runtime record at `/run/mojt/boot-checks.json` identifies the chosen mode,
`content_verified` and reader/current-state durations. Running identity records
what booted, independently of the selected next-boot deployment. See the
[handover contract](native-system-handover.md).

## Diagnose preparation or boot costs

Use `tools/mojt-boot-profile.py` with the retained System Python to measure the
installed reader/check graph. The profiler loads the installed tools; a checkout
does not silently replace the deployed manager or its embedded initramfs code.
It records actual observations, with a machine-readable report available through
`--json`. Nested timings overlap and must not be summed as independent phases.

Preparation profiling is separate from activation and boot. Ordinary activation
only chooses an admitted entry. Use the [stage policy](stage-fast-path.md) and
[operation boundaries](activation-performance.md) to interpret the measured work.
Historical timings and test-specific results are in
[the profiling report](reports/boot-performance-history.md).
