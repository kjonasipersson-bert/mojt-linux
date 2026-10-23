<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Frozen binary environments with pacman

**Status:** experimental comparator to the [Nix probe](mpm-nix-experiment.md).
The adapter and simulated-backend tests exist; actual pacman installation and
namespace execution on the owner's machine are pending. This is an environment
backend experiment, not a production MPM package format or a backend decision.

## Scope

Use original Arch binary packages and their resolved dependencies in separate
root filesystems, built from the dated Arch Linux Archive snapshots
`2024/06/01` and `2025/06/01`. Exact Python versions and available signatures
are determined during the real run; archive access has not been verified from
the agent's environment. There is no source build, AUR or System/boot setup.

Pacman resolves and installs the packages. MPM records the snapshot, copies
of repository metadata, exact resolved versions, package archive SHA256 values,
and exported commands. Each environment retains its own local package database.
Package archives are retained in a cache per catalog, so a later catalog cannot
overwrite an older archive with the same filename. No shared cache optimization
is attempted in this first probe.

Bubblewrap provides the runtime filesystem view: the environment root is
mounted read-only as `/`, including its own `/usr` and dynamic loader. The
caller's current directory is bind-mounted at `/work`; that is also the runtime
HOME and working directory. `/tmp` and `/run` are temporary, `/dev` is minimal,
and `/proc` describes the runtime PID namespace. Network access is inherited,
and `/etc/resolv.conf` and `/etc/hosts` are bound from the outer container.
There is no host `/usr` bind in the runtime. Absolute host file paths outside
`/work` are not generally accessible. Desktop, device and service integration
remain untested. This is not a general-purpose security sandbox policy.

Unlike the Nix probe, the retained unit is an **entire environment**. Switching
`cli` changes all its exports together. Independent per-application selection
inside a shared environment is not implemented. This difference is a central
comparison result to assess, not an assumption that the final MPM contract has
changed. Conventional CLI execution now goes through a launcher and namespace;
its usability/cost still needs evaluation against Mojt's native-execution goal.

## Prepare a separate Arch Distrobox

On the Debian host, outside the existing Nix Distrobox:

```sh
mkdir -p "$HOME/mojt-lab/mpm-pacman-home"
distrobox create --name mojt-mpm-pacman \
  --image docker.io/library/archlinux:latest \
  --home "$HOME/mojt-lab/mpm-pacman-home" --no-entry
distrobox enter mojt-mpm-pacman
```

Inside the new container:

```sh
sudo pacman -Syu --needed archlinux-keyring gnupg ca-certificates bubblewrap python git
mkdir -p "$HOME/mpm-pacman-test"
cd "$HOME/mpm-pacman-test"
git clone --single-branch --branch experiment/pacman-environments \
  https://github.com/kjonasipersson-bert/mojt-linux.git mojt-pacman-adapter
cd mojt-pacman-adapter

python3 tools/mpm-pacman-prototype \
  --root "$HOME/mpm-pacman-test/preflight-state" ports check
```

`check` verifies that nested user/mount/PID namespaces and chroot work, without
creating the MPM root or fetching archive packages. In the builder namespace,
UID 0 maps to the ordinary container user; it is not Debian host root. Run
the adapter without sudo. Package-tool setup is the only sudo step.

If namespace creation is denied, report that output before continuing. A
different container setup or a dedicated VM may be needed. The agent workspace
has Bubblewrap 0.9.0 but UID mapping was denied (`Operation not permitted`),
so it cannot validate the actual namespace run.

The image and builder packages are a current tool environment; the two guest
userspaces come exclusively from the selected historical repositories. Builder
versions are printed during preflight. Old snapshots are test inputs rather
than a proposed Mojt update policy.

## Run the complete real comparison

After successful preflight, inside the Arch container/repository:

```sh
MPM_PACMAN_LAB="$(mktemp -d "$HOME/mpm-pacman-test/environments.XXXXXX")"
python3 tests/run-mpm-pacman-environments.py --root "$MPM_PACMAN_LAB"
```

This explicitly imports packages, creates profiles and changes the active
environment in that new root. It retains all results after success or failure.
The runner checks:

- Metadata refresh and preview do not install applications.
- Both binary environments run different Python versions and load `ssl`,
  `zlib` and their own glibc. Each runtime reads an environment-specific stamp
  from `/etc/mojt-environment`, including in a spawned interpreter.
- The environment `/usr` is read-only, while `/work` supports file reads/writes.
- Installing B leaves A active; explicit activation selects B.
- The captured A profile still runs A, with unchanged project-reference bytes.
- HTTPS works in both environments with their installed certificate packages
  and the explicitly shared networking/resolver configuration.
- Repeating install does not publish another generation.

The captured `<root>/test-project/pin.json` is an experiment reference, not a
production project lock. It does not prove removal/GC protection or upgrade
policy enforcement. There is no `upgrade`, `remove` or cleanup command.

## Manual command model

```sh
mpm() { python3 tools/mpm-pacman-prototype --root "$MPM_PACMAN_LAB" ports "$@"; }
mpm update --manifest manifests/mpm-pacman-a.toml -y
mpm install --dry-run
mpm install -y
"$MPM_PACMAN_LAB/current/bin/python3" --version
mpm status
```

The first install of an environment activates its exports. Later imports
retain existing selection. `activate EXACT_ENVIRONMENT_ID` only selects a
retained environment; `run EXACT_ENVIRONMENT_ID COMMAND -- ARGUMENTS` bypasses
the default selection. Fixed launchers named `COMMAND-env-ENVIRONMENT_ID`
remain alongside the defaults. These identities are experimental conventions.
Generated launchers use POSIX sh and the builder's absolute Bubblewrap path;
ordinary command execution does not need the adapter or outer Python. The
management CLI and acceptance runner still need Python. Launchers retain
absolute environment paths, so the lab must stay at its original location.

`update --dry-run` prints the intended snapshot refresh without resolving or
writing repository metadata. Real `update` fetches metadata, resolves the
whole package set against an empty local database, and saves the plan. Install
uses the saved sync databases and does not refresh them. The actual installed
versions and cached archive digests must match the saved plan before an
environment is published. A single profile symlink replacement selects a
complete generation, and previous generations are retained. A failed build
may leave a staging directory/cache for inspection; fsync durability, recovery
and cleanup are not implemented.

Only the lab directory is writable in the builder's outer filesystem view.
Pacman scriptlets and hooks execute within the guest staging root with minimal
device/proc mounts. The child user namespace receives capabilities needed for
chroot/file ownership; runtime applications receive no capabilities. Guest
files are physically owned by the ordinary user in this single-user probe.
It does not validate System service accounts or a production installer's UID/GID
handling. Local owners can edit stored roots, so immutability here is logical
plus read-only runtime mounting, not protection against that owner.

## Authentication and validation status

The isolated keyring is initialized from the builder's installed
`archlinux-keyring`. Package signatures are required. Database signatures are
optional, matching the configured `Required DatabaseOptional` policy; no claim
of independently authenticated historical repository snapshots is made.
SHA256 values identify metadata/package bytes and detect changes; they do not
replace signature verification. Signature/key/archive failures stop the run.

Agent-side checks: 15 simulated-backend regression tests passed, and the adapter,
live runner and embedded Python probe passed syntax checks. The local Bubblewrap
attempt failed at UID mapping, and pacman is unavailable locally. Neither those
unit tests nor the syntax checks establish real pacman/Bubblewrap compatibility.

```sh
python3 -m unittest discover -s tests -p 'test_mpm_pacman_prototype.py' -v
```

References: [pacman](https://man.archlinux.org/man/pacman.8.en),
[Bubblewrap](https://man.archlinux.org/man/bwrap.1.en),
[Distrobox creation](https://distrobox.it/usage/distrobox-create/),
[Arch Linux Archive](https://wiki.archlinux.org/title/Arch_Linux_Archive).
