<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Exact installed boot updates

`mpm system activate --artifact sha256:FULL_ID` selects an already prepared
System boot entry for the **next boot**. It performs bounded metadata checks and
atomic selection only. It never constructs initramfs or rescans package/provider
content. If no entry exists, prepare it with `stage` first. `upgrade --artifact ID`
combines preparation and selection for an explicit installed update target.

```sh
mpm system install --from-file SYSTEM.tar.zst --expected-id sha256:FULL_ID -y
mpm system stage --artifact sha256:FULL_ID -y
mpm system activate --artifact sha256:FULL_ID -y
mpm system status
# Reboot deliberately, then inspect status again.
```

System installation takes exact component archives through `--dependency-file`,
or obtains them from one accepted named-source snapshot. Default installation
performs required materialization without retained-content or provider scrubs;
`install --verify` explicitly adds these integrity checks. Installation never
selects next boot. Base and Kernel use the same preparation/activation split on
native-v2; Base preparation needs `--base-context FILE` with exact Kernel bounds.
Direct `select` and `rollback` use `--expected-selected ID`. Their default path
checks metadata; `--verify` explicitly audits retained content before publication.
See [operation boundaries](activation-performance.md).

The remaining preflight/constructor sections describe **preparation**, invoked by
`stage` and `upgrade`, not ordinary `activate`. Their `--dry-run` performs preflight
without writing runtime bundles, boot trees, slots or the menu. There is no
public `mpm system plan` operation. Preparation uses the mounted installation,
its delivered Python, static BusyBox and helpers. It freezes the running manager's
retained interpreter closure; candidate Python is never run. An offline target
cannot borrow the host's unrelated store/runtime.

The authoritative native-v2 selection is the baseline, even when another
combination is still running. Exactly one of Base/System/Kernel changes; the
other two and the machine's boot policy stay fixed. Previous deployments remain
retained. No existing installation is reformatted, and no reboot is performed.
Damaged native-v2 metadata never falls back to the old image-preparation format.

This first joined updater accepts **explicit exact installed candidates**. It
does not refresh sources, select a moving release policy or create new tracking
wishes implicitly. Catalog-driven moving Base/System/Kernel upgrades remain
future work. Existing Ports request/upgrade semantics are unchanged.

## Evidence and gates

Internal preflight records bind:

- Physical target/installation identity, selected deployment, root UUID and full
  menu checksum. Existing shared read locks are used without creating locks.
- Exact retained Base artifact/receipt/realization, Kernel artifact/image/module
  identity and bounds bound to that exact Base.
- Candidate System artifact/receipt/realization, composition, measured manifest,
  human label and unavailable runtime outputs.
- Actual Base ABI/state layout, current Ports format and persistent account
  shells. ABI facts come from the verified Base, not the candidate System.
- Measured management compatibility, provider preservation, startup review and
  missing-default observations. Account/provider paths are confined to the
  retained Base or accepted provider closure; host files cannot satisfy them.

Current menu, target identity and observed state are checked again before the
result is returned. The internal `recheck` recomputes the complete plan and
refuses changed inputs. A saved result is information, not permission to execute
effects. No wishes, configuration, cache, registry, slot or boot pointer changes.

## Planning from an active native-v2 installation

Internal System preflight supports a selected native-v2 baseline. Its result uses
`mojt-system-transition-preflight-v2`; the fresh-image v1 result is unchanged.
V2 plans additionally bind `baseline_format`, `baseline_entry`, `selected_inputs`
and `selected_system` (exact artifact/composition/manifest/generation plus receipt
and realization IDs). Base/Kernel references retain their complete native input
fields, including the explicit upstream Kernel version and Base bounds evidence.
No synthetic v1 deployment is created.

Planning checks the selected slot bytes, installed selected System profile,
candidate profile/provider content, native Base and Kernel against their exact
records. Base ABI facts come from the installed Base's verified release manifest;
Kernel bounds must reproduce the selected input's bound policy digest. The whole
menu/hook, target identity and observed persistent state are checked again under
existing read locks. `recheck` accepts the two explicit plan formats and recomputes
the appropriate plan, refusing changed selection or account/configuration state.
No lock, profile, request or installation record is created by planning.

Native selected profiles name components, so their external startup dependencies
come from `retained_providers`, not from legacy Nix-specific manifest fields.
Core passes each provider a closed `mojt-system-provider-baseline-v1` description
with fields `format` and `references`. Those references stay opaque to core; the
manager-owned adapter's pure `preserves` comparison interprets them and declares
which delivered adapter files must stay unchanged. The Nix boot adapter projects
native references and delegates to the unchanged runtime adapter. Nix compares the complete
selected path/NAR-hash union, rejects conflicting hashes, and allows additional
candidate dependencies while preserving the selected closure. This also preserves
existing service libc dependencies; it does not infer plugin/desktop ABI safety.

The joined updater uses `mojt-boot-transition-preflight-v1`, recording the exact
baseline inputs, candidate boot Base/System/Kernel and one permitted area. The
same handover, constructor, immutable slot store, readiness receipt and atomic
menu publisher used by image preparation consume this result. A saved preflight
is never an executable authorization: the constructor/admission boundary repeats
it under locks and refuses changed selection, target or persistent state.

A failed construction may leave retained verified content, but does not select
it. Repeating staging reuses only a complete admitted deployment with matching
exact inputs and constructor. Repeating activation of the selected candidate is
a no-op. The menu is the next-boot commit point; post-publication durability
errors remain explicit and do not delete the published result. Normal boot keeps
its metadata/state checks and does not run full content scans.

## First initialization/service contract

The implemented policy is deliberately **unchanged startup, tooling changes
only**, recorded by `mojt-system-startup-review-v1`. It permits MPM/tool modules,
MPM/inspector frontends, test files, the MPM manual and newly added admin commands.
It normalizes only write bits removed during immutable installation; other
metadata/content differences remain meaningful. A changed version marker must
match the candidate's human label.

All remaining profile content must be preserved: setup/start/environment,
units, helper declarations/producers, authentication data and service configs.
Changed/removed services or startup inputs block. No new migration or initializer
is inferred from an empty lifecycle list or a package-supplied script.

Providers implement their own pure preservation comparison. The Nix adapter
requires the entire selected startup closure's exact paths/NAR hashes to remain
accepted and its delivered adapter implementation to remain unchanged. Additional
dependencies may coexist. A newer glibc cannot silently replace the old service
closure under this policy; preserved services retain their original dependencies.
This is not a general proof of runtime libc/plugin compatibility.

The two declared late-created privileged helpers must retain their existing
contract/producer. Planning neither creates nor borrows them from the current
host. New helper/privilege initialization needs a supported later contract.
Missing defaults likewise block for explicit preparation; existing local files
and symlinks are preserved without being followed or overwritten.

`checks.compatible=true` means this bounded metadata/content policy passed.
It does not report service health or a bootable candidate. Service upgrades,
provider runtime changes and state migrations need separate supported contracts,
not a user flag bypassing these gates.

## Remaining deployment work

The existing assembled System's flat `defaults/journald.conf` and
`defaults/timesyncd.conf` are resources linked from `/etc/systemd`; observation
checks those actual persistent paths, without creating unused top-level copies
or replacing local configuration. A linked `systemd` parent is refused.

Both `stage_ready` and `boot_ready` remain false. This reader observes the
existing verified v1 layout and the active native-v2 selection through separate
explicit result formats; it does not convert either record format. The [native-v2 record/storage layer](native-boot-v2.md) validates inputs,
binding and deployment, and atomically retains a complete immutable slot without
selection. It does not yet consume this preflight as execution authorization.
The [diagnostic constructor/early reader](native-initramfs-reader.md) now verifies
exact trees from its trusted private runtime. The [System handover mode](native-system-handover.md) now joins this preflight,
current-state checks and a separate boot Base to runtime/shutdown handover.
[Prepared-candidate admission/selection/status](native-system-selection.md) is
implemented. Active-v2 planning is implemented; staging a new generation from
that plan and request-to-boot integration remain before complete administration.
No backward migration is required.

The [prepared single A/B/A owner test](system-boot-acceptance.md) now exercises the
new-image constructor and installed selection/status frontend. The owner
completed its A/B/A boot/return and clean-shutdown acceptance on 2026-11-09 with
exact Base/Kernel and persistent state retained. These synthetic preflight tests
are separate from that real VM evidence. Three focused cases cover tooling/provider preservation,
real root retained-content inspection without writes, and refusal of changed
service/provider contracts plus stale persistent-account evidence.
