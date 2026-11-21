<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Generic PC hardware: readiness and acceptance procedure

This procedure covers the `pc-x86_64` profile and its `pc-x86_64-v1` native boot
policy. It distinguishes a short read-only probe from booting a new image.
No new Kernel compilation is required if the existing Kernel provides the early
drivers. Preserve the working installation and its recovery deployment.

## Short probe on an existing Mojt installation

From the reviewed source checkout, with Python, kmod and udevadm available:

```sh
python3 -I -B tests/check-pc-hardware.py
```

The probe calls `modprobe --show-depends` against the running Kernel's module
tree, then `udevadm trigger --dry-run` to enumerate devices. It must not load
modules, trigger events, compile, download, install or change boot selection.
It reports which checks passed. Missing early drivers are a failure to resolve
this profile, not a reason to overwrite the running Kernel. Retain stderr.

If the extracted broader firmware input is already available, also check it:

```sh
python3 -I -B tests/check-pc-hardware.py --firmware-root /path/to/firmware-root
```

Without this option, firmware inputs are explicitly not tested. A successful
short probe does not validate booting the new System or real Wi-Fi/GPU firmware.

## Fresh-image acceptance

Prepare the firmware input and explicit native Base/Kernel/System inputs using
the [hardware chapter](../../doc/handbook/part-iii/hardware.md) and
[MBT bootstrap procedure](../mbt-minimal.md#fresh-native-v2-bootstrap).
Use a new output directory with `--hardware-profile pc-x86_64`, first with
`--dry-run`, then without it. Do not modify an old immutable System profile or
change the running installation's machine policy to make a test pass.

Check that:

1. Preview names `pc-x86_64-v1` and the intended exact Base/Kernel inputs.
2. Construction retains all firmware families, licenses and any input provenance;
   the Kernel module tree remains owned by the Kernel artifact.
3. A separate image boots on SATA, USB and NVMe emulation, including a second boot
   on another supported bus, with persistent state retained. Use a separate copy
   from any active image. CI's synthetic firmware checks mount/ownership paths,
   not real wireless or GPU operation.
4. A physical test uses separate boot media/target and has a working recovery
   option. Check local login, keyboard, storage, networking and SSH if enabled.
   Record the actual tested device models and Kernel/firmware versions locally.
5. `systemctl status mojt-hardware.service systemd-udevd.service` succeeds, and
   `journalctl -b -u mojt-hardware.service` and `journalctl -b -k` show any probing
   or firmware failures. Inspect actual device operation, not only unit status.
6. Reboot and shutdown complete, and the preserved previous installation still
   boots. Do not infer that another device family works from this result.

The old ThinkPad profile stays available. This change does not implement a live
ThinkPad-to-PC profile migration or bypass System's unchanged-startup gate.

## Automated scope

Unit/integration tests cover family/license input refusals, immutable input
freezing, generic udev command ordering and failure propagation, profile mismatch
refusal, fresh native image/mounted-target construction and portable inputs.
The hardware boot workflow adds a generic NVMe-to-USB storage probe alongside
the existing SATA/USB and shutdown tests. Report local, CI, VM and physical
outcomes separately; the existence of a workflow is not a recorded PASS.
