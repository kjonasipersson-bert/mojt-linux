<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# 7. Building and installing a Kernel

This chapter follows a Kernel from source to a running Mojt installation using
the public MBT and MPM commands. It assumes an existing native-v2 installation,
a builder-enabled System, and an administrator account. Use a working current
deployment and retain its Kernel and boot entry throughout the procedure.

| Operation | Runs as | Effect |
| --- | --- | --- |
| Prepare compiler tools | Administrator on the current single-user Nix store | Import a private pinned tool environment |
| Compile | Ordinary build user | Create a Kernel, matching modules and build evidence |
| Package | Build user or administrator | Create an exact native Kernel archive |
| Install | Administrator | Retain the archive and Kernel/module tree; leave next boot unchanged |
| Prepare and select | Administrator | Construct a complete boot entry and select it for next boot |
| Reboot | Administrator | Start the selected combination |

Base, System and Ports keep their independent lifecycles. A Kernel change uses
the selected compatible Base and System. Persistent configuration and user data
remain shared across Kernel changes; selecting an older Kernel does not roll
back application data.

## 7.1. Choose a recipe and starting configuration

Builder-enabled Systems bundle exact source recipes:

| Track | Upstream version | Kernel/module release |
| --- | --- | --- |
| `linux-kernel-lts` | 6.18.63 | `6.18.63-mojt-lts1` |
| `linux-kernel` | 7.3.4 | `7.3.4-mojt1` |

These are pinned versions, not automatic lookups of the latest release. The
examples below build the LTS track. Use a separate workspace and service name
for the other track. An explicit reviewed recipe can instead be selected with
`--plan FILE`; it is mutually exclusive with `--track`.

Supply a reviewed x86-64 Debian Kernel configuration. The builder freezes it,
checks the supplied SHA256, applies the recipe policy, runs `olddefconfig` and
records the complete configuration diff. It does not infer a starting config
from whichever host happens to run the command.

You need space for source, object files, staged modules and the package. Full
builds with a broad Debian configuration can take hours on modest hardware.
The initial builder accepts one to four parallel jobs; the examples use two.
Do not replace a running Kernel's on-disk module tree with build output.

## 7.2. Prepare tools and the build account

Inspect the current installation first, as administrator:

```sh
mpm system status
mpm kernel status
mbt build kernel --help
```

The following examples use an ordinary account named `mojtbuild` with home
`/home/mojtbuild`. Substitute your actual account and paths consistently. If
creating a new dedicated account, run as root:

```sh
useradd -m -U -s /run/mojt-system/bin/bash mojtbuild
```

Do not repeat account creation if it already exists. The background build below
needs no password or SSH access for this account.

Prepare a **new** environment as root. If a matching prepared environment is
already available, reuse its path instead. The output must not exist:

```sh
install -d -m 0755 /var/lib/mojt/kernel-build
(
    umask 022
    mbt env --profile kernel \
      --source-manifest /run/mojt-system/ports.toml \
      --output /var/lib/mojt/kernel-build/environment
)
```

Review the pin and tool imports at the prompt. `umask 022` makes the root-owned
environment readable/traversable by the build user. Keep that parent readable
as well. MBT imports the pinned binary compiler environment separately from
Ports defaults; it does not grant the build user write access to the Nix store.

Place the reviewed config at a readable, stable path, for example
`/var/lib/mojt/kernel-build/debian.config`. For a **new** config destination:

```sh
install -m 0444 /path/to/reviewed-debian.config \
  /var/lib/mojt/kernel-build/debian.config
```

Replace the input placeholder with the actual reviewed file. Reuse an existing
accepted copy without overwriting it. Record its digest in the root shell used
for the preview and launch below:

```sh
CONFIG_SHA256=$(sha256sum /var/lib/mojt/kernel-build/debian.config | cut -d ' ' -f 1)
printf '%s\n' "$CONFIG_SHA256"
```

## 7.3. Build as an ordinary user, including over SSH

Create the workspace under the build user's identity. Run this launch command
as root; `systemd-run` runs `mkdir` as `mojtbuild`:

```sh
systemd-run --wait --pipe --collect --uid=mojtbuild --gid=mojtbuild \
  /usr/bin/mkdir -p -m 0700 /home/mojtbuild/kernel-build/lts
```

Preview the exact inputs. A root preview is permitted because it executes no
compiler, fetches no source and creates no result:

```sh
mbt build kernel --track linux-kernel-lts \
  --config /var/lib/mojt/kernel-build/debian.config \
  --config-sha256 "$CONFIG_SHA256" \
  --environment /var/lib/mojt/kernel-build/environment \
  --output /home/mojtbuild/kernel-build/lts/result --jobs 2 --dry-run
```

After the preview succeeds, start the actual build in a detached service:

```sh
systemd-run --unit=kernel-lts-build --uid=mojtbuild --gid=mojtbuild \
  --property=WorkingDirectory=/home/mojtbuild/kernel-build/lts \
  --property=UMask=0022 --property=RemainAfterExit=yes \
  --setenv=HOME=/home/mojtbuild --setenv=PATH=/run/mojt-system/bin:/usr/bin:/bin \
  /run/mojt-system/bin/mbt build kernel --track linux-kernel-lts \
  --config /var/lib/mojt/kernel-build/debian.config \
  --config-sha256 "$CONFIG_SHA256" \
  --environment /var/lib/mojt/kernel-build/environment \
  --output /home/mojtbuild/kernel-build/lts/result --jobs 2 -y
```

Compilation runs under the ordinary UID; root only launches the service. Source,
objects and modules stay in the separate workspace. The service continues if
SSH disconnects. Follow real phase messages and compiler output with:

```sh
journalctl -fu kernel-lts-build
```

Ctrl-C leaves the journal viewer without cancelling the build. When the build
finishes, inspect its exit status:

```sh
systemctl show kernel-lts-build -p Result -p ExecMainStatus
```

Expect `Result=success`, `ExecMainStatus=0`, and the builder's `READY` message
identifying `result/kernel.json`. `RemainAfterExit=yes` retains the successful
service for inspection; it does not keep compiling. The result contains its
Kernel release, matching modules, configuration diff and input provenance.

An ordinary user with direct terminal access can run the same `mbt build kernel`
command without `systemd-run`. Actual compilation as root is refused. For new
builds, use new output paths and service names; completed outputs are retained.
For supported interrupted builds, see [explicit resume](../part-i/mbt.md#43-build-a-kernel-as-an-ordinary-user).

## 7.4. Package and install the result

As root, use a new package output directory:

```sh
mbt package kernel --build /home/mojtbuild/kernel-build/lts/result \
  --revision 1 --output /var/lib/mojt/kernel-build/package-lts
```

The packager checks the completed build evidence and staged Kernel/modules.
An incomplete result with a `.building` marker is refused. It reports the
archive filename and full artifact ID. Keep both: version labels alone cannot
distinguish different builds. The packaging revision is independent of the
upstream Kernel version.

Replace `ARCHIVE` below with that archive's full path and
`sha256:FULL_KERNEL_ID` with the reported artifact ID:

```sh
mbt package verify ARCHIVE --expected-id sha256:FULL_KERNEL_ID
mpm kernel install --from-file ARCHIVE \
  --expected-id sha256:FULL_KERNEL_ID --dry-run
mpm kernel install --from-file ARCHIVE \
  --expected-id sha256:FULL_KERNEL_ID
mpm kernel status
```

Installation retains the exact content. The running Kernel and next-boot
selection remain unchanged. SHA256 identifies/integrity-checks the local build;
it is not publisher authentication. Keep the previous working Kernel installed.

## 7.5. Prepare and select next boot

Preview the change using the installed artifact ID:

```sh
mpm kernel upgrade --artifact sha256:FULL_KERNEL_ID --dry-run
```

Review the proposed Base, System and Kernel and any compatibility refusal.
After a successful preview, perform the preparation and selection:

```sh
mpm kernel upgrade --artifact sha256:FULL_KERNEL_ID
mpm kernel status
mpm system status
```

Here `upgrade --artifact` uses the exact **already installed** Kernel. It joins
boot preparation and selection, without fetching another release or changing an
upgrade wish. A standalone `stage` command is not required. Constructing the
matching initramfs and boot entry can take time; phase starts and completions
are reported without estimated percentages. The current Kernel keeps running.

Check that Next boot names the intended Kernel and that Base/System are the
expected retained choices. Running and Next boot differ until the reboot.

### When the retained Base declares an older Kernel range

An otherwise usable Base can have declared Kernel bounds that exclude the new
version. MPM refuses that transition instead of silently broadening the range.
For an explicit compatibility test, supply a reviewed Base-context JSON file
bound to the **same exact Base artifact and release**. Its format is:

```json
{
  "format": "mpm-kernel-base-context-v1",
  "platform": "x86_64-linux",
  "base": {
    "artifact": "sha256:FULL_CURRENT_BASE_ID",
    "release": "CURRENT_BASE_RELEASE"
  },
  "kernel_min": "UNCHANGED_ACCEPTED_MINIMUM",
  "kernel_max": "6.18.63"
}
```

Replace the uppercase placeholders with facts from the retained Base context
and `mpm base status --json`. Preserve the accepted minimum and choose the
reviewed maximum; do not substitute guessed identities or rewrite release files.
This is a local declaration for the requested test, not proof that every version
in the interval has booted. If the existing range already covers the Kernel,
leave it unchanged.

Use the existing Base operation to prepare/select that exact Base with the new
context, then repeat the Kernel preview and upgrade:

```sh
mpm base upgrade --artifact sha256:FULL_CURRENT_BASE_ID \
  --base-context /path/to/reviewed-base-context.json --dry-run
mpm base upgrade --artifact sha256:FULL_CURRENT_BASE_ID \
  --base-context /path/to/reviewed-base-context.json
```

The Base content remains the same. This updates the selected deployment's
declared context; no separate context-only reboot is needed before the Kernel
upgrade. Other compatibility gates still apply.

## 7.6. Reboot, check and return to a previous Kernel

After verifying the intended next boot, reboot deliberately:

```sh
systemctl reboot
```

Log in again, by console or SSH, then inspect the actual running combination:

```sh
uname -r
mpm kernel status
mpm system status
```

For the bundled LTS recipe, expect `6.18.63-mojt-lts1`. Running and Next boot
should identify the same intended deployment. Confirm the matching module tree
is available and exercise the machine's network, storage and needed services.
An installed or prepared entry alone does not establish boot success.

To return to a compatible **already prepared** Kernel, choose it interactively:

```sh
mpm kernel activate
```

Or select its full installed artifact ID explicitly:

```sh
mpm kernel activate --artifact sha256:FULL_PREVIOUS_KERNEL_ID
mpm kernel status
```

Activation selects a retained prepared entry without rebuilding it. Reboot and
repeat the running-status checks. The chooser only offers prepared combinations
compatible with the other selected areas; retain complete recovery entries as
well. If the new Kernel cannot reach a login, select the previous retained entry
in the bootloader menu. Configuration and application state stay persistent.

See [MBT](../part-i/mbt.md) for build-environment, packaging and resume details,
[MPM](../part-i/mpm.md#38-activate-and-reboot) for selection semantics, and
[SSH](ssh.md) for remote administration.
