<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Source Base switch and return: short VM test

Scope: one switch from our working source Base 0.2.0 to a local marked test
successor (`0.2.0-test1`), followed by one return. This does not test Void-built
releases or migration from Base 0.1.3. The successor uses the retained compiled
source build rootfs, with a different version and one file under `/usr/lib`.
There is no compiler execution, Kernel build or System generation replacement.

The host helper makes a separate raw disk copy of the working source Base VM.
It packages the successor and attaches a read-only input disk. All install,
stage and selection operations use the VM's ordinary installed MPM. No manager
replacement or production code changes are needed for this test.

## Debian host

Shut down the source Base VM with `poweroff` and wait for QEMU to exit. Run as
the ordinary host user, using the checkout containing these test scripts:

```sh
TEST=(python3 -I -B tests/prepare-source-base-transition.py
  --vm "$HOME/mojt-base-boot-test/image"
  --base-build "$HOME/mojt-base-result"
  --output "$HOME/mojt-base-switch-test")
"${TEST[@]}" --check-inputs
"${TEST[@]}"
bash "$HOME/mojt-base-switch-test/run-qemu.sh"
```

The paths are examples; `--vm` identifies the image directory containing
`disk.img` and `bootstrap.json`. Keep the completed source build's `rootfs`
directory. The output must not exist. Host prerequisites are the previous VM
tools plus `qemu-img` (Debian package `qemu-utils`). Input checking creates no
output. Copying uses QEMU image locking without a force-share override; the
original VM must remain stopped throughout copying. Original disks are never
attached to the test VM. Failed private output is retained for diagnosis.

## Copied Mojt VM

Log in using the original VM's password. Copy the test driver once:

```sh
mkdir -p /mnt/mojt-base-transition
mount -o ro LABEL=MOJT_BASE_SWAP /mnt/mojt-base-transition
cp /mnt/mojt-base-transition/bt.py /root/bt.py
python3 /root/bt.py start
```

`start` creates two persistent markers in `/etc` and `/var`, installs and stages
the test Base, checks that staging left running/next boot unchanged, then selects
the test Base for next boot. It never reboots automatically. On PASS:

```sh
reboot
```

The launcher exits on reboot. Start the **same copied VM** again on the host:

```sh
bash "$HOME/mojt-base-switch-test/run-qemu.sh"
```

Inside Mojt:

```sh
python3 /root/bt.py after
```

The driver remounts its read-only input disk if necessary. It checks the new
Base identity and visible content marker, unchanged exact System/Kernel and
boot policy, account/machine identity, persistent root layout, both state
markers, glibc 2.44, account/localhost lookup, MPM status and failed services.
It then selects the original Base for next boot. On PASS, reboot and launch
the same copy once more. Inside Mojt:

```sh
python3 /root/bt.py check-back
```

The final check requires a different boot, the original Base and absence of the
test Base's `/usr/lib` marker, with the same System/Kernel and persistent state.
The test leaves its checkpoint and markers on this disposable copy. A failure
stops the driver without automatic reboot, return selection or cleanup.

If content installation succeeded but preparation/selection stopped, keep the
same VM and checkpoint, update `/root/bt.py` to the matching revised test driver,
then run `python3 /root/bt.py resume`. This reuses the installed Base, verifies
existing Kernel bounds, and continues preparation/selection without reinstalling
or creating new markers. It also works after a reboot into the original Base.
It refuses phases after successful selection; use `after` and `check-back` for
the actual reboot checks. A passing `stage --dry-run` alone is not preparation
or boot acceptance.

Record VM results separately from fixture tests. Publishing this procedure does
not establish successful reboot/return acceptance on the owner's VM.
