<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Concrete distribution formats: first review draft

2026-11-01. Proposed wire/storage formats for D2/D3/D4 in
[the decision register](../../distribution-decisions.md), not deployed formats.
MBT syntax is deliberately unchanged by this increment. No existing archive,
Kernel registry, boot menu or Ports database is silently converted.

| Contract | Format / schema | Detailed rules |
| --- | --- | --- |
| System composition | `mojt-system-composition-v1` / [schema](system-composition.schema.json) | [Composition](system-composition.md) |
| Native store identity | `mojt-artifact-store-v1` / [schema](artifact-store.schema.json) | [Storage](artifact-storage.md) |
| Installed native object receipt | `mojt-install-receipt-v1` / [schema](install-receipt.schema.json) | [Storage](artifact-storage.md) |
| Declared lifecycle actions | `mojt-lifecycle-set-v1` / [schema](lifecycle-set.schema.json) | [Actions](lifecycle-actions.md) |
| Per-action attempt/result | `mojt-lifecycle-result-v1` / [schema](lifecycle-result.schema.json) | [Result registry](lifecycle-results.md) |

The [common schema](common.schema.json) defines exact native references,
provider-owned references, paths, hashes, compatibility declarations and effect
observations. JSON Schema draft 2020-12 checks structure. The linked documents
also impose semantic, filesystem, provenance, dependency and recovery rules
that JSON Schema alone cannot establish. The runtime MUST enforce both.

## Encoding, identities and limits

Every new top-level record has exactly `format`, `id`, `description`. Unknown
fields/formats are rejected. Required fields are never omitted; use explicit
empty lists or permitted nulls. No generic extension bag or executable metadata.
Provider `identity` is the intentional opaque exception: the provider's explicit
versioned identity validator must accept it before use; the core cannot infer
its semantics or change provider.

Use the existing native artifact canonical encoding: sorted string keys,
`ensure_ascii=True`, separators `,`/`:`, ASCII bytes, no whitespace or floats.
For THESE new records, `id = sha256(canonical({format, description}))`, excluding
only the top-level `id`. Store canonical complete JSON plus one newline. A
readable indented example represents the same value, not the stored encoding.
No Unicode normalization, omitted/default field insertion or array reordering
during identity verification. Producers obey the documented stable array order.
Reject duplicate JSON keys, floats/nonfinite values, unpaired Unicode surrogates,
integers outside signed 64-bit range and non-UTF-8 input before schema validation.

Limits: 16 MiB encoded metadata, nesting depth 64, at most 4096 entries per
collection unless the schema is stricter. Relative paths have no empty, `.`,
`..`, backslash, colon or control-character components; at most 64 components
and 4096 UTF-8 bytes. Absolute account home/shell paths obey the same component
rules after their leading slash. Do not follow a symlink to validate authority.
Schema patterns are an initial lexical gate, not a filesystem boundary.

Full lowercase `sha256:` plus 64 hex digits is content identity. Raw archive/file
hashes use 64 hex digits without the prefix, as existing native descriptors do.
The schema IDs under `https://mojt.invalid/spec/draft-v1/` are offline identifiers,
not network locations; validators register the local schema documents and do not
fetch remote references. These drafts are GPL-2.0-only (C) 2026 Jonas Persson,
including the schema files and synthetic examples.

## Compatibility and publication

The existing `mojt-artifact-v1` descriptor, canonicalization and category-rooted
archive format remain unchanged. Their IDs are not new record IDs. The existing
`mojt-system-manifest-v1` hashes its description under its own rules; do not
re-hash/relabel it as a composition. A deployment binds both the distributable
composition's native artifact and its independently measured realized manifest.
Existing `mpm-kernel-install-v1`, Kernel boot records and Ports formats also
retain their established semantics. New readers need explicit compatibility
adapters; old readers are never expected to accept a new marker or extra fields.

No implicit read-time migration, registry creation or marker replacement.
Before activating a System, check current-manager and selected-runtime support
for every shared record family and required handler they will use. Old Systems
that cannot manage new metadata are refused before normal rollback selection.
The transition/rollback plan must cover state publication ordering; this draft
does not make cross-registry format upgrades atomic.

Initial native trust in these schemas is explicit local-file trust only. Native
remote publisher trust remains D7; provider dependency validation remains with
the named adapter. A local receipt or a content hash is not a publisher signature.

## Examples and validation

[Examples](examples/system-composition.json) are synthetic structural fixtures:
external artifact/provider IDs do not identify shipped content and no archive,
tool, service or real installation is created. The six examples link composition,
action set, store identity, receipt and a started/completed attempt. All new
record IDs and the result hash chain are recomputed, not placeholder hashes.

Run the documentation validator with Python 3.11+ and `jsonschema` (validated
here with 4.26.0):

```sh
python3 docs/formats/draft-v1/check_examples.py
```

This is a documentation consistency check, not an installer/runtime validator or
an implementation of D2-D4. It checks schemas, example identities/references,
ordering, result transitions and selected negative cases. Real archive, root
ownership, adapter, concurrent-writer, interruption and boot tests remain
implementation acceptance. No extra manual VM cycle is needed for this text.
