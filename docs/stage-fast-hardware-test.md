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

Owner results are pending. This short test establishes preparation/performance
only; it does not claim a new physical boot or installed-tooling delivery.
