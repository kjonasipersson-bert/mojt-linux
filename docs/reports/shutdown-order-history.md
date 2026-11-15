<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Static shutdown and final unmount acceptance

Historical test record from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
The fixtures and observations below are not the current command contract.

## Owner shutdown acceptance: 2026-10-30

At functional revision `d0aa861d7280d22409c658421d8ac59977277c95`,
both CI jobs passed. The owner then supplied the complete poweroff console
output from the focused Mojt image test. Ordinary sessions, user manager,
network services, login sessions and D-Bus stopped before final shutdown.
The transient privileged and temporary mounts unmounted normally.

The console contained no failed unmount, busy/read-only fallback or cleanup
error. After reaching the system poweroff target, it reported:

```text
Mojt shutdown: entered static exitrd
Mojt shutdown: old root and backing filesystem fully unmounted
reboot: Power down
```

This closes the observed shutdown-order finding for the tested Mojt image.
The result establishes the script's mount-table verification and normal poweroff;
it is not an owner-run offline filesystem check, power-cut test or general
hardware/libc compatibility proof. The separate automated fixture includes its
own successful offline ext4 check.

No full install/stage/select/rollback or account loop was repeated.
Verification-performance work remains separate and unchanged.
