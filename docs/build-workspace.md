<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Full image build on Mojt: private workspace

The tested tool environment lives in the retained selector VM. Shut that VM down
and use `tools/mojt-build-workspace.py` on the Debian host to create a separate
VM copy plus an input-populated raw ext4 workspace. The source VM must remain
stopped until copying completes. QEMU image locking rejects an active source
writer; force-share is never used. Existing output paths are refused. Failed
preparation retains only its new incomplete output for inspection.

The host tool requires sudo, git, cp, qemu-img, mkfs.ext4 and e2fsck. It copies the
selected Base generation, release metadata and directory target state under the
installer's shared lock, the existing exported System payload, and matching
kernel/modules. It archives a clean source checkout's exact HEAD, excluding Git
administration files. It does not snapshot the running guest filesystem as a
System payload. Input file contents, modes and link targets are frozen into
inputs.json; symlinks are recorded without following external targets. Unexpected
special files stop preparation. Do not update the source payload during copying.

Example host command (substitute existing private paths):

```sh
sudo python3 tools/mojt-build-workspace.py \
  --source /PINNED/CHECKOUT --vm /STOPPED/VM \
  --target /OFFLINE/BASE-TARGET --payload /EXPORTED/SYSTEM-PAYLOAD \
  --kernel /INPUTS/boot/vmlinuz-RELEASE \
  --modules /INPUTS/usr/lib/modules/RELEASE \
  --base 0.1.3 --output /NEW/WORKSPACE
```

The output has vm/disk.img (private copy of the prepared machine),
vm/workspace.img (64 GiB sparse ext4, label MOJT-BUILD and a fresh UUID), a
patched vm/run-qemu.sh with an extra VirtIO workspace drive and 4 GiB RAM, plus
an independent inputs.json and retained staging tree. Root filesystem, prepared
Nix tools/roots and user state remain intact in the VM copy. The source image
and launcher are not changed. Only regular image files in the new output are
formatted, never host devices. The invoking sudo user's ownership is restored
for the VM files, allowing normal unprivileged QEMU launch.

Inside Mojt identify the extra filesystem using its printed UUID, then mount it
at /var/lib/mojt/build-work. Device names are not assumed: the existing boot disk
can be SATA while the workspace is VirtIO. For the example below W is that mount:

```sh
ENV=/var/lib/mojt/build-preview.L3UspR/environment
W=/var/lib/mojt/build-work
"$ENV/run" python3 -I -B "$W/inputs/source/tools/mojt-build-workspace.py" --verify "$W"
```

This comparison is read-only and detects input content, mode or link changes.
Run builder Python with -B so imports do not add bytecode caches to frozen source.
The target's installer lock is used by the builder; frozen input data is not
migrated. Do not create the output beneath inputs/. Native build uses:

```sh
"$ENV/run" python3 -I -B "$W/inputs/source/tools/mojt-vm-build.py" \
  --target "$W/inputs/base-target" --system-payload "$W/inputs/system-payload" \
  --kernel "$W/inputs/kernel/vmlinuz-RELEASE" \
  --modules-dir "$W/inputs/kernel/lib/modules/RELEASE" \
  --busybox /RECORDED/STATIC-BUSYBOX/bin/busybox \
  --base-generation 0.1.3 --system-generation system-selfbuild-A \
  --boot-mode uefi --login-mode password --root-shell /run/mojt-system/bin/bash \
  --disk-size-mib 8192 --output "$W/output/image"
```

The new guest root password may be requested on the terminal. The command should
be launched directly, preserving terminal input. Use the actual recorded static
BusyBox path from environment.json. This is a serial-only build, without the
physical-hardware firmware profile. It uses the original Debian kernel/module
pair. Newly built kernel compilation remains later work.

After successful assembly, check its System manifest and frozen input inventory,
cleanly stop the build VM, copy out the result from the private workspace, and
boot that result on Debian. Do not mount workspace.img on the host while QEMU
writes to it. A host read-only loop mount of this new regular ext4 image after
shutdown can be used for result transfer. The source/reference VM remains kept.

Targeted automation covers launcher shape/RAM/extra-drive changes, exact input
inventory and tampering detection, symlink handling, existing-output refusal,
source preservation and a simulated active-source conversion failure. Actual
native full-image build and result boot remain owner-run acceptance. No repeated
network/account/A/B/A test is required for workspace preparation.


## Owner full image build and result boot (2026-10-27)

The owner copied the retained tool VM and used a separate 64-GiB workspace with
4 GiB RAM. Frozen inputs were the reviewed builder source, Base 0.1.3, the
existing step-10 System payload and Debian kernel/modules 6.12.107+deb13-amd64.
File bytes, modes and symlink targets matched their frozen inventory before and
after complete image assembly inside Mojt.

The builder reported one UEFI boot pair, System system-selfbuild-A and 10 early
modules. The resulting image was then booted on the Debian host. The supplied
authenticated root console reported system-selfbuild-A, Base VERSION_ID=0.1.3,
kernel 6.12.107+deb13-amd64 and ttyS0. The systemctl --failed listing was empty.

This establishes complete owner-run image assembly on Mojt from frozen prebuilt
inputs followed by successful result boot and root login. Copy/byte-comparison
commands were supplied for transfer, but their separate hash output was not
pasted; no measured disk hash is claimed here. Machine-specific paths, workspace
identifiers and detailed local reports remain private.

This does not establish source compilation of System packages or a kernel,
in-place System updates, bit-for-bit reproducible images or general libc/ABI
compatibility. Earlier native-tool loader and DNS/TLS checks remain the bounded
libc evidence. No repeated account/network/A/B/A acceptance was requested for
this result boot. Retain the reference VM and successful result locally.
