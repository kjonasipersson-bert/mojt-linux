<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Interactive Bash in System

The owner successfully installed `bashInteractive` through MPM in the running
Mojt VM and approved Bash as a System component on 2026-10-24. System step 5
adds that package to the cumulative step 4 payload. It uses the existing
Nixpkgs pin; the agent verified Bash 5.3p20 from its signed binary cache.

Only `bash` is exported through `/run/mojt-system/bin`; Base's `/bin/sh` and
Base contents are unchanged. The authenticated VM recipe explicitly selects
`/run/mojt-system/bin/bash` in the **new VM's copied** root account. Omitting
`--root-shell` preserves the copied account's existing selection. The builder
checks that the selected System generation exports the exact Bash executable
from the verified payload before changing that account.

## Console defaults

The System profile provides a user/host/directory prompt, Readline editing,
basic command/file completion and append-mode history. Root history lives in
`/var/lib/mojt/console/root.history`, with directory mode 0700 and file mode
0600, owned by root. A prompt hook appends completed commands so an ordinary
console shutdown does not depend on logging out first. This is history
retention, not an audit log or a crash-durability guarantee.

Mojt adds `/etc/profile.d/mojt-bash.sh` and adds `/etc/bashrc` only when absent.
It preserves existing local `/etc/profile`, `/etc/bashrc` and history contents.
A newly created default `/etc/profile` sources both Mojt environment and Bash
hooks. If an existing local profile does not source `/etc/profile.d/*.sh`, the
administrator can source `/etc/profile.d/mojt-bash.sh` explicitly. User startup
files may override the defaults. This adds no programmable completion package
or user-account management framework.

`checkwinsize` is enabled, but it reads the TTY's registered size; it does not
query the remote terminal. It therefore cannot fix the reported `stty size`
value `0 0`. Continue using the manual rows/columns workaround described in
[the administration guide](system-admin-tools.md#serial-terminal-geometry-over-ssh-and-qemu)
until serial-size handling is implemented separately.

## Export step 5 in the Nix Distrobox

Update the existing `feature/system-admin-tools` checkout in `mojt-mpm-nix`,
without sudo. A fresh output directory is required:

```sh
cd "$HOME/mpm-system-test/mojt-admin-tools"
git pull --ff-only

python3 tools/mojt-system-prepare.py \
  --step 5 --output "$HOME/mpm-system-test/system-step5" --dry-run

python3 tools/mojt-system-prepare.py \
  --step 5 --output "$HOME/mpm-system-test/system-step5" -y
```

An existing step 4 payload cannot supply the new package role. Retain earlier
payloads and VM disks; this is a new-image build, not an in-place System upgrade.

## Build and test on the Debian host

After shutting down Mojt and leaving the Distrobox:

```sh
cd "$HOME/mojt-lab/mojt-admin-tools"
git pull --ff-only

TARGET="$HOME/mojt-lab/root-test-013"
PAYLOAD="$HOME/mojt-lab/mpm-nix-home/mpm-system-test/system-step5"
KREL="$(uname -r)"
VM="$HOME/mojt-lab/vm/system-step5-$(date +%Y%m%d-%H%M%S)"

sudo python3 tools/mojt-vm-build.py \
  --target "$TARGET" \
  --kernel "/boot/vmlinuz-$KREL" \
  --system-payload "$PAYLOAD" \
  --disk-size-mib 6144 \
  --login-mode password --root-shell /run/mojt-system/bin/bash \
  --output "$VM"

"$VM/run-qemu.sh"
```

After normal root login, without manually starting Bash:

```sh
printf 'Bash: %s; flags: %s\n' "$BASH_VERSION" "$-"
printf 'History: %s\n' "$HISTFILE"
shopt histappend checkwinsize
bind -l
mpm ports list
mojt-system-check admin
mojt-system-check network
```

Expect a nonempty Bash version, `i` in the flags, the persistent history path,
both shell options enabled and Readline functions. Exercise up-arrow recall
and tab completion. Enter `printf 'Mojt Bash history probe\n'`, power off with
`systemctl poweroff`, restart the **same disk** and use `history` to find the
probe. `/bin/sh` remains available explicitly for POSIX/recovery work.

This recipe uses QEMU's external kernel/initramfs arguments. The additive
[UEFI disk recipe](uefi-disk-boot.md) reuses the same step 5 payload and puts
the boot pair on the disk.

## Validation boundary

Regression tests cover additive step 5 roles, unchanged Base, explicit login
selection, missing/changed System Bash rejection, preserved local configuration
and history, and refusal to follow a history-directory link outside staging.
An agent-side PTY test with the real pinned Nix Bash and Mojt profile passed
line editing, history recall, tab completion, per-prompt history append and
history recall in a second shell. Test paths substituted temporary locations
for the guest's `/run` and `/var`; this was not a Mojt boot/login test.

The owner's Ports Bash trial passed. The new System step 5 login and reboot
acceptance remain pending.
