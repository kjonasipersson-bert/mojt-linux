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
No fixed bottleneck conclusion is made before the owner measurement.

Existing evidence is never overwritten. On any error, keep the files and inspect
`mpm system status`. A failed/partial stage can have retained immutable content;
normal MPM publication semantics apply. Do not remove cache/checkpoint files to
force another sample. After inspection, `--output /var/lib/mojt/NEW_NAME` permits
a separate attempt. Reports are written even when the measured command fails.

## Validation status

Automated tests cover nested own-time accounting, real tree scans and tamper
refusal, exception propagation and restoration, the unchanged installed launcher
dispatch, constructor/payload-key identity under observation, and E/F context
guards. These tests do not claim that the diagnostic has run on the owner's SSD.
The actual phase breakdown remains pending owner execution.
