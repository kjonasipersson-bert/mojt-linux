<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Retained firmware generation and ordinary QEMU guest-agent procedure

This is a target-side test procedure, not a report of physical success. It keeps
the current Base, Kernel, boot profile, ordinary services and persistent
configuration. The new System replaces firmware data and adds the fixed,
conditionally started upstream QEMU guest-agent service. It does not convert an
existing ThinkPad boot policy to the generic PC policy.

## Preconditions and preparation

Use the reviewed checkout as root on installed native Mojt, with running and next
boot identifying the same deployment. The helper supports the existing
single-runtime System composition and native hardware metadata version 2. It
uses the installed Nixpkgs source, Nix, MPM and retained tar/zstd helpers. No new
Kernel build is needed. Firmware binaries, source/license data, archives and the
new installed generation require additional disk space.

```sh
python3 -I -B tools/mojt-system-firmware-test.py prepare
```

Preparation freezes the reviewed manager/MBT cohort before execution. It imports
binary `linux-firmware` and `qemu_kvm.ga`, obtains exact upstream license/source
data, copies owned System content and creates `system-firmware-1`. Other provider
references remain retained. Nix source fetching is restricted to the selected
fixed-output fetch; a plan that would build dependencies is refused. Imported
binaries use Nix's signature policy. This does not establish native Mojt release
signing or physical device acceptance.

Old firmware names and regulatory data are retained while incoming files replace
collisions in the new copy. Upstream `WHENCE` and license texts are included. No
running profile, package hook or persistent configuration is patched/executed by
the packager. Running System and next boot must remain unchanged.
Both older root-level license files and upstream's `LICENSES/` directory are
retained alongside `WHENCE`.

The workspace is `/var/lib/mojt/firmware-system-test`. After a checkpointed
interruption, rerun `prepare` with the same script and frozen code. Inspect its
phase and package paths with:

```sh
python3 -I -B tools/mojt-system-firmware-test.py status
```

After updating the reviewed checkout to fix an unfinished preparation, explicitly
refresh its frozen code with:

```sh
python3 -I -B tools/mojt-system-firmware-test.py prepare --refresh-code
```

This requires phase `preparing`, no published package, unchanged running/selected
deployment and intact old frozen resources. It retains the original checkpoint
baseline, downloaded Nix objects and roots, and the previous frozen resources.
Completed preparation cannot be refreshed this way.

## Install, select and check

```sh
python3 -I -B tools/mojt-system-firmware-test.py install
```

The running manager imports the native generation/component with `--content-only`.
The complete installed candidate cohort is verified, then its public System-stage
frontend runs in a fresh isolated Python process. This uses the new firmware
transition reader without replacing any running manager file. Preparation phases
remain visible and next boot stays unchanged. Normal Base, Kernel, provider and
startup checks remain in the path.

```sh
python3 -I -B tools/mojt-system-firmware-test.py activate
```

Review the displayed System change and retained Base/Kernel. Selection uses an
expected-selected guard and does not reboot automatically. Reboot deliberately,
then run:

```sh
python3 -I -B tools/mojt-system-firmware-test.py check
systemctl status mojt-hardware.service qemu-guest-agent.service
journalctl -b -k
```

`check` verifies running/selected System identity, original Base/Kernel/boot policy,
the selected read-only `/lib/firmware` binding and ordinary agent version. Without
a QEMU agent channel, the agent service should be inactive/skipped, not failed.
Check real networking and devices separately. Retain firmware diagnostics locally;
unit success is not acceptance of every device family.

## QEMU scope

Use a disposable guest image with the selected profile's supported boot controller
and a VirtIO serial port named `org.qemu.guest_agent.0`; see the
[hardware chapter](../../doc/handbook/part-iii/hardware.md#86-qemu-guests).
Use an offline image, not a copy treated as consistent while its disk is mounted.
Check IP networking/SSH independently. With libvirt, read-only host probes include:

```sh
virsh qemu-agent-command VM_NAME '{"execute":"guest-ping"}'
virsh qemu-agent-command VM_NAME '{"execute":"guest-info"}'
```

CI's tiny guest probe uses a real Kernel, ordinary distribution qemu-ga and VirtIO
serial. It validates protocol transport, not the complete Mojt System, every RPC,
graphical integration or physical firmware. Report these scopes separately.

## Return

While the new generation is running and selected:

```sh
python3 -I -B tools/mojt-system-firmware-test.py back
```

Reboot deliberately. `mpm system status` should show the original generation
running and selected, with its original firmware and the same Base/Kernel.
Keep the new generation and evidence until acceptance is complete.
