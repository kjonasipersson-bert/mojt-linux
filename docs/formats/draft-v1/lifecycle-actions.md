<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Lifecycle action sets v1

Review draft. [Schema](lifecycle-set.schema.json),
[example](examples/lifecycle-set.json), [encoding](README.md).

An action set contains `platform` and ordered `actions`. Each action has exactly
`key`, `type`, `version`, `phase`, `required`, `after`, `parameters`. Keys are
unique local identifiers sorted by key. `after` contains sorted unique keys in
this set, not host service names or commands. Reject missing/self dependencies,
cycles and a stage action depending on initialization. Initialization may depend
on staging only through verified retained staging results for matching inputs.
Every v1 action is required; optional/ignored unknown actions are not introduced.
An empty set means no declared action, not proof of global compatibility.

## Closed initial handler vocabulary

| Type, version | Fixed phase | Parameters / semantics |
| --- | --- | --- |
| `kernel-derived`, 1 | `stage` | Boolean `module_index` and `initramfs`, at least one true; engine supplies exact Kernel/modules, Base/System and construction inputs; private generation-owned output only |
| `manual-index`, 1 | `stage` | Unique sorted profile-relative `profile_paths`; aggregate only those verified profile inputs into private generation-owned manual index |
| `ensure-account`, 1 | `initialize` | `name`, `group`, `allocation: system`, canonical absolute `home` and `shell`; preserve/create stable named UID/GID under approved local system-account range policy; no login/password reset or implicit home creation |
| `ensure-directory`, 1 | `initialize` | `namespace` is `etc` or `var`, relative `path`, `owner`, `group`, permission `mode` 0..511; ensure only that directory, without following unsafe links or recursive repair |
| `missing-default`, 1 | `initialize` | `namespace: etc`, relative `path`, exact `source` reference/path/SHA256, root owner/group and mode; exclusive create if missing, preserve existing entries, report unresolved required configuration separately |

An actor is `root` or `account:NAME`. Account references must bind stable existing
accounts or an explicit prerequisite account action, with the resolved numeric
binding recorded in results. Preserve collisions and fail; never renumber users.
Account home/shell must be target-appropriate permitted paths; the shell must
exist in the target and cannot refer to a mutable Ports choice. No arbitrary
execution from account fields. Protected account files are not action logs.

Namespaces map to the target's persistent etc/var trees. A path alone is not
permission: the owning state declaration and approved plan must authorize it.
Reject duplicate/conflicting path/account owners; do not implicitly create
parents with guessed permissions. Parents must already exist or have explicit
initialization declarations/prerequisites. A default source must be an exact
listed dependency, safe regular file, with matching bytes. `manual-index`
validates all contributors and has a fixed handler-supplied tool, not an
arbitrary command template. Unsupported handler or prerequisite blocks planning.

`kernel-derived` writes only its private boot slot's module index and initramfs;
it never edits the retained module tree. `manual-index` writes only the new
profile's reserved `generated/manual-index/` subtree; mappings into that subtree
are rejected. It must not write through source links into provider/native trees.
Its `input_profile` evidence hashes the frozen input inventory excluding derived
outputs, not the final manifest that will itself inventory the cache. Derived
output location and tool/format are fixed by the versioned handler, not supplied
as an arbitrary destination/command by a package.

Handlers are versioned trusted code in the executing System, advertising exact
type/version/phase and implementation identity. Declaring these names does not
implement them. Import, descriptor verification and plan display never execute
them. M1 may support a smaller advertised set; a package needing an absent one
is refused. No handler accepts shell text, executable/interpreter paths, network
callbacks, arbitrary delete/reset, service start/stop or database migration.

## Ownership, identity and execution

Definitions contain no owning artifact ID, target machine, timestamps or mutable
state. A composition/package inventories and references the action set. For
older Kernel packages, a trusted planner may generate a set from the exact
approved Kernel/deployment preparation inputs; it does not execute package code
or edit the retained descriptor. Such generated sets are retained by full ID.

Execution binds definition to explicit target/context and trusted handler.
Stage context uses a preparation-input identity, NOT the future deployment ID:
the deployment depends on generated initramfs bytes, so the reverse binding
would make a hash cycle. Initialization uses an already complete selected
deployment/profile ID. Results remain external to the content they describe.
The [result format](lifecycle-results.md) specifies invocation identity.

Preparation performs all possible read-only ownership/schema/handler checks.
For next-boot state initialization, recheck relevant prerequisites before
mutation. Normal data record changes under a compatible schema do not alone
invalidate approval. Target initialization is explicit; preparing an offline
image cannot invoke the build host's accounts/services. Boot initialization
runs after persistent mounts/identity and before dependent services; failure
leaves dependents stopped, preserves independent diagnostics and reports degraded
readiness. First-version declarations cannot authorize a destructive migration.

State support records declare schema family/read/write versions for named owned
paths. Their family-specific reader validates actual metadata; declaration is
not observation. Unknown required state or old manager support blocks selection.
Unmanaged user/application data is not a new implicit schema requirement.

Future migration/optional action types require reviewed format/capability
extensions and explicit runtime support. An unrecognized action must never be
interpreted as a shell command, ignored because content verified, or run by an
older manager. See the broader [lifecycle policy](../../mpm-lifecycle.md).

