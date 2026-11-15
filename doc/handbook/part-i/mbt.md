<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# 4. mbt — Mojt build/bootstrap tool

[Handbook](../README.md) · [Previous: MPM](mpm.md) · [Next: Common tasks](../part-ii/README.md)

## 4.1. From inputs to build results

MBT prepares private tool environments, builds a Kernel, packages results and
bootstraps new installation targets. MPM manages the resulting content and
selections on an existing installation. Building or packaging a result leaves
its installation and activation to a separate MPM operation.

The current frontend is experimental and available in builder-enabled Systems.
From a repository checkout, use `python3 tools/mbt`. Its supported operations are:

| Command | Result |
| --- | --- |
| `mbt env` | A private pinned image or Kernel tool environment |
| `mbt build kernel` | A versioned Kernel and matching modules in a workspace |
| `mbt package` | A native archive from prepared inputs, or archive verification |
| `mbt bootstrap` | A fresh image or installation onto explicitly prepared mounted partitions |

This chapter gives a Kernel build journey and a bootstrap preview. It assumes
accepted inputs already exist. The general installation procedure belongs in
the future [installation chapter](installing-mojt.md).

## 4.2. Prepare a private compiler environment

Use a builder-enabled System with its pinned source manifest, working binary
provider and enough disk space. Choose a new environment path whose parent
exists. For example, create a workspace readable by the ordinary build user:

```sh
mkdir -p "$HOME/build" "$HOME/packages"
mbt env --profile kernel \
  --source-manifest /run/mojt-system/ports.toml \
  --output "$HOME/build/kernel-env" --dry-run
```

Review the pin and planned binary tool imports. Then repeat without `--dry-run`
to create the environment. Tool acquisition needs the provider's store permissions.
On the current root-owned single-user Nix store, an administrator must import
the tools into a path readable/traversable by the build user. In that case replace
`$HOME/build/kernel-env` with that explicitly chosen shared path in every step;
running the same command as root with `$HOME` would choose root's home instead.
MBT does not silently change store permissions or start a daemon.

The environment retains compiler, headers, tools and library closure separately
from ordinary Ports defaults. Its `run` launcher also permits manual commands:

```sh
"$HOME/build/kernel-env/run" gcc --version
```

Use the actual environment path if the administrator prepared it elsewhere.
An existing output is refused. Retain incomplete attempts for inspection and use
a new destination when appropriate. A private tool environment pins tools;
it is not a security sandbox.

## 4.3. Build a Kernel as an ordinary user

You need a reviewed build recipe, its frozen starting configuration and the
configuration's SHA256. Builder Systems include the initial example recipe at
`/run/mojt-system/share/mbt/kernel-first-build.json`; it pins a particular source
commit rather than following the latest Kernel. Supply your accepted config
file explicitly. It is not inferred from the running machine.

With the prepared environment available to this user:

```sh
mbt build kernel \
  --plan /run/mojt-system/share/mbt/kernel-first-build.json \
  --config "$HOME/build/kernel.config" --config-sha256 FULL_CONFIG_SHA256 \
  --environment "$HOME/build/kernel-env" \
  --output "$HOME/build/kernel-result" --jobs 2 --dry-run
```

Replace `FULL_CONFIG_SHA256` with the accepted file digest. The preview validates
local prerequisites; it fetches no source and executes no compiler. Repeat the
same command without `--dry-run` to compile as the ordinary build user.
Source, object files and staged output remain in the workspace, rather than
replacing the running Kernel or its `/lib/modules` tree.

A successful result contains a versioned Kernel, matching modules, config diff
and `kernel.json` with build evidence. A failed build retains an incomplete
workspace, rather than advertising a completed result.

If you already have a clean source checkout at the required commit, add
`--source /path/to/clean-linux` to reuse it. For an eligible interrupted build
before module staging, explicit continuation uses the original inputs and output:

```sh
mbt build kernel \
  --plan /run/mojt-system/share/mbt/kernel-first-build.json \
  --config "$HOME/build/kernel.config" --config-sha256 FULL_CONFIG_SHA256 \
  --environment "$HOME/build/kernel-env" \
  --output "$HOME/build/kernel-result" --jobs 2 \
  --source /path/to/clean-linux --resume --dry-run
```

Review the resume preview before repeating without `--dry-run`. Resume is limited
to supported incomplete work; it does not adopt arbitrary or completed output.

## 4.4. Package and verify the result

After a successful build, package it as the build user:

```sh
mbt package kernel --build "$HOME/build/kernel-result" \
  --revision 1 --output "$HOME/packages/kernel"
```

The packager reports the archive path and exact artifact ID. Use those values:

```sh
mbt package verify /path/to/reported-kernel.tar.zst \
  --expected-id sha256:FULL_REPORTED_ARTIFACT_ID
```

Packaging revision describes Mojt packaging and is distinct from the upstream
Kernel version. Package creation has no `--dry-run`; `package verify` checks an
existing archive without installing it.

As administrator, install the resulting package through MPM:

```sh
mpm kernel install --from-file /path/to/reported-kernel.tar.zst \
  --expected-id sha256:FULL_REPORTED_ARTIFACT_ID --dry-run
mpm kernel install --from-file /path/to/reported-kernel.tar.zst \
  --expected-id sha256:FULL_REPORTED_ARTIFACT_ID
```

Continue with [MPM preparation and activation](mpm.md#38-prepare-activate-and-reboot)
to prepare the new boot choice, inspect it, activate it and reboot deliberately.
Retain the previous working Kernel and deployment for a compatible return.

The same packager also accepts an already prepared Base release or System tree.
These commands package existing inputs; they do not compile all their sources:

```sh
mbt package base --help
mbt package system --help
```

## 4.5. Prepare image tools

Image assembly uses a different private environment from Kernel compilation.
Select a new output and preview its required tools:

```sh
mbt env --profile image \
  --source-manifest /run/mojt-system/ports.toml \
  --output "$HOME/build/image-env" --dry-run
```

Repeat without `--dry-run` using the provider's required permissions. The
resulting `run` launcher supplies the pinned image tools when invoking MBT.
Creating this environment changes neither the Kernel environment nor ordinary
Ports command selections.

## 4.6. Preview a fresh bootstrap

Bootstrap consumes exact retained Base and Kernel inputs, an account-enabled
System payload and a reviewed Base context. It uses the same MPM installation
and deployment functions as an existing installation. The following is a
**template with placeholder inputs**, rather than a self-contained installer:

```sh
mbt bootstrap \
  --base-package /inputs/base.tar.zst \
  --base-artifact sha256:FULL_BASE_ID \
  --base-context /inputs/base-context.json \
  --kernel-registry /inputs/kernel-registry \
  --kernel-artifact sha256:FULL_KERNEL_ID \
  --system-payload /inputs/system-payload \
  --system-generation system-builder-A \
  --system-version 0.2 --system-revision 1 \
  --with-build-tools \
  --output /path/to/new-image-directory --dry-run
```

The preview validates inputs and reports prerequisites. Actual image creation
requires root, required image tools and an interactive terminal for the new
machine's password. An ordinary-user preview does not establish that privileged
namespace checks or full construction have passed. Bootstrap does not reboot.

`--output` creates a new regular disk image. The separate `--target-root` mode
requires explicitly identified, empty mounted partitions and does not partition
or format a device. Both are new-target operations. Updating an existing Mojt
installation belongs to MPM.

Bootstrap currently assembles prebuilt inputs; it does not rebuild Base and all
third-party System packages from source. Detailed input preparation, hardware
profile limits and mounted-target requirements remain in the technical guides.

## 4.7. Further reading

See the [MBT manual](../../../man/mbt.1),
[executable interface guide](../../../docs/mbt-minimal.md),
[Kernel build records](../../../docs/kernel-build.md),
[build environments](../../../docs/build-on-mojt.md) and
[mounted-target implementation](../../../docs/mounted-installation.md).

[Previous: MPM](mpm.md) · [Next: Common tasks](../part-ii/README.md)
