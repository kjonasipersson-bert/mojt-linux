<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Source-installed Kernel through native image, staging and boot

Bounded follow-up to the [accepted source-install workflow](kernel-source-install.md).
The existing six-step consolidation order remains authoritative. This closes
origin-retention gaps and prepares one owner reboot acceptance; it does not add
a new installer, resolver, MBT syntax or build policy.

## Preserve origin while assembling a fresh image

The native image builder previously reimported the input archive as an explicit
local file. For a source-installed Kernel this lost the registered source/cache
observation. It now freezes the expected complete installation record from
preview, forwards its acquisition evidence to the existing Kernel installer and
checks that copied artifact, raw encoding, trust and acquisition origin match.
It rechecks the input record after copying. A changed record or lost origin
prevents publishing the new image. Source installation files are not rewritten.

The destination has its own installation UID/time, as expected for a new image;
the original source/cache observation is retained exactly. This does not register
the input machine's source configuration or trust policy on the new machine.
An origin observation describes how the bytes were obtained, not live authority
to fetch more content. Artifact identity and Kernel release remain unchanged.

## Versioned boot input evidence

Fresh image and staged input receipts use `mojt-native-image-inputs-v2`.
Their Kernel fields are:

| Field | Meaning |
| --- | --- |
| `kernel_artifact` | Exact Kernel for this deployment |
| `kernel_installation_digest` | Digest of this disk's complete installed Kernel record |
| `kernel_acquisition` | Retained source/cache origin, or null for explicit local-file input |
| `source_kernel_installation_digest` | Original input installation digest; fresh-image bootstrap only |

Fresh-image copying checks the destination record through assembly. Existing-disk
staging records the candidate's installation/origin, rather than inheriting the
previous Kernel's fields. It checks the candidate record again before publishing
the slot. Deployment inspection verifies that the receipt matches the installed
record as well as the Kernel's image/module identity and bound initramfs.

This is a deliberate receipt-version change. New boot management rejects v1 input
receipts rather than inventing their missing origin binding. The next test uses a
fresh native image; no migration of experimental disks is provided. The boot
deployment/content identity and selection format themselves are unchanged:
transport observations do not become a new Kernel artifact or boot policy.

System assembly also creates a protected `/var/lib/mojt` state parent for MPM on
a fresh image. It rejects symlinked/unprotected parents instead of depending on
acceptance input files to create that directory incidentally.

## Narrow VM acceptance

The latest installation-only VM uses a standalone registry and boot pair. This
test needs a separate fresh native image with exact Base/System/Kernel bindings
and the new delivered System runtime. Reuse the already built Kernel, Base release
and exported System payload; do not compile another Kernel for this gate.
Keep other VM disks detached.

### Debian-host preparation

Run `tests/prepare-kernel-source-boot.py` as the ordinary Debian user from the
pinned source checkout, directly in an interactive terminal. Do not pipe it or
wrap it in a shell heredoc: image assembly prompts for the new guest root password.
The helper checks host tools/input paths, uses the existing Base packer and
Kernel installer, previews the native image and invokes the same image builder
with sudo. It prints progress before expensive package/image verification.

```sh
python3 -I -B /CHECKOUT/tests/prepare-kernel-source-boot.py \
  --output /NEW/TEST \
  --base-release /RETAINED/base-0.1.3-x86_64 \
  --kernel-package /RETAINED/kernel-package.tar.zst \
  --expected-kernel sha256:EXACT_KERNEL_ID \
  --system-payload /RETAINED/system-step10 \
  --path-file /HOME/mojt-source-boot-test-path
```

The output must not exist and must be separate from every input. This wraps the
retained Base release without modifying it and creates a private host Kernel
registry. The test-local Base context admits only this already accepted upstream
Kernel version; it is not published compatibility policy for future versions.
The exported System payload is reused, while System assembly delivers MPM from
the pinned checkout. No old VM disk is attached or converted.

The helper produces `run-qemu.sh` alongside `image/` and a separate 32 MiB ext4
disk containing the pinned acceptance scripts plus their checksum inventory.
Its wrapper attaches the new VM disk first and the test-input disk second with
`readonly=on`. The original image launcher is unchanged. Start the wrapper
reported by `READY` rather than `image/run-qemu.sh`:

```sh
bash "$(cat /HOME/mojt-source-boot-test-path)/run-qemu.sh"
```

After logging in as root, inspect System version, `uname -r`, the native Kernel
artifact and failed units. Expect `system-source-kernel-boot`, the previously
compiled Kernel release and its exact input artifact ID, with no failed units.
Mount the extra test disk in this disposable guest before each test session:

```sh
mkdir -p /run/source-boot-inputs
mount -o ro /dev/vdb /run/source-boot-inputs
```

The script paths below can then use `/run/source-boot-inputs` in place of `/TEST`.
After the deliberate restart, mount the input disk again before `check`; the
checkpoint remains under persistent `/var`. The input script checksums and source
revision are also recorded in host-side `preparation.json`. These local checks
provide integrity/traceability of owner-selected test inputs, not release signing.

### Guest phases

`tests/run-kernel-source-boot.py` uses the selected System's installed MPM commands.
Place it beside `run-kernel-source-acceptance.py` in the disposable guest. It has
explicit phases, recorded under `/var/lib/mojt/kernel-source-boot/state.json`:

1. `prepare`: verify native selected/running baseline agreement, package a distinct
   revision from its retained Kernel tree and original build provenance, register
   an owner-trusted local source, preview/install it and save its origin record.
   The source archive is removed afterward to prove staging uses installed data.
2. `stage`: run preview, stage and repeat; retain the exact bound deployment and
   check that staging leaves next boot unchanged.
3. `select`: select with the expected-current guard, then prove the running exact
   deployment and boot ID are still the baseline. Stop for one owner restart.
4. `check`: after restarting the SAME disposable VM, require the new runtime
   artifact and deployment IDs, the correct read-only native module tree,
   unchanged installed origin/record, Base/System and machine identity, both
   retained deployments and no failed units.

For example, run each phase deliberately inside the native guest:

```sh
/run/mojt-system/bin/python3 -I -B /TEST/tests/run-kernel-source-boot.py prepare
/run/mojt-system/bin/python3 -I -B /TEST/tests/run-kernel-source-boot.py stage
/run/mojt-system/bin/python3 -I -B /TEST/tests/run-kernel-source-boot.py select
# Owner: systemctl poweroff, start the SAME disposable image again.
/run/mojt-system/bin/python3 -I -B /TEST/tests/run-kernel-source-boot.py check
```

The runner prints phase progress and preserves its checkpoint/data on failure.
It refuses an existing preparation lab and requires the same script checksum in
later phases. Selection never reboots automatically. Optional `rollback` and
`check-old` phases support explicit recovery; they are not a required repeat A/B
matrix for this bounded gate.

The revision-only candidate intentionally uses the same compiled `kernel_release`.
Success therefore requires exact runtime artifact/deployment IDs and module-tree
bindings, not `uname` matching. This proves the source-to-boot join; it does not
claim a new compiler build, a different upstream Kernel version or hardware support.

## Validation status

Real package tests cover source-origin preservation and refusal of changed/lost
evidence while freezing a private image registry. System assembly tests cover the
fresh state parent and external symlink refusal. Root/real-cpio integration tests
exercise full image assembly from a source-installed input and source install
through stage/select after removing source/archive availability. Those tests use
synthetic guest executables/disk output; they are not real boot acceptance.

**Owner reboot acceptance is pending.** The successful #38 installation test
remains valid evidence for its original scope. One forward reboot in this separate
native image is the next owner gate after CI; an additional hardware or full
Base/System/Kernel cross-product is not requested here.

Host-preparation tests exercise refusal of existing/overlapping or symlinked
output paths, the narrow test context, refusal of an unexpected launcher and the
actual generated QEMU argument list (including a path containing spaces). A fake
QEMU executable records those arguments; this is not a VM boot test.
