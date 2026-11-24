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
| `mbt build base` | A source-built Base release and native MPM package, with size measurements |
| `mbt repo prepare` | A signed Base catalog and publication receipt, without uploading |
| `mbt package` | A native archive from prepared inputs, or archive verification |
| `mbt bootstrap` | A fresh image or installation onto explicitly prepared mounted partitions |

`mbt build base --output base-result --jobs 2` builds the pinned Base 0.2.1
release and a native archive under `base-result/package`. It reports compressed
and regular-file payload sizes. It requires a plain host GCC and native build
utilities; the current bootstrap rejects Nix compiler wrappers. Availability in
MBT does not supply those tools or create a self-hosting toolchain. See the
[Base build reference](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/base-source-build.md).

`mbt repo prepare --config repository.toml --output new-publication` signs a
finite Base catalog using the publishing host's Ed25519 key and OpenSSL 3+.
Archives can then be uploaded as GitHub Release assets with standard tools.
The private key stays outside packages and the source checkout. See
[repository publication](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/native-repository.md).

For a complete installed-system journey, including background compilation over
SSH, installation, next-boot selection and return, see
[Building and installing a Kernel](../part-iii/kernel.md). This chapter gives
the build interfaces and a bootstrap preview. It assumes accepted inputs already
exist. The general installation procedure belongs in
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

The default starting configuration is the bundled `manifests/mojt.config`.
A reviewed `mojt.config` in your workspace overrides it.
Its digest is measured and frozen automatically; an explicit `--config-sha256`
can require a previously reviewed value. With no track/plan option, the pinned
LTS recipe is selected. Builder-enabled Systems include two track recipes:

| `--track` | Pinned upstream version | Kernel/module release |
| --- | --- | --- |
| `linux-kernel-lts` | 6.18.63 | `6.18.63-mojt-lts1` |
| `linux-kernel` | 7.3.4 | `7.3.4-mojt1` |

The names select bundled exact commits, not a live "latest" lookup. Updating a
recipe is explicit. The tracks use separate output directories and module trees;
building either leaves the running Kernel unchanged. `--plan FILE` instead
selects an explicit recipe, including the retained initial 6.12 example. It is
mutually exclusive with `--track`.

An explicit `--config FILE` overrides both the local and bundled configuration.
The builder checks and records its digest,
applies the recipe policy, runs `olddefconfig` and retains the complete config
diff. It does not silently choose `/proc/config.gz` or a host config.

With the prepared environment available to this user:

```sh
mbt build kernel \
  --track linux-kernel-lts \
  --config "$HOME/build/kernel.config" --config-sha256 FULL_CONFIG_SHA256 \
  --environment "$HOME/build/kernel-env" \
  --output "$HOME/build/kernel-result" --jobs 2 --dry-run
```

Replace `FULL_CONFIG_SHA256` with the accepted file digest. The preview validates
local prerequisites; it fetches no source and executes no compiler. Repeat the
same command without `--dry-run` to compile as your current user. A dedicated
build account is not required; root builds are also permitted.
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
  --track linux-kernel-lts \
  --config "$HOME/build/kernel.config" --config-sha256 FULL_CONFIG_SHA256 \
  --environment "$HOME/build/kernel-env" \
  --output "$HOME/build/kernel-result" --jobs 2 \
  --source /path/to/clean-linux --resume --dry-run
```

Review the resume preview before repeating without `--dry-run`. Resume is limited
to supported incomplete work; it does not adopt arbitrary or completed output. If the original build fetched
its own source, `--source "$HOME/build/kernel-result/source"` can reuse that
checked checkout during resume.

## 4.4. Package and verify the result

After a successful build, package it as your current user. With default paths,
`mbt package kernel` reads `kernel-result`, uses revision 1 and creates
`kernel-package`. An explicit invocation is:

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

Continue with [Kernel preparation and selection](../part-iii/kernel.md#75-prepare-and-select-next-boot)
to prepare/select the new boot choice, inspect it and reboot deliberately.
Retain the previous working Kernel and deployment for a compatible return.

The same packager also accepts an already prepared Base release or System tree.
These commands package existing inputs; they do not compile all their sources:

```sh
mbt package base --help
mbt package system --help
```

### Package a System successor

On installed Mojt, run as administrator:

```sh
mbt package system --running --output ./system-package
```

The builder packages its bundled Runtime resources with the running System's
startup content and exact provider references. The new generation references
retained components; its profile contains links and small management records.
It does not copy a complete System profile. Firmware is omitted by default.
Use `--firmware keep` to retain the current firmware selection without copying
or repackaging its data. Devices requiring firmware need an appropriate selection.

The JSON result reports the generation archive, full artifact ID and new Runtime
dependency archives. Pass these to `mpm system install --from-file ...
--expected-id ... --dependency-file ...`; retained firmware needs no new archive.
Installation prepares the boot entry on the running native-v2 installation,
leaving selection and reboot explicit. Packaging itself changes neither.
See [component generations](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/system-components.md) for storage,
validation and compatibility limits.

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

For a serial UEFI VM with a Btrfs root, add `--root-fs btrfs` and launch
the finished VM with the generated `run-qemu.sh`. The image requires
`mkfs.btrfs` and a Btrfs-capable input Kernel. Ext4 is the default.
[Image and boot requirements](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/mbt-minimal.md#fresh-native-v2-bootstrap)

`--output` creates a new regular disk image. The separate `--target-root` mode
requires explicitly identified, empty mounted partitions and does not partition
or format a device. Both are new-target operations. Updating an existing Mojt
installation belongs to MPM.

Bootstrap currently assembles prebuilt inputs; it does not rebuild Base and all
third-party System packages from source. See the [hardware chapter](../part-iii/hardware.md)
for the PC and retained ThinkPad profiles and firmware inputs. Detailed input
preparation and mounted-target requirements remain in the technical guides.

## 4.7. Further reading

See the [MBT manual](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/man/mbt.1),
[executable interface guide](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/mbt-minimal.md),
[Kernel build records](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/kernel-build.md),
[build environments](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/build-on-mojt.md) and
[mounted-target implementation](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/mounted-installation.md).

[Previous: MPM](mpm.md) · [Next: Common tasks](../part-ii/README.md)
