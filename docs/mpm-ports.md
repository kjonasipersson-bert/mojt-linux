<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Using MPM for ordinary Ports

This iteration extends the working Nix probe into a usable experimental CLI.
It installs command-line applications from a pinned local Nixpkgs source,
without a new TOML entry for every application. It does not implement the
entire [MPM contract](mpm.md), NixOS service activation or desktop integration.

## Inside a newly built step 3 Mojt VM

The guest entry point now accepts the area explicitly: **`mpm ports ...`**.
The old guest shorthand `mpm install` is replaced. The default state directory
is `/var/lib/mojt/ports`. The System image provides the initial source pin:

```sh
mpm ports update --dry-run
mpm ports update -y
mpm ports search less
mpm ports info less
mpm ports install less --dry-run
mpm ports install less -y
less --version
mpm ports install git vim -y
git --version
vi --version
mpm ports list
```

`update` selects the supplied local source on first use. Subsequent calls
reuse the saved source pin; they do not update channels or secretly advance
to the latest Nixpkgs. To change source, explicitly use `update --manifest
FILE` with another already-present source pin. Updating never installs,
removes or activates applications. `info` and `search` use the same saved
source and cannot silently change it.

Search matches a case-insensitive **attribute-name fragment**, not package
descriptions or command names. It lists top-level attributes by default:

```sh
mpm ports search python
mpm ports search requests --scope python313Packages
mpm ports search vi --limit 100
mpm ports info python313Packages.requests
```

Search evaluates at most the displayed attribute-candidate limit (default 50,
maximum 200), skipping package sets and entries that fail evaluation. Narrow
the fragment if results are limited. Nested attributes may also be passed
directly to `info` and `install`. Not every package is a standalone program;
outputs without executable `bin/` files cannot be installed by this iteration.

## Installation and activation

For ordinary requests, the Ports name is the Nixpkgs attribute. To retain
different attributes under one application name, use `--attribute`:

```sh
mpm ports install python --attribute python312 -y
mpm ports install python --attribute python313 -y
mpm ports list
mpm ports activate 'EXACT_IDENTITY_FROM_LIST' --dry-run
mpm ports activate 'EXACT_IDENTITY_FROM_LIST' -y
```

The first install activates default commands. Further versions leave the
default unchanged. Every installed application exports fixed command aliases
containing its upstream version and full Nix output hash. Activation accepts
an installed exact identity; a bare name is accepted only when unambiguous.
It never fetches another version. Series selectors/upgrades remain deferred.

The adapter chooses Nixpkgs' binary output (`lib.getBin`: `bin`, otherwise
`out`, otherwise the default). It discovers executable files in that output's
`bin/`, including executable symlinks. It roots the output and source, and
records the transitive closure and NAR hashes. It imports output paths only;
missing binary substitutes fail rather than starting source builds.

When the output is already local, its command names can be checked before
approval. Otherwise the preview explicitly says they will be discovered
after import. MPM downloads into the store, validates exports and builds a
complete private profile **before** switching `current`. A discovered
command collision aborts publication; the previous profile stays active,
although downloaded/rooted objects may remain. This is a known gap relative
to the contract's fully resolved preview. Use `--no-activate` to retain a
conflicting application through its fixed aliases without claiming defaults.

MPM never edits Base/System binaries or administrator command files. Login
PATH places the Ports profile before System and Base commands, allowing
interactive use of the selected Ports version. This can shadow a command
from those layers. The MPM guest launcher uses a fixed System Python and
System-first backend PATH, independent of the interactive Python selection.
MPM, the Nix entry points and the System checker are reserved management
commands; Ports may retain them through fixed aliases with `--no-activate`,
but cannot claim their unqualified names.
After first installation/removal of a previously found command, `hash -r`
may be needed to clear the current shell's command-path cache.

The VM builder adds `/etc/profile.d/mojt-system.sh` without replacing existing
profile contents. The normal Base login profile must source that directory.
For a custom profile that does not, source `/run/mojt-system/environment`
explicitly or add the hook yourself. Existing built VM disks contain the old
wrapper: rebuilding with this checkout is required to get the new guest CLI.
The existing exported step 3 payload can be reused; the wrapper comes from
the VM builder's checkout, not from the payload.

## Removal

```sh
mpm ports list
mpm ports remove 'EXACT_IDENTITY_FROM_LIST' --dry-run
mpm ports remove 'EXACT_IDENTITY_FROM_LIST' -y
```

Removing an inactive installation preserves the active one. Removing the
active installation restores the most recently active remaining installation;
if none was active before, it selects the most recently installed one. With
no replacement, default command aliases disappear. Ordering uses persisted
event sequences, including first-install and fallback activations, not clock
timestamps or highest-version sorting. A bare name is refused if several
versions are installed. Multiple explicit removal targets form one plan.

Removal changes the current profile only. The store objects, their GC roots
and old profiles remain available, including captured project references.
It does not reclaim disk space. Profile pruning, physical GC, production
project locks and a user-facing rollback command remain future work.

The profile file and directories are flushed before the atomic selection
change, and the selection directory is flushed afterwards. Failures before
selection preserve the previous profile. An I/O failure after the rename
may mean selection already committed: MPM explicitly reports this uncertainty
and retains the new generation for inspection instead of deleting it. This
does not establish complete power-loss recovery for all backend state.

## Testing in the existing Nix Distrobox

From a checkout containing this change, inside `mojt-mpm-nix`:

```sh
MPM_PORTS_LAB="$(mktemp -d "$HOME/mpm-nix-test/ordinary-ports.XXXXXX")"
python3 tests/run-mpm-nix-ports.py --root "$MPM_PORTS_LAB"
```

The opt-in runner imports hello, less, git and Vim, verifies the exported
`vi`, then tests parallel Python versions, removal-triggered fallback, last
removal and a captured old generation. It leaves the lab and roots intact.
This is separate from the earlier Python probe and needs no sudo or host
Nix installation. A source-only manifest containing `format` and `[nixpkgs]`
is sufficient; the historical example's curated hello entry also works.

For manual CLI use in that lab:

```sh
mpm() { python3 tools/mpm --root "$MPM_PORTS_LAB" "$@"; }
mpm ports list
PATH="$MPM_PORTS_LAB/current/bin:$PATH"
export PATH
```

Inside the new Mojt VM, `mojt-system-check ports` retains the earlier
boot/import/Python acceptance. `mojt-system-check programs` additionally runs
the new ordinary-Ports test in a separate persistent lab. Reboot the same
disk and check `mpm ports list` plus the installed commands to verify that
the interactive installation set survives boot.

Simulated backend regressions run without Nix or root:

```sh
python3 -m unittest discover -s tests -p 'test_mpm_nix_prototype.py' -v
python3 -m unittest discover -s tests -p 'test_system_vm.py' -v
```

Current limits also include unaudited host-service requirements, no GUI data
or desktop-file integration, no generalized multi-output environment, no
power-loss durability guarantee and no reconciliation of raw Nix changes.

## Agent-side validation (2026-10-24)

Real Nix 2.35.4, using the pinned revision
`5adc50831c259f87faeb09ddf930d43597197473`, passed the ordinary-program
acceptance in `/tmp` and again under `/var/lib/mojt` in the agent runtime:
hello 2.12.3, less 710, Git 2.56.0, Vim 9.2.1164 (including `vi`), and Python
3.12.15/3.13.16. Imports used the public signed binary cache. The checks
covered generic attribute lookup, command discovery, retained closures,
independent activation, historical fallback, last removal and a captured
generation. These were real CLI subprocesses, separate from simulated tests.

An unresolved runtime-local anomaly was also observed with test state under
`/workspace/scratch`: successive subprocesses could observe older profile
selections, losing earlier entries in a later plan. The same sequence passed
outside that directory and with an additional test-only `sync()` after each
subprocess. Targeted file/directory fsync did not eliminate the anomaly.
No global-sync workaround is added to MPM and no filesystem cause is claimed
as established. The owner's Distrobox acceptance below subsequently passed;
fresh Mojt VM acceptance for this iteration remains pending.

## Owner-reported Distrobox acceptance (2026-10-24)

The owner ran `tests/run-mpm-nix-ports.py` inside the existing Nix Distrobox
and reported success. The supplied final output reached:

```text
PASS: removal restores prior activation; last removal preserves captured profile
No physical collection performed; production project locks and GC remain deferred.
```

The runner reaches this point only after the ordinary-program, parallel-Python,
historical fallback, last-removal, captured-generation and idempotence checks.
The final removal explicitly listed the Python 3.12 aliases being removed,
reported no installed replacement, retained store objects and old profiles,
then published the complete profile. The source was the existing pinned
Nixpkgs revision, not an implicit channel update. No corresponding stale-profile
failure was reported in the owner's Distrobox. This is owner-reported evidence,
separate from agent execution and from the still-pending new VM run.

## Fresh VM acceptance with the existing step 3 payload

Shut down any running Mojt VM. Leave the Distrobox with `exit`; perform this
build on the Debian host. Use a fresh checkout and VM output directory so the
earlier images remain available. The exported step 3 payload does not need
to be regenerated: MPM and its tests are copied from this checkout by the
VM builder.

```sh
cd "$HOME/mojt-lab"
git clone --single-branch --branch feature/mpm-usable-ports \
  https://github.com/kjonasipersson-bert/mojt-linux.git \
  mojt-usable-ports
cd mojt-usable-ports

TARGET="$HOME/mojt-lab/root-test-013"
PAYLOAD="$HOME/mojt-lab/mpm-nix-home/mpm-system-test/system-step3"
KREL="$(uname -r)"
VM="$HOME/mojt-lab/vm/mpm-ports-$(date +%Y%m%d-%H%M%S)"

sudo python3 tools/mojt-vm-build.py \
  --target "$TARGET" \
  --kernel "/boot/vmlinuz-$KREL" \
  --system-payload "$PAYLOAD" \
  --disk-size-mib 6144 \
  --login-mode password --root-shell /bin/sh \
  --output "$VM"

"$VM/run-qemu.sh"
```

Log in and run:

```sh
. /run/mojt-system/environment
mojt-system-check network
mojt-system-check ports
mojt-system-check programs

mpm ports install less vim --dry-run
mpm ports install less vim -y
mpm ports list
less --version
vi --version
```

`ports` selects the guest's saved source pin and installs hello in the normal
Ports profile. `programs` exercises the full new test in a separate lab; its
less/Vim installations do not populate the normal profile. The explicit
installation above therefore also verifies the guest launcher, normal state
root and interactive PATH.

Finally run `systemctl poweroff`, relaunch the **same** `$VM/run-qemu.sh` on
the host and log in again. Before sourcing the environment manually, check:

```sh
command -v mpm
command -v less
command -v vi
mpm ports list
less --version
vi --version
```

Expected: MPM and the selected Ports are available after normal login; the
installed set and active defaults survived the boot. If a custom existing
`/etc/profile` does not source `profile.d`, inspect the add-missing login hook
described above rather than overwriting administrator configuration.
