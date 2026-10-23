<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# System in three small VM steps

**Status:** the owner exported the step 1 payload (69 store objects). After the
preset fix, boot/service health passed on two boots and shutdown reached poweroff.
The persistence check stopped because its `cmp` dependency was absent from Base;
the corrected check still needs to run against the retained markers. Shutdown
used the exitrd's busy-mount/read-only fallback. Full step 1 acceptance and steps
2/3 remain pending.
The existing Base/state VM builder is extended through an opt-in
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
in `/etc` and `/var`. These are text boot IDs, compared with shell builtins after
reading them with `cat`; Base need not provide `cmp`. Missing, empty or different
markers fail the check. The write action refuses to overwrite pre-existing markers.
Check shutdown output as well: an exitrd provides a static BusyBox shutdown
environment for unmount/read-only handling before forced final poweroff.
Successful persistence alone is not a power-loss durability or clean-unmount
proof. The first real run must inspect both boot and shutdown logs.

Step 1 explicitly has no QEMU NIC. Kernel and required module dependencies remain
host supplied and copied to the initramfs; full kernel/firmware packaging and a
bootloader are later work.

### First-boot preset fix

The first real VM boot used Base 0.1.3, System 0.2-step1 and host kernel
7.2.9+deb13-amd64 (VM built 2026-10-23T18:47:01Z). PID 1 and the setup, console,
journal and udev service checks passed. The overall boot check failed on
`proc-sys-fs-binfmt_misc.mount`, `systemd-resolved.service`,
`systemd-timesyncd.service`, `systemd-journalctl-metrics.socket`,
`systemd-resolved-monitor.socket` and `systemd-resolved-varlink.socket`.

The assembly lacked a preset policy. Systemd applies presets at first boot;
without any policy it enables all available units with installation rules.
The corrected start script publishes `99-mojt-vm.preset` containing `disable *`
in `/run/systemd/system-preset` **before** executing PID 1. Mojt's explicit
target dependencies still start the intended services. Administrator presets
in `/etc` retain their normal precedence. Upstream dependency directories are
also excluded when exposed as symlinks.

Pull the updated branch on the Debian host and build a **new VM output** with
the existing payload using the build commands above. No payload re-export is
needed. Preserve the failed VM for inspection; rebuilding from the original
Base/state avoids carrying its first-boot enablement links into the new image.
The boot check continues to reject every failed unit.

### Retest and persistence-check correction

The corrected VM (built 2026-10-23T19:00:10Z) passed `mojt-system-check boot`
before and after restarting the same disk. Its persistence check exited at
`cmp: not found`, before comparing either marker or checking the boot ID. This
was a test dependency error, not evidence of lost state. The corrected check
uses `cat` and shell string comparisons and rejects unreadable/empty/mismatched
markers or the same boot ID. A regression executes it with only `id` and `cat`
in PATH, including positive and negative marker cases.

For an already-built VM, preserve its disk and existing markers. The equivalent
check can be run directly at its root console without rebuilding:

```sh
sh -eu -c '
old="$(cat /etc/mojt-system-persistence-test)"
var="$(cat /var/lib/mojt/system-persistence-test)"
current="$(cat /proc/sys/kernel/random/boot_id)"
[ -n "$old" ]
[ "$old" = "$var" ]
[ "$old" != "$current" ]
echo "PASS: both /etc and /var markers survived a different boot"
'
```

The reported shutdown stopped services, synchronized filesystems, entered the
exitrd and powered off. Exitrd output included `devtmpfs busy - remounted
read-only` and `/dev/vda busy - remounted read-only`; this records the fallback,
not proof that the backing filesystem was fully detached. Final mount flags
were not captured. The console also showed a concatenated command option and
bus-connection errors around shutdown; their exact timing/cause is unresolved.
Run console commands individually and inspect whether the bus error repeats
during an otherwise idle boot. Persistence acceptance remains pending.

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
setup and optional bus/network units. A runtime preset defaults optional units
to disabled before first-boot preset application. Persistent
`/etc/systemd/system` takes precedence. Distribution generators are disabled for
this narrow experiment; Mojt explicitly supplies the required mounts and services. No general fstab,
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
shell syntax. A real offline `systemctl preset-all` regression reproduces the
missing-policy enablement, verifies the generated default-off policy for service,
socket and mount units, and checks administrator preset precedence. It does not
boot systemd. The workspace lacks Nix, QEMU, BusyBox and matching kernel tooling;
it has not imported real payloads or booted these System images.

Recorded checks after the persistence-check fix: all 23 System regressions and all 27
existing VM-builder regressions passed, including shell syntax checks. The earlier
combined suite passed 88 of 89 tests; the unchanged Base root-ownership test
cannot perform chown to UID/GID 1000 in this workspace (EINVAL). Full System
acceptance remains unverified.

```sh
python3 -m unittest discover -s tests -p 'test_system_vm.py' -v
python3 -m unittest discover -s tests -p 'test_vm_builder.py' -v
```

References: [systemd initrd interface](https://systemd.io/INITRD_INTERFACE/),
[unit paths](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html),
[first-boot presets](https://www.freedesktop.org/software/systemd/man/latest/systemd.preset.html),
[NetworkManager configuration](https://www.networkmanager.dev/docs/api/latest/NetworkManager.conf.html),
[store registration export](https://nix.dev/manual/nix/2.35/command-ref/nix-store/dump-db.html)
and [import](https://nix.dev/manual/nix/2.35/command-ref/nix-store/load-db.html).
