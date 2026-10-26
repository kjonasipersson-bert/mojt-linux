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

The accepted update model keeps Base as complete releases, System as coherent
generations, and Ports as parallel program versions with active selections
and transaction history. Shared MPM verbs preserve those different units of
change. See the [roadmap](docs/roadmap.md) for completed experiments and the
next priorities; these policies are broader than the implemented CLI.

## Status

**Experimental prototype with verified QEMU boot.** On x86-64/glibc, the current
scripts bootstrap and package whole-image Base generations, preserve machine
state, and compose a System VM using pinned Nixpkgs binaries and a host kernel.
The owner has verified systemd boot, persistent `/etc` and `/var`, networking,
and MPM/Nix binary imports with parallel Python versions inside Mojt.
There is no production installer, System release format or signed release
channel yet. See the [System guide](docs/system-nix-vm.md) for measured scope
and remaining integration work.

The owner has also verified explicit Base/System generation selection and
return, persistent markers, authenticated serial-console access from SSH,
and controlled new-image build interruption. The owner subsequently verified
two different kernels with matching modules and retained machine state. Updates
to an existing boot disk remain separate work.

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

An additive [System administration step](docs/system-admin-tools.md) supplies
procps, util-linux, less and a small vi editor (nvi), with a new payload and
an explicit `mojt-system-check admin` acceptance probe.

[System step 5](docs/system-bash.md) adds interactive Bash, a console profile
and persistent root history. Its new-VM recipe explicitly selects Bash for
root login while retaining Base's `/bin/sh`. The opt-in
[UEFI disk boot](docs/uefi-disk-boot.md) builds GPT, an EFI partition with GRUB,
and a disk-contained kernel/initramfs pair. The default direct-boot mode remains
available for comparison.

The opt-in [ThinkPad USB profile](docs/thinkpad-usb-boot.md) prepares local
console login, full versioned kernel modules and Debian firmware for an X1
Carbon 3rd generation. System step 6 adds kmod and Wi-Fi userspace; the same
disk can be probed with SATA and USB storage in QEMU before physical testing.

[System step 7](docs/system-diagnostics.md) adds iputils, DNS client tools,
ethtool, PCI/USB inspection and strace, plus ss/modinfo from existing packages.
It provides separate local and network diagnostic probes and a two-kernel
serial-VM recipe. The owner completed package export and VM acceptance.

[System step 8](docs/system-console-time.md) integrates explicit terminal-size
measurement, persistent bounded journal defaults and systemd-timesyncd.
The owner verified both kernels, stable machine identity, retained journals,
NTP synchronization and quiet login prompts.

[System step 9](docs/system-environment.md) prepares timezone data, man-db and
selected System manuals, retaining C.UTF-8 as the default. The owner verified
export, local timezone, UTF-8 and manual rendering after correcting console
SIGPIPE handling. A separate step 9 A/B run was explicitly deferred to the
next System stage.

For early Mojt versions, Nix remains exposed and supplies System packages as
well as Ports through a shared store. Mojt controls System activation;
host-service requirements belong to MPM's separate capability model. See the
[accepted interim policy](docs/architecture.md#accepted-early-nixsystem-policy-2026-10-23)
for the decision and implementation boundaries.

The [Base/System generation experiment](docs/boot-generations.md) composes
several explicitly pinned boot pairs in one new UEFI image, with shared
persistent state and retained System closures. It includes a compatible Base B
recipe and manual A/A → A/B → B/B → A/A acceptance. This is image composition;
updating an existing running installation remains future work.

The [serial-console guide](docs/vm-serial-console.md) prepares a private copy
of an existing VM for password login and guest commands directly from an SSH
terminal, retaining its generations and persistent state.

```sh
python3 -m unittest discover -s tests -p 'test_system_vm.py' -v
```

The [persistent state layout](docs/state-layout.md) documents how the runtime
`/etc`, `/var`, `/home` and `/root` paths attach to shared machine state, and
how this differs from adding or selecting a boot generation. New home mounting
is prepared for the account stage; real VM acceptance is pending.

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
