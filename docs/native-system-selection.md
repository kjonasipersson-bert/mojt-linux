<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native-v2 System staging, selection and status

This joins the [handover constructor](native-system-handover.md) to one atomic
next-boot authority. It remains consolidation step 3, on the path to M1 joined
administration and M2 native self-hosting. Prepared-candidate owner A/B/A boot,
return and clean static-exitrd shutdown passed on 2026-11-09; see the
[recorded acceptance](system-boot-acceptance.md#owner-acceptance-2026-11-09).

## Retained content is not a selectable System

`mpm_boot_selection.stage` is the manager/image-preparation API: run the trusted
System constructor, retain the exact Kernel/initramfs slot, then admit the result.
Admission accepts an in-process `CompletedBuild`, not decoded JSON, a package hook
or a self-declared boolean. It checks current constructor code, exact archive and
slot binding, rechecks the preflight, and verifies source trees and current
handover gates. Verification-only archives cannot qualify. This typed join is a
manager API contract, not an authentication or hostile-root security boundary.

The root-owned immutable receipt at `boot/mpm/ready/DEPLOYMENT_HEX.json` uses
`mojt-boot-stage-receipt-v1` with closed fields `installation`, `deployment`,
`inputs`, `archive`, `proof`, and `handover`. It binds the actual completed
constructor's proofs and handover contract to the retained slot. Receipt
publication is atomic/durable; no selected pointer or wishes change. Failure
after content retention can leave an unadmitted slot, which is not selectable.
Recovery after uncertain publication inspects retained content instead of deleting
possibly committed files. SHA256 is integrity, not publisher authentication.

The current staging API consumes the existing preflight/builder inputs. Automatic
installed `mpm system stage` and planning/staging a fresh generation from an
already active v2 baseline remain a separate join. An image preparer can stage
both accepted System candidates before publishing the initial image.

## One bootloader authority

Fresh private-image assembly installs this exact `boot/mojt/grub.cfg` hook:

```grub
# Mojt native-v2 boot hook v1
configfile /boot/mpm/grub.cfg
```

The initial-image API `initialize` requires the hook, no v1 boot registry and no
existing v2 selection. It does not rewrite a live/v1 hook or migrate experimental
disks. The image must stay unpublished until initial selection succeeds. The
whole v2 menu at `boot/mpm/grub.cfg` embeds its canonical selection record and
is the sole authoritative selection commit point. It needs no separately updated
selection database. Missing/modified hooks and inconsistent menus fail closed.

Installed commands then use exact deployment IDs:

```sh
mpm system status
mpm system select --deployment sha256:FULL_ID \
    --expected-selected sha256:CURRENT_ID --dry-run
mpm system select --deployment sha256:FULL_ID \
    --expected-selected sha256:CURRENT_ID -y
mpm system rollback --expected-selected sha256:CURRENT_ID -y
```

Offline commands require `--disk-root`. Only administrators can select, including
preview. Selection verifies admitted slots, current immutable trees and state,
checks preparing/candidate/recovery registry support, and preserves exact Base,
Kernel and boot policy. All entries are retained. Rollback validates the previous
choice against current state instead of restoring historical configuration/data.
Neither operation changes running services, reboots, changes wish roots or
collects content. Initial boot wish roots are null; request-to-boot integration
is still required before declaring complete configuration-driven administration.

Publication holds existing store/install/Kernel/boot and existing Ports locks,
rechecks the selected baseline, stages/fsyncs one complete menu and replaces it
atomically. Pre-rename failure preserves the old choice. Post-rename flush failure
reports uncertainty and keeps the new menu plus both deployments. A repeated
selection is a no-op. Operation-local tree proofs avoid hashing a shared immutable
dependency once per menu entry; they never persist across independent operations.
State can change after selection; the early handover checks it again at boot.

## Installed, selected and running

Base/System status reads v1 or v2 descriptions while preserving their real record
formats and deployment IDs. Installed runtime reads `native-v2.json` or the legacy
runtime record, refuses ambiguity/foreign installation and checks the observed
Kernel release. A label or uname alone never supplies an artifact identity.
Kernel status joins v2 selection and explicit runtime evidence; System status also
lists admitted deployment IDs. Read-only metadata status creates no registry,
loads no provider and does not decompress/scrub payloads. It is not a fresh
integrity or boot-health check. Missing running evidence stays unknown.

The measured `mpm-boot-v2` registry capability protects current state against an
old recovery reader/writer. V1 boot writers explicitly refuse a v2 authority;
Base/Kernel content import remains separate, and v2 Base/Kernel boot changes are
not silently routed through an unused legacy menu.

## Focused evidence and next gate

The existing actual-archive root/chroot case now admits two native System
generations, initializes the private hook/menu, previews/selects/returns, and
checks distinct selected/running identities. It covers stale expected selection,
no-op, retained entries, refusal of v1 fallback and failures before/after menu
replacement. This is not a real firmware/Kernel/System boot or owner Debian test.

The [disposable A/B/A VM preparation and checkpointed owner test](system-boot-acceptance.md)
use these manager APIs. Owner boot/return passed with exact Base/Kernel/state,
selected/running identities and the previous journal retained. Next close
active-v2 preflight/staging and
request/configuration joins before MBT bootstrap reuses the same code. Self-hosting
still requires pinned source recipes for Base and Mojt-owned System code, plus
the joined build/package/install/boot cycle; the new menu alone does not prove it.
