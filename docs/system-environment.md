<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# System step 9: timezone data, manuals and environment

The owner inspected step 8 on 2026-10-26: `/etc/localtime` and `/etc/timezone`
were absent and date displayed UTC. Base locale reported C, C.utf8 and POSIX.
System Python accepted C.UTF-8 with UTF-8 encoding, but neither en_US.UTF-8
nor sv_SE.UTF-8. This establishes a working UTF-8 baseline, not Swedish
formatting support. Keep LANG=C.UTF-8 and leave LC_ALL unset by default.

Step 9 adds tzdata and man-db. It explicitly imports the man outputs of the
same pinned systemd, curl, iputils and tzdata derivations. man-db includes
its own manuals. Other packages' manuals and translated manuals remain
future work. The runtime closure includes the renderer and compression tools;
the VM does not build documentation or run mandb against the immutable store.

System exposes man/manpath, an explicit MANPATH and TZDIR. Existing nonempty
MANPATH/TZDIR values are respected. No global TZ or LOCALE_ARCHIVE is set.
In particular, do not share one locale archive blindly between the different
Base and System glibc versions. Additional locales need separate integration.

Timezone selection is machine policy in persistent `/etc`. A regular copy of
the selected TZif file avoids a link into an obsolete store closure when a
generation is removed. This deliberately retains the selected rule snapshot:
a later tzdata update must explicitly refresh `/etc/localtime`. Existing
localtime/timezone settings are never replaced by the builder. No timedated
service is introduced; use the explicit configuration below. NTP continues
to synchronize the clock independently of its local display timezone.

## Prepare in the existing Nix Distrobox

From Debian, enter the existing ordinary-user container:

```sh
distrobox enter mojt-mpm-nix
```

Inside that container, use a fresh checkout and payload:

```sh
bash <<'MOJT_ENVIRONMENT'
set -euo pipefail
SOURCE="$HOME/mpm-system-test/mojt-system-environment"
PAYLOAD="$HOME/mpm-system-test/system-step9"
git clone --single-branch --branch feature/system-environment \
  https://github.com/kjonasipersson-bert/mojt-linux.git "$SOURCE"
python3 "$SOURCE/tools/mojt-system-prepare.py" \
  --step 9 --output "$PAYLOAD" --dry-run
MOJT_ENVIRONMENT
```

After reviewing the preview, export in the same container:

```sh
python3 "$HOME/mpm-system-test/mojt-system-environment/tools/mojt-system-prepare.py" \
  --step 9 --output "$HOME/mpm-system-test/system-step9" -y
```

Missing signed binary substitutes or missing manual hierarchies must stop
preparation. Actual cache availability and guest operation are not established
by synthetic tests. Exit the container after export.

## New two-kernel VM

Use the [retained two-kernel build recipe](system-diagnostics.md#build-with-the-retained-two-kernel-sets)
on Debian, with these substitutions:

```sh
SOURCE="$HOME/mojt-lab/mpm-nix-home/mpm-system-test/mojt-system-environment"
PAYLOAD="$HOME/mojt-lab/mpm-nix-home/mpm-system-test/system-step9"
```

Use a fresh `mojt-environment.XXXXXX` output directory and label its pairs
system-environment-A/B. Keep the accepted step 8 VM. This is a new-image
experiment; it does not transfer state from earlier VM disks.

## Guest acceptance

Run mojt-console-size by itself at an idle prompt, then:

```sh
unset LINES COLUMNS
mojt-system-check environment
man man
man ping
man systemctl
```

Check interactive paging and quit each manual with q. The environment probe
also locates manuals and renders ping to text, checks System C.UTF-8 and
checks Stockholm winter/summer offsets directly from the selected TZif file.

For an explicit Europe/Stockholm selection, run inside the new Mojt VM:

```sh
zones="$(cat /run/mojt-system/zoneinfo-path)"
test -f "$zones/Europe/Stockholm" &&
cp --remove-destination -- "$zones/Europe/Stockholm" /etc/localtime &&
chmod 0644 /etc/localtime &&
printf 'Europe/Stockholm\n' >/etc/timezone &&
sync
unset TZ
date '+%Y-%m-%d %H:%M:%S %Z %z'
/run/mojt-system/bin/python3 -c 'import time; print(time.strftime("%Y-%m-%d %H:%M:%S %Z %z"))'
```

On 2026-10-26 Stockholm should display CET +0100 in both programs. This
selection does not require a Swedish locale. Confirm the configuration is a
regular persistent file, and create the usual journal/persistence markers:

```sh
test ! -L /etc/localtime
findmnt -T /etc/localtime -o TARGET,SOURCE,FSTYPE
mojt-system-check journal-write
mojt-system-check persistence-write
```

Install hello and record its resolved path as in the step 8 acceptance. Shut
down orderly with the existing direct-target workaround while logind is absent:

```sh
systemctl start poweroff.target --job-mode=replace-irreversibly --no-block
```

Boot the same disk into B, then return to A. On each, confirm matching
kernel/modules, the same machine ID, local date/time in both Base date and
System Python, retained `/etc/timezone`, environment, journal-check,
persistence-check, diagnostics, diagnostics-network, the same Ports artifact
and clock after NTP replies arrive. Do not treat an initially unsynchronized
clock as a confirmed NTP failure.

## Validation status

Synthetic tests cover payload completeness, environment defaults and retained
machine timezone settings. Real Nix export and step 9 VM acceptance are pending.
The owner already verified the preceding step 8 A/B/A run, including persistent
identity/journal, NTP, quiet consoles, diagnostics, networking and Ports.

## Initial owner acceptance and console signal correction

The owner exported 202 store objects and booted the new VM at
`/home/jonasp/mojt-environment.ZEB2eX/serial-image`. Base date and System Python
both reported CET +0100 after selecting Europe/Stockholm. The timezone file
resided in persistent ext4 `/etc`, and the clock probe confirmed NTP replies.
Cross-generation timezone persistence and interactive manual acceptance remain
pending.

The environment probe located all four manuals and rendered ping successfully,
but lookup printed gzip Broken pipe warnings. The serial console service
reported IgnoreSIGPIPE=yes. Running the same four lookups through Python
subprocess with restore_signals=True removed the warnings, with all exit
statuses zero. This supports inherited SIGPIPE handling as the cause rather
than missing manual data. Both Mojt console unit generators now explicitly
set IgnoreSIGPIPE=no, matching the signal semantics needed by shell pipelines.
This is a builder/unit correction; the exported payload can be reused.

For the existing VM, create a persistent drop-in for both console units:

```sh
for service in mojt-console mojt-serial-console; do
    mkdir -p "/etc/systemd/system/$service.service.d"
    printf '[Service]\nIgnoreSIGPIPE=no\n' >"/etc/systemd/system/$service.service.d/20-sigpipe.conf"
done
systemctl daemon-reload
```

This does not change signals in the current shell. Log out and authenticate
again, then rerun `mojt-system-check environment` and interactive manuals.
The drop-ins survive generation changes because they reside in `/etc`.

## Accepted scope after the signal correction

The owner applied the persistent console drop-ins, logged in again and
confirmed IgnoreSIGPIPE=no. All four manual lookups completed without gzip
warnings, and `mojt-system-check environment` passed. The owner confirmed the
fix works and explicitly chose to omit a separate step 9 A/B run, carrying
these checks into the next System stage instead. Do not report step 9 timezone
or manual persistence across generations as tested. The earlier step 8 A/B/A
acceptance remains the kernel/identity/journal reference.

Next work is preparation of the coherent local-account stage described in the
[System proposal](system-completeness-proposal.md), beginning with an inventory
of existing homes, shell paths and local account/session configuration before
changing authentication. Root recovery remains enabled during acceptance.
