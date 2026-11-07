<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Base install and status: owner-agreed contract

Owner-agreed behavior, 2026-11-06. The first
[implementation](base-installation.md) merged in PR #40. The subsequent
[deployment integration](base-boot-staging.md) is in PR #41, with bounded
owner boot/return acceptance passed on 2026-11-07. This is the
behavior contract in the [six-step plan](mpm-consolidation-plan.md), authorized
by the owner after the command-meaning review. It preserves the
[MPM user model](management-workflow.md)
and accepted independent lifecycles. No public MBT spelling is decided here.

## The two commands in one sentence each

`mpm base install` makes one complete exact Base available on the chosen
installation, including a validated rootfs tree, without changing machine
configuration, next boot or the running system.

`mpm base status` explains which exact Bases are installed, which Base the
selected next-boot deployment references, and which Base is running; it changes
nothing and does not invent an answer from a version label.

## What counts as installed

A Base is a complete Unix userspace, distributed as one native package wrapping
`rootfs.tar.zst`, its release manifest and provenance. It is not a set of mutable
runtime packages. A successful installation requires all of:

1. Accepted exact artifact/transport identity and an explicit trust decision.
2. Complete verified descriptor, retained archive, provenance and install receipt.
3. A separately validated rootfs realization on this target, with measured
   inventory and exact source/extractor identity. Preserve the Base's reviewed
   target ownership, modes and supported links; do not apply generic normalized
   archive-storage modes to a bootable Unix rootfs.
4. Complete publication evidence linking that realization to its exact artifact.
   Validate declared requirements/dependencies; refuse unsupported required
   mechanisms rather than ignoring them.

A cached archive is **cached**, not installed. A published archive-only native
object with no completed Base realization is **retained, not installed**. An
interrupted realization is **incomplete**, not installed. These distinctions
survive restart and are visible in diagnostics. Installation does not yet prove
compatibility with a particular System/Kernel or boot readiness.

The generic [artifact store](formats/draft-v1/artifact-storage.md) and
[native deployment layout](formats/draft-v1/boot-deployment-v2.md) are implementation
inputs, still drafts. Full artifact IDs identify stored objects; realization
records bind their measured runtime trees. A release label is display metadata,
not a storage key. Installing `0.1.3-r2` must not overwrite `0.1.3-r1`, and two
different full artifacts advertising the same release ID must also coexist.
An ambiguous catalog release must be disambiguated before installation.

## Installation effects and limits

| Resource | Allowed result of Base install |
| --- | --- |
| Accepted metadata | Read the chosen snapshot; no implicit refresh or alternative provider/build |
| Cache | Acquire/reverify the exact approved archive and retain origin evidence |
| Base content | Add the exact verified object and complete private realization beside existing content |
| Base receipt/history | Record the exact committed result; preserve the original receipt on an identical repeat |
| Requested policies | An exact import is not a new moving upgrade wish or a replacement of configuration/interactive claims |
| `/etc`, `/var`, `/home`, `/root` machine state | No default merge, file removal, account creation, schema migration or home modification |
| Boot menu, selected deployment, current links | Unchanged; no implicit staging or selection |
| Running root, processes, services, Kernel/modules | Unchanged; no restart or module-tree replacement |
| Device layout | Unchanged; no mount/format/partition/bootstrap operation |

Cache/MPM bookkeeping under persistent `/var` may of course change; the machine
state rule excludes these explicitly planned management writes. The new Base's
own `/usr/etc` defaults are retained as immutable content and are not copied
into persistent `/etc` during installation.

Missing defaults or supported state initialization belong to an explicitly
approved deployment/lifecycle preparation or a new-target bootstrap. Required
unknown effects block that later transition. Existing local files are never
silently overwritten/removed. This proposal does not implement or authorize an
automatic defaults merge merely by adding a lifecycle label.

The existing `mojt-base-install install --no-activate` still prepares persistent
state and keys its rootfs by release label. Therefore wrapping that command
unchanged does **not** meet this contract. Reuse its reviewed archive/identity
validation and extractor policy behind a content-only boundary; do not duplicate
the entire installer or change old experimental disks implicitly.

## Proposed invocation boundary

The first bounded implementation should mirror the established exact Kernel
import interface. These are interface examples with placeholder IDs; substitute real verified values:

```sh
mpm base install --from-file /packages/base-EXACT.tar.zst \
  --expected-id sha256:FULL_ARTIFACT_ID --dry-run
mpm base install --from-file /packages/base-EXACT.tar.zst \
  --expected-id sha256:FULL_ARTIFACT_ID -y

mpm base install --source local --expected-id sha256:FULL_ARTIFACT_ID \
  --archive-sha256 FULL_ARCHIVE_SHA256 --dry-run
mpm base install --source local --expected-id sha256:FULL_ARTIFACT_ID \
  --archive-sha256 FULL_ARCHIVE_SHA256 -y

mpm base status
mpm base status --verify
mpm base status --json
```

Local-file input verifies the complete native wrapper and nested rootfs before
publishing a successful install. Source input reuses accepted metadata, owner
policy and native cache; its preview must distinguish metadata validation from
archive/rootfs verification still to be performed. Optional exact snapshot input
has the same meaning as the established Kernel source input. No hidden update,
build, repository publication, bootstrap or activation occurs.

For normal use, the target remains the current installation; the user should not
need to name internal directories. Explicit offline/new-target operation must
identify one target installation consistently across content, realization and
status. Do not silently interpret global `--root` as a disk in one area and a
registry in another. The first implementation uses explicit `--disk-root` for both actions, matching
the existing native Kernel boot target option. It rejects global `--root` for Base.
Its versioned target/receipt/status records are described in the implementation guide.

The existing name/series/exact selector model also remains the intended normal
catalog route: for example the Base family `mojt`, `mojt@0.1` or
`mojt@=0.1.3-r1`. Connecting that route and persisted wishes is a separate join,
not a reason to make users type a full hash for every everyday install. Selectors
must resolve one exact build from accepted metadata and preserve other wishes.
Their presence here does not claim today's Base CLI accepts positional selectors.
Exact import alone does not adopt a moving policy. Upgrade is driven by explicit
tracked wishes, never by iterating over every installed Base.

## Preview, repeat and failure

Preview shows the target, exact package/release/build, archive/source evidence,
known download/storage requirements, intended content writes and explicit
`next boot: unchanged`, `running: unchanged`, `machine configuration: unchanged`.
Unknown requirements are labelled or block as appropriate. It creates no store,
target, lock, receipt, realization or acquisition root, and executes no package
code. Reading a local archive is allowed; source preview need not download it.

A repeat of a complete identical installation verifies retained content and is
a no-op: no new receipt/history entry, realization or selection. It must work
from retained verified content when the original source/archive is unavailable;
source-mode use still checks the accepted authorization binding where applicable.
Different compressed bytes for the same artifact do not replace the first
retained representation/receipt. Damage is reported rather than repaired by an
unapproved overwrite. Changed required realization semantics need explicit
versioned support, not silent reinterpretation of a prior receipt.

This no-op rule concerns an identical import and unchanged wishes. A later
configuration/interactive join may add a new independent reason without fetching
bytes again; that is an explicit request-state change, not a new installation
receipt or permission to erase another reason. Keep the original content receipt
and explain the logical change separately.

Before final publication, failure leaves existing complete installs and choices
intact. Verified cache/retained objects or incomplete work may remain, but are
reported accurately. A rename followed by failed durability flush is publication
uncertainty; retain potentially published content for inspection. No claim of one
atomic commit across cache, object storage, realization and persistent effects.

## Status: the operator's answer

Human output leads with **Running**, **Next boot**, and **Installed**, using
release labels plus artifact identifiers. It names the deployment behind a
running/selected observation and says whether they agree. Short IDs are display
abbreviations only; full IDs remain available in JSON and exact inspection.
Neither a pathname called `current` nor `/usr/lib/os-release` proves an exact
artifact. Do not infer identity by choosing the only matching version in a store.

Illustrative output, **not an accepted machine-output schema**:

```text
Base on this installation
Running:    0.1.3-r1  sha256:AAAA...  deployment sha256:1111...
Next boot:  0.1.3-r1  sha256:AAAA...  deployment sha256:1111...

Installed:
  0.1.3-r1  sha256:AAAA...  running, next boot
  0.1.4-r1  sha256:BBBB...  not selected

Integrity: verified at installation; use --verify for a current content check
```

After selecting a complete deployment containing BBBB, **Next boot** changes;
**Running** remains AAAA until an actual reboot. Install itself leaves both at
AAAA. The two observations can point to different System/Kernel combinations;
status identifies their complete deployments rather than implying an independent
Base toggle. A booted artifact with missing/damaged local records is reported as
a running observation plus a retention/integrity problem, not simply omitted.

| Target/evidence condition | Required status behavior |
| --- | --- |
| No store/installation yet | Show no installed content and explicit unavailable target identity; create nothing |
| No selection record | Next boot unknown/not configured, never guess a default from installed versions |
| Inspecting an offline target | Running unknown for that target; never attach the inspection host's Base identity |
| Missing authoritative running record | Running exact identity unknown; a label may be shown as an unverified observation |
| Stored-only or interrupted realization | Separate retained/incomplete entries; do not count as installed |
| Damaged/unsupported required records | Diagnostic and nonzero failure; never convert into an empty successful result |
| Normal read | Validate bounded records; report content verification time/scope honestly |
| `--verify` | Recheck retained archive, descriptor, complete realization inventory and required evidence; fail on damage |

Ordinary users can inspect readable target records. Shared mutation requires an
administrator. Status requires no source refresh/provider/network, package code,
mount, new lock file or cleanup. Machine output is versioned, includes full IDs,
target and integrity scope, and distinguishes unknown from absent and failure.
Its exact schema/exit classes must be defined before implementation; the draft
human table is not that schema.

## What comes after agreement

Implement and test content-only Base import, realization, origin retention and
honest status first. Cover same-label different artifacts, no-op/offline repeat,
unsafe archives/links, corruption, unknown formats, incomplete/publication failure,
read-only status and unchanged state/boot selections. Reuse cache/transaction
primitives and the reviewed Base extractor; do not build a competing installer.

Then generalize deployment staging/selection to a changed Base while preserving
the chosen System and Kernel, subject to explicit compatibility/state/management
gates. Only that next join needs a new owner boot test. System import/composition
and its deployment join follow in the governing roadmap, before public MBT
bootstrap/build integration. No repeated Kernel matrix is required here.

**Owner agreement:** the two command meanings and the definition of installed
Base above were accepted on 2026-11-06, with defaults/state preparation deferred
to an explicit transition. Exact import/status implementation is authorized.
New MBT spellings and Base deployment/upgrade integration remain separate work.
