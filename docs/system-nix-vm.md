<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# System in three small VM steps

**Status:** implementation prepared; real payload import and QEMU acceptance
are pending. The existing Base/state VM builder is extended through an opt-in
`--system-payload` argument. Existing BusyBox-init VMs remain usable.

The owner selected Nix for Ports after the Nix and pacman comparisons.
This experiment also uses the same pinned Nixpkgs source to supply System
binaries, without adopting NixOS or deciding a production System release format.
Mojt supplies the early-boot assembly and service configuration.

| Step | Added components | Acceptance in the Mojt VM |
| --- | --- | --- |
| 1 | systemd, journal, udev, serial console | PID 1, service health, poweroff and state across boots |
| 2 | D-Bus, NetworkManager, curl, CA bundle, iproute2 | VirtIO Ethernet, DHCP, routing, DNS and HTTPS |
| 3 | Nix, management Python, MPM prototype, pinned Nixpkgs source | Binary Ports imports, parallel Python and saved activation |

Each step is cumulative. Build a new payload and VM for each step. They are
isolated experiments, not an in-place upgrade procedure for the preceding VM.
Use the same disk twice when testing persistence.

## Prepare step 1 inside the existing Nix Distrobox

Enter `mojt-mpm-nix`, not the Arch comparator container. No sudo is used here:

```sh
mkdir -p "$HOME/mpm-system-test"
cd "$HOME/mpm-system-test"
git clone --single-branch --branch experiment/system-nix-vm \
  https://github.com/kjonasipersson-bert/mojt-linux.git mojt-system-adapter
cd mojt-system-adapter

python3 tools/mojt-system-prepare.py \
  --step 1 --output "$HOME/mpm-system-test/system-step1" --dry-run

python3 tools/mojt-system-prepare.py \
  --step 1 --output "$HOME/mpm-system-test/system-step1" -y
```

The default source manifest reuses the previously tested source at
`/nix/store/4abi8hv3y6sxq7lgwlllclkjlnx65gd4-nixpkgs/nixpkgs`,
revision `5adc50831c259f87faeb09ddf930d43597197473`. Other machines must pass
`--source-manifest FILE` with their actual local pin.

The preparation tool evaluates the requested attributes, previews their output
imports, and realises only output paths. No derivations or custom source builds
are requested. Missing substitutes are errors. Nix's configured signature checks
remain in force. Temporary GC roots protect source/outputs during copying.

The self-contained output has `system.json`, `nix/store/` and a subset database
`registration` from `nix-store --dump-db`. Nix verifies original store contents
before copying; an additional digest records each exported tree, including
symlinks and modes. The VM builder checks these transfer digests. They provide
integrity/change detection, not signed Mojt releases or protection from an owner
who can replace the payload and metadata together.

Output directories must not exist. Failed preparation does not publish a partial
payload; already imported objects may remain in the Distrobox Nix store.
Step 3 also exports the source tree and can use substantially more disk space.

## Build on the Debian host

Exit the Distrobox. The Debian host still does not need Nix. It needs the
dependencies from [the original VM guide](vm-boot.md), the installed Mojt Base,
and a matching host kernel/modules pair.

```sh
git clone --single-branch --branch experiment/system-nix-vm \
  https://github.com/kjonasipersson-bert/mojt-linux.git \
  "$HOME/mojt-lab/mojt-system-adapter"
cd "$HOME/mojt-lab/mojt-system-adapter"

TARGET="$HOME/mojt-lab/root-test-013"
PAYLOAD="$HOME/mojt-lab/mpm-nix-home/mpm-system-test/system-step1"
KREL="$(uname -r)"
VM="$HOME/mojt-lab/vm/system-step1-$(date +%Y%m%d-%H%M%S)"

sudo python3 tools/mojt-vm-build.py \
  --target "$TARGET" \
  --kernel "/boot/vmlinuz-$KREL" \
  --system-payload "$PAYLOAD" \
  --disk-size-mib 2048 \
  --login-mode password --root-shell /bin/sh \
  --output "$VM"

"$VM/run-qemu.sh"
```

Adjust TARGET and PAYLOAD to the actual existing paths. The payload path shown
is the host-side location for the previously configured custom Distrobox home.
Select a different installed kernel pair if the running kernel's image/modules
are absent. Output directories must be new.

Password mode retains the existing VM-builder provisioning behavior: credentials
are preserved or interactively created only in copied VM state. The BusyBox
getty/login applets remain temporary System console tools supervised by systemd;
PAM/logind/user-session integration is not implemented. An existing inittab
remains machine state but is not used by systemd.

The builder adds empty mountpoint scaffolding to the VM copy of Base and
copies the System payload to a separate store. The source installation,
published Base releases and old VM images are untouched. `build.json` records
the System step, Nixpkgs source, Base and actual kernel release.

## Step 1: boot and state

At the VM root console:

```sh
. /run/mojt-system/environment
mojt-system-check boot
mojt-system-check persistence-write
systemctl poweroff
```

Start the **same** VM disk again using its `run-qemu.sh`, log in, then:

```sh
. /run/mojt-system/environment
mojt-system-check boot
mojt-system-check persistence-check
systemctl --failed
```

The persistence check requires a different kernel boot ID and matching markers
in `/etc` and `/var`. It refuses to overwrite pre-existing test markers.
Check shutdown output as well: an exitrd provides a static BusyBox shutdown
environment for unmount/read-only handling before forced final poweroff.
Successful persistence alone is not a power-loss durability or clean-unmount
proof. The first real run must inspect both boot and shutdown logs.

Step 1 explicitly has no QEMU NIC. Kernel and required module dependencies remain
host supplied and copied to the initramfs; full kernel/firmware packaging and a
bootloader are later work.

## Step 2: networking

In the Nix Distrobox checkout, prepare a new payload:

```sh
python3 tools/mojt-system-prepare.py \
  --step 2 --output "$HOME/mpm-system-test/system-step2" -y
```

On the host, repeat VM construction with the `system-step2` payload and a new
VM output. Retain password mode and use at least 4096 MiB disk space.
The launcher supplies a QEMU user-network VirtIO NIC without inbound port
forwarding; matching `virtio_net` dependencies are added to the initramfs.

Inside that VM:

```sh
. /run/mojt-system/environment
mojt-system-check network
```

NetworkManager uses its internal DHCP client, keyfile configuration, and an
explicit regular `/etc/resolv.conf`. Existing resolver symlinks or conflicting
experiment configuration stop image construction rather than being overwritten.
The copied connection/network state can evolve normally inside the VM.

The D-Bus service has its own sysusers-created account and socket activation.
This initial bus policy permits root management; NetworkManager uses root-only
authorization without a Polkit agent. It is not a desktop or multiuser policy.
Wi-Fi, VPNs, DNS caching and service activation beyond these explicit units
are not acceptance targets.

## Step 3: MPM/Nix inside Mojt

Prepare another new payload in the Nix Distrobox:

```sh
python3 tools/mojt-system-prepare.py \
  --step 3 --output "$HOME/mpm-system-test/system-step3" -y
```

Build a new host VM with that payload and at least 6144 MiB disk space.
Increase the launcher's memory if the host needs more for Nixpkgs evaluation.
Inside the VM:

```sh
. /run/mojt-system/environment
mojt-system-check network
mojt-system-check ports
```

On first boot, setup loads only the exported store registration and roots the
System objects/source. This root-operated, binary-import-only test has no Nix
daemon, build users or automatic GC. Package signatures remain required and
local source builds are disabled. Ordinary-user administration, daemon/socket
permissions and production removal/GC policy are separate work.

MPM's default experiment state is `/var/lib/mojt/ports`. Its user-facing wrapper
accepts actions such as `mpm status` and `mpm install -y`. The Ports check imports
hello from the binary cache, then reuses the existing Python 3.12/3.13 acceptance
runner in a fresh `/var/lib/mojt/python-acceptance-UUID` root. Both roots remain
available. Management Python belongs to this System experiment; Base still has
no required Python runtime. Captured project references remain experimental.

## Filesystem and service assembly

The disk keeps separate `base/`, `state/`, `system/` and `nix/` trees.
Early boot selects Base, binds persistent state and the store, exposes the
selected System profile read-only at `/run/mojt-system`, and starts systemd
through that profile. `/run` and `/tmp` are volatile. The containing disk remains
reachable at `/run/mojt-disk`.

The profile reuses Nixpkgs systemd vendor unit files, with Mojt-owned console,
setup and optional bus/network units. Persistent `/etc/systemd/system` takes
precedence. Distribution generators are disabled for this narrow experiment;
Mojt explicitly supplies the required mounts and services. No general fstab,
automount or NixOS activation implementation is implied.

Nixpkgs binaries can encode distribution assumptions (for example systemd's
compiled tty GID and default shell locations). BusyBox supplies console login
here and the VM uses preloaded VirtIO drivers. Broader account, firmware, PAM,
device and service integration still needs verification. This is a deliberate
test of the integration boundary, not evidence that arbitrary System packages
work merely because their store objects are present.

Agent-side validation uses synthetic package trees and a simulated Nix backend.
It covers transfer integrity, missing/extra objects, failed/previews exports,
state preservation, authenticated console selection, service generation and
shell syntax. The workspace lacks Nix, QEMU, BusyBox and matching kernel tooling;
it has not imported real payloads or booted these System images.

Recorded checks: all 20 System regressions and all 27 existing VM-builder
regressions passed. The combined suite passed 88 of 89 tests; the unchanged
Base root-ownership test cannot perform chown to UID/GID 1000 in this workspace
(EINVAL). Syntax/help checks passed. No real System boot success is claimed.

```sh
python3 -m unittest discover -s tests -p 'test_system_vm.py' -v
python3 -m unittest discover -s tests -p 'test_vm_builder.py' -v
```

References: [systemd initrd interface](https://systemd.io/INITRD_INTERFACE/),
[unit paths](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html),
[NetworkManager configuration](https://www.networkmanager.dev/docs/api/latest/NetworkManager.conf.html),
[store registration export](https://nix.dev/manual/nix/2.35/command-ref/nix-store/dump-db.html)
and [import](https://nix.dev/manual/nix/2.35/command-ref/nix-store/load-db.html).
