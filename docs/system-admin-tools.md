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
passed in the agent runtime. Actual mount/unmount and kernel-log access
remain to be accepted in the Mojt VM; this runtime check is not a boot test.

Regression tests cover the additive step, unchanged Base, retained MPM/source,
split-output command links, missing executable rejection, payload export and
temporary-mount cleanup on success and failure. The owner's step 4 export,
VM boot and reboot acceptance have not yet been reported.
