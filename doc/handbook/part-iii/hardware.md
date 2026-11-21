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

## 8.5 Updating firmware in an existing System

The firmware-data transition keeps Base, Kernel, early driver lists, machine
profile and ordinary services. Its `firmware-update.json` contract binds the
selected System manifest, before/after hardware metadata and firmware/license
inventories. Unrelated service, Kernel module and state-schema changes remain
blocked. Returning to a retained prepared deployment selects its original
firmware and services.

This transition may also add the fixed `qemu-guest-agent.service` described below
and its retained binary dependencies. It is a narrow supported service
introduction, not a general service-upgrade or machine-profile migration rule.

The target-side delivery procedure imports `linux-firmware` and `qemu_kvm.ga`
from the installation's pinned Nixpkgs source. Exact upstream firmware source is
retained for `WHENCE` and license texts. Its fixed-output fetch is refused if it
would build other dependencies. Original firmware filenames and regulatory data
are retained; incoming files replace collisions only in the new immutable
component. No Kernel compilation is involved. This differs from the extracted
Debian firmware input used when bootstrapping fresh images.

Preparation downloads and packages substantial data; activation selects the
prepared boot entry. The installed manager imports the package. If the running
manager predates this transition reader, the delivery procedure uses the verified
installed candidate manager to prepare its deployment in an isolated process.
Running manager files and persistent configuration are not patched. See the
[target-side procedure](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/reports/firmware-generation-test.md).

## 8.6 QEMU guests

The bundled Kernel configuration enables VirtIO PCI, block, network, console,
SCSI, balloon, input and graphics, plus virtiofs and 9p. Configuration alone does
not prove that every feature works in a guest. Early boot follows the selected
profile: the retained ThinkPad policy includes VirtIO block; the PC profile also
includes VirtIO SCSI and NVMe. Runtime devices use the complete selected module
tree. A graphical desktop and SPICE integration are separate work.

The firmware-generation procedure includes ordinary `qemu-ga` and
`qemu-guest-agent.service`. After hardware setup the service refreshes VirtIO and
port udev events, then starts only if
`/dev/virtio-ports/org.qemu.guest_agent.0` exists. Without the channel it is skipped,
including on physical hardware. Runtime state uses `/run/qemu-guest-agent`.

```sh
qemu-ga --version
systemctl status qemu-guest-agent.service
journalctl -b -u qemu-guest-agent.service
```

Optional machine configuration is `/etc/qemu/qemu-ga.conf`, using upstream INI
syntax. Keep `daemon=0` for this foreground systemd service. The service does not
create or overwrite the configuration. See the upstream
[QEMU Guest Agent reference](https://www.qemu.org/docs/master/interop/qemu-ga.html).

Configure the named channel through libvirt/virt-manager or add these host QEMU
options, choosing a local socket path:

```sh
-chardev socket,path=/tmp/mojt-qga.sock,server=on,wait=off,id=qga
-device virtio-serial-pci
-device virtserialport,chardev=qga,name=org.qemu.guest_agent.0
```

If the channel is added after boot, use
`systemctl start qemu-guest-agent.service`. Agent communication and the guest's
IP networking/SSH are separate facilities. Firmware does not supply VirtIO
drivers; they belong to the selected Kernel.
