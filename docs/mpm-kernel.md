<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Local Kernel install and status prototype

Status: experimental local native import/installation and read-only inspection,
following merged PR #28 and its [real package acceptance](native-artifact-format.md#owner-native-package-acceptance-2026-10-29).
The command works from a repository checkout with Python 3.11+ and zstd, without
Nix/provider code. The installed System launcher still invokes the older Nix
prototype directly; bundling/adopting this frontend in System is separate work.
No `activate`, upgrade, automatic tracking policy, catalog acquisition, boot
publication, GRUB/initramfs generation or existing-disk updater is implemented.
The next [read-only deployment planner](kernel-deployment-plan.md) checks an
installed Kernel against an explicit complete selection and initramfs binding;
it does not adopt that selection or establish boot readiness.

## Commands

Use a new, dedicated registry for the first experiment:

```sh
python3 -I -B tools/mpm --root /NEW/KERNEL-REGISTRY kernel status --json

python3 -I -B tools/mpm --root /NEW/KERNEL-REGISTRY kernel install \
  --from-file /LOCAL/KERNEL.tar.zst --expected-id sha256:FULL_ARTIFACT_ID --dry-run

python3 -I -B tools/mpm --root /NEW/KERNEL-REGISTRY kernel install \
  --from-file /LOCAL/KERNEL.tar.zst --expected-id sha256:FULL_ARTIFACT_ID -y

python3 -I -B tools/mpm --root /NEW/KERNEL-REGISTRY kernel status --verify --json
```

`--root` can precede `kernel` or follow `install`/`status`; specify it only once.
The default is `/var/lib/mojt/kernel`, separate from Ports metadata. Mutating
that shared registry requires effective UID 0 (for example via sudo). An ordinary
user can use their own private registry and inspect a readable shared registry.
Writable registries/ancestors or ancestors owned by an untrusted user are refused;
the root-owned sticky temporary-directory case is explicitly allowed. Running as
root against another user's home directory is not the private-lab workflow:
use that user for their lab, or a root-owned VM workspace.

The full SHA256 artifact ID is required; a short filename suffix/version is
insufficient. `--from-file` is explicit local acquisition and trust in that exact
content, not an authenticated publisher claim or a saved Kernel pin/follow wish.
There is no implicit Nix lookup, network fallback or source build. The archive
must be a local regular file, not a symlink. The producer's `artifact.json` and
transport sidecar are not prerequisites: the embedded descriptor is verified.

Without `-y`, the command shows its plan and asks whether to register the local
artifact. `--dry-run` verifies/plans without creating the registry, lock, staging,
retained payloads or install records. Status likewise never initializes state.
Normal inspection reads installed metadata; `status --verify` also hashes the
retained archive and every extracted file, checks the complete tree inventory,
normalized permissions and stored descriptor. It needs no original source file
or live catalog. Reinstalling the same exact artifact fully checks the retained
copy, reports no change and preserves its original record/timestamp. Damage is
reported, not silently overwritten with a replacement archive.

## Installed, selected and running

- **Installed:** complete, verified native Kernel content registered in this
  registry, with its original package and local installation evidence.
- **Selected:** unknown in this prototype, because the authoritative complete
  bootdeployment selection is not yet integrated. Installation never creates a
  Kernel-only selection pointer that could diverge from Base/System choices.
- **Running:** the actual `uname` release. Exact artifact identity is unknown
  until an authoritative deployment binding is available. An installed row can
  report that its release matches; matching text does not prove matching builds.

Installation retains content without choosing it for a deployment. It does not
relax the accepted selected-Base bounds or System/hardware/firmware gates for a
future resolve/upgrade/activate. This initial direct-file path does not derive
Base limits from the running system or manufacture compatibility metadata.
The plan/status explicitly report deployment compatibility as unevaluated; an
installed artifact is not a declaration of boot readiness. Kernel catalog
resolution remains the [separate existing read-only policy prototype](mpm-catalog.md).

Installed content is not automatically an upgrade wish. Tracking policies remain
separate future metadata. Multiple artifacts, even with the same kernel release,
are retained by full ID rather than colliding in the running `/lib/modules`.
No `/boot`, running module tree, Base/System/Ports state, boot menu, service or
selected/running deployment is changed by this command.

## Import boundary and storage

Only `kernel`/`linux` artifacts matching the host architecture's Linux platform
are accepted. The first subset requires empty dependency and requirement lists/
objects. Any nonempty declaration is rejected because acquisition/evaluation is
not implemented; ignoring it would incorrectly claim a complete installation.
Every payload/evidence member must be a regular file or directory; symlinks and
hardlinks, including otherwise valid evidence links, are refused before import.
The upstream Kernel layout is checked by the existing native descriptor validator.
Local paths are bounded to 64 components/4096 encoded bytes.

The approved source is copied through a no-follow file descriptor into a private
staging snapshot, bounded in size and fsynced. Its full artifact/content checks
are rerun after copying, so changing the source between planning and import
cannot register another build. The frozen copy is retained as `archive.tar.zst`.
Extraction is a second explicit streaming pass into a private staging directory:
validated names, exclusive file creation, no link/device types, and file hashing
while writing. It uses no tar extract/extractall or package hooks.

Published objects live under `REGISTRY/installed/FULL_HEX_ID/`, containing
`artifact.json`, `archive.tar.zst`, `installed.json`, `payload/` and optional
`provenance/`. The marker `.mojt-kernel-registry` identifies the strict registry
format; `.lock` serializes writers. Unknown formats/unmanaged nonempty roots
are refused. Existing contents are never automatically adopted or migrated.

The private extracted representation is owned by the installer and read-only:
directories 0555, files 0444 with original execute bits retained. Setuid/setgid,
write bits and package-requested numeric owners are not applied to the host.
The unmodified archive/descriptor retain original ownership and mode metadata
for future area-specific deployment handling. This is a declared storage
representation policy, not a change to the native artifact's content identity.

All files and the complete installation record are prepared/fsynced before one
directory rename registers the object. `.install-*` directories are siblings of
final object directories, allowing a read-only directory to be renamed within
the same parent without a writable published window. Status reports these as
staging, never as installed content; it also reports reserved `staging/` entries.
Normal failure cleans only its own unpublished stage. Interrupted stages are
reported without adoption/deletion. Earlier installed builds remain unchanged.
If publication's directory fsync fails after rename, inspect status: the complete
object may already be visible. This is not a power-cut-tested recovery protocol.

`installed.json` records the schema, full artifact ID, retained archive checksum/
size, installation UID/time, explicit-local-file trust and storage policy. It is
published with its object, not through a separately updated database or ledger.
Byte integrity does not authenticate remote publishers or prove runtime ABI.
Remote repository trust/update and production hostile-input/resource hardening
remain separate work; this first workflow uses an owner-controlled local package
and an explicitly supplied full artifact ID.

## Focused verification

```sh
python3 -B -m unittest discover -s tests -p 'test_mpm_kernel.py' -v
```

The real tar/zstd fixture tests cover preview/status with no writes, private
extraction/registration, no-op retention, different builds sharing one kernel
release, concurrent writers, interrupted extraction/publication, source changes,
damaged content, unsafe roots/links, unsupported dependencies/requirements,
normalized permissions, shared administration and no provider files/executables.

## Owner local Kernel installation acceptance, 2026-10-29

The owner ran the repository frontend at functional revision
`013cb40947243b28efc5ee6caa7f3063f600ab77` as an ordinary user on Debian,
using a dedicated private registry and the previously accepted real package:

`sha256:eed451b5497d078b8de4c098539cf63a4551aa0a46864fe7550b59066fe26250`

Empty status and installation preview created no registry or installed content.
Installation retained package version `6.12.107-r1` and actual kernel release
`6.12.107-mojt1`; `status --verify` verified the retained archive, extracted
files and metadata. No staging entries remained. Repeating installation reported
no change, preserving the complete status and original installation record.
The source archive checksum remained unchanged.

Ordinary status then reported the installed package as
`verified-at-installation`, distinct from the fresh `verified-now` scrub.
Selected deployment remained unknown, and running release was the Debian
host's `7.2.9+deb13-amd64`, with exact running artifact unknown. Installation
did not create a deployment selection or claim compatibility/boot readiness.
This accepts local import/status/idempotence for the real package; it does not
test boot activation, repository trust, shared privileged installation or
power-loss recovery. No new kernel build or VM boot cycle was required.
