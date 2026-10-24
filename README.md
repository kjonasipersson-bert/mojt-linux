<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt Linux

```text
       |  |  |
   +---+--+--+---+
 --|             |--
 --|   .-----.   |--
 --|  (  @@@  )  |--
   |   '-----'   |
   |   |||||||   |
   +---+--+--+---+
       |  |  |
```

**A small Linux base. Independently managed system components and applications.**

*Mojt* is an engineering-slang word from Lund, Sweden, roughly meaning a gadget or contraption.

Mojt is an experimental Linux distribution inspired by BSD's separation of the base operating system and ports. Its Base prototype is a versioned filesystem image, not a continuously updated package collection. System services and Ports are composed separately.

Read the [manifesto](docs/manifesto.md), [architecture notes](docs/architecture.md), [Base format specification](docs/base-format.md), and the draft [MPM package-management contract](docs/mpm.md).

## Status

**Experimental prototype with verified QEMU boot.** On x86-64/glibc, the current
scripts bootstrap and package whole-image Base generations, preserve machine
state, and compose a System VM using pinned Nixpkgs binaries and a host kernel.
The owner has verified systemd boot, persistent `/etc` and `/var`, networking,
and MPM/Nix binary imports with parallel Python versions inside Mojt.
There is no production installer, System release format or signed release
channel yet. See the [System guide](docs/system-nix-vm.md) for measured scope
and remaining integration work.

## Requirements on the build/test host

A Linux x86-64 host with Bash, Python 3.11+, `curl`, `tar`, `zstd`, `sha256sum`, `sudo`, and standard Unix tools. Tests involving `chroot`, `mount`, and `unshare` require appropriate root privileges. Base has no Python runtime requirement; the MPM/Nix System experiment supplies its own management Python. The System guide lists additional Nix preparation and VM-build requirements.

## Quick start

Run these in a trusted throwaway host or VM (the bootstrap invokes privileged package installation inside a chosen rootfs):

```bash
./bootstrap/void.sh

LAB="$HOME/mojt-lab"
sudo ./tools/mojt-base-pack \
    "$LAB/rootfs" manifests/base-0.1.1.toml "$LAB/releases" \
    --packages "$LAB/base-0.1-packages.txt"

sudo ./tools/mojt-base-install install \
    "$LAB/releases/base-0.1.1-x86_64" \
    --target "$LAB/installation"

./tools/mojt-base-install status --target "$LAB/installation"
```

An upgrade/rollback test can be run after the 0.1.1 bootstrap and release are available:

```bash
./tests/test-base-upgrade.sh
```

The test produces Base 0.1.2 with one additional default, then checks installation, preservation of `/etc` and `/var`, and rollback in a separate test target.

## MPM/Nix Ports experiment

The [ordinary Ports guide](docs/mpm-ports.md) covers `mpm ports search`,
`info`, `install`, `list`, `activate` and `remove`, including history-based
fallback and a new opt-in acceptance run. `tools/mpm` is the repository entry
point; newly built step 3 guests expose the same CLI as `mpm`.

The original `tools/mpm-nix-prototype` evaluates a small TOML selection from an already
pinned Nixpkgs source, imports binary outputs and retains private command
profiles. First installation activates the requested commands; later installs
preserve existing activation. No Base/System files or host command paths are
changed. See the [experiment guide](docs/mpm-nix-experiment.md) for the
Distrobox acceptance run, scope and test limitations.

```sh
python3 -m unittest discover -s tests -p 'test_mpm_nix_prototype.py' -v
```

## Frozen pacman environment experiment

`tools/mpm-pacman-prototype` compares original Arch binary packages in separate,
frozen userspaces. Pacman resolves and installs; private profiles select complete
runtime roots through Bubblewrap. See the [experiment guide](docs/mpm-pacman-experiment.md)
for the dedicated Arch Distrobox setup, namespace preflight and opt-in real test.
The owner completed the real environment-level acceptance run. Regression
tests simulate the backend and namespace operations. Nix was subsequently
selected for Ports; this adapter remains the comparison experiment.

```sh
python3 -m unittest discover -s tests -p 'test_mpm_pacman_prototype.py' -v
```

## System VM experiment

The opt-in System work has three cumulative steps: systemd boot with persistent
state, NetworkManager/D-Bus networking, and MPM/Nix inside Mojt. Nix binary
inputs are exported from the existing Distrobox; the Debian VM build host does
not need Nix installed. All three initial acceptance steps passed on the
owner's Mojt VM, including native `hello`, Python 3.12/3.13 activation and a
retained project reference. See the [System guide](docs/system-nix-vm.md) for
preparation, evidence and limitations.

For early Mojt versions, Nix remains exposed and supplies System packages as
well as Ports through a shared store. Mojt controls System activation;
host-service requirements belong to MPM's separate capability model. See the
[accepted interim policy](docs/architecture.md#accepted-early-nixsystem-policy-2026-10-23)
for the decision and implementation boundaries.

```sh
python3 -m unittest discover -s tests -p 'test_system_vm.py' -v
```

## Project layout

```text
bootstrap/      host-side bootstrap backends
manifests/      source manifests used to create Base releases
tools/          Base/VM tools and package-backend experiments
tests/          integration tests
docs/           manifesto, architecture, and format
```

## License and copyright

Mojt's original tools and documentation are licensed under **GPL-2.0-only**. Copyright (C) 2026 **Jonas Persson**. See `LICENSE`.

Packages and other third-party components included in Base images retain their **own** licenses and respective copyright holders; this repository's GPLv2 notice does not replace those terms. Future external contributors retain their rights unless separately agreed.
