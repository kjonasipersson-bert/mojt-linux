<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt development priorities

This roadmap distinguishes implemented behavior from future work. Command
references describe the code at this commit; proposals below are not implemented
interfaces. The [architecture](architecture.md) defines the area boundaries.

## Current capabilities

| Area | Implemented behavior | Main remaining boundary |
| --- | --- | --- |
| Base | Whole-release construction, native import/realization/status, exact compatible boot selection and return | Moving-policy upgrades and source/backend expansion |
| System | Coherent profiles, native composition/component import, live installation with boot preparation, prepared-entry activation and status | General service/runtime-dependency upgrades and state migrations |
| Kernel | Exact local/source installation, retained origin/modules, preparation/selection/return and pinned LTS/stable builds with a bundled configuration | Moving-policy acquisition and broader hardware coverage |
| Ports | Parallel versions, independent wishes, atomic profiles, explicit/following activation, history and active-version manuals | Native Port publication, cleanup and broader provider coverage |
| Filesystem | Writable persistent root/local storage, immutable selected releases, persistent configuration/data/homes | Explicit incompatible-layout and data/schema migrations |
| Interaction | Readable running/next/prepared entries, change/reboot previews and phase completion messages | Continued feedback on real administrative workflows |
| MBT | Private build environments, Kernel build/packaging and fresh native-v2 bootstrap | Complete source builds of Base and Mojt-owned System components |

## Next work for planning

1. Broaden firmware coverage. Define a supported hardware set and include the
   required firmware in System, rather than promising universal support.
   Keep firmware ownership and licensing explicit, and preserve independent
   Kernel selection and a retained recovery deployment.
2. Continue focused usability work and MBT development against the installed
   workflows. Keep activation a bounded atomic choice; construction belongs to
   preparation, and full audits remain explicit.
3. Extend pinned source builds beyond the Kernel to Base and Mojt-owned System
   components, reusing the existing build environments and native package format.

These are priorities for scoping, not a commitment to new command names or a
reason to repeat unchanged test matrices. Performance profiling remains available
when a concrete bottleneck justifies another change.

## Architectural constraints

- Base/System normally combine within declared requirements; version labels do
  not create compulsory release pairing.
- OS-area updates preserve unrelated Kernel/Base/System and Ports choices.
- Installed content is not automatically an upgrade wish. Upgrade scope follows
  recorded wishes and explicit requests.
- Preparation, next-boot selection and running identity stay distinct. Normal
  live System install includes preparation; Base/Kernel install integration is
  still separate. Offline/content-only import remains useful.
- Persistent configuration, databases and local files survive code changes and
  return. Schema rollback is not automatic.
- Required metadata, compatibility and publication checks remain even when full
  byte audits are disabled. Retained recovery content is preserved.

## Longer-term work

- Build Base and Mojt-owned System components from pinned sources/recipes on
  Mojt. Assembling prebuilt inputs and building a Kernel do not establish full
  source self-hosting.
- Define authenticated native release publication, signing and trusted channels.
- Complete supported lifecycle/initialization/migration contracts without
  arbitrary package hooks.
- Add supported native Ports distribution, explicit retention/garbage collection
  and further version-policy/provider integration.
- Develop bootstrap choices for directory targets, disk images and physical
  disks, with defined machine profiles and local/media/repository inputs.
- Expand representative hardware and failure/recovery coverage as supported
  features change.

[Development/test reports](reports/README.md) retain historical results and
measurements separately from this current capability and priority list.
