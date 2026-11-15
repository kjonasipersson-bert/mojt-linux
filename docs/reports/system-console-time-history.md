<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Console, clock and persistent journal acceptance

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

## Initial owner run and D-Bus correction

The owner exported 191 objects and built the serial VM at
`/home/jonasp/mojt-console-time.oyCH7A`. On system-console-A with kernel
6.12.107+deb13-amd64, mojt-console-size changed the tty from 0x0 to 72x138,
and stty confirmed it. Journal flush completed successfully and journalctl
reported 8 MiB; cross-boot persistence has not yet been tested.

The bus failed to start, so timesyncd was not started due to a failed dependency.
The generator had put an allow-user connection rule inside a per-user policy.
A real private dbus-daemon reproduced the parser rejection: that rule has
bus-global semantics. The corrected generator places connection permission in
the default policy while keeping service name ownership and messaging rules
scoped to the service account. A new regression starts a real isolated daemon
with the generated policy, changing only host-test identity/transport.

This is a builder-only correction; the exported step 8 payload can be reused
with the updated checkout to build a fresh image. No corrected real bus or NTP
acceptance is claimed until the owner boots the corrected image.

## Owner tools-B findings and follow-up

The corrected image at `/home/jonasp/mojt-console-time-fixed.qeCpek` booted
with functioning D-Bus. The owner observed initial NTP synchronization under A
at 2026-10-26 15:32:06 UTC, then created the journal/state markers and installed
hello. On B, the supplied output confirms kernel/modules 7.2.9+deb13-amd64,
terminal geometry 72x138 and confirmed timesyncd synchronization to
194.58.204.148, with two received packets. These are actual owner VM results.

The initial journal-check rejected the saved hyphenated /proc boot UUID before
querying journal contents. The checker now validates and normalizes it to the
32-character form accepted by journalctl. The remainder of the owner's chained
checks did not execute after that failure; persistence/Ports checks for B and
return acceptance remain pending. This was not evidence of journal data loss.

Informational kernel driver messages could still arrive after the serial login
prompt because the serial getty was ordered after setup, not after hardware
loading. A new oneshot now sets the console printk threshold before both local
and adapted serial gettys. Messages remain in the kernel ring buffer/journal;
errors may still appear on the console. It intentionally does not silence all
boot diagnostics. This correction requires a new image to verify its boot order.

The image has no logind yet. The ordinary systemctl poweroff command reports
missing org.freedesktop.login1 before its successful fallback. For the current
root-operated VM, use the equivalent direct PID 1 target request:

```sh
systemctl start poweroff.target --job-mode=replace-irreversibly --no-block
```

This uses normal systemd shutdown ordering, without --force. It is a temporary
root administration recipe, not an ordinary-user authorization/inhibitor policy.
Full logind/session integration belongs to the account stage. Do not treat the
absence of logind as a reason to bypass filesystem shutdown.

## Persistent files found under changing machine identities

On a subsequent B boot the owner supplied evidence that /etc/machine-id was
mounted from tmpfs and /var/log/journal contained three different machine-ID
directories, each with an 8 MiB system.journal. Journal logs confirmed a
successful runtime-to-disk flush. Thus journal files survived, but normal
journalctl selection did not show the previous identity's boots. The proposed
--merge/--list-boots combination is unsupported; inspect each directory with
journalctl --directory instead.

Step 8 now explicitly runs the selected systemd-machine-id-setup --commit
after Mojt setup and before journald/D-Bus/login. The unit has no default
dependencies (to avoid a sysinit/journald ordering cycle) and is pulled into
sysinit.target. It commits an existing transient ID rather than generating
a replacement or overwriting a valid persistent identity. /etc is already
mounted from writable persistent state before PID 1 starts. The commit helper
is verified as part of the payload's System output. A stable identity across subsequent boots and cross-generation journal
visibility were subsequently verified in the clean owner run below. No historical journal directories are removed or merged by this fix.

## Clean owner acceptance: A → B → A (2026-10-26)

The owner exported step 8 with 191 store objects, updated the builder through
commit `26750e1bf6c97754a79b237b8ad7b7f5bc3e589c`, and built a fresh serial VM:
`/home/jonasp/mojt-console-time-clean.ThiOJC/serial-image`.
No manual machine-ID repair was applied to this clean image. Base remained 0.1.3.

| Boot | Kernel | Observed acceptance |
| --- | --- | --- |
| system-console-A | 6.12.107+deb13-amd64 | Automatic machine-ID commit to ext4, no failed units, successful quiet/flush units, 72x138 tty geometry and confirmed NTP |
| system-console-B | 7.2.9+deb13-amd64 | Same persistent machine ID, previous-boot journal, /etc and /var markers, diagnostics, network/DNS/HTTPS, same hello artifact and confirmed NTP |
| Return to system-console-A | 6.12.107+deb13-amd64 | Same machine ID, three visible boots, retained journal marker/state/hello artifact, diagnostics/network and confirmed NTP |

The persistent machine ID was `d84c7a3cf90446b7ad6e8748d363e224`.
On initial A the owner left the login prompt idle for about two minutes and
reported no unsolicited log interference; they explicitly confirmed a quiet
B console too. Terminal measurement returned 72x138; the owner had also
confirmed full-size top after measuring and unsetting stale LINES/COLUMNS.
Terminal queries remain manual after login or window changes.

The clean B journal check found the marker from initial A without directory
overrides. The final A output listed all three boot IDs:
`72f6459c31c7422680cfe86901ced052`,
`6c0a2ff6df334b2fb2f5663a30c69580`,
`6d5756a3c2854341bbf31f0b9608b48f`.
Journal disk usage was 8 MiB. This demonstrates cross-boot visibility with a
stable identity; it is not a stress test of rotation or retention limits.

Timesyncd confirmed initial synchronization at 16:19:19 UTC on initial A,
16:23:23 UTC on B and 16:25:43 UTC on return A. The immediate clock check
correctly reported not-yet-synchronized before replies arrived; subsequent
checks passed. Offline operation and boot do not wait for successful NTP.

The owner installed hello under initial A and saved its resolved executable
path. B and final A printed Hello, world! and same-artifact PASS without a
reinstallation request. Local diagnostics and existing network tests passed
with each selected kernel's modules. Earlier admin-tool acceptance remains
documented in the step 7 run; no new ordinary-user or logind acceptance is
claimed here.

This completes the clean VM acceptance for this step. It is owner Debian-host
evidence, not an agent-run VM test. Automatic terminal resizing, geographic
timezone configuration, timedated/logind, account management, physical hardware
coverage and in-place boot-disk updates remain separate work. A timezone such
as Europe/Stockholm is persistent machine configuration; NTP synchronization
alone does not select it.

