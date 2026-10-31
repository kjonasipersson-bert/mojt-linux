<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Command syntax: discussion before consolidation

The owner requested a coherent command language and a separate syntax discussion.
The System-runtime increment delivers existing commands; it does not settle new
verbs, add an `mpt` alias or rename MPM. Keep current scripts working while these
questions are resolved.

| Question | Current behavior / decision to discuss |
| --- | --- |
| Next-boot choice | `kernel stage/select/rollback` exist; consider a normal `activate` workflow while preserving install versus selection |
| Target selection | `--root` means a standalone registry/profile; `--disk-root` means a boot installation. Consider one consistent target model without reinterpreting old scripts |
| Overall status | Area-specific status exists. Define whether a future `mpm status` combines installed, selected, running and pending changes |
| Catalog selection | Discovery uses explicit `--catalog`; Ports also has saved provider/catalog policy. Define configured defaults and their provenance |
| Build environments | Define create/inspect/run/retain semantics and privilege boundaries before adding environment verbs |
| Bootstrap/build/package | Discuss the proposed `mojt` workflow tool alongside `mpm` content management; do not turn building into an implicit install step |
| Privilege and preview | Shared mutations require administration; decide which planning operations should also be available to ordinary users |

Preserve the agreed semantics regardless of spelling: metadata update does not
install, installation is distinct from activation, Kernel selection does not
change the running Kernel, System changes create coherent new generations,
and persistent data is not rolled back with program content. Maintain literal
search and exact identity/provenance rules. Examples of future syntax must be
labelled proposals until implemented and documented in `mpm(1)`.
