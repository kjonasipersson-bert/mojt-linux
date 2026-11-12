<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# USB startup, then installation to prepared SSD partitions

The first native-v2 mounted installer reuses the existing fresh bootstrap:
exact Base/Kernel inputs and the frozen System payload are assembled privately,
installed through MPM, and admitted/selected through the same boot APIs. The
completed filesystem can be packed into an image or copied to explicitly mounted
target partitions. MPM's installed/selected/running model and update commands are
unchanged. There is no public planning verb, package hook or second package database.

The physical sequence is USB boot, SSD installation, SSD boot, then ordinary
MPM/MBT timings and compilation on SSD. USB is the startup/installation medium;
no heavy physical compiler or rollback matrix is required on it.

## Bounded initial target

- x86-64 UEFI; the existing ThinkPad X1 Carbon 3 local-console USB/SATA profile,
  or the serial VirtIO profile for the focused VM installation test.
- Already partitioned/formatted GPT disk: one ext4 root partition and one FAT32
  EFI System Partition, mounted at **separate, nonnested** root-owned mountpoints.
- Fresh empty filesystems; root may contain only an empty `lost+found`. An existing
  `EFI` directory is refused, even if empty. Shared ESPs and existing installations
  are outside this first increment.
- Both partitions belong to the same disk. Alias/child mounts, another mounted
  partition on that disk, active swap there, wrong partition types, mismatched
  device/filesystem identities and a root UUID duplicated on another device fail
  inspection. The target cannot be the running installation's disk.
- Target transport must match the selected early-boot profile. VirtIO block is
  supported for the VM; the hardware profile also supports AHCI SATA and USB
  storage/UAS. Internal NVMe, encrypted roots and logical volumes require a
  supported subsequent profile; they are not silently accepted.

MBT never partitions, formats, resizes, selects an arbitrary disk or writes its
partition table. Device preparation and the choice to erase a disk happen as a
separate explicit operation after identifying its model/serial/capacity. Root
privileges are needed even for the mounted preview, which reads block metadata.

## Prepare a self-contained installer image

Build the supported USB image with the already reviewed exact bootstrap inputs
and add `--with-build-tools --with-installer-inputs`. For a nominal 32-GB medium,
use `--disk-size-mib 24576` and inspect its actual capacity before a separate image
write. Retain the accepted original VM and its build outputs.

`--with-installer-inputs` carries a closed data directory at
`/var/lib/mojt/installer-inputs` in persistent state. Its versioned `inputs.json`
binds the Base archive/context, exact installed Kernel registry, System export,
static BusyBox, optional firmware/licenses and reviewed bootstrap defaults.
Each resource has a transfer digest; the descriptor has a content identity.
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

Before taking the USB to the physical machine, boot its VM once and prepare the
private **image** tool environment as root (not a compiler environment):

```sh
umask 022
mbt env --profile image --source-manifest /run/mojt-system/ports.toml \
  --output /var/lib/mojt/installer-tools -y
```

This supplies the existing image tools plus `blkid`, including host chroot/mount,
copy/sync and GRUB. The environment and its retained provider closure travel
with the USB. The actual SSD installation can then run offline from its carried
inputs. Shut the VM down cleanly before copying/writing its image. Do not move
the private tool environment to a different guest path.

## Preview the mounted target

After the separately reviewed SSD preparation, mount root at `/mnt/mojt-root`
and the ESP at `/mnt/mojt-esp` (example mountpoints). Mount them writable and
root-controlled; for FAT, use suitable root UID/GID and masks. Neither filesystem
is formatted by the following commands. As root, use installed MBT through the
private installation environment:

```sh
/var/lib/mojt/installer-tools/run /run/mojt-system/bin/mbt bootstrap \
  --inputs /var/lib/mojt/installer-inputs \
  --target-root /mnt/mojt-root --efi-directory /mnt/mojt-esp \
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
/var/lib/mojt/installer-tools/run /run/mojt-system/bin/mbt bootstrap \
  --inputs /var/lib/mojt/installer-inputs \
  --target-root /mnt/mojt-root --efi-directory /mnt/mojt-esp \
  --expected-root-uuid ROOT_UUID --expected-efi-partuuid ESP_PARTUUID \
  --system-generation system-ssd-A
```

The expected identities bind the reviewed target and are mandatory for writes.
They are rechecked after construction and during publication. Keep the terminal
attached for the **new installation's** root password. Existing USB credentials
and machine identity are not copied. No automatic reboot occurs.

## Construction and publication

The common constructor finishes in a root-controlled private directory. It
uses the **target's existing UUID**, creates the same MPM installation/retention,
initramfs, boot-Base and native-v2 selection, and builds the same standalone GRUB
loader used for images. It never formats the mounted destination or constructs
an intermediate disk image. The target root is an installation store containing
artifacts, realizations, provider content, boot records and `state`; it is not a
traditional root for `chroot /mnt/mojt-root`.

MBT holds cooperating locks on the disk/partition devices and open mountpoint
descriptors. After rechecking target identity/emptiness/capacity, it writes
`.mojt-bootstrap-incomplete`, copies the completed tree preserving ownership,
modes, links and special files, then verifies the copied native-v2 proofs and
selection. The root filesystem is flushed before the fallback EFI directory is
published. The loader is staged/flushed privately on the ESP, then its `EFI`
directory is renamed into place and the ESP is flushed.

No UEFI NVRAM entry or unrelated bootloader is changed. The initial entry is
`EFI/BOOT/BOOTX64.EFI`, bound to the target UUID and the installed MPM boot menu.
Use the machine's one-time UEFI menu with Secure Boot disabled for this unsigned
development chain. A named internal-disk NVRAM entry can be a later operation.

This is a fresh-target installation with an EFI publication boundary, not an
atomic replacement of an entire disk. Failure before publication retains partial
target data and its incomplete marker with no newly published fallback loader.
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

## Focused validation and next owner test

Tests exercise fixed input-data expansion/corruption refusal, mount/device guards,
copy/verification failures, target flush ordering and the late-publication case.
The joined root/archive fixture reuses the common hardware constructor and MPM
proofs, copies a real fixture tree, checks the copied selection and portable input
data, and proves the image writer/handoff is not used. Kernel/block metadata,
firmware/ELF bytes, provider execution and the EFI binary are fixture boundaries;
this is not a real installed-disk boot result.

Before physical use, run **one focused VM installation**: installer USB image plus
one disposable prepared target disk; preview, install, shut down, then boot with
only the target disk attached. Check its own root UUID, native-v2 selected/running
agreement, local login/network and no failed units. There is no need to repeat
the old Kernel/Base/System A/B/A matrix. Actual hardware installation/boot remains
a separate owner result. After SSD boot, use the [lightweight timing guide](physical-performance.md)
for first/repeated commands and a fresh compiler build on SSD.
