<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# First Mojt VM — experimental direct-kernel boot

This is a **host-side QEMU/KVM prototype**, not a bootable installer, not a
signed System release and not a permanent kernel package format. It reuses
an installed Mojt Base and matching host-supplied Linux kernel/modules.

The builder makes **copies** of the selected installed Base and persistent
`state/etc` and `state/var` into a standalone ext4 disk file. Existing
releases and target installations are not changed. The output directory
must not exist. The VM changes **its own copied state**, not the source.

## Host requirements

- Debian/compatible x86-64 Linux host, Python 3.11+ and root for image creation
- A host `/boot/vmlinuz-KREL` with matching `/lib/modules/KREL`
- `sudo apt install busybox-static cpio kmod e2fsprogs zstd`
- GNU `cp`, `qemu-system-x86_64`, preferably `/dev/kvm`
- An existing Mojt installation containing a completed Base generation and
  persistent state, such as `$HOME/mojt-lab/root-test-013`

Check that the BusyBox applets `sh mount insmod readlink sleep switch_root`
are provided by the statically linked binary. A dynamic BusyBox is rejected.
The first initramfs supports **virtio-blk + ext4** and a single raw disk.
Kernel modules used for those components are resolved with host `modprobe`,
decompressed if needed and inserted in dependency order. Other hardware,
filesystems, root encryption and System services are unsupported for now.

## Build a new VM image

From the Mojt Git checkout:

```sh
cd ~/src/mojt-linux
KREL="$(uname -r)"
test -f "/boot/vmlinuz-$KREL"
test -d "/lib/modules/$KREL"

TARGET="$HOME/mojt-lab/root-test-013"
VM="$HOME/mojt-lab/vm/first-$(date +%Y%m%d-%H%M%S)"

sudo python3 tools/mojt-vm-build.py \
  --target "$TARGET" \
  --kernel "/boot/vmlinuz-$KREL" \
  --output "$VM"
```

If the running kernel has no matching image/modules installed, select an
installed pair explicitly instead of using `uname -r`. The builder refuses
to overwrite an existing output. `VM` is the path of the new directory,
not of the disk file. Copying persistent state includes private machine
configuration; the VM directory is restricted to the invoking user.

The result contains:

```text
VM/
  vmlinuz
  initramfs.cpio.gz
  disk.img                 # raw ext4, no partitions
  run-qemu.sh
  build.json
```

## Boot

```sh
"$VM/run-qemu.sh"
```

The launcher uses QEMU's `-kernel` and `-initrd` options instead of GRUB
or UEFI, VirtIO for the raw ext4 disk, and `console=ttyS0` with
`-serial mon:stdio`. QEMU tries KVM first and falls back to TCG. Exit the
monitor with `Ctrl-A X`. Do not start two simultaneous VMs that write the
same `disk.img` file.

The initramfs should print:

```text
Mojt Linux - early boot
Selected Base: 0.1.3
Switching to Mojt Base...
```

Once in Mojt, verify `cat /etc/os-release`, `id`, `uname -a` and
`cat /proc/mounts`. The Base intentionally lacks `mount`; the early
initramfs handled mounts. The console is `/bin/sh` as PID 1, not a service
manager; leaving it may trigger a kernel panic (expected for this demo).

### What this experiment does not establish

- No bootloader/UEFI, disk partitioning or installed kernel on the guest disk
- No permanent kernel packaging, System dependency resolver or GNOME policy
- No unattended shutdown/reboot, networking, login manager or persistent logs
- No guest-side verification of release signatures or runtime rootfs integrity
- No real-machine, power-failure or multiple-release boot switching tests

The kernel release and modules must match exactly. Errors in module loading
or mounting result in an early BusyBox shell for diagnosis; share the serial
log if that happens.

## Regression tests

```sh
python3 -m unittest discover -s tests -p 'test_vm_builder.py' -v
```

These are builder/unit tests, **not** a QEMU boot acceptance test. The final
VM must be booted and checked on a host with a suitable kernel and KVM/QEMU.
