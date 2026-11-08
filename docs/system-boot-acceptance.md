<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# One native-v2 System A/B/A owner test

This is the next acceptance gate for [System selection](native-system-selection.md),
not another Base/Kernel combination matrix. It proves a real firmware/Kernel/PID1
handover to a changed exact System, installed-MPM selection and return, persistent
state and the static shutdown exitrd. Preparation is implemented; owner boot
acceptance is pending. CI checks preparation boundaries, records and the existing
actual-archive/chroot path; it does not run this Nix-backed VM journey.

## Inputs and isolation

Run preparation as the ordinary Debian user, directly in an interactive terminal.
Use the current pinned source checkout for the image/preparation tools and all
delivered MPM code. An already retained, verified step-10 provider payload with
GNU tar can be reused: that export contains provider binaries, not the MPM source
code assembled by the current checkout. Reuse the accepted Base release and exact native Kernel package;
neither input nor any previous VM disk is modified or attached.

The existing native image builder creates a new private `.unpublished-image` and
asks for a new VM root password. A root helper in a private mount namespace mounts
only that new disk. A temporary execution root runs the explicitly supplied
bootstrap System Python/Nix against the new disk's own `/nix`, with its actual
registration and accepted NAR hashes. Host Nix is not used; candidates do not
execute during staging. Only the fixed registration load is performed, not the
bootstrap setup script or arbitrary package hooks.

Both native candidates preserve the bootstrap startup/services/provider closure.
Their labels, version file, harmless tooling marker and exact artifacts differ.
The same manager constructor builds and admits both complete slots before the
initial hook/menu is published. Only after successful unmount/detach does the
preparer rename `image` and publish its outer `run-qemu.sh` and path file. A
failure retains private evidence and publishes no READY launcher. Do not launch
an internal `.unpublished-image` or use the finalizer on an existing installation.

This is fresh-image preparation, not live v1 migration or active-v2 staging.
The trusted bootstrap interpreter is explicitly taken from the supplied System's
verified Python output. Its private initramfs closure does not change Base libc.
The ordinary Nix runtime adapter is unchanged. Hashes are integrity evidence,
not publisher authentication.

## Debian preparation

The host needs the same native-image prerequisites as the earlier Base test,
plus `losetup`, `mount`, `umount`, `unshare` and `chroot`. Nix is needed only when
preparing the System payload (the existing Distrobox route is sufficient).

```sh
python3 -I -B "$SOURCE/tests/prepare-system-boot.py" \
  --base-release /home/jonasp/mojt-lab/releases/base-0.1.3-x86_64 \
  --kernel-package /home/jonasp/mojt-kernel-package.MMLKo3/package/kernel-linux-6.12.107-r1-x86_64-linux-eed451b5497d.tar.zst \
  --expected-kernel sha256:eed451b5497d078b8de4c098539cf63a4551aa0a46864fe7550b59066fe26250 \
  --system-payload /home/jonasp/mojt-lab/mpm-nix-home/mojt-base-deployment.k3eJaO/system-step10 \
  --output "$LAB/vm" \
  --path-file /home/jonasp/mojt-system-boot-test-path
```

`SOURCE` is the pinned checkout and `LAB` its separate new private test directory;
the payload is the retained result of `mojt-system-prepare.py --step 10`. Re-export
only if it is unavailable or lacks GNU tar. Preparation can
take several minutes because complete provider trees are verified and two real
initramfs archives are built. Progress messages identify these phases. Do not
retry into the same output or interrupt just because hashing is quiet.

Start only the final launcher (it uses the serial console):

```sh
QEMU_DISPLAY=none bash "$(cat /home/jonasp/mojt-system-boot-test-path)/run-qemu.sh"
```

## Three boots, one checkpoint

Log in as root. The test runner/checkpoint is already on persistent storage;
there is no need to remount the read-only input disk after each reboot.

On A:

```sh
python3 -I -B /var/lib/mojt/system-boot-acceptance/run.py baseline
python3 -I -B /var/lib/mojt/system-boot-acceptance/run.py select
systemctl poweroff
```

Restart the **same final launcher**. Accept the default B entry. On B:

```sh
python3 -I -B /var/lib/mojt/system-boot-acceptance/run.py check
python3 -I -B /var/lib/mojt/system-boot-acceptance/run.py rollback
systemctl poweroff
```

Restart the same launcher again; accept the default A entry:

```sh
python3 -I -B /var/lib/mojt/system-boot-acceptance/run.py check-old
```

The runner checks exact deployment/artifact IDs and System marker, unchanged
Base/Kernel/installation, selected/running agreement, read-only root/System/module
mounts, account/machine/timezone data, the existing Ports profile (including an
empty baseline), all four persistent mount markers, the A journal and no failed
units. It uses the installed `mpm` frontend for preview, selection, status and
rollback. A real changed boot ID is required each way. It does not install extra
Ports just to repeat the previously accepted Ports suite.

At both shutdowns retain the serial-console ending. Require:

```text
Mojt shutdown: entered static exitrd
Mojt shutdown: old root and backing filesystem fully unmounted
```

Busy unmount errors or the exitrd ERROR/read-only fallback are not clean-shutdown
acceptance even if the machine powers off. If a phase fails, retain its output
and checkpoint; do not rebuild or rerun earlier phases blindly.

## Scope after acceptance

This closes the prepared-candidate boot/return proof only. Public installed
System staging from an active v2 baseline, request/configuration-to-boot joins,
v2 Base/Kernel boot updates and MBT reuse remain separate roadmap work. Native
self-hosting still requires pinned Base and Mojt-owned System source recipes;
assembling this test from prebuilt inputs does not meet that milestone.
