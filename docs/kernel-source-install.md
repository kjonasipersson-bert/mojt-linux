<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Registered source to Kernel installation

Implemented in the installed MPM frontend, consolidation steps 1 and 2. This
joins the [named source/cache flow](source-runtime-integration.md) to the existing
Kernel publisher. It changes neither the current Base/System nor boot selection.

## Commands and exact scope

After explicitly registering/updating a native source:

```sh
mpm kernel install --source local --expected-id "$ARTIFACT" \
    --archive-sha256 "$ARCHIVE_SHA256" --dry-run
mpm kernel install --source local --expected-id "$ARTIFACT" \
    --archive-sha256 "$ARCHIVE_SHA256"
mpm kernel status --json
```

`ARTIFACT` is a full native artifact ID, while the archive SHA256 identifies one
approved compressed representation. `--snapshot ID` pins a retained snapshot;
otherwise planning pins the currently accepted snapshot. A subsequent metadata
refresh under the same source/policy does not replace that planned snapshot.
An authorization reconfiguration invalidates the old source binding.

Source/cache defaults come from the selected System runtime, including explicit
Runtime overrides in an installed copy. `--sources-root` and `--cache-root`
override them. The installed Kernel registry still defaults to
`/run/mojt-disk/kernel`; standalone checkout use retains its explicit `--root`
or `/var/lib/mojt/kernel` default. The three roots must be disjoint. File-based
`--from-file ... --expected-id ...` remains a separate input mode; mixing source
options into that mode is rejected.

Planning validates accepted metadata, the descriptor, platform and the existing
Kernel installer's supported subset before acquiring bytes. Unsupported
dependencies, requirements and file types fail before cache/registry writes.
`--dry-run` creates neither root nor lock and does not claim to verify an archive
body. It therefore needs no retained zstd helper. Actual source installation
needs the selected System's retained codec and administrator authorization.
Kernel/Base deployment compatibility remains explicitly unevaluated here.

## Publication and origin evidence

`mojt-kernel-source-install-plan-v1` uses the canonical envelope identity rule.
Its description binds `root`, `sources_root`, `cache_root`, `name`, `artifact`,
the exact `snapshot`, the native `acquisition` plan and shared `installation`
eligibility. It is a narrow compound plan, not the general saved approval format.
After confirmation, execution recomputes it while holding the source registry's
shared authorization lock. The existing cache lock protects archive acquisition;
the existing Kernel lock protects final installation. Source authorization remains
locked through the Kernel publication.

The existing installer freezes and re-verifies the copied archive and publishes
the complete read-only module/image tree. It rechecks the selected raw archive
encoding as well as artifact identity, and applies the acquisition expansion cap
to verification of both the input and private frozen copy. A changed compression
encoding with the same logical artifact is not silently substituted.

The `mpm-kernel-install-v1` record has optional `acquisition` origin evidence for
source installs: exact source ID/name, the complete `mojt-cache-record-v1`
observation and the accepted outer expansion cap. Its trust kind is
`registered-native-source`, binding the source and verification IDs. Status checks
the observation identity and its artifact/archive binding, then exposes this
origin separately from installed/selected/running facts. This protected local
receipt is neither a publisher signature nor evidence of deployment compatibility.

Existing file installs retain their explicit-local-file origin. A repeat of an
already installed artifact fully checks retained content and leaves its original
installation record unchanged, even if another source now offers it. It needs
neither a source archive nor a populated cache and creates no replacement cache.
Changing the proposed source never relabels historical installation provenance.

Acquisition and installation are separate durable phases. If installation fails,
verified cache content remains available for retry while no partial Kernel object
is published. Cache success is not installation success. Selected/running
deployments, boot records, machine/user state and Ports are outside this action.

## Validation and VM gate

Real tar/zstd tests cover the joined pipeline, eligibility before acquisition,
origin preservation, no-ops without source/cache bytes, source reconfiguration,
source authorization locking through publication, failed extraction/retry and
same-artifact/raw-encoding substitution. An isolated delivered copy installs and
inspects packages from `/` without provider files or checkout imports. Existing
local-file Kernel tests remain passing.

**Next owner acceptance is one bounded VM test before merging this integration.**
Use a disposable copy with a System that delivers this MPM runtime and a real
native Kernel artifact not already installed in its Kernel registry. An existing
build can be packaged with another explicit package revision while retaining the
original build provenance and `kernel_release`; no kernel rebuild is required.
Keep the original VM disk detached. Do not repeat the whole A/B test matrix.

The acceptance runner uses the installed `/run/mojt-system/bin/mpm`, its ordinary
runtime defaults, a unique named source and a private fixture repository. It checks
source registration/update, write-free preview, real installation and retained
provenance/tree, repeat no-op after removing fixture archive availability, and
unchanged running Kernel, machine ID, Base/System and existing boot records.
It retains its lab and JSON result. It performs neither selection nor reboot.

Once that updated System and real archive are in the VM, run as root:

```sh
/run/mojt-system/bin/python3 -I -B \
    /path/to/pinned-source/tests/run-kernel-source-acceptance.py \
    --archive /path/to/real/kernel-package.tar.zst
```

The runner refuses an already installed artifact because that would only test a
no-op. Its synthetic source-policy fixture is deliberately owner-trusted local
metadata; it does not introduce a signed distribution service. The fixture
publisher is exercised in unit tests, including package revisions, but **VM
acceptance has not run in this development environment**. A later `stage`/`select`
test and restart are a separate boot-deployment gate, not an installation step.
