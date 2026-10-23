<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt Linux

**A small Linux base. Independently managed system components and applications.**

*Mojt* is an engineering-slang word from Lund, Sweden, roughly meaning a gadget or contraption.

Mojt is an experimental Linux distribution inspired by BSD's separation of the base operating system and ports. Its initial Base prototype is a versioned filesystem image, not a continuously updated package collection. System services and a future Ports environment are separate concepts.

Read the [manifesto](docs/manifesto.md), [architecture notes](docs/architecture.md), [Base format specification](docs/base-format.md), and the draft [MPM package-management contract](docs/mpm.md).

## Status

**Early prototype, not a bootable distribution.** On x86-64/glibc, the current scripts can bootstrap a userspace from Void packages, pack a Mojt Base release, install parallel generations, add missing configuration defaults, and switch or roll back the active generation. Tests have been run on Linux hosts; there is no boot integration or signed release channel yet.

## Requirements on the build/test host

A Linux x86-64 host with Bash, Python 3.11+, `curl`, `tar`, `zstd`, `sha256sum`, `sudo`, and standard Unix tools. Tests involving `chroot`, `mount`, and `unshare` require appropriate root privileges. No Mojt runtime installation needs Python.

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

`tools/mpm-nix-prototype` evaluates a small TOML selection from an already
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
Actual execution on the owner's machine is pending; regression tests simulate
the backend and namespace operations.

```sh
python3 -m unittest discover -s tests -p 'test_mpm_pacman_prototype.py' -v
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
