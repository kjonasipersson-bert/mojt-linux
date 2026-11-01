<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Fresh Ports commands in the delivered System runtime

PR #36 now connects the common `mpm` frontend to `mpm_ports_cli.py` and the fresh
request/resolver/profile APIs. System assembly delivers the closed module set
alongside its pinned Python. Ports commands no longer dispatch through the old
imperative Nix experiment. That experiment remains a separately invoked tool and
an optional read-only exporter dependency, not a store conversion path.

This advances steps 1–2 of the [governing plan](mpm-consolidation-plan.md).
It does not complete Base/System installation, bootstrap or build integration.
MBT command syntax remains outside this increment.

## Operator inputs and ordinary flow

Use a new empty registry; no existing installation migration is needed. A local
accepted bundle is a content-identified envelope:

```json
{
  "format": "mojt-ports-sources-v1",
  "id": "sha256:<canonical envelope hash excluding id>",
  "description": {
    "platform": "x86_64-linux",
    "sources": {
      "local": {
        "snapshot": "sha256:<accepted snapshot identity>",
        "catalogs": {"hello": "complete mpm-release-catalog-v1 object"},
        "offers": ["complete exact provider offer objects"]
      }
    }
  }
}
```

The strings standing for complete objects are explanatory placeholders, not valid
input. See `mpm_request_plan.sources_view` for the closed fields. Native/provider
identity and integrity bindings stay explicit. `--expected-sources ID` additionally
pins the envelope supplied with `--sources FILE`. Accepting local operator data
is not metadata signature authentication or a remote source discovery service.

```sh
mpm ports update --sources hello-sources.json --dry-run
mpm ports update --sources hello-sources.json -y
mpm ports install hello@2.12 -y
mpm ports upgrade hello --dry-run
mpm ports upgrade hello -y
mpm ports list --exact
mpm ports activate 'sha256:REFERENCE_FROM_LIST' -y
mpm ports activate hello@2.12 -y
mpm ports history --json
```

Initial install/apply can also accept `--sources` directly. Later operations use
the accepted finite data stored in the selected profile. Multiple named sources
require explicit `install --source NAME`. `update` always requires a deliberate
snapshot input. There is no fallback to a channel, attribute evaluation or source
build. The optional `mpm-nix-catalog.py --bundle` exporter produces this envelope
from already-local Nix outputs and explicit pinned sources, including closure
hashes and executable names; exporting does not fetch or retain payloads.
A live import acceptance with the new adapter remains required.

Without `-y`, the command displays the target, exact package references, effective
choices, request revisions and source snapshots before asking to apply. `--dry-run`
returns the full plan and executes no provider command or state write. Installed
shared mutations require an administrator before input/provider work. Read-only
status/list/history/search/info work without a provider or a checkout.

## Preserved request and activation semantics

The publisher now takes an explicit `advance` claim set. New wishes resolve, but
accepted targets advance only when requested. Exact-release wishes keep their
accepted full build and dependencies, even if a new snapshot withdraws/replaces
that release. Original resolution evidence remains linked to retained profiles.
`update` can publish new metadata while preserving all package choices; installing
another package does not upgrade existing wishes. Named `upgrade` cannot advance
unrelated wishes. Exact active overrides survive following-request upgrades.

Installed activation uses the stored upstream/revision/scheme/stability evidence,
not reconstructed version strings or current catalog preference. Unknown and
preview releases stay exact-only. Build ambiguity requires the full reference ID.
Following activation requires one accepted interactive wish targeting the installed
object; a configuration-only target first needs an independent interactive wish.
`--no-activate` preserves the absence of a default on first installation.

Ports-only configuration application:

```toml
format = "mojt-configuration-v1"
name = "workstation"

[ports]
source = "local"
packages = ["hello@2.12"]
active = { hello = "hello@2.12" }
```

```sh
mpm ports apply --configuration mojt-configuration.toml --dry-run
mpm ports apply --configuration mojt-configuration.toml -y
```

Only that named configuration's claims are reconciled; removed entries release
its reason. Independent interactive reasons and overrides survive. Reapplication
resolves its own moving wishes without upgrading unrelated interactive wishes.
A file containing Base/System/Kernel sections is rejected rather than partially
reported as applied. Public imperative removal/reset remains unimplemented here.

## System boundary and evidence

`MPM_FILES` includes all new modules. The System manifest derives its declared
reader/writer formats and capabilities from the delivered fresh frontend:
`mojt-ports-profile-v1` and `mpm-request-origins-v1`. Target inspection understands
the content-identified envelope; a candidate missing either support is refused.
No numeric legacy format is advertised as manageable by this new dispatcher.
The profile binds the target platform, and a different-platform writer is refused.

Tests exercise the public dispatcher, dry-run/cancellation, actual file import and
command execution, metadata-only updates/withdrawal, explicit upgrades and pins,
configuration reasons, unknown stability and installed execution without a checkout
or prototype. The file-copy provider is a trusted fixture injected by the test
harness, not a production provider or native archive support. Separate tests cover
Nix protocol and bundle shape; neither is live Nix cache acceptance. Native Kernel
frontend regressions and System payload/capability tests remain in CI.

Remaining gates: live Nix import acceptance, remote authenticated source acquisition,
imperative reason/version removal and reset, native Port archives, lifecycle effects
and complete recovery, then the remaining Base/System/bootstrap/build milestones.
No global compiler/libc selection changes or runtime ABI proof follow from this work.
