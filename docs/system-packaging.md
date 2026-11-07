<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# From an assembled System profile to a local native kit

This joins existing System assembly, native packaging, named sources/cache and
the content installer. It does not assemble or select a boot deployment.

## Input and packaging

Use a **newly assembled** tree from the current builder, containing
`system/GENERATION/manifest.json` and measured `management.json`. An old step
payload (`system.json` plus exported store objects) is an input to assembly,
not this command's completed profile. The bundled MPM must advertise the new
profile-link/runtime-output capabilities; the packer does not silently replace
old code. It inventories the actual profile and refuses changed inputs.

```sh
python3 tools/mojt-artifact-pack.py system \
  --tree /BUILD/assembled-tree --generation system-example \
  --version 0.2.0 --revision 1 \
  --nix-store /ABSOLUTE/retained/bin/nix-store \
  --output /BUILD/system-kit
```

The explicit Nix helper queries the already present outputs, compares the full
closure and NAR hashes with the assembled manifest, and verifies store bytes.
It performs no realise/import/build, GC-root update or profile activation. No
candidate executable, setup script or unit is executed. Source-profile copies
must match the original measured inventory before packaging.

The native archives contain only `./system/*`, following the existing package
format. `component/` holds the owned profile files and original symbolic links,
with exact provider dependencies. `generation/` holds the resolved composition,
an empty manager-owned lifecycle set and the original assembled manifest as
provenance. Numeric archive ownership is explicitly root, independent of the
packaging user's UID; this does not change source ownership. Write bits are
removed by the installer, as before.

`0.2.0-r1` is the owned System package release. It is independent of the human
generation label and provider package versions, and is not the Kernel release.
Changing contents changes the full artifact ID even if the label is reused.
The original manifest ID, provider references and packer code hash are retained.
Repeated packaging of the same frozen inputs/version gives the same artifact
identities; local source metadata additionally binds its explicit kit location.

## Named source and installation

The kit also contains `policy.json`, `source.json`, `snapshot.json`,
`catalog.json`, `acquisition-map.json` and versioned `kit.json`. They use the
existing owner-authorized local source/cache formats. Hashes provide integrity,
not publisher authentication. Review/authorize a local kit before registering it.
Moving a kit requires new explicit location/policy metadata, not rewriting an
accepted snapshot behind MPM's back.

```sh
mpm source add system-kit --from-file /KIT/source.json \
  --policy-file /KIT/policy.json --dry-run
mpm source add system-kit --from-file /KIT/source.json \
  --policy-file /KIT/policy.json -y
mpm source update system-kit -y

mpm system install --source system-kit --expected-id sha256:GENERATION_ID \
  --archive-sha256 ARCHIVE_SHA256 --dry-run
```

Inspect the plan, then repeat the final command with `-y` instead of `--dry-run`.
The exact generation ID is in `kit.json`; its compressed encoding checksum is
in `generation/archive.json`. IDs/checksums are complete, not the abbreviations
shown above. `--snapshot` pins an accepted snapshot; source/cache roots can be
explicitly selected just as for Base.

Source preview is metadata-only: it shows native acquisitions and exact provider
requirements, with `archive_verified=false` and `profile_validated=false`.
It creates neither cache nor installation content and needs no codec/provider
command. Actual installation keeps source authorization locked, freezes/verifies
all new native inputs in the common cache, and calls the same content installer.
Complete compatible installed components can be reused. Missing or ambiguous
component encodings block; there is no arbitrary mirror/encoding/provider choice.
Both generation and newly acquired component receipts retain their source/cache
verification evidence. An exact completed repeat verifies retained data without
fetching again, including when the original kit directory is gone.

Provider operations currently require the running installation, whose selected
System supplies the adapter/helper. An explicit offline target cannot use the
inspector host's unrelated Nix store. Offline bootstrap/provider seeding remains
a separate target-adapter join.

## Link and readiness boundaries

Relative/profile-absolute links resolve inside the immutable profile. External
links must belong to an explicitly accepted provider closure; verification also
checks their actual resolved targets remain in that closure. Loops, dangling
local links and arbitrary host paths are refused. Hardlinks remain unsupported
in this System importer. The common unpacker permits symlinks only on this
explicit path and never opens/chmods/extracts descendants through a link.

The current account profile additionally links `sudo`/`passwd` to late-created
`/run/mojt-privileged` helpers. These are declared by versioned
`mojt-profile-runtime-outputs-v1` metadata with the bounded
`mojt-privileged-v1` producer, and require measured management support. They are
retained as **unavailable runtime requirements**, never copied from the running
host, created or granted privileges during installation. Static executable
provides do not claim those outputs already exist.

The kit explicitly has `deployment_ready=false`. Its generation carries a
`mojt-system-content-only-v1` deployment contract: existing profile services/setup
still need initialization review and the next System deployment/service gate.
An empty manager-owned lifecycle set does not claim that arbitrary stored
services have no state effects. Installation neither runs those services nor
chooses the generation for boot. This preserves the existing behavior as data
while making the remaining integration explicit. No ELF/libc runtime
compatibility claim follows from successful content packaging/import.

Three focused synthetic tests cover real package reproducibility/provenance and
metadata-only source preview, forbidden link targets, and root source/cache
installation with original links/origins/no-op retention. Provider I/O is
simulated; live Nix import and a new System boot are not claimed. Owner VM
acceptance belongs to the following actual deployment integration.
