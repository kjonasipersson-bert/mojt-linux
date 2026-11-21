<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# 8. Hardware and firmware

## 8.1 Ownership and supported scope

Kernel artifacts own their versioned module trees. System supplies firmware,
upstream licenses and device initialization. Base supplies neither. Selecting
another Kernel keeps the selected System's firmware; selecting another System
can change firmware without replacing the Kernel. A new Kernel can require newer
firmware, so independent lifecycles do not guarantee every combination works.

The `pc-x86_64` bootstrap profile targets UEFI x86-64 PCs using an ext4 root
filesystem on NVMe, AHCI SATA, USB storage, VirtIO block or VirtIO SCSI. It includes
PS/2 and USB keyboard modules for the local password console. It does not provide
Secure Boot, encrypted root, RAID, every storage controller or a graphical desktop.

The earlier `thinkpad-x1-carbon-3` profile retains its fixed Intel device policy
and existing firmware requirements. Existing boot selections keep their profile;
installing new tools does not migrate them. The two profiles cannot share one
native-v2 selection menu. Use a separate image/target to try the PC profile while
keeping the previous working installation available.

## 8.2 Device detection

The initramfs includes only the early driver dependency closure, resolved from the
exact selected Kernel with kmod. NVMe and VirtIO SCSI are included in the PC
profile. A required early driver must exist as a module or be recorded as built
in; construction refuses missing drivers rather than using the host Kernel.

The complete selected module tree and System firmware are mounted read-only before
System starts. After System setup and systemd-udevd, the PC hardware service uses
`udevadm trigger --action=add` for subsystems and devices, waiting for those events
to complete. Standard udev rules load drivers for detected devices. It does not
require Intel graphics, Ethernet or Wi-Fi hardware. Device-specific failures remain
visible in the journal; successful event processing is not proof that each device
works. See the upstream [udevadm reference](https://www.freedesktop.org/software/systemd/man/latest/udevadm.html).

## 8.3 Firmware input

For the current Debian bootstrap backend, extract these packages into one new
firmware root:

| Package | Included firmware family |
| --- | --- |
| `firmware-iwlwifi` | Intel Wi-Fi |
| `firmware-intel-graphics` | Intel graphics |
| `firmware-amd-graphics` | AMD graphics |
| `firmware-realtek` | Realtek network devices |
| `firmware-atheros` | Qualcomm Atheros Wi-Fi |
| `firmware-mediatek` | MediaTek Wi-Fi |
| `firmware-brcm80211` | Broadcom Wi-Fi supported by upstream drivers |
| `wireless-regdb` | Wi-Fi regulatory database and signature |

These are bootstrap package names, not mutable runtime packages managed by Mojt.
See Debian's [firmware package index](https://packages.debian.org/source/trixie/firmware-nonfree).
The package version still determines which devices' firmware is included; newer
hardware may require newer inputs. Proprietary drivers, every audio/Bluetooth
device and board-specific configuration are outside this profile's coverage.

On a Debian builder configured with the intended suite and `non-free-firmware`,
use a new workspace. APT uses its configured authenticated package indexes:

```sh
mkdir pc-firmware-work
cd pc-firmware-work
mkdir packages firmware-root
cd packages
apt-get download firmware-iwlwifi firmware-intel-graphics firmware-amd-graphics \
  firmware-realtek firmware-atheros firmware-mediatek firmware-brcm80211 wireless-regdb
for package in ./*.deb; do
  dpkg-deb --extract "$package" ../firmware-root
  dpkg-deb --show --showformat='${Package} ${Version}\n' "$package"
done > ../firmware-root/packages.txt
sha256sum ./*.deb > ../firmware-root/SHA256SUMS
cd ..
```

Retain the downloaded archives and their version/hash records for repeating the
build. The firmware root must contain `usr/lib/firmware` (or `lib/firmware`), a
payload for each listed family, the regulatory database/signature and
`usr/share/doc/PACKAGE/copyright` for every listed package. Absolute, escaping or
broken links and special files are rejected. Extraction does not run package
scripts; the builder explicitly selects Debian's signed regulatory database when
the normal filenames are absent.

Bootstrap freezes the firmware and license trees, with any `packages.txt` and
`SHA256SUMS` records, into its private workspace. Changed inputs are rejected.
System packaging inventories their bytes and mounts them at `/lib/firmware` for
the chosen boot. Plain hashes provide integrity, not publisher authentication.

## 8.4 Constructing and checking a PC image

Add these options to the existing
[native bootstrap workflow](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/mbt-minimal.md#fresh-native-v2-bootstrap):

```sh
--hardware-profile pc-x86_64 --firmware-root /path/to/pc-firmware-work/firmware-root
```

Use explicit Base, Kernel and System inputs as in that workflow. Preview with
`--dry-run`, then construct a new image or an explicitly selected mounted target.
This does not convert an existing ThinkPad boot selection. Native records bind
`pc-x86_64-v1` and the local console to the selected System and Kernel.

For an image, `QEMU_DISK_BUS=sata`, `usb` or `nvme` chooses the emulated disk bus.
Emulated storage boots do not validate physical Wi-Fi/GPU firmware. On hardware,
check the actual network and devices, inspect `journalctl -b -k`, and retain the
previous working image until the new installation has been checked.
