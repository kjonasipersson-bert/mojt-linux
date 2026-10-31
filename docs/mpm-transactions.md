<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Installation and transaction rules

This is the common contract for the existing Base directory installer, native
Kernel registry, Kernel boot publisher and Ports adapter. It consolidates their
coordination/publication rules without replacing area-specific formats, adding
a database or claiming an existing-disk System installer.

## Responsibilities and phases

1. Resolve a request against an explicit catalog snapshot or exact local input.
   Preserve request policy, exact artifact identity and source evidence separately.
   Missing bytes or an ambiguous source are explicit outcomes, never an implicit
   provider change or source build.
2. Plan the exact operation and show its scope. Read-only inspection/preview
   creates no installation locks, registry, staging content, payloads or roots.
   Confirmation authorizes that plan; a changed baseline requires another plan.
3. Acquire and verify exact content using its declared provider. Hashes establish
   content integrity, not publisher authenticity. Keep acquisition separate from
   boot selection and compilation. Retain complete runtime dependencies before
   publication; sharing a version string is not dependency equivalence.
4. Prepare private area-owned staging content. Never extract a native archive
   into the running root or run package-supplied installation hooks. Build jobs
   use their own workspaces; they do not hold installation locks while compiling.
5. Hold all cooperating resource locks needed for publication, in deterministic
   order. Re-read the authoritative baseline and recheck content/compatibility at
   the publication boundary. Reuse within one operation is not a persistent
   integrity cache. An unchanged plan is a no-op, not a new history entry.
6. Flush complete prepared files/directories, then publish through the area's
   commit point. Keep existing profiles/deployments and references needed for
   recovery. Flush the containing directory after the atomic rename.
7. Report what committed and what remains installed/selected/running. A failure
   after the rename is different from an uncommitted preparation failure.

This is a logical phase contract, not a claim that every legacy path already
moves all acquisition outside its lock: Ports still serializes import/publish
under its profile lock; Kernel import and initramfs staging also retain their
current conservative lock scopes. Moving lengthy preparation outside a lock
requires frozen inputs and the same final revalidation gates.

## Area semantics and authoritative records

| Area/operation | Authoritative record / commit point | Selection effect |
| --- | --- | --- |
| Base directory install | Complete release metadata plus installed Base tree | Legacy directory activation can select `base/current`; it is not a boot-menu update |
| Base directory activate | Atomic `base/current` symlink replacement | Directory selection only |
| Kernel install | Published exact object directory with descriptor, retained archive and `installed.json` | No boot selection or running change |
| Kernel stage | Complete immutable boot slot | Does not select next boot |
| Kernel select/rollback | One generated `boot/mojt/grub.cfg`, containing selected/previous IDs | Next boot only |
| Ports publish | One `current` symlink to complete profile/state/transaction files | New program starts use the selected profile |
| Future System install/activate | To reuse these rules with an immutable composition and complete deployment | Not implemented here |

Do not promote `base/current` or `system/current` into the authoritative boot
selection. Boot deployments bind exact Base, System userspace, Kernel/modules
and initramfs. Installation is not activation. Content rollback does not revert
shared configuration, accounts or application/database formats.

Existing history formats remain unchanged: Ports transactions live in committed
profiles, Kernel installation evidence lives with the retained object, and the
boot menu records selected/previous deployments. There is no new global audit
history or journal whose contents can disagree with a committed selection.

## Shared locking implementation

`tools/mpm_transaction.py` supplies provider-independent `file_lock`, ordered
`resource_locks` and single-file/pointer `publish`. Base, Kernel and Ports keep
their existing lock names so initialized older cooperating writers use the same
inodes. Lock files are never truncated, replaced or removed on release. Reject
symlink paths, nonregular/multiply-linked locks, writable lock files and unsafe
exclusive-lock ownership. Verify the inode again after waiting.

For a native layout-v1 disk, Kernel stage/select/rollback holds all these locks:

| Resource | Path relative to the installation root |
| --- | --- |
| Base directory writer | `.install-lock` |
| Boot publisher | `boot/mpm/.lock` |
| Native Kernel writer | `kernel/.lock` |
| Shared Ports writer | `state/var/lib/mojt/ports/.lock` |

The helper sorts distinct absolute paths before acquisition and releases them
in reverse order. Single-area writers acquire only their own lock. Under the
guest's existing `/var` bind, `/var/lib/mojt/ports/.lock` is the same inode as
the disk-root state path; no guessed global registry or new central daemon is
needed. The standalone Kernel registry must still be explicitly chosen when
installing to another disk; this increment does not change CLI root defaults.

A boot transaction may create only the Ports directory and its coordination
lock before the first Ports import. The new Ports writer recognizes this exact
empty state, initializes it under the lock and refuses unrelated local files.
Older writers may refuse that not-yet-initialized root; no state is silently
adopted. Read-only inspection treats a valid lock-only root as empty.

All four locks are held through final content/compatibility verification and
boot publication. Thus cooperating Base/Kernel/Ports writers cannot change the
facts between the late check and commit. This does not coordinate external
`useradd`/database tools, manual root file edits, direct Nix operations or older
boot publishers that held only the boot lock. Those writers must remain idle.
There is no general global snapshot of all machine state or filesystem freeze.
This is a local-filesystem flock/rename contract, not distributed locking.

The helper and [complete MPM frontend](mpm-system-runtime.md) are bundled with
newly built System profiles. No retained System profile is edited in place.

## Failure and recovery boundaries

Before pointer publication, an error preserves the old selection; private
staging may be removed by the operation's existing cleanup rules. Successful
rename is the logical commit point for that pointer. If directory sync fails,
`PublicationUncertain` explicitly reports that publication may have committed.
The new selected content must be retained; never report a successful rollback
or delete a possibly selected generation. Asynchronous interruption immediately
after rename is checked against the prepared inode and reported the same way.

Status/inspection of authoritative records determines what is currently visible.
It cannot prove power-loss durability after a failed flush. Existing incomplete
staging/registry reports and explicit Base recovery remain area-specific. This
increment adds no blind automatic repair, replay log, filesystem data rollback,
cross-area atomic commit, retention pruning or garbage collection.

## Validation

`test_mpm_transaction.py` uses real child processes and legacy flock calls to
test exclusion, stable lock identity, deterministic acquisition and unsafe-lock
rejection. Failure injection covers pre-rename preservation, post-rename sync
failure and interruption. Kernel boot tests verify all four actual resource
locks and retention of both deployments after a post-publication failure.
Ports tests cover lock-only initialization and existing committed-profile/history
failure semantics; System tests check that the helper is actually delivered.
Existing Kernel, Base, preview, no-op and late-integrity-gate tests remain in
place. These are focused regressions; no repeated manual account/boot loop is
required for this consolidation.

