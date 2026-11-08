<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native-v2 verification initramfs

This implements the constructor/early-verification part of the
[native-v2 boot foundation](native-boot-v2.md), within consolidation step 3.
It is an internal diagnostic constructor, not a successful System deployment or
a replacement for the accepted v1 initramfs. No public command syntax changes.

## A trusted interpreter before target code

Base remains Python-free. The administrator explicitly designates a trusted,
exact provider runtime and interpreter for the constructor. `freeze_runtime`
verifies that reference with its manager-owned adapter and copies its bounded
trees into a private bundle at their guest paths. This is independent of the
candidate System's interpreter and does not discover an interpreter on PATH.

The provider-neutral `boot_paths(reference, root)` protocol returns sorted,
nonoverlapping relative roots. It is a projection of an already verified
reference, not verification by itself. The Nix adapter projects the exact output
closure, refusing an offline copy that merely resembles the inspector's store.
Other adapters must explicitly implement the same finite tree-export protocol.
The reader needs no provider executable or provider database in initramfs.

The versioned `mojt-boot-python-runtime-v1` record binds the original reference,
absolute guest interpreter and complete measured trees. Runtime copies preserve
ordinary modes/owners and within-tree hardlinks; special files, privileged or
other-writable entries, xattrs and links outside the copied closure are refused.
The final newc writer preserves file/link bytes and ordinary metadata, representing
runtime hardlinks as separate identical files. Python starts with `-I -S -B`
under static BusyBox `env -i`, avoiding inherited loader/Python environment and
site/user startup code. Runtime libraries are supplied by that copied closure;
Base libc is not replaced or used to bootstrap the reader.

The runtime provider is an explicit local trust choice. Integrity verification
does not make arbitrary provider code trustworthy or authenticate a publisher.

## Constructor and hash order

`mojt-verification-initramfs-constructor-v1` identifies manager code hashes,
the frozen runtime record and static BusyBox digest. This constructor reference
exists before boot inputs and is checked against their exact `constructor` field.
No package-supplied constructor is executed.

The constructor audits installed input content with the existing native-v2
store checks. Its `mojt-boot-tree-proof-v1` record binds the input ID and complete
Base realization, System profile, native module and provider tree inventories.
Inventories include type, owner/group, mode, file size/hash, xattrs and within-tree
hardlink relationships. They are bounded and do not follow directory symlinks or
open special files. Shared provider roots are measured once.

The proof, inputs, trusted code and runtime are embedded in a real bounded
gzip/newc archive, using the existing writer and independent archive inventory
inspection. Matching early modules use the existing Kernel dependency ordering
and decompression. Only after archive bytes exist is the input/archive binding
created; the later deployment ID is never embedded in its own hash input.
Construction writes only its new private work directory and leaves installation
content, boot selection and persistent state unchanged. Failed work may remain
for diagnosis; it is never returned as completed or selected.

## Early verification and present boundary

Static BusyBox loads the prepared modules, finds the embedded root UUID and
mounts that filesystem read-only. The bundled reader validates:

- One exact deployment selector and the complete derived command line, including
  reserved arguments. Optional GRUB `BOOT_IMAGE` must identify that same slot.
- Canonical v2 sidecars, full deployment/input identities, the installation ID,
  Kernel/initramfs file bytes and expected running Kernel release.
- Full inventories of the exact Base, System, native module and provider trees
  before returning their paths. Paths derive from full artifact identities;
  mutable generation labels/current pointers are not used for lookup.

It imports no target Python modules, runs no provider executable and executes no
candidate program. Its result is a diagnostic verification receipt, not the
running deployment status. A release-string comparison is an additional mismatch
check, not proof of the running artifact or hardware attestation.

The current init script deliberately enters a diagnostic shell after verification.
`boot_ready=false`, `handover=false`, and `selection_changed=false` remain explicit.
The script neither initializes state nor invokes System start. Initializer/default
and current-state compatibility gates, additive Base mountpoint realization,
read-only runtime mounts, static shutdown handover and authoritative boot
selection must be joined before exposing successful `mpm system stage/select`.

## Focused validation

Two inexpensive nonroot cases cover bounded no-follow inventories, special-file
refusal, exact command-line policy and provider projection boundaries. One root
CI case builds the actual archive with a deliberately small trusted distro Python
fixture, extracts it independently with GNU cpio, and runs the embedded reader
in chroot without host Python/libraries. It checks exact content and refusal of
changed boot arguments and Base files. Installed target content remains unchanged
during construction. This exercises runtime isolation and reader execution; it
does not claim a v2 Kernel boot, System service health or arbitrary libc/desktop
compatibility. The production provider remains Nix; the distro runtime adapter
exists only inside this independent test.
