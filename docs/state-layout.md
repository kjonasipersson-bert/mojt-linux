<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Persistent state and generation selection

Code generations and persistent machine data have independent lifecycles.
Selecting or booting older code does not restore an earlier filesystem snapshot,
configuration, account database or service schema.

## Native-v2 runtime mapping

The managed backing installation is mounted at `/run/mojt-disk`.

| Backing directory | Runtime path | Lifetime |
| --- | --- | --- |
| `state/rootfs` | `/`, including local top-level files/directories | Persistent |
| `state/etc` | `/etc` | Persistent configuration and identity |
| `state/var` | `/var` | Persistent service/package data |
| `state/home` | `/home` | Persistent ordinary-user homes |
| `state/root` | `/root` | Persistent root-account home |
| `state/local` | `/usr/local` | Persistent local software |
| Selected sealed boot Base tree | `/usr` and other reserved Base trees/files | Follows selected Base, read-only |
| Selected System profile | `/run/mojt-system` | Follows booted System, read-only |
| Selected Kernel module tree | `/lib/modules` | Follows booted Kernel, read-only |
| Temporary filesystems | `/run`, `/tmp` | Recreated at boot |

`/opt`, `/srv`, local mountpoints and administrator-created root paths live in the
persistent root. `/root` is a separate account home, not another spelling of `/`.
The [Handbook filesystem tables](../doc/handbook/part-iii/filesystem-layout.md)
are the complete user-facing path and generation-change reference.

## Initialization and compatibility

A writable-root handover initializes the marked root shell atomically on first
boot, not during stage. It projects immutable Base content rather than copying
it into writable machine data. It refuses an unmarked existing root, foreign
installation markers, unsafe mountpoints, changed reserved aliases and
incompatible top-level projections instead of silently overwriting data.

Existing persistent `/etc`, `/var`, `/home` and `/root` remain shared. Ownership,
permissions, credentials and files belong to machine state. Missing release
defaults may be added through supported preparation; existing configuration is
not silently replaced or removed. Stateful schema migrations require a supported
contract, and returning to older code does not reverse them.

Older entries keep their embedded mount code and can still use a read-only root.
They retain new root/local data on disk without exposing it through their older
layout. Returning to a writable-root deployment exposes it again. They continue
to share the established configuration, service-data and home mappings.

A Base with a different reserved top-level projection, or adoption of a foreign
nonempty root/home layout, requires explicit migration support. Do not change a
layout marker, delete state or hide local files underneath a mount to bypass a
compatibility refusal. See the [handover contract](native-system-handover.md).
