<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Activation and preparation performance measurements

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

The owner found both original test installation and first activation
unacceptably slow, with substantial fan activity. That first activation used the
old running MPM. The original #54 change only reduced selection audit passes
from two to one and did not meet the required fast activation boundary.
The focused owner result below records installation/preparation timing and
qualitative activation acceptance for the replacement.
The [successor hardware test](../activation-fast-hardware-test.md) delivers the new
manager as C and measures D through its public installed MPM. Original A/B
checkpoints stay separate. The earlier [A/B delivery](../activation-hardware-test.md)
remains pinned to the old implementation.


## Owner result — 2026-11-14

The [C/D acceptance record](../activation-fast-hardware-test.md#recorded-owner-acceptance--2026-11-14)
records D installation at **11.595 s wall / 6.095 s CPU** and preparation at
**275.823 s wall / 265.932 s CPU**. Candidate checks took 43.16 s within that
preparation total. These are actual console measurements from the owner's SSD,
not timings of the isolated development environment or the old bootstrap.

The owner confirmed invalid-input/cancellation behavior, selected D using public
`mpm system activate`, reported C running/D selected, then confirmed successful
D boot/after-check and working Ports. Activation felt fast but not immediate;
the owner explicitly accepted it as sufficient for now. Its elapsed time is
**unmeasured**, because direct activation bypassed the helper's timing/logging.
No repeated activation is required to close this bounded acceptance gate.

Preparation remains the known performance issue. Investigate its repeated
retained-content/provider scans and construction separately; keep its cost
visible rather than adding it back to ordinary activation. The proposals for
writable-root layout, kernel building, firmware and MBT remain distinct work.


## Reusable construction and owner result — 2026-11-14–15

The [reusable initramfs payload](../reusable-initramfs.md) separates runtime/drivers
from the small exact-deployment member. Base/System identity changes alone no
longer require rebuilding that large member. A warm update reuses its compressed
bytes and skips runtime freezing/copying, module decoding and large-payload
compression. Existing preparation/admission integrity checks still run.

The [E/F owner acceptance](../initramfs-payload-hardware-test.md#recorded-owner-acceptance--2026-11-1415)
records F installation without `--verify` at 11.483 s wall / 4.996 s CPU,
cold preparation at 286.737 s / 276.351 s, and warm preparation at approximately
229 s / 219 s. Candidate checks were about 45 s within each preparation total.
Warm preparation passed the helper's exact payload-key reuse check. The owner
reported activation at 4.2 s elapsed, then successful F reboot and `after` PASS
with original Base/Kernel and working Ports/Neovim. Activation CPU time and
optional return were not reported. Measurements come from photographs/reports;
the SSD evidence bundle was not imported.

This closes the bounded physical reuse/boot gate. In this one run, warm total
preparation was about 58 s (20%) shorter than cold preparation, with different
System generations. It is not an isolated payload benchmark. Roughly four
minutes remains unacceptable; remove repeated broad content audits from ordinary
preparation while preserving required metadata, compatibility, safe construction
and atomic publication checks. The current measurements do not attribute every
remaining second to those audits. The subsequent
[owner phase profile](../stage-profiling.md#owner-phase-profile--2026-11-15)
measured 233.777 s total: 759 Nix commands used 99.074 s, including 253 full
`--verify-path` calls at 85.721 s. File hashing alone used another 33.238 s over
52,487 calls. The planner ran five times and some identical tree scans recur;
the payload cache itself took 0.455 s. These results prioritize repeated provider
and retained-content checks before further payload construction work. The Nix
breakdown is included in its subtotal; inclusive phase durations must not be
added to their own-time entries. The profiling diagnostic itself changes no
audit policy. The subsequent [ordinary stage implementation](../stage-fast-path.md)
makes full content audits explicit and reuses unchanged metadata within each
call, while retaining current-state and publication checks. The subsequent
[private-code SSD test](../stage-fast-hardware-test.md#recorded-owner-result--2026-11-15)
measured 134.812 s cold and 66.369 s warm, with no `--verify-path` calls: warm
elapsed time fell 71.6% from 233.777 s. Warm payload reuse took 0.285 s; remaining
own costs include 13.197 s of Nix metadata queries and 10.767 s of link checks.
Both metadata query types still ran 253 times; the cause of missed reuse is not
established by this summary. This tests private code and unchanged boot choice,
not new installed tooling or another physical boot. Automatic preparation inside
normal live System installation was integrated subsequently; see
[the usability acceptance](../mpm-usability-hardware-test.md). Historical timings here
measure the separately invoked operations, not the joined installation command.

The [final Nix query-cache measurement](../stage-fast-hardware-test.md#final-nix-query-cache-measurement--2026-11-15)
then measured 110.759 s cold and 55.171 s warm (54.713 s warm CPU), with 36
queries of each type: 72 Nix commands in 1.887 s instead of 506 in 13.197 s.
Warm stage is a further 16.9% shorter, or 76.4% shorter than the original
233.777 s profile. Both MPM calls exited 0 and the delivery guards exact payload
reuse, unchanged running/menu state and zero `--verify-path` calls. These remain
private-code preparation measurements. The owner's performance increment is
complete; further tuning is deferred in favor of the roadmap.
