<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# First self-booting Mojt disk

The owner approved a simple UEFI/GPT/GRUB image on 2026-10-24. The new opt-in
`--boot-mode uefi` uses one boot entry and the same host kernel source as the
accepted direct-boot VM. It reuses the System step 5 payload, including Bash.
The default `direct` mode remains available.

## What the image contains

| Location | Contents |
| --- | --- |
| GPT partition 1 | 128 MiB FAT32 EFI partition; standalone GRUB at `EFI/BOOT/BOOTX64.EFI` |
| GPT partition 2 | ext4 Mojt filesystem with existing Base/System/State/Nix layout |
| `/boot/mojt/0.2-step5/` on ext4 | Kernel, initramfs, one-entry GRUB config and `boot.json` |
| Output `build.json` | Build provenance, partition extents/UUID, boot-input hashes and System metadata |

GRUB searches ext4 by UUID. The kernel command line names that UUID and the
exact System generation; initramfs validates both and mounts that generation
directly, including its identity files. It does not consult a newer
`system/current` for this boot pair. Kernel, initramfs and source module hashes
are recorded for inspection; this is not a signed/Secure Boot implementation.

The builder uses `sfdisk`, `mkfs.ext4`, `mkfs.vfat`, `grub-mkstandalone` and
`mcopy` against new regular files. It never invokes `grub-install`, mounts the
image or creates loop mappings. Files are staged privately and the final VM
directory is published only after successful assembly. Existing output
directories are refused; a failed build leaves no new published VM.

The firmware launcher has **no `-kernel`, `-initrd` or `-append`**. QEMU needs
host OVMF firmware; the launcher creates a private `OVMF_VARS.fd` on first use
and preserves it on later starts. A fallback EFI path lets a disk-only copy
boot with a new variable file. External copies of the kernel/initramfs and
`run-qemu-direct.sh` are retained only for diagnosis and are not used by the
normal firmware launcher.

## Prepare System step 5 if it is not already exported

An existing step 5 payload can be reused unchanged. If it does not exist,
enter `mojt-mpm-nix` and export it without sudo:

```sh
cd "$HOME/mpm-system-test"
git clone --single-branch --branch feature/uefi-disk-boot \
  https://github.com/kjonasipersson-bert/mojt-linux.git mojt-uefi-boot
cd mojt-uefi-boot

python3 tools/mojt-system-prepare.py \
  --step 5 --output "$HOME/mpm-system-test/system-step5" --dry-run
python3 tools/mojt-system-prepare.py \
  --step 5 --output "$HOME/mpm-system-test/system-step5" -y
```

The exporter refuses an existing output directory. It uses the same pinned
Nixpkgs source; no channel update or source build is required.

## Build on the Debian host

Shut down the old Mojt VM and leave Distrobox. Install the additional image
tools and firmware on Debian; the earlier VM prerequisites still apply:

```sh
sudo apt-get install grub-common grub-efi-amd64-bin fdisk dosfstools mtools ovmf

cd "$HOME/mojt-lab"
git clone --single-branch --branch feature/uefi-disk-boot \
  https://github.com/kjonasipersson-bert/mojt-linux.git mojt-uefi-boot
cd mojt-uefi-boot

TARGET="$HOME/mojt-lab/root-test-013"
PAYLOAD="$HOME/mojt-lab/mpm-nix-home/mpm-system-test/system-step5"
KREL="$(uname -r)"
VM="$HOME/mojt-lab/vm/uefi-step5-$(date +%Y%m%d-%H%M%S)"

sudo python3 tools/mojt-vm-build.py \
  --target "$TARGET" \
  --kernel "/boot/vmlinuz-$KREL" \
  --system-payload "$PAYLOAD" \
  --boot-mode uefi --disk-size-mib 6144 \
  --login-mode password --root-shell /run/mojt-system/bin/bash \
  --output "$VM"

"$VM/run-qemu.sh"
```

The selected static BusyBox must include `findfs` in addition to earlier
required applets. The builder checks this before copying state. Matching
kernel modules must be present; `--modules-dir` also supports a separate tree
ending in `lib/modules/<release>` with kmod dependency metadata.

The launcher defaults to `/usr/share/OVMF/OVMF_CODE_4M.fd` and
`/usr/share/OVMF/OVMF_VARS_4M.fd`. If installed elsewhere, select a matching
non-Secure-Boot pair through `OVMF_CODE` and `OVMF_VARS_TEMPLATE`. Keep the
same pair for a given VM variable file. The GRUB menu and guest console use
115200-baud serial. Terminal sizing remains the separate issue described in
[the administration guide](system-admin-tools.md#serial-terminal-geometry-over-ssh-and-qemu).

## Acceptance inside the full Mojt VM

After the GRUB menu and normal root login:

```sh
test -d /sys/firmware/efi && echo 'PASS: UEFI firmware boot'
cat /proc/cmdline
printf 'Bash: %s\n' "$BASH_VERSION"
cat /run/mojt-disk/boot/mojt/0.2-step5/boot.json
mojt-system-check boot
mojt-system-check admin
mojt-system-check network
mojt-system-check ports

mpm ports install vim -y
vi /etc/mojt-uefi-note
printf 'Mojt UEFI history probe\n'
systemctl --failed --no-pager
systemctl poweroff
```

Expect `root=UUID=...` and `mojt.system=0.2-step5` in the command line,
matching `boot.json`, plus the selected kernel release and Bash login. Restart
the same launcher, inspect the saved note and `mpm ports list`, and use
`history` to find the probe. The password is provisioned in the new VM as
before; the source Base/state installation is not changed.

Finally, while the VM is powered off, copy **only the disk and firmware
launcher** to a fresh private directory on Debian. Keep `VM` set to the source
VM directory from the build. The copy is created directly under your home
directory, so it does not require write access to the build's parent directory:

```sh
(
set -eu
umask 077
: "${VM:?Set VM to the directory containing the powered-off source VM}"
test -r "$VM/disk.img"
test -r "$VM/run-qemu.sh"
COPY="$(mktemp -d "$HOME/uefi-disk-copy.XXXXXX")"
printf 'Test copy: %s\n' "$COPY"
cp --sparse=always "$VM/disk.img" "$COPY/disk.img"
chmod 600 "$COPY/disk.img"
cp "$VM/run-qemu.sh" "$COPY/run-qemu.sh"
"$COPY/run-qemu.sh"
)
```

There is no copied `OVMF_VARS.fd`, kernel, initramfs, source payload or build
tree. The launcher creates new VM variables. Verify login, the retained note
and Ports again. This is the decisive disk-independence check.

The subshell stops at the first failure without changing your interactive
shell's options. `mktemp -d` creates a new mode-0700 directory and prints its
path before copying. The VM builder runs with sudo and may have created a
root-owned parent such as `~/mojt-lab/vm`; this can prevent creating a sibling
copy even though the built VM directory itself belongs to you. Inspect that
parent with `ls -ld "$HOME/mojt-lab/vm"` if needed. A copy-directory failure
occurs before the firmware/boot test and does not require rebuilding the image.

## Validation and remaining scope

Local regressions cover selector validation, UUID/pinned-generation early
init, source module-tree selection, boot hashes, partition boundaries,
existing-image rejection, private retained firmware variables and cleanup
after a simulated GRUB failure. A real image test checks GPT, FAT/EFI loader,
ext4 UUID and exact kernel/initramfs files. CI runs that image test with real
GRUB and filesystem tools.

The agent also ran `tests/run-uefi-smoke.py` using QEMU 8.2.2/TCG, OVMF,
GRUB 2.12, BusyBox 1.36.1 and Ubuntu kernel 6.8.0-138-generic with matching
modules. It uses a synthetic static guest and the actual Mojt early-init
assembly, with an intentionally unusable `system/current` link. Firmware
boot, pinned System, UUID discovery, repeat boot with `/etc` and `/var` state,
and disk-only transfer to fresh variables passed. Device-node packaging used
fakeroot in the constrained agent runtime; no host devices were created.
This is boot-chain evidence, not full Mojt service/login/network acceptance.

## Owner-reported disk-copy acceptance (2026-10-24)

The owner reported that the final disk-copy test works after moving the copy
directory into their home directory. The original attempt failed while creating
the copy directory, before QEMU started; no image rebuild was needed. The
successful recipe copies only the powered-off disk and firmware launcher,
creates fresh firmware variables and starts the copied Mojt disk without
external kernel/initramfs files. This completes the owner-reported disk-boot
milestone. Individual login/service/network/Ports and history-check logs from
this UEFI run were not supplied, so those checks are not separately attested
by this report.

The feature remains an experimental image builder, not a hardware installer,
kernel release pipeline, System updater or automatic rollback mechanism.
Persistent service state is not rolled back by a boot entry.

References: [GNU GRUB standalone image tool](https://manpages.debian.org/bookworm/grub-common/grub-mkstandalone.1.en.html),
[mtools image access](https://www.gnu.org/s/mtools/manual/mtools.html#Drive-letters),
and [QEMU boot options](https://www.qemu.org/docs/master/system/qemu-manpage.html).
