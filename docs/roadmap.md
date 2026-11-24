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
| Base | Whole-release construction, a standalone pinned source producer with shared table defaults, native import/realization/status, exact compatible boot selection/return and signed Base source upgrades | Physical source-Base acceptance and wider repository/channel policies |
| System | Coherent profiles, native composition/component import, live installation with boot preparation, prepared-entry activation and status | General service/runtime-dependency upgrades and state migrations |
| Kernel | Exact local/source installation, retained origin/modules, preparation/selection/return and pinned LTS/stable builds with a bundled configuration | Moving-policy acquisition and broader hardware coverage |
| Ports | Parallel versions, independent wishes, atomic profiles, explicit/following activation, history and active-version manuals | Native Port publication, cleanup and broader provider coverage |
| Filesystem | Writable persistent root/local storage, immutable selected releases, persistent configuration/data/homes | Explicit incompatible-layout and data/schema migrations |
| Interaction | Readable running/next/prepared entries, change/reboot previews and phase completion messages | Continued feedback on real administrative workflows |
| Installation | Offline whole-disk installation from prepared UEFI media, with Btrfs and optional partition-backed swap | Physical hardware acceptance and automated media builds |
| MBT | Private build environments, Kernel and source Base build/packaging with size reporting, fresh native-v2 bootstrap and signed Base catalog preparation | Native toolchain control and source builds of Mojt-owned System components |

## Next work for planning

The [signed Base repository prototype](native-repository.md) supplies the first
publication/acquisition path. Exercise an actual publisher-owned key and GitHub
Release, then the ordinary Base update in a repository-enabled System. Extending
that same boundary to native System/Kernel publication remains a separate step;
Nix-backed applications do not need to be republished as Mojt archives.

1. Validate the generic PC hardware profile on representative physical machines.
   The profile includes broader firmware inputs, udev probing and NVMe/SATA/USB
   early drivers; emulated boots do not establish physical firmware coverage.
   Existing ThinkPad selections retain their machine policy. Firmware data and
   the fixed optional QEMU guest service have a bounded transition contract;
   live machine-profile changes and other service migrations remain separate work.
2. Continue focused usability work and MBT development against the installed
   workflows. Keep activation a bounded atomic choice; construction belongs to
   preparation, and full audits remain explicit.
3. Complete physical source-Base acceptance against the
   [libc/shared runtime contract](libc-contract.md), and integrate the
   [producer](base-source-build.md) with a controlled toolchain in MBT. Extend
   pinned source builds to Mojt-owned System components using the existing
   native package format.
4. Add scoped retention/GC for accumulated generations and their unreferenced
   content, protecting running/next boot, deliberately retained recovery choices
   and application/toolchain/data references. Define the preview and explicit
   retirement boundary before provider-root release or physical deletion.

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
  live System and Base install include preparation; Kernel install integration is
  still separate. Offline/content-only import remains useful.
- Persistent configuration, databases and local files survive code changes and
  return. Schema rollback is not automatic.
- Required metadata, compatibility and publication checks remain even when full
  byte audits are disabled. Retained recovery content is preserved.

## Longer-term work

- Build Base and Mojt-owned System components from pinned sources/recipes on
  Mojt. Assembling prebuilt inputs and building a Kernel do not establish full
  source self-hosting.
- Extend the signed Base prototype to additional native categories and channel
  policies, with explicit key rotation/revocation and freshness contracts.
- Complete supported lifecycle/initialization/migration contracts without
  arbitrary package hooks.
- Add supported native Ports distribution, explicit retention/garbage collection
  and further version-policy/provider integration.
- Automate the production of bootable `install.img` media using pinned Base,
  System, Kernel and hardware-profile inputs. Include the offline tool closure,
  verify the resulting image with a two-disk UEFI smoke test and decide where
  the build belongs in the release workflow.
- Expand representative hardware and failure/recovery coverage as supported
  features change.

[Development/test reports](reports/README.md) retain historical results and
measurements separately from this current capability and priority list.
