<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Build and update a local Base

Base is one complete versioned Unix userspace release. MBT builds/packages it;
MPM installs it and manages boot choices. Use a System carrying the current
manager to use these commands; updating a source checkout does not replace the
manager in a running System.

## Build and package

On an x86-64 Linux build host with the [documented native tools](base-source-build.md):

```sh
mbt build base --output base-result --jobs 2 --dry-run
mbt build base --output base-result --jobs 2
```

The bootstrap currently requires plain host GCC and rejects Nix compiler wrappers.
It neither installs build tools nor supplies a self-hosting compiler environment.
The output must be new. `releases/` contains the complete Base release; `package/`
contains the native MPM archive. `result.json` records the exact package path/ID,
source provenance, and compressed/regular-file payload sizes. The console prints
the package path too. Sources, build objects, tools and logs are outside Base.

`mbt package base --release DIRECTORY --revision 1 --output DIRECTORY` can also
package an existing complete release without compilation or rewriting it.

## Install and choose

Use a trusted native Base archive, not the inner `rootfs.tar.zst` alone. As root
on the running native-v2 installation:

```sh
mpm base install --from-file /packages/base.tar.zst
mpm base status
mpm base activate
```

`install` verifies/retains the archive and rootfs, adds missing regular machine
configuration defaults after approval, and prepares a boot entry. Existing
`/etc` files, including locally edited service/protocol tables, remain unchanged.
Preparation never changes next boot. `activate` offers prepared choices and
shows what will change before selection. Reboot deliberately when ready.

Alternatively, one local command includes installation, preparation and approval
of next boot:

```sh
mpm base upgrade --from-file /packages/base.tar.zst
```

Both paths preserve the selected System, Kernel, machine boot policy and user
state. They neither fetch a newer release nor rebuild anything. `--expected-id`
can require a known artifact ID; when omitted for a local file, the same archive
verification derives it. This is integrity checking, not publisher authentication.
Source acquisition still requires the explicit artifact and archive identities.

Without `--base-context FILE`, a new Base preparation is constrained to the exact
already selected Kernel upstream version. This is a local update target, not
inherited bounds or a producer claim of support for an entire Kernel series.
System/Base ABI, state, accounts and boot-construction checks remain in force.
An explicit context can declare a different supported range. Preparing a later
Kernel outside the exact constraint needs an explicit compatible Base context.

`--dry-run` accepts/verifies the content without installing it, adding defaults,
constructing boot files or selecting next boot. It does not claim deployment
compatibility before the content is installed. `-y` approves the command's
advertised effects; `--verify` requests full retained-content audits during
preparation. Normal archive acceptance still validates incoming content.

## Partial completion and advanced operations

If preparation fails, installed content and any successfully added defaults remain;
next boot is not selected by preparation. Retry the same command after a
construction failure. An interrupted missing-default lifecycle action retains
evidence and requires explicit reconciliation through the existing defaults
protocol; it is not silently adopted or automatically repaired.
If selection is declined or stale, an already prepared entry remains available.
A publication uncertainty must be inspected using status before another choice;
do not assume that a reported final flush failure means publication did not occur.

`install --content-only` and explicit `--disk-root` offline targets retain content
without adding defaults or preparing boot. Local file `upgrade` requires the
running native-v2 installation. The lower-level import API remains content-only;
explicit `stage`, `select` and `rollback` remain available.

Automatic default preparation supports regular files in existing protected
configuration directories. It does not replace local files/symlinks, create
missing directory trees, initialize account databases, merge defaults, or migrate
schemas. Unsupported preparation stops with an error. Rollback does not remove
previously added `/etc` files or undo persistent data changes.
