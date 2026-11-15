<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Reusable initramfs construction test results

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

## Validation and remaining gates

Focused tests cover Base/System-independent keys, dependency invalidation,
corrupt-cache refusal, durable publication failure behavior, exact fresh bindings
and real two-member archive bytes. A warm constructor test refuses any second
runtime clone or heavy payload build. A small real-Kernel QEMU probe boots two
different overlays over the same cached payload; full native-v2 constructor,
reader, handover, selection and bootstrap regressions remain separate checks.
The minimal probe is not full System, firmware or storage-driver acceptance.

The [E/F owner acceptance](../initramfs-payload-hardware-test.md#recorded-owner-acceptance--2026-11-1415)
passed on 2026-11-14–15: F installation took 11.483 s wall / 4.996 s CPU,
cold preparation 286.737 s / 276.351 s, and warm preparation approximately
229 s / 219 s. The warm helper PASS checks reuse of the exact cold payload key
for a newly prepared F deployment. Candidate checks (about 45 s) are included in
the preparation totals. The owner reported activation at 4.2 s, then successful
F boot and `after` PASS, including Ports/Neovim and preserved Base/Kernel.
This closes the focused physical two-member boot/reuse gate, with about 20%
less total preparation time in this one comparison. Preparation still takes
nearly four minutes; performance remains open and remaining phase costs have
not been individually measured. Optional E return was not reported.
The previous C/D acceptance covers the earlier monolithic constructor.
Future ordinary install/preparation integration must reuse this path and preserve
the accepted fast atomic choice, explicit requirements and independent lifecycles.
