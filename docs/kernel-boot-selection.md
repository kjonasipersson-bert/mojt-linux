<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Existing native-disk Kernel staging and next-boot selection

This experimental frontend follows the accepted fresh native image
builder. It targets that builder's x86_64 serial UEFI/VirtIO layout, initially
with one explicit native boot pair. It rejects customized/unknown boot menus.
Native-v2 uses the [shared preparation/selection path](system-transition.md).
The format-specific interface below remains a separate low-level reference.

Building, packaging, installing, staging and selecting remain separate actions.
`kernel install` retains an artifact in the disk's independent Kernel registry.
`kernel stage` generates a deployment-specific initramfs and publishes a complete
new boot slot, without changing the running or next-boot selection. `select`
changes only next boot; `rollback` selects the previously selected deployment.
No command invokes Nix, downloads content, compiles a Kernel, changes Base libc,
updates the selected System userspace or changes Ports wishes.

## Explicit commands

Use the source checkout's `tools/mpm` or the [common frontend delivered in new
System assemblies](mpm-system-runtime.md). Retained step-10 images are not
modified in place. Installed commands default to the mounted installation;
the source examples below use explicit targets. Boot commands use `--disk-root`, not the
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
The [shared transaction rules](mpm-transactions.md) coordinate boot commands with
the existing Base, Kernel registry and Ports locks. All four resources stay locked
through final checks and publication. External account/System writers, manual
root edits and older boot publishers must still remain idle. This is not atomic
coordination with arbitrary machine-state changes.

## Verification cost and regression scope

Boot publication is a production integrity boundary, not a development test.
Normal commands must keep these checks regardless of CI configuration:

- **Stage**: validate the installed Kernel and the selected Base/System before
  building; recheck the candidate archive and selected deployment/installation
  immediately before publishing the complete immutable boot slot.
- **Select/rollback**: validate the selected and candidate deployments and
  compatibility on preview; recheck both boot entries, selected Base/System,
  compatibility and the unchanged menu immediately before atomic replacement.
- **Status**: report metadata and current exact identities, not a claim that
  every immutable Base/System file was freshly audited. Use explicit full
  verification when that stronger guarantee is required.

Within a single invocation, already inspected menu entries are reused when
enumerating staged slots. This is an in-memory operation-local reuse, **not** a
persistent integrity cache. Each publication still has an independent late
integrity gate; corruption detected there must stop publication.

The regression workflow distinguishes three occasions:

1. **Draft / intermediate commits**: syntax, focused Kernel integrity/
   publication tests, shared locks, Base/Ports publication regressions and
   shutdown contracts; no repeated full hardware boot matrix.
2. **Ready-for-review PRs and pushes to main**: existing full regression
   suites, real image/boot tests and the hardware shutdown fixture.
3. **Manual workflow dispatch**: run the same full regression jobs when needed
   before a high-risk change or release.

Keep tests for distinct failure modes, but avoid adding an end-to-end VM boot
for each internal helper. When a bug becomes a regression, first extend the
smallest applicable test; retain real boot tests for cross-component behavior
that cannot be demonstrated by a unit/integration fixture. Test-count and
call-count observations are not measured wall-clock performance on a target
machine. Do not weaken release or installation verification to make CI faster.
