<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native-v2 System initialization and handover

This extends the [trusted initramfs reader](native-initramfs-reader.md) within
consolidation step 3. The explicitly enabled System constructor joins the
unchanged-startup preflight, prepares an immutable boot Base, rechecks current
state, attaches runtime mounts and transfers PID 1 to the retained System start.
It publishes no boot choice or new CLI. Verification-only mode remains available.

## Preparation and formats

`mpm_boot_handover.prepare` rechecks the compatible System preflight under the
shared store/install/boot/Kernel and existing Ports locks. It preserves the
selected exact Base/Kernel and binds candidate, installation, root UUID, reviewed
baseline manifest and measured recovery support. Providers explicitly project
their boot mount namespaces; package hooks are never executed.

The existing native Base extractor creates a separate rootfs copy, preserving
content, modes, ownership, xattrs and hardlinks, with only the reviewed empty
mountpoint additions. Original installed Base content is unchanged. The sealed
result lives under `realizations/boot-base/FULL_REALIZATION_HEX/tree/rootfs`.
Exact reuse verifies it. Directory publication uses staging/fsync/rename and
retains possibly committed content after uncertain flush failure. Incomplete
private work may remain for diagnosis; no defaults or user data are changed.

| Record | Closed description fields |
| --- | --- |
| `mojt-boot-base-realization-v1` | `installation`, `base`, `source_realization`, `inventory`, `scaffold`, `extractor`, `code` |
| `mojt-system-handover-v1` | `inputs`, `preflight`, `baseline_manifest`, `baseline_support`, `base_facts`, `boot_base`, `mounts` |

Both use the common canonical envelope/full SHA256 ID. The embedded handover
contract is bound by the final initramfs archive without a hash cycle. Constructor
identity distinguishes verification-only and System-handover purposes.

## Current-state and runtime gates

Normal handover checks exact input/slot metadata and required roots without a
full content scan. It checks boot Base metadata/containment, candidate manifest
and unchanged-startup review. Preparation and explicit full-audit mode additionally
verify every retained tree and the boot Base inventory. It observes current
state layout, Ports format/capabilities, management registry compatibility for
preparing/candidate/recovery code, and already-present defaults. Unsupported
migrations or missing defaults block before writable mounts. Historical passwd
contents are not required: compatible local account/configuration edits persist.
Account shells and System start resolve in the future guest namespace, never
against host files, and must belong to retained immutable content. Mutable-state
executables cannot qualify. Required mountpoints must be real empty directories.

After these checks the backing filesystem becomes writable. New handovers bind
`state/rootfs` as writable `/`, then project the selected Base's immutable
top-level trees/files read-only (normally `/usr`, with canonical Base aliases).
System and native modules bind read-only; `/etc`, `/var`, `/home` and `/root`
retain their existing persistent mounts. `state/local` binds writable at
`/usr/local`; `/opt`, `/srv`, `/mnt`, `/media`, `/boot` and custom root paths
remain in the persistent root directory. `/run` and `/tmp` are tmpfs. Provider namespaces remain writable for later
imports, but each retained System dependency gets a read-only bind. The separate
Nix boot adapter projects today's `nix` namespace; core handover uses declared
paths. New namespaces require supported empty mountpoints and cannot cover
Base/state/runtime paths.

The existing static shutdown script is staged under `/run/initramfs`. Early image
mounts, including dependency objects, get runtime mount-unit policies keeping
them until static exitrd cleanup. Handover moves `/dev`, `/proc`, `/sys`, then the
backing disk, and execs static BusyBox `switch_root` to `/run/mojt-system/start`.
Its normal unchanged setup/services run; no general lifecycle executor is added.
The root is atomically initialized at first boot with an installation-bound
`mojt-writable-root-v1` marker, never during stage. The marker binds the
immutable top-level projection, not a Base release ID. Compatible Base changes
reuse the same machine directories. Unknown roots, foreign markers, changed
reserved aliases/mountpoint types, incompatible projections and hidden files
under reserved mountpoints are refused rather than overwritten. Base `/usr/local`
must be a real empty mountpoint; sealed boot Base scaffolding adds it when absent.
No persistent-state layout-version bump, automatic migration or change to old
boot records is made. Older entries retain their embedded read-only-root behavior
and keep new root/local data without exposing it. See the
[Handbook filesystem chapter](../doc/handbook/part-iii/filesystem-layout.md) for
the complete persistence and generation-change rules.

On a pre-exec failure, completed moves/binds are reversed and backing read-only
mode is restored when possible. No forced/lazy unmount or successful-cleanup
claim hides errors; the diagnostic shell remains the failure path. Successfully
published root scaffolding remains after a later failure and is reusable;
existing persistent files are never rolled back or removed.

Runtime evidence is separately versioned at `/run/mojt/native-v2.json`, with the
complete deployment/input identity. It is never forged as v1. [Atomic selection/status](native-system-selection.md) now consumes admitted
constructor results and preserves the distinct runtime identity. V1 writers refuse
a v2 authority. The public native-v2 install/preparation/activation workflow is
described in [boot updates](system-transition.md).

`/run/mojt/boot-checks.json` separately records normal/full-audit mode and the
metadata-reader/current-state durations. Normal mode reports
`content_verified=false`: the runtime identity is not a new payload integrity
attestation. It does not write verification results into persistent state.

## Scope

The handover gate preserves startup/services and provider runtime dependencies;
it does not authorize arbitrary hooks, general service upgrades or schema
migrations. MBT reuses the native installation/handover APIs for fresh bootstrap.
Complete source builds of Base and Mojt-owned System components remain separate
from assembling retained prebuilt inputs. See the [roadmap](roadmap.md).
