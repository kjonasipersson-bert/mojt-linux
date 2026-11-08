<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Generalized native boot inputs, deployment and selection v2

The [record/storage subset](../../native-boot-v2.md) implements strict record
validation, pure menu rendering and immutable slot retention. The active updater
and initrd are unchanged; the [handover constructor and admitted selection publisher](../../native-system-selection.md)
now implement the first bounded subset. Owner boot acceptance and active-v2
preflight/staging remain integration gates. The
[System preflight](../../system-transition.md) binds native candidate inputs and
unchanged-startup gates; it is not yet joined to v2 execution.
The [workflow schema](workflow-formats.schema.json) defines new closed v2 records.
Existing `mojt-boot-deployment-v1`, binding v1 and generated Kernel menu v1 retain
their original hash rules and readers. Unknown v2 is refused, not parsed as v1.

## Binding construction without a hash cycle

| Format | Exact binding |
| --- | --- |
| `mojt-boot-inputs-v2` | Installation/platform/layout; Base artifact/release/rootfs digest and explicit Kernel bounds/evidence; System artifact/composition/measured-manifest/generation; Kernel artifact/upstream/release/image/modules; exact firmware, constructor, boot policy and state/management requirements |
| `mojt-initramfs-binding-v2` | Input-record ID, actual archive SHA256/size and matching constructor identity |
| `mojt-boot-deployment-v2` | Complete input record and binding, plus sorted exact boot-file inventory; embeds both records so identity validation is self-contained |
| `mojt-boot-selection-v2` | Installation, selected/previous deployment IDs, retained entry paths and Base/System/Kernel request-state roots |

All new IDs follow the common format-plus-description rule. Base limits are
inclusive numeric upstream bounds from exact accepted evidence; Kernel upstream
comes from verified descriptor metadata, never guessed from `-mojt1` or package
revision. Example limits are synthetic, not supported Base 0.1.3 declarations.
State/management requirements must match the actual selected System's bundled
capabilities and current target facts. Include all exact dependencies/firmware;
a compatible version label alone is not enough for external modules/drivers.

First verify/assemble Base and System from exact inputs and retain their measured
runtime evidence. Build an input record without generated initramfs, binding,
deployment ID or final slot path. The constructor embeds only input identity
and the generic v2 loader logic. Generate initramfs; measure actual bytes; create
binding; then create deployment. No generated output contains the final deployment
ID inside its own hash input. Sidecars contain canonical records, not new copies
with guessed fields. Constructor inputs/code/runtime are retained exactly.

Final slot is `boot/mojt/deployments/FULL_DEPLOYMENT_HEX/`. It contains
`vmlinuz`, `initramfs.cpio.gz`, `inputs.json`, `binding.json`, `deployment.json`.
The boot-file inventory is exactly vmlinuz/initramfs for this initial profile;
sidecars are already bound embedded records and cannot inventory themselves.
Image hash and initramfs hash/size must agree with inputs/binding. Slot publication
is complete-directory staging/verification/fsync/rename, not boot selection.

The boot menu's kernel command line is generated after the ID is known:
selected console parameters, `rdinit=/init`, `root=UUID=ROOT_UUID`,
`mojt.deployment=FULL_HEX`, followed by approved nonreserved extra arguments.
Do not hash this final derived command line back into inputs/initramfs. No user
extra may replace root/rdinit/console/mojt fields. The initial profile permits
only `quiet`, `loglevel=0..7` and numeric `panic=N`, uniquely keyed and sorted;
unsupported arguments/profile/firmware requirements block rather than inject
shell/GRUB text. Physical profiles and Secure Boot require separate D8 work.

## Native-v2 lookup and early boot

The layout is explicitly new. Verified runtime trees are prepared under full-ID
paths: `realizations/base/BASE_ARTIFACT_HEX`,
`realizations/system/SYSTEM_MANIFEST_HEX`, and
`realizations/kernel/KERNEL_ARTIFACT_HEX`. They are realizations of retained
verified content, not aliases named only by version. Check complete inventory,
ownership/modes, source/extractor/assembler identity and target compatibility;
do not treat an arbitrary copied directory as a valid realization. M1 reuses
the reviewed Base extractor/System manifest/native module inventory policies;
additional attributes or unsupported payload layouts must be explicitly refused.

Generic early boot uses the embedded input identity, mounted exact root UUID
and command-line deployment selector to load the final slot's sidecar. Validate
v2 identity, input match, installation binding, slot/image/initramfs/Kernel module
binding and canonical containment before choosing Base/System/module paths.
No following mutable `base/current` or `system/current`. Mount immutable content
and the exact module tree read-only, persistent state separately, validate required
management/state gates, then initialize supported lifecycle actions before their
dependent services. Failures enter the retained diagnostic/recovery path.

Expose exact running deployment/native artifact identities only after those
checks; matching uname or labels remains insufficient. First implementation is
the declared serial UEFI/QEMU/VirtIO profile. A JSON binding or successful hash
check alone does not prove its initramfs mount logic or physical boot readiness.

## Selection and request authority

Prepare complete candidate slots before changing next boot. Base-only updates
preserve exact System/Kernel; System-only preserve Base/Kernel; Kernel-only
preserve Base/System. Use selected as baseline even if running differs. Required
cross-area changes need explicit plan scope. Boot selection is not live activation
or automatic reboot. System content changes still create immutable generations.

Request roots are exactly one row for each of base/kernel/system (sorted), with
null only for confirmed absence. Selection entries are unique/sorted full IDs;
each path equals its own full-ID slot, and selected/nonnull previous must be
entries. Preserve other retained entries and validate current recovery compatibility.
Do not derive selection from timestamps, request-state desires or menu position.

For atomic publication use a dedicated generated `boot/mpm/grub.cfg` carrying
the complete canonical v2 selection record in a recognized header and complete
derived entries. This is the single authoritative menu/metadata commit point,
not one separately updated selection.json plus a menu. Stage/fsync/replace/fsync
under cooperating store/area/boot locks, retaining both slots after uncertainty.
Update boot-area request-state roots through this record; Ports keeps its own
atomic profile/state/history boundary. No new independently updated root database.

Rollback creates a new validated selection, preserving shared user/configuration
wishes and recording any explicit active override. It must not blindly restore
old management metadata just because older code is chosen. Check that older
System can read/write current formats and current state. M1 refuses state changes
that break its retained recovery choice; later data restore needs explicit support.
Keep running/selected/build/recovery references protected from future collection.

## Fresh-install acceptance gate

Implement native-v2 for a new target with its matching management and early-boot
runtime. No v1 conversion, dual-reader support or legacy installation migration
is required. Preserve format markers and reject unsupported records. Real v2
boot/return, Base/System changes and publication failure tests remain required;
synthetic fixtures do not establish those results. See the
[initial-format policy](../../format-policy.md).
