<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Installed Kernel source acquisition acceptance

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

## Owner installed-System VM acceptance, 2026-11-06

The owner built a fresh, independent UEFI/serial VM from source revision
`386b20430e1b33a72c640700e0ea98ef69e9accc`, reusing the retained Base/System
binary inputs and the matched Debian Kernel/module set. Before acceptance the
guest reported:

- System: `system-source-kernel-test`.
- Running Kernel: `6.12.107+deb13-amd64`.
- MPM: `/run/mojt-system/bin/mpm`.
- No failed units at the initial boot check.

The real input was the previously accepted native package
`kernel-linux-6.12.107-r1-x86_64-linux-eed451b5497d.tar.zst`, copied into the
VM's persistent test-input directory. No new Kernel compilation was required.
The owner ran the pinned `run-kernel-source-acceptance.py` with the selected
System Python and reported:

```text
PASS: installed System MPM joined named source, cache and exact Kernel installation
PASS: retained source provenance, archive and module tree verified; repeat was a no-op
PASS: running Kernel, machine identity, Base/System and existing boot records unchanged
No boot selection or reboot performed. Lab retained: /var/lib/mojt/kernel-source-acceptance.dr52vial
```

This accepts the installed command join, real acquisition/installation, retained
origin/tree verification and no-op behavior after the fixture archive was removed.
The result JSON is retained in that guest lab as `result.json`. No source/snapshot
or verification IDs have been inferred from the log. It does not accept remote
publisher authentication, dependency acquisition, Kernel boot compatibility,
selection or a restart into this installed package. No additional A/B matrix or
physical-hardware result is claimed.
