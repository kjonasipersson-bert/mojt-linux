<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MPM delivered by System

New step-3+ System assemblies deliver the common MPM frontend, native/catalog
modules and optional Nix adapter as one explicit management file set. The
installed `bin/mpm` starts the selected System's pinned Python with `-I -B` and
the System launcher. It does not start the Nix prototype unconditionally.
The same `mpm_cli.py` dispatches the source checkout and installed commands.

`mojt_system.MPM_FILES` is the closed source-file inventory. The generated System
manifest binds the installed bytes, modes, Python reference and provider closure.
`mpm-runtime.json` records the file set, interpreter, fixed targets and retained
helper identity. It is descriptive build evidence, not an administrator-editable
startup configuration or a second authoritative selection database.

## Defaults and explicit targets

| Operation | Installed default | Explicit target behavior |
| --- | --- | --- |
| Ports | `/var/lib/mojt/ports`, selected System's `ports.toml` source pin | Existing global overrides remain explicit |
| Kernel install/registry inspection/plan | `/run/mojt-disk/kernel` | `--root` retains standalone registry semantics |
| Kernel stage/select/rollback | `/run/mojt-disk` | `--disk-root` retains its explicit target |
| Kernel status with native binding | Disk selection plus `/run/mojt/deployment.json` | Another explicit disk is never labelled with this machine's runtime record |
| Catalog discovery | Explicit local `--catalog` snapshot | No implicit metadata adoption, refresh or provider fallback |

For a fresh native single-pair image, the installed frontend can supply the
initial baseline from the explicit runtime deployment record. The retained
baseline descriptor must match that record, and the existing boot engine still
checks the entire generated menu and its exact bytes/content. This is not
adoption from `uname`, `current` links or a guessed installed version. Once a
managed boot menu exists, its selected identity is authoritative even while an
older deployment is still running. Existing source-checkout commands retain
their explicit target/baseline contract.

On older non-native System images without a runtime deployment binding, Kernel
status reports standalone installed content and unknown selected/running build
identity. It does not invent a native deployment. The frontend never creates a
missing running disk mount merely to satisfy a default path.

## Runtime dependencies and isolation

The installed launcher ignores user Python search paths and replaces PATH with
the private MPM helpers, selected System commands and Base tools. Ports programs
cannot replace the interpreter, codec or module helper through their active
profile. This is environment isolation, not a security sandbox.

Native archive verification requires `zstd`. At assembly, select it only from
the existing verified System object closure, allowing a command already present
as a transitive dependency. Resolve guest symlinks inside that payload, require
the resulting executable to remain in the declared closure, deduplicate aliases
and reject distinct ambiguous candidates. Expose it only through
`libexec/mpm/bin/zstd`; no host-PATH or Ports lookup, new import or global command
activation occurs. Missing codec evidence is recorded as null and native
verification fails with a prerequisite message before installation writes.
Thus earlier payload formats and package-role sets remain usable; the current
step-10 payload's retained zstd binary can be reused without another export.

Actual Kernel staging also requires the System `modprobe` command (step 6+).
Earlier Systems may inspect catalogs/metadata but do not claim complete Kernel
staging capability. Native/catalog paths and explicit finite-catalog Ports
resolution never load the optional Nix adapter.
The current System still retains its Nix-backed runtime objects; this increment
does not relocate them, replace Base libc or compile MPM into a binary.

## Permissions and unchanged semantics

The common installed frontend permits ordinary users to read catalogs, Ports
status/history/search and native Kernel status/plans. Shared mutation requests
require an administrator before provider loading or target modification.
The old account-enabled wrapper's Ports-only whitelist is removed; its umask
policy remains. Area installers retain their filesystem/ownership checks.
Direct root edits or invoking internal backend files is not a supported MPM
transaction, just as before; this is not a new privilege broker.

Installation still retains content without selecting a Kernel. Stage prepares
a slot, select changes next boot, and status distinguishes that choice from the
explicit running record. Existing Ports requests, first-install behavior,
selection policies, metadata versions and history are unchanged. The shared
[transaction rules](mpm-transactions.md) and final integrity gates remain in use.
Retained System generations are not edited in place: a new assembly carries the
new frontend, and booting an older generation uses its retained frontend.

## Validation and next scope

Tests execute the delivered module set from another directory with isolated
Python and an empty initial PATH, without source-checkout imports. Native tests
remove provider files and exercise real package verification/import, read-only
status/stage preview, initramfs staging/no-op, selection and distinct
selected/running identities on a synthetic disk fixture. Staging uses the same
synthetic executable/module substitutions as the existing boot tests; the
complete imported builder library set comes from the delivered copy.
Separate tests use the real adapter for read-only Ports
status, and inspect actual System runtime delivery and helper selection/refusal.
The fixture's running release is simulated; these are integration tests, not a
new physical Kernel boot or a libc compatibility proof.

No repeated owner VM/account loop is required before this integration. A future
single complete bootstrap/build/install/boot acceptance tests the installed
commands on the real Mojt runtime. Base/System mutation commands, trusted native
repository acquisition and the unified build/bootstrap interface remain separate
work. Existing MPM syntax is retained. The separate new-tool interface discussion
concerns [MBT](mbt-cli-discussion.md). The [gap matrix](mpm-gap-matrix.md) records
the remaining joins to the complete installed-machine workflow.
