<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# 3. mpm — Mojt package manager

[Handbook](../README.md) · [Previous: Installing Mojt](installing-mojt.md) · [Next: MBT](mbt.md)

## 3.1. What MPM manages

MPM manages content and selections on an existing installation:

```text
mpm <area> <action> [arguments]
```

| Area | Content | Selection |
| --- | --- | --- |
| `base` | Whole Base releases | Base in a complete next-boot deployment |
| `system` | Coherent System userspace generations | System in a complete next-boot deployment |
| `kernel` | Exact Kernel builds and matching modules | Kernel in a complete next-boot deployment |
| `ports` | Applications and toolchains | Active command profile |

The examples below use an installed Mojt System and its default target. Run
shared mutations as an administrator. Read-only inspection is available to
ordinary users. The current frontend supports a bounded experimental subset:
native boot examples require an existing managed native-v2 installation.

MPM delegates binary acquisition to providers where needed. It does not compile
missing packages as a hidden fallback. [MBT](mbt.md) handles explicit builds.

## 3.2. Inspect before changing anything

```sh
mpm base status
mpm system status
mpm kernel status
mpm ports list
mpm ports history
```

Boot status shows **Running**, **Next boot** and **Prepared boot entries** with
readable generation/release names and short identities. Installed content without
a boot entry is marked **not prepared**. Prepared entries include their Base and
Kernel, and tags show which entry is running or selected. **Reboot: pending**
means next boot differs from running. Offline inspection reports the running
identity as unknown. A prepared or selected deployment is not evidence that it
has booted successfully; names alone do not distinguish different builds.
Use machine-readable output when you need complete records:

```sh
mpm system status --json
mpm ports list --exact
mpm ports status
```

`list --exact` includes complete installed reference IDs. Ports status returns
profile, wishes and selection information as JSON. Full content audits are
explicit operations and can take time:

```sh
mpm base status --verify
mpm system status --verify
```

When using a repository checkout, invoke `python3 tools/mpm` from its root.
Base/System and boot operations then need an explicit `--disk-root` pointing to
the managed installation. An explicit target is offline inspection and does not
inherit the host's running identity. Global `--root` names a Ports registry,
rather than a disk installation; do not use it as a substitute for `--disk-root`.

## 3.3. Install and use a Port

On a configured installed System, MPM uses the System's pinned provider source.
A basic application workflow is:

```sh
mpm ports install hello --dry-run
mpm ports install hello
mpm ports list
hello
```

Review the requested imports and selection effects at the prompts. First
unambiguous installation normally establishes the default command; subsequent
versions preserve an existing default. Use `--no-activate` when adding content
without establishing that initial default.

A preview for a newly discovered package can be an acquisition preview: exact
command exports are learned by inspecting the binary. It performs no payload
import and is not proof of a completed installation.

Search and inspection use accepted local metadata:

```sh
mpm ports search hello
mpm ports info hello
```

Search does not query the entire remote Nixpkgs collection. A name absent from
this local view may still be discoverable by an explicit install against the
pinned provider. The frontend imports available binary substitutes only;
unavailable binaries fail without starting a source build.

### Read a Port's manual

```sh
man git
man nvim
man neovim
man ncdu
manpath
```

The System's `man` and `manpath` wrappers add manuals for the active Ports
versions at invocation, so an existing shell needs no new login. MPM imports
separate provider manual outputs along with binaries when available. The
upstream page can have a different name: Neovim provides `nvim(1)`; `man neovim`
also works when its pinned package metadata declares that main program. MPM
does not invent manuals for packages without one; use their `--help` or upstream
documentation. An explicit `man -M DIRECTORY` still overrides the search path.

After updating from an older System, repeat the existing install wishes to
complete their manual dependencies, for example:

```sh
mpm ports install neovim git ncdu mdbook
```

This repair uses the same pinned source and keeps accepted exact binaries,
active choices and version policies. It refuses a changed binary rather than
silently upgrading. An unavailable manual substitute fails before changing the
active profile. Previously accepted explicit catalog bundles are not silently
supplemented; their producer must include the manual dependencies.

## 3.4. Choose a version policy

| Selector | Meaning |
| --- | --- |
| `hello` | Latest eligible stable release in the accepted view |
| `hello@2.12` | Latest eligible stable release in the numeric 2.12 series |
| `hello@=2.12.3` | Exactly the declared release `2.12.3` |

A release can have several builds. A version label alone may therefore be
ambiguous; use a full installed reference from `list --exact` when needed.
Other version schemes may support exact matching only.

For example, **if both releases are offered by your accepted sources**, you can
retain two versions and select between them:

```sh
mpm ports install hello@=2.12.1
mpm ports install hello@=2.12.3
mpm ports list --exact
mpm ports activate hello@=2.12.1
hello --version
mpm ports activate hello@=2.12.3
hello --version
```

These release numbers illustrate the model, rather than promising availability
in every source pin. An exact selector does not search repository history or
make an old package appear in the current catalog.

Exact activation pins the active default. To let an already accepted latest
wish control that default, install the wish and activate it as a following choice:

```sh
mpm ports install hello
mpm ports activate hello
```

A following default can advance with its wish during upgrade. An exact active
override stays fixed even if another following installation wish advances.

## 3.5. Metadata update and package upgrade

Metadata describes what is offered. Upgrade changes accepted targets of saved
wishes. These are separate operations:

```sh
mpm ports update
mpm ports upgrade hello --dry-run
mpm ports upgrade hello
```

In the current installed-provider path, plain `update` checks or accepts the
System's pinned view; it does **not** fetch a newer Nixpkgs revision. An existing
view keeps its pin. To accept another explicitly prepared finite source bundle:

```sh
mpm ports update --sources /packages/ports-sources.json --dry-run
mpm ports update --sources /packages/ports-sources.json
mpm ports upgrade --dry-run
mpm ports upgrade
```

The file must be a valid `mojt-ports-sources-v1` bundle, not an arbitrary provider
manifest. Updating metadata leaves installed and active choices alone. Upgrade
without names considers all saved wishes; it does not upgrade every retained
old artifact. Exact wishes and exact active pins retain their separate meanings.
Old content and previous profiles remain retained.

## 3.6. Remove a wish or reset a default

```sh
mpm ports remove hello --dry-run
mpm ports remove hello
mpm ports reset hello --dry-run
mpm ports reset hello
```

These are independent operations: use `remove` to release interactive installation
wishes and overrides for a role. Use `reset` to release only its interactive
active override, preserving installation wishes and restoring an adopted
configuration default where present. Running reset after removal is usually
unnecessary; the examples show each command's spelling.

Configuration-owned wishes survive interactive removal. Edit and apply their
own configuration to release those claims. Selector-qualified removal has a
narrower scope, for example `mpm ports remove hello@2.12` releases that interactive
series wish while preserving an independent exact active pin.

Removal is logical: old profiles, provider objects, retention roots and user
data remain. It does not reclaim disk space. History records committed changes;
it is not a general undo command. Physical collection and a user-facing Ports
transaction rollback remain future work.

## 3.7. Install exact boot content

The following examples require trusted native packages, complete artifact IDs
and an existing managed target. Run them as an administrator. A native Base
package wraps the release; raw `rootfs.tar.zst` alone is not this input format.

```sh
mpm base install --from-file /packages/base.tar.zst \
  --expected-id sha256:FULL_BASE_ID --dry-run
mpm base install --from-file /packages/base.tar.zst \
  --expected-id sha256:FULL_BASE_ID

mpm system install --from-file /packages/system.tar.zst \
  --expected-id sha256:FULL_SYSTEM_ID \
  --dependency-file /packages/system-component.tar.zst --dry-run
mpm system install --from-file /packages/system.tar.zst \
  --expected-id sha256:FULL_SYSTEM_ID \
  --dependency-file /packages/system-component.tar.zst

mpm kernel install --from-file /packages/kernel.tar.zst \
  --expected-id sha256:FULL_KERNEL_ID --dry-run
mpm kernel install --from-file /packages/kernel.tar.zst \
  --expected-id sha256:FULL_KERNEL_ID
```

Repeat `--dependency-file` for each missing native System component. Already
installed exact components can be reused. Installation retains the content;
it leaves next boot and the running system unchanged. Exact imports do not
create moving upgrade wishes.

On the running native-v2 installation, normal **System** installation also
checks compatibility and prepares its boot entry using the current Base and
Kernel. Long work prints phase starts and completion times on stderr, without
estimated percentages. Next boot stays unchanged. If preparation fails, the
command fails, reports that content is retained, and leaves the selection alone;
fix the reported problem and repeat installation to retry preparation. `--verify`
adds full content audits; it is not required for ordinary installation.

Use `mpm system install ... --content-only` to import without preparation.
Explicit `--disk-root` targets are offline and also remain content-only. Base and
Kernel installation still require separate preparation in this implementation.
A dry-run does not install, construct or promise a boot-ready entry.

## 3.8. Activate and reboot

For an installed compatible System generation on a native-v2 installation:

```sh
mpm system status
mpm system activate --artifact sha256:FULL_SYSTEM_ID --dry-run
mpm system activate --artifact sha256:FULL_SYSTEM_ID
mpm system status
```

The ordinary flow is **install → activate → deliberate reboot**. `activate`
selects an already prepared entry for next boot; it does not construct one.
Before approval it shows the old and new Base, System and Kernel, explicitly
marks unchanged parts, and explains whether a reboot is needed. A short artifact
ID distinguishes different builds with the same readable name. A missing prepared
candidate is an error. On installed Systems, `mpm system activate` without an
artifact opens an interactive chooser of prepared choices compatible with the
other currently selected areas; `q` cancels it. A standalone `stage --artifact ID`
remains an advanced preparation/retry command for content-only imports,
alternatives, bootstrap and build tools. It is not a mandatory extra step after
normal live System installation.

After checking next-boot status, reboot deliberately and inspect the result:

```sh
reboot
# After logging in again:
mpm system status
mpm base status
mpm kernel status
```

The exact running identities should now match the intended selected deployment.
Base and Kernel currently use the explicit stage/activate shape. Base preparation additionally
requires an accepted context file declaring exact Kernel bounds:

```sh
mpm base stage --artifact sha256:FULL_BASE_ID \
  --base-context /packages/base-context.json --dry-run
mpm kernel stage --artifact sha256:FULL_KERNEL_ID --dry-run
```

These two commands are previews only. After successful real staging, the
corresponding `mpm base activate` or `mpm kernel activate` selects that prepared
choice. Compatibility checks can refuse unsupported transitions, missing
configuration or required service/data changes.

The exact upgrade convenience joins preparation and selection:

```sh
mpm system upgrade --artifact sha256:FULL_SYSTEM_ID --dry-run
mpm system upgrade --artifact sha256:FULL_SYSTEM_ID
```

Use this when explicitly joining preparation and the next-boot choice. It works
with an explicit installed artifact. General moving-policy Base/System/Kernel
resolution and automatic migrations are not implemented.

## 3.9. Return to a retained deployment

Read the current deployment identity from status/selection records and substitute
its complete ID below. The expected-selected guard refuses a stale choice:

```sh
mpm system rollback --expected-selected sha256:CURRENT_DEPLOYMENT_ID --dry-run
mpm system rollback --expected-selected sha256:CURRENT_DEPLOYMENT_ID
mpm system status
```

Rollback selects the previous compatible deployment within the requested area.
It can refuse a change that would also replace another area's component.
Inspect next boot before rebooting. Persistent configuration, databases and user
files retain their current contents when older code boots.

## 3.10. Further reading

See the [MPM manual](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/man/mpm.1),
[Ports implementation](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/ports-cli-integration.md),
[removal/reset semantics](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/ports-remove-reset.md),
[native System transitions](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/system-transition.md) and
[activation behavior](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/activation-performance.md).
The [MPM contract](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/mpm.md) describes the wider design and marks
remaining implementation gaps.

[Previous: Installing Mojt](installing-mojt.md) · [Next: MBT](mbt.md)
