<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Ports wish removal and active-choice reset

This bounded follow-up advances steps 1–2 of the
[governing six-step plan](mpm-consolidation-plan.md), using the existing request,
exact-lock, profile and history publisher. The pure operations in
`mpm_requests.py` perform no I/O and do not inspect any provider. System already
delivers this module and the common frontend; no new data format or migration is
needed. This does not complete all remaining MPM milestones.

| Command | Released reason | Preserved reasons/content |
| --- | --- | --- |
| `mpm ports remove hello` | All interactive wishes and active overrides for role hello | All configuration wishes and their adopted documents |
| `mpm ports remove hello@2.12` | Matching interactive series wish | Other wishes and independent exact active pin |
| `mpm ports remove hello --source local` | Interactive wishes bound to local | Other source wishes and independent exact active pin |
| `mpm ports reset hello` | Interactive active override only | All installation wishes; restores adopted explicit configuration default |

The exact active override is an independent retention root. A selector-qualified
release therefore can leave the default executable available while its series
alias disappears. A bare role release also releases that role's interactive
selection root. If a configuration still owns the package it remains in the
profile; removal never silently edits the configuration document. Plans show
which wishes are removed and how selection origin changes.

Reset returns control to explicit defaults in the already adopted documents.
It does not reread files or react to a missing file as an empty configuration.
Conflicting configured defaults previously masked by an interactive override
block reset atomically. With no explicit configured choice, the existing
installed fallback rules retain the previous eligible default or choose by
committed activation/install order. Reset does not invent a floating wish.

These operations use accepted exact targets and `advance=[]`, including when
new catalog metadata has withdrawn those targets. No source input/refresh or
new payload acquisition is permitted as a side effect. Content still referenced
by the resulting profile is verified before publication through the same adapter
contract. No alternate transaction/rollback implementation is introduced.
The same single pointer commits released wishes, effective choice, aliases and
linked history. Repetition creates neither another profile nor history event.

Preview before applying:

```sh
mpm ports remove hello@2.12 --dry-run
mpm ports remove hello@2.12 -y
mpm ports reset hello --dry-run
mpm ports reset hello -y
```

The existing administrator and target ownership gates apply before operator input
or provider work. Read-only commands keep their existing permissions. A missing
profile is refused without creating a registry. Existing profile metadata is
version-validated; removal/reset do not import experimental stores.

This is logical wish/selection management. It does not delete provider objects,
GC roots, old profiles, shared dependencies, user data or boot content. Removing
one historical artifact by full reference ID, physically collecting bytes and
forgetting an entire named configuration source remain separate work. A bare
unknown role or already absent interactive wish is an unchanged no-op.

Validation: pure ownership/revision tests cover independent sources, exact pins,
input immutability, conflict refusal and repeated operations. Joined frontend
filesystem tests execute retained commands, verify restored configuration control
after metadata withdrawal, check alias removal with retained bytes/history, and
make acquisition fail if accidentally attempted. The shared publisher's failure
and stale-plan regressions continue to apply. These reversible metadata/profile
operations do not require repeating the unchanged VM boot matrix.
