<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# UEFI disk-copy boot acceptance

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

## Owner-reported disk-copy acceptance (2026-10-24)

The owner reported that the final disk-copy test works after moving the copy
directory into their home directory. The original attempt failed while creating
the copy directory, before QEMU started; no image rebuild was needed. The
successful recipe copies only the powered-off disk and firmware launcher,
creates fresh firmware variables and starts the copied Mojt disk without
external kernel/initramfs files. This completes the owner-reported disk-boot
milestone. Individual login/service/network/Ports and history-check logs from
this UEFI run were not supplied, so those checks are not separately attested
by this report.

The feature remains an experimental image builder, not a hardware installer,
kernel release pipeline, System updater or automatic rollback mechanism.
Persistent service state is not rolled back by a boot entry.

References: [GNU GRUB standalone image tool](https://manpages.debian.org/bookworm/grub-common/grub-mkstandalone.1.en.html),
[mtools image access](https://www.gnu.org/s/mtools/manual/mtools.html#Drive-letters),
and [QEMU boot options](https://www.qemu.org/docs/master/system/qemu-manpage.html).
