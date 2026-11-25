<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# 2. Installing Mojt

[Handbook](../README.md) · [Previous: Introduction](introduction.md) · [Next: MPM](mpm.md)

Use a prepared Mojt `install.img` for the target's hardware profile. The
raw image can boot as a virtual disk or be written to a USB drive. It carries
the Base, System, Kernel, and tools needed for an offline installation. See
the [media preparation guide](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/mounted-installation.md#prepare-a-self-contained-installer-image)
if you need to build the image yourself.

Boot the medium in x86-64 UEFI mode with Secure Boot disabled for the unsigned
bootloader. The installation medium opens a root shell on its console without
a password prompt. Run

```sh
mbt install
```

Choose the whole disk and the swap size in GiB. Enter selects zero swap.
Check the device name, model, capacity, and serial number where shown. Typing
the displayed device path confirms erasing the entire disk. The installer
creates a GPT disk with a 128 MiB FAT32 EFI partition, an optional swap
partition, and Btrfs on the remaining space. Choose a new root password when
prompted. Wait for `Mojt installed`, then power off, remove or detach the
installation medium, and boot from the target disk. Log in with the password
you just set. Use `cat /usr/lib/os-release` to check the running Base and
`cat /proc/swaps` to check that any requested swap partition is active.

The USB medium is read-only during the session. Temporary files and live
settings are kept in RAM and discarded when the machine shuts down.
The installer uses one whole disk with a storage driver supported by the
installation kit's hardware profile. The prompts use the console keyboard
layout of the booted medium.

[Previous: Introduction](introduction.md) · [Next: MPM](mpm.md)
