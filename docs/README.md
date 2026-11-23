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
- [Component System generations and optional firmware](system-components.md)
- [Normal System operation and audit boundaries](system-normal-operation.md)
- [Base import](base-installation.md) and [Base boot preparation/selection](base-boot-staging.md)
- [Build an independent Base from source](base-source-build.md)
- [Libc runtime ownership and shared boundaries](mpm-libc-policy.md), [System/Base ABI requirements](system-manifest.md#base-abi-requirements) and [optional libc inventory](libc-inventory.md)
- [Shared libc resources, responsibilities and open integration decisions](libc-integration.md)
- [Native-v2 selection](native-system-selection.md) and [handover](native-system-handover.md)
- [System assembly](system-nix-vm.md), [accounts](system-accounts.md), [console/time](system-console-time.md) and [manuals/environment](system-environment.md)
- [Preparation/audit policy](stage-fast-path.md), [boot verification](boot-performance.md) and [reusable initramfs](reusable-initramfs.md)
- [Handbook website build](handbook-web.md)

## Design and future work

The [manifesto](manifesto.md) states the goals. The [roadmap](roadmap.md) separates
current capabilities from future priorities. The [distribution contract](distribution-contract.md),
[lifecycle proposal](mpm-lifecycle.md) and [decision register](distribution-decisions.md)
include proposed policies; proposals are not implemented commands.

The [Base content inventory](reports/base-content-inventory.md) reviews the Void
construction inputs and packing rules as evidence for defining a source-built
Base. It does not change the current release contents or decide libc/ABI policy.
The [source-build and libc review](reports/base-source-build-review.md) proposes
a smaller input set and identifies compatibility gates and open runtime
questions. The [source producer](base-source-build.md) implements the first
private build path; runtime/boot acceptance remains a separate step.

## Test procedures and historical evidence

[Test reports](reports/README.md) retain dated observations, measurements,
fixture labels, environments and historical implementation notes. Dedicated
acceptance guides describe repeatable test procedures; neither kind of document
is the current user/interface contract. Old reports may describe commands and
limitations superseded by later code. Use the Handbook/current references above
for normal administration.
