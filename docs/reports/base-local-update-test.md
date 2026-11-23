<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Local Base 0.2.0 to 0.2.1 update: short VM test

This report contains the acceptance procedure and the recorded VM result below.
It tests the public MBT build and installed MPM workflow. Keep the physical installation and old VM
images unchanged. One new disposable VM starts with the retained source Base
0.2.0 and current System tooling; a separate read-only disk supplies Base 0.2.1.
No marked test release, mandatory separate stage, or return round is needed.

## Debian host

Use this revision's checkout, with the native build and existing VM tools from
the source Base build/first-boot guides. The previous Base 0.2.0 build remains
at `$HOME/mojt-base-result`. The saved input check locates the retained Kernel
and System export. Use new output paths:

```sh
cd "$HOME/mojt-base-src"
python3 -I -B tools/mbt build base \
  --output "$HOME/mojt-base-021-result" --jobs 2

PACKAGE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["package"]["path"])' \
  "$HOME/mojt-base-021-result/result.json")

TEST=(python3 -I -B tests/prepare-source-base-boot.py
  --from-check "$HOME/mojt-normal-boot.CY1x3d/vm/input-check.json"
  --base-build "$HOME/mojt-base-result"
  --with-build-tools --update-package "$PACKAGE"
  --output "$HOME/mojt-base-update-test")
"${TEST[@]}" --check-inputs
"${TEST[@]}"
QEMU_MEMORY_MIB=4096 bash "$HOME/mojt-base-update-test/run-qemu.sh"
```

The build must print size measurements and an MPM package path. The VM helper
uses a new disk, retains the exact Kernel/System package inputs and installs this
revision's manager/build resources. It requests a VM root password through the
ordinary bootstrap. The source/compiler build runs as the ordinary host user;
only new-image assembly uses sudo. `--check-inputs` writes nothing.

## Inside the new Mojt VM

Log in as root. Initial Base must be 0.2.0. Create two persistent markers, then
run the normal installation; do not run stage separately:

```sh
cat /usr/lib/os-release
mpm base status
mbt build base --help
mkdir -p /mnt/base-update
mount -o ro LABEL=MOJT_BASE_UPDATE /mnt/base-update
printf 'keep me\n' >/etc/mojt-base-update-check
printf 'keep me\n' >/var/mojt-base-update-check
mpm base install --from-file /mnt/base-update/base.tar.zst
mpm base status
getent services https/tcp
getent protocols tcp
```

Approve installation and the listed missing defaults. Expect an installed and
prepared Base 0.2.1, while running and next boot still name 0.2.0. Existing files
are preserved; missing IANA tables become available without changing running
Base. Then exercise the combined upgrade command on the same package. It should
reuse the installed/prepared result and show only Base changing:

```sh
mpm base upgrade --from-file /mnt/base-update/base.tar.zst
mpm base status
reboot
```

Approve next-boot selection. System and Kernel must stay the same. QEMU exits on
reboot; relaunch the same new VM on the host with the command above. Inside Mojt:

```sh
cat /usr/lib/os-release
getconf GNU_LIBC_VERSION
getent services https/tcp
getent protocols tcp
cat /etc/mojt-base-update-check /var/mojt-base-update-check
mpm base status
systemctl --failed --no-pager
```

PASS requires Base 0.2.1, glibc 2.44, https=443/tcp, tcp=6, both markers unchanged,
matching running/next boot, the original System/Kernel and no failed units.
Stop here; no automatic return selection or cleanup is part of this test.

## Recorded VM result: 2026-11-23

The owner reported that the complete procedure passed using ordinary MBT/MPM
commands from revision `ec955c561f330d68c475e714d4fedfee5899d9c4`.
The supplied post-reboot output confirms:

- `/usr/lib/os-release` identifies Base 0.2.1.
- Running and next boot both reference Base artifact prefix `c31da01d8e8d`.
- Prepared entries retain Base 0.2.0 (`2bc563193e99`) and Base 0.2.1
  (`611f10570204`); the latter is running and selected. Both use
  Kernel `6.12.107-mojt1`.
- Service lookup resolves `https` to `443/tcp`; protocol lookup resolves `tcp`
  to `6 TCP`.
- Both `/etc/mojt-base-update-check` and `/var/mojt-base-update-check` still
  contain `keep me`.
- `systemctl --failed` lists zero failed units.

The libc-version command was mistyped as `etconf GNU_LIBC_VERSION`, so this
transcript does not contain a new runtime libc-version observation. The packaged
CI libc check passed separately; that is not a substitute for a command observed
in this VM. This result establishes the reported local install/preparation,
selection and reboot workflow, not physical-machine acceptance, remote package
distribution or Nix-toolchain self-hosting.

## Size observation before this change

The complete CI-built Base 0.2.1 from commit `62cba186ecdfba7858ebddcd599c73658b02d55c`
(run 45227796645) measured 9,600,053 compressed bytes (9.16 MiB) and 39,493,810
regular-file payload bytes (37.66 MiB): 887 regular files, 991 archive entries.
Measurement streams the packaged rootfs archive, counting hardlinked payload
only at its data entry. It excludes filesystem block allocation, retained outer
packages, source/build trees and compiler/tool environments. New builds report
their own figures; this observation is not a fixed size budget.
