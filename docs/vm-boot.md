<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# First Mojt VM — experimental direct-kernel boot

This is a **host-side QEMU/KVM prototype**, not a bootable installer, not a
signed System release and not a permanent kernel package format. It reuses
an installed Mojt Base and matching host-supplied Linux kernel/modules.

This guide describes the earlier BusyBox-init mode, which remains available
without `--system-payload`. The current
[System VM experiment](system-nix-vm.md) adds systemd, networking and MPM/Nix;
its three initial acceptance steps have passed inside Mojt.

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
initramfs handled mounts. The experimental System layer now supplies **BusyBox init as PID 1**.
A shell is respawned on `ttyS0`; exiting the shell should return to a new
prompt instead of killing PID 1. This is explicitly **not** a decision to
use BusyBox as Mojt's production init. It is an isolated VM/rescue-style
boot implementation. The separate static BusyBox and default `inittab`
live under `system/prototype-init` in the guest image; the runtime binary
is bind-mounted into `/run/mojt-system` before `switch_root`. The guest
`/etc/inittab` lives in persistent state. An existing inittab is preserved.

To request a graceful shutdown from the VM console:

```sh
/run/mojt-system/busybox poweroff
```

BusyBox init runs its shutdown action (sync) and powers off the guest. This
is still a first-stage prototype, **not** yet a validated clean unmount and
restart/shutdown service manager. Check the serial console and rerun the
persistence test rather than assuming that all writes are durable.

The VM has an **unauthenticated root console** by default and must not
be exposed to untrusted users, networking or remote consoles. The opt-in
`--login-mode password` described below enables local serial-console login.
A root entry with `x` in `/etc/passwd` but no `/etc/shadow` is still
diagnosed, never silently repaired in development mode.

### What this experiment does not establish

- No bootloader/UEFI, disk partitioning or installed kernel on the guest disk
- No permanent kernel packaging, System dependency resolver or GNOME policy
- No production-grade service supervision, networking, login manager or persistent logs
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

## Experimental authenticated serial login (opt-in)

This is a **System** prototype, not a permanent BusyBox-based init or
production credential manager. Build a **new** VM image from the same
installed Base, this time adding `--login-mode password`:

```sh
cd ~/src/mojt-linux
KREL="$(uname -r)"
TARGET="$HOME/mojt-lab/root-test-013"
VM="$HOME/mojt-lab/vm/login-$(date +%Y%m%d-%H%M%S)"

sudo python3 tools/mojt-vm-build.py \
  --target "$TARGET" \
  --kernel "/boot/vmlinuz-$KREL" \
  --output "$VM" \
  --login-mode password

"$VM/run-qemu.sh"
```

The builder checks that the **static** BusyBox has `getty`, `login`
and `passwd` applets. It installs the prototype tools under
`system/prototype-init` and adds an authenticated `ttyS0` getty to the
VM copy of persistent `/etc/inittab`. The login program is supplied by
System, **not** Base. Existing nonmatching inittab files are rejected
rather than silently keeping an unauthenticated root shell.

If `/etc/shadow` is absent in the copied state, the builder prompts
twice for a new root password on the **host terminal**, uses the host's
OpenSSL SHA512-crypt implementation to produce a salted hash, and
creates `shadow` and, when missing, `gshadow` with restrictive modes.
Other copied accounts are password-locked by default. It does **not**
copy Debian's credentials, write the password into the process
arguments, or mutate the source Mojt installation. No password or hash
goes into `build.json` or Git. The output disk contains password hashes
and other machine state; keep the VM directory private.

If a shadow file already exists, the builder preserves it instead of
resetting the password. A locked or otherwise unusable root entry is
an error requiring explicit account repair. An existing `securetty`
that does not allow `ttyS0` is preserved and rejected. A missing file
is initialized for the local VM serial console.

### Root shell compatibility check

The copied `/etc/passwd` may name `/bin/bash` (from the Void bootstrap),
but Mojt Base 0.1.3 only guarantees `/bin/sh`. An authenticated login
can accept the password and **still fail to launch a shell**. The builder
therefore validates that the root account's shell is executable **inside
the selected Base** before asking for any password.

If the copied account specifies a missing shell, image construction stops
with a diagnostic instead of generating a broken login VM. To explicitly
select the available shell **only in the new VM's copied `/etc/passwd`**,
add the argument below to the builder command:

```sh
  --root-shell /bin/sh
```

For example, use `--login-mode password --root-shell /bin/sh` together.
This does not rewrite the source installation's `state/etc/passwd`, the
Base image, or any old VM disk. Other account records remain unchanged.
No root shell is substituted silently. When provisioning an installed
system later, this check will belong to the proper installation process.

The `Void` banner and `(none)` hostname may still appear: the existing
persistent `/etc/issue` and unset kernel hostname are separate from
authentication. This prototype deliberately preserves the existing
machine configuration rather than silently overwriting it. We can add
System-owned branding and hostname defaults in a later change.

On QEMU's serial console you should see a login prompt. Enter
`root` and the password you configured. Test that an incorrect password
does **not** grant a root shell, then test the correct password.
A first boot is only successful if both cases work. After login:

```sh
id
cat /etc/os-release
ls -l /etc/shadow
/run/mojt-system/busybox poweroff
```

To change the password from inside this experimental VM, BusyBox
provides `/run/mojt-system/busybox passwd root` (subject to the chosen
BusyBox build's password backend).

**Security limits:** This is a trusted, local serial-console experiment.
No network login is configured, no PAM stack or multiuser provisioning
is implemented, and the early initramfs has a recovery shell on failures.
Do not treat the VM as a hardened or remotely accessible installation.
BusyBox's compiled shadow-password support is not proven by its applet
list; successful and unsuccessful login must be tested on the actual
Debian/KVM host before merging.

The earlier `development` mode (the default for compatibility) still
deliberately gives an **unauthenticated root shell**. Never interpret
merely setting a root password in `shadow` as closing this bypass.

## System and Base identity at boot

The VM now has an **experimental System version `0.1`** independent of
the selected Base version. Its `system/prototype-init/version` metadata is
written by the VM image builder; `assembled-at-utc` records the **VM
assembly date**, not a formally published/reproducible System release date.
The latter will belong to a future proper System release format.

Early boot combines:

- `system/prototype-init/version` (System `0.1`)
- `base/current` (for example, Base `0.1.3`)
- `system/prototype-init/assembled-at-utc` (UTC build timestamp)
- `/proc/sys/kernel/osrelease` (actual booted kernel)
- `state/etc/hostname` (machine-local hostname)

It writes the following **runtime** files, regenerating them at each boot:

```text
/run/mojt/issue
/run/mojt/motd
```

In password mode, System's BusyBox `getty` uses
`-f /run/mojt/issue` rather than the persistent `/etc/issue`, allowing
the old Void-derived local configuration to remain unchanged.

For a VM with System `0.1` and Base `0.1.3`, the login banner is:

```text
Mojt Linux 0.1/0.1.3 (x86_64)

mojt login:
```

The generated MOTD contains separate System and Base versions, the UTC
image assembly time, and the actual kernel version. A machine with no
existing `/etc/motd` receives **only in the copied VM state** a symlink
to `/run/mojt/motd`, so BusyBox login displays it after authentication.
If an administrator already has an `/etc/motd` (including an inherited
Void file), that local file is **not replaced or shadowed**. In that case,
the generated message remains available for inspection with:

```sh
cat /run/mojt/motd
```

A missing `state/etc/hostname` is initialized to `mojt` **only in the
new VM image's copied state**. Existing valid hostnames are preserved.
The kernel hostname is set early on each boot; no change is made to the
Debian host's UTS namespace. Invalid hostname entries are rejected during
image creation rather than overwritten.

Separately, when packing **new Base releases**, `mojt-base-pack`
replaces the Void-sourced `/usr/etc/issue` default with
`Mojt Linux Base <version>`. This remains meaningful for a Base-only
container without the System layer. Old Base releases are immutable and
are **not** repacked or modified by this VM work. The Base fallback text
does not include a System version.

This prototype deliberately does not implement a full System release
manager, timestamp signing, local MOTD merge policy, or a bootloader.
