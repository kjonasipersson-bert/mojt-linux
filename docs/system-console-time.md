<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# System step 8: console geometry, persistent journal and time

System integrates terminal geometry, persistent journald storage and the
selected systemd output's timesyncd/timedatectl tools. NTP synchronization does
not select a geographic timezone, and boot does not wait for a successful NTP
exchange. Machine timezone is persistent `/etc` configuration.

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
terminal reply support; those require a real guest environment.

Upstream references:
[timesyncd](https://www.freedesktop.org/software/systemd/man/latest/systemd-timesyncd.service.html),
[journald configuration](https://www.freedesktop.org/software/systemd/man/latest/journald.conf.html).

## Local consoles and later account-stage update

The step 10 console tool recognizes Linux virtual consoles through KDGETMODE
and reads their kernel-provided TIOCGWINSZ geometry instead of sending CSI 18 t.
This avoids a serial-terminal query on tty1. It does not propagate QEMU window
resizing: a local console's grid follows the guest display mode, while a serial
console still needs an explicit query or known rows/columns. See the
[account-stage console notes](system-accounts.md#console-size-local-versus-serial).
