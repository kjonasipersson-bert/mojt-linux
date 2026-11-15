<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt documentation

## Current behavior and usage

Start with the [Mojt Handbook](../doc/handbook/README.md) for normal use. These
references describe the implementation and supported limits at this commit:

- [Architecture](architecture.md) and [persistent state](state-layout.md)
- [MPM contract](mpm.md), [Ports](mpm-ports.md) and [management workflow](management-workflow.md)
- [System installation/boot updates](system-transition.md) and [native System packaging](system-packaging.md)
- [Base import](base-installation.md) and [Base boot preparation/selection](base-boot-staging.md)
- [Native-v2 selection](native-system-selection.md) and [handover](native-system-handover.md)
- [System assembly](system-nix-vm.md), [accounts](system-accounts.md), [console/time](system-console-time.md) and [manuals/environment](system-environment.md)
- [Preparation/audit policy](stage-fast-path.md), [boot verification](boot-performance.md) and [reusable initramfs](reusable-initramfs.md)
- [Handbook website build](handbook-web.md)

## Design and future work

The [manifesto](manifesto.md) states the goals. The [roadmap](roadmap.md) separates
current capabilities from future priorities. The [distribution contract](distribution-contract.md),
[lifecycle proposal](mpm-lifecycle.md) and [decision register](distribution-decisions.md)
include proposed policies; proposals are not implemented commands.

## Test procedures and historical evidence

[Test reports](reports/README.md) retain dated observations, measurements,
fixture labels, environments and historical implementation notes. Dedicated
acceptance guides describe repeatable test procedures; neither kind of document
is the current user/interface contract. Old reports may describe commands and
limitations superseded by later code. Use the Handbook/current references above
for normal administration.
