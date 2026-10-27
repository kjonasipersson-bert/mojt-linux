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

The [accepted Ports update/recovery model](mpm.md#ports-recovery-and-transaction-history-accepted-2026-10-26)
uses parallel application versions, active selections and readable transaction
history. This iteration implements a first upgrade engine for recorded
Nix attribute requests and a committed history interface. Retained internal
profiles are implementation details; users do not need to manage a whole-Ports
generation after every update. The selector branch adds release-series operations
and explicit format-3 adoption, documented below. General undo remains unimplemented. The command reference lives in [man/mpm.1](../man/mpm.1)
and is included in new System builds with manual support (step 9 or later).

## Selector-mode integration

Native attribute examples below remain valid on unconverted format-1/2 state.
The selector branch adds `ports metadata --catalog FILE [--adopt SELECTOR]`,
selector-aware install/info/activate/upgrade and accepted series aliases. This
explicitly writes format 3; older System MPM readers/writers refuse it. Native
requests keep their old behavior until explicitly adopted. Review the
[selector integration and compatibility contract](mpm-selectors.md#9-implemented-transaction-integration-2026-10-27)
before converting a shared state directory. Real transaction/VM acceptance is
pending; use a new isolated root with `tests/run-mpm-selectors.py` first.

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
mpm ports list --exact
mpm ports activate 'EXACT_IDENTITY_FROM_LIST' --dry-run
mpm ports activate 'EXACT_IDENTITY_FROM_LIST' -y
```

The first install activates default commands. Further versions leave the
default unchanged. Every installed application exports fixed command aliases
containing its upstream version and full Nix output hash. Activation accepts
an installed exact identity; a bare name is accepted only when unambiguous.
It never fetches another version. Release-series selectors remain deferred.
Use `activate EXACT --follow` to explicitly follow its recorded request, provided
that artifact is the request's current target. Without `--follow`, an exact
activation pins the default; an unambiguous bare name follows its current
request target when one exists.

The ordinary `list` view shows **installed versions**, not request constraints:

```text
Installed versions (* = active default):
* hello 2.12.3 [hello]
* less 710 [less]
* vim 9.2.1164 [vim]
```

`list --exact` instead shows exact installed artifact identities, including
the Nix output hash, for activation/removal of a particular build. `list
--json` keeps the detailed records and `identity` field unchanged. An artifact
identity containing `@=` does not mean the user requested an exact-version
lock: `install vim` still resolves a concrete immutable output from the
saved source. Recorded requests, resolved artifacts and active selection policies are
separate concepts. `status` shows all three. Exact active pins result from
explicit selection, never from the mere presence of `@=` in an artifact ID.

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

## Upgrade and recovery history

```sh
mpm ports update --manifest /path/to/local-source-pin.toml --dry-run
mpm ports update --manifest /path/to/local-source-pin.toml -y
mpm ports upgrade --dry-run
mpm ports upgrade hello -y
mpm ports history
mpm ports history --json --limit 10
mpm ports status
man mpm
```

The source must already exist locally and match its declared revision.
`upgrade` uses the saved snapshot, never refreshes it implicitly, and never
changes another area's selections. Repeating `update` without another manifest
keeps the same pin; a subsequent upgrade can therefore legitimately do nothing.

Every explicit name/attribute installation records one request. Several
attributes under one logical name remain independent requests. Their targets
advance together when that name is upgraded, but only the request followed by
the active selection changes unqualified commands. An inactive request stays
inactive. An exact active pin stays on its artifact even if a newer request
target is imported. Old artifacts, fixed aliases and closure/source roots remain.
Reinstalling another build retains it without advancing an existing request
or changing defaults; use approved `upgrade` to advance a request.

The initial version adapter supports dotted integers, refuses numerical
downgrades, and accepts same-version rebuilds with different output hashes.
Changed nonnumeric versions fail rather than guessing an order. This is an
attribute policy, **not** the future `@series` policy: moving an attribute to
another major release may be proposed and must be reviewed in the plan.
There is no `install NAME@series` or exact-release install parser yet.

Changed operations publish metadata **format 2**. Existing format-1 selections
become exact pins; the old files do not establish user intent. To adopt an
existing installation, explicitly `install NAME --attribute ATTRIBUTE`, then
use `activate TARGET --follow` if its active default should follow that
recorded request. An ordinary read, preview or unchanged plan does not migrate.
An old MPM writer refuses format 2; binaries and existing command links remain
usable. Returning to an older System is therefore not the same as returning to
an earlier MPM state. Review the compatibility warning and retain reference disks.

Each successful changed operation publishes `transaction.json` alongside
`state.json` in its profile, with one atomic `current` selection. History follows
the committed parent chain, so failed/unpublished profiles are excluded.
Sequences establish order; UTC timestamps and effective invoking UIDs provide
context, not a tamper-proof audit trail or proof of which sudo user initiated it.
JSON includes the selected catalog and before/after request, policy and active
state; text summarizes installation/removal and selection changes. Legacy
profiles without records end the chain. General undo and pruning are deferred.

`mpm system upgrade` is still design only. Its shared principles are explicit
catalog/request/resolution/selection state, a reviewable plan, retained content
and an atomic commit. Its effect differs: a changed immutable System generation
is prepared for next boot, with selected deployment distinct from running
content. Ports defaults change immediately. A future System updater must validate
persistent MPM metadata compatibility with its bundled writer and preserve
independent Base, Kernel and Ports choices. No account or application data
rollback follows automatically from selecting an older System.

## Upgrade acceptance in an isolated lab

Inside the Nix Distrobox, from this checkout:

```sh
LAB="$(mktemp -d "$HOME/mpm-nix-test/upgrade.XXXXXX")"
python3 tests/run-mpm-nix-upgrade.py --root "$LAB"
```

The default uses one pinned source: it checks real imports, repeat no-ops,
exact pin/follow policy, preview isolation and committed history. To exercise
an actual version change, pass `--from-manifest OLD.toml --to-manifest NEW.toml`
with two already available pinned snapshots and `--name hello` (or another
standalone program). The runner reports explicitly whether a different artifact
was available; a same-snapshot pass is not evidence of a real version upgrade.
It keeps the lab and roots, never operates on the live shared Ports root, and
does not change System. Repeat VM acceptance in a fresh image before merging.

## Removal

```sh
mpm ports list --exact
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
as established. The owner's Distrobox and Mojt VM acceptance below
subsequently passed without a corresponding reported failure.

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
separate from agent execution and from the subsequent VM report.

## Owner-reported Mojt VM acceptance (2026-10-24)

The owner reported that the fresh VM checks and operation after reboot
worked. After reboot, they edited and read `helo.txt` using Vim installed
with MPM. The supplied `mpm ports list` output still showed hello 2.12.3,
less 710 and Vim 9.2.1164 as active. This establishes owner-reported
interactive program use and retention of the installed set across reboot;
the detailed checker/reboot logs were not supplied. It does not establish
that the newly edited file itself survived another reboot.

The report used the earlier list format containing `name@=version-nix-hash`.
The subsequent presentation-only change separates normal version display
from `list --exact`; the owner's report predates that display change.

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

## Upgrade implementation validation (2026-10-26)

Agent-side simulated Nix tests: 47 passed, including following/pinned defaults,
inactive and multiple requests, explicit name filtering, preserved sources and
old artifacts, numerical downgrade/unknown-version rejection, legacy adoption,
request removal/fallback, dry-run/cancellation, failure before publication and
committed transaction ancestry. System assembly tests passed (59, one skipped),
including copying the MPM manual and adding its hierarchy to the default MANPATH.
The roff source rendered with groff without warnings; the VM environment checker
now also locates and renders `mpm(1)`.

The available broader local suite passed 202 tests with eight tool/environment
skips. The separate Base archive ownership test could not run because this
runtime rejects its `chown(..., 1000, 1000)` setup; it remains enabled in CI.
At that validation point real Nix changed-artifact and fresh Mojt VM acceptance
were pending; the subsequent owner-run Distrobox evidence is recorded below.
Earlier Ports and account VM reports do not establish acceptance of this change.

## Owner-reported real upgrade acceptance (2026-10-26)

The owner completed the isolated Distrobox no-op/import/policy/history runner,
then the two-snapshot changed-artifact test:

- Old source: `ac62194c3917d5f474c1a844b6fd6da2db95077d`, archived NixOS 25.05.
- New source: `5adc50831c259f87faeb09ddf930d43597197473`, the retained test snapshot.
- Old artifact: `hello@=2.12.1-nix-na5dnb0l6rjkzrbld3xn4188dd8nknhh`.
- New artifact: `hello@=2.12.3-nix-pa6rydwgjxxmmvdxap7qk9c85h8jbimy`.

The changed-artifact runner passed, retaining the old installation while the
request advanced and an exact active pin remained fixed. Explicit following
activation selected the new artifact, whose executable reported GNU Hello 2.12.3.
A separate fresh profile then passed following-default advancement from 2.12.1
to 2.12.3 and a repeated upgrade published no further profile. Supplied history
showed install, metadata-only source update and upgrade as distinct transactions.

The owner also reported successful exact reactivation of 2.12.1, an upgrade
no-op preserving that pin and the newer request target, and explicit `--follow`
reactivation of 2.12.3 with both installed records retained. History sequences
5 and 6 recorded those selection/policy changes without installations/removals.
These are owner-run real Nix Distrobox results, not agent execution or VM evidence.
The subsequent fresh Mojt VM integration results are recorded below.

## Owner-reported Mojt MPM A/B/A acceptance (2026-10-26)

The owner built a fresh step-10 VM at
`/home/jonasp/mojt-mpm-upgrade.tQvldL/serial-image`, using the new checkout's
MPM and bundled manual. System userspace and Base 0.1.3 were fixed; the boot
sequence was system-mpm-A / 6.12.107+deb13-amd64, system-mpm-B /
7.2.9+deb13-amd64, then A / 6.12.107+deb13-amd64. These are compatible
System profiles with different kernel/module inputs, not two MPM versions or
a test of an existing-disk System updater.

On A, the owner confirmed interactive `man mpm` use. Shared Ports imported
hello 2.12.3, first installation recorded the following request, dry-run and
upgrade with the unchanged snapshot produced no extra transaction, and history
showed the two update/install records. The ordinary mpmtest account could read
history and its attempted shared upgrade was denied with the administrator
requirement. Its user/session/runtime check and home marker were reported
successful on B.

Before switching to B, the supplied test froze complete MPM state/history,
machine and user identity and the hello path in an A checkpoint. A B-side exact
activation changed hello's selection policy to an exact pin while retaining
the installed artifact and request. The B checkpoint was written only after
asserting an upgrade no-op preserved the pinned state and full history.

On the return to A, the owner supplied all final PASS lines: stable machine
and user identities; complete state equality against the B checkpoint with
the exact pin still set; complete history equality; the same hello artifact
and user home marker; and another upgrade no-op preserving state and history.
The journal listed all three boots and retained the previous-boot marker;
/etc, /var, /home and /root persistence checks passed. No failed units remained.
The earlier full root comparison output from B was not pasted; final A evidence
is the complete comparison against B's validated checkpoint, plus the reported
ordinary-user checks on B. Real changed-version upgrade was established in
Distrobox; this VM run establishes integration and metadata persistence across
the two kernel sets, not a changed-version import inside the VM.
