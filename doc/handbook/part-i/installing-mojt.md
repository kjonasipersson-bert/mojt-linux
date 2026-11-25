<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# 2. Installing Mojt

[Handbook](../README.md) · [Previous: Introduction](introduction.md) · [Next: MPM](mpm.md)

## Create the USB media

Use a prepared Mojt `install.img` for the target's hardware profile. The raw
image includes the Base, System, Kernel, and tools needed to install offline.
For a general x86-64 PC, use an image built with the `pc-x86_64` profile.
The [media preparation guide](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/mounted-installation.md#prepare-a-self-contained-installer-image)
explains how to build the image. If you built it locally, use the resulting
`disk.img` in place of `install.img` below.

The USB drive must hold the full image. Writing the image erases the entire
USB drive. On a Linux host, compare the disk list before and after plugging
in the drive. Identify it by model, size, and serial number.

```sh
lsblk -o NAME,PATH,TYPE,TRAN,SIZE,MODEL,SERIAL,MOUNTPOINTS
ls -l /dev/disk/by-id/usb-*
```

Unmount any mounted partitions on that USB drive with `sudo umount`, passing
each mounted partition's device path. Set `usb` to the matching whole-drive
link in `/dev/disk/by-id/`. Partition links end in `-partN`, where `N` is the
partition number. Check the drive and its mountpoints again before writing.

```sh
image=./install.img
usb=/dev/disk/by-id/usb-REPLACE_WITH_DEVICE_ID
lsblk -o NAME,TYPE,SIZE,MODEL,SERIAL,MOUNTPOINTS "$usb"
```

Once the correct whole drive is identified and its partitions are unmounted,
write the raw image and wait for the command to finish before removing the
drive.

```sh
sudo dd if="$image" of="$usb" bs=16M conv=fsync,nocreat status=progress
```

## Install to a disk

Select the USB drive in the machine's UEFI boot menu. The installation
medium requires x86-64 UEFI with Secure Boot disabled for the unsigned
bootloader. It opens a local root shell without a password prompt. The USB
drive is read-only during the session. Temporary files and live settings
are kept in RAM and discarded at shutdown.

Identify the intended target disk, then start the installer.

```sh
lsblk -o NAME,PATH,RO,SIZE,MODEL,SERIAL,MOUNTPOINTS
mbt install
```

1. Choose the number of the target disk by checking its device path, model,
   capacity, and serial number where shown. The installation USB is excluded
   from the list. Press Enter at the disk prompt to cancel.
2. Enter the swap size in GiB. Press Enter for 0 GiB.
3. Wait for the installer to check its inputs and show the planned layout.
   Type the displayed device path only if the entire selected disk can be
   erased. Press Enter at this prompt to cancel. The installer creates a GPT
   disk with a 128 MiB FAT32 EFI partition, an optional swap partition, and
   Btrfs on the remaining space.
4. Choose a root password for the installed system when prompted. Wait for
   `Mojt installed`, then run `systemctl poweroff`.

The target disk's storage driver must be supported by the installation kit's
hardware profile. The prompts use the installation console's keyboard layout.

## Boot the installed system

Remove the USB drive and boot from the target disk. Select it in the UEFI
boot menu if needed. Log in as `root` with the password set during installation.
Check the running Base and that `/` is mounted as writable Btrfs.

```sh
cat /usr/lib/os-release
findmnt -T /
```

If you requested swap, run `cat /proc/swaps` to check that it is active.

[Previous: Introduction](introduction.md) · [Next: MPM](mpm.md)
