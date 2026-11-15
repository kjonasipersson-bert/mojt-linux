<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Reusable early-boot payload and exact deployment metadata

This is the first implementation increment after the accepted Base/System
composability and ordinary install/choose/reboot direction. It reduces repeated
construction without weakening the existing preparation/admission checks. Normal
installation still needs its separate preparation integration; the ordinary
user should ultimately not need a manual `stage` command. See [MPM](mpm.md).

## Two standard archive members

Prepared native-v2 initramfs files now concatenate two independently generated
and inspected gzip/newc members:

1. A reusable payload: static BusyBox/applets, early Kernel modules, shutdown
   helper and the explicitly retained bootstrap Python/runtime closure.
2. A small deployment member: `/init`, the manager-owned boot code and the exact
   inputs, tree proof, runtime descriptor and handover metadata under `/mojt`.

Linux supports concatenated compressed CPIO archives; the later member supplies
the final `/init`. This uses the documented
[Linux 6.12 initramfs buffer format](https://www.kernel.org/doc/html/v6.12/driver-api/early-userspace/buffer-format.html).
The reusable member contains a rescue-only placeholder `/init`; it cannot become
an admitted System deployment by itself.

The bootloader still loads one `initramfs.cpio.gz` file. The existing v2
inputs/binding/deployment/ready/selection formats remain unchanged: each final
file has its own complete SHA256, size and exact deployment binding. A new
System or Base choice gets fresh metadata and a distinct deployment even when
the large first member is reused byte-for-byte. No current selection, running
System or persistent configuration is changed by preparation.

## Actual rebuild inputs

| Input change | Rebuild reusable payload? |
| --- | --- |
| Selected Base identity/version | No, if actual compatibility requirements still pass |
| Selected System identity/version | No, by itself |
| Root UUID, normal boot arguments or unrelated MPM CLI code | No; fresh deployment member carries the current values/code |
| Exact Kernel build/module identity | Yes |
| Bootstrap Python/runtime measurement | Yes |
| Static BusyBox | Yes |
| Early driver profile or required applet set | Yes |
| Shutdown helper or payload generator/format implementation | Yes |

The payload key includes platform, exact Kernel facts, runtime measurement,
BusyBox hash, boot profile, handover mode, applets, shutdown content and the
implementation hashes that generate the large member. It deliberately excludes
Base/System selections and per-deployment root UUID. Kernel replacement is an
important rebuild trigger, rather than the sole possible trigger.

On a warm live update, the constructor skips freezing/cloning the runtime,
decoding the early modules, creating the large initramfs tree and compressing
that payload. It still generates the small member and final exact binding.
The existing runtime description, preflight, retained-input audits, source-tree
proofs, slot retention and final admission checks remain. The bounded owner
measurement below does not establish a fixed speedup. Separating optional
integrity scrubs from ordinary preparation remains subsequent work.

## Private content cache

The reusable member is retained under
`boot/mpm/initramfs-payloads/INPUTS_HEX/`, containing `payload.json` and
`initramfs.cpio.gz`. Its private inputs/receipt formats are
`mojt-initramfs-payload-inputs-v1` and `mojt-initramfs-payload-v1`.
This cache is not a second boot-choice authority or executable approval record.

Root ownership, protected ancestors, regular files, canonical metadata, exact
input matching, size and compressed-byte hash are checked on reuse. SHA256 is
integrity evidence, not publisher authentication. A cache-local lock coordinates
writers while existing store read locks protect inputs. New entries are sealed,
fsynced and atomically published. Corrupt entries fail explicitly; existing
entries are never silently replaced. Pre-rename failures preserve the previous
boot choice, and uncertain post-rename flush failures retain possibly committed
cache content. Reuse can complete its durability flushes on retry.

There are at most 128 completed payloads per installation. Automatic cache GC is
not implemented. Abandoned temporary entries are not candidates for reuse.
Both members are individually inspected when generated; the combined compressed
and expanded sizes retain the existing 256 MiB limits. Reuse hashes the cached
compressed bytes without decompressing or recompressing the large member.

`stage --json` reports `initramfs_payload.inputs` and
`initramfs_payload.reused`; stderr also reports whether the runtime/drivers were
built or reused. Selecting an already prepared deployment stays a fast metadata
operation. Pure constructor callers can retain the previous monolithic mode;
MPM/MBT's staged handover path uses the reusable payload.

## Validation and remaining gates

Focused tests cover Base/System-independent keys, dependency invalidation,
corrupt-cache refusal, durable publication failure behavior, exact fresh bindings
and real two-member archive bytes. A warm constructor test refuses any second
runtime clone or heavy payload build. A small real-Kernel QEMU probe boots two
different overlays over the same cached payload; full native-v2 constructor,
reader, handover, selection and bootstrap regressions remain separate checks.
The minimal probe is not full System, firmware or storage-driver acceptance.

The [E/F owner acceptance](initramfs-payload-hardware-test.md#recorded-owner-acceptance--2026-11-1415)
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
