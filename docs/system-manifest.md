<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# System manifest and declared compatibility

This limited increment describes a completed System and checks explicit
installation requirements. It does not implement `mpm system upgrade`, change
GRUB/next-boot selection, migrate state or modify a running System. The next
milestone is running the existing build tools on Mojt to produce a new image.

## Manifest

The fresh-image builder writes `system/<generation>/manifest.json` after each
System profile is complete, including hardware staging. Existing payloads remain
usable: the manifest is generated from the payload's verified records and this
builder checkout. It is separate from the payload's existing `system.json` and
the boot deployment's `boot.json`. Kernel/initramfs selection stays in the
existing boot descriptor; this increment does not invent an independent Kernel
release format or conflate a System label with its content identity.

`mojt-system-manifest-v1` contains `format`, `id` and `description`. The ID is
SHA256 of canonical JSON for the complete description. The description records:

- Human build label and Base architecture.
- Exact declared Base ABI and persistent state-layout requirements.
- Supported Ports read/write formats and capability identifiers.
- Available executable `/run/mojt-system/bin/*` paths.
- Opaque backend artifact/provenance records: this adapter records the retained
  Nix source, package role/output mapping, verified object integrity and registration.
- Builder source-file hashes and payload-record hash.
- Complete System profile file hashes, modes, links and directories, excluding
  the manifest itself to avoid recursive identity. A manifest file is not a
  signature or an on-demand audit of the actual profile bytes.

Generated profile files, labels and assembly timestamps participate in identity;
identical packages alone do not imply identical System identities or reproducible
images. Persistent `/etc`, `/var`, homes and Ports are not included in this
immutable profile inventory. The pure model does not interpret backend identity,
package version, path, digest or dependency syntax. No dependency/libc solver is
added. Core schema changes require an explicit new format.

The Nix adapter reads literal capability declarations from the bundled MPM
source using AST data extraction. It does not execute that source while
inventorying a candidate. Formats 1/2/3 and `mpm-ports-selectors-v1` match the
current MPM implementation; a System without MPM advertises no Ports support.
Future writers must update both declarations and their actual validation, with
an appropriate compatibility test.

## Preflight

Before publishing the new image, the builder compares each candidate with its
private copied installation state. It checks architecture, exact declared Base
ABI, state-layout version, Ports read and write formats/capabilities, and
persistent accounts' required `/run/mojt-system/` shells. Thus a candidate whose
MPM supports only formats 1/2 is rejected when the copied state uses format 3.
The comparison uses installation facts, not the running System's version label.
Unknown manifest/context formats, corrupt identities, incomplete format-3
capability evidence and dangling Ports profiles fail rather than being inferred.

This is a conservative declaration check. It does not prove runtime ABI,
PAM/NSS, desktop or kernel-driver compatibility. Other Base-provided account
shells are outside this model; the existing builder still checks the root shell
against the assembled Base/System. It performs no data migration or fallback.

## Read-only inspection

```sh
python3 tools/mojt-system-inspect.py \
  --candidate manifests/system-manifest-example.json \
  --context manifests/system-context-example.json
```

These examples use a synthetic non-Nix backend and are not installable payloads.
To inspect real completed manifests and explicit installation facts:

```sh
python3 tools/mojt-system-inspect.py \
  --candidate /ASSEMBLED/system/system-B/manifest.json \
  --target /INSTALLATION --base 0.1.3 \
  --running /EXPLICIT/RUNNING/manifest.json
```

`--target` is an offline directory installation or assembled tree with
`releases/base-<version>.toml` and shared `state/`. It reads the selected Ports
snapshot and System-provided account shell requirements. An initialized but
empty Ports directory is treated as no Ports state; a dangling current link is
an error. `--context` instead accepts explicit `mojt-system-context-v1` JSON for
portable policy checks. Neither mode writes installation files, roots or state.

Output shows candidate, explicitly supplied running/selected identities,
complete before/after description fields, compatibility result and reasons.
`--selected FILE` is an explicitly supplied next-boot manifest; omission produces
null/unknown. No next-boot choice is inferred from a running label or `current`
link, and no choice is scheduled. Return code 0 means declared compatibility;
1 means incompatible or invalid input. Source-checkout and built step-3+ System
wrappers are supported; new Systems expose `mojt-system-inspect`.

## Validation and remaining work

Targeted tests cover compatible input, older writers, unknown capabilities and
formats, architecture/ABI/layout/shell mismatch, explicit selected/running
reporting, read-only CLI behavior, dangling state, deterministic assembled
manifest creation and builder rejection of incompatible Ports metadata.
Existing System/generation assembly tests cover multiple pairs and interrupted
publication. No repeat of the selector A/B/A manual checks is required for this
metadata-only increment. Full runtime/image acceptance can accompany the first
build-on-Mojt experiment, when the manifest is consumed in that workflow.

Existing-disk System deployment, durable boot publication, automatic fallback,
project locks, retention/GC and runtime libc work remain separate tasks.
