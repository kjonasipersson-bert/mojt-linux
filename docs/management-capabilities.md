<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Management, state and handler compatibility

This consolidation step adds a bounded compatibility gate before native System
installation/deployment. It does not install a System, run lifecycle actions,
migrate data, start services or declare a deployment ready. Existing MPM and MBT
command syntax is unchanged.

## Measured System support

New step-3+ assemblies include `system/GENERATION/management.json`, an ordinary
file in the measured System profile inventory. Its independent versioned format
avoids silently extending the closed `mojt-system-manifest-v1` wire. The profile
manifest binds its SHA256/mode; the sidecar binds the exact bundled code closure
for the advertised native capabilities, checked against profile metadata/bytes.
It contains no self-referential manifest/artifact ID.

`mojt-management-capabilities-v1` uses the standard `{format, description, id}`
envelope; ID hashes canonical `{format, description}`. Its description contains:

| Field | Meaning |
| --- | --- |
| `management` | Sorted unique format families, integer `read`/`write` versions and named capabilities. Write versions must also be readable. |
| `state` | Exact owner, namespace, relative path, schema family and read/write versions; overlapping owned paths are refused. |
| `handlers` | Exact type, integer version, phase and protocol contract; no executable text or arbitrary path. |
| `implementation` | `mojt-manager-code` reference containing the SHA256 of every module/helper needed by the advertised native defaults protocol. |

The first producer reads literal declarations from the retained
`mpm_defaults.py` with AST data extraction; it never imports candidate Python.
Current declarations support the `mpm-defaults` registry family, version 1, and
`missing-default` version 1 / `initialize` /
`mojt-defaults-preparation-v1`. This is the bounded preparation protocol from
[#42](https://github.com/kjonasipersson-bert/mojt-linux/pull/42), **not** support
for the proposed general lifecycle action-set/result/saved-plan wires. Optional
provider adapters are independently inventoried by System; a native
preparing manager needs no Nix prototype/catalog/binary adapter files merely to
inspect or prepare defaults. No managed data-schema family is advertised yet:
`state` is empty. Registry-format support
is distinct from knowing the schema of a service's database or configuration.

An old writer cannot gain support by adding a new sidecar claim: its declared
support must match the literal bundled declarations. The complete native
capability code must be retained/inventoried, with matching hashes/modes. This is measured
publisher/runtime declaration evidence, not a proof that arbitrary new code is
correct or authentic. Existing source trust and exact artifact bindings remain
necessary; hashes are not signatures.

## Both runtimes and actual observations

`mojt-management-context-v1` is a separate content-identified observation record.
It contains required `registries`, observed managed `state` and required `actions`.
Registry/schema observations bind evidence IDs; versions are positive integers,
never release strings or timestamps. Actions bind exact type/version/phase/
contract. Lists are bounded, sorted and unique; unknown wire versions fail.

The pure checker compares this context with **both** the preparing manager and
the candidate System runtime. Matching filenames, a newer package label or one
runtime understanding a format do not establish that the other can read/write
it. Every observed registry must be readable and writable. Managed state needs
an exact owner/location/family match and supported schema version for both
operations; parent-path support does not grant a child ownership claim. Required
handler phase and protocol must match exactly. The known defaults operation also
requires reader/writer support for its result registry before the first effect,
even when that registry is currently absent. Nothing executes during checking.

Actual target observation currently covers only the implemented lifecycle
registry at `state/var/lib/mojt/lifecycle/defaults-v1`. Existing Ports checks stay
in their established System-manifest preflight. Other management registries and
real service-schema observations are not claimed to be covered by this increment.
Future System composition readers must join their actual observations; a caller
cannot replace target facts with a supplied empty list.

The observer validates protected directories, installation/invocation identities,
known plan/approval/result shapes and hash chains under existing shared invocation
locks, without creating locks or files. Metadata scans are bounded: at most 128
invocations, 4096 record reads and 32 MiB of record bytes per observation, in
addition to each registry's existing limits. A missing registry means verified
absence, not invented version 1. Unknown lifecycle directories/versions, unsafe
links, corrupt records and incomplete initialization are errors, not absence.
Interrupted attempts or abandoned result temps block the transition until an
administrator explicitly reconciles them through the known defaults operation.

Reading a known older result must not require its handler code to be the
currently executing code. The structural reader therefore accepts intact known
records with earlier implementation references. This neither migrates them nor
grants authority to replay them: execution still rederives the exact plan from
the current handler, verified source and actual protected target. A stale plan
requires a new preparation/approval. Local file bytes are not inferred from old
completion records, and this registry observation is not readiness evidence.

## Integrated boundaries

- Fresh System finalization measures/inventories the sidecar and checks the
  copied target before image publication. A System without MPM cannot silently
  accept a target which already requires its lifecycle registry support.
- `mojt-system-inspect --target ...` reports the additional measured-management
  check when the candidate or target uses it. Its old `--context` mode still
  checks only the explicitly supplied ABI/layout/Ports facts; it does not infer
  unprovided management state or claim whole-system compatibility.
- Existing native Kernel/Base boot preflight checks the retained System's
  measured support against actual target state. The existing late `live_context`
  rechecks repeat the gate under publication locks before staging/selection.
  No changes are made to closed boot/context record formats or area scope.
- Missing required declarations block; an old System with no sidecar has unknown
  support, not an implicit fallback. With no observed requirement it remains
  usable under the existing narrow manifest checks. Already-built images are
  not patched and older executables are not retroactively upgraded by this file.

The checker resolves its own dependencies only from the executing manager's
fixed helper directory, restoring the import search path after inspection. It
never imports the candidate's handlers or uses Ports/host PATH for execution.

## Next gate and validation

Native System install/status/composition is next. It must retain exact inputs,
feed the management checker actual state and declared required actions, preserve
Base/Kernel choices and add a separate authorized initialization/service gate.
General lifecycle execution, service ordering, data migration, automatic fallback,
ready status and complete cross-registry capability coverage remain future work.

Automated coverage includes older readers/writers, incompatible owner/schema/
phase/protocol, both runtime roles, forged support, changed/missing code, no
candidate execution during measurement, actual completed/interrupted defaults
records and no-write refusals. Native boot tests inject unknown state before
staging/selection and immediately before menu publication. The focused CI job
runs real root-owned registry tests; existing Base, Kernel, runtime delivery and
System assembly regressions remain enabled. No new unchanged owner VM matrix is
needed for this metadata gate. Actual System/initialization activation will need
focused owner VM acceptance.
