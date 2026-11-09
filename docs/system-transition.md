<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Exact System transition preflight

`mpm system plan` is a verified read-only preflight for an **already installed**
native System generation. It binds the candidate artifact/composition/profile to
the authoritative selected deployment, preserving its exact Base and Kernel.
It neither stages/selects boot content nor runs initialization or services.

```sh
mpm system plan --artifact sha256:FULL_SYSTEM_ARTIFACT --json
```

Installed commands use the mounted installation. Checkout/offline inspection
requires `--disk-root /TARGET`; a fresh v1 baseline additionally needs the exact
`--baseline boot/mojt/GENERATION/BASE` entry. The installed frontend derives this
only from the already bound fresh runtime record; managed menus remain the
authority even when running and selected differ. Labels/uname are not selection.

Verified planning requires administrator access, the selected System's retained
codec and any necessary provider adapter. Explicit offline provider targets
retain the existing refusal to use the inspector host's unrelated store. The
selected Base must also have a verified native installation/realization; merely
having a legacy `base/VERSION` directory is insufficient.

## Evidence and gates

The `mojt-system-transition-preflight-v1` result records:

- Physical target/installation identity, selected deployment, root UUID and full
  menu checksum. Existing shared read locks are used without creating locks.
- Exact retained Base artifact/receipt/realization, Kernel artifact/image/module
  identity and bounds bound to that exact Base.
- Candidate System artifact/receipt/realization, composition, measured manifest,
  human label and unavailable runtime outputs.
- Actual Base ABI/state layout, current Ports format and persistent account
  shells. ABI facts come from the verified Base, not the candidate System.
- Measured management compatibility, provider preservation, startup review and
  missing-default observations. Account/provider paths are confined to the
  retained Base or accepted provider closure; host files cannot satisfy them.

Current menu, target identity and observed state are checked again before the
result is returned. The internal `recheck` recomputes the complete plan and
refuses changed inputs. A saved result is information, not permission to execute
effects. No wishes, configuration, cache, registry, slot or boot pointer changes.

## First initialization/service contract

The implemented policy is deliberately **unchanged startup, tooling changes
only**, recorded by `mojt-system-startup-review-v1`. It permits MPM/tool modules,
MPM/inspector frontends, test files, the MPM manual and newly added admin commands.
It normalizes only write bits removed during immutable installation; other
metadata/content differences remain meaningful. A changed version marker must
match the candidate's human label.

All remaining profile content must be preserved: setup/start/environment,
units, helper declarations/producers, authentication data and service configs.
Changed/removed services or startup inputs block. No new migration or initializer
is inferred from an empty lifecycle list or a package-supplied script.

Providers implement their own pure preservation comparison. The Nix adapter
requires the entire selected startup closure's exact paths/NAR hashes to remain
accepted and its delivered adapter implementation to remain unchanged. Additional
dependencies may coexist. A newer glibc cannot silently replace the old service
closure under this policy; preserved services retain their original dependencies.
This is not a general proof of runtime libc/plugin compatibility.

The two declared late-created privileged helpers must retain their existing
contract/producer. Planning neither creates nor borrows them from the current
host. New helper/privilege initialization needs a supported later contract.
Missing defaults likewise block for explicit preparation; existing local files
and symlinks are preserved without being followed or overwritten.

`checks.compatible=true` means this bounded metadata/content policy passed.
It does not report service health or a bootable candidate. Service upgrades,
provider runtime changes and state migrations need separate supported contracts,
not a user flag bypassing these gates.

## Remaining deployment work

The existing assembled System's flat `defaults/journald.conf` and
`defaults/timesyncd.conf` are resources linked from `/etc/systemd`; observation
checks those actual persistent paths, without creating unused top-level copies
or replacing local configuration. A linked `systemd` parent is refused.

Both `stage_ready` and `boot_ready` remain false. This reader observes the
existing verified v1 layout; it does not convert it to native-v2 or alter the
closed v1 System reference. The [native-v2 record/storage layer](native-boot-v2.md) now validates inputs,
binding and deployment, and atomically retains a complete immutable slot without
selection. It does not yet consume this preflight as execution authorization.
The [diagnostic constructor/early reader](native-initramfs-reader.md) now verifies
exact trees from its trusted private runtime. The [System handover mode](native-system-handover.md) now joins this preflight,
current-state checks and a separate boot Base to runtime/shutdown handover.
[Prepared-candidate admission/selection/status](native-system-selection.md) is
implemented. Planning/staging a new generation from an active v2 baseline and
request-to-boot integration remain before complete administration. No backward migration is required.

The [prepared single A/B/A owner test](system-boot-acceptance.md) now exercises the
new-image constructor and installed selection/status frontend. The owner
completed its A/B/A boot/return and clean-shutdown acceptance on 2026-11-09 with
exact Base/Kernel and persistent state retained. These synthetic preflight tests
are separate from that real VM evidence. Three focused cases cover tooling/provider preservation,
real root retained-content inspection without writes, and refusal of changed
service/provider contracts plus stale persistent-account evidence.
