<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt Package Management Contract (draft 0.1)

**Status:** design contract; **not implemented**. This document records
agreed architecture and accepted high-level selector semantics:
`@3.0` selects the newest eligible stable release in the 3.0 line, while
`@=3.0` matches an exact package-release identifier. The full identifier
grammar, version comparison and backend adaptation remain to be specified
before implementing a parser. No package backend or on-disk Ports/System
package format has been chosen.

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
| `install` | Resolve and retain a selected release plus dependencies. For Ports, first installation of a directly requested application also establishes its default activation; later installs leave the existing activation unchanged. |
| `upgrade` | Show a complete proposed upgrade **within the selected area**; after approval, install eligible releases while preserving old versions. Tracked Ports series aliases may advance; an active *series selection* stays the same. |
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
were fetched. A future read-only command such as `mpm ports list --available`
(or `mpm ports info gimp`) should show all eligible versions and their source;
the exact inspection command is not yet fixed. `install` and `upgrade`
resolve against the currently selected
local snapshot and MUST NOT perform a hidden `update`. If it is missing or
too old for the requested policy, report this and offer an explicit refresh.

Before changes, show the complete **resolved** plan: exact package releases,
added/removed dependencies, external capability requirements, selected
repository snapshot, download sizes where available, state migrations,
activation/reboot implications, and preserved prior versions. A `-y` flag
may skip confirmation of **that** plan; it cannot bypass validation,
cross-area safeguards, or version pins.

Installation and activation are separate operations, **with one deliberate
Ports convenience exception**: the first successful installation of a
directly requested application, when no version of that application was
previously installed or active, also activates the selected version/series
as the system-wide default. This first-install activation MUST be included
in the transaction preview. Installing further versions of that application
MUST NOT change its active selection, even if the new version is newer.
Dependency installations do not independently claim default command names.
If a default command is already owned by unrelated/local software, MPM must
not overwrite it; report the conflict and require explicit handling.

An explicit `mpm ports activate` selects an already installed exact release
or series for the system-wide profile. This is distinct from installing an
additional version. Kernel activation selects a boot target, never rewrites
the running kernel's module tree. For Base/System, a deployment references
a known compatible combination rather than forming every possible Cartesian
product of independent versions.

Rollback selects previously published, still available content. Persistent
`/etc`, `/var`, and future user data are not automatically rolled back.
An old System may be incompatible with newly migrated state; reactivation
must warn about known compatibility/security problems.

## 3. Package selectors: release lines and exact identifiers (accepted)

**Decision:** `gimp@3.0` selects the **newest eligible stable published
release in the 3.0 line**, as listed in the chosen local catalog snapshot.
`gimp@=3.0` instead requests a package whose **canonical release identifier
is exactly `3.0`**; it does not match `3.0.0` or `3.0.8`. An exact
identifier must actually exist in the catalog.

This deliberately favors a convenient release-line selector for users who
want subsequent bugfix releases without crossing into another release line.
The exact form is explicit for reproducible or pinned choices. We rejected
making `@3.0` exact-by-default because that would unexpectedly exclude
maintenance releases such as `3.0.8`.

The CLI must display the exact resolved result. "Newest" means newest
**eligible in the selected channel and local snapshot**, not a claim that
the selected release has the fewest bugs or is universally the safest.
Other ecosystems also distinguish exact matching and release-series
matching (for example Python packaging uses `==3.0` versus `==3.0.*`);
Mojt uses its own notation, not Python's version standard.
See [Python Packaging: version specifiers](https://packaging.python.org/en/latest/specifications/version-specifiers/).

### Selector examples (full grammar still to be specified)

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

Then, under the accepted release-line/exact distinction and the illustrative
package-revision convention above:

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

### Upgrade intent is retained per request (accepted)

MPM remembers the installation selector as an upgrade policy **separately
from the resolved immutable artifact and active selection**. Each explicitly
requested series is its own tracked intent, even for the same application:

- Unqualified `gimp`: propose newer eligible stable releases without a
  version-series restriction.
- Series `gimp@3.0`: propose only newer eligible releases in the 3.0 line.
- Exact `gimp@=3.0.8-r2`: **never propose a version upgrade** for that
  exact request; report known security advisories without silently changing
  it.

If both `blender@4.9` and `blender@5.3` have been requested, a normal
`mpm ports upgrade` may propose newer releases in **both** series. Each
installed release remains available, and the old release is not overwritten.
`mpm ports update` merely refreshes metadata, never installed software.

An explicit `mpm ports activate gimp@3.0` selects the installed **3.0
series**, without downloading anything. The active selector is retained:
subsequent approved `upgrade` operations may advance the binary reached
through the active 3.0 series, but MUST NOT silently switch the active
series to 3.1. An explicit `activate gimp@=3.0.8-r2` instead selects that
exact immutable release, and its unqualified command stays pinned there.
When the selected series has no installed candidate, activation fails rather
than fetching a new one. The choice and resolved target must be displayed.

An ordinary upgrade MUST NOT mutate an exact project lock or change the
project's resolved dependency closure. The mechanism for changing an
existing requested policy (e.g. from a series to unqualified latest) is
not yet specified; such a change must be explicit.

### Command aliases and system-wide activation (accepted)

Every installed directly addressable application version should be
invocable through ordinary Unix command names, without exposing store
paths. MPM manages **three logically distinct alias types**:

| Alias | Contract |
| --- | --- |
| `blender` | The explicitly active **series** or **exact release** in the system-wide profile; created on first install |
| `blender-4.9` | A **moving series alias**, pointing to the currently selected installed Blender 4.9.x release for that tracked series; it advances on an approved series upgrade or explicit series activation |
| `blender-4.9.12-r2` | A **fixed exact-release alias**, pointing to that immutable package release for as long as it remains installed |

Alias names above illustrate a possible canonical package revision suffix
(`-r2`); the real naming/escaping convention remains open. The exact
alias must distinguish distinct rebuilds of an identical upstream version.
Aliases must not be created by ambiguous string-prefix matching.
Every installed release of a directly requested command is given an exact
release alias, even when it was installed through a series selector;
a later series upgrade retains the old exact alias. For a package with
multiple executable commands, alias naming and command-name conflict
policies still need specification.

An installation of `blender@=4.9.12-r2` publishes a fixed alias for that
release; installation of `blender@4.9` publishes the tracked series alias
as well. They may point to the same underlying object and need not duplicate
it. The initial default activation follows the *selector* used for the
first explicit install:

- First `install blender@4.9` makes `blender` follow the 4.9 **series**.
  An approved future 4.9.x upgrade may advance both `blender-4.9` and
  the effective target of `blender`.
- First `install blender@=4.9.12-r2` makes `blender` follow that **exact
  release**; no future upgrade changes its target.
- Later `install blender@5.3` creates the 5.3 series alias and installs
  its dependencies, but `blender` continues to refer to 4.9 until the
  user explicitly runs `mpm ports activate blender@5.3`.

The default alias targets a series/exact selection, **not** simply the
highest installed version. This makes activating a new series explicit
without blocking ordinary approved maintenance upgrades *within* an active
series. Merely refreshing a repository catalog or installing an additional
version (even a newer release in an **already installed series**) MUST NOT
advance existing series or default aliases. A new exact alias can still be
created for that added release. An approved `upgrade` advances its tracked
series alias, and an explicit `activate` can select the newest installed
eligible release in the requested series. In other words, a moving series
alias follows the last **accepted series target**, not every background
change in the set of installed releases.

Conceptually, the public aliases can be symlinks (or small launchers where
necessary) into MPM-owned profiles backed by immutable objects. MPM MUST
publish complete profile changes atomically and preserve old object
references needed by pins and rollback. A direct symlink into a store is
not a universal solution for applications with runtime layout or invocation
requirements; the actual backend integration remains open.

**Scope for the first implementation:** a system-wide activation profile
whose commands are placed in a dedicated MPM-owned directory on `PATH`.
`/usr/local/bin` is an illustrative traditional location, not a settled
namespace; MPM must not overwrite administrator-owned paths. Per-user
overrides (for example `~/.local/bin` earlier on `PATH`) and project-specific
profiles are intended, but their mechanics are deferred.

### Worked activation example

```text
mpm ports install blender@4.9
  -> installs 4.9.12, first Blender install: activates series 4.9
     blender        -> 4.9.12
     blender-4.9    -> 4.9.12

mpm ports install blender@5.3
  -> installs 5.3.7 without changing the active series
     blender        -> 4.9.12
     blender-4.9    -> 4.9.12
     blender-5.3    -> 5.3.7

mpm ports activate blender@5.3
  -> changes the default series only
     blender        -> 5.3.7
     blender-4.9    -> 4.9.12
     blender-5.3    -> 5.3.7

mpm ports upgrade
  -> with user approval, installs 4.9.13 and 5.3.8; retains old releases
     blender        -> 5.3.8
     blender-4.9    -> 4.9.13
     blender-5.3    -> 5.3.8
     blender-4.9.12 -> old exact release, retained while installed
```

The example suppresses packaging revisions in the displayed release names;
real exact-release aliases must account for them. The synthetic example
also assumes none of the existing public command names conflict with
unmanaged local files. An exact project lock
continues to reference its own immutable release and dependency closure
throughout these operations.

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

1. Specify detailed matching/version ordering for epochs, pre-releases,
   nonnumeric upstream versions and backend package revisions, while
   preserving the accepted `@3.0` versus `@=3.0` distinction.
2. Choose how full package identities are represented across backends
   (upstream version, packaging revision/epoch, repository and content digest).
3. Specify commands for explicitly changing/removing retained upgrade
   intents and for listing installed series, exact releases and active
   selections.
4. Specify the profile namespace, command-name collision policy, exact alias
   naming for packaging revisions and packages with multiple executables;
   user and project override mechanics are deferred.
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
packaging, a selector parser, package-backed System composition,
external capability packages, signed catalogs and a production boot selector.

This draft is a contract for future design review, not a command reference
for existing Mojt tools.
