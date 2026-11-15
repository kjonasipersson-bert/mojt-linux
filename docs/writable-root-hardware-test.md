<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Writable-root G/H/G hardware acceptance

Start as root on the accepted SSD with **F running and selected** and the existing
`/var/lib/mojt/initramfs-payload-55/state.json` checkpoint. Keep the earlier
performance evidence. This test installs two new System generations, preserving
Base, Kernel, firmware, provider identities and original F recovery entry. It
never formats a disk, replaces installed F files or reboots automatically.

Functional code is pinned at `0976c58d2202609ba1545739e5abd2c98b8794b1`.
The one-file helper pins 17 changed tool/manual files and the previously tested
native package/evidence driver by digest. It copies the accepted F runtime into
new packages, checks unchanged startup/provider policy, and records all evidence
under `/var/lib/mojt/writable-root-60`. This is reviewed maintenance delivery,
not a signed native release.

## Prepare and boot G

Download the reviewed delivery's **`tools/mojt-writable-root-test.py`**, retain
that filename, and copy it by USB to **`/root/mojt-writable-root-test.py`**.
Use the exact delivery revision supplied with the review, after CI passes.

```sh
python3 /root/mojt-writable-root-test.py prepare
python3 /root/mojt-writable-root-test.py enter
```

Confirm each requested operation with `y`. `prepare` only packages G and H.
`enter` installs G using F's public MPM, then runs the installed G launcher in a
fresh isolated process using F's interpreter/runtime defaults to prepare G.
The complete G code cohort is checked against the prepared hash map before
execution. This explicit private-code maintenance step avoids first booting G
with F's old embedded read-only-root builder. It does not patch F or run a mixed
old/new imported manager. The public F selector chooses the exact admitted G
entry. Its command/result and combined stage output are retained.

The first preparation can construct a new boot payload; it is not another
performance benchmark. Preparation must leave `state/rootfs` absent. On `READY`,
reboot deliberately into G, then run:

```sh
python3 /root/mojt-writable-root-test.py check
```

This checks the exact deployment, original Base/Kernel/boot policy, reviewed
installed tools, installation marker, writable-root/local backing mounts and
read-only Base/System files. It attempts only a non-truncating writable open of
the release files; it writes no bytes to them. It also runs Ports listing and
Neovim's version check.

On this first G check, it creates uniquely named small marker directories under
`/`, `/opt`, `/srv`, `/usr/local`, `/etc`, `/var/lib`, `/home` and `/root`, plus a
`/tmp` marker. Existing files are never overwritten. Their token and boot ID are
saved with the test evidence. Root scaffolding itself was initialized by G boot,
not by `stage` or this marker check.

## Change to H and verify persistence

```sh
python3 /root/mojt-writable-root-test.py next
```

Confirm with `y`. G's installed public MPM installs and prepares H, retaining
G's running state and next-boot choice during preparation; it then selects the
exact H deployment. On `READY`, reboot deliberately, then run:

```sh
python3 /root/mojt-writable-root-test.py check
```

Expect `PASS` for H: all eight persistent markers match, the temporary marker is
gone, release mounts remain read-only, and Ports/Neovim work. Record whether
shutdown completed without failed unmount/read-only fallback messages.

## Return to writable-root G

```sh
python3 /root/mojt-writable-root-test.py back
```

Confirm, reboot deliberately into the exact retained G entry, then run:

```sh
python3 /root/mojt-writable-root-test.py check
```

Expect `PASS` for G return with the same persistent markers and clean shutdown.
This establishes generation-change and return persistence for the new layout;
no different-Base/Kernel or state/schema migration matrix is claimed. Older F
still has its embedded read-only root. It remains a recovery entry and can see
the established `/etc`, `/var`, `/home` and `/root`, while new root/local data
stays retained without being exposed by its older layout.

## Evidence and failure handling

Report the three `check` results (G, H and G return), Ports behavior and shutdown
observations. Evidence includes `state.json`, stage/install/select logs and
results, `checked-G-first.json`, `checked-H.json`, and
`checked-G-return.json`. Nothing is uploaded automatically.

If an action fails, keep the work directory and inspect:

```sh
python3 /root/mojt-writable-root-test.py status
mpm system status
```

For boot failure, choose the original F entry from the retained boot menu.
Do not clear caches or remove `state/rootfs`, `state/local`, the layout marker or
old boot entries to force a retry. Successful initialization can remain after a
later boot failure; unknown or incompatible roots are deliberately refused.
The helper declines an existing preparation directory rather than overwriting
partial evidence. No automatic rollback of writable data is attempted.


## Recorded owner acceptance — 2026-11-15

The owner reported that all steps of the G/H/G sequence returned PASS and
everything behaved as expected, using delivery `d3bd849f` with functional code
pinned at `0976c58d`. This closes the bounded physical writable-root boot,
generation-change and return gate.

The three checks cover exact G/H/G deployment selection, retained original
Base/Kernel/boot policy, writable root/local backing mounts, eight persistent
marker locations, temporary-file removal after reboot, read-only Base/System
files, and working Ports/Neovim. The report is the owner's confirmation; the
SSD evidence bundle and a separate shutdown transcript were not imported. No
shutdown problem was reported. This is not a different-Base/Kernel matrix or
a new old-F recovery boot claim. Existing boot entries and user data remain
retained; no cleanup or state/schema rollback was performed.
