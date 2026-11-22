<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Normal System operation and explicit audits

The normal installed System path accepts inputs at the operation boundary and
passes checked facts to its internal consumers. It does not use a full retained
history audit as the implementation of reading one deployment.

## Installation and preparation

Incoming archive structure, paths, types, ownership, modes, exact dependencies,
decompressor failures and new component stream checks remain part of import.
Each new immutable payload is durably published once. The profile projects its
components; firmware is not copied into another complete generation.

Under the preparation locks, the selected System and candidate are read into
checked in-process descriptions containing their receipts, composition, manifest,
components, provider references and declared management support. Shared component
facts are passed through the operation. These Python objects are not serialized
write authority. Public standalone saved-plan/constructor APIs retain their own
input acceptance and audit boundaries.

Normal preparation checks the new profile's links once, checks Base/Kernel/ABI
and startup compatibility, and constructs the required boot files. Final
admission rechecks selection bytes, installation/target identity and relevant
persistent account/Ports/layout facts. MPM locks do not prevent an administrator
editing persistent files independently. Required final file synchronization,
atomic publication and post-publication uncertainty handling remain in place.

A retained interpreter descriptor below `boot/mpm/runtime-descriptors/` is bound
to the exact runtime identity in the selected constructor, provider reference and
interpreter path. An unchanged runtime can reuse this accepted metadata before
checking the payload cache. Missing or changed runtime inputs need fresh
measurement. The first operation with an older installation can create this
metadata; later warm operations reuse it. Runtime files must still be available.

Cold production copies the accepted interpreter content directly into its private
initramfs tree. Source bytes are hashed against the accepted inventory while
copying. Disposable code/runtime copies do not use per-file durability flushes;
the published payload and deployment files do. The newc writer enforces supported
nodes, metadata and expansion limits, using explicit fast gzip compression
(level 1). The independent decompress-and-compare
check remains available through full verification and standalone producer tests.

## Boot

Normal early inspection binds the exact command line, running Kernel, deployment
and required roots. Handover checks the selected System's declared requirements
against actual persistent state, required account/start executables, defaults,
protected mountpoints and known registry formats. Its component receipt facts
are shared with the early reader when applicable.

It does not enumerate unrelated installed System objects, reconstruct their
realizations or replay the immutable startup comparison for every retained
entry. Startup acceptance was required before the exact manifest could be
admitted. Unknown persistent schema formats and incompatible current state still
refuse handover. Historical defaults invocation consistency and unrelated object
damage are explicit audit/repair concerns; current required defaults are checked
against their actual machine paths.

The existing serialized deployment, handover and receipt formats are retained.
Existing slots are not rewritten. Older installed readers retain their own
behavior; these changes apply to newly produced reader code and management tools.

## Selection and status

Reading running or next boot resolves only the requested deployment. Menu
structure, slot paths, command syntax and machine policy are checked without
opening unrelated handover receipts. Selection compares the old choice with the
expected choice, resolves the target admitted entry, preserves unchanged menu
blocks and atomically publishes the new menu. It rechecks current selection at
publication. Complete menu reconstruction remains part of explicit inspection.

Plain status lists protected metadata summaries. It does not establish current
payload integrity or rerun boot-readiness gates for each listed generation. A
prepared label identifies a retained admission record, not a new audit of its
contents. Selecting or booting an entry still validates that specific admission.
Use `--verify` for full retained archive/profile/provider/boot checks. The audit
paths continue to detect damaged content and inconsistent retained history.

Test orchestration observes running/selected identities directly. Full status is
a distinct usability check; it is not the implementation of every test invariant.
