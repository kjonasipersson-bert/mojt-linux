<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Installed named sources, frozen snapshots and native acquisition

Implemented bounded integration in consolidation steps 1 and 2. It connects
`mpm_sources.py`, `mpm_sources_cli.py` and the native cache to the same MPM
frontend delivered in System. Python remains in System. No Nix import, global
compiler/libc change, service activation or boot publication is involved.

The [signed Base repository](native-repository.md) also supports HTTPS sources:
`mpm base repo add NAME --url URL --key-file PUBLIC_PEM` registers owner-selected trust,
and `mpm base repo update NAME` authenticates one complete signed catalog. Local source
commands below retain their protected-directory behavior. Base source installation
can resolve the accepted release with `mpm base install mojt@0.2 --repo NAME`; it does
not refresh implicitly.

## Command flow

The source and policy files use the versioned records in
[native source/cache](native-source-cache.md). Commands below assume those files
already exist and `local` matches the name in both records. These commands belong
to the new System runtime; an older VM does not gain them until that runtime is
delivered. On an installed machine, mutation requires an administrator. The source
checkout can use a private owner-controlled lab with explicit roots.

```sh
mpm kernel repo add local --from-file /protected/source.json \
    --policy-file /protected/policy.json --dry-run
mpm kernel repo add local --from-file /protected/source.json \
    --policy-file /protected/policy.json
mpm kernel repo update local --dry-run
mpm kernel repo update local
mpm kernel repo list
mpm kernel repo show local --json
```

`add` adopts the exact source and a copy of its protected owner policy. It does
not refresh metadata. A new/reconfigured source reports `refresh_required=true`.
A repeat identical registration keeps its accepted snapshot. Changing the source,
channel, location or policy needs explicit `add ... --replace`; this clears the
current snapshot while retaining previous records. Editing an original input
policy file after registration does not reconfigure the accepted copy. Reconfigure
through `mpm kernel repo add --replace` to change authorization.

For a local-directory source, `update` reads `snapshot.json`, `catalog.json` and `acquisition-map.json`
relative to the registered repository root, plus descriptors named by that map.
`--snapshot-file`, `--catalog-file` and `--acquisition-file` change these confined
relative metadata locations. Absolute paths, escapes, unsafe links and special
files are rejected. The source root itself changes only through reconfiguration.
All accepted descriptor/catalog/map bytes are frozen before current publication.
No archive body, provider, installed package or active wish is changed by update.

The initial named-source implementation accepts one release catalog per snapshot,
including an empty catalog after withdrawal. All candidate payloads must have
validated native offers. Different families/areas can use separate named sources.
This bounds each update to 64 MiB of frozen metadata, with the existing 16 MiB
per-file limits. Mixed/other-provider offers need a metadata adapter integration;
the pre-existing explicit Nix-backed Ports bundle workflow remains available.

Exact native acquisition is a separate action:

```sh
mpm kernel repo fetch "$ARTIFACT" --repo local \
    --archive-sha256 "$ARCHIVE_SHA256" --dry-run
mpm kernel repo fetch "$ARTIFACT" --repo local \
    --archive-sha256 "$ARCHIVE_SHA256"
```

`ARTIFACT` is a full `sha256:` native artifact ID. `ARCHIVE_SHA256` is one raw
64-hex compressed encoding approved by the accepted map. The two identities are
different. The public command area determines the artifact kind. Fetch defaults to the
current accepted snapshot; `--snapshot ID` pins an already retained older one.
An older snapshot is usable only if it still binds the currently registered source
and policy. A newer snapshot of the same source does not revoke an explicit pin;
source/policy reconfiguration prevents silently reusing the old authorization.

Mutation commands display their exact plan and ask for confirmation; `-y` accepts
that command's plan. `--dry-run` emits a read-only plan without creating a registry,
cache, lock or payload. This preview does not claim the archive body was verified.
The narrow acquisition plan is not the general saved execution/approval protocol.

## Paths, publication and inspection

Each area has its own registry at `/var/lib/mojt/sources/AREA`; native cache defaults to
`/var/lib/mojt/cache`, alongside the existing machine state. `--root` selects the
area registry for repo metadata commands and the cache for repo fetch. Fetch's
`--repos-root` can explicitly select another source registry. Do not put either
root inside the other. Target parents must exist and satisfy ownership checks.

The version marker is `{"format":"mojt-source-registry-v1"}` in `registry.json`.
Immutable envelopes live under `objects/<ID_HEX>.json`, exact raw bytes under
`metadata/<SHA256>`, and `names/NAME/current` points relatively to a registration.
`mojt-source-registration-v1` describes `{name,source,policy,snapshot}`; a null
snapshot requires refresh. `mojt-source-change-plan-v1` binds the absolute root,
name, baseline registration ID, proposed description and sorted raw metadata
hashes. Record IDs use the existing canonical envelope rule, excluding `id`.

Writers serialize on the stable `.lock`. Complete immutable evidence is flushed
before one atomic current-pointer publication. Failure before that point preserves
the last good pointer; after-pointer fsync failure reports uncertain durability
and retains the new state. Interrupted initial directory creation is refused as
incomplete, rather than silently adopted. Orphan evidence is retained; no GC is
introduced. A cache fetch holds a shared registry lock across verification so
source reconfiguration cannot race its authorization. Cache acquisition has its
own independent writer lock.

`list`/`show` read accepted metadata without provider execution or refresh. Show
reports the selected snapshot, retained catalog, pending-refresh state and whether
the local repository directory is present. Snapshot age is explicitly unknown;
directory presence does not prove archive availability or freshness. They do not
rehash cached archive bodies. Valid cached bytes can be reverified while the
original repository is unavailable, using the frozen metadata and accepted policy.

## Evidence and remaining work

`tests/test_mpm_sources.py` covers a delivered copy launched from `/` with isolated
Python imports and no Nix files, actual tar/zstd acquisition, read-only previews,
no-ops, offline metadata reuse, withdrawal, old pins, reconfiguration, path safety,
publication/flush failure and authorization locking. Existing cache/package tests
cover four category namespaces and full byte verification.

The cache output is still acquisition evidence. The [Kernel source-install join](kernel-source-install.md)
now passes an exact acquired archive to the existing installer, retaining source
provenance and keeping boot selection separate. Base and System also have native
install joins; the [Base HTTPS repository](native-repository.md) authenticates
signed remote publication. Native Ports publication, pruning and lifecycle
recovery remain separate work.
