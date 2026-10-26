<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt Package Management Contract (draft 0.2)

**Status:** accepted design contract with a partial experimental implementation.
The current CLI implements a subset of Ports operations; the commands below
are design examples unless identified as implemented in section 6. This
document records the update model accepted on 2026-10-26 and the previously
accepted high-level selector semantics:
`@3.0` selects the newest eligible stable release in the 3.0 line, while
`@=3.0` matches an exact package-release identifier. The full identifier
grammar, version comparison and backend adaptation remain to be specified
before implementing a parser. Nix is selected for Ports and, for early Mojt
versions, for System package acquisition and shared dependency storage.
System release/deployment formats and the full command grammar remain open.

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

Base is distributed and managed as one complete release. Its construction
may use packages or source builds, but the installed Base is not maintained
through individual runtime package upgrades. Build provenance remains
inspectable. See the [Base release unit](base-format.md#accepted-base-release-unit-2026-10-26).

`kernel` is a CLI area for a **System-owned component**, not an independent
fifth OS layer. Its release identity includes a unique build identity; a
`uname -r` string alone is not sufficient to distinguish all builds.

Actions in one area MUST NOT implicitly install, upgrade, remove, or activate
content in another. If an operation requires a different Base or Kernel, the
plan must explain the requirement and obtain explicit approval for a
cross-area plan. An approval option such as `-y` MUST NOT silently expand
the requested scope.

Acquiring or retaining an immutable shared dependency is not a change to
another area's declared package selection or activation. The shared-store
exception below does not permit such changes as a side effect.

Each package-managed area must preserve separate **catalog/repository
selection, desired package sets, dependency-resolution scope, activation state
and mutable-file ownership**. The accepted early Nix backend shares the
immutable store and its object/reference database between System and Ports;
separate backend databases are not required for that case. A shared object can
be retained by both areas without making their activation choices shared.
Installing a Ports dependency must not change the selected System generation
or its services. Shared storage does not permit package scripts or activation
to overwrite another area's mutable files.

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
| `upgrade` | Propose changes to tracked requests **within the selected area**, respecting their policies and pins. After approval, retain eligible new releases and advance permitted selections, preserving previous content. Boot-area selections take effect at the next boot; Ports selections apply to new program starts. |
| `activate` | Select an **already installed** version for a chosen profile, or a bootable deployment for Base/System/Kernel. |
| `remove` | Remove selected Ports installations from the current profile; if an active installation is removed, choose an installed replacement by the history rule below. Physical collection is separate and must preserve dependencies, project pins and rollback references. Base/System/Kernel deployment removal needs separate safeguards. |

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
mpm ports upgrade neovim
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

Consistent verbs do not require the same unit of update or recovery in every
area. Base uses complete releases, System uses coherent generations, and
Ports uses independent application installations and active selections.

Installation and activation are separate operations, **with one deliberate
Ports convenience exception**: the first successful installation of a
directly requested application, when no version of that application was
previously installed or active, also activates the selected version/series
as the system-wide default. This first-install activation MUST be included
in the transaction preview. Installing further versions of that application
MUST NOT change its active selection, even if the new version is newer.
Outside this first-install Ports exception, `install` retains content without
advancing the selected profile/deployment. Approved `upgrade` may advance a
selection under its stored policy; explicit `activate` chooses installed content.
Dependency installations do not independently claim default command names.
If a default command is already owned by unrelated/local software, MPM must
not overwrite it; report the conflict and require explicit handling.

An explicit `mpm ports activate` selects an already installed exact release
or series for the system-wide profile. This is distinct from installing an
additional version. Kernel activation selects a boot target, never rewrites
the running kernel's module tree. For Base/System, a deployment references
a known compatible combination rather than forming every possible Cartesian
product of independent versions.

Boot rollback selects a previously published, still available deployment.
Ports recovery normally selects an installed application version explicitly;
it does not require restoring a whole Ports generation. Persistent
`/etc`, `/var`, and future user data are not automatically rolled back.
An old System may be incompatible with newly migrated state; reactivation
must warn about known compatibility/security problems.

### System generations and boot deployments (accepted 2026-10-26)

A successful upgrade that changes System content MUST publish a new immutable
System generation. Each generation records its exact composition, requests,
source/catalog inputs and resolved dependency references. Previously published
generations retain their original contents. Resolution with no changes reports
a no-op rather than creating a duplicate content generation.

Tracked requests belong to the selected logical profile. A generation kept
for recovery is a historical result, not another independent upgrade request.
An upgrade does not iterate over every retained generation and update each
one. Requested policy, resolved artifact identity and selected content MUST
remain distinguishable; an exact resolved reference alone does not imply an
exact-version upgrade policy.

A boot deployment binds exact Base, System and Kernel build identities to
the required modules and boot artifacts. These component identities and the
deployment identity are distinct:

| Operation | New content and deployment | Preserved component choices |
| --- | --- | --- |
| `mpm base upgrade` | Install a complete published Base release and prepare a deployment using it | System userspace and Kernel |
| `mpm system upgrade` | Publish a changed System generation and prepare a deployment using it | Base and Kernel |
| `mpm kernel upgrade` | Retain the new Kernel build, matching modules and boot artifacts, and prepare a deployment using them | Base and System userspace |

A Base upgrade installs an existing release identity; it does not manufacture
a new Base release version locally. A Kernel-only change need not create a
new System userspace release. Kernel remains a System-owned component, with
its own MPM upgrade scope. Compatibility validation may reject a proposed
combination or require an explicitly approved cross-area plan.

After approval and validation, an upgrade advances the selected deployment
where the stored policy permits it. Explicit pins remain effective. The
candidate and its boot artifacts must be complete before selection; a failure
before that commit point leaves the previously selected deployment in place.
The initial activation model selects the next boot; it neither reboots the
machine automatically nor switches the running root, kernel or services.
Live System activation would require a separate, explicit design.

This is the accepted user model, not the current builder's on-disk format.
The [generation experiment](boot-generations.md) composes fresh images and
uses System labels that also bind kernel inputs. It has not implemented
independent Kernel selection or an updater for an existing boot disk.

### Installed, selected and running state (accepted 2026-10-26)

Status and transaction previews MUST distinguish:

- Installed content: available exact releases and their retained dependencies.
- Selected content: what new program starts or the next boot will use,
  together with its selection/upgrade policy.
- Running content: the currently booted Base/System/Kernel; already running
  applications may likewise continue using earlier content.

For boot areas, subsequent mutations use the selected deployment as their
baseline even when another deployment is still running. If S17 is running
and S18 is selected for the next boot, a further upgrade starts from S18's
profile and requests. The plan shows both the running and selected identities
and the baseline it will change. Read-only inspection can describe either.

The user must be able to inspect each System generation's directly selected
components, exact builds, source inputs, dependency closure and differences
from a previous generation. A generation number alone is insufficient.
Views should separate explicit choices from their dependencies. Exact
inspection command names and output schemas remain to be specified.

### Ports recovery and transaction history (accepted 2026-10-26)

Ports does not require a user-managed, numbered generation of the entire
application collection after every upgrade. Its public model is parallel
installed versions, per-application active selections and upgrade policies,
and readable transaction history. `mpm ports upgrade neovim` targets the
tracked Neovim requests and shows any affected series; unrelated application
requests and active selections remain unchanged. Immutable dependency
objects may be acquired or reused without changing those other selections.

Previous installed versions remain available. In the intended interface,
if the exact release is available from the selected catalog, recovery can be:

```sh
mpm ports install neovim@=0.12.5
mpm ports activate neovim@=0.12.5
```

These are contract examples, not commands accepted by the current CLI.
If the version is already installed, only activation is needed.
Installing another version preserves the existing active choice. Explicit
exact activation pins the default command to that release. Separately tracked
upgrade requests are not silently removed or rewritten by that activation.
Historical release availability is not guaranteed by a version string alone;
retained installed artifacts provide the normal recovery path.

Transaction history MUST identify the request and policy, source/catalog,
exact old/new builds, installed-set and active-selection changes, and retained
previous versions. A general transaction-undo command is a possible later
convenience, not an accepted command or a prerequisite for application-level
recovery. Its interaction with later changes would need a separate design.

MPM still publishes complete, validated profile changes atomically. Internal
profile snapshots are an implementation mechanism, not a requirement to
expose or permanently retain a numbered Ports generation for every operation.
History/checkpoint retention and physical GC policy remain future work.
Collection MUST preserve still-installed versions, dependencies, project pins
and explicitly retained recovery references across all areas. The current
prototype retains old profiles and roots; this decision does not add pruning.

### Ports removal and historical fallback (accepted 2026-10-24)

Removal from the current Ports installation set is distinct from physically
deleting immutable objects. Removing an inactive installation leaves the
active selection unchanged. Removing the active installation MUST select a
remaining installation of that application, using this order:

1. The most recently activated remaining installation.
2. If none has ever been active, the most recently installed remaining installation.
3. If none remains, remove the application's unqualified command aliases.

Record ordering with committed event sequences, not wall-clock timestamps
or upstream version comparison. First-install activation and removal-triggered
fallback count as activations; an idempotent activation changes no history.
Distinct builds of one upstream version are distinct installations. Resolve
all targets of a multi-removal before choosing replacements: an installation
being removed cannot become a fallback in the same transaction.

For an active series selection, apply the same ordering within that series
first. If the series becomes empty, apply it to the remaining installations
and explicitly show the resulting change of selection in the preview. The
current Nix adapter implements exact activations only; series aliases remain
future work and MUST NOT be inferred from version prefixes.

Show all removals, exact fallback identities, lost/default commands and
retained rollback references before confirmation. Publish removal and
activation as one complete profile change. Any validation/import/publication
failure before the selection rename leaves the old profile selected. An I/O
failure after that commit point may mean the new profile was selected; report
the uncertainty and retain the complete generation for inspection. A bare name with multiple installed
versions is ambiguous in the initial wrapper: require exact identities from
`mpm ports list --exact`, rather than silently removing one or all versions.

Old profiles and project references may continue using the removed version.
Dependencies required by remaining applications are likewise retained. GC
may physically delete an object only after all protecting references have
been released. `remove` MUST NOT imply that disk space was reclaimed; report
when store objects are retained. A later, explicit retention/collection policy
will govern releasing rollback profiles and GC roots.

Existing prototype states predate activation-history tracking. On their first
relevant mutation, retain the recorded installation insertion order and mark
only the currently active versions as known activations. Report that earlier
activation order is unknown; do not fabricate historical choices. Read-only
commands and no-op transactions do not rewrite those states.

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

- Isolated catalogs, desired package sets, activation/install targets and
  update scopes. Nix's shared immutable store/reference database is allowed;
  MPM's logical area state and mutable-file ownership remain separate.
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

Nix is selected for Ports and, for early Mojt versions, for System package
acquisition and dependency storage. Both areas use one Nix store and
object/reference database; separate manifests, catalogs and activation state
define their logical boundaries. Its store location, own libc closures,
package addressing and Mojt-specific upgrade policies still need production
integration. This is not a commitment to NixOS or a permanent System
package/deployment format. Base does not acquire a mutable runtime package
database because a backend exists for System or Ports.

### Accepted early Nix exposure and service boundaries

The Nix CLI remains exposed for direct administration in early Mojt versions.
Mojt owns System generation selection, unit integration and service activation;
importing another System package or changing a Nix profile does not itself
constitute an MPM System activation. The current root-operated experiment has
no guard that forces direct Nix operations through MPM. The supported-operation
policy and detection/reconciliation of external changes remain open; MPM must
not pretend those safeguards are implemented.

The dependency model must distinguish these requirements:

| Requirement | Responsibility |
| --- | --- |
| Exact files/libraries in a Nix runtime closure | Nix imports the referenced store objects and reuses already registered objects with matching identities. |
| Host service/API, such as logind on the system D-Bus | Mojt/MPM records the requirement separately and verifies a compatible provider. |
| Integration of a packaged systemd unit or D-Bus policy | Mojt explicitly configures/activates it through a System plan. Merely importing its files does not activate it. |

An installed systemd package, its libraries, systemd as PID 1, and an available
logind service are separate facts. Capability metadata must not infer all of
them from the package's presence. A different backend's similarly named package
must not be registered as if it were an absent exact Nix output.

An unmet host-service requirement must be reported in the Ports plan; meeting
it through System changes requires the explicit cross-area plan defined above.
The capability schema, probes and enforcement are not implemented by the
current adapter, which reports external capabilities as unaudited. Reference
and GC policy must preserve objects needed by any retained System generation,
Ports profile or project reference, including shared objects.

Background: [Nix runtime closures](https://nix.dev/manual/nix/2.35/glossary.html),
[logind's system-bus interface](https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.login1.html),
and [NixOS's separate package/service integration](https://nixos.org/manual/nixos/unstable/).

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
6. Complete production integration of the selected Nix Ports backend and the
   interim Nix System backend; define verified host-service/Base/Kernel
   capabilities and supported direct-Nix/reconciliation behavior.
7. Specify the release/deployment formats and production integration for the
   accepted System-generation and independent Kernel model. The current
   experiment's System labels are not the final public identity format.
8. Specify transactional publication, boot success/fallback behavior and
   state migration warnings. No automatic state rollback is promised.
9. Specify readable transaction history, retention and collection, without
   requiring a user-visible whole-Ports generation after each operation.
   A general Ports transaction-undo command remains optional future design.

## 6. Implementation status

**Implemented today:** host-side whole-image Base packaging and generation
installation/selection, persistent-state preservation, and fresh UEFI images
with explicit Base/System boot pairs. The owner verified full Mojt
A/A → A/B → B/B → A/A boots, authenticated serial login, and controlled
new-image build interruption with no published output and an unchanged
completed VM disk. Both System labels used the same kernel/payload; this is
not evidence of a different-kernel upgrade or an existing-disk updater.

The full System VM uses systemd, NetworkManager/D-Bus, Nix and management
Python. Its earlier VM acceptance also covered networking and binary Ports
imports with parallel Python versions. The current `mpm` CLI accepts only
the `ports` area: `update`, `install`, `activate`, `remove`, `status`, `list`,
`search` and `info`. It supports exact installed artifact selection and
history-based removal fallback; that event ordering is not yet the readable
transaction-history interface specified above. See the
[ordinary Ports guide](mpm-ports.md) for runnable commands and limits.

**Not implemented:** MPM Base/System/Kernel commands, `upgrade` (including
Ports), release-series selectors and their full parser, readable transaction
history, user-facing rollback/undo, production project profiles/locks,
pruning/GC, verified external capabilities, signed catalogs, production
deployment formats, and durable updates to existing boot disks.

These accepted policies guide future implementation; this document is not
a complete command reference. See the [roadmap](roadmap.md) for the next work.
