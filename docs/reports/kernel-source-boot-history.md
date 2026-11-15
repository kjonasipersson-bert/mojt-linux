<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Source-installed Kernel boot acceptance

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

**Owner reboot acceptance passed on 2026-11-06**, using source revision
`0dd0b40` and the delivered System `system-source-kernel-boot`:

- Baseline: Kernel `6.12.107-mojt1`, artifact
  `sha256:eed451b5497d078b8de4c098539cf63a4551aa0a46864fe7550b59066fe26250`,
  with no failed units.
- Source-installed candidate:
  `sha256:4f0598d7b6d66e5992c0ff22f94a15509588bd8afedba602c89d18a6bf36f88a`.
  Its source origin was retained, repeat installation was unchanged and initial
  boot selection remained intact.
- Staging was repeatable without changing next boot. Selection changed next
  boot while leaving the running deployment unchanged.
- After one owner poweroff/restart of the same test VM, exact deployment
  `sha256:e59efe04e41103eea82a18b19c8c6616659ee449abe6c60a9928e7d6c8dd7612`
  was running. The installed origin/record, correct read-only modules,
  Base/System and machine identity were retained; selected/running IDs agreed
  and no units failed.

The extra test-input disk was attached read-only. Its ext4 message about skipping
orphan cleanup because write access was unavailable did not prevent mounting or
reading the test scripts. No write-enabling workaround is needed for this fixture.
The successful #38 installation test remains valid for its original scope. This
bounded gate adds real boot evidence; it does not assert a new Kernel compilation,
a different upstream version, Base/System upgrade, or physical-hardware acceptance.

Host-preparation tests exercise refusal of existing/overlapping or symlinked
output paths, the narrow test context, refusal of an unexpected launcher and the
actual generated QEMU argument list (including a path containing spaces). A fake
QEMU executable records those arguments; this is not a VM boot test.
