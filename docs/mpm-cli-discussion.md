<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MPM syntax is retained; new-tool syntax belongs to MBT

The owner clarified on 2026-10-31 that the existing MPM syntax is satisfactory.
The requested discussion concerns **MBT**, the Mojt Build/Bootstrap Tool. The
earlier spelling `mpt` was not a request to rename MPM or add an alias.

Keep existing MPM commands and scripts working. Implement the remaining Base
and System workflows using the accepted area/action semantics; this work does
not require replacing `stage/select`, renaming target options or inventing a
new overall command language.

See [MBT syntax discussion](mbt-cli-discussion.md) for new tooling and
[the MPM gap matrix](mpm-gap-matrix.md) for the remaining implementation joins.
