<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MPM/Nix Ports experiment

**Status:** a narrow backend probe, not a production MPM implementation or
the complete MPM contract. The owner has now selected Nix for Ports after
the comparator tests. Requires Linux, Python 3.11+, and an
existing Nix installation with the traditional `nix-instantiate` and
`nix-store` commands. Flakes and experimental Nix CLI features are not needed.
Run as the ordinary user inside the dedicated Distrobox, without `sudo`.

The owner has run the adapter inside the dedicated Debian 13 Distrobox on a
Debian host, using Nix 2.35.4, Python 3.13.5 and the pinned Nixpkgs revision
shown below. The real import checks passed; local regression tests continue
to use a simulated Nix backend. These are distinct sources of evidence.
The initial real acceptance sequence for binary Ports imports and private
activation is complete in that container. Production upgrade/project-lock
semantics and execution inside Mojt remain open.

## Owner-reported acceptance results (2026-10-23)

| Check | Observed result |
| --- | --- |
| Pinned source selection | The manual source pin and adapter selected the same hello output |
| First application import | `hello` 2.12.3 imported, activated and printed `Hello, world!` |
| Runtime store metadata | The adapter recorded five hello closure objects with NAR hashes |
| Idempotent installation | Repeating installation printed `No changes.` and preserved the selected profile generation |
| Independent MPM GC roots | Nix reported MPM's own source and hello roots, alongside earlier manual test roots |
| Larger binary import | curl 8.22.0 imported; Nix fetched 17 additional store objects (10.8 MiB download, 29.8 MiB unpacked) |
| Native network execution | The imported curl printed its version and fetched `https://cache.nixos.org/nix-cache-info` over HTTPS |
| Preservation of existing selection | hello still ran and its resolved output path was unchanged after curl installation |
| Parallel build identities | Full curl and curlMinimal 8.22.0 retained distinct objects and fixed aliases; importing the second left the full build active |
| Explicit activation and return | The minimal build was activated, the full build restored, and both exact commands and the older profile still ran |
| Parallel upstream versions | Python 3.12.15 and 3.13.16 imported under one Mojt port name; the second installation left 3.12 active |
| Interpreter extensions and retention | Both fixed interpreter aliases loaded `ssl` and `zlib`; both outputs had registered MPM GC roots |
| Captured project reference | After activation selected 3.13, the saved generation still executed 3.12, with unchanged pin bytes and recorded artifact/closure metadata |
| Repeated Python installation | The selected generation and captured project reference remained unchanged |

The 17 objects are the additional downloads, not a claim about curl's total
closure size. HTTPS success includes the container's existing environment,
networking and certificate configuration; it does not establish independence
from all host services or a working Mojt System. These tests inspected GC
registrations without destructive garbage collection. Production project
locks, upgrade policies and execution on Mojt itself remain pending.

## Manifest and local catalog

`manifests/mpm-nix-example.toml` describes the owner's existing pinned source:

```toml
format = 1

[nixpkgs]
path = "/nix/store/4abi8hv3y6sxq7lgwlllclkjlnx65gd4-nixpkgs/nixpkgs"
revision = "5adc50831c259f87faeb09ddf930d43597197473"
system = "x86_64-linux"

[[ports]]
name = "hello"
attribute = "hello"
commands = ["hello"]
```

Other machines must supply their own already-present source path and actual
revision. A relative path is resolved relative to the manifest. The source
must resolve inside `/nix/store` and its `.git-revision` must match. This
is a local source pin, not portable retrieval from a remote revision.

`ports update --manifest FILE` evaluates only these attributes from that
source, with explicit platform, empty Nixpkgs config and overlays. It disables
import-from-derivation. It records the source revision, source store object
and registered NAR hash, and the selected output paths and upstream versions
in a new local catalog. It roots the source but does not realise applications
or alter their active selection. It never runs `nix-channel --update`.

`ports install` imports all entries from the saved local catalog; optional
names restrict the selection. It does not re-read the manifest or reevaluate
Nixpkgs. Removing an entry from the manifest/catalog never uninstalls it.

Only already-built output paths are passed to `nix-store --realise`; no
derivations are realised and no source builds are attempted. A missing binary
substitute is an error. Nix's native dry-run shows the available download
preview before approval; MPM prints its exact output and activation choices.
This is not yet the production contract's complete machine-readable plan:
capabilities and runtime integration are explicitly unaudited, and closure
hashes are recorded after realisation. Nix's existing signature-verification
configuration remains in effect; the adapter does not replace it.

## First real acceptance run

From the repository root **inside the container**:

```sh
MPM_NIX_LAB="$HOME/mpm-nix-test/mpm-state"
mpm() { python3 ./tools/mpm-nix-prototype --root "$MPM_NIX_LAB" ports "$@"; }

mpm update --manifest manifests/mpm-nix-example.toml --dry-run
mpm update --manifest manifests/mpm-nix-example.toml -y
mpm status

mpm install --dry-run
mpm install -y
"$MPM_NIX_LAB/current/bin/hello"
mpm status
```

Expected: update alone leaves `installed` and `active` empty; install records
one hello output and its runtime store closure, and prints `Activate: hello`.
The command prints `Hello, world!`. Repeating `mpm install -y` should print
`No changes.` and leave `current` unchanged. The fixture need not have exactly
five closure entries on another revision or platform.

Check that MPM registered its **own** roots, even though the earlier manual
`hello-result`/`hello-pinned` links still exist:

```sh
python3 - "$MPM_NIX_LAB" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
state = json.loads((root / "current/state.json").read_text())
paths = {state["catalog"]["source"]["store"]}
paths.update(record["output"] for record in state["installed"].values())
for output in sorted(paths):
    registered = subprocess.check_output(
        ["nix-store", "--query", "--roots", output], text=True)
    expected = str(root / "gcroots" / Path(output).name)
    assert any(line.split(" -> ", 1)[0] == expected for line in registered.splitlines()), registered
    print("PASS: registered GC root:", expected)
PY
```

This inspects registrations without running garbage collection or removing
the earlier manually created roots. Do not move or rename the experiment
directory: indirect Nix GC roots are registered at their absolute locations.

To test a larger declarative list, make a private copy of the manifest and
append another entry, for example:

```toml
[[ports]]
name = "curl"
attribute = "curl"
commands = ["curl"]
```

Then explicitly `update --manifest YOUR_FILE`, inspect `install --dry-run`
and approve `install`. Keep this first acceptance run to hello before adding
more packages, so adapter failures are easy to identify.

## Opt-in test with two Python versions

The pinned Nixpkgs revision includes `python312` and `python313`. The
real acceptance test imports them under the same Mojt port name `python`,
exporting `python3`. This runner is not part of unittest discovery or CI
and must be invoked explicitly inside the container:

```sh
MPM_PYTHON_LAB="$(mktemp -d "$HOME/mpm-nix-test/python-lab.XXXXXX")"
python3 tests/run-mpm-nix-python.py --root "$MPM_PYTHON_LAB"
```

The runner requires a new/empty directory, uses the source pin from
`manifests/mpm-nix-example.toml` (or `--source-manifest FILE`), imports
binary packages, and leaves the experiment retained after success or failure.
It does not change the earlier curl experiment. Its generated catalogs only
contain the requested Python attribute; it does not evaluate all of Nixpkgs.
No source builds are attempted. A missing binary substitute fails the test.

It checks that both fixed commands run, both outputs have registered MPM
GC roots, a second install leaves Python 3.12 active, and explicit activation
switches the default to Python 3.13. Each interpreter runs with `-I` and
imports `ssl` and `zlib` to exercise binary extension loading as well as
interpreter startup. Network requests are not part of this Python test.

The runner also captures the first profile generation, exact identity and
recorded closure in `<root>/test-project/pin.json`. After default activation
changes, it checks that those reference bytes and artifact metadata remain
unchanged and that the captured generation still executes Python 3.12.
This is a **test reference**, not an implemented production project-lock
format, environment resolver or proof of pin protection during removal/GC.
An ordinary reinstall is tested; an `upgrade` action remains unimplemented.

Agent-side validation of the runner was limited to syntax/help checks. The
owner then ran it successfully in the Distrobox with Python 3.12.15 and
3.13.16. The first interpreter needed 14 additional store objects (57.9 MiB
download, 144.2 MiB unpacked); the second needed one additional object
(54.9 MiB download, 128.9 MiB unpacked), reusing dependencies already present.
These are incremental downloads for this test environment, not total closure
sizes or general installation-size estimates.

## Activation and retained identity

The accepted first-install convenience rule applies: the first install of
an application establishes its default commands, shown in the preview.
Later installs retain additional objects without moving its defaults. Each
retained command also has a fixed alias:

```text
hello-<upstream-version>-nix-<full-Nix-store-hash>
```

The full store hash distinguishes rebuilds even with the same upstream
version. This is an **experimental identity/alias convention**, not the final
Mojt release identifier grammar. A port name and explicit command list map
Mojt selection to Nix attributes; no Nixpkgs version history is searched.

`status` prints each installed exact identity, for example
`hello@=2.12.3-nix-<full-hash>`. Select an already installed identity with:

```sh
mpm activate 'EXACT_IDENTITY_FROM_STATUS' --dry-run
mpm activate 'EXACT_IDENTITY_FROM_STATUS' -y
```

Activation reads retained state, never resolves a catalog entry, and never
installs a missing application. It changes the default commands atomically;
all fixed aliases remain. Neither ordinary `PATH` nor Nix user profiles are
modified. To use the defaults in a temporary shell scope:

```sh
(PATH="$MPM_NIX_LAB/current/bin:$PATH"; export PATH; hello)
```

The output and source objects have separate permanent indirect GC roots
under `<root>/gcroots`. Each imported output records its transitive store
closure including itself, plus the NAR hashes reported by the Nix database.
Those hashes identify registered content; they are not independent content
verification, authentication, or a guarantee of reproducible rebuilding.
Kernel, hardware, service and dynamically loaded host dependencies are not
necessarily represented by the Nix store closure.

## Publication, tests and limits

Writers serialize with `flock`. Profiles contain metadata and complete sets
of command links. A single `os.replace` publishes `current`. Old profiles,
sources and application objects remain retained. Separate command lookups
can straddle a switch; resolve `current` once when retaining a consistent
multi-command snapshot. Files already downloaded or rooted before failure
may remain, but the previous active profile remains selected. Stale staging
cleanup and power-loss durability are not implemented.

Use a new/empty dedicated root. The probe refuses unmanaged directories,
modified profile aliases, command collisions and missing retention links.
State and manifests are trusted local inputs, not a hardened boundary against
the directory owner or concurrent changes outside MPM. Do not point it at an
existing production profile, Base directory or the backend-free experiment.

Run the simulated-backend tests without Nix, root or network:

```sh
python3 -m unittest discover -s tests -p 'test_mpm_nix_prototype.py' -v
```

They exercise saved-catalog installation, same-version rebuild retention,
exact activation, root locations, collision rejection, idempotence and
failure before publication. They use a simulated backend and synthetic
executable files: they do not establish Nix CLI compatibility, real GC
retention, or execution on the owner's Debian host. The real acceptance run
above is needed for those first two checks in the Distrobox.

Recorded agent-workspace validation: all 16 adapter tests passed. The combined
suite passed 52 of 53 tests; the unchanged Base root-ownership test could not
perform `os.chown(..., 1000, 1000)` in this environment (`EINVAL`). This is not
a claim of a passing full suite or a test run on the owner's Debian host.

Not implemented: series selection and upgrade policies, project profiles or
portable lockfiles, removal/GC, automatic selection of multiple Nix outputs,
desktop/service integration, system capability checks, System or boot. Only
the selected default output is imported; explicit commands must be executable
under that output's `bin/`. It is not a claim to support every Nixpkgs package.
There is no implicit reconciliation that removes packages absent from TOML.

References: [Nix store realisation](https://nix.dev/manual/nix/2.35/command-ref/nix-store/realise.html),
[store queries and hashes](https://nix.dev/manual/nix/2.35/command-ref/nix-store/query.html),
[Nix evaluation](https://nix.dev/manual/nix/2.35/command-ref/nix-instantiate.html),
and the [MPM contract](mpm.md).
