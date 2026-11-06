<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Owner acceptance: changed Base, retained System/Kernel, return

Prepared owner test, not a claimed VM result. Use one new disposable native VM;
previous VM disks and the Debian root disk must not be attached. No hardware or
large cross-product matrix is requested. Existing image/Kernel tests are not
repeated manually.

## Debian preparation

Use one reviewed/pinned source checkout containing this increment. The previously
exported step-10 System payload lacks the retained GNU tar role, so first prepare
a fresh step-10 payload with the same established Nix input workflow into a new
output directory. Do not overwrite the retained payload or any reference VM.
This is test setup; Base-only selection inside the VM subsequently retains that
exact assembled System throughout the test.

Inventory the retained Base **release directory** (manifest.toml plus
rootfs.tar.zst), own-built native Kernel package and fresh System payload. Run
from the ordinary Debian user's interactive terminal, not a heredoc or pipeline:

```
python3 -I -B SOURCE/tests/prepare-base-boot.py \
  --base-release BASE_RELEASE_DIRECTORY \
  --kernel-package EXACT_KERNEL_ARCHIVE \
  --expected-kernel sha256:FULL_KERNEL_ARTIFACT_ID \
  --system-payload FRESH_SYSTEM_PAYLOAD \
  --output NEW_DISPOSABLE_TEST_DIRECTORY
```

Paths above are placeholders to replace after inspecting actual retained inputs.
Preparation reuses the existing reviewed host helper's native-image pipeline,
private host Kernel registry, fresh-output guards and isolated QEMU launcher. It
packages the unchanged release, installs the exact Kernel into a private host
registry, writes narrowly scoped test bounds, previews, then assembles the new
image with sudo and an interactive new guest root password. It also creates a
separate read-only test-input disk and records source revision/script hashes.
Only that new VM image and the test disk are attached. No install or boot choice
is made on Debian or an older VM. Its `READY` launcher is the one to start.

## Guest preparation and selection

Log in as root. Mount the read-only input disk and copy the reviewed runner to
persistent /var so subsequent boots do not need it remounted. For this prepared
VirtIO launcher, vda is the VM disk and vdb the separate input disk. Check lsblk
before mounting; do not substitute another device by guessing.

```
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINTS
mkdir -p /run/base-test-inputs
mount -o ro /dev/vdb /run/base-test-inputs
python3 -I -B - <<'PY'
import hashlib, json
from pathlib import Path
root = Path('/run/base-test-inputs')
expected = json.loads((root / 'inventory.json').read_text())
source = root / 'tests/run-base-boot-acceptance.py'
assert hashlib.sha256(source.read_bytes()).hexdigest() == expected['tests/run-base-boot-acceptance.py']
target = Path('/var/lib/mojt/run-base-boot-acceptance.py')
assert not target.exists()
target.write_bytes(source.read_bytes())
print('PASS: transferred acceptance script matches the prepared input inventory')
PY
```

The inventory is transfer-integrity evidence from the reviewed preparation, not
release authentication. The installed `/run/mojt-system/bin/mpm` and its delivered
Python runtime perform the actual installation, staging and selection. The runner
does not invoke a checkout MPM.

```
python3 -I -B /var/lib/mojt/run-base-boot-acceptance.py prepare
python3 -I -B /var/lib/mojt/run-base-boot-acceptance.py stage
python3 -I -B /var/lib/mojt/run-base-boot-acceptance.py select
```

Preparation makes a new, explicitly acceptance-only Base release in private /var.
It copies the verified current Base preserving Unix metadata, changes only its
release identity and adds an immutable content marker. Original Base, libc,
System, Kernel and their records remain unchanged. Its original ABI is retained;
Kernel bounds are deliberately the one already accepted upstream Kernel version,
not a broad supported release policy. The generated fixture is not a published
Mojt release. An existing lab is not overwritten; inspect its checkpoint after a
failure. The runner writes unique /etc,/var,/home,/root markers and records
account/machine/timezone file digests and the current Ports profile (including
hello's executable path if present). It does not install Ports or fetch packages;
absence of a Ports profile is recorded honestly, not counted as package retention.

Staging preview writes no slots; staging/repeat leaves next boot unchanged.
Selection verifies next-boot versus still-running identity separately. Wait for
its READY, then power off cleanly and restart the **same prepared launcher/disk**:

```
systemctl poweroff
```

Choose the default new deployment. After login:

```
python3 -I -B /var/lib/mojt/run-base-boot-acceptance.py check
```

This must confirm exact selected/running IDs, the new release and content marker,
the actual slot-root mount read-only, unchanged exact System/Kernel, read-only
native modules, persistent markers/identities/accounts/Ports baseline and no failed
units. Paste failure output rather than retrying with changed inputs.

## Return

Only after the candidate check passes:

```
python3 -I -B /var/lib/mojt/run-base-boot-acceptance.py rollback
systemctl poweroff
```

Restart the same launcher. After login:

```
python3 -I -B /var/lib/mojt/run-base-boot-acceptance.py check-old
```

The previous exact deployment and original Base must be running, the test-only
immutable marker absent, and state/System/Kernel still retained. Both slots remain
available. Also retain the shutdown console result, especially the static exitrd's
full-unmount line. No automatic fallback, arbitrary migrations, signed release
trust, full generalized v2 protocol or physical hardware acceptance is claimed.
