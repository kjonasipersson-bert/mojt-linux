<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native-v2 boot performance investigation

The accepted System A/B/A VM showed roughly 24 seconds between the early Kernel
messages and backing-filesystem remount, before systemd started. This identifies
the early-boot interval, not its cause. Performance acceptance remains open;
the successful functional boot/return acceptance is not a latency measurement.

## Measure the existing graph first

Run `tools/mojt-boot-profile.py` as root with the selected System's Python on the
existing accepted native-v2 VM. The script loads the **installed** manager from
`/run/mojt-system/tools`, observes its unchanged calls, and checks the running
deployment's retained proof/handover receipt. It does not import a replacement
manager from a checkout. The deployed initramfs and measured code stay intact.

It times loading the reader, reading the running record/receipt, exact early
verification, and the current-state/boot-Base gates. Nested measurements include
individual tree scans, retained Kernel/initramfs file hashing, canonical JSON,
slot inspection and handover validation. These nested totals overlap the phase
durations and must not be added together. The default report prints a compact
summary and eight slowest trees; `--json` emits all observations and exact
deployment identity under `mojt-boot-profile-v1`.

The probe never calls `enter()`/`_enter()`, mounts/remounts, publishes a menu,
writes package/state records, executes a provider or clears caches. File reads
can populate caches and update access times on writable filesystems. As with
other integrity checks, run without concurrent installation or state edits.
An existing verification refusal is propagated, not relaxed for the measurement.

This is a **running-system recheck**, using the installed interpreter and
possibly warm caches. Its timings are not cold-boot claims: they exclude Kernel,
initramfs decompression/module loading, the private interpreter startup, mounts
and switch-root. Timer wrappers add small observer overhead. If its phases do
not explain the observed delay, instrument the actual initramfs boundaries next;
do not conclude that a fast warm scan explains a slow cold boot.

## Normal boot policy

The owner clarified that a normal Mojt boot must not run these complete content
audits. Integrity verification belongs at installation/staging and in explicit
diagnostics. Normal boot checks the exact deployment/installation metadata,
Kernel command line/release, required paths, current state and safe mount layout.
It does not rehash boot files, walk Base/System/module/provider trees, or snapshot
the boot Base. There is no persistent cached checksum pretending to be a fresh
verification. Current-state compatibility gates and read-only mounts remain.

The reader separates `inspect` (normal) from `verify` (full audit). Handover uses
inspection by default; an explicit `--verify-content` selects a full audit.
The existing profiling tool still measures a full audit because invoking it is
an explicit diagnostic action. Its previous timing results are therefore not
predictions for the new normal boot path. The faster inventory remains useful
for install/stage/select and diagnostics.

One fresh boot with the updated constructor remains the owner check: inspect
`/run/mojt/boot-checks.json`, which must report `mode=normal` and
`content_verified=false`, then confirm the exact deployment and healthy units.
The versioned `mojt-boot-checks-v1` report includes integer `reader_ms` and
`state_gates_ms`; these exclude Kernel/initramfs startup and mount/exec time.
Existing images keep their embedded reader, so another warm scan of the old VM
cannot test the new boot path. Another A/B/A matrix is unnecessary for this
inspection-only change. Keep the performance follow-up open until that boot is
measured, without requiring more inventory microbenchmarks from the owner.

## Owner measurement and first optimization (2026-11-10)

On the accepted VM, deployment
`sha256:12d493be77d2ead2d1ff550e422ac3614399120344fa8e726097f825e37b5f9a`,
Kernel `6.12.107-mojt1`, the installed probe reported:

| Work | Seconds |
| --- | ---: |
| Load installed reader | 0.146 |
| Read running record/receipt | 0.077 |
| Exact early verification | 13.642 |
| Current-state/boot-Base gates | 0.557 |
| Nested tree measurement: 210 calls | 13.366 |
| Slowest tree: nixpkgs | 8.493 |
| Native module tree | 1.343 |
| Nested canonical JSON: 124712 calls | 2.004 |

The measured graph had 123955 nodes / 1288.2 MiB plus the separate boot-Base
snapshot. All gates passed. These are running-system observations, not actual
cold-boot phase times; nested rows overlap.

The legacy System exporter explicitly adds the pinned nixpkgs source to its
outputs at step 3 and later. The System packager retains that source as an
explicit provider dependency for later Ports evaluation. Its many small files
therefore appear in the explicit full-audit graph. This change does **not** silently
drop that dependency from verification. Separating optional catalog/build data
from startup dependencies requires an explicit composition/storage contract.

The first optimization reduces work per entry: use scandir's child paths and
one no-follow stat at visitation, read through the existing checked descriptor
without a buffered Python file object, and reuse a canonical JSON encoder for
internally constructed measurement rows. External metadata validation remains
unchanged. All file bytes, metadata, hardlink relations, frame bytes and limits
remain covered; the proof format and digest are unchanged. There is no persistent
checksum cache or extra concurrency.

A local warm-cache before/new/new/before comparison of 20000 small files in 20
directories (20021 total nodes) took 0.477–0.482 seconds before and 0.221–0.228
after; all four measurements matched exactly. This development-host result is
not an estimate of the owner's boot speedup.

The probe supports `--compare-inventory FILE --expected-sha256 HEX`. It reads and
checks the explicitly supplied candidate code before compiling it, then invokes
the installed gates three times: installed, process-local candidate, installed.
Only the measurement/snapshot functions are temporarily substituted; the same
retained proofs and all current-state gates must pass, with matching deployment
and tree coverage. The installed functions are restored on success or failure.
No installed code, initramfs, proof, boot selection or package/state file is
replaced. The final installed run supplies a warm baseline; do not attribute
cache warming in the first run to the optimization. The report format is
`mojt-boot-profile-comparison-v1` (`--json` includes each complete run).

The owner's installed/candidate/installed comparison on the same deployment
passed both implementations against the retained proofs and current-state gates:

| Implementation | Early full audit (s) | Current-state gates (s) |
| --- | ---: | ---: |
| Installed before | 13.549 | 0.547 |
| Candidate | 11.616 | 0.568 |
| Installed after | 13.878 | 0.573 |

nixpkgs took 7.287 seconds with the candidate versus 8.637 in the final installed
run. This is roughly a two-second improvement to explicit auditing; it is not a
cold-boot acceptance result. The owner policy above removes that audit from
normal boot entirely, rather than relying on a faster mandatory scan.

Status: owner comparison passed; normal inspection and explicit audit are
separated in code/docs, with focused tests that forbid any content scan on the
normal path. One fresh normal boot remains pending; no further warm comparison
or repeated A/B/A acceptance is requested.
