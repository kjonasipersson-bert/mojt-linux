<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Small System administration toolset

System step 4 adds a small administration set to the accepted step 3 VM.
It retains systemd, networking and MPM/Nix, and leaves the Base image and
earlier step 1–3 payload definitions unchanged. This is a System payload
addition, not an `mpm system install` implementation.

| System package | Exported commands |
| --- | --- |
| procps | `ps`, `top`, `free`, `pgrep`, `uptime` |
| util-linux | `lsblk`, `findmnt`, `mount`, `umount`, `dmesg`, `blkid` |
| less | `less` |
| nvi | `vi`, `ex` |

Commands live in the selected System generation's `bin`, exposed through
`/run/mojt-system/bin`. There are no new services, preset rules, login/PAM
configuration or setuid wrappers. Administration is still root-operated in
the VM. The Nix source and complete runtime closures are exported/registered
and protected by System GC roots, as in step 3. util-linux's binary output
links to its separate mount output; both are retained through the closure.

`EDITOR` and `VISUAL` default to `vi`, and `PAGER` to `less`, without replacing
nonempty existing environment preferences. nvi supplies a small vi even
before Ports are installed. A later Ports installation of Vim can provide
the interactive `vi` through the existing Ports-first PATH. The System vi
remains accessible explicitly as `/run/mojt-system/bin/vi`. Similarly, System
less does not appear in `mpm ports list`; that command lists Ports only.

## Export a new payload in the Nix Distrobox

Unlike the earlier wrapper-only update, this change **requires a new payload**.
The old step 3 payload does not contain the added package outputs. Inside the
existing `mojt-mpm-nix` container, without sudo:

```sh
cd "$HOME/mpm-system-test"
git clone --single-branch --branch feature/system-admin-tools \
  https://github.com/kjonasipersson-bert/mojt-linux.git \
  mojt-admin-tools
cd mojt-admin-tools

python3 tools/mojt-system-prepare.py \
  --step 4 --output "$HOME/mpm-system-test/system-step4" --dry-run

python3 tools/mojt-system-prepare.py \
  --step 4 --output "$HOME/mpm-system-test/system-step4" -y
```

The source pin remains the existing Nixpkgs revision from
`manifests/mpm-nix-example.toml`. No channel update or source build is done.
Preparation verifies the transferred store trees and refuses an existing
output directory. Keep the previous payloads for comparison/recovery.

## Build a new VM on the Debian host

Shut down any running Mojt VM and leave the Distrobox with `exit`. On the
Debian host, use the existing Base target and the newly exported payload:

```sh
cd "$HOME/mojt-lab"
git clone --single-branch --branch feature/system-admin-tools \
  https://github.com/kjonasipersson-bert/mojt-linux.git \
  mojt-admin-tools
cd mojt-admin-tools

TARGET="$HOME/mojt-lab/root-test-013"
PAYLOAD="$HOME/mojt-lab/mpm-nix-home/mpm-system-test/system-step4"
KREL="$(uname -r)"
VM="$HOME/mojt-lab/vm/system-step4-$(date +%Y%m%d-%H%M%S)"

sudo python3 tools/mojt-vm-build.py \
  --target "$TARGET" \
  --kernel "/boot/vmlinuz-$KREL" \
  --system-payload "$PAYLOAD" \
  --disk-size-mib 6144 \
  --login-mode password --root-shell /bin/sh \
  --output "$VM"

"$VM/run-qemu.sh"
```

This creates System `0.2-step4` and includes the latest MPM list presentation.
It still uses the existing QEMU direct kernel/initramfs boot; installing a
bootloader on the disk is a separate next step.

## Acceptance inside the new VM

After normal root login:

```sh
command -v ps
command -v vi
command -v less
ps -p 1 -o pid,comm
free -h
lsblk

mojt-system-check admin
mojt-system-check network
mojt-system-check ports
```

The admin checker uses System-first PATH to test System tools even when a
Ports profile shadows a command. It checks PID 1 through procps, runs one
batch `top` frame, inspects memory/disks/mounts and reads the kernel log. It
mounts a new 1 MiB tmpfs under a private `/tmp/mojt-admin.*` directory, verifies
the mount and unmounts it. An exit/signal trap cleans up on failure too. The
editor check creates a temporary file through noninteractive `ex`, verifies
its content and removes it. No persistent configuration or block-device
contents are changed by this probe.

Also exercise the serial terminal interactively:

```sh
top
less /etc/os-release
vi /etc/mojt-admin-note
```

Quit `top`/`less` with `q`; save a note in vi with `:wq`. Run `systemctl
poweroff`, restart the same `$VM/run-qemu.sh`, and verify that the tools are
available after normal login and the note in `/etc/mojt-admin-note` remains.
If the existing login profile is custom, the explicit environment hook
`. /run/mojt-system/environment` remains available; do not overwrite local
configuration to enable the hook.

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
[System step 5](system-bash.md) implements that addition with console defaults
and persistent root history. Automatic serial-terminal sizing remains open.
