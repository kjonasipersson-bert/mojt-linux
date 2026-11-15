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

Boot status distinguishes installed, running and next-boot identities. A prepared
or selected deployment is not evidence that it has booted successfully.
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

## 3.8. Prepare, activate and reboot

For an installed compatible System generation on a native-v2 installation:

```sh
mpm system stage --artifact sha256:FULL_SYSTEM_ID --dry-run
mpm system stage --artifact sha256:FULL_SYSTEM_ID
mpm system status
mpm system activate --artifact sha256:FULL_SYSTEM_ID --dry-run
mpm system activate --artifact sha256:FULL_SYSTEM_ID
mpm system status
```

`stage` checks compatibility and constructs an admitted boot deployment, retaining
Base and Kernel. Preparation can take time. `activate` selects an already
prepared entry for next boot; it does not construct one. A missing prepared
candidate is an error. On installed Systems, `mpm system activate` without an
artifact opens an interactive chooser of prepared choices; `q` cancels it.

After checking next-boot status, reboot deliberately and inspect the result:

```sh
reboot
# After logging in again:
mpm system status
mpm base status
mpm kernel status
```

The exact running identities should now match the intended selected deployment.
Base and Kernel use the same stage/activate shape. Base preparation additionally
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

Use this as an alternative to the separate stage/activate sequence. It works
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

See the [MPM manual](../../../man/mpm.1),
[Ports implementation](../../../docs/ports-cli-integration.md),
[removal/reset semantics](../../../docs/ports-remove-reset.md),
[native System transitions](../../../docs/system-transition.md) and
[activation behavior](../../../docs/activation-performance.md).
The [MPM contract](../../../docs/mpm.md) describes the wider design and marks
remaining implementation gaps.

[Previous: Installing Mojt](installing-mojt.md) · [Next: MBT](mbt.md)
