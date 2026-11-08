<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native-v2 boot records and retained slots

This is the record/storage increment of the
[System transition](system-transition.md), within consolidation step 3.
It implements the four closed records in the
[v2 format contract](formats/draft-v1/boot-deployment-v2.md).
The internal libraries are delivered in System; they introduce no public CLI.

## Identity without a hash cycle

1. Boot inputs bind exact installed Base, System composition/measured profile,
   Kernel image/modules and explicit upstream version, installation and root UUID,
   Base Kernel bounds with their supplied policy digest, and constructor reference.
2. The initramfs binding identifies those inputs and the resulting archive bytes.
3. The deployment embeds both complete records and inventories the Kernel image
   and initramfs. Its full ID names the immutable slot.
4. A selection record can then refer to deployment IDs. The pure renderer derives
   `mojt.deployment=FULL_HEX` after deployment identity exists.

IDs use SHA256 over the canonical format/description envelope. The descriptor
and sidecars do not inventory themselves. Labels and `uname` are never artifact
identities. Constructor/provider identities remain opaque; retention executes
neither package code nor a constructor named by metadata. Digests establish
integrity, not authentication or trusted release policy.

The first supported record subset is `x86_64-linux`, `native-v2`, serial console,
`qemu-uefi-virtio-v1`, no firmware/state-schema requirements, and a small explicit
allowlist of optional Kernel arguments. Unsupported requirements fail closed.
This profile identifier is a contract restriction, not evidence of a v2 VM boot.

## What retention verifies and writes

`mpm_boot_v2_store.retain` audits the common installation identity, verified Base
archive and extracted realization, native System composition and realized profile,
provider closure through its existing manager-owned adapter, and retained Kernel
image/modules. Supplied Base bounds must match the exact input policy digest;
the Kernel range uses explicit numeric upstream metadata, never a release suffix.
Declared management requirements must fit both measured preparing/candidate code.

Binary inputs are frozen with bounded no-follow copying and verified against
the exact deployment inventory. The only completed content publication is:

```text
boot/mojt/deployments/FULL_DEPLOYMENT_HEX/
    inputs.json
    binding.json
    deployment.json
    vmlinuz
    initramfs.cpio.gz
```

Files are private regular root-owned 0444 entries; the directory is 0555.
Sidecars must be canonical and identical to the embedded records. Existing linked,
incomplete or damaged slots are refused. Exact retries verify retained content
and do not need the original source files. A retry flushes the retained slot and
parent again, allowing recovery from an uncertain earlier directory flush.

Publication holds the shared artifact, installation, Kernel and boot writer locks
in deterministic order. It uses same-filesystem staging, fsync and one rename.
A pre-rename failure removes only staging. A post-rename flush failure retains
the possibly committed complete slot and reports publication uncertainty.
Preparation can leave coordination directories/locks, but no boot choice.
Dry-run creates no target directories, slots or locks.

`inspect` checks retained sidecars/bytes; it does not repeat the installed input
audit. `retain`, including its no-op and dry-run paths, does repeat that audit.
Neither function certifies the initramfs contents as executable or bootable.

## Gates still ahead

Results explicitly say `boot_ready=false` and `selection_changed=false`.
Retention does not run the System startup/state compatibility review, prepare
defaults, create boot mountpoint realizations, authorize lifecycle actions, or
replace a menu. It must not be exposed as successful `system stage` yet.
The pure GRUB renderer/parser is available for validation; there is no v2
selection publisher. Existing v1 boot paths are untouched.

The next integration must connect a measured initramfs constructor and trusted
early reader, verify all exact inputs before mounting them, join the existing
System preflight and initialization gates, and publish one authoritative complete
next-boot choice. Only then run a focused owner System boot/return test. This
increment needs focused record/storage CI, not another unchanged Kernel/Base VM
matrix or a hardware test.
