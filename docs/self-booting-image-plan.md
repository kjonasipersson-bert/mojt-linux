<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Accepted milestone: a self-booting disk

Status: approved by the owner on 2026-10-24. An experimental implementation
and [build/acceptance guide](uefi-disk-boot.md) are now available. The real
synthetic firmware-boot probe passed; full Mojt UEFI acceptance remains pending.
The following records the agreed scope. System step 5 Bash is additive to the
earlier accepted boot, network, native Ports and administration work.

## Current dependency on the launcher

The original direct mode creates a raw ext4 image without a partition table. Its
launcher supplies external `vmlinuz`, `initramfs.cpio.gz` and the command line
through QEMU's `-kernel`, `-initrd` and `-append`. Early init mounts `/dev/vda`
directly. That mode does not contain a firmware-bootable system. The new opt-in
UEFI mode supplies the partitioned disk and image-contained boot artifacts.

The next milestone should boot from the disk through ordinary VM firmware.
It should preserve the tested Base/System/State/Nix layout and current service
configuration, avoiding a simultaneous kernel-source or desktop transition.

## Recommended first target

Use x86-64 UEFI with GPT and GRUB, initially without Secure Boot:

| Disk component | Contents and responsibility |
| --- | --- |
| FAT32 EFI System Partition | EFI fallback bootloader at `EFI/BOOT/BOOTX64.EFI`; Mojt boot infrastructure |
| ext4 Mojt partition | Existing Base, System generations, persistent State and Nix store; versioned boot artifacts under `/boot/mojt/` |
| Versioned boot entry | Exact System selection, kernel, matching initramfs/module inputs and kernel command line |

GRUB is recommended for a visible serial boot menu and a future choice among
retained boot entries. This does not establish an automatic rollback policy.
The first image needs one known-good entry and a usable serial console; BIOS
support can be evaluated after that path works.

Install the EFI loader into the image's fallback path rather than registering
a host firmware entry. QEMU uses OVMF firmware and its own per-VM variable
file. Image construction operates only on a newly created regular image, using
regular partition images and mtools instead of mappings/mounts. It must not
install a bootloader on the Debian host's disk or change host NVRAM.

## Small implementation steps

1. Add an opt-in partitioned-image mode: GPT, EFI System Partition, ext4 Mojt
   partition and image-contained GRUB. Keep the current direct-boot recipe
   available as a diagnostic path during development.
2. Put the existing tested host kernel and generated initramfs on that disk
   as an exact pair, with a manifest recording their hashes, module input and
   System generation. GRUB loads those disk files. Kernel packaging can move
   to a Mojt-controlled source later; changing it now would obscure boot-chain
   failures with a separate kernel transition.
3. Teach early init to locate the Mojt partition by a stable UUID/PARTUUID,
   with the required discovery helper included in the initramfs. Remove the
   `/dev/vda` whole-disk assumption. A boot entry must select its corresponding
   System generation explicitly rather than silently using a changed
   `system/current` with an older kernel/initramfs pair.
4. Add a firmware-boot launcher with no `-kernel`, `-initrd` or `-append`.
   Keep serial output from GRUB through kernel, initramfs and authenticated
   Bash login. Run existing boot, network, Ports and persistence checks.

The first builder is still a VM image tool. A hardware installer, complete
module/firmware policy, Secure Boot, in-place System updates, automatic
fallback and transactional boot selection are separate work. Retaining a
boot entry alone does not roll back persistent `/etc`, `/var` or service data.

## Acceptance that proves the milestone

- Boot the image through OVMF with all external kernel/initramfs arguments
  removed, and inspect the boot entry and guest kernel command line.
- Log in through the serial console, run the existing boot/admin/network/Ports
  checks, install a program and write a persistent note.
- Shut down, restart the same disk and verify the program, note and history.
- Copy the powered-off disk alone into a clean VM directory and boot with a
  fresh firmware-variable file. No original payload directory or external
  kernel/initramfs may be required at runtime. Firmware and QEMU remain host
  prerequisites.
- Fail the build cleanly for missing kernel/initramfs inputs, undersized
  images and partition/bootloader failures, leaving existing images and the
  host boot setup untouched.

References: [QEMU direct Linux boot](https://www.qemu.org/docs/master/system/linuxboot.html),
[QEMU firmware/boot options](https://www.qemu.org/docs/master/system/qemu-manpage.html),
and [GNU GRUB EFI/removable installation](https://www.gnu.org/software/grub/manual/grub/html_node/Installing-GRUB-using-grub_002dinstall.html).
