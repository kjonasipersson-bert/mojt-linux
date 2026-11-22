<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Test reports and development history

These reports preserve evidence, environments, limitations and historical
observations. Their local generation names (for example A/B or G/H), private
paths, dates and timings identify test fixtures, not product release interfaces.
Historical "next"/"pending" statements apply to the recorded revision. Use the
[Handbook](../../doc/handbook/README.md) and [current documentation](../README.md)
for how the code works now.

## Extracted historical records

- [Project introduction and validation history](README-history.md)
- [Activation and preparation performance measurements](activation-performance-history.md)
- [Architecture development history](architecture-history.md)
- [Native-v2 boot profiling and latency history](boot-performance-history.md)
- [Private build environment acceptance](build-on-mojt-history.md)
- [Private workspace image-build acceptance](build-workspace-history.md)
- [Kernel selection, shutdown and verification history](kernel-boot-selection-history.md)
- [Native Kernel build and packaging acceptance](kernel-build-history.md)
- [Source-installed Kernel boot acceptance](kernel-source-boot-history.md)
- [Installed Kernel source acquisition acceptance](kernel-source-install-history.md)
- [MPM consolidation planning and acceptance history](mpm-consolidation-plan-history.md)
- [MPM implementation-status history](mpm-implementation-history.md)
- [Local Kernel installation acceptance](mpm-kernel-history.md)
- [Ports experiment and acceptance history](mpm-ports-history.md)
- [Selector resolver and transaction acceptance](mpm-selectors-history.md)
- [Native artifact packaging acceptance](native-artifact-format-history.md)
- [Native image boot and module acceptance](native-image-build-history.md)
- [Native handover boot and writable-root acceptance](native-system-handover-history.md)
- [Reusable initramfs construction test results](reusable-initramfs-history.md)
- [Development roadmap history](roadmap-history.md)
- [Static shutdown and final unmount acceptance](shutdown-order-history.md)
- [Ordinary stage regression and performance history](stage-fast-path-history.md)
- [Persistent-state development and acceptance history](state-layout-history.md)
- [Accounts and session shutdown acceptance](system-accounts-history.md)
- [Administration tools and console acceptance](system-admin-tools-history.md)
- [Console, clock and persistent journal acceptance](system-console-time-history.md)
- [Diagnostics and USB database acceptance](system-diagnostics-history.md)
- [Timezone, manual pages and console-signal acceptance](system-environment-history.md)
- [Early System VM assembly and acceptance](system-nix-vm-history.md)
- [UEFI disk-copy boot acceptance](uefi-disk-boot-history.md)
- [Serial-console and interrupted-image-build acceptance](vm-serial-console-history.md)

## Dedicated test procedures and acceptance records

Existing dedicated reports retain their original paths:

- [Base boot/return](../base-boot-acceptance.md)
- [Native-v2 System boot/return](../system-boot-acceptance.md)
- [Writable-root boot and persistence](../writable-root-hardware-test.md)
- [MPM interaction and manual-page checks](../mpm-usability-hardware-test.md)
- [Kernel tracks and SSH acceptance procedure](kernel-tracks-ssh-test.md)
- [Generic PC hardware readiness and acceptance](pc-hardware-test.md)
- [Retained firmware generation and QEMU guest agent](firmware-generation-test.md)
- [Ports frontend/adapter](../ports-profile-acceptance.md)
- [Activation measurements](../activation-fast-hardware-test.md)
- [Initramfs payload reuse](../initramfs-payload-hardware-test.md)
- [Stage preparation measurements](../stage-fast-hardware-test.md)
- [Stage profiling](../stage-profiling.md)
- [Nix provider experiment](../mpm-nix-experiment.md) and [pacman comparison](../mpm-pacman-experiment.md)
- [Hardware-profile boot experiment](../thinkpad-usb-boot.md)

Reports distinguish automated fixtures, virtual machines and physical-machine
observations. A reported PASS is scoped to that report's inputs and checks; it
is not a general hardware, compatibility, security or performance guarantee.
