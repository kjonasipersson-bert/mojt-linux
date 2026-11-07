<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Owner acceptance: changed Base, retained System/Kernel, return

Owner-run changed-Base boot and return passed on 2026-11-07 at source
`f9d70ec5400429086aaa10bd85109b2dede095a4`. The procedure below remains the
focused reproduction recipe; the recorded result and limits follow at the end.
Use one new disposable native VM; previous VM disks and the Debian root disk
must not be attached. No repeated component cross-product matrix is requested.

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
Kernel registry preparation uses the common protected-ancestry policy. An owned
private home may contain inaccessible group-writable lab directories; a private
child never excuses a writable ancestor above that boundary, and the registry
itself must remain protected. No chmod of the owner's existing directories is
needed. This path is checked before packaging inputs. If a preparation fails,
retain its partial directory and choose a new output when retrying.

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


## Account-shell regression found in owner staging

An owner test at f27c4804 installed its distinct Base, then correctly left next
boot unchanged when preflight incorrectly treated a System-closure nologin path
as Base content. The check is corrected to verify exact retained System provider
ownership/content instead. Test fixtures now include provider-backed service
accounts throughout staging/selection/return, not only a root Base shell.

This changes management code delivered in immutable System. Re-exporting the
Nix payload is unnecessary, but a fresh native test image must assemble the fixed
management files. Retain the previous stopped image/checkpoint; do not hot-patch
its System, rewrite passwd or weaken the gate to continue. Start the focused
acceptance from the fixed fresh baseline. No changed-Base boot result is claimed
for the stopped attempt.


## Recorded owner acceptance: 2026-11-07

The owner completed the following through the installed System MPM on a fresh
private native VM. These are owner-reported VM results, not execution on the
owner's host by the assistant.

| Input or observation | Recorded value/result |
| --- | --- |
| Source | `f9d70ec5400429086aaa10bd85109b2dede095a4` |
| Retained image | `/home/jonasp/mojt-lab/mpm-nix-home/mojt-base-deployment.k3eJaO/vm-shell-fixed/image` |
| Image build UTC | `2026-11-07T09:30:15Z` |
| Original Base | `0.1.3`, `sha256:4718c046420a2901ed8fd6bc52cac012de1bcfab8e47c15431eaa4b015e9f6f3` |
| Test Base | `0.1.3-boot-test`, `sha256:1bff295d5bad99506ec90e3e8268fd17cab206f6f6201a85e41ee75bfe583b2e` |
| System | Exact selected `system-base-boot-test` manifest retained through boot and return |
| Kernel | `6.12.107-mojt1`, exact artifact `sha256:eed451b5497d078b8de4c098539cf63a4551aa0a46864fe7550b59066fe26250` retained |
| Install | Distinct Base installed; original Base/System/Kernel and next boot retained |
| Stage/repeat | Changed Base staged; next boot unchanged; repeat was a no-op |
| Candidate boot | Exact new deployment running; actual Base root read-only; selected/running IDs agree |
| State | Machine/account data, persistent markers and the saved Ports baseline retained |
| Modules/services | Exact native modules read-only; no failed units on either checked boot |
| Return | Previous exact deployment and Base 0.1.3 restored; all final acceptance PASS lines reported |

Exact deployment IDs and account-file digests remain in the private guest
checkpoint `/var/lib/mojt/base-boot-acceptance/state.json`; they were not copied
into this public report. The Ports assertion compares the saved baseline and is
not a separate claim that a real Ports package was installed or upgraded here.
The new Base deliberately retains libc; this is no proof of changed-libc ABI
compatibility. Shutdown console/full-unmount lines were not included in the
reported result, so no additional shutdown-specific observation is recorded.

This closes this bounded Base-only owner acceptance gate. It does not complete
System composition/install/upgrade, missing-default or general lifecycle actions,
moving Base requests/upgrades, bootstrap/MBT, the generalized v2 deployment
protocol, the final joined distribution journey or physical hardware acceptance.
Retain the successful VM and its checkpoint. No further manual repetition of this
component matrix is required before the next integration change.
