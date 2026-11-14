<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Activation performance and installed choices

`mpm system activate`, `upgrade` and `stage` (and their Base/Kernel equivalents)
can omit `--artifact` in a terminal. They list installed candidates by release
and full identity. Enter a number or `q`; invalid numbers prompt again. No
candidate is automatically selected. This list is metadata-only and does not
promise compatibility. Existing preflight checks decide that after the choice.
`--yes`, `--json` and noninteractive input require `--artifact` explicitly.

Activation displays the target, candidate, selected deployment and next-boot
effect before confirmation. The running system stays unchanged; old deployments
remain retained and reboot is deliberate. Progress and elapsed phase times go
to stderr, preserving JSON on stdout. Candidate checks, deployment preparation
and selection/publication are measured separately. Preparation includes its
own candidate recheck; those times must not be added as disjoint subphases.

Selection preview now validates exact metadata without a full content audit.
The final locked selection preparation still fully verifies every menu entry,
its trees, handover gates and management compatibility before atomic publication.
There is no persistent verification cache. Failed or stale gates refuse
publication, including for an existing staged candidate. To audit a preview:

```sh
mpm system select --deployment sha256:... --expected-selected sha256:... --dry-run --verify
```

This change removes one duplicate selection audit (two passes become one for
normal committed selection). Full activation still contains preflight,
construction, retention and admission checks; it is not yet a single-scan
pipeline. It also does not move required import/publication checks into an
optional verification mode. Explicit status verification remains available.

The owner reported roughly 5–10 minutes for the prior physical update, without
phase measurements. Capture stderr for a subsequent focused update and compare
phase times on the same machine. No measured whole-update speedup is claimed.
