<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Component-based System generations

A component-based generation contains exact references to a Runtime and,
optionally, firmware. Component payloads are installed once in the native System
object store. The generation's profile contains controlled symbolic links,
`manifest.json`, `management.json` and its readable `version` marker. It does not
copy component file contents into another complete profile.

Base, Kernel, Ports and persistent state retain their independent lifecycles.
An installed generation can be prepared and selected through the ordinary MPM
commands. Installation on a live native-v2 target automatically prepares boot;
selection remains a separate operation and never implies an automatic reboot.

## Build a successor on Mojt

Run the installed builder as administrator:

```sh
mbt package system --running --output ./system-package
```

This packages the reviewed builder's bundled Runtime resources against the
running System's owned startup content and exact provider references. It creates
a new numeric packaging revision and a readable default generation label.
`--generation NAME` chooses a label and `--revision N` advances the packaging
revision by N. It does not rebuild upstream provider binaries or install/select
its output.

The default is minimal firmware selection: no firmware component. On a hardware
System, the new hardware declaration retains the Kernel/module/machine policy
and explicitly records absent firmware. Firmware-dependent devices require a
System with appropriate firmware; minimal does not mean universal device support.

To retain the current System's exact firmware selection:

```sh
mbt package system --running --firmware keep --output ./system-package
```

The builder reuses the retained firmware reference. It does not open, copy or
repackage firmware data or its containing archive. The first conversion from a
materialized generation may reference firmware subtrees of its existing Runtime
component. That original object remains retained; conversion does not move,
modify or delete it. Later Runtime updates keep that same reference.

The JSON result reports the generation archive, exact artifact ID and new Runtime
dependency archives. Install them using the existing `mpm system install
--from-file ... --expected-id ... --dependency-file ...` interface. Existing
firmware referenced by the generation needs no dependency archive. No package
code or interpreter from the candidate runs during installation.

The assembled-tree packaging interface remains available for bootstrap inputs:
`mbt package system --tree ... --generation ... --version ... --revision ...
--nix-store ... --output ...`. It retains its materialized profile layout.

## Storage and publication

| Representation | Contents |
| --- | --- |
| Native component object | One retained archive, descriptor/receipt and one sealed extracted payload |
| Generation object | Composition/lifecycle records and exact component references |
| Component profile | Declared links, parent scaffolding and small generated records |
| Prepared deployment | Boot files and the usual exact input, proof and handover records |

A generation descriptor declares
`metadata.profile_layout = mojt-system-component-profile-v1`.
The profile manifest retains its envelope and stores component projections as
`{component: {artifact: FULL_ID, path: PAYLOAD_RELATIVE_PATH}}`. Its
`provenance.native_profile` binds the component roles and mappings to the exact
composition. Complete file inventories stay in the component descriptors;
normal compatibility comparisons expand Runtime metadata, not firmware bytes.
Unchanged firmware is compared by reference. Conversion and firmware-selection
changes can compare its descriptor inventory without reading its files.

Incoming new component bytes are checked against their descriptor while being
extracted. Paths, links, modes, ownership, sizes, dependencies and composition
remain checked. Already installed exact components use protected metadata in
normal operation. `--verify` additionally audits retained archives, extracted
files and complete boot/component proofs. Expected hashes and descriptors are
integrity evidence, not publisher authentication.

Each new payload is made durable before immutable publication. The small
profile is separately published using the normal locked staging/rename path.
No hardlinks join mutable generation trees. A failure before publication cleans
only owned staging; uncertain publication preserves the potentially committed
result for inspection and explicit retry.

## Boot and return

Profile links name exact payloads below
`/run/mojt-disk/artifacts/system/installed/FULL_HEX/payload/`. Preparation resolves
these guest paths against the explicit target disk, not the builder's host
`/run`. The early reader binds native component receipts and expected payload
measurements. Normal boot checks metadata and required roots; explicit full
audit measures referenced payload contents.

Handover mounts the referenced component payloads read-only, attaches the profile
and projects firmware to `/lib/firmware` when selected. The component mounts move
with the backing disk to `/run/mojt-disk`. Their systemd mount policies retain them
through static exitrd shutdown. `/etc`, `/var`, `/home`, `/root` and local writable
root content keep their persistent locations.

Materialized generations remain readable and selectable with the new manager.
Existing objects, profiles and boot records are preserved. This does not install
new readers into old System code; older management tools may refuse new profile
operations. The existing envelopes and receipt bindings remain compatible with
booting retained materialized generations. The acceptance procedure checks an
actual return rather than treating a reader declaration as boot evidence.

See [normal operation boundaries](system-normal-operation.md), the
[component acceptance procedure](reports/system-components-test.md) and the
[normal-operation test](reports/system-normal-operation-test.md).

## Retain OpenSSL for repository-enabled management tools

`mbt package system --running --openssl-output /nix/store/EXACT-openssl-bin
--output NEW_DIRECTORY` can add the already registered output's exact closure
and `bin/openssl` / `libexec/mpm/bin/openssl` links. This adds a System-owned
provider reference even if the output was originally acquired with Ports.
Ports activation/removal therefore does not govern management tool availability.
The builder does not fetch, compile or globally activate OpenSSL. Existing
helper targets cannot be replaced by this addition. The new System must still
be installed, prepared and selected through MPM, then booted.
