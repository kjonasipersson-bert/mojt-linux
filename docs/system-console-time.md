<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# System step 8: console geometry, persistent journal and time

The owner's corrected step 7 VM reported `stty size` as `0 0`, TERM vt100 and
only the current boot in `journalctl --list-boots`. The selected systemd 262
already contains systemd-timesyncd and timedatectl. Step 8 keeps the package
roles of step 7 and adds Mojt integration, not another NTP package.

## Console size

`mojt-console-size` queries the actual terminal with CSI 18 t and registers
its reported rows/columns on the controlling tty. It uses System's existing
Python runtime and standard library. It is explicit, not a login/prompt hook:
unsupported terminals time out after two seconds without blocking login.
TTY flags are restored on completion or failure. Run it at an idle prompt;
typing during the query can interfere with the reply. After resizing the
outer terminal, run it again; QEMU does not propagate SSH SIGWINCH geometry.

```sh
mojt-console-size
stty size
```

If unsupported, use `mojt-console-size ROWS COLS` with the real dimensions,
for example `mojt-console-size 40 140` for an actual 40-by-140 terminal.
No shell output is evaluated and TERM is not automatically changed. Existing
Bash checkwinsize observes the tty's geometry on subsequent prompts. Verify
top/less interactively. Automatic resize propagation is not implemented.

## Logging defaults

System owns default journald configuration: persistent storage, 64 MiB disk
budget, 16 MiB runtime budget and 14-day retention. Those are journal policy
limits, not a strict filesystem quota. Console/kmsg forwarding is disabled by
default; logs remain available through journalctl. Deliberately running a
checker still prints its requested journal excerpts. Kernel console filtering
continues to use the hardware profile's existing setting.

The profile holds defaults under `defaults/`. Only a missing
`/etc/systemd/journald.conf` gets a link to the running profile's default;
an existing administrator file or link is retained. Explicit administrator
drop-ins still apply. Setup creates the persistent journal directory/group
permissions before journald starts. A dedicated oneshot flushes early runtime
entries to persistent storage. Existing administrator settings can intentionally
keep logging volatile; acceptance must then explain that policy difference.

## Time service

The selected System timesyncd runs as a dedicated service identity with
CAP_SYS_TIME, persistent `/var/lib/systemd/timesync` and volatile runtime state.
Mojt explicitly enables its unit and system-bus policy. The existing package
supplies the daemon, timedatectl and systemd-cat. No timedated service or NTP
server is enabled in this step. Use `timedatectl timesync-status`, rather than
assuming every timedatectl operation has been integrated.

A missing `/etc/systemd/timesyncd.conf` links to System's default with
`0.pool.ntp.org` and `1.pool.ntp.org`. Existing local configuration and drop-ins
take precedence as configured by systemd. These are development-image defaults;
a production distribution should review NTP pool use and deployment-specific
servers. NetworkManager DHCP NTP information is not automatically imported
through systemd-networkd (which is not enabled). Offline boot remains usable;
the daemon retries without making successful NTP synchronization a boot gate.
Do not enable a second time daemon alongside this one.

## Preparation

Inside the existing mojt-mpm-nix Distrobox, as the ordinary user:

```bash
bash <<'MOJT_CONSOLE_TIME' || printf '%s\n' 'Console/time preparation stopped; see the error above.' >&2
set -euo pipefail
SOURCE="$HOME/mpm-system-test/mojt-console-time"
git clone --single-branch --branch feature/system-console-time \
  https://github.com/kjonasipersson-bert/mojt-linux.git "$SOURCE"
python3 "$SOURCE/tools/mojt-system-prepare.py" \
  --step 8 --output "$HOME/mpm-system-test/system-step8" --dry-run
python3 "$SOURCE/tools/mojt-system-prepare.py" \
  --step 8 --output "$HOME/mpm-system-test/system-step8" -y
MOJT_CONSOLE_TIME
```

Use a fresh output and preserve the working step 7 VM. On the Debian host,
follow the [two-kernel build recipe](system-diagnostics.md#build-with-the-retained-two-kernel-sets)
with SOURCE set to the host-visible mojt-console-time checkout and PAYLOAD
set to its exported system-step8. This preserves the earlier images and uses
the same Base and kernel/module inputs. Current step 8 is a new-image
experiment, not an update to an existing installation.

## Manual guest acceptance

After ordinary authenticated login on tools-A:

```sh
mojt-console-size
stty size
systemctl status systemd-timesyncd.service --no-pager
timedatectl timesync-status --no-pager
mojt-system-check clock
mojt-system-check diagnostics-network
mojt-system-check journal-write
```

An active time daemon is not proof of synchronization. The clock checker
also requires the daemon's synchronized marker; if still waiting, inspect
`journalctl -u systemd-timesyncd.service -b --no-pager` and rerun once NTP
replies arrive. Do not force an incorrect system time to test this service.
Check that no journal messages spontaneously overwrite the idle login prompt.

Power off in Mojt, start the same disk and choose tools-B. Then run:

```sh
mojt-console-size
mojt-system-check clock
mojt-system-check journal-check
mojt-system-check diagnostics
mojt-system-check diagnostics-network
```

Return to tools-A and repeat. Record the selected identities, matching modules,
clock server/synchronization, tty geometry and previous-boot log visibility.
Retain the ordinary persistence/Ports checks from step 7 as regression checks.
Old step 7 images are a separate recovery reference; account/configuration
compatibility with arbitrary old profiles is not established by this recipe.

## Validation boundaries

Real PTY tests cover explicit geometry, query/reply handling, timeout and tty
restoration. Synthetic assembly tests cover service/default integration and
preserving administrator logging configuration. They do not prove actual NTP
exchange, system-bus integration, persistent journald operation or Windows
terminal reply support; those require the owner VM run above.

Upstream references:
[timesyncd](https://www.freedesktop.org/software/systemd/man/latest/systemd-timesyncd.service.html),
[journald configuration](https://www.freedesktop.org/software/systemd/man/latest/journald.conf.html).

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
is verified as part of the payload's System output. A stable identity across
subsequent boots and cross-generation journal visibility still need owner
acceptance. No historical journal directories are removed or merged by this fix.
