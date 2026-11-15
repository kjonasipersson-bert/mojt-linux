<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Administration tools and console acceptance

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

## Validation status

Agent-side real Nix 2.35.4 evaluation and signed binary imports succeeded
against revision `5adc50831c259f87faeb09ddf930d43597197473`: procps 4.0.7,
util-linux 2.42.4, less 710 and nvi 1.81.6. Every selected executable was
present, including util-linux's cross-output mount links. Real process,
memory, disk, pager/version probes and a noninteractive vi/ex file edit
passed in the agent runtime. This runtime check is not a boot test; see the
subsequent owner report below for Mojt VM evidence.

Regression tests cover the additive step, unchanged Base, retained MPM/source,
split-output command links, missing executable rejection, payload export and
temporary-mount cleanup on success and failure.

## Owner-reported VM acceptance (2026-10-24)

The owner reported that the step 4 setup worked. The supplied screenshot
shows interactive procps `top` running in Mojt with systemd as PID 1, followed
by util-linux `findmnt` showing the Base root and persistent state mounts.
Detailed checker/reboot logs were not supplied. A serial-terminal sizing
issue was reported separately: the guest behaved as though it had 25 rows
while the actual terminal was taller. The connection was Windows terminal
to Debian over SSH, then the existing QEMU serial console. The screenshot
shows `top` updating a smaller upper region with older output below it.
The owner then reported `stty size` as `0 0`, confirming that the guest TTY
had no registered window size, and confirmed that the selected static
BusyBox has no `resize` applet. They also reported that the interactive
console environment feels too limited.



## Serial terminal geometry over SSH and QEMU

The launcher uses `-display none -serial mon:stdio`, and getty advertises
`vt100`. The screenshot and reported geometry are consistent with a stale
guest TTY window size; host terminal resizes are not synchronized by this
Mojt serial-console setup. Confirm inside Mojt, after quitting `top` with `q`:

```sh
stty size
```

The owner's static BusyBox does not include `resize`; the VM builder has
never required that applet. A dedicated resize tool is therefore still a
System follow-up. If stale values of `LINES`/`COLUMNS` are exported, unset
them before restarting the application after setting the kernel TTY size:

```sh
unset LINES COLUMNS
```

For the current image, set the guest size explicitly with
`stty rows ROWS cols COLS`. For example,
`stty rows 40 cols 140` is appropriate only for an actual 40-by-140 terminal.
`stty size` in the Debian SSH terminal **before launching QEMU** gives the
host-side rows/columns to copy into the guest. Recheck after changing the
Windows terminal window size. These workarounds change the current TTY, not
the System payload, and do not require rebuilding the VM. Their result has
not yet been reported by the owner. Automatic serial-login/resize handling
remains a console follow-up.

References: [GNU stty special settings](https://www.gnu.org/software/coreutils/manual/html_node/Special.html),
[BusyBox applets](https://busybox.net/downloads/BusyBox.html), and
[UTM's QEMU serial resize command](https://docs.getutm.app/settings-qemu/devices/serial/#resize-console-command).

## Interactive shell trial and System follow-up

The current VM recipes explicitly select `/bin/sh` from Base for root login.
That is the minimal POSIX shell, not a configured interactive shell profile.
An interactive Bash can already be tried through MPM inside the booted VM:

```sh
mpm ports install bash --attribute bashInteractive -y
bash -i
```

`exit` returns to the original login shell. This trial does not change the
account's login shell or `/bin/sh`. Bash supplies Readline command editing,
history and basic completion; serial window-size synchronization is a separate
problem and is not fixed by starting Bash. This temporary Ports trial alone
does not establish persistent-history or login-shell policy.

The agent fetched the pinned source's `bashInteractive` binary (5.3p20),
verified its Readline bindings and enabled history/editing options, and ran
the shell successfully. On 2026-10-24 the owner reported that installing the
package in the running Mojt VM worked very well and approved Bash in System.
[System step 5](../system-bash.md) implements that addition with console defaults
and persistent root history. Automatic serial-terminal sizing remains open.
