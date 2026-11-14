<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# First installed Ports repair

The fresh Ports frontend initially required an explicit finite catalog even
though System delivered a pinned Nixpkgs manifest. PR #53 restores ordinary
installed `mpm ports install NAME` discovery. `mojt-system-ports-repair.py` is a
fixed maintenance bridge for delivering that repair to a booted native-v2 Mojt
installation which cannot yet acquire a published successor System release.

Transfer the script through an explicitly trusted USB stick, then copy it to
`/root/ports-update.py` on the installed SSD. Run it with the installed Python as
root, booted into the installed `system-ssd-A` (the USB installer is refused).
It needs working HTTPS and the existing native System registry, curl,
packaging codec and MPM. It does not require Git, a compiler, a Nix update or
another USB image. The workspace is `/var/lib/mojt/ports-repair`, on the SSD.

```sh
python3 /root/ports-update.py prepare
python3 /root/ports-update.py install
python3 /root/ports-update.py activate
```

`prepare` downloads five bounded source/manual files from one fixed Git commit
and checks hashes embedded in the USB-delivered script. Python is the delivered
program format here: no downloaded code is imported or executed during package
construction. The hashes bind the data to the operator's chosen script, not to
a release signature. This is not a signed remote package catalog.

The bridge copies the retained runtime component into a private SSD workspace,
checks its owned-file inventory, replaces the fixed tooling/manual files and
version marker, and creates ordinary native component/generation archives. It
retains original build provenance, exact parent artifact IDs, source revision,
file checksums and the bridge checksum. The System package revision advances by
one; its label is `system-ports-fix-1`. Provider dependencies, lifecycle actions,
service declarations and state schemas are preserved. Only the existing
single-runtime, whole-directory profile composition is supported. An unfamiliar
composition fails rather than attempting a migration.

`install` asks for confirmation and calls the **running installed MPM** with the
generation and component archive. It does not alter next boot. `activate` asks
separately and uses the existing exact `mpm system upgrade --artifact` path.
That path performs compatibility checks and boot preparation; it retains the
previous deployment and never reboots automatically. Another already selected
deployment blocks the bridge. Failed preparations keep their workspace for
inspection rather than overwriting an old generation or the running profile.

After activation, reboot deliberately, then inspect:

```sh
cat /run/mojt-system/version
mpm system status
mpm ports install hello --dry-run
mpm ports install hello -y
hello
```

The current source pin offers its own available releases. This bridge does not
implement channel refresh, arbitrary remote native artifacts or a general System
release builder. The ordinary native package format and installation/selection
contracts are unchanged. Future published System bundles can be downloaded and
installed directly without this local repackaging step.

Validation uses actual native archives and a temporary root-mapped installation:
bad network bytes are rejected, the previous component/profile stays unchanged,
the candidate installs with the existing manager and passes the tooling-only
startup review. External provider I/O and physical boot are not exercised by
those tests; physical acceptance is still required for this delivery.
