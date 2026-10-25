<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# ThinkPad X1 Carbon 3rd generation: first USB boot

Target: Lenovo 20BTS0SK02, Intel i7-5600U, UEFI, HD Graphics 5500
(`i915`), Intel I218-LM (`e1000e`), Intel Wireless 7265 (`iwlwifi`),
Intel xHCI/EHCI USB and AHCI SATA. The owner supplied PCI IDs and the active
drivers from Arch. Arch's kernel/modules are **not** inputs to this build.

This opt-in profile extends the existing UEFI/GPT/GRUB builder. Base remains
the same whole-image release. Kernel, complete versioned modules, firmware and
firmware licenses belong to the selected System generation. The boot entry
pins that generation, and modules/firmware are bind-mounted read-only at
`/lib/modules` and `/lib/firmware` before System starts. The source Base and
persistent state are not modified; only a new image is assembled.

The early module closure covers USB mass storage/UAS, SCSI disks, SATA, ext4,
PS/2 and USB keyboards, and the previous VirtIO path. It is resolved using
host kmod. Graphics and network drivers are loaded after firmware is mounted.
Full modules permit subsequent udev loading; development `build`/`source`
links to host headers are omitted. Input tree digests and package provenance
are recorded in `hardware.json` and `build.json`; these are transfer checks,
not release authentication.

Local root login uses BusyBox getty/login on `tty1`, `TERM=linux`, and System
Bash. GRUB supports firmware console and serial; kernel console selection
ends in `tty0`. Serial kernel logging remains available. No unauthenticated
local shell is enabled. This is a text-console profile with a US keyboard
layout, not a desktop or a general hardware installer.

## 1. Export System step 6 in the Nix Distrobox

Step 6 adds kmod, `iw`, and `wpa_supplicant` to step 5. NetworkManager is
reused; an explicitly started D-Bus supplicant provides Wi-Fi authentication.
Use a **new** payload directory; existing step 5 exports remain intact.

```sh
cd "$HOME/mpm-system-test"
git clone --single-branch --branch feature/thinkpad-usb-boot \
  https://github.com/kjonasipersson-bert/mojt-linux.git mojt-thinkpad
cd mojt-thinkpad
python3 tools/mojt-system-prepare.py \
  --step 6 --output "$HOME/mpm-system-test/system-step6" --dry-run
python3 tools/mojt-system-prepare.py \
  --step 6 --output "$HOME/mpm-system-test/system-step6" -y
```

This uses the existing pinned Nixpkgs source and signed binary substitutes.
No Nix installation on the Debian build host is needed.

## 2. Prepare Debian Trixie kernel and firmware inputs

Run on the **Debian Trixie build host**, outside Distrobox. Its configured,
authenticated APT sources must include `non-free-firmware`. Install only the
build tools on the host; the kernel/firmware packages below are downloaded
and extracted into a fresh directory, not installed over the host kernel.

```sh
sudo apt-get update
sudo apt-get install python3 zstd cpio kmod busybox-static e2fsprogs \
  grub-common grub-efi-amd64-bin fdisk dosfstools mtools ovmf \
  qemu-system-x86 qemu-system-gui

cd "$HOME/mojt-lab"
git clone --single-branch --branch feature/thinkpad-usb-boot \
  https://github.com/kjonasipersson-bert/mojt-linux.git mojt-thinkpad
cd mojt-thinkpad

INPUTS="$(mktemp -d "$HOME/mojt-thinkpad-inputs.XXXXXX")" &&
(
set -eu
export LC_ALL=C
export PATH="/usr/sbin:/sbin:$PATH"
command -v depmod >/dev/null
mkdir "$INPUTS/debs" "$INPUTS/root"
cd "$INPUTS/debs"
KPKG="$(apt-cache depends linux-image-amd64/trixie |
  sed -n 's/^  Depends: \(linux-image-[^ ]*\)$/\1/p' | head -n 1)"
test -n "$KPKG"
printf 'Selected Trixie kernel package: %s\n' "$KPKG"
apt-get download "$KPKG/trixie" firmware-iwlwifi/trixie \
  firmware-intel-graphics/trixie wireless-regdb/trixie
sha256sum ./*.deb >"$INPUTS/root/SHA256SUMS"
for package in ./*.deb; do
  dpkg-deb -f "$package" Package Version >>"$INPUTS/root/packages.txt"
  dpkg-deb -x "$package" "$INPUTS/root"
done
set -- "$INPUTS/root"/boot/vmlinuz-*
if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo 'Expected one extracted kernel image; refusing incomplete kernel inputs.' >&2
  exit 1
fi
KREL="${1##*/vmlinuz-}"
MODULE_ROOT="$INPUTS/root/usr"
if [ ! -d "$MODULE_ROOT/lib/modules/$KREL" ]; then MODULE_ROOT="$INPUTS/root"; fi
test -d "$MODULE_ROOT/lib/modules/$KREL/kernel" || {
  echo 'Matching kernel modules missing; refusing incomplete kernel inputs.' >&2
  exit 1
}
depmod -b "$MODULE_ROOT" "$KREL"
test -s "$MODULE_ROOT/lib/modules/$KREL/modules.dep"
printf 'Prepared kernel: %s\nRetained inputs: %s\n' "$KREL" "$INPUTS"
)
```

Stop if preparation fails; do not continue with partial inputs. APT verifies
downloads against its authenticated repository metadata. Retain the `.deb`
files alongside the recorded versions/hashes to rebuild this exact input set.
Every download selects `/trixie` explicitly, so installed backports kernels,
APT priorities and a newer default `linux-image-amd64` candidate do not select
a backports kernel. This recipe requires the selected stable kernel package
to contain the image and matching modules; missing payloads fail before the
success message. The release is read from the extracted kernel filename,
not inferred from a potentially empty transitional package.
The subshell includes `/usr/sbin` and `/sbin` in PATH because `depmod` may not
be in an ordinary Debian user's login PATH. Neither depmod nor extraction
requires sudo when operating on these user-owned input files.
`depmod` generates the dependency metadata normally created by Debian's
kernel post-install script. The builder selects the signed Debian regulatory
database normally selected by `wireless-regdb`'s alternatives post-install
script. Neither post-install script is executed on the build host.
Firmware copyright files accompany the firmware inside System. CPU microcode
updates are not added by this first profile.

If an earlier attempt failed (for example, `depmod: command not found` after
downloading a small backports kernel metapackage), leave that partial directory
alone and rerun the updated preparation block to create a fresh `INPUTS`.
Reuse the existing checkout with `git pull --ff-only`; do not clone it again.
The old recipe printed a retained-input path even after failure; the updated
recipe prints its success message only after validating the kernel, modules
and generated dependency metadata.

## 3. Build a fresh image on Debian

Keep `INPUTS` from the preceding section. `TARGET` is the existing installed
Base used in previous VM builds. Adjust `PAYLOAD` if your shared Distrobox
home is mounted elsewhere. This image needs at least an 8 GiB USB device.

```sh
TARGET="$HOME/mojt-lab/root-test-013"
PAYLOAD="$HOME/mojt-lab/mpm-nix-home/mpm-system-test/system-step6"
IMAGE="$HOME/mojt-thinkpad-$(date +%Y%m%d-%H%M%S)"
KERNEL="$(find "$INPUTS/root/boot" -maxdepth 1 -type f -name 'vmlinuz-*')"
KREL="${KERNEL##*/vmlinuz-}"
MODULES="$INPUTS/root/usr/lib/modules/$KREL"
if [ ! -d "$MODULES" ]; then MODULES="$INPUTS/root/lib/modules/$KREL"; fi
test -f "$KERNEL" && test -d "$MODULES" &&
sudo python3 tools/mojt-vm-build.py \
  --target "$TARGET" --output "$IMAGE" \
  --kernel "$KERNEL" --modules-dir "$MODULES" \
  --firmware-root "$INPUTS/root" \
  --system-payload "$PAYLOAD" \
  --boot-mode uefi --hardware-profile thinkpad-x1-carbon-3 \
  --disk-size-mib 6144 --login-mode password \
  --root-shell /run/mojt-system/bin/bash
```

The builder requires step 6, UEFI, password login and the firmware/license
inputs. It refuses existing output directories. Missing kernel modules abort
the build. Existing copied `/etc/securetty` must explicitly permit `tty1`;
the builder refuses incompatible state rather than silently expanding it.

## 4. Test the same image with SATA and USB in QEMU

On a graphical Debian session:

```sh
"$IMAGE/run-qemu.sh"                         # SATA, local screen/keyboard
# After clean guest shutdown:
QEMU_DISK_BUS=usb "$IMAGE/run-qemu.sh"       # xHCI + USB mass storage
```

The launcher explicitly assigns `bootindex=1` to the image device on either
bus. This tells OVMF which disk to prioritize even when the persistent variable
file contains a boot entry for the previous SATA device path.

If an image built with an earlier launcher drops into `UEFI Interactive Shell`
after switching buses, and its EFI partition is mapped as `FS0:`, try:

```text
fs0:\EFI\BOOT\BOOTX64.EFI
```

That starts the EFI fallback loader already on the disk. If it reaches GRUB,
the firmware's automatic boot selection was the failed step, before the
kernel. To add the explicit priority to an existing generated launcher, shut
down the guest and exit QEMU, then run on the Debian host:

```sh
: "${IMAGE:?Set IMAGE to the existing image directory}"
sed -i.before-bootindex \
  -e 's/bus=ide\.0)/bus=ide.0,bootindex=1)/' \
  -e 's/bus=xhci\.0)/bus=xhci.0,bootindex=1)/' \
  "$IMAGE/run-qemu.sh"
QEMU_DISK_BUS=usb "$IMAGE/run-qemu.sh"
```

The edit preserves the original launcher as `run-qemu.sh.before-bootindex`.
It does not rebuild or edit `disk.img`, remove firmware variables, or change
the guest's persistent state. New launchers include this setting directly.

For an SSH-only build host, `QEMU_DISPLAY=vnc=127.0.0.1:1` exposes the local
screen through VNC on the host loopback interface (use an SSH tunnel).
`QEMU_DISPLAY=none` is for automated boot probes, not interactive local login.

Inside Mojt, check Bash login, terminal dimensions (`stty size`), keyboard
editing, and then:

```sh
mojt-system-check boot
systemctl status mojt-hardware.service --no-pager
uname -r
lsmod
findmnt /lib/modules
findmnt /lib/firmware
mojt-system-check admin
mojt-system-check network
mpm ports install hello -y
hello
printf 'USB boot persistence\n' >/etc/mojt-usb-note
systemctl poweroff
```

Restart with USB storage and confirm `/etc/mojt-usb-note`, installed Ports
and Bash history remain. QEMU uses an emulated `e1000e` network device.
It cannot validate the ThinkPad display, physical keyboard or Intel Wi-Fi.

## 5. Physical USB boot

Use the tested, cleanly shut-down `disk.img`. The image has a fallback
`EFI/BOOT/BOOTX64.EFI` and needs UEFI with **Secure Boot disabled** for this
unsigned development boot chain. No firmware boot entry needs to be installed.

Write the whole image to a spare USB device with a disk-imaging tool, verifying
the device by model, size and serial before writing. This replaces that USB's
contents. No automatic writer or guessed `/dev/sdX` command is supplied here.
Select the USB through the ThinkPad's one-time UEFI boot menu.

The profile has no fstab entries or automounter for internal partitions;
initramfs mounts only the image UUID. Internal disks may appear in `lsblk`
but are not mounted. Do not connect a second copy with the same filesystem
UUID during a boot test.

After local login, repeat the checks above. For Wi-Fi, run:

```sh
nmcli device status
nmcli device wifi list
nmcli --ask device wifi connect 'YOUR_SSID'
# Replace wlp4s0 with the Wi-Fi interface shown by nmcli:
MOJT_TEST_INTERFACE=wlp4s0 mojt-system-check network
```

`--ask` avoids placing the password in command history. NetworkManager stores
the connection under persistent `/etc`. Wired networking can be used instead
if the ThinkPad Ethernet adapter/connector is available. After shutdown/reboot,
check the saved note, network reconnection, Ports and Bash history again.

## Validation status

Regression tests cover cumulative step 6, authenticated tty1 setup, complete
module/firmware staging, license retention, input/symlink safety and exact
System-generation mounts. `tests/run-uefi-smoke.py --hardware-profile
thinkpad-x1-carbon-3 --disk-bus sata|usb` exercises firmware/GRUB, UUID disk
discovery, local kernel console, module/firmware mounts and state persistence
with a synthetic static guest. Its firmware fixture does not drive hardware.
The owner-reported physical checks are recorded below. Repeatable cold/warm
boot and persistence across a physical reboot remain to be reported.

### Agent-side real Debian boot probes (2026-10-25)

The probes passed with Debian Trixie's `linux-image-6.12.107+deb13-amd64`
(`6.12.107-1`), firmware-iwlwifi/firmware-intel-graphics `20250410-2`, and
wireless-regdb `2026.05.30-1~deb13u1`. The actual complete module/firmware trees,
copyright files and signed Debian regulatory-database selection were staged.
Both SATA and xHCI/USB mass-storage probes booted via OVMF/GRUB twice and booted
a disk-only copy with fresh firmware variables. Each run checked the local
kernel console, pinned System, read-only module/firmware mounts and persistent
`/etc`/`/var`. The guest was synthetic/static; Wi-Fi firmware was transferred
and mounted, not exercised on an Intel device.

The runtime used QEMU 8.2.2/TCG, GRUB 2.12, OVMF and BusyBox 1.36.1. Fakeroot
packaged device nodes because the agent environment cannot create real ones.
The probes also exposed optional `crc32c_intel` rejection on QEMU's default
CPU and a BusyBox bind-remount lookup through `/lib -> usr/lib`. The loader
now logs unavailable modules and continues to the mandatory disk/mount
checks; bind remounts name both source and destination. Emergency shells
explicitly reopen the console instead of inheriting the module-list input.

The boot probe also supports `--disk-bus sata --switch-bus usb` to change the
device path between boots while retaining the same disk and firmware variables.
CI includes this transition alongside the separate SATA and USB tests.

### Owner-reported physical acceptance (2026-10-25)

The owner booted the USB image on the ThinkPad X1 Carbon 3rd generation and
supplied a photograph showing local root login, the step 6 hardware profile,
Base 0.1.3, kernel 6.12.107+deb13-amd64, i915 framebuffer output and a started
NetworkManager. The owner then reported that the requested checks worked,
nearby wireless networks were visible and nmcli successfully connected to the
home Wi-Fi network. They ran `mpm ports update`, installed Neovim with
`mpm ports install neovim`, and edited a file with Neovim on the machine.
These are owner-side physical-hardware results, separate from the agent's
synthetic boot probes.

Earlier physical boot attempts showed a black screen followed by reboot
before any visible GRUB menu. Several otherwise identical attempts eventually
booted successfully; no cause or corrective change has been established.
Intermittent pre-GRUB startup therefore remains an open issue. Persistence of
the Wi-Fi connection, installed Ports and files after a physical reboot has
not yet been separately reported.
