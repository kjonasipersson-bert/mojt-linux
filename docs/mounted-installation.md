<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Installer media and mounted bootstrap

Mojt uses a raw disk image for installation media. The whole-disk installer
prepares the confirmed target and delegates content installation to the same
native-v2 bootstrap used for explicitly mounted target partitions.

## Whole-disk installation

The UEFI installation image boots to a password-free local root console. Run

```sh
mbt install
```

This lists unused writable disks and asks for a disk, an optional swap size in
GiB and exact disk-path confirmation before erasing it. The installer creates
GPT, a 128 MiB FAT32 ESP, optional partition-backed swap, and single-device Btrfs
on the rest of the disk. The selected Kernel must supply Btrfs and the profile's
early storage drivers. Choose a new root password for the target. Swap is configured
with a persistent systemd unit using its GPT partition UUID. The keyboard
layout stays that of the installation console. The installed system retains
the ordinary native-v2 layout, with writable state and read-only release content.

Linux sets the installation disk and its root partition read-only before
mounting the root filesystem and skips filesystem journal replay. The ESP
stays unmounted in Linux. The live root, `/etc`, `/var`, `/tmp` and
`/run` use RAM. The input kit stays on the medium at a read-only mount under
`/var`. Logs and network changes disappear after shutdown. The large
installation workspace lives on the confirmed target disk.

## Prepared partition installation

- x86-64 UEFI; the existing ThinkPad X1 Carbon 3 local-console USB/SATA profile,
  or the serial VirtIO profile for the focused VM installation test.
- Already partitioned/formatted GPT disk: one ext4 or Btrfs root partition and one FAT32
  EFI System Partition, mounted at **separate, nonnested** root-owned mountpoints.
- Btrfs requires `--root-fs btrfs`, a single-device filesystem and a mount of its top-level subvolume.
- Fresh empty filesystems; root may contain only an empty `lost+found`. An existing
  `EFI` directory is refused, even if empty. Shared ESPs and existing installations
  are outside this first increment.
- Both partitions belong to the same disk. Alias/child mounts, another mounted
  partition on that disk, active swap there, wrong partition types, mismatched
  device/filesystem identities and a root UUID duplicated on another device fail
  inspection. The target cannot be the running installation's disk.
- Target transport must match the selected early-boot profile. VirtIO block is
  supported for the VM. The ThinkPad profile adds AHCI SATA and USB storage/UAS.
  The generic PC profile also supports NVMe and VirtIO SCSI. Encrypted roots
  and logical volumes are outside the supported target layout.

`mbt bootstrap` accepts explicitly prepared partitions. The separate
`mbt install` command can partition and format the confirmed whole disk. Device preparation and the choice to erase a disk happen as a
separate explicit operation after identifying its model/serial/capacity. Root
privileges are needed even for the mounted preview, which reads block metadata.

## Prepare a self-contained installer image

Build manually from exact reviewed Base and Kernel artifacts, Base compatibility
evidence, an exported System payload, and static BusyBox. This example produces
a serial VirtIO image. For a physical USB installer, select the tested target
hardware profile and supply its firmware inputs. Use a Btrfs-capable Kernel
even when the installer image itself uses ext4. Export System step 12 with
the offline tools from the pinned Nix source. Run this command in the Nix
build environment as an ordinary user.

```sh
python3 tools/mojt-system-prepare.py --step 12 --with-installer-tools \
  --output SYSTEM_EXPORT -y
```

```sh
sudo ./tools/mbt bootstrap \
  --base-package BASE_ARCHIVE --base-artifact BASE_ID --base-context BASE_CONTEXT \
  --kernel-registry KERNEL_REGISTRY --kernel-artifact KERNEL_ID \
  --system-payload SYSTEM_EXPORT --system-generation system-installer \
  --with-build-tools --with-installer-inputs \
  --root-fs ext4 --disk-size-mib 8192 --output INSTALLER_DIR
```

Substitute full artifact IDs and paths. For a general x86-64 PC USB installer,
add `--hardware-profile pc-x86_64 --firmware-root FIRMWARE_DIR` with the full
firmware inputs for that profile. Size the raw image
for the embedded inputs and installer tools. The USB device must
have at least the image's logical capacity. The mounted bootstrap assembles
the installation in a private directory on the confirmed target disk.
That disk needs space for both the staging inputs and the installed tree.
The output directory must be new. A fresh image built with `--with-installer-inputs`
opens a root shell on its console, with the root password locked. A mounted
target still prompts for its own root password.

`--with-installer-inputs` carries a closed data directory at
`/var/lib/mojt/installer-inputs` in the live session. Its versioned `inputs.json`
binds the Base archive/context, exact installed Kernel registry, System export,
static BusyBox, optional firmware/licenses and reviewed bootstrap defaults.
Each resource has a transfer digest; the descriptor has a content identity.
System-export symlinks are inventoried and copied literally as guest data;
they are never resolved against the builder host. Creating/reading the kit
does not require a host `/nix` or Nix installation. The existing System reader
retains its guest-path validation when consuming the export.
The kit includes neither a source checkout nor the installer machine's account
state or passwords. Hashes are integrity evidence, not publisher authentication.
The System export is deliberately retained as a bootstrap input; this is not
a new native System package format or generalized repository protocol.

The optional kit is copied from the same private frozen inputs that bootstrap
uses. Ordinary builder images do not gain this copy unless explicitly requested.
The installed MBT reads only fixed data fields from `--inputs DIRECTORY`, checks
the closed resources and expands them into its existing exact input options.
Mixing the kit with competing Base/Kernel/provider/firmware input flags is refused.
System label/version/revision can be chosen explicitly for the new installation.
No code, shell commands or hooks are loaded from the kit. Its source identity is
retained in the mounted installation receipt.

The completed `INSTALLER_DIR/disk.img` already carries the installation tools
and can be copied as `install.img` or attached directly as a raw boot disk.
For USB, identify the intended whole USB device by model, capacity, and
serial number, unmount its partitions, and use a disk-image writer to write
the image. The installation can run offline on the first boot.

## Preview the mounted target

After the separately reviewed SSD preparation, mount root at `/run/mojt-target-root`
and the ESP at `/run/mojt-target-esp` (example mountpoints). Mount them writable
and root-controlled, with suitable root UID/GID and masks for FAT32. For Btrfs,
mount the top-level subvolume with `subvolid=5` and add `--root-fs btrfs` to
both commands below. The examples use the default ext4 target filesystem.
At the installer console, use the bundled MBT and disk tools.

```sh
mbt bootstrap \
  --inputs /var/lib/mojt/installer-inputs \
  --target-root /run/mojt-target-root --efi-directory /run/mojt-target-esp \
  --system-generation system-ssd-A --dry-run
```

This reports `mojt-mounted-bootstrap-preview-v1`, exact source identities and the
actual device/GPT/mount/UUID bindings. `target_written=false` means no target
content or EFI selection was written. Temporary execution resources and the
privileged namespace probe remain distinct from target writes. Inspect the
reported whole disk and both partitions before proceeding.

For the actual invocation, replace the following uppercase placeholders with
`target.root.uuid` and `target.efi.partuuid` from that preview:

```sh
mbt bootstrap \
  --inputs /var/lib/mojt/installer-inputs \
  --target-root /run/mojt-target-root --efi-directory /run/mojt-target-esp \
  --expected-root-uuid ROOT_UUID --expected-efi-partuuid ESP_PARTUUID \
  --system-generation system-ssd-A
```

The expected identities bind the reviewed target and are mandatory for writes.
They are rechecked after construction and during publication. Keep the terminal
attached for the **new installation's** root password. Existing USB credentials
and machine identity are not copied. No automatic reboot occurs.

## Construction and publication

The common constructor finishes in a root-controlled private directory on
the already confirmed root filesystem. It
uses the **target's existing UUID**, creates the same MPM installation/retention,
initramfs, boot-Base and native-v2 selection, and builds the same standalone GRUB
loader used for images. It never formats the mounted destination or constructs
an intermediate disk image. The target root is an installation store containing
artifacts, realizations, provider content, boot records and `state`; it is not a
traditional root for `chroot /run/mojt-target-root`.

MBT holds cooperating locks on the disk/partition devices and open mountpoint
descriptors. It binds the opened mountpoint by Linux mount ID and verifies
the partition identity separately, including the single Btrfs backing device.
After rechecking target identity and entries, it writes
`.mojt-bootstrap-incomplete`, moves the completed entries into place on the
same filesystem and verifies the installed native-v2 proofs and selection.
The root filesystem is flushed before the fallback EFI directory is
published. The loader is staged/flushed privately on the ESP, then its `EFI`
directory is renamed into place and the ESP is flushed.

No UEFI NVRAM entry or unrelated bootloader is changed. The initial entry is
`EFI/BOOT/BOOTX64.EFI`, bound to the target UUID and the installed MPM boot menu.
Use the machine's one-time UEFI menu with Secure Boot disabled for this unsigned
development chain. A named internal-disk NVRAM entry can be a later operation.

This is a fresh-target installation with an EFI publication boundary, not an
atomic replacement of an entire disk. Failure after the incomplete marker was created retains any published target
data and that marker. The fallback loader is published only after verification.
A failed construction before the marker normally removes its private workspace.
The target is then nonempty and cannot be adopted/resumed by another invocation.
Inspect it before separately authorized cleanup; no automatic deletion occurs.
Failure after EFI publication is explicitly `PublicationUncertain`: the target
may already be bootable and is retained. Never retry it as a fresh target.

Success retains `/var/lib/mojt/mounted-install.json` in the new installation
and, for a public MBT execution, its builder runtime receipt. These describe the
initial construction, not current boot authority; MPM's boot records remain
authoritative after updates. Mounted target ownership is never handed to a sudo
caller. Default installation verification remains enabled; normal boot still
does not scan complete payloads.

## Acceptance and diagnostics

Use the [offline two-disk VM procedure](reports/installer-test.md) before testing
an installer change on physical hardware. In a failed install, retain the last
installer output and the target image. Check the incomplete marker and whether
the fallback EFI file was published before planning a retry. Physical install
and boot coverage is tracked in the [roadmap](roadmap.md).
