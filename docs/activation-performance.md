<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Activation performance and installed choices

The 2026-11-14 owner decision separates preparation from choosing next boot.
Normal activation must only select a completed entry. Normal System installation
must perform the required import/materialization work, without integrity scrubs.
Full content verification is explicit through `--verify`.

## Operation boundaries

| Command | Normal work | Explicit verification |
| --- | --- | --- |
| `mpm system install` | Freeze/copy and safely unpack each new archive once; compose one profile; retain provider binaries; atomically publish completed objects/profile | `--verify` hashes payloads and audits reused objects, profile content and provider closures |
| `mpm {base,system,kernel} stage --artifact ID` | Prepare and admit a complete boot deployment without selecting it | Existing constructor/admission verification remains part of preparation |
| `mpm {base,system,kernel} activate --artifact ID` | Find an admitted entry for the artifact and preserved other areas; atomically choose next boot | `--verify` audits retained boot entries before selection |
| `mpm {base,system,kernel} select` / `rollback` | Choose an admitted deployment or the previous entry | `--verify` audits retained boot entries before selection |
| `mpm {base,system,kernel} upgrade --artifact ID` | Prepare an explicit installed update, then choose it | Preparation still includes its constructor/admission checks |

Activation never constructs an initramfs, imports providers, scans installed
payloads, runs Nix or repeats startup preflight. A missing prepared entry is an
error directing the user to `stage`. Ambiguous prepared deployments require an
exact `select --deployment` choice; labels never identify content. A repeat of
the current choice makes no selection change.

Selection keeps inexpensive metadata checks: installation and receipt bindings,
slot/boot-file existence, sizes and protected paths, area preservation, exact
expected selection and menu consistency. The writer locks, rereads the baseline,
fsyncs a temporary complete menu and atomically replaces the one authoritative
boot menu. There is no separate mutable selection database. Failures before
rename preserve the old menu; post-rename flush errors report uncertainty and
retain the possibly committed choice. Running services and persistent state do
not change. The normal boot reader retains its current-state checks.

`--verify` is off by default. It audits once under final selection locks; with
`--dry-run` it audits the preview without publishing. A failed explicit audit
prevents selection. Normal selection does not assert a fresh integrity audit.

## System installation

Default local installation checks descriptor identities and safely unpacks the
archive in one pass without payload hash comparison. It checks bounded member
names/order/types/sizes, permissions and link targets; decompressor errors and
failed copies/provider commands still fail. Compressed archive identity is
recorded during the required private copy. Existing protected metadata is reused;
there is no retained archive/tree or Nix `--verify-path` scrub. The private
profile is composed once, copied durably and published without rebuilding it.
Its expected payload hashes come from component descriptors; generated management
evidence is still produced by the manager. Those expected hashes are not a claim
that normal installation audited the delivered bytes.

Nix realisation remains binary-only with signature enforcement and propagates
its exit status. System's lean install method does not change the inherited
Ports `ensure`/`verify` contract or the startup-bound runtime adapter file.
Named-source cache acquisition retains its independent source/trust checks;
`install --verify` controls the additional System installation audit.

## Interactive choices and evidence

Terminal users may omit `--artifact`. `activate` lists **prepared** candidates;
`stage` and `upgrade` list installed artifacts. Lists show release and exact
artifact ID. Invalid input reprompts, and `q` cancels without a boot change.
Scripts, `--yes` and `--json` require an explicit artifact. Activation displays
the next-boot effect before consent and never reboots automatically.

The owner found both original test installation and first activation
unacceptably slow, with substantial fan activity. That first activation used the
old running MPM. The original #54 change only reduced selection audit passes
from two to one and did not meet the required fast activation boundary.
No real-machine latency is claimed for this replacement implementation.
The [successor hardware test](activation-fast-hardware-test.md) delivers the new
manager as C and measures D through its public installed MPM. Original A/B
checkpoints stay separate. The earlier [A/B delivery](activation-hardware-test.md)
remains pinned to the old implementation.
