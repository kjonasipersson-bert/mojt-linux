<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native handover boot and writable-root acceptance

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

## Acceptance and self-hosting

Focused CI reuses the actual-archive chroot test for exact reader and System
state gates, including refusal of a changed layout. One additional root case
checks Base-copy reuse, unchanged menu/state and reverse cleanup after an injected
late mount failure. Mount/exec calls are injected; these CI cases alone are not
real System boot or shutdown evidence. The admitted v2 selection/status join
subsequently passed [owner A/B/A boot/return and clean shutdown](../system-boot-acceptance.md#owner-acceptance-2026-11-09)
on 2026-11-09, preserving exact Base/Kernel and persistent state. Public active-v2
staging and request integration remain.

The new writable-root increment has separate [G/H/G hardware instructions and owner acceptance](../writable-root-hardware-test.md#recorded-owner-acceptance--2026-11-15).
The owner reported every step PASS on 2026-11-15 with delivery `d3bd849f`,
covering physical G/H/G boot and return, persistent root/local state, cleared
temporary files, read-only release mounts and working Ports. The collaborator
did not run tests on the owner's machine or import its full evidence/shutdown
transcript; no different-Base/Kernel matrix or old-F recovery boot is claimed.

MBT must subsequently reuse these installation/handover APIs for bootstrap and
the existing build environment, Kernel build and native packaging. The destination
is **M2 native self-hosting**: Mojt builds Base and Mojt-owned System components
from pinned sources/recipes and installs/boots them. M1 joined administration is
the prerequisite. Importing tools or assembling prebuilt Base/System images alone
does not establish M2. Full third-party source coverage is the separate M3 gate.
