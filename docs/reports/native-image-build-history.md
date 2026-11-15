<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native image boot and module acceptance

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

Focused owner acceptance reuses the already built/installed Kernel, wraps
the unchanged Base release and exports no new System packages. Preview, build one
new disk, boot it once, and check:

- Running release and recorded full Kernel artifact match the intended inputs.
- `/lib/modules` is read-only and sourced from the exact native registry object;
  module filenames/vermagic match the running Kernel and the active network
  driver is identified (its own version field need not be the Kernel release).
- The generated deployment records name the intended Base/System, no systemd
  units failed, and the existing network/HTTPS path works.

No repeated account or A/B/A test is needed for this fresh-image integration.
The first owner boot found a BusyBox remount lookup failure with Base's
`/lib -> usr/lib` layout. The native module remount now supplies both source and
target explicitly, bypassing a literal-path lookup in `/proc/mounts` while
retaining read-only protection. Focused BusyBox tests cover argument handling
and, where mount namespaces are available, read-only behavior through that link.
The automated tests use real native tar/zstd packages, audited Base installation,
System fixture assembly and actual cpio serialization/independent inspection,
but synthetic guest programs/disk output and simulated initramfs device creation.
Character-device header validation has a separate fixture. CI protects the new
boundaries; the owner's separate full-Mojt result below supplies focused runtime
evidence for this image.

The standalone planner still reports `boot_ready: false`: successful assembly is
not general hardware/firmware, Secure Boot, libc/desktop ABI, power-cut recovery
or publisher authentication evidence. Retain the accepted reference images for
recovery and comparison. Production acquisition, policy tracking,
transactional activation/rollback and durable existing-disk updates remain future
work. The new image does not modify the running Kernel/Base/System/Ports state.

## Owner native image acceptance: 2026-10-30

The owner built and booted a corrected fresh serial UEFI image on the Debian
host using functional revision `fa1289d56009aac0a00ef00e17d45a57a5661f85`.
The original Base 0.1.3 release was wrapped without rebuilding it; the previously
installed Kernel and exported step-10 System payload were reused. No Kernel
recompilation or new System package export was required.

| Input | Accepted identity |
| --- | --- |
| Base | Original release `0.1.3`, native package `0.1.3-r1`, `sha256:4718c046420a2901ed8fd6bc52cac012de1bcfab8e47c15431eaa4b015e9f6f3` |
| Kernel | Native package `6.12.107-r1`, running release `6.12.107-mojt1`, `sha256:eed451b5497d078b8de4c098539cf63a4551aa0a46864fe7550b59066fe26250` |
| System | Reused step-10 payload, generated selection `system-native-A` |

The owner reported:

- Root serial login succeeded; `uname -r` and the runtime native Kernel record
  matched the exact intended input.
- `findmnt` resolved `/lib/modules` to `/usr/lib/modules`, mounted read-only
  from that exact native registry object's `payload/lib/modules` tree.
- `modinfo` found the retained e1000e module with
  `6.12.107-mojt1 SMP preempt mod_unload modversions` vermagic. This inspects
  module metadata; the active QEMU network driver was `virtio_net`.
- The runtime deployment record named the exact Base/Kernel, System generation
  and manifest, Kernel image/module digest, and initramfs archive/binding.
- No systemd units failed. The network interface had an IPv4 address and
  certificate-verified HTTPS returned the expected Nix cache information.

The initially reported `Modules: 0` did not mean the native Kernel object was
empty: it was the early-initramfs module count, while the full retained module
tree was mounted separately after the root disk became available. The observed
VirtIO boot/network path succeeded.

Both CI jobs passed for the functional revision above. This acceptance covers
one fresh image and its measured VM boot. It does not add existing-disk
activation/rollback, general Base Kernel bounds, firmware/Secure Boot coverage
or a libc compatibility solver. The deliberately narrow local Base range used
for this experiment is not a publisher-wide compatibility declaration.
