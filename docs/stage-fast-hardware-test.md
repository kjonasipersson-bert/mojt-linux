<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Short ordinary-stage performance test

Start with the accepted **F running and selected**, keeping the existing
`/var/lib/mojt/initramfs-payload-55` checkpoint. This test uses functional code
from `8b5c22b98f53587f79fbece136899b417343b3bb`, with per-file hashes, and the
unchanged profiler from `1b825382610660fbfc2920b977963b7f7b454a57`.
Use the exact reviewed delivery after its CI passes. This is reviewed maintenance
code, not a signed native release.

## One command, two preparations

Download the exact delivery's `tools/mojt-stage-fast-test.py` on the computer
displaying the chat, save as **stage-fast.py**, and transfer it by USB to
**/root/stage-fast.py**. Preserve `payload.py`, `stage-profile.py` and all previous
test evidence.

```sh
python3 /root/stage-fast.py
```

Confirm with `y`. The helper checks F's running/selected identities and the E/F
checkpoint, then downloads and verifies the pinned changed files and profiler.
It copies F's complete closed MPM code list, substitutes only those reviewed
files, hashes the resulting cohort and seals a private directory. It never
replaces files inside F or installs a new System generation. Each child probe
rechecks the private cohort before executing it under F's installed isolated
Python and normal target/provider defaults.

This explicitly tests **new MPM code in a private bundle**, not the old installed
MPM binary. The helper prints the real public stage arguments and identifies
the private launcher. The profiler observes that launcher's unchanged frontend,
stage checks and return/error behavior.

The helper performs two real preparations without selecting them:

1. Prepare retained E with the new constructor. Producer code has changed, so
   expect a first new payload build. This is the cold sample and can still take
   time; it is not the warm comparison with the previous 233.777 s profile.
2. Prepare retained D using the exact same new payload inputs. This is the warm
   sample. Expect `Early-boot runtime/drivers: reused` and a new deployment.

Each sample must return success, make a newly prepared deployment, leave the
running deployment/menu unchanged, report `verification_requested: false`, and
perform **zero Nix `--verify-path` commands**. The second must reuse the exact
first payload key. A no-op, unexpected full audit, cold reuse or different warm
payload fails the test rather than becoming a misleading performance sample.
Metadata queries, compatibility/current-state gates and command-error checks
remain enabled. No cache clearing, repeated benchmark loop, boot selection,
System package installation or reboot occurs.

## Send the result

Expect `PASS` and send:

```text
/var/lib/mojt/stage-fast-57/summary.txt
```

This contains both phase summaries. The **WARM STAGE** total is the relevant
comparison with the previous approximately 234 s installed-stage measurement.
No fixed speedup is promised before the actual run. Setup, downloads, copying,
code validation, startup, status checks and confirmations are outside the timed
MPM phases; observer overhead and potentially warm filesystem caches remain.
This is an engineering comparison using different retained System targets,
not a controlled cold-cache benchmark.

Individual results are under `cold/` and `warm/`: `profile.json`,
`mpm-result.json`, `stage.log`, and `summary.txt`. The private code and its exact
hash map remain under `code/` and `state.json`. No logs are uploaded automatically.

On failure, keep all evidence and inspect `mpm system status`. F should still
run and be selected, but a failed operation may have retained immutable content
or a complete deployment. Do not remove cache/checkpoint files to force another
sample. The helper refuses an existing work directory, preserving partial
evidence for inspection before any repeat.

## Recorded owner result — 2026-11-15

The owner returned `summary57.txt` (SHA256
`b5ca9285d80c9e0d17ac5cc38bbb0ec3906ffbdf33e2cc4fee1d42950f91ac19`)
from the private-code test pinned above. Both measured MPM calls exited 0.

| Measurement | Wall seconds | Total CPU seconds |
| --- | ---: | ---: |
| Previous installed stage profile | 233.777 | 223.577 |
| New cold stage | 134.812 | 125.894 |
| New warm stage | 66.369 | 65.992 |
| New warm candidate preparation (included in total) | 9.027 | 8.985 |

Warm elapsed time is 167.408 s shorter, a 71.6% reduction (3.52 times faster)
in this engineering comparison. The warm CPU total is 52.778 s Python plus
13.214 s children. Both profiles contain zero `--verify-path` commands.
The combined summary is written only after both probe validations and the final
installed-F status guard pass. Those validations require fresh deployments,
unchanged running/menu state, normal verification policy and exact cold/warm
payload-key reuse. The full JSON/log evidence was not imported.

Cold payload work took 57.004 s, including 43.334 s of gzip compression.
Warm payload work took only 0.285 s. The remaining warm costs include:

| Observed own time | Wall seconds | Calls |
| --- | ---: | ---: |
| Nix subprocesses | 13.197 | 506 |
| System link checks | 10.767 | 7 |
| Transition preparation | 7.089 | 5 |
| Canonical JSON encoding | 5.985 | 10,256 |
| Selected-context checks | 4.854 | 6 |

These are own times with observed child work subtracted; do not add inclusive
phase durations to this table. Nix still runs 253 requisite queries and 253 hash
queries, unchanged from the previous warm profile. Thus metadata-query reuse
has not reduced subprocess counts on this machine. The summary does not expose
which conservative cache guard prevented reuse, so no specific cause is claimed.
Repeated metadata/link checks are the next measured targets; payload reuse is
already cheap on the warm path.

This establishes bounded private-code preparation/performance only. It does not
claim a new physical boot or replacement of installed F tooling. No further
reboot is needed to interpret this result.
