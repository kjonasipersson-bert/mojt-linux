<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Use the existing Mojt VM from an SSH terminal

`tools/mojt-vm-serial.py` makes a separate copy of a **stopped**, local-console,
password-login UEFI VM and adds an authenticated serial console. GRUB, login and the guest
shell then use the current terminal. The existing password, all Base/System
pairs, persistent state, Ports and firmware variables are retained. The
original image remains unchanged.

The copied persistent `/etc` gains a `mojt-serial-console.service`, its
`mojt.target.wants` link and a missing `ttyS0` entry in `securetty`. Existing
local-console access remains available. No Base/System profile, password or
boot artifact is rewritten. Conflicting configuration is refused.
An image whose System profile already selects serial login is refused, since
starting two gettys on the same tty would conflict; use its existing launcher.

## Prepare the copy on the Debian host

First shut down the current guest cleanly using `systemctl poweroff` **inside
Mojt**. Image preparation uses default QEMU image locks and refuses an active
QEMU writer. The extracted ext4 filesystem must also pass a read-only check.
Never use `--force-share` to work around a running source VM. See the upstream
[qemu-img offline-image guidance](https://www.qemu.org/docs/master/tools/qemu-img.html).

Host dependencies are `qemu-utils`, `e2fsprogs`, `fdisk` and `util-linux`.
Image preparation itself runs as the ordinary image owner, without sudo,
mounts or loop devices. The copy and temporary partition files require free
space; both disk images remain sparse.

For the owner's existing experiment:

```bash
bash <<'MOJT_SERIAL' || printf '%s\n' 'Serial VM preparation stopped; see the error above.' >&2
set -euo pipefail
export PATH="/usr/sbin:/sbin:$PATH"
WORK="$HOME/mojt-generations.9eMyMQ"
git -C "$WORK/source" pull --ff-only
python3 "$WORK/source/tools/mojt-vm-serial.py" \
  --source "$WORK/image" --output "$WORK/serial-image"
MOJT_SERIAL
```

The output directory must be new. If preparation fails, the completed source
VM remains available. The tool never replaces an existing output directory.

## Start and use it from SSH

Run the launcher separately in the interactive SSH terminal:

```bash
"$HOME/mojt-generations.9eMyMQ/serial-image/run-qemu.sh"
```

Use GRUB's arrow keys, select a pair, and log in as `root` with the existing
VM password. Commands can now be pasted into the terminal. The headless
launcher defaults to `QEMU_DISPLAY=none`; it retains the SATA/USB bus choice
and the existing terminal multiplexer (`-serial mon:stdio`). No network login
or host port forwarding is needed for this console.

Inside Mojt, `systemctl poweroff` cleanly shuts down the guest and returns to
the Debian SSH prompt. `Ctrl-A`, then `c` switches between the guest serial
console and QEMU's monitor. Use guest shutdown rather than terminating QEMU
when preserving state. A plain `exit` logs out of the guest shell.

An optional `tmux` session can keep the console running across SSH reconnects:
start `tmux new -s mojt` before the launcher, detach with `Ctrl-B`, then `d`,
and reconnect using `tmux attach -t mojt`.

## Manual interruption test on the Debian host

After confirming login in the serial copy, shut down that guest. Keep it
stopped while checking its disk hash. The following block builds toward a
different output path. At **New Mojt VM root password**, press `Ctrl-C`.
It must report an interruption, leave no published interrupted image, and
retain the completed serial VM's disk hash.

```bash
bash <<'MOJT_INTERRUPT' || printf '%s\n' 'Interruption probe stopped; see the error above.' >&2
set -euo pipefail
export PATH="/usr/sbin:/sbin:$PATH"
WORK="$HOME/mojt-generations.9eMyMQ"
. "$WORK/experiment.env"
. "$WORK/hardware.env"
PAYLOAD="$HOME/mojt-lab/mpm-nix-home/mpm-system-test/system-step6"
test ! -e "$WORK/interrupted-image"
test ! -L "$WORK/interrupted-image"
sudo -v </dev/tty
before="$(sha256sum "$WORK/serial-image/disk.img")"
interrupted=0
trap 'interrupted=1' INT
if sudo python3 "$WORK/source/tools/mojt-vm-build.py" \
  --target "$TARGET" --output "$WORK/interrupted-image" \
  --kernel "$KERNEL" --modules-dir "$MODULES" \
  --firmware-root "$INPUTS/root" --system-payload "$PAYLOAD" \
  --boot-mode uefi --hardware-profile thinkpad-x1-carbon-3 \
  --base-generation "$BASE_A" --system-generation system-A \
  --additional-generations "$WORK/generations.toml" \
  --disk-size-mib 8192 --login-mode password \
  --root-shell /run/mojt-system/bin/bash </dev/tty; then
  status=0
else
  status=$?
fi
trap - INT
test "$interrupted" -eq 1
test "$status" -ne 0
test ! -e "$WORK/interrupted-image"
test ! -L "$WORK/interrupted-image"
test "$before" = "$(sha256sum "$WORK/serial-image/disk.img")"
printf '\nPASS: interrupted build published no image; completed VM disk unchanged.\n'
MOJT_INTERRUPT
```

Start `serial-image/run-qemu.sh` again. Confirm the selected Base/System pair
and the two existing generation markers. This tests a controlled build
interruption; it does not establish power-loss recovery or update atomicity
on an existing boot disk.

## Owner acceptance

On 2026-10-26, the owner logged in as root with the existing VM password
through the adapted copy's serial console on the Debian host. The real Mojt
systemd guest reported `/dev/ttyS0`, System `system-A`, Base `0.1.3` and
kernel `6.12.107+deb13-amd64`. Both `/etc/generation-marker` and
`/var/generation-marker` still contained `generation-test-9eMyMQ`.

This verifies authenticated console login and guest shell commands with the
full System payload. Restart after a controlled build interruption remains
the next manual check.

## Validation boundaries

The regression suite uses real GPT/ext4 image copies and checks source
immutability, retained state/shadow credentials, all boot pairs, preserved
firmware variables, refusal of linked/conflicting configuration and existing
outputs, active QEMU image locks, and failure before publication.

The opt-in firmware probe's `--serial-login --generations` run boots the
adapted copy, authenticates a synthetic BusyBox guest on `ttyS0`, executes
shell commands and repeats the generation sequence and disk-only transfer.
Its fixture dispatches the getty directly after checking the unit/link; it
does not run systemd or the real Nix payload. The full Mojt systemd serial-console
acceptance is recorded above; the owner's manual interruption run is pending.
