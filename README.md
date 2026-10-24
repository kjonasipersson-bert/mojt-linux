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

## Backend-free MPM experiment

`tools/mpm-prototype` tests the Ports activation contract with synthetic
commands in a disposable directory. It requires only Linux, Python 3.11+
and `/bin/sh`, with no root privileges, network access or package backend.
See [the experiment guide](docs/mpm-experiment.md) for a complete walkthrough.

```bash
python3 -m unittest discover -s tests -p 'test_mpm_prototype.py' -v
```

## Project layout

```text
bootstrap/      host-side bootstrap backends
manifests/      source manifests used to create Base releases
tools/          Base/VM tools and the backend-free MPM experiment
tests/          integration tests
docs/           manifesto, architecture, and format
```

## License and copyright

Mojt's original tools and documentation are licensed under **GPL-2.0-only**. Copyright (C) 2026 **Jonas Persson**. See `LICENSE`.

Packages and other third-party components included in Base images retain their **own** licenses and respective copyright holders; this repository's GPLv2 notice does not replace those terms. Future external contributors retain their rights unless separately agreed.

