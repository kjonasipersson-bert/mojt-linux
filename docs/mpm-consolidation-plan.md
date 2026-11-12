<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MPM consolidation: governing six-step plan

Owner-confirmed 2026-11-01. This is the governing implementation order.
The detailed [gap matrix](mpm-gap-matrix.md) and format specifications support
these milestones; neither separate experiments nor new format documents replace
the full installed-machine goal. Target fresh installations with explicit format
versions, not backward migration of experimental installations.

| Step | Goal | Current evidence and remaining completion gate |
| --- | --- | --- |
| 1 | Establish the baseline and deliver complete MPM in System | Common frontend/runtime is merged. Configuration ownership, exact resolution and a complete Ports publisher/acquisition API are implemented in #36. The installed Ports frontend now joins configuration, accepted finite sources, imports and profiles without a checkout. A bounded real Nix adapter/frontend acceptance passed. Interactive reason removal and active-choice reset are implemented in the bounded follow-up. Completion still needs supported Base/System operations, remaining request/configuration joins and honest diagnostics. Local native source/cache acquisition is implemented; general authenticated remote publication remains the separate P2 gate. |
| 2 | Consolidate installation and transaction rules | Shared locks/publication primitives are merged; late baseline guards and the fresh Ports profile publisher are added here. Complete other area publishers, lifecycle effects and failure recovery; planning alone is not a transaction commit. |
| 3 | Make Base and System actual MPM installation units | Base exact import/realization/status merged in #40; bounded Base staging/selection/boot/return passed owner acceptance in #41 on 2026-11-07. Bounded native System composition/component install/status now materializes an immutable profile. Exact provider runtime dependency retention now reuses the Ports adapter protocol; current profile packaging and named-source/cache acquisition are joined. Verified System planning now binds selected Base/Kernel and a bounded unchanged-startup/tooling-only gate. Native-v2 deployment/upgrade and remaining authorized initialization/service gating remain before bootstrap. |
| 4 | Build bootstrap on those functions | Reuse the same MPM acquisition/install/deploy libraries for explicit new targets; no second installer or experimental-script-only path. MBT syntax remains a separate discussion. |
| 5 | Integrate environment, Kernel build and packaging | Prior real builds/boot experiments exist. Join exact environment retention, ordinary-user builds, native packaging and normal MPM install/select without global compiler/libc changes. |
| 6 | One joined acceptance flow, then hardware | Prove the delivered tools administer the installation, update Base/System, build/install/boot a Kernel and recover with state retained. Then accept a supported physical profile; do not repeat unchanged component cross-products. |

## Current bounded increment: Ports resolution through publication

PR #36 belongs to steps 1 and 2. `mpm_requests.py` owns versioned declarative
and interactive wishes; `mpm_request_plan.py` joins them to the shared resolver
and explicit adapter bindings. `mpm_ports_profile.py` now joins exact acquisition,
physical verification, complete profile/alias assembly and request/history
publication through one atomic pointer. `mpm_nix_binary.py` is its first production
binary-output adapter. See [implementation and limits](ports-profile-implementation.md).

The fresh APIs are now [connected to the installed frontend and System delivery](ports-cli-integration.md).
`update` preserves accepted targets, `upgrade` advances only its explicit moving
wish scope, and exact full-build pins survive catalog withdrawal. Ports-only
configuration apply, installed-evidence activation and linked history use the same
publisher. Source inputs are explicit content-identified finite bundles; no implicit
remote refresh or experimental-store migration is provided.

Filesystem and installed-copy tests exercise this join. The
[owner-run real Nix adapter/frontend acceptance](ports-profile-acceptance.md) passed
on 2026-11-01 at code revision `40ee0f2`, including registered roots and unchanged
repeat installation/history. The bounded [remove/reset follow-up](ports-remove-reset.md) releases interactive
reasons and returns active control to adopted configuration without acquisition.
Next gate: remote source acquisition, artifact-only pruning/configuration forgetting
and native Port support.
Non-Ports reconciliation and lifecycle/recovery remain explicit work. Preserve the
same provider-independent transaction boundary for Base/System.

## Next bounded increment: native source acquisition and cache

The [local native source/cache library](native-source-cache.md) adds actual verified
archive acquisition for Base, System, Kernel and Port without a provider dependency.
It joins accepted source/snapshot/catalog/acquisition records to a separately
protected owner policy, a read-only exact plan and no-overwrite cache publication.
Real synthetic tar/zstd tests exercise all categories and failure/retry boundaries.
The library and source/cache commands ship in System. Named registrations, explicit
metadata refresh and exact fetch now use frozen snapshots. The first
[source-to-install join](kernel-source-install.md) connects them to the existing
Kernel publisher, with shared eligibility, retained origin evidence and separate
boot selection. The bounded owner VM acceptance passed on 2026-11-06 at
source revision `386b204`, using the installed runtime and a real package; see the
[recorded evidence](kernel-source-install.md#owner-installed-system-vm-acceptance-2026-11-06).
PR #38 passed full CI and merged. Base/System and native Ports installation integration
remain pending. See [source runtime integration](source-runtime-integration.md).
Local owner trust does not implement
remote authentication or signing. This advances steps 1 and 2; it does not mark
MPM complete or displace actual Base/System installation in step 3.

## Following bounded gate: source-installed Kernel to native boot

PR #38 passed full CI and owner installation acceptance, then merged. The
[native boot follow-up](kernel-source-boot.md) retains acquisition origin during
fresh-image copying and candidate staging, with mandatory v2 input-receipt binding.
It also makes the fresh MPM state parent part of System assembly. The owner
accepted one exact source-installed deployment boot on 2026-11-06 in a separate
native image at `0dd0b40`, retaining source origin, read-only modules, Base/System
and machine identity, with selected/running IDs agreeing and no failed units.
Existing build/package inputs were reused. Installation, staging, selection and
reboot remain separate actions. This continues steps 1–2 and supports the later joined
acceptance milestone; it does not complete Base/System installation or bootstrap.

## Immediate review gate: Base installation and inspection

Following merged #39 and its accepted source-installed Kernel reboot, the owner
requested review of MPM/MBT documentation before Base implementation. The
[shared user model](management-workflow.md) and
[Base install/status proposal](mpm-base-contract.md) are that review surface.
They propose complete exact Base retention plus a validated runtime tree, no
implicit defaults/state/boot changes, and separate installed/next-boot/running
inspection. The owner agreed to these meanings on 2026-11-06. The first
[exact import/realization/status implementation](base-installation.md) merged in PR #40 after full green CI;
Base-only boot selection/return is implemented and owner-accepted in #41;
System integration remains a later gate.
MBT's final spelling remains deferred and it must reuse this installation model.

Content-only Base import/realization/status is merged. The next bounded increment
adds [read-only Base transition preflight](base-deployment-preflight.md), binding
the installed candidate to the selected System/Kernel and observed state. It now feeds [exact Base slot staging](base-boot-staging.md) with explicit next-boot selection/return and joined status.
The first subset refuses missing defaults and retains matching System management
code. The [fresh-VM owner acceptance](base-boot-acceptance.md#recorded-owner-acceptance-2026-11-07)
passed on 2026-11-07: exact changed Base booted read-only and returned to the old
deployment with System/Kernel and saved state retained. PR #41 is merged.
The [bounded defaults preparation library](defaults-preparation.md) now adds an
explicit root-authorized ensure-file operation and durable attempt evidence. It
is not called by install/stage/select, and is not the general lifecycle executor.
The next [management/state/handler gate](management-capabilities.md) now measures
bundled support, observes the actual defaults registry and checks both runtimes
without effects. [Native System install/status](system-installation.md) now
implements local native leaf components and immutable profile realization.
Provider/source joins and System-scoped deployment/initialization remain next. Do not add another unchanged manual Kernel/Base matrix or move
bootstrap/build work ahead of the six-step order.

Progress reports must name the step, implemented behavior, validation and the
remaining gate. Unit tests, schema checks and prior experiments do not mark a
whole milestone complete. No new public command syntax is implied by this plan.


Native-v2 progress within step 3: [exact records and immutable slot retention](native-boot-v2.md)
are implemented without selecting boot. The diagnostic constructor/early reader
now runs from a private trusted Python closure. Bounded preflight/state checks and
mount/shutdown handover now join a separate immutable boot Base. Admitted staging,
atomic v2 selection and explicit runtime status now join prepared candidates.
The [single changed-System A/B/A VM test](system-boot-acceptance.md#owner-acceptance-2026-11-09)
passed owner boot/return and clean-shutdown acceptance on 2026-11-09. Public
active-v2 preflight/staging and
configuration/request joins remain before complete M1 and MBT bootstrap.

The boot-performance follow-up in #49 is owner-accepted: normal native-v2 boot
checks metadata/paths/current state without full payload scans. Its measured
reader and state gates totalled 344 ms (not total boot time), with no failed
units. Full content verification remains an administrative/explicit operation;
see [recorded evidence](boot-performance.md#fresh-normal-boot-acceptance-2026-11-10).

## Short route to physical installation (owner direction, 2026-11-10)

Finish two coherent deliveries, then run one joined physical acceptance journey:

1. Join installed MPM's exact Base/System/Kernel update path on native-v2; retain
   Ports, shared transaction rules and independent installed/selected/running
   status. Preview belongs to the real operation's `--dry-run`, not a public
   `mpm system plan` command. PR #50 now joins the internal preflight to handover,
   constructor/stage and atomic selection. Explicit exact installed targets are
   supported first; moving policies and generalized lifecycle work are deferred.
2. Deliver a thin usable MBT around the working environment, Kernel build,
   packager and image tools, plus one supported physical machine profile. Agree
   on its minimal public spelling before implementing it. New-target bootstrap
   reuses MPM installation/deployment code; updates never reformat the target.
3. Accept a dedicated physical disk: boot, use Ports, update the installation,
   compile/package/install/boot a Kernel and return to retained boot content.
   Fix observed blockers rather than repeating all old component cross-products.

The focused root/archive CI journey reuses one disk/runtime fixture to exercise
System, Base and Kernel changes. A bounded real VM journey remains before physical
rollout; these automated archive/chroot checks are not a real Kernel boot.
No further read-only planning PR, generic migration framework, native Ports
backend, GC or complete third-party source rebuild is required for this milestone.
Normal boot stays free of full content scans. The first System policy still
requires unchanged startup/service dependencies; unsupported service transitions
are reported as blocked, not silently accepted.

PR #50 merged after all three full CI jobs passed at
`b4f3c7885590ec3a8367d1ad3cd398379b397e13` (merge
`e24e3bfd10a92c734af48c09552cd842fbd6d584`). No additional owner component matrix
was required before merge. The joined VM acceptance remains part of completing
MBT/bootstrap before physical rollout.

Step 2 has started with [minimal MBT](mbt-minimal.md): an experimental thin
frontend over the existing environment, Kernel build and packager, optional
builder System delivery and its manual. It now includes fresh serial UEFI/VirtIO
native-v2 image bootstrap through the same MPM install/stage/select libraries,
with directory construction before mkfs and no loop-device finalization. An
installed builder carries the fixed code/assets needed to assemble its successor.
The ThinkPad X1 Carbon 3 image profile now joins local console, USB/SATA/keyboard
modules, System-owned firmware/licenses and the independently retained native
Kernel. Its policy is preserved by MPM updates; firmware is read-only and normal
boot adds no content scans. This draft does not settle all command spellings or
write a physical disk; bootstrap/profile have automated fixture coverage, not
owner VM acceptance yet. Repeated owner preparation failures exposed a missing
execution-runtime boundary: Git checkout modes were being checked as installed
manager modes. The draft now prepares fixed code/assets before manager imports,
keeps MPM target/runtime checks strict and performs privileged entry preflight
before password/assembly. Public packaging and bootstrap-preview tests exercise
real Git umask/private-home/namespace boundaries. Complete public construction
with the real System payload remains a gate before another owner VM attempt.
The next work stays in the same delivery: establish that construction gate,
one joined VM acceptance, then the dedicated physical disk. Do not substitute an old-format image or call source assembly of
prebuilt inputs a complete source rebuild.

The owner reaffirmed native self-hosting as the destination on 2026-11-08.
Complete the joined M1 administration/bootstrap flow, then M2 source recipes for
Base and Mojt-owned System code; report imported third-party inputs separately.
Do not relabel the existing prebuilt-input image assembly as native self-hosting.

## Physical installation before physical compilation

The current physical priority is USB startup, installation to prepared SSD
partitions, SSD boot, then lightweight MPM/MBT measurements and a compiler build
on SSD. Do not repeat the heavy VM verification matrix or use USB storage as the
physical compilation baseline. The [mounted installation increment](mounted-installation.md)
reuses the common native-v2 constructor and MPM installation/selection APIs, with
a portable data-only installer kit and an EFI-last publication boundary. It is
a fresh-target prototype; one focused disposable-target VM installation/boot
remains before physical use. Device partitioning/formatting is an explicit
separate operation. The [performance guide](physical-performance.md) applies to
the resulting SSD installation, preserving normal command verification.
