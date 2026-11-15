<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Reusable initramfs payload: E/F hardware test

This is the successor to the accepted [C/D test](activation-fast-hardware-test.md).
Use the reviewed exact delivery commit after its CI passes. Functional files are
pinned to `b4772dfcbb1456ed65b74c511412790988711aba`, with ten individual file
hashes in `tools/mojt-system-fast-test.py`. These are reviewed maintenance inputs,
not signed releases. Keep previous scripts and evidence.

Start as root on the installed Mojt SSD, normally in accepted
`system-activation-D`, with running and next boot equal. Existing accepted
Ports-fix and activation A/B/C baselines are also supported. This is a tooling
update using the same Base, Kernel, firmware policy and runtime provider; it does
not build a Kernel, use MBT to bootstrap a disk or exercise a new firmware matrix.
There are two deliberate boots. No command reboots automatically.

## Delivery and entry

On the computer displaying the chat, download `tools/mojt-system-fast-test.py`
from the exact reviewed delivery link, save it as **payload.py**, and transfer it
by USB to **/root/payload.py**. Do not overwrite the previous `msft.py`. No long
URL, artifact ID, compiler or Git checkout is needed on Mojt.

```sh
python3 /root/payload.py prepare
```

This downloads pinned files and packages **E** (`system-payload-E`) and **F**
(`system-payload-F`) without installing or selecting them. Package preparation
may take time and is outside measured MPM operations. It reuses owned component
content and provider references, without copying or rebuilding the Nix closure.

```sh
python3 /root/payload.py enter
```

Confirm. Old installed MPM visibly installs E, prepares it and selects its exact
deployment. This bootstrap can still be slow; its timings do not measure the new
constructor. F remains packaged but uninstalled. At `READY: E selected`, reboot
deliberately, then check `mpm system status`: running and next boot must both be E.

## Cold construction, then reuse

```sh
python3 /root/payload.py install
python3 /root/payload.py prime
```

Confirm each operation. `install` uses new installed `mpm system install` for F,
without `--verify`, keeping E running/selected. `prime` invokes new installed
`mpm system stage` for the original System (normally D), again without selecting
it. Its old prepared deployment used the old constructor; this creates a fresh
deployment and the first reusable payload with the new manager. Expect
`Early-boot runtime/drivers: built`, `changed: true`, and
`initramfs_payload.reused: false`. The helper refuses an existing cache/no-op as
a cold performance sample. This first construction can still take minutes.

```sh
python3 /root/payload.py stage
```

This prepares F through public installed MPM and keeps E selected. Expect
`Early-boot runtime/drivers: reused`, `changed: true`, and
`initramfs_payload.reused: true` with the same payload inputs ID as `prime`.
The helper checks those exact results. F must have a newly bound deployment;
a no-op cannot pass as warm reuse. Runtime copying, early-module decoding and
large-payload compression are skipped. Existing preflight, integrity and
admission work remains, so no fixed total speedup is promised.

Report the printed `prime: ... s wall, ... s CPU` and `stage: ... s wall,
... s CPU` lines. They measure complete MPM preparation, not isolated payload
construction or activation. Helper status/pin checks and confirmation input are
outside the timer. Every changing operation prints the real `+ mpm ...` command.

## Select F and boot the combined archive

```sh
python3 /root/payload.py activate
```

Confirm. This selects the exact prepared F using the existing metadata-only
activation path and an expected-current guard. Expect E running, F next boot,
with the original Base/Kernel/boot policy. This test does not change the accepted
activation performance contract. The previously accepted interactive cancellation
test need not be repeated; the optional `cancel` command remains available before
activation.

After successful selection, reboot deliberately. Then:

```sh
mpm system status
python3 /root/payload.py after
```

Expect F running/selected, the exact measured deployment, original Base/Kernel,
and working Ports/Neovim. This boot is the physical acceptance gate for the new
combined initramfs. It has not been performed by automated packaging tests.

## Evidence, errors and optional return

Evidence is separate from C/D under `/var/lib/mojt/initramfs-payload-55`.
`prime.json`, `stage.json`, their `.log` files and `*-result.json` record actual
argv, process wall/CPU time, exit codes and payload reuse. `after.json` records
boot acceptance. No logs are uploaded automatically.

On any error, stop and keep the evidence. Inspect:

```sh
python3 /root/payload.py status
```

Existing evidence names are never overwritten. Do not remove cache entries or
test state to force a sample; an interrupted operation needs inspection. A
post-publication failure can mean content or next boot was already committed.
No installation, selection or reboot is inferred from the error code alone.

After successful F acceptance, optional `python3 /root/payload.py back` selects
the original exact E deployment for next boot. It does not reboot or roll back
persistent state. D and previous accepted generations remain retained.

## Recorded owner acceptance — 2026-11-14–15

The owner used the delivery from
`d1984592b2a95eb534b7224bc6846fe8c4dd8fd3` as `/root/payload.py`, with
functional files pinned to `b4772dfc`. E was entered using the old manager;
after reboot, the owner confirmed E running and selected. The first photograph
records bootstrap installation at 11.420 s wall / 5.029 s CPU, preparation at
271.555 s wall / 267.609 s CPU (35.61 s candidate checks included), and selection
at 2.124 s wall / 2.108 s CPU. Those are old-manager bootstrap measurements,
not new-constructor samples.

| New-manager operation | Observed result | Evidence |
| --- | --- | --- |
| F installation without `--verify` | PASS; 11.483 s wall / 4.996 s CPU; original Base/Kernel/boot policy retained | Second owner console photograph; supersedes the earlier rounded 11.4 s report |
| Cold preparation of retained D (`prime`) | PASS; payload built; 286.737 s wall / 276.351 s CPU | Same photograph; 45.04 s candidate checks are included in the preparation total |
| Warm preparation of F (`stage`) | PASS; approximately 229 s wall / 219 s CPU; approximately 45 s candidate checks included | Owner report, rounded to seconds; helper PASS requires a new deployment reusing the exact cold payload inputs ID |
| F activation | Approximately 4.2 s elapsed | Owner report; no activation CPU time supplied |
| Deliberate F reboot and `after` | Worked; PASS | Owner confirmation after the requested reboot/after sequence; helper checks exact F running/selected, retained Base/Kernel/boot policy, Ports and Neovim |

In this one SSD run, warm preparation took about 58 s less wall time (about 20%)
than cold preparation. These are complete preparation measurements for different
System generations, not isolated compression timings or a general benchmark.
The result confirms reuse and physical boot of the combined archive. It does
not attribute every remaining second to verification, prove a new Kernel/Base
combination, or make the remaining roughly four-minute preparation acceptable.
Separating repeated content audits from required preparation remains open.

Evidence remains under `/var/lib/mojt/initramfs-payload-55` on the owner's SSD.
This record uses the shared photographs and reports; no evidence bundle was
imported and no host test was run by the collaborator. Optional return to E was
not reported. Previous C/D acceptance remains a separate historical result.
