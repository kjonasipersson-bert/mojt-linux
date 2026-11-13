<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Physical MPM/MBT performance: the ordinary command path

This is a small manual measurement session after the joined VM journey in
[minimal MBT](mbt-minimal.md#one-joined-acceptance-journey) and
[installation to SSD](mounted-installation.md). USB is the startup/installation
medium; compiler and ordinary-command measurements run on the SSD installation.
It changes neither
the installed tools nor their verification policy. It is not another acceptance
harness, a hardware benchmark suite or a full generation cross-product.

## Prepare before visiting the machine

Use the supported ThinkPad X1 Carbon 3 profile and the accepted native-v2
bootstrap path. Keep the accepted VM image, builds and inputs as the reference.

For a device marketed as 32 GB, prepare a **new 24576-MiB (24-GiB) image** using
the existing `mbt bootstrap --disk-size-mib 24576` option, the same exact
Base/Kernel/System inputs, the hardware profile and
`--with-build-tools --with-installer-inputs`.
Use a new output directory and a fresh guest password. This is ordinary bootstrap,
using the same constructor as mounted SSD installation. Do not truncate the 32768-MiB
reference image: changing just the file length would leave its filesystem and
GPT inconsistent. No resizing of the accepted image is needed.

A 24576-MiB image requires 25769803776 bytes; the 32768-MiB reference requires
34359738368 bytes and is too large for many nominal 32-GB devices. Inspect the
actual destination capacity in bytes before deciding it fits. The destination's
model/serial and mounted partitions must be inspected on the Debian host before
a separately authorized write. This guide does not select a disk or provide a
generic disk-write command. Use the one-time UEFI boot menu with Secure Boot
disabled for this unsigned chain. The USB write and prepared SSD target are
separate explicit choices; existing OS partitions are never implicitly selected.

Shut any VM using the image down cleanly and wait for QEMU to exit before copying
or writing it. A successful static-exitrd shutdown is the completion signal;
do not copy a live disk. Do not attach two copies with the same filesystem UUID
during physical boot.

Copy this guide and [`tests/measure-command.sh`](../tests/measure-command.sh)
from one reviewed, pinned repository revision into `/var/lib/mojt/performance/`
before starting the measurements. This can be done in the running VM before its
clean shutdown, or once booted on the physical machine. Keep the helper root-owned
and readable (`0644`); it is invoked through Bash. The measurement helper needs
no System rebuild, offline filesystem editing or additional package. Bash and
`date` are already supplied by the builder. Retain its repository revision and
SHA256 with the results; hashes identify content, not its publisher.

Prepare only the private **image-tool** environment on the USB as described in
the installation guide. Its carried kit and tools then install Mojt to the
prepared SSD partitions without a checkout or compiler. Boot from SSD before
collecting the following timings; a USB boot needs only login, keyboard/display,
basic network usability and available installed tools.

The new SSD installation carries the normal System closure and exact installed
Kernel/provenance, but no compiler environment or previous build objects. Its
first Kernel-profile `mbt env` measures acquisition of missing build-tool outputs.
Record outputs already shared with System; this is not an entirely empty Nix
store. Read the original Debian config from the retained Kernel provenance and
acquire the pinned upstream source when needed. Check free space on SSD before
compiling, allowing for objects, staged modules, package and installation.
The original VM remains the reference with earlier builds retained. Copy the
small timing helper/guide into the SSD's persistent state if they were prepared
on USB; installation does not copy the USB's general mutable state.

## Measurement rules

- Run the installed `/run/mojt-system/bin/mpm` and `mbt`, without a checkout.
- Measure each mutating operation once. Repeat only the short read-only commands
  below. Never repeat installation merely to collect more timing samples.
- Default command verification is included in the measured operation. Do not add
  `--verify`, the diagnostic full-tree boot profiler or acceptance scripts.
- Keep normal boot mode. Do not drop caches, run GC, change global loader paths,
  remove retained content or bypass integrity checks to improve a number.
- Record AC/battery state, storage medium/USB port, CPU/RAM, job count and cache
  conditions. A first invocation is not proof of a cold filesystem cache.
- Leave command output on the terminal. The helper records only invocation,
  UTC start, UID, wall/user/system seconds and exit status in a new private file.
  It does not record stdin or passwords; do not pass secrets in command arguments.
  It returns the command's exit status and never retries or reboots.

Ordinary-user timings and root timings need separately owned result directories.
Choose fresh directories for a new session; the helper refuses existing reports.

## SSD boot and fast baseline

Time power-on to the usable login prompt with an external clock. Record whether
this was power-on or reboot and whether the GRUB timeout was included or skipped.
That includes firmware/bootloader time and is separate from a command duration.

After login as root, collect this small unmeasured context once:

```sh
uname -r
grep -E 'model name' /proc/cpuinfo | head -n 1
grep -E 'MemTotal|MemAvailable' /proc/meminfo
df -h /home /var
cat /run/mojt/boot-checks.json
systemctl --failed --no-pager
nmcli device status
```

Check that boot-checks reports `mode=normal` and `content_verified=false`.
Its reader/state timings are early-boot components, not total boot time. Use
`nmcli --ask` if Wi-Fi needs configuration; connecting Wi-Fi is outside the
MPM/MBT command timing. No repeated network or account acceptance matrix is needed.

Then run the small read-only baseline, retaining the default verification scope:

```bash
M=/var/lib/mojt/performance/measure-command.sh
R="$(mktemp -d /var/lib/mojt/performance/run.XXXXXX)"
bash "$M" "$R/mpm-kernel-first.txt" -- /run/mojt-system/bin/mpm kernel status
bash "$M" "$R/mpm-kernel-repeat.txt" -- /run/mojt-system/bin/mpm kernel status
bash "$M" "$R/mpm-system.txt" -- /run/mojt-system/bin/mpm system status
bash "$M" "$R/mbt-help-first.txt" -- /run/mojt-system/bin/mbt --help
bash "$M" "$R/mbt-help-repeat.txt" -- /run/mojt-system/bin/mbt --help
cat "$R/"*.txt
```

`mbt --help` measures frontend startup only; it does not prepare an execution
snapshot, fetch a provider, or measure environment creation. Status is metadata
inspection, not a content scrub. Preserve those labels when comparing results.

## One optional full build and update on SSD

The following uppercase paths/IDs are explicit placeholders to fill from the
retained installation on site. Use a new workspace and a new localversion, for
example `-mojt3`, rather than overwriting a retained build or module tree.
Keep the original upstream pin/config and change only the intended localversion.
Package revision and compiled release remain separate identities.

| Phase | Normal command to put after `REPORT --` in the timing helper | User |
| --- | --- | --- |
| Tool environment | `mbt env --profile kernel --source-manifest /run/mojt-system/ports.toml --output NEW_ENV -y` | root for the current provider store |
| Kernel build | `mbt build kernel --plan PLAN --config CONFIG --config-sha256 HASH --environment TOOLS --source SOURCE --output NEW_BUILD --jobs JOBS -y` | ordinary builder |
| Package | `TOOLS/run /run/mojt-system/bin/mbt package kernel --build NEW_BUILD --revision 1 --output NEW_PACKAGE` | ordinary builder |
| Install | `mpm kernel install --from-file ARCHIVE --expected-id ARTIFACT -y` | root |
| Select next boot | `mpm kernel activate --artifact ARTIFACT --expected-selected OLD_DEPLOYMENT -y` | root |

Use the absolute installed MPM/MBT paths, as in the baseline. Prefix every row
with `bash "$M" NEW_REPORT --`; measure environment creation, build, package,
installation and activation separately. Commands keep their normal terminal
output. The package step selects `zstd` through the private tool environment.
Packaging prints a potentially large descriptor. Save that normal machine-readable
output to a new file, consistently across comparisons, instead of timing terminal
rendering. For example, as the ordinary builder, with the placeholders filled:

```bash
bash "$M" "$R/package.txt" -- "$TOOLS/run" /run/mojt-system/bin/mbt \
  package kernel --build "$NEW_BUILD" --revision 1 --output "$NEW_PACKAGE" \
  >"$WORK/package-result.json"
```

The timing report still goes to its separate file and command errors stay visible.
For a new root-created tool environment, use `umask 022` and a traversable parent
so the ordinary builder can read/execute it. Do not run the compiler as root.
No extra dry-run or independent full archive verification is required in this
performance session; the normal commands still perform their own validation.

Choose the build job count after seeing physical CPU/RAM. Start with two if using
the previous 4-GiB configuration; the current driver supports one to four jobs.
`--source` must name the retained clean checkout matching the recipe's exact
commit/origin. New objects are compiled in `NEW_BUILD`; old objects are not reused.
That timing excludes source transfer and is labelled a fresh object build with
retained source. To include network source transfer, omit `--source` and label it
explicitly; never treat the difference as compiler speed.

An image copied after the VM build already has the tool outputs in its Nix store.
Creating a new environment in it is a **populated-store** measurement, including
the ordinary closure verification and probes, not an uncached download test.
Keep acquisition logs if new outputs are fetched. A separately bootstrapped builder, retaining its normal
System closure but no previous compiler environment, measures acquisition of the
actually missing tool outputs. Record those shared inputs rather than calling
the whole store empty. No cleanup of this working installation is part of the session. Likewise, an already installed
Kernel measures the no-op path, not first installation. Build a distinct release
for the installation/activation timings, or label reuse of an existing candidate
as such. After a new build, its packaging version string is not the boot artifact
identity: use the full ID returned by the packager.

Keep the previous deployment ID before activation. After success, use normal
`systemctl poweroff` and the physical boot menu. On next boot, check `uname -r`,
`mpm kernel status`, `systemctl --failed --no-pager` and basic network usability.
These are quick checks outside the operation timer. Confirm the new exact
artifact is selected/running, not merely the same release string. The previous
deployment stays available as a recovery choice. Do not require another rollback
matrix; collect more diagnostics only if something fails on real hardware.

Kernel `uname` build time may still show the recipe's fixed 1970 timestamp. The
helper's UTC timestamps/wall durations measure this run; the embedded Kernel
timestamp is not elapsed build time and is not a system clock measurement.

## Reading the result

Report wall seconds and CPU seconds separately. Low CPU relative to wall time can
include storage/network waits; it is not by itself a diagnosis. Record both
read-only invocations without claiming that either cleared or warmed every cache.
Do not add early-boot milliseconds to a manually measured power-on duration.
Report slow default installation/activation honestly, including their built-in
verification. Investigate a slow phase afterward rather than adding heavy tracing
to the baseline, and keep failure/nonzero results instead of timing silent retries.

This guide and timer can be prepared/tested without the physical machine. No
physical performance result, disk write or hardware acceptance is claimed here.
