<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Focused fast-install and activation hardware test

Run after the reviewed delivery head's CI passes. Functional code is pinned to
`991714acfab88676521599ca8f303cd24b09590f`, which passed all three CI jobs.
The USB script has an exact SHA256 for each of its nine downloaded files. These
are reviewed maintenance inputs, not signed native releases. The original A/B
script and checkpoints remain historical; do not replace/delete their state.

This test needs two deliberate boots: into **C** to run the new manager, then
into **D** to accept the measured selection. It keeps the existing SSD,
Base, Kernel, firmware policy and provider dependencies. No full hardware matrix,
source compilation, service migration, Ports upgrade or reinstallation is needed.
The script never reboots. Start as root on the installed SSD with no pending boot
choice, in the accepted Ports-fix System or original activation A/B.

## Delivery

On the computer showing the chat, download `tools/mojt-system-fast-test.py` from
the reviewed exact delivery commit, save it as **fast.py**, then transfer it over
USB to **/root/fast.py**. No long URL or artifact ID needs to be typed on Mojt.
The chat supplies the exact download link and one next command at a time.
No Git/compiler/checkout is needed on Mojt; use its installed Python.

The helper only supplies exact long arguments, packages the small owned tooling
component and records evidence. Before every changing command it prints
`+ mpm ...`; those are real calls to `/run/mojt-system/bin/mpm`. It does not replace
MPM installation or boot-selection logic. Package assembly reuses the installed
native packaging API. This test does not build a Kernel or bootstrap a disk, so
it does not claim MBT build/bootstrap acceptance.

## 1. Prepare packages only

```sh
python3 /root/fast.py prepare
```

Expect C (`system-activation-C`) and D (`system-activation-D`) with different
versions and exact artifact IDs. This downloads pinned files and packages only
the owned component; it does not copy the Nix closure. Existing System content,
startup/service data, provider dependencies and state schemas are preserved.
Next boot stays unchanged. Preparation/package audits are outside performance
samples; they may take time.

If any command fails, stop and keep its error/evidence. Inspect with:

```sh
python3 /root/fast.py status
```

Existing log/result names are never overwritten. An interrupted preparation or
failed operation is inspected before retrying; deleting evidence is not a repair
step. A post-publication error may mean the boot choice was committed: inspect
status before retrying or rebooting.

## 2. Enter C using old MPM

```sh
python3 /root/fast.py enter
```

Confirm the transition. It visibly invokes old MPM three times: install **only
C**, `stage` C, then `select` the exact staged C deployment with the original
expected-selected guard. Installation and staging leave next boot unchanged;
selection is the sole commit. This one-time transition can still be slow because
it runs the old manager. Its `bootstrap-*` timings do **not** measure new MPM.
D remains packaged but uninstalled, so its later installation uses the new code.

When `READY: C selected` appears, deliberately reboot:

```sh
reboot
```

After logging in, inspect the public interface:

```sh
mpm system status
```

Running and next boot must both be `system-activation-C`.

## 3. Measure D installation and preparation separately

```sh
python3 /root/fast.py install
```

Confirm. The printed command is new installed `mpm system install`, with explicit
local generation/component paths and IDs, `-y --json`, and **no `--verify`**.
The wrapper checks pinned running tools before timing. Expect D installed, C
still running/selected, and one `install: ... s wall, ... s CPU; exit 0` line.
A previously installed D is refused so a no-op cannot be presented as a fresh
installation sample. The candidate's frontend/interpreter are never used to
perform its installation.

Next:

```sh
python3 /root/fast.py stage
```

This visibly runs new installed `mpm system stage`, preparing/admitting D and
leaving C selected. It still performs construction and admission checks and may
take time. Its `stage` timing is preparation cost, never activation latency.

## 4. Exercise the actual interactive chooser

```sh
python3 /root/fast.py cancel
```

The printed public command is `mpm system activate`. Enter **0**, then **q**.
Expect an invalid-number reprompt, explicit cancellation and unchanged next boot.
The helper requires those chooser messages as well as unchanged exact identities;
an unrelated MPM failure does not count as a passed cancellation test. The list
contains prepared candidates, with label and identity; no list number is assumed.
This interactive duration includes typing and is not a performance sample.

## 5. Measure activation only

```sh
python3 /root/fast.py activate
```

The helper displays exact D and asks for confirmation **before starting the
clock**. It then visibly invokes installed
`mpm system activate --artifact EXACT_D --expected-selected C_SLOT -y --json`,
with no `--verify`.
Long IDs come from the checkpoint, not keyboard input. Expect a prompt return:
selection should not scan payloads, run Nix or build initramfs. The output records
MPM's process wall/CPU time, excluding the helper's status/pin checks, your answer,
and its final evidence checks. No hardware speedup or fixed latency is claimed
before this measurement.

Expect exact staged D selected, C still running, identical original Base/Kernel
and boot policy, then `PASS`. Retained previous entries remain available.
Reboot deliberately only after successful selection:

```sh
reboot
```

Then:

```sh
mpm system status
python3 /root/fast.py after
```

Expect D both running and selected, exact staged deployment identity, unchanged
Base/Kernel, successful `mpm ports list` and Neovim `--version`.

## Evidence and optional return

Evidence stays on the SSD under `/var/lib/mojt/activation-fast-54`. The most useful
files are `install.json`, `stage.json`, `activate.json`, their `.log` files,
`cancel.log` and `after.json`. Each timed operation stores its actual argv,
return code, before-status and process `elapsed_ns`, `user_us`, `system_us` as
integers; `.log` retains stdout/stderr and `*-result.json` the MPM JSON result.
Successful steps also save `*-after.json`. Report the three printed times and
any errors first. Bootstrap and preparation times are separate evidence.
No logs are uploaded or posted automatically.

C remains the previous known deployment. To select that exact retained C when D
is running, without typing deployment IDs:

```sh
python3 /root/fast.py back
```

Confirm, inspect the printed `mpm system select` result, then reboot deliberately
if returning. This optional return changes next boot only and does not undo
persistent state or discard either generation.

The root-mapped automated tests exercise real packaging/installation plus runner
and guard behavior; they do not claim a physical boot, owner-machine timings or
new firmware coverage. Hardware acceptance remains pending until the owner
returns results.
