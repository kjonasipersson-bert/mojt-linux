<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Diagnostics and USB database acceptance

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

## Validation status

Synthetic regressions cover cumulative roles, unchanged earlier exports,
preserved Base/account data, exact command links, missing DNS command rejection,
and executed local-check success/failure cleanup. They do not establish real
Nix evaluation, signed binary availability or guest behavior of these tools.
The corrected owner-side export and full-Mojt boot acceptance are recorded below.

## Initial owner run and USB correction

The owner exported 191 objects and booted a fresh two-pair serial VM at
`/home/jonasp/mojt-diagnostics.BELV3c`. On the initial tools-A run the network
and admin probes passed. Local ping/tracepath, module metadata and strace also
ran successfully, and hello was imported and activated. However, lsusb emitted
`unable to initialize usb spec` while returning zero, causing the initial local
probe to report a false overall PASS for USB. That initial PASS did not establish USB acceptance; the corrected run below supersedes it.

The owner's strace showed missing compiled hwdb files at all searched paths,
including `/etc/systemd/hwdb/hwdb.bin` and `/etc/udev/hwdb.bin`. The corrected
exporter supplies the database, and the checker treats lsusb stderr as failure
as well as checking its exit status. An empty USB tree is permitted when the
VM has no USB controller; it is not evidence of physical USB device operation.
Re-export to a fresh payload directory, for example `system-step7-hwdb`, and
build toward a new VM output. Retain the initial disk and its test markers.

Synthetic tests cover private compilation, missing compiler output, digest
changes, unsafe persistent configuration, the generation-specific link and
zero-exit USB warnings. Corrected owner acceptance is recorded below.

## Corrected owner VM acceptance (2026-10-26)

The owner exported `system-step7-hwdb` successfully (191 store objects), then
built a new two-pair image and authenticated serial copy at
`/home/jonasp/mojt-diagnostics-hwdb.mIVQjJ/serial-image`. The VM assembly
timestamp was `2026-10-26T14:49:05Z`. Base remained 0.1.3 and both pairs
used the same corrected step 7 userspace and firmware input.

| Boot | Kernel/module release | Result |
| --- | --- | --- |
| system-tools-A | 6.12.107+deb13-amd64 | Supplied full output confirms System identity, database link/presence and successful diagnostics, network and admin checks |
| system-tools-B | 7.2.9+deb13-amd64 | Supplied full output confirms System/kernel/module identity, diagnostics, network/admin, persistent markers and the same hello executable |
| Return to system-tools-A | 6.12.107+deb13-amd64 expected | Owner confirmed the requested return/check sequence succeeded; supplied final excerpt confirms admin, persistence, hello and same-artifact PASS |

The A log shows `/etc/udev/hwdb.bin -> /run/mojt-system/hwdb.bin` and a
nonempty selected System database. The corrected lsusb check passed on A
and B without the earlier initialization warning. USB tree output was empty;
this verifies tool/database startup, not actual USB device enumeration or
physical USB hardware compatibility.

Local checks exercised loopback ping/tracepath, arping version, DNS-tool
startup, ethtool version, PCI listing, socket inspection, running-kernel ext4
module metadata and syscall tracing. Network checks showed DHCP/default route,
DNS/HTTPS, dig/nslookup and e1000e driver inspection with the matching release.
The admin check covered process/memory/disk/mount tools, journal, pager and
temporary vi editing. No new ordinary-user or privileged ping policy was tested.

The owner created the persistent markers and installed hello under A before
switching to B. B and the return to A both reported retained /etc and /var
markers, `Hello, world!` and `PASS: same Ports artifact`, comparing the
resolved executable with the path saved under A. The return excerpt does not
repeat identity or diagnostic output; those checks are owner-confirmed.

This completes manual full-Mojt A → B → A acceptance for the corrected
diagnostic toolset on both kernel/module sets. It is owner-host evidence,
not an agent-run VM test. In-place boot-disk updates, automatic fallback,
physical-device coverage and state rollback remain outside this experiment.
