<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# First source-built Base boot: owner test procedure

This procedure boots a completed source-built Base with retained System package
inputs and an exact existing Kernel. It creates one new native-v2 VM with one
System generation, using the ordinary bootstrap constructor. It does not build
a Kernel, attach an earlier VM disk, update the host or replace an installation.

This tests the new Base's startup/runtime boundary. It does not yet test a
Base-only transition on an existing writable root or preservation of that
installation's machine state. The new System carries current management code
and new Base-specific deployment metadata; its third-party package inputs come
from the saved export. A subsequent generation-change test is separate.

## Host preparation

Run as the ordinary Debian user in the source-builder checkout. Inputs:

- A completed `mojt-base-build.py` workspace with `result.json`, the release
  archive/manifest and no `INCOMPLETE` marker.
- A previous native-v2 VM's `input-check.json`, produced by its preparer.
- The exact Kernel archive and complete System export referenced by that file.
- The native-image host tools, static BusyBox, QEMU/OVMF and bootstrap's
  mount/chroot/namespace tools. For Debian, the additional packages normally are:

```sh
sudo apt install qemu-system-x86 ovmf busybox-static cpio kmod e2fsprogs fdisk \
  dosfstools mtools grub-common grub-efi-amd64-bin openssl util-linux
```

The saved JSON supplies input locations and expected Kernel/System identities.
It cannot choose the new output, helper code, a disk to overwrite, or a shell
command. The System export record must still match; existing import/bootstrap
checks validate actual archive and provider content.

Set explicit paths. Replace the first path with the input-check file from the
working VM; the directories below are examples, not global registrations:

```sh
TEST=(python3 -I -B tests/prepare-source-base-boot.py
  --from-check /PATH/TO/EXISTING-VM/input-check.json
  --base-build "$HOME/mojt-base-result"
  --output "$HOME/mojt-base-boot-test")
"${TEST[@]}" --check-inputs
```

Input checking reads the release and retained inputs without sudo, output
directories, VM image construction or selection changes. After it passes, run:

```sh
"${TEST[@]}"
```

Preparation packages the new Base, retains the exact Kernel in a private
registry and invokes `mojt_bootstrap.py` once for one new image. It may request
sudo and a new guest root password. It never attaches the saved VM disk. Phase
output from normal bootstrap remains visible. The new workspace's `INCOMPLETE`
marker remains if preparation fails; preserve it and the failure output instead
of deleting/reusing the directory.

## Start and inspect the guest

Start only the newly reported launcher:

```sh
QEMU_DISPLAY=none bash "$HOME/mojt-base-boot-test/image/run-qemu.sh"
```

Log in as root using the password chosen during preparation. Inside **Mojt**:

```sh
cat /usr/lib/os-release
getconf GNU_LIBC_VERSION
uname -r
mpm system status
systemctl --failed --no-pager
```

Expect the built Base version, glibc 2.44, the same Kernel release named in the
saved input check and System `system-source-base-test`. Running and next boot
must agree. There should be no failed units.

Exercise the Base/System runtime boundary:

```sh
printf 'abc\n' | grep -P 'a.c'
LC_ALL=C.UTF-8 locale charmap
python3 -I -B -c 'import pwd,socket,locale; print(pwd.getpwnam("root").pw_uid); print(socket.getaddrinfo("localhost", None)); print(locale.setlocale(locale.LC_ALL, "C.UTF-8"))'
curl -I https://cache.nixos.org
```

PCRE grep, UTF-8, root/localhost lookup and HTTPS should work. A network failure
alone needs diagnosis; it does not automatically establish a libc problem.
Record the actual output and distinguish local tests, this guest boot and any
later physical-machine or generation-transition test. No successful guest boot
is claimed merely by publishing this procedure.

The subsequent [source Base switch and return test](source-base-transition-test.md)
uses a copy of this working VM and a marked successor of the same source Base.
It does not require a Void-built installation.
