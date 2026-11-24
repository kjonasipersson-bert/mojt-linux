<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# 2. Installing Mojt

[Handbook](../README.md) · [Previous: Introduction](introduction.md) · [Next: MPM](mpm.md)

Boot the Mojt installation USB in x86-64 UEFI mode. Use a builder-enabled
image prepared with `--with-build-tools --with-installer-inputs` and the
private image tool environment. The medium carries the Base, System, and Kernel
inputs and can install offline.

As root on the USB system, run

```sh
/var/lib/mojt/installer-tools/run /run/mojt-system/bin/mbt install
```

Choose the whole disk and the swap size in GiB. Enter selects zero swap.
Check the device name, model, capacity, and serial number where shown. Typing
the displayed device path confirms erasing the entire disk. The installer
creates a GPT disk with a 128 MiB FAT32 EFI partition, an optional swap
partition, and Btrfs on the remaining space. Choose a new root password when
prompted. After installation, shut down, remove the USB, and boot from the
target disk.

The installer supports one whole disk with a storage driver supported by the
installation kit's hardware profile. It uses the console keyboard layout of
the booted medium. See the [USB preparation guide](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/mounted-installation.md#prepare-a-self-contained-installer-image).

[Previous: Introduction](introduction.md) · [Next: MPM](mpm.md)
