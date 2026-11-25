<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Offline whole-disk installer on a two-disk VM

The [media preparation guide](../mounted-installation.md#prepare-a-self-contained-installer-image)
describes the supported build. Use a serial VirtIO installer image for this
test.

## Procedure

On the host, copy the prepared raw installer image and create a separate,
sparse 40 GiB target file. The host must have QEMU and matching OVMF code and
variable templates. Set `INSTALLER_DIR` to the directory containing the
prepared `disk.img`.

```sh
LAB=$(mktemp -d)
cp --sparse=always "$INSTALLER_DIR/disk.img" "$LAB/installer.img"
sha256sum "$LAB/installer.img" >"$LAB/installer.sha256"
truncate -s 40G "$LAB/target.img"

boot_test() {
    vars=$1
    shift
    cp /usr/share/OVMF/OVMF_VARS_4M.fd "$LAB/$vars"
    qemu-system-x86_64 \
        -machine q35,accel=kvm:tcg -m 4096 -smp 2 \
        -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
        -drive "if=pflash,format=raw,file=$LAB/$vars" \
        -nic none -display none -serial mon:stdio -no-reboot "$@"
}

boot_test install-vars.fd \
    -drive "if=none,format=raw,id=installer,readonly=on,file=$LAB/installer.img" \
    -device virtio-blk-pci,drive=installer,bootindex=1 \
    -drive "if=none,format=raw,id=target,file=$LAB/target.img" \
    -device virtio-blk-pci,drive=target
```

At the installer console, run `mbt install`. Check that the boot disk
is excluded and only the empty 40 GiB disk is offered. Select it, set 2 GiB
swap, confirm the exact device path and enter a new root password. Wait
for `Mojt installed` and power off. On the host, run
`sha256sum --check "$LAB/installer.sha256"`.

Boot only the target, with fresh firmware variables, in the same host shell.

```sh
boot_test target-vars.fd \
    -drive "if=none,format=raw,id=target,file=$LAB/target.img" \
    -device virtio-blk-pci,drive=target,bootindex=1
```

Log in with the new password. Read `/usr/lib/os-release` and check
`grep ' / btrfs ' /proc/mounts` and `cat /proc/swaps`. Require the intended
Base, a writable Btrfs root and automatically active swap at the requested
size. This procedure exposes only disposable regular-file disks to QEMU.

## Acceptance criterion for read-only media

Repeat with a fresh target file and cancel at disk confirmation. Check the
source hash again. Repeat the successful run and the cancellation with the
source attached writable at the QEMU layer (omit `readonly=on` for the
installer drive). Inside the installer, verify the kernel has made the
installer disk read-only with `lsblk -o NAME,RO,MOUNTPOINTS` and that the
source, including its GPT and EFI partition, remains byte-identical once
powered off.

## Read-only startup probe on 2026-11-25

A minimal QEMU/OVMF test image booted the installer initramfs mount code
with ext4 and Btrfs roots. For each filesystem, the image was attached with
both read-only and writable QEMU backing. Linux reported the disk, ESP and
root partition read-only, rejected an attempt to remount the source root
writable, and powered off with the full image SHA256 unchanged. A separate
mount-namespace test exercised the RAM-backed root handover and read-only
installer input mount. Whole-disk installation from the rebuilt media
remains to be exercised end to end.

## Recorded acceptance on 2026-11-24

The offline test used Debian with QEMU/OVMF and installer revision
`0f18c60083803592473d4d80ca47502ef17e6e5c`. The target booted by itself to
login. It reported System `system-installer-021`, Base 0.2.1 and Kernel
`6.12.107-mojt1`. Root was writable Btrfs on `/dev/vda3`, using subvolume
ID 5. `/proc/swaps` reported active partition swap on `/dev/vda2` with
2,097,148 KiB usable, matching the requested 2 GiB partition.

An earlier run stopped after formatting because the mounted target check
compared Btrfs device numbers from two different kernel interfaces. The
corrected revision matches the opened directory to its Linux mount ID and
checks the backing partition separately. Physical USB and SSD acceptance
remain separate.

The older prepared-partition path was accepted in a VirtIO VM on 2026-11-12
with an ext4 root and FAT32 ESP. Its independent boot agreed with the
selected UUID and deployment, reached login and had no failed units.


## Physical USB boot on 2026-11-24

The generic `pc-x86_64` USB image booted on Lenovo hardware with
Base 0.2.1 and Kernel `6.12.107-mojt1`. NetworkManager joined the local
wireless network through `nmcli`. DNS resolution and ping to `www.dn.se`
worked. `man bash` and `man nmcli` were missing in that System export.

The locally compiled `6.18.63-mojt-lts1` Kernel belongs to the existing
Lenovo installation. The USB result applies to the 6.12 build input. A
whole-disk installation test from a separate 8 GiB generic PC USB image on a
faster machine reached native construction. A copy between the private
`/var/tmp/mojt-native-inputs-*` paths failed with `No space left on device`.
The run did not reach target content publication or target boot. The
subsequent implementation moves assembly to the confirmed target disk.
A complete physical retry with that implementation remains outstanding.
