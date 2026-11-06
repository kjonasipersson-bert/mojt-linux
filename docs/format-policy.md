<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Initial formats: fresh installations, explicit versions

Owner decision, 2026-11-01. There are no installations to support. Implement
the selected initial formats directly for new installations. Support for older
experiment files, automatic adoption/conversion, transitional layouts, dual
readers/writers and migration tooling is not an initial MPM requirement.
Earlier transition/backward-compatibility tasks in the design history are
superseded by this decision; historical experiment evidence remains historical.

Keep explicit format identifiers in user configuration, source/snapshot/request
records, locks/plans/approval, native descriptors/store/receipts, compositions,
boot and lifecycle records. `format = "mojt-configuration-v1"` is the proposed
TOML marker; machine records already carry named version markers. A missing or
unknown required version fails clearly before mutation; do not guess, silently
reinterpret it or implement an older reader solely for an experiment.

The proposed boot v2 names identify their schema and do not require an updater
from boot v1. Existing prototype code may remain as build/test material until
replaced; it is not a supported on-disk input for the new installer by default.
Future deliberate incompatible changes get new format versions. Designing an
actual migration can wait until a supported installation needs one.

This does not waive data integrity, source trust, authorization, atomic publication
or recovery. Within the new system, retained deployments must be compatible with
current managed state before use; code rollback still does not roll back data.
Capability checks and unknown-version refusal remain necessary for future safety,
without obliging the first implementation to consume every old format.

Implementation priority: normalized configuration and independently owned wishes,
then per-area state publication, acquisition/retention and complete deployment.
Use the [gap matrix](mpm-gap-matrix.md) and [format specification](formats/draft-v1/README.md).
