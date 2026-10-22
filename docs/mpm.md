<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt Package Management Contract (draft 0.1)

**Status:** proposed interface contract; **not implemented**. This document
records the agreed architecture and a deliberately explicit **proposal** for
version selector syntax. Version selector syntax remains subject to review
before it becomes a compatibility promise. No package backend or on-disk
Ports/System package format has been chosen.

The guiding rule is that Mojt can update **Base, System, Kernel, and Ports
independently**, without silently updating applications or pinned project
toolchains during an operating-system update. `mpm` is the stable user-facing
front-end; it need not implement its own general dependency solver or use the
same backend for every area.

See [the manifesto](manifesto.md), [architecture](architecture.md), and
[Base release format](base-format.md) for the established layer boundaries.

## 1. Areas and boundaries

The command shape is:

```text
mpm <area> <action> [arguments]
```

| Area | Scope | Ownership / lifecycle |
| --- | --- | --- |
| `base` | Complete, glibc-based Base releases | Whole-image installation and activation; not mutable runtime packages |
| `system` | System userspace, init, services, profiles | Independent release lifecycle and package construction |
| `kernel` | Linux kernel, matching modules and boot artifacts | Separate, version-unique System component; independently selectable at boot |
| `ports` | Applications, toolchains and their libraries | Parallel, versioned installations with independently activated profiles |

`kernel` is a CLI area for a **System-owned component**, not an independent
fifth OS layer. Its release identity includes a unique build identity; a
`uname -r` string alone is not sufficient to distinguish all builds.

Actions in one area MUST NOT implicitly install, upgrade, remove, or activate
content in another. If an operation requires a different Base or Kernel, the
plan must explain the requirement and obtain explicit approval for a
cross-area plan. An approval option such as `-y` MUST NOT silently expand
the requested scope.

Each package-managed area must be isolated at least at the levels of
**repository selection, package database, dependency resolution, and
file ownership**. Separate databases are not enough if installation scripts
or runtime library lookup can modify or use another area's mutable files.

Base and Kernel advertise verified external capabilities, e.g.,
`glibc = 2.41` and `linux >= 6.1`. System may depend on these without
the System backend taking ownership of their files. A generic minimum kernel
version is the default System constraint; external modules and some drivers
may require exact-build matches, feature checks, or narrower constraints.
A declared `provides` is not a substitute for checking the actual ABI.

## 2. Operations

| Action | Intended behavior |
| --- | --- |
| `update` | Refresh local repository/release catalog metadata, like `apt update`. No packages installed, removed, or activated. |
| `install` | Resolve and install a selected release plus dependencies; do not activate it automatically. |
| `upgrade` | Show a complete proposed upgrade **within the selected area**; after approval, prepare/install the new version(s) without silently discarding old versions. |
| `activate` | Select an **already installed** version for a chosen profile, or a bootable deployment for Base/System/Kernel. |
| `remove` | Remove an unreferenced, inactive installation only when pinned projects, profiles, dependencies, and rollback references do not need it. |

Examples, describing desired behavior rather than runnable commands:

```sh
mpm base update
mpm system upgrade
mpm kernel upgrade
mpm ports update
mpm ports install gimp
mpm ports install gimp@3.0
mpm ports activate gimp@3.0
mpm ports install gcc@14
```

`update` operates on the **local catalog**, not installed payloads. The user
must be able to inspect which repository snapshot and package/release versions
were fetched. `install` and `upgrade` resolve against the currently selected
local snapshot and MUST NOT perform a hidden `update`. If it is missing or
too old for the requested policy, report this and offer an explicit refresh.

Before changes, show the complete **resolved** plan: exact package releases,
added/removed dependencies, external capability requirements, selected
repository snapshot, download sizes where available, state migrations,
activation/reboot implications, and preserved prior versions. A `-y` flag
may skip confirmation of **that** plan; it cannot bypass validation,
cross-area safeguards, or version pins.

Installing is not activating. For Ports, activation selects an existing
installation in an explicit profile while keeping directly addressable older
versions available. Kernel activation selects a boot target, never rewrites
the running kernel's module tree. For Base/System, a deployment references a
known compatible combination rather than forming every possible Cartesian
product of independent versions.

Rollback selects previously published, still available content. Persistent
`/etc`, `/var`, and future user data are not automatically rolled back.
An old System may be incompatible with newly migrated state; reactivation
must warn about known compatibility/security problems.

## 3. Package selectors: `gimp@3.0` (PROPOSED, NOT YET FINAL)

This is a conscious choice between two reasonable user interfaces:

1. **Exact by default:** `gimp@3.0` denotes only a release actually named
   `3.0`. This is trivial to explain and implement, but does not find later
   bugfix releases such as `3.0.8`; users must know and type the full version.
2. **Release-line selector:** `gimp@3.0` means the **newest eligible
   published stable release in the 3.0 line** in the selected local catalog.
   It is more convenient for users who mean "GIMP 3.0, with current fixes",
   but requires an explicit matching/ordering contract.

**Recommended choice for discussion: option 2**, with an unmistakable syntax
for exact requests. The CLI must print what a selector actually resolved to;
"latest" is a repository decision, not proof that the chosen release has
the fewest bugs or all security fixes.

### Proposed selector grammar

| Request | Meaning |
| --- | --- |
| `mpm ports install gimp` | Newest eligible stable GIMP in the selected channel and local catalog |
| `mpm ports install gimp@3.0` | Newest eligible stable member of GIMP's `3.0` release line |
| `mpm ports install gimp@3.0.8` | Newest eligible package revision for upstream release line `3.0.8` |
| `mpm ports install gimp@=3.0.8-r2` | **Exact package release identifier** `3.0.8-r2`, if present |
| `mpm ports install gimp@=3.0` | **Exact package release identifier** `3.0`; not automatically `3.0.0` or `3.0.8` |

These examples assume a packaging scheme with an upstream version and a
packager revision such as `-r2`. The canonical identifier format and
normalization rules are **not yet defined** and must not be copied blindly
from apk, XBPS, Debian, Nix, or SemVer. Equality means equality of the
catalog's canonical full package-release identifier. A full artifact identity
additionally includes its repository/source and immutable content digest.

The `@3.0` rule matches **numeric, dot-delimited upstream version
components**, not arbitrary textual prefixes: `3.0`, `3.0.1`, and
`3.0.10` match, but `3.1`, `3.00`, `13.0`, and `3.0rc1` do not.
Pre-releases are excluded unless the user explicitly selects an appropriate
pre-release channel or exact identifier. Ordering must be numeric where
components are numeric, so `3.0.10` is newer than `3.0.9`, and must use
backend-aware revision comparisons for package rebuilds.

Not all upstream versions follow dotted numeric rules. For nonconforming
versions, the backend must provide a reliable version adapter or `mpm` must
require an exact identifier; it MUST NOT guess from string sorting.

### Concrete resolution example

Imagine that the *selected local snapshot* contains:

```text
gimp 3.0.0-r1   stable
gimp 3.0.8-r1   stable
gimp 3.0.8-r2   stable
gimp 3.1.0-r1   stable
gimp 3.0.9-rc1  preview
```

Then, under the proposed rules:

```text
mpm ports install gimp          -> gimp 3.1.0-r1
mpm ports install gimp@3.0      -> gimp 3.0.8-r2
mpm ports install gimp@=3.0.8-r1 -> gimp 3.0.8-r1
mpm ports install gimp@=3.0     -> not found
```

`@3.0` is a **one-time resolution for the current transaction**, not a
floating symlink: once `3.0.8-r2` is installed, the installed object stays
that release. A later `mpm ports update` may reveal `3.0.9`, but neither
`update` nor `install` silently changes any active profile.

**Recommended tracking policy, still open for review:** remember the user's
requested selector (`3.0`, exact `=3.0.8-r2`, or channel default) as an
explicit *future upgrade constraint*, separate from both the installed
artifact identity and the active profile. Thus an ordinary upgrade of a
`gimp@3.0` intent may propose `3.0.9` but not `3.1.0`, whereas an exact
request remains pinned until deliberately changed. No such upgrade may
change a separately pinned project profile without explicit approval.

`activate gimp@3.0`, if accepted as selector syntax, should resolve only
among **already installed** matching versions (never fetch or install).
To avoid ambiguity, activation must show the selected exact release and
profile, and fail if the backend cannot determine a unique deterministic
winner. Activation by a full exact ID is always possible.

For reproducible project locks and rollback, record **not just the requested
selector**, but the exact resolved package release, catalog snapshot/source,
and immutable artifact identity with transitive dependencies. Package names
or upstream version strings alone are insufficient.

## 4. Backend requirements and separation of concerns

`mpm` defines the semantics above. Its backend(s) implement acquisition,
dependency resolution, package installation and versioned content storage
using established technology where feasible.

Required capabilities, whether native to a backend or provided by a small
Mojt adapter:

- Isolated catalogs, install targets, package databases and update scopes.
- Versioned dependencies and virtual/external capability providers without
  letting a System backend install or remove Base/Kernel-owned content.
- Transaction simulation/inspection and deterministic resolution against a
  selected catalog snapshot.
- Ability to retain multiple installed versions. This does **not** require
  two versions of the same package name in a single backend database if
  separate immutable roots, prefixes, or store objects guarantee coexistence.
- Ports-specific versioned runtime library closure, pinned toolchains and
  independent activation. An alternative installation **root** is not
  automatically a relocatable installation **prefix**.
- Controlled staging of package scripts, hooks, account changes and services
  without writing to live persistent state or starting host services.
- Safe ownership, integrity, provenance and explicit cleanup of unreferenced
  content. Plain SHA256 is not release authentication; trusted signatures
  and repository policy remain separate work.
- Visibility into why a package is retained (active profile, dependency,
  project pin, or rollback reference).

Current candidates include apk, XBPS, FreeBSD pkg, pkgsrc/pkgin, Nix, and
other established managers. Nix's immutable store and dependency closures
may fit Ports especially well, but its store location, own libc closures,
and package-revision addressing need explicit evaluation. None is selected
by this contract. Base does not acquire a mutable runtime package database
because a backend exists for System or Ports.

## 5. Deliberately unresolved details

1. Confirm or change the proposed `@3.0` **release-line** default versus
   **exact** semantics before implementing the command parser.
2. Choose how full package identities are represented across backends
   (upstream version, packaging revision/epoch, repository and content digest).
3. Decide whether an installation selector persists as an upgrade constraint
   (recommended above), and how users explicitly change or remove that intent.
4. Define explicit profile scope (system-wide, user, project), and how
   activation conflicts and command-name collisions are reported.
5. Define signed repository snapshots, channel preference, downgrade and
   pre-release policy, and handling of withdrawn or known-vulnerable builds.
6. Select and test System and Ports backend candidates independently; decide
   the minimum set of external Base/Kernel capabilities they can safely use.
7. Establish System release composition and how System-owned files are made
   visible beside the Base tree. Avoid committing to an overlay/prefix
   mechanism before testing it.
8. Specify transactional publication, boot success/fallback behavior and
   state migration warnings. No automatic state rollback is promised.

## 6. Implementation status

**Implemented today:** versioned whole-image Base packaging, multi-generation
installation/activation and conservative preservation of persistent state;
a QEMU VM prototype with a System-owned BusyBox init/login, a host-supplied
kernel and a combined System/Base login banner.

**Not implemented:** `mpm`, Ports installation and activation, System release
packaging, the proposed selector grammar, package-backed System composition,
external capability packages, signed catalogs and a production boot selector.

This draft is a contract for future design review, not a command reference
for existing Mojt tools.
