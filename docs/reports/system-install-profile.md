<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# One-step System installation and preparation measurement

This procedure measures the complete ordinary System install command, including
automatic native-v2 boot preparation. It records the remaining copy/extraction
rounds, Python-process file/directory sync counts and their elapsed time. Nested
durations overlap and must not be added to the total.

## Preconditions and command

Use the reviewed checkout as root on native installed Mojt. Running and next boot
must identify the same deployment. The retained System needs the existing
single-runtime composition, numeric package revision and whole top-level profile
mappings. This procedure uses the installed retained Python, tar/zstd and provider
inputs. No new firmware acquisition or Kernel compilation is performed.

```sh
python3 -I -B tools/mojt-system-install-profile.py
```

The command freezes the complete reviewed manager/MBT resource cohort and the
diagnostic's support scripts in a new private run directory. A fresh isolated
process checks their identities before using them. The running manager is never
patched. It packages a fresh tooling-only System from the running generation's
owned content, preserving firmware, Kernel/Base/boot policy, services, provider
references and persistent state schemas. The unchanged-startup review must accept
that exact change. No package-provided interpreter or lifecycle action is run.

Packaging can take time and is reported separately, outside installation timing.
The measured call is the public `mpm system install --from-file ...
--expected-id ... --dependency-file ... -y --json` frontend using the frozen
reviewed code, including its normal checks and automatic preparation. It uses
disk temporary space under the diagnostic workspace. Both cold and reused
early-boot payloads are reported explicitly. Comparison with a prior cold build
must account for a reused payload rather than attributing all improvement to I/O.
This is the frontend operation's total in the diagnostic process, excluding
interpreter startup. Packaging has already imported modules and read the owned
content; the sample is not a cold-cache shell-to-exit benchmark.

The new generation is installed and prepared, **not selected**. Running System
and next boot must remain exactly the same after packaging and after the command.
The helper does not select or reboot. It retains the package, generation, prepared
entry and reports for inspection; it does not remove recovery content.

## Read the result

At completion, inspect these parts of the output together:

- `TOTAL install + boot preparation`: elapsed wall time and Python/completed
  child CPU for the one public command. Packaging and before/after status checks
  are excluded.
- The `_freeze` rows: required input archive copies and extraction. Inputs are
  copied for validation/retention; caller-owned archives are never moved.
- `build_profile`: the independent durable System profile materialization.
- `_retain`: private object placement. On the same filesystem this should show
  object moves and metadata syncs, with no payload/archive recopying.
- `copy_profile`: final private profile placement. On the same filesystem this
  should show a move, no file copies/syncs and directory syncs only.
- `Early-boot payload reused`: distinguish a warm preparation from a cold build.
- The final PASS means fresh content and boot preparation completed and the
  running/selected baseline remained exact. A no-op or skipped preparation is
  refused as an incomplete measurement.

Python-process sync timings are included in their phase/total wall times. Provider
and other subprocess file I/O/syncs are not observed; their completed CPU and
elapsed calls are recorded separately where supported. This is function-level
profiling with observer overhead, not a disk trace or power-loss experiment.

Reports are kept in a new `/var/lib/mojt/system-install-profile/run-*` directory:

| File | Contents |
| --- | --- |
| `context.json` | Baseline, frozen execution identity and support script checksums |
| `candidate.json` | Exact package identity/paths and generation label |
| `mpm-result.json` | Unmodified public frontend JSON |
| `phases.log` | Python phase messages; child stderr also remains visible live |
| `profile.json` | Inclusive/own timings, I/O counts, source evidence and result |
| `summary.txt` | Total, copy/sync rows, cache outcome and phase summary |

Keep failed runs for inspection. Do not automatically retry or clean retained
objects after an error. Each new invocation creates a distinct candidate label,
so a completed installation cannot be mistaken for a fresh performance sample.
This uses the real System payload and needs space for private packaging,
archives, retained objects and an installed profile; it is larger than the small
synthetic profile-placement benchmark. Booting the candidate is a separate test.
