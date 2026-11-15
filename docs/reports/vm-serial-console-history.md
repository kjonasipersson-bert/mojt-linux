<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Serial-console and interrupted-image-build acceptance

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

## Owner acceptance

On 2026-10-26, the owner logged in as root with the existing VM password
through the adapted copy's serial console on the Debian host. The real Mojt
systemd guest reported `/dev/ttyS0`, System `system-A`, Base `0.1.3` and
kernel `6.12.107+deb13-amd64`. Both `/etc/generation-marker` and
`/var/generation-marker` still contained `generation-test-9eMyMQ`.

This verifies authenticated console login and guest shell commands with the
full System payload.

The owner pressed Ctrl-C at the new build's password prompt and observed
`mojt-vm-build: password entry aborted`. The completed serial VM restarted
successfully with Base `0.1.3`, System `system-A`, `/dev/ttyS0` and both
existing state markers.

The owner then repeated the interruption with the corrected probe above
while the completed VM was stopped. It reported:

```text
PASS: interrupted build published no image; completed VM disk unchanged.
```

This confirms the builder's abort diagnostic and nonzero exit status, absence
of a published `interrupted-image` path (including a symlink), and an unchanged
SHA256 checksum for the completed serial VM disk. Together with the observed
post-abort restart, the controlled manual interruption acceptance is complete.

