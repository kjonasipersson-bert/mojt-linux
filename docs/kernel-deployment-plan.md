<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Read-only Kernel deployment planning

The local Kernel install/status increment passed real owner acceptance and
PR #29 merged. This next experimental increment adds `mpm kernel plan` in a
checkout. It binds an installed native Kernel to a complete proposed boot
deployment and checks explicit declarations without publishing or selecting it.
It is not `activate`, an existing-disk updater, an initramfs builder or a claim
that all required content is ready to boot.

## Command and inputs

```sh
python3 -I -B tools/mpm --root /KERNEL-REGISTRY kernel plan \
  --request /LOCAL/PLAN/request.json --json
```

`--root` names the Kernel registry, not an installation root or target disk.
It may precede `kernel` or follow `plan`, once only. No administrator privilege
is required for readable inputs. The command initializes no registry, lock,
selection, cache, stage or boot files. It needs Python 3.11+, the checkout and
the retained installed object; no provider executables, network or zstd command
are needed for this planning operation. Installation itself still needs zstd.

The request is strict `mpm-kernel-plan-request-v1` JSON:

```json
{
  "format": "mpm-kernel-plan-request-v1",
  "kernel": "sha256:FULL_INSTALLED_KERNEL_ID",
  "selected": "selected.json",
  "base_context": "base-kernel-bounds.json",
  "system_manifest": "system-manifest.json",
  "system_context": "installation-context.json",
  "initramfs": "initramfs.cpio.gz",
  "initramfs_binding": "initramfs-binding.json"
}
```

The example ID is a placeholder, not executable test metadata. Paths are local,
relative to the request's directory unless absolute. URLs, input symlinks,
symlink ancestors, FIFOs and nonregular inputs are rejected. JSON is bounded,
rejects duplicate keys/floats and unknown envelope fields. Missing selection or
compatibility metadata fails; `uname`, `current`, catalogs and version labels
are never substituted as authority. Inputs are owner-controlled local evidence,
not authenticated statements from a disk or publisher.

## Complete deployment identity

`mojt-boot-deployment-v1` has exactly `format`, `id`, `description`. Its ID is
the native canonical SHA256 of the description, using the same integer-only,
ASCII-escaped canonical JSON as native artifacts. It is a typed deployment ID,
not a package artifact ID or signature. The description contains:

| Field | Exact reference |
| --- | --- |
| `platform` | Explicit architecture/Linux platform |
| `base` | `{artifact, release}`: full native Base artifact ID and release label |
| `system` | `{manifest, generation}`: exact existing `mojt-system-manifest-v1` ID and label |
| `kernel` | `{artifact, release, image_sha256, modules_digest}`: full installed artifact ID, actual kernel release, image hash and canonical digest of its complete versioned module inventory |
| `initramfs` | `{archive: {sha256, size}, binding}`: exact archive evidence and binding declaration ID |
| `boot` | `{root_uuid, console, cmdline}`: canonical filesystem UUID, explicit serial/local console and the existing exact generated Base/System boot command line |

Kernel IDs, package versions and actual kernel releases remain separate. Two
builds with the same release and different bytes have different artifact and
deployment identities. Module inventory includes recorded file content/modes/
owners and the complete matching release tree from the native descriptor;
its digest is not inferred from `uname` or module filenames alone.

The supplied selected deployment is an explicit baseline, not automatically
adopted selected state. A Kernel plan preserves its exact Base, System manifest,
platform, root UUID and console/command line. It may change only Kernel and
initramfs references. Selection/request tracking policies remain separate.
Repeating identical inputs produces the same candidate and evidence; when the
candidate equals the explicit baseline, `no_change` is true. Nothing is saved.

## Declared compatibility and early-boot binding

1. The exact candidate must already be installed in the registry. Every retained
   file, descriptor, archive hash, inventory and normalized permission is checked
   again. Missing/damaged candidates fail; no import, fallback or repair occurs.
2. The existing `mpm-kernel-base-context-v1` must name the baseline's exact Base
   artifact/release and platform. Its inclusive minimum and maximum constrain
   numeric upstream Kernel metadata, not package revision or the local release
   suffix. Missing bounds fail. No actual Base 0.1.3 bound is invented here.
3. The System manifest must exactly match the baseline's manifest ID and label.
   Its existing compatibility checker enforces declared Base ABI, architecture,
   state layout, persistent Ports read/write formats/capabilities and required
   System shell paths. External runtime identities remain opaque.
4. Installation facts use `mpm-deployment-context-v1`, with exactly `format`,
   `selected`, `base`, `root_uuid`, `facts`. These bind the selected deployment ID,
   Base reference and root UUID to the existing `mojt-system-context-v1` facts.
   Supplying another selected/running context does not silently change scope.
5. `mojt-initramfs-binding-v1` has `format`, `id`, `description`, with canonical
   description identity. That description contains exactly `platform`, `base`,
   `system`, `kernel`, `boot`, `archive`, using the deployment's reference shapes.
   All must match the candidate, including its exact module inventory and root
   UUID. The actual supplied initramfs bytes/size must match `archive`. Changing
   only the Kernel ID or same-release build invalidates the old binding.

A successful plan returns `mpm-kernel-plan-v1`: complete candidate, explicit
baseline ID/source, exact Kernel/initramfs changes, input-context digests,
System check and fresh Kernel integrity evidence. Invalid/incompatible inputs
exit nonzero with a reason. The plan always returns `boot_ready: false` and
`writes: false`, even when declaration checks pass.

## Evidence limits and next integration

The Base reference is not yet checked against installed native Base content;
System metadata identity is checked but its payload/provider closures are not
audited. Compatibility facts and the initramfs binding are explicit local
declarations. Matching the archive checksum does not inspect its cpio contents,
prove its mount logic, validate modules' runtime ABI or authenticate the producer.
These limits are included in successful output, not hidden behind a ready flag.
Hardware/firmware, external modules, Secure Boot and runtime libc compatibility
are not evaluated. There is no Base libc replacement or global library-path edit.

Current image builders emit format-1 `boot.json` and mount modules/firmware from
the System profile. Those records lack these exact references and are not
automatically adopted. The new deployment record is not written over an old
boot record or converted into a GRUB entry. A future builder must explicitly
consume native Kernel content, mount the chosen modules, generate/bind the
deployment-specific initramfs and verify Base/System payloads/dependencies.
It must preserve the selected System userspace while composing the independent
Kernel choice, without reusing an old System-name boot directory for new bytes.
Only a separate transactional publication/selection operation may activate it.

The focused tests use real installed tar/zstd fixture packages and deliberately
synthetic, nonbootable initramfs bytes. They cover complete identity and selected
scope, every declaration gate, same-release builds, damaged/missing content,
binding/byte mismatches, malformed input, provider-free CLI and unchanged inputs.
CI is sufficient for this read-only increment. One focused build/boot acceptance
belongs with the first actual native-Kernel deployment builder, rather than
repeating the earlier account/network/generation loops here.
