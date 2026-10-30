<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Existing native-disk Kernel staging and next-boot selection

This experimental checkout frontend follows the accepted fresh native image
builder. It targets that builder's x86_64 serial UEFI/VirtIO layout, initially
with one explicit native boot pair. It rejects customized/unknown boot menus.
The owner accepted the functional boot/rollback sequence on 2026-10-30.
A focused corrected-image shutdown test also passed on 2026-10-30;
excessive repeated verification remains open. See the measured results below.

Building, packaging, installing, staging and selecting remain separate actions.
`kernel install` retains an artifact in the disk's independent Kernel registry.
`kernel stage` generates a deployment-specific initramfs and publishes a complete
new boot slot, without changing the running or next-boot selection. `select`
changes only next boot; `rollback` selects the previously selected deployment.
No command invokes Nix, downloads content, compiles a Kernel, changes Base libc,
updates the selected System userspace or changes Ports wishes.

## Explicit commands

Use the new source checkout's `tools/mpm`; the existing installed step-10 System
frontend is not silently replaced. These commands use `--disk-root`, not the
standalone install/status registry option `--root`. Shared mutations require root.
The registry is `DISK/kernel`. `--baseline` identifies the original native boot
pair directory relative to DISK. Its complete menu and all content bindings must
match before it can be the baseline; `uname` does not adopt a selection.
After the first managed selection, the menu itself identifies the selected entry.

```sh
python3 -I -B tools/mpm kernel status --disk-root /DISK \
  --baseline boot/mojt/SYSTEM/BASE --json

python3 -I -B tools/mpm kernel stage --disk-root /DISK \
  --baseline boot/mojt/SYSTEM/BASE --artifact sha256:FULL_KERNEL_ID --dry-run

python3 -I -B tools/mpm kernel stage --disk-root /DISK \
  --baseline boot/mojt/SYSTEM/BASE --artifact sha256:FULL_KERNEL_ID -y

python3 -I -B tools/mpm kernel select --disk-root /DISK \
  --baseline boot/mojt/SYSTEM/BASE --deployment sha256:STAGED_DEPLOYMENT_ID \
  --expected-selected sha256:CURRENT_DEPLOYMENT_ID --dry-run

python3 -I -B tools/mpm kernel select --disk-root /DISK \
  --baseline boot/mojt/SYSTEM/BASE --deployment sha256:STAGED_DEPLOYMENT_ID \
  --expected-selected sha256:CURRENT_DEPLOYMENT_ID -y

python3 -I -B tools/mpm kernel status --disk-root /DISK --json
python3 -I -B tools/mpm kernel rollback --disk-root /DISK \
  --expected-selected sha256:CURRENT_DEPLOYMENT_ID -y
```

To report actual running identity in the guest, explicitly add
`--running-record /run/mojt/deployment.json` to status. The record must describe
the actual running release. The reported evidence is an explicit runtime record,
not hardware attestation; a release string alone never identifies an artifact.
Installed, staged, selected, previous and running identities remain distinct.

Staging uses the verified selected System's static BusyBox by default, plus the
existing `modprobe` and `zstd` executables. `--busybox` may explicitly supply a
trusted alternative. No new `cpio` installation is required: a bounded Python
newc/gzip writer serializes the private init tree, which the independent existing
archive inspector verifies. GNU cpio independently reads/extracts it in tests.
The acceptance runner privately exposes the zstd executable already retained in
the selected System's verified provider closure; it imports no new package.

## Verification and publication

- Reverify the installed exact Kernel object/archive, selected boot binaries and
  initramfs binding. Check the real immutable Base inventory against its assembly
  receipt and the real System profile/provider objects against its manifest.
  Additional store objects from Ports are allowed and are not System inputs.
- Reuse the deployment resolver's Base bounds, exact System userspace and current
  ABI/state/Ports/shell gates. Recheck them at selection, including rollback;
  older software is not automatically allowed to read newer persistent data.
  `--base-context FILE` can supply an explicit alternative staging declaration
  for the same Base identity. No bounds or fallback are inferred.
- Generate the existing reviewed root/state/System boot template with the
  candidate's exact native module mount. Pin UUID, Base, System and actual Kernel
  release. The initramfs reads its runtime record from its new immutable slot.
- Verify decoded early modules and the complete actual archive inventory,
  contents, modes, owners and character device numbers. Copy the selected Kernel
  image and complete sidecars to `boot/mpm/slots/LOCAL_NONCE`, then publish that
  directory. The local slot name avoids an initramfs/deployment digest cycle.
- Staging does not rewrite `boot/mojt/grub.cfg`. Repeating a stage with identical
  exact inputs and the same builder/BusyBox fingerprint reuses its complete slot.
- Selection keeps the original and previously selected entries in the menu.
  One atomic replacement of `boot/mojt/grub.cfg` publishes its exact generated
  menu and selected/previous identity comments together. There is no second
  authoritative selected-pointer file to disagree with it. The EFI loader already
  loads this path; neither EFI binaries nor the ESP are rewritten.
- Hold a boot registry lock and require the expected current selection. Write and
  fsync complete content before publication; reject altered/custom menus, linked
  paths, missing/damaged content and unsupported scope. Incomplete stage names
  are reported, never silently selected, adopted or collected.

Failed pre-publication selection leaves the old menu intact. The directory and
menu publication boundaries have injected-failure tests. This is not a general
power-cut recovery protocol: an interrupted initial registry setup can require
explicit inspection. No automatic boot-success/failure counter, unattended
fallback, pruning or recovery of arbitrary existing installations is provided.
The previous menu entry remains a manual GRUB recovery option.
The boot lock serializes these boot commands. Other Ports/account/System writers
must remain idle during this experiment; a shared cross-layer transaction lock
is future work. Selection rechecks compatibility facts immediately before menu
publication, but does not claim atomic coordination with unrelated writers.

## Focused owner acceptance

Stop the accepted reference VM first. As the ordinary Debian VM owner, prepare
one separate copy with `tests/prepare-kernel-boot-vm.py --image /ACCEPTED/IMAGE
--output /NEW/VM`. The helper refuses an open source disk, checks its metadata
remains unchanged while copying and attaches only the copy plus a read-only source disk.
Keep the original VM stopped during this test; both disk copies retain its UUID.

Boot the copy. Mount `LABEL=MOJT-KERNEL-LAB` read-only, verify `inventory.json`
against its files, then invoke its `source/tests/run-kernel-boot-acceptance.py`:

1. `prepare`: package the already installed payload with a distinct test-only
   native revision, retaining the actual Kernel release and original build
   provenance; install it without changing next boot.
2. `stage`, then `select`: preview, stage and prove repeat/no-selection changes;
   select next boot and prove the old exact Kernel is still running.
3. Power off/start the SAME VM copy; run `check` to verify the new exact identity,
   runtime record, read-only module source, preserved Base/System/machine ID and
   absence of failed units.
4. Run `rollback`, power off/start the same copy, then run `check-old` to verify
   the original deployment is running and both deployments remain retained.

This deliberately tests two artifacts with the same compiled Linux release.
`uname -r` remains unchanged; full artifact/deployment IDs must distinguish the
new boot and rollback. It does not claim compilation or testing of another
upstream version, general firmware/hardware/libc compatibility or publisher trust.
No repeated System account/A/B/A test or new System export is requested.

## Owner functional acceptance: 2026-10-30

Functional revision `0bf01411963c89cfa5a702d2dfc74c8c7c4bc5af` passed both CI
jobs. On a separate copy of the accepted native VM disk, the owner then confirmed:

- A distinct test-only Kernel package was installed without changing next boot.
  The actual compiled Linux release and original build provenance were retained.
- Staging generated a complete deployment, repeating it was a no-op, and the
  original next-boot selection remained unchanged.
- Selection changed next boot while the old exact artifact was still running.
  Both entries were visible in GRUB despite sharing the same Linux release.
- The newly selected deployment booted. Its exact runtime identity and read-only
  module source matched, Base/System and machine identity were retained, and no
  systemd units failed during the running-system check.
- Rollback selected the original deployment without deleting either deployment.
  After another boot, `check-old` confirmed the original exact deployment/module
  source, unchanged Base/System and machine identity, and no failed running units.

The original native package was `6.12.107-r1`, artifact
`sha256:eed451b5497d078b8de4c098539cf63a4551aa0a46864fe7550b59066fe26250`.
The test-only package was `6.12.107-r2`, artifact
`sha256:4b8d94c4396784fa8914e244d1da2bc4ee46a925770e403aef3a6584ae51c92d`.
Both run as `6.12.107-mojt1`; the test specifically demonstrates why full artifact
and deployment identities must not be inferred from `uname -r`.

No new Kernel compilation, System export, provider acquisition or account test
loop was performed. Keep the accepted reference disk and this test copy.

### Shutdown finding and accepted correction

The owner reported real shutdown failures for `/run/mojt-system`,
`/usr/lib/modules` and `/var`: each unmount helper returned status 32 with
`target is busy`. Their loaded mount units have default dependencies and are
ordered before `umount.target`. These are failures during shutdown even though
the following running-system `systemctl --failed` check is empty.

A read-only process-map inspection during runtime identified udev mappings of
`/run/mojt-system/hwdb.bin` and the selected Kernel's binary module indexes, plus
journald's shared writable mapping of the persistent journal under `/var`.
These are concrete retained references to investigate in the shutdown lifetime
ordering; runtime maps alone do not establish exactly when each is released
during the failing shutdown transaction.

The legacy shared System shutdown script performed sync, `umount -a -r`, then
another sync. Its late output reported busy devtmpfs/backing-disk mounts being
remounted read-only. That original log did not establish clean unmounting or
prove data corruption.

The correction coordinates the lifetime of udev/journald and their retained
references with early mount teardown and the final static shutdown phase.
It preserves immutable System profiles and retained initramfs/deployments,
and uses neither forced nor lazy unmounts.

The [shutdown-order correction](shutdown-order.md) now supplies a runtime mount
lifetime policy and explicit final old-root/device cleanup. The real systemd/QEMU
fixture reproduces the legacy failures and passes the corrected shutdown plus an
offline filesystem check. At functional revision
`d0aa861d7280d22409c658421d8ac59977277c95`, both CI jobs passed, followed by
the owner's focused Mojt poweroff test on 2026-10-30. The complete console output
had no failed unmount or busy/read-only fallback, reported entry into the static
exitrd and verified the old root/backing filesystem fully unmounted before
normal power down. No unrelated acceptance loops were repeated. This closes
the observed shutdown finding for the tested image; performance work remains open.

### Open verification performance finding

The owner reported slow stage/select scripts. The test runner deliberately
invokes preview, mutation and repeat/status checks. Instrumenting the tested
revision against the existing synthetic native-disk fixture found:

| Invocation | Full Kernel object checks | Base inventory passes | System closure passes |
| --- | ---: | ---: | ---: |
| Stage preview | 3 | 1 | 1 |
| Stage actual | 7 | 2 | 2 |
| Stage repeat/no-op | 4 | 1 | 1 |
| Select preview | 3 | 1 | 1 |
| Select actual | 4 | 2 | 2 |
| Status after selection | 5 | 0 | 0 |

Those calls total 26 full Kernel checks and seven complete Base/System passes
for the stage/select test sequence alone. Fixture call counts are evidence of
redundant work, not timings or an I/O measurement of the owner's real VM.

Next, add phase timings on a real retained input and remove duplicate scans
within one operation. Keep fresh integrity and compatibility checks at actual
publication boundaries, explicit full verification, corruption refusal and
selected-versus-running semantics. Do not replace them with an unvalidated
persistent cache or change the accepted test checkout midway through a boot run.
