<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native-v2 boot performance investigation

The accepted System A/B/A VM showed roughly 24 seconds between the early Kernel
messages and backing-filesystem remount, before systemd started. This identifies
the early-boot interval, not its cause. Performance acceptance remains open;
the successful functional boot/return acceptance is not a latency measurement.

## Measure the existing graph first

Run `tools/mojt-boot-profile.py` as root with the selected System's Python on the
existing accepted native-v2 VM. The script loads the **installed** manager from
`/run/mojt-system/tools`, observes its unchanged calls, and checks the running
deployment's retained proof/handover receipt. It does not import a replacement
manager from a checkout. The deployed initramfs and measured code stay intact.

It times loading the reader, reading the running record/receipt, exact early
verification, and the current-state/boot-Base gates. Nested measurements include
individual tree scans, retained Kernel/initramfs file hashing, canonical JSON,
slot inspection and handover validation. These nested totals overlap the phase
durations and must not be added together. The default report prints a compact
summary and eight slowest trees; `--json` emits all observations and exact
deployment identity under `mojt-boot-profile-v1`.

The probe never calls `enter()`/`_enter()`, mounts/remounts, publishes a menu,
writes package/state records, executes a provider or clears caches. File reads
can populate caches and update access times on writable filesystems. As with
other integrity checks, run without concurrent installation or state edits.
An existing verification refusal is propagated, not relaxed for the measurement.

This is a **running-system recheck**, using the installed interpreter and
possibly warm caches. Its timings are not cold-boot claims: they exclude Kernel,
initramfs decompression/module loading, the private interpreter startup, mounts
and switch-root. Timer wrappers add small observer overhead. If its phases do
not explain the observed delay, instrument the actual initramfs boundaries next;
do not conclude that a fast warm scan explains a slow cold boot.

## Fix and close the follow-up

Use the measured dominant work to choose one focused change. Preserve content,
metadata, link/mode/owner/xattr checks, exact identities and current-state gates.
Do not substitute a persistent cached checksum for reading mutable backing
storage. Distinct Base realization/scaffold trees are distinct verification
inputs, even when much of their content is equal.

Compare before/after on the same graph with cache conditions stated. Then time
one fresh boot with the updated constructor, proving that it reaches the same
exact deployment and clean runtime. Another A/B/A matrix is unnecessary unless
the change affects staging, selection, mounts or return behavior. Record phase
times and the remaining cost before closing the performance follow-up.

Status: diagnostic probe implemented; owner graph measurement and optimization
are pending. A local 10000-small-file experiment found roughly 0.29 seconds per
inventory on the development host; that synthetic warm result does not explain
or reproduce the owner's 24-second early-boot interval.
