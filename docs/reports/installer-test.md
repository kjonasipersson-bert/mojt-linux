<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Offline whole-disk installer on a two-disk VM

The [media preparation guide](../mounted-installation.md#prepare-a-self-contained-installer-image)
describes the supported build. Use a serial VirtIO installer image for this
test. Prepare its private image tools while online and shut it down.

## Procedure

On the host, copy the prepared raw installer image and create a separate,
sparse 40 GiB target file. The host must have QEMU and matching OVMF code and
variable templates. Set `INSTALLER_DIR` to the directory containing the
prepared `disk.img`.

```sh
LAB=$(mktemp -d)
cp --sparse=always "$INSTALLER_DIR/disk.img" "$LAB/installer.img"
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
    -drive "if=none,format=raw,id=installer,file=$LAB/installer.img" \
    -device virtio-blk-pci,drive=installer,bootindex=1 \
    -drive "if=none,format=raw,id=target,file=$LAB/target.img" \
    -device virtio-blk-pci,drive=target
```

Log in as root on the installer. Run `/var/lib/mojt/installer-tools/run
/run/mojt-system/bin/mbt install` as one command. Check that the boot disk
is excluded and only the empty 40 GiB disk is offered. Select it, set 2 GiB
swap, confirm the exact device path and enter a new root password. Wait
for `Mojt installed` and power off. Keep the installer output if it fails.

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

## Recorded acceptance on 2026-11-24

The owner ran the offline test on Debian with QEMU/OVMF using installer revision
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
