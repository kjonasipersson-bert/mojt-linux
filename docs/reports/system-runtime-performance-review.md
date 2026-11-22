<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Review: normal System installation, preparation, status and boot

Reviewed source: `a87481c9812eff444d7ea0191feb14a3d82f8398`.
This is an engineering review and proposed work plan, not the current user
interface contract. No production changes are included in this report.

## Conclusion and scope

Component profiles remove the large materialized firmware/profile copy, but the
normal operation still assembles many independent inspector APIs. Those APIs
repeatedly read, validate, canonicalize and copy the same evidence. Several also
expand an exact operation into a review of unrelated retained history. The
existing operation-local cache reduces some reads but still performs substantial
filesystem work on a hit.

The next change should reduce the scope and number of operations before tuning
JSON encoding or adding more caches. External records still require validation
at their entry boundaries. Mutable machine state and selection still require
checks at publication. Immutable facts already checked inside that transaction
should be passed to the next internal step.

Scope: the ordinary public System install frontend, content import, native-v2
preparation and selection, status, early reader/handover, provider integration,
the initramfs producer and the component acceptance helper. This is not a review
of every Ports operation, Kernel compilation, signing or garbage collection.

## Findings, ordered by priority

### R1 — boot and preparation inspect unrelated installed history

`mpm_boot_handover.check` calls `mpm_management.observe_target`.
`observe_target` calls `mpm_system.registry_observation`, which opens every
System object and realizes every installed generation, and then calls
`required_capabilities`, which walks the objects again. It also calls
`mpm_boot_selection.observation`, which reads every entry in the selection menu.
The same management observation is made during transition preparation.

Purpose: determine managed-format support, compatibility and recovery capability.
The purpose is valid; checking all artifact contents/realizations is excessive
for booting one already admitted deployment. It also makes unrelated damaged
history capable of blocking normal boot.

Proposed boundary: inspect actual persistent schema/registry formats and the
selected deployment's exact dependencies. Establish the recovery capability
contract when changing managed formats or publishing a selection. Keep the
full retained-object consistency walk in explicit audit/repair. Replacing the
walk requires a clear format-support contract, not an assertion that old objects
do not matter. Prefer existing small records; avoid a new general cache service.

Sources: `mpm_boot_handover.py:176`, `mpm_management.py:303`,
`mpm_system.py:123,807`, `mpm_boot_selection.py:241`.

### R2 — reading one selected entry expands all boot receipts

`mpm_boot_selection.current` calls `ready` for every menu entry. Each `ready`
opens a slot's sidecars, validates the deployment, proof and handover contract.
`available` separately performs the same work for every prepared receipt.
Transition setup reads `current`; normal staging then reads `available` to find
an existing exact deployment and to obtain reusable proof measurements.
Selection preview and locked application both call `current` again.

Purpose: bind the menu to admitted entries and preserve atomic selection.
The selected entry and requested target need exact checks. Unchanged entries do
not need their complete handover reconstructed at every read. The menu's own
bounded structure and paths must still be checked.

Proposed boundary: separate reading the selection record, resolving a specific
admitted entry, enumerating display summaries and auditing all entries. Pass the
already resolved selected/target entries through the locked operation. Preserve
the final compare with the actual selection bytes and installation identity.
Initially, an exact-match search can use bounded small summaries; do not decode
full handovers merely to decide whether their input IDs match.

Sources: `mpm_boot_selection.py:65,155,209,268`,
`mpm_system_transition.py:291`, `mpm_boot_update.py:93,188`.

### R3 — immutable System facts are repeatedly reconstructed

`realization` reopens the generation object, composition, each dependency and
profile manifest. `retained_providers`, `native_components`, management readers
and logical-inventory expansion independently ask for overlapping facts.
`realization` itself has no checked-result context, even when its object reader
can reuse metadata. Complete records are validated again after a cached read.

Purpose: exact object/receipt/composition/profile bindings. Keep this validation
when accepting an independently supplied installed object. Avoid reconstructing
the same bindings at every internal call.

Proposed boundary: one transaction-owned set of checked Base, System, Kernel,
component and provider facts. Pass explicit facts to internal functions. Do not
expose an unchecked JSON plan as authorization. Retain checks for replacement or
missing referenced objects at the relevant boundary; inspect mutable state
separately. This is a replacement for redundant internal reads, not another
transparent cache around every existing inspector.

Sources: `mpm_system.py:117,138,265,292,559`,
`mpm_system_transition.py:331`, `mpm_boot_v2_store.py:35`.

### R4 — cache hits still walk protected ancestors repeatedly

`mpm_native_io.preparation_cached.signature` resolves each supplied path and
walks every parent. An object lookup supplies overlapping paths for registry
directories, lock files, the object directory and its sidecars. A hit still
constructs this whole signature and deep-copies the result. A miss constructs
the signature both before and after the read. Cached JSON can then be copied
and validated again by its caller.

Purpose: prevent stale process-local facts from hiding replacement or unsafe
paths. Preserve that property, but establish common protected ancestors once at
transaction entry. Use explicit checked objects and held handles where useful;
recheck specific mutable bindings rather than repeatedly resolving every
ancestor of every field. Do not introduce persistent caches with undeclared
invalidation rules.

Source: `mpm_native_io.py:54`.

### R5 — normal preparation checks the complete link set twice

`mpm_system_transition._prepare` calls `system.verify_links`.
`mpm_boot_update._stage_locked` subsequently calls `store.audit_inputs`, which
calls `verify_links` again, alongside repeated Base/System/Kernel identity work.
For component profiles, `verify_links` expands descriptor inventories and
resolves each symlink into native/provider content.

Purpose: reject escapes, loops, dangling paths and undeclared provider targets.
That is an acceptance requirement for new content. Repeat checks of unchanged
immutable content belong to explicit audit or a genuinely independent entry
point. Normal boot still needs the executable and required mount roots it will
actually use.

Proposed boundary: verify the new link set once before admission and pass the
checked result through construction. Let standalone APIs validate their own
inputs. Do not run their complete acceptance sequence again when called from
the already checked locked transaction.

Sources: `mpm_system.py:322,359`, `mpm_system_transition.py:367`,
`mpm_boot_update.py:142`, `mpm_boot_v2_store.py:35`.

### R6 — nested handover evidence is repeatedly replayed

`mpm_boot_handover.validate` validates nested input/preflight/Base records and
the full baseline manifest. `mpm_boot_v2.envelope` canonicalizes to check an ID,
canonicalizes again for a size limit, then deep-copies the description.
`ready`, slot inspection and later handover checks repeat those operations.
Handover also recomputes `transition.profile_review` at boot against the saved
baseline, even though startup acceptance was a prerequisite to admission.
Legacy-to-component conversion can expand firmware descriptor metadata during
that replay without reading firmware bytes.

Purpose: bind exact immutable startup inputs and recheck current-state needs.
The immutable startup decision and the mutable current-state check should be
different operations.

Proposed boundary: validate a supplied envelope once, retain its parsed bounded
description/identity, and consume it internally. A compact admitted boot contract
should contain the facts boot needs, not require replaying the full development
preflight and baseline comparison. Review compatibility with retained readers
before changing a serialized format. Optimize the traversal count before
changing canonical encoding; encoding changes would alter artifact identities.

Sources: `mpm_boot_handover.py:37,176`, `mpm_boot_v2.py:31,66`,
`mpm_boot_v2_store.py:84`, `mpm_system_transition.py:139`.

### R7 — a warm payload still needs a complete runtime inventory

`describe_runtime` snapshots every exported interpreter-closure tree and checks
its links before the payload-cache lookup. The resulting complete inventory is
embedded in a runtime descriptor. Thus a cache hit avoids reconstruction but
does not avoid measuring the runtime first.

Purpose: choose the exact trusted interpreter and bind the payload inputs.
For an unchanged retained interpreter, use its already accepted exact identity
and runtime receipt to find the payload. Measure a newly accepted runtime, a
missing cache or an explicit audit. Runtime availability and root bindings still
need checks. This requires binding the stored runtime receipt to the accepted
provider identity; a path string alone is insufficient.

Sources: `mpm_boot_update.py:116`, `mpm_boot_constructor.py:60,221,234`.

### R8 — cold initramfs production repeatedly reads its own private output

The runtime path can be inventoried by `describe_runtime`, copied and checked by
`clone_runtime`, inventoried again in `assemble`, copied and checked a second
time by `clone_runtime`, then read by `write_initramfs`. The writer compresses
the archive and unconditionally decompresses/hashes it against a fresh inventory
of its private tree using `inspect_initramfs`.

Purpose: exact input acquisition, copy integrity and writer correctness. Hash
bytes while copying/serializing and enforce actual archive sizes/paths there.
The independent pack/unpack/fixture comparison is a strong regression test and
explicit audit candidate. Assess the writer's streaming checks before removing
it from normal operation; do not replace it with a blind copy.

Also benchmark explicit compression settings and peak memory for the cold
producer. The current writer holds complete buffers and performs compression
followed by decompression. No compression change can explain or fix all work in
the warm path.

Sources: `mpm_boot_constructor.py:76,305`, `mpm_boot_inventory.py:134`,
`mpm_kernel_boot.py:254`, `mojt_native_image.py:287`.

### R9 — provider work scales with references, not unique required work

Each retained reference is inspected independently. The Nix boot adapter checks
roots, closure paths and exported commands on every call; its query cache only
removes repeated identical query sets. Overlapping closures and equivalent
required output checks still repeat path work. Normal content import also
invokes `--realise` for each exact reference, including already retained ones.

Purpose: acquire missing binary outputs, retain GC roots and refuse unbound
provider paths. Keep substitution/signature policy and provider exit-code
handling. Group required output/root work once per operation, deduplicate
overlapping paths, and consider a fast reuse path for already accepted retained
outputs. Keep fresh database/content closure audits explicit. Changing the normal
database-check policy requires a documented provider contract and refusal tests.

Sources: `mpm_system.py:96,103`, `mpm_nix_boot.py:14,39,74`.

### R10 — status and the acceptance helper expand diagnostic work unnecessarily

`system.status` resolves every generation and its dependencies, reads manifests
again, then resolves every prepared boot receipt. `description` and `unwrap`
revalidate the same deployment repeatedly while constructing output rows.
The component helper invokes full `system status` five times during successful
preparation to observe the same running/selected identities. These checks run
outside its measured install calls.

Purpose: display retained history, and prove that a test did not change the
selection. Listing history inherently depends on its length; it should not
require replaying full boot-readiness and component inspection for each row.
The helper needs direct exact running/selection reads, plus its targeted
persistent-state comparisons. Keep complete status as a separate usability
check, not the implementation of every test invariant.

Sources: `mpm_system.py:830`, `mpm_boot_status.py:16,33,59`,
`mpm_boot_selection.py:247,268`, `mojt-system-firmware-test.py:72`,
`mojt-system-components-test.py:73,140`.

### R11 — lower-priority durability, reuse and import candidates

- `controls` uses a durable file-copy helper for disposable initramfs code trees.
  Cold runtime copying does the same. Scratch needs correct bytes and ownership;
  final published payload/slot files need durability. Keep final file and parent
  directory synchronization. Do not disable synchronization globally.
- Cached payload reuse hashes its archive and synchronizes unchanged cache
  directories. Archive bytes must be read to construct the concatenated result;
  whether a hash belongs on every reuse is an explicit integrity-policy choice,
  not a free optimization. Avoid unrelated directory synchronization on reuse.
- The final initramfs is written to a temporary file, then copied/hashed/synced
  into its slot. Consider direct private-slot construction/promotion on the
  publication filesystem. Preserve cross-filesystem fallback and publication
  uncertainty behavior.
- The heavy payload key hashes whole general helper modules. Changes unrelated
  to emitted heavy payload can invalidate it. Separate the actual payload
  producer identity from unrelated manager implementation changes; continue
  invalidating on every input that affects payload bytes.
- Boot-Base preparation searches all retained boot-Base records and runs GNU
  tar discovery on reuse. Fresh scaffolding invokes full Base copy/compare paths.
  An exact retained scaffolding reference should avoid rebuilding or re-auditing
  unchanged Base content. A newly generated scaffold still needs its path/layout
  and durable-output checks.
- Import owns a useful single-pass extraction path already. Avoid further
  profile copies. Examine repeated descriptor validation before reducing the
  remaining necessary new-payload writes. Mode-fix synchronization is conditional;
  it is not correct to describe every imported file as synchronized twice.

Sources: `mpm_boot_constructor.py:221,234,275`,
`mpm_boot_selection.py:128`, `mpm_boot_v2_store.py:130,156`,
`mpm_boot_base.py:45`, `mpm_base_boot.py:98`, `mpm_system.py:662,703`.

### R12 — System package production and execution-cohort checks repeat reads

The general archive packer inventories its input, writes/compresses the archive,
inventories the source again, verifies the complete output archive, reads it
again for the transport hash, and synchronizes the archive again with the
sidecars. Mutable source capture needs a coherent checked snapshot; a separate
full writer round trip is a test/audit candidate once that capture and the
streaming writer have the required invariants. Compute transport hashes while
writing where practical. Keep the required final durable output publication.

The MBT execution cohort is deliberately frozen before importing it, and the
child validates it again. The component helper then reads the cohort resources
again for packaging. Distinguish the necessary mutable-checkout capture and
child trust boundary from rechecking an already accepted private frozen cohort.
Do not make generic whole-builder resource copying the normal implementation
of every installed command. This review ranks these below the history/boot
path issues; the protocol still needs a trustworthy code/input boundary.

Sources: `mojt_artifact.py:329`, `mbt_runtime.py:91,118`,
`mojt-system-components-test.py:44,73,140`, `mojt_system_package.py:183`.

## Local structural probe

An isolated root-user-namespace probe used the existing
`test_system_install_transaction.InstallationTransaction` fixture. Its initramfs
producer is simulated; archives, installed objects and normal gate/status
readers are real. The selected deployment remained unchanged. Additional
unselected installed generations came from `fixture.f.f.candidate()`.
Python function-call instrumentation counted the normal handover gate, without
requesting a content audit. These are local synthetic counts, not target-machine
timings or full boot evidence.

| Installed System generations | `object_record` calls | Actual `_object_record` calls | `realization` calls | `artifact.canonical` calls |
| --- | ---: | ---: | ---: | ---: |
| 2 | 12 | 12 | 2 | 219 |
| 6 | 36 | 36 | 6 | 519 |
| 10 | 60 | 60 | 10 | 819 |

At ten generations, the object callers were `registry_observation` (20),
`realization` (20) and `required_capabilities` (20). Normal boot currently has
no preparation cache scope, so these object reads were real reader calls.

A separate warmed preparation-scope probe made 50 lookups of the same generation
object. It made no `_object_record` reader call, but still made 500
`Path.resolve` and 3,600 Python-level `Path.stat` calls. A high `object_record`
call count therefore does not itself mean the same number of archive/data reads;
both the call graph and the cache-hit work matter.

## Safety requirements for the replacement path

| Boundary | Required work |
| --- | --- |
| Incoming archive | Expected identity, bounded structure/size, member paths/types/links/modes, new component stream checks, decompressor/provider failures |
| Locked preparation | Exact selected and candidate bindings, Base/Kernel/System compatibility, new startup/link acceptance, required persistent schemas/defaults/account shells |
| Final admission/publication | Current selection and target identity, relevant persistent-state changes, exact built result, durable private output and atomic publication |
| Normal boot | Exact selected/admitted input binding, required roots/executables/mounts, installation/Kernel identity and actual persistent-state compatibility |
| Explicit audit | Retained archive/file hashes, complete inventories and history consistency, independent archive round-trip checks where requested |

An existing immutable result is not authorization to ignore changed mutable
configuration. Locks do not prevent an administrator editing persistent files
outside MPM. Cheap, targeted final checks must remain. Public standalone saved
plan/constructor APIs must still validate their independent input boundary.

## Proposed implementation and acceptance

Make one coherent normal-path change covering R1-R7 and R10: direct selected-entry
access, a checked transaction context, targeted boot gates, one new-content link
check, reuse of accepted runtime facts and narrow test observations. Preserve
standalone/audit entry points. Include any necessary compact boot-contract change
with explicit retained-reader compatibility rather than hiding it in a cache.

Then address the cold producer in R8/R11 as a separate production operation with
streamed input checks and durable final output. R9 and remaining R11 items have
lower priority unless a profile of the reduced path demonstrates otherwise.
The packaging/cohort work in R12 is also secondary to the normal boot and warm
preparation path.

Acceptance should test structural limits, not fragile stopwatch thresholds:

- Add unrelated retained generations/entries; normal boot must not open or
  realize those generations to start the selected deployment.
- Measure unique immutable objects and cache-hit filesystem work, not just
  logical public-reader calls. Check the new acceptance boundary once; internal
  consumers must not silently rerun it.
- A warm Runtime update must not snapshot the unchanged interpreter closure,
  open/repack firmware or duplicate profile payloads.
- Preserve refusal for unsafe archives/links, missing selected dependencies,
  incompatible state/Kernel/ABI and selection/state changes before publication.
- Preserve atomic failure/retry, uncertain publication and explicit audit damage
  detection. Unrelated broken history should remain discoverable by audit.
- Report production install/preparation time separately from test orchestration.
  Reuse retained local inputs for subsequent measurements. Require a physical
  reboot when boot behavior changes, and a return boot when reader/storage-format
  compatibility changes; ordinary timing-only checks need neither by default.

No wall-time saving is promised by adding overlapping function times. The review
identifies removable work and its required replacement boundary; the next
measurement must confirm the resulting production operation.
