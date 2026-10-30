<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt development priorities

Updated 2026-10-29. This records the agreed order and measured progress;
future commands and policies are not claims of implemented functionality.
The [architecture](architecture.md) defines the layer boundaries and the
[MPM contract](mpm.md) records the accepted update semantics.

## Completed foundation

- Whole-image Base packaging, side-by-side installation and return to an
  earlier Base, with persistent configuration/state preservation.
- A bootable System with systemd, networking and usable Nix-backed Ports.
- A full Mojt VM generation sequence A/A → A/B → B/B → A/A, with explicit
  Base/System boot selections and shared persistent markers. Base B was
  intentionally ABI-compatible; both System labels used the same Debian
  kernel and upstream System payload.
- A second full Mojt VM experiment completed kernel/module switching
  `6.12.107+deb13-amd64` → `7.2.9+deb13-amd64` → `6.12.107+deb13-amd64`,
  keeping Base 0.1.3 and System userspace fixed, with persistent markers,
  networking and the same installed Ports hello artifact. B identity/marker/HTTPS
  checks were owner-confirmed; see the evidence distinction in the acceptance log.
- System step 7 diagnostics passed on both retained kernels, including the
  corrected udev hardware database, network checks and the same Ports artifact.
- A clean step 8 VM completed A → B → A with automatic persistent machine-ID
  commitment, retained journals across all three boots, confirmed NTP, quiet
  login consoles and an explicit working terminal-size query.
- Authenticated full-Mojt serial console in the SSH terminal, retaining the
  tested VM's credentials and state.
- Controlled interruption of a fresh image build at password entry, successful
  return to the completed VM, and a repeated probe confirming no published
  interrupted output and an unchanged completed VM disk checksum.
- Accepted update policy: Base is one complete release; a content-changing
  System upgrade creates a new immutable generation; Ports recovery uses
  individual versions/activation and readable history without requiring
  user-managed whole-Ports generations.

See [generation acceptance](boot-generations.md) and
[serial/interruption acceptance](vm-serial-console.md) for evidence and limits.
Fresh-image assembly and controlled abort checks do not establish durable
updates to an existing boot disk or power-loss recovery.

## Work order

| Priority | Track | Next work |
| --- | --- | --- |
| 1 | Base/System generations | VM Base/System and different-kernel return experiments completed. Retain the reference images; production boot-disk updates, compatibility and automatic fallback remain future work. |
| 2 | More complete System | Diagnostics and console/time/journal acceptance completed. Timezone/UTF-8/manual checks accepted on System A; separate A/B checks deferred to the next stage. The account A/B/A run now preserves new users, identity and home data, with working PAM/sudo, session cleanup and shared Ports. Superseded-password rejection is owner-confirmed. Account integration merged; retain its reference image. |
| 3 | MPM development | Ports upgrade/history and backend-independent selector integration passed real Nix and compatible-image VM acceptance and merged. PR #25's limited System manifest/preflight increment also merged. Existing-disk Base/System/Kernel publication remains future work; project locks precede pruning/GC. Libc integration stays deferred, with opaque dependency identities retained. |
| 4 | Build System on Mojt | Owner-run full image assembly and result boot passed on 2026-10-27: frozen Base 0.1.3, step-10 System payload and Debian 6.12.107 kernel/modules. Inputs unchanged; result system-selfbuild-A boots with root serial login and no failed units. This is image assembly from prebuilt inputs; source compilation of all System packages remains separate work. |
| 5 | Own-built Linux kernel | Native compilation, image assembly and focused VM acceptance passed on 2026-10-28 for 6.12.107-mojt1, based on the frozen Debian configuration. Matching e1000e module/driver, zero failed services and HTTPS confirmed. PR #27 merged after green CI; retain the Debian reference and accepted result. |

MPM work continues alongside System integration where needed. The current
working Debian kernel remains the reference while the build/deployment chain
is developed; the first own-built kernel now completes the next measured
milestone after generation switching and image assembly.

## MPM selectors and runtime identity

The Ports upgrade/history/manual block is merged. The owner verified real Nix
hello 2.12.1 -> 2.12.3, following and exact selections, recovery and a fresh
Mojt A/B/A run retaining state/history, users and the same artifact.
See [the measured acceptance log](mpm-ports.md).

The [selector branch](mpm-selectors.md) now implements pure parser/resolver,
request/alias policy, Nix transaction integration and explicit format-3
metadata adoption. Owner-run read-only tests passed both without a backend and
with a real two-snapshot hello catalog. New transaction policy has automated coverage and owner-reported real isolated
transaction plus fresh compatible-image A/B/A VM acceptance. Older MPM writers must refuse the new shared metadata;
System deployment compatibility must check this before scheduling generations.
Libc work remains deferred: preserve exact opaque dependency identities, without
adding a loader replacement or compatibility solver to this increment.

Keep the latest tested reference VM. Optional SSH and personal Ports remain later tracks. Image assembly on Mojt
and the first own-built kernel build/boot have now passed. PR #27 is merged.
The next architecture increment is the Mojt-owned artifact/catalog model below;
existing-disk activation remains separate implementation work.

## Implementation boundaries

The repository frontend implements Ports, local native Kernel install/status
and read-only complete deployment planning.
Base/System mutations, Kernel deployment activation/upgrade operations, general
undo, production project locks and GC remain unimplemented. Native format-2
upgrades/history have real Distrobox/VM acceptance; format-3 selector transaction
integration has owner-run real and VM acceptance. General
version adapters and mixed-runtime compatibility checks remain future work.

System manifest/preflight schemas now exist. Independent Kernel selection,
existing-disk compatibility enforcement and production boot publication/fallback
remain work to specify and implement. Future status/plans must show installed, selected and running
content, directly selected components, dependencies and exact changes.



## Limited System compatibility increment

Following selector merge, [System manifests and preflight](system-manifest.md)
provide an immutable content description, metadata capability gate and read-only
candidate/running/explicitly-selected comparison. PR #25 implemented
this in the fresh-image builder; it does not implement existing-disk System
upgrade. Targeted automated acceptance is sufficient for this declaration layer;
manual runtime acceptance accompanies the first build-on-Mojt image experiment.
A complete System updater, project locks and GC are not prerequisites for that
controlled build experiment. Libc/desktop work remains deferred.


## Build-on-Mojt acceptance

PR #25's manifest/preflight block passed CI and merged. The owner then accepted
[the private build environment](build-on-mojt.md) and [full image assembly/boot](build-workspace.md#owner-full-image-build-and-result-boot-2026-10-27).
The static clean launcher, pinned tools, ELF closure checks, native Python
DNS/HTTPS runtime and disk/EFI tools passed. A private 64-GiB workspace carried
frozen Base/System/kernel/source inputs; verification passed before and after
assembly inside Mojt. The resulting system-selfbuild-A booted on Debian with
authenticated ttyS0 login and no failed units. Keep the successful result and
reference VM. No repeated account/network/generation checks are required here.

The own-built kernel/configuration milestone with matching versioned modules
has now passed native build and focused VM acceptance; see the next section.
The working Debian kernel remains the reference.
Compiling all System packages, production existing-disk updates, project locks
and GC remain separate work. Libc evidence is bounded to the measured tools and
runtime; no Base libraries were replaced or global library paths added.


## Own-built kernel acceptance

PR #26 passed CI and merged after owner native image-build/result-boot acceptance.
The [first kernel experiment](kernel-build.md#native-acceptance-2026-10-28) then
completed its native acceptance: a separate pinned GCC 14 environment compiled
upstream stable 6.12.107 as `6.12.107-mojt1`, using a frozen Debian config and
staging matching versioned modules. Mojt assembled a fresh UEFI image with the
same frozen Base 0.1.3/System payload; input verification passed.

The owner booted that image on the Debian host as `system-kernel-A`. The new
release was running, the matching e1000e module was loaded, the network driver
reported the same release, certificate-verified HTTPS worked and no units had
failed. Compiler/host-helper evidence remained within the pinned tool closure;
Base libc was not replaced. This is the complete first kernel-build/VM milestone,
not a general libc compatibility proof or compilation of all System packages.

Retain the known-good reference disks and the accepted result. PR #27 merged
after green CI. Production Kernel publication/rollback, source
builds of the complete System, project locks and GC remain separate increments;
this acceptance does not implement new MPM layer commands.

## Next architecture increment: Mojt-owned artifacts and catalogs

The owner requires a standalone MPM/Mojt distribution model. Building and
installing are separate: complete Base releases, own-built kernels and
Mojt-owned System components need native distribution sources and a catalog of
offered artifacts that are not yet installed. Nix and other providers remain
optional integrations rather than the authority for MPM's catalog or policy.

The [artifact architecture manifesto](mpm-artifact-architecture.md) begins that
design, building on the existing pure selector/catalog contract. It distinguishes
catalog-known, cached/verified, installed, selected and running content; starts
from local repositories and retained snapshots; and proposes static publication
without a mandatory external service or remote database. Native descriptor,
identity/trust formats and migration rules remain to review before acquisition
or installation is implemented.

PR #28 also contains a [read-only local catalog prototype](mpm-catalog.md):
literal name/alias search, explicit descriptions, grouped package inspection and
versions, plus Kernel resolution using pinned/latest-LTS/latest-upstream policy
intersected with explicit selected-Base bounds. It wraps the unchanged pure
resolver schema and runs without provider code, Nix or network access. Examples
are synthetic metadata, not published kernel packages or actual Base limits.

PR #28 additionally prototypes [the native package format](native-artifact-format.md)
and packer/verifier. All four kinds use a single category-rooted tar.zst with
embedded descriptor; an external identical descriptor serves catalog discovery.
Real tar/zstd fixtures cover Base, System components/compositions, Kernel and
Port, filesystem metadata boundaries and version/build traceability. Existing
Base archives and ready Kernel build records are preserved rather than rewritten.

The owner completed [real Kernel package acceptance](native-artifact-format.md#owner-native-package-acceptance-2026-10-29)
on 2026-10-29: Mojt packaged the existing build without recompilation, retained
the original input records and actual kernel release, and Debian independently
verified the transferred package, descriptor copies and original build evidence.
The accepted artifact is recorded by its full content ID in the format guide.
Functional-head CI is green; the acceptance follow-up changes documentation only.

PR #28 passed review, final-head CI and native package acceptance and merged on
2026-10-29. The next [local Kernel install/status prototype](mpm-kernel.md) now
registers an explicitly identified local artifact with retained archive, private
read-only tree and installation record, preserving selected/running deployments.
It adds read-only inspection/scrubbing and reports unknown deployment bindings
instead of identifying builds from `uname`. Unsupported dependencies/requirements
are rejected, and existing Ports state/dispatch remain unchanged.

The owner completed [real local Kernel install/status acceptance](mpm-kernel.md#owner-local-kernel-installation-acceptance-2026-10-29)
on 2026-10-29 as an ordinary Debian user with a dedicated private registry.
Empty status/preview created no registry; installation and full retained-content
verification passed; repeating installation preserved status and the installation
record. The source package checksum was unchanged. Selected deployment remained
unknown and the running Debian kernel was distinguished from installed content.

Production repository trust/update, catalog acquisition, policy persistence and
boot activation remain separate increments. The next deployment work must bind
exact Base/System/Kernel/module/initramfs content and enforce compatibility
before selecting a boot entry. No repeated unrelated VM acceptance is required.

PR #29 merged after final-head green CI and the owner acceptance above. The
next [read-only complete Kernel deployment planner](kernel-deployment-plan.md)
checks installed bytes and explicit selected Base bounds, System identity and
ABI/state/Ports/shell declarations, plus initramfs file/identity bindings.
It preserves Base/System userspace and does not write or adopt a selection.
All plans explicitly leave boot readiness unestablished: Base/System payload
verification, authoritative state lookup, actual initramfs contents/mounts,
hardware/firmware and runtime ABI checks remain outside this metadata increment.

The next build integration must consume the chosen native Kernel/module tree,
generate and bind a deployment-specific initramfs, and verify the exact Base and
System inputs. Current initramfs logic mounts modules from the System profile;
old boot descriptors cannot be silently reused for the independent native
Kernel choice. A focused result boot belongs with that builder change. Durable
existing-disk publication, selection and recovery remain separate work.

PR #30 merged after final-head green CI. The next
[fresh native image builder](native-image-build.md) now verifies a native Base
package, privately reimports an exact installed Kernel, snapshots the existing
System payload and creates one new serial UEFI image. The generated initramfs
mounts the native module tree independently of System; actual gzip/newc content
is inspected against the generated script, device metadata and early modules.
Complete deployment/binding/planner evidence is emitted for that new image.
Original Base files/metadata/xattrs/hardlink topology must be preserved; only
additive mountpoint scaffolding is allowed and recorded. Base libc is unchanged.

The owner completed [fresh native image acceptance](native-image-build.md#owner-native-image-acceptance-2026-10-30)
on 2026-10-30 at functional revision `fa1289d56009aac0a00ef00e17d45a57a5661f85`.
The first boot exposed a BusyBox remount lookup through Base's merged-/usr
layout; an explicit source/target remount fixed it. The corrected image booted
as `system-native-A` with the exact native Kernel artifact, read-only registry
module tree, matching e1000e metadata, working VirtIO networking/HTTPS and zero
failed units. The runtime deployment named the expected exact Base/System/Kernel
and initramfs bindings. Both functional-head CI jobs passed.
No recompilation, new System export or repeated account/A/B/A test was needed.
Automated fixture assembly remains distinct from this owner-measured VM result.

The next deployment increment is existing-disk staging/publication, explicit
selection/status and recovery without changing the selected Base/System
userspace. Preserve old deployments and distinguish installed, selected and
running identities. Catalog acquisition/trust and policy persistence remain
separate boundaries; project locks still precede pruning/GC.

Console usability follow-up: automate geometry setup/refresh for direct
Debian-host QEMU serial sessions. A manual terminal reset/size adjustment resolved
the owner's display/paste problem during this test. No automatic terminal fix
is implemented by the package-format work.
