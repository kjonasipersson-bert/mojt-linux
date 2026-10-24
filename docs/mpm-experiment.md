<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MPM experiment A: Ports without a package backend

**Status:** runnable host-side experiment, not a package manager. It tests
a subset of the [MPM contract](mpm.md) before selecting a backend. It does
not modify Base, System, Kernel, `/etc`, `/var`, or host command directories.
All paths are beneath an explicitly supplied disposable `--root`.

The only payloads are two synthetic command families, `blender` and `gimp`.
Each generated shell script prints its name and exact fixture release.
The fixture version numbers do not assert that corresponding upstream
releases exist. No application is downloaded, built or launched.

## Run the acceptance test

From the repository root on Linux with Python 3.11+ and `/bin/sh`:

```sh
python3 -m unittest discover -s tests -p 'test_mpm_prototype.py' -v
```

No elevated privileges, network, external Python packages, prebuilt Base
image or package backend are required. Tests use temporary directories.

## Interactive walkthrough

Run from the repository root in a POSIX shell:

```sh
MPM_LAB="$(mktemp -d -t mojt-mpm.XXXXXX)"
mpm() { python3 ./tools/mpm-prototype --root "$MPM_LAB" "$@"; }

mpm ports update --catalog tests/fixtures/mpm/catalog-1.toml -y
mpm ports install blender@4.9 -y
mpm ports install blender@5.3 -y

"$MPM_LAB/current/bin/blender"        # blender 4.9.12-r1
"$MPM_LAB/current/bin/blender-5.3"    # blender 5.3.7-r1

mpm ports activate blender@5.3 -y
mpm ports update --catalog tests/fixtures/mpm/catalog-2.toml -y
mpm ports upgrade --dry-run
mpm ports upgrade                      # review the plan, then type y
mpm ports status                       # full JSON state and identities
```

`-y` approves the displayed plan; omit it for confirmation. `--dry-run`
does not write anything. A real mutating command initializes the private
root marker, lock and empty storage directories before planning; cancellation
does not publish a generation or install payloads. `update` copies an explicit
local fixture snapshot into a new profile generation. `install` and `upgrade`
use that saved snapshot, even if its original TOML file changes or disappears.
Neither operation performs an implicit refresh.

After the approved upgrade:

| Command | Dummy release |
| --- | --- |
| `blender` | `5.3.8-r1` |
| `blender-4.9` | `4.9.13-r1` |
| `blender-5.3` | `5.3.8-r1` |
| `blender-4.9.12-r1` | `4.9.12-r1` |
| `blender-5.3.7-r1` | `5.3.7-r1` |

To exercise ordinary Unix command lookup, put the dedicated directory on
`PATH` in a subshell. It contains only the dummy commands:

```sh
(PATH="$MPM_LAB/current/bin:$PATH"; export PATH; blender; blender-4.9)
```

An exact default can be selected without changing the retained series intents:

```sh
mpm ports activate blender@=4.9.12-r1 -y
mpm ports upgrade -y
"$MPM_LAB/current/bin/blender"        # still blender 4.9.12-r1
```

The subtle install/upgrade distinction can be tested in another fresh root:
install `blender@4.9` against catalog 1, update to catalog 2, then **install**
`blender@4.9` again. A new exact alias is published, while both `blender`
and `blender-4.9` still select `4.9.12-r1`. Only `upgrade` or explicit
`activate blender@4.9` advances the series alias to the installed `4.9.13-r1`.

## Experiment-only conventions

- Only `ports` exists. Supported actions are `update`, `install`, `activate`,
  `upgrade` and read-only `status`. There is no `remove` or garbage collection.
- Requests must explicitly use `name@series` or `name@=release`. Unqualified
  latest requests are deferred, including their interaction with active series.
  Activation changes a selection, not the installation's retained upgrade intent.
- Names contain lowercase ASCII letters and digits, starting with a letter;
  each package exposes exactly one command with that name. This deliberately
  avoids settling the contract's multi-command and escaping questions.
- Fixture releases use canonical dotted nonnegative numbers with no leading
  zeroes plus a positive numeric `-rN` revision. Series have dotted numbers
  only; comparisons use numeric components and revision numbers. Exact matching
  is literal: `@=3.0` does not match `3.0.0-r1`. These rules are **not** a
  production version grammar or an adapter for any existing package ecosystem.
- Only stable records participate in series resolution; preview records can
  be requested exactly. Epochs, prerelease syntax, channel selection, repository
  preference, withdrawals and security advisory handling are deferred.
- Each retained object records source, acquisition snapshot, canonical release,
  full payload SHA256 and object path. There are **no dependencies** or external
  capability requirements in this experiment. SHA256 identifies the generated
  bytes; it does not authenticate a repository.
- There is one simulated system-wide profile inside the private root.
  Per-user overrides and project profile/lockfile commands remain deferred.

## Publication and storage

The disposable layout is an implementation detail, not a Ports package format:

```text
<root>/
  .mpm-experiment
  .lock
  store/<name>-<release>-<sha256>/bin/<name>
  profiles/<generation>/state.json
  profiles/<generation>/bin/<aliases>
  current -> profiles/<generation>
```

Requested upgrade intents, resolved installed objects, accepted series targets
and active selectors are separate fields. Additional installations never
retarget existing series/default aliases. An explicit series activation picks
the newest eligible **installed** candidate, without accessing the catalog or
installing content. Exact activation remains pinned across upgrades.

Writers serialize with `flock`. Complete metadata and command symlinks are
built in a new generation; a single `os.replace` of `current` publishes it.
Readers traversing `current` see a complete old or new generation. Separate
lookups can span a switch; callers needing a consistent multi-read snapshot
must resolve `current` once and retain that generation path. This is not
a switch of any running process's filesystem root.

Old profiles and store objects are retained. MPM never edits an existing
object, and generated executables have read-only file modes. This is logical
immutability, not protection against the directory owner modifying files.
Existing objects are checked before mutations. A failed publication leaves
the selected profile unchanged; already staged objects may remain unreferenced
and can be reused on retry. A process killed during staging may leave staging
directories or an unpublished generation. No cleanup/recovery command or
power-loss durability (`fsync`) guarantee is provided.

The root must be new/empty or already marked as this experiment. Unmanaged
`current` paths and changed/extra commands in the selected profile cause an
error rather than being overwritten. No existing administrator bin directory
is adopted. Use trusted local fixtures and a private disposable directory;
this prototype is not a hardened importer for hostile state or concurrent
modification outside MPM.

The pin test captures an exact artifact reference, source/snapshot/digest,
an empty dependency closure and the old executable bytes, then verifies that
ordinary upgrade preserves them and old-generation commands still run.
This tests retention only: it does not implement or validate production
project locks, dependency resolution, ELF library closure or sandboxing.

The acceptance tests also exercise parallel series, exact-first activation,
numeric/revision ordering, preview exclusion, missing activation candidates,
explicit snapshot refresh, dry runs/cancellation, unmanaged path conflicts,
object corruption, concurrent writers and failure just before publication.
