<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Timezone, manual pages and console-signal acceptance

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

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
[System proposal](../system-completeness-proposal.md), beginning with an inventory
of existing homes, shell paths and local account/session configuration before
changing authentication. Root recovery remains enabled during acceptance.
