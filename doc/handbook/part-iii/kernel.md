<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# 7. Building and installing a Kernel

MBT builds and packages a Kernel; MPM installs it and chooses next boot. Use your
existing account and a separate working directory. A dedicated build account is
not required. Ordinary-user builds are recommended; root can also build, for
example on an experimental machine. MBT neither changes users nor elevates
privileges automatically. Shared installation and boot selection require root.

This procedure assumes a builder-enabled System and an existing native-v2
installation. Retain the previous working Kernel and complete boot entry.

## 7.1. Choose a recipe and starting configuration

The bundled recipes pin exact upstream commits:

| Track | Upstream version | Kernel/module release |
| --- | --- | --- |
| `linux-kernel-lts` (default) | 6.18.63 | `6.18.63-mojt-lts1` |
| `linux-kernel` | 7.3.4 | `7.3.4-mojt1` |

These versions are explicit recipes, not automatic "latest" lookups. Use a
separate working directory for each build. MBT supplies the versioned x86-64
**`manifests/mojt.config`** baseline. It is a broad starting configuration derived
from a Debian seed with Mojt policy applied. Firmware remains part of System;
this baseline does not establish support for every machine.

To customize a build, place a reviewed `mojt.config` in its working directory,
or select another file with `--config FILE`. An explicit file takes precedence
over the local file, which takes precedence over the bundled baseline. A broken
local file is an error, rather than a reason to fall back silently.

On an installed builder, start a local customization with:

```sh
cp /run/mojt-system/manifests/mojt.config ./mojt.config
```

MBT freezes the selected file, records its digest, applies the recipe policy,
runs `olddefconfig` and retains the configuration diff. You can supply a different
file with `--config FILE`, or require a previously reviewed digest with
`--config-sha256 SHA256`. The normal flow does not require typing the hash.

## 7.2. Prepare tools once

Check that the tools are available:

```sh
mbt build kernel --help
mpm kernel status
```

The default compiler environment is
`/var/lib/mojt/kernel-build/environment`. Reuse it if already prepared. To create
it on the current root-owned single-user Nix store, run as root:

```sh
install -d -m 0755 /var/lib/mojt/kernel-build
(
    umask 022
    mbt env --profile kernel \
      --source-manifest /run/mojt-system/ports.toml \
      --output /var/lib/mojt/kernel-build/environment
)
```

Review the pinned tool imports at the prompt. `umask 022` makes the root-owned
files readable by your ordinary account. This preparation is separate from
Ports defaults and need not be repeated for every Kernel build. An existing
output is refused. Use `--environment DIRECTORY` if tools are prepared elsewhere.

## 7.3. Build

In a new working directory, with the compiler environment prepared:

```sh
mbt build kernel --dry-run
mbt build kernel
```

The default is the pinned LTS recipe, two parallel jobs and a new `kernel-result`
directory. MBT shows the inputs and asks before the real build. A preview does
not fetch sources, run a compiler or create the result. To build the other track
instead, in a separate workspace:

```sh
mbt build kernel --track linux-kernel
```

Source, objects and matching modules stay in the result directory. The running
Kernel is unchanged. A broad configuration can take hours to compile. Real phase
starts/completions and compiler output are shown, without estimated percentages.
The final `READY` message names `kernel-result/kernel.json`.

### Keep a root SSH build running after disconnection

After reviewing the preview, a root SSH session can use an ordinary transient
systemd service instead of the foreground command:

```sh
systemd-run --unit=kernel-build --working-directory="$PWD" \
  /run/mojt-system/bin/mbt build kernel -y
journalctl -fu kernel-build
```

The same configuration precedence applies to the background build. Ctrl-C leaves the journal
viewer; SSH disconnection does not cancel the service. `-y` accepts the build
already reviewed in the preview. For an ordinary account, use your existing
persistent terminal session, or a user service when a user manager is available.
No separate account needs to be created.

Use new result paths for new builds; completed output is not overwritten.
Advanced source reuse, jobs and eligible interrupted-build continuation are
covered in the [MBT chapter](../part-i/mbt.md#43-build-a-kernel-as-an-ordinary-user).

## 7.4. Package and install

After a successful build, in the same directory:

```sh
mbt package kernel
```

This checks the completed result and creates `kernel-package` with packaging
revision 1. It reports the archive filename and full artifact ID. An incomplete
build is refused. Explicit `--build`, `--output` and `--revision` override those
defaults when needed. Packaging neither installs nor selects the Kernel.

As root, substitute the reported archive path and artifact ID:

```sh
mpm kernel install --from-file ARCHIVE --expected-id sha256:FULL_KERNEL_ID
mpm kernel status
```

Installation retains the exact Kernel/module tree and leaves both the running
Kernel and next boot unchanged. The explicit artifact ID binds this import to
the package you reviewed; SHA256 is integrity/identity evidence, not publisher
authentication. Keep the previous Kernel installed.

## 7.5. Prepare and select next boot

As root, choose the installed candidate interactively:

```sh
mpm kernel upgrade
mpm kernel status
```

The chooser shows readable installed candidates. Review the proposed Base,
System and Kernel before accepting. `upgrade` prepares the matching initramfs
and boot entry, then selects next boot. A separate `stage` command is not needed.
Construction can take time; the current Kernel keeps running.

For an exact noninteractive target or a preview, use
`--artifact sha256:FULL_KERNEL_ID`; add `--dry-run` for inspection only. Exact
Kernel upgrades do not fetch a newer release or create a moving upgrade wish.

If the retained Base declares an older Kernel range, MPM refuses the transition.
Review its compatibility context rather than changing bounds automatically.
An explicit updated context must bind the same Base artifact/release/platform,
preserve the accepted minimum and declare the reviewed maximum. The public
`mpm base upgrade --artifact ID --base-context FILE` operation can prepare/select
that context for the same Base, followed by the Kernel upgrade without a separate
context-only reboot. Base content remains unchanged. See
[MPM](../part-i/mpm.md#38-activate-and-reboot) and the
[Base/Kernel context reference](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/kernel-deployment-plan.md)
for explicit advanced inputs. A declared range is not runtime compatibility proof.

## 7.6. Reboot, check and return

Confirm that Next boot names the intended Kernel and retained Base/System, then:

```sh
systemctl reboot
```

Log in again and inspect what actually runs:

```sh
uname -r
mpm kernel status
mpm system status
```

For the bundled LTS recipe, expect `6.18.63-mojt-lts1`, with Running and Next boot
identifying the intended deployment. Confirm the matching module tree and test
needed storage, networking and services. A prepared entry alone is not boot proof.

To return to a compatible retained prepared Kernel:

```sh
mpm kernel activate
```

Choose the previous Kernel, review the change, reboot and repeat the status
checks. Activation selects a prepared entry without rebuilding. If the new
Kernel cannot reach a login, select the previous complete entry in the bootloader.
Base, System and Ports keep their independent lifecycles. Persistent configuration
and application data remain shared; choosing an older Kernel does not undo data.

See [MBT](../part-i/mbt.md) for advanced build options and [SSH](ssh.md) for remote
administration.
