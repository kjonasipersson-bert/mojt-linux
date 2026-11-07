<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# System composition v1

The [native content installer](../../system-installation.md) now implements a
bounded native subset, including controlled profile symlinks and exact provider
runtime dependencies of native components, with no lifecycle execution. Remaining
provider/generalized deployment clauses below are review drafts. The [schema](system-composition.schema.json)
defines the complete field set; [common rules](README.md) govern identity and
encoding. [Example](examples/system-composition.json).

## Meaning and archive binding

The composition describes a resolved immutable System userspace. Requested
selectors, mutable source URLs, machine IDs, timestamps and local installation
paths belong elsewhere. Human `label` does not choose storage or identify a
build. `platform` is an exact supported target, not inferred from a package name.
Kernel/Base choices are deployment inputs, not selected components here.

Distribute this as existing native kind `system`, `system_role: generation`:

```text
./system/artifact.json
./system/payload/composition.json
./system/payload/lifecycle.json
```

The existing descriptor's `metadata` carries `system_role: generation` and
`composition: {format: mojt-system-composition-v1, id: FULL_ID,
path: payload/composition.json}`. This uses existing opaque metadata, not an
unversioned top-level descriptor extension. Inventory both JSON files. Each
must match its declared format/content ID. No self-reference: lifecycle
definitions do not contain the owning artifact or composition's ID; context
binds ownership later. The outer artifact inventories the composition, and the
composition references the lifecycle set. Never include the outer artifact ID
inside those files.

The outer descriptor's native/provider dependencies MUST equal the unique
direct references named in `components`. Their transitive closures are verified
and retained by the relevant adapters before publication. A composition cannot
claim dependency availability merely by listing it. A native System component
uses `system_role: component`; components do not become independent selected
System generations when acquired.

## Fields and semantic validation

| Field in description | Rule |
| --- | --- |
| `components` | Unique roles sorted by role, each binding an exact native reference or opaque provider identity; repeated references in different roles are allowed |
| `requirements` | Exact declared Base ABI name/value facts, state-layout version and required Kernel/host capabilities; unsupported required facts block, not silently succeed |
| `management` | Supported read/write format versions and capabilities by unique family, sorted by family; versions increasing, write subset of read; evidence must come from actual bundled manager support |
| `state` | Managed owner/namespace/path and schema-family read/write versions; unique owner/location, sorted by namespace/path/owner; conflicts across owners block |
| `profile` | Paths relative to `/run/mojt-system`, sorted uniquely; each source binds an exact listed component and relative component path; no arbitrary absolute copying |
| `services` | Unique unit names sorted by name and an explicit enablement boolean; unit must be provided by the realized profile; this is configuration, not immediate service start |
| `runtime` | Profile-relative interpreter, frontend and module directory; paths must resolve to retained compatible content in the realized profile |
| `lifecycle` | Exact action-set format/ID and `payload/lifecycle.json` path within this package's inventory |

Base ABI entries and required capability lists are unique and sorted by name.
This first wire format declares exact ABI facts and named capabilities, not a
new range/dependency solver. It does not bypass the existing selected-Base Kernel
policy bounds. Unknown platforms/required capabilities or unsupported provider
identity versions block the relevant operation with the missing fact reported.

Reject duplicate destination paths and destination ancestor/descendant overlap
(a mapped tree cannot be overlaid by another component's child). Validate source
type, containment, symlink behavior and runtime dependencies through the adapter;
opaque source paths are not authorization to read arbitrary host files. Profile
links may resolve into exact retained native/provider trees, never a mutable
`current` alias. Do not materialize every transitive dependency into PATH.

The profile subtree `generated/` is reserved for versioned assembler/handler
output and cannot be a component mapping. Generated outputs are inventoried
after staging; handlers cannot use this reservation to write arbitrary paths.

Managed state declarations describe requirements/support, not current live data
or a writable path grant. Bind them to the actual installation during preflight.
Ordinary user files outside declared state remain unmanaged. Any required
host-service condition needs an actual compatible capability check; similarly
named files or packages do not prove it exists.

## Realization and deployment

Assemble a private profile deterministically from verified inputs, then generate
the existing measured System manifest and validate actual profile inventory,
management support, account shells and runtime requirements. A composition is
intent for exact assembly; a measured manifest is evidence of the result. If
assembly adds platform-specific generated files, inventory/hash them and record
the assembler identity/inputs in realization evidence.

The generalized future deployment binds native Base and System artifact IDs,
composition ID, realized System manifest ID, exact Kernel/modules/initramfs and
hardware/console profile. Extending current deployment wire/layout requires an
explicit new version and compatible reader; do not add fields to today's
closed `mojt-boot-deployment-v1`. This format increment does not implement that
generalization or substitute a composition ID for an old manifest ID.

The proposed [generalized boot v2](boot-deployment-v2.md) now gives those binding
fields and single-menu publication rules. It remains a draft; native-v2 readers,
layout realization and transition/failure/boot acceptance must be implemented.

Changing content creates a new composition/artifact; updating a label or request
pointer does not mutate a retained generation. Selecting a System changes next
boot, after complete deployment and lifecycle compatibility checks, not the
currently running services. Read/compare is side-effect free.

