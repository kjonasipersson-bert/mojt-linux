<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Private workspace image-build acceptance

Historical test record from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
The fixtures and observations below are not the current command contract.

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
