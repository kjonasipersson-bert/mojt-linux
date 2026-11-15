<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Profile the installed stage path before further optimization

The accepted [E/F SSD test](initramfs-payload-hardware-test.md) measured about
229 s wall / 219 s CPU for warm preparation, including about 45 s of candidate
checks. The next step is measurement, not removal of checks based on guesses.

`tools/mojt-stage-profile.py` is a standalone maintenance diagnostic. It runs the
real `/run/mojt-system/tools/mpm-system` launcher with ordinary
`system stage --artifact ID -y --json` arguments, under the installed MPM Python.
It temporarily wraps the installed functions in that process to measure their
unchanged calls, return values and exceptions. It restores the functions on
success and failure. It never installs profiling code into the System or patches
the constructor files. Consequently their measured code identities and the
payload-cache key remain unchanged. There is no new public MPM flag or format,
and the diagnostic is not added to the installed manager's file list.

This is a real preparation operation: it retains a new deployment/receipt when
needed. It does not select, activate, install a System package or reboot. All
existing stage checks, copying, cache decisions, locking and publication run as
usual. The diagnostic checks that the running deployment and menu stay exactly
the same. It does not bypass admission for the measurement.

## One-file SSD test after E/F acceptance

Save the reviewed exact `tools/mojt-stage-profile.py` delivery as
**/root/stage-profile.py**, using USB as before. Leave the accepted F running and
selected, and preserve `/var/lib/mojt/initramfs-payload-55`.

```sh
python3 /root/stage-profile.py
```

The script uses the installed isolated Python automatically. Default mode reads
the E/F checkpoint and prepares retained **E** with the unchanged manager in F.
E's old bootstrap slot used the previous constructor, so this should produce a
fresh exact deployment while reusing the payload already built in the E/F test.
The helper checks a new deployment, `initramfs_payload.reused: true` and the exact
accepted payload inputs ID. A no-op or unexpected cold build cannot be presented
as a successful warm sample. A previous diagnostic run or an independently
prepared identical E may instead produce a no-op; keep that result for inspection.

The exact public MPM command is printed before confirmation. Answer `y` for
the measured preparation. Running F and next boot remain F; no new package,
System transition or deliberate reboot is needed for this diagnostic. The shell
wrapper is not a subprocess in this measurement: its installed Python launcher
is executed in the observing process, with the same frontend/defaults/checks.

For another deliberately chosen installed System, `--artifact sha256:FULL_ID`
is available. That explicit mode does not assume the E/F payload key or warm
cache. An unprepared exact deployment is needed for a complete preparation
sample. An unchanged selection and successful no-op are reported as an incomplete
sample, not a performance success.

## Read the results

Progress and phase durations appear live. At the end, the compact summary shows:

- Wall and total CPU for each coarse phase: candidate checks, runtime selection
  and description, source identity, handover preparation, constructor work,
  payload cache, slot retention and final admission. Nested phase IDs/parents
  are retained in the full report.
- The functions with the largest **own wall time**, after subtracting their
  observed direct children. This includes their unobserved work and waits; it
  is not a claim to have timed every source statement or syscall separately.
- Individual slow tree scans and Nix query/verification totals, with call counts
  so repeated work is visible. Archive writing, gzip compression and archive
  inspection are observed separately if construction actually occurs.
- Total Python CPU and CPU of completed child processes, distinguishing Python
  work from provider/decompressor work. Child CPU can exceed elapsed time with
  parallel subprocesses. Nix daemon/server CPU is not charged to this process.

Phase times and nested call/tree/Nix totals overlap; **do not add inclusive
totals**. Own times partition the observed call tree, with timer/reporting
overhead and unobserved work remaining in their enclosing function. Wall time
includes I/O and lock waits. This is coarse function profiling; add finer probes
only if the remaining own time identifies a function that needs them.

Evidence is saved in a new protected **/var/lib/mojt/stage-profile** directory:

| File | Contents |
| --- | --- |
| `summary.txt` | Compact human-readable durations, own-time ranking and slow scans |
| `profile.json` | Nanosecond duration counters, call counts, phase hierarchy, tree paths, script/interpreter identity, MPM exit code and full result |
| `mpm-result.json` | Unmodified public MPM stdout JSON |
| `stage.log` | Original MPM stderr plus live phase progress |

Send the summary or photographs of its timing sections first. No evidence is
uploaded automatically. Setup imports, status checks, the confirmation prompt,
final status checks and summary writing are outside the timed MPM call. This
omits normal process/interpreter startup and adds observer overhead. It does
not provide cold-cache or uninstrumented timing claims; caches are not cleared.
The owner measurement below records one observed run, not a general benchmark.

Existing evidence is never overwritten. On any error, keep the files and inspect
`mpm system status`. A failed/partial stage can have retained immutable content;
normal MPM publication semantics apply. Do not remove cache/checkpoint files to
force another sample. After inspection, `--output /var/lib/mojt/NEW_NAME` permits
a separate attempt. Reports are written even when the measured command fails.

## Validation status

Automated tests cover nested own-time accounting, real tree scans and tamper
refusal, exception propagation and restoration, the unchanged installed launcher
dispatch, constructor/payload-key identity under observation, and E/F context
guards. The diagnostic delivery `1b825382` passed all three CI jobs (run
`43697244149`). The automated tests are separate from the owner measurement.

## Owner phase profile — 2026-11-15

The owner supplied `summary.txt` from the requested installed-stage probe. Its
SHA256 is `51805aea0b35e0794b1aef66a98fb448163a5b29b9a997becd52658c6b62648d`.
Only that summary was imported; the full `profile.json`, MPM JSON and stderr log
were not supplied. It records MPM exit 0 and no failed measured phase. It does
not itself include the diagnostic's final context/reuse assertions, so this
record does not infer their result from the exit code alone.

Total measured MPM time was **233.777 s wall / 223.577 s CPU**, with 132.115 s
Python CPU and 91.463 s completed-child CPU (rounded components). The update
stage itself took 233.770 s wall. Candidate checks took 45.626 s within that
total, runtime selection/description/source identity 0.086/2.703/0.322 s,
handover preparation 38.107 s, and selection's preparation path 119.550 s.
The latter contains constructor work 60.523 s, slot retention 19.775 s and final
admission 39.188 s. These inclusive phases must not be added to their children.
Other work, including repeated preflight, falls outside this coarse phase list.

The **own-time** ranking identifies the following costs after subtracting
observed nested calls:

| Function/work | Calls | Own wall time |
| --- | ---: | ---: |
| Nix provider subprocesses (`_run`) | 759 | 99.074 s |
| Regular file SHA256 (`file_sha`) | 52,487 | 33.238 s |
| Other System object-record work (`object_record`) | 455 | 18.565 s |
| Tree measurement (`measure`) | 421 | 17.171 s |
| Canonical JSON (`canonical`) | 23,047 | 11.744 s |
| Profile-link checks (`verify_links`) | 7 | 10.727 s |

The Nix commands break down as **253 `--verify-path` calls taking 85.721 s**,
253 `--query --requisites` calls taking 6.759 s, and 253 `--query --hash` calls
taking 6.594 s. These are components of the 99.074 s Nix time, not extra costs.
Nix subprocesses account for about 42% of total measured wall time; full path
verification alone accounts for about 37%.

The planner `_prepare` ran **five times**. The slowest listed tree scans include
the same nixpkgs tree twice (3.626/3.616 s) and the same Kernel module tree at
least three times (1.256/1.252/1.250 s). Call counts do not establish how many
distinct files, System objects or provider identities were involved, but the
summary and call graph demonstrate repeated planning and some repeated scans.

In contrast to the larger constructor phase, **`cached_payload` took 0.455 s**.
No runtime-freeze or module-decoding phase appears in the summary. Constructor
and admission phases still contain full audits/rechecks; their names must not be
interpreted as time spent solely copying or compressing an initramfs.

The next optimization should separate the default path from repeated full Nix
and retained-file audits, keeping an explicit full-verification option. Share
operation-local checks for identical immutable inputs only where the existing
lock/snapshot contract permits; retain fresh selection, persistent-state,
compatibility and publication checks. Then address repeated object metadata,
hash and tree work. This is a measured priority, not an implemented policy change
or a predicted final latency. No further SSD run is needed to identify these
first targets.
