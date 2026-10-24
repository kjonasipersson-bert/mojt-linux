<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# System in three small VM steps

**Status:** step 1 boot/service health and `/etc` + `/var` persistence across
boots passed on the owner's VM. Shutdown reached poweroff using the exitrd's
busy-mount/read-only fallback; complete storage detachment remains unverified.
Step 2 boot/service health, DHCPv4, routing, DNS resolution and HTTPS over IPv4
passed in the owner's VM through the direct checks below, with no failed units.
Step 3 passed both the corrected network probe and the complete MPM/parallel
Python check in a fresh Mojt VM. All three initial acceptance steps are complete;
production release/deployment and upgrade policies remain open.
The existing Base/state VM builder is extended through an opt-in
`--system-payload` argument. Existing BusyBox-init VMs remain usable.

The owner selected Nix for Ports after the Nix and pacman comparisons.
Following the successful VM run, the owner also selected Nix for System
packages for now, with a shared store/database and exposed Nix CLI in early
versions. Mojt retains System generation and service activation control;
host-service requirements are to be modeled separately in MPM. See the
[accepted policy](architecture.md#accepted-early-nixsystem-policy-2026-10-23).
The experiment uses the same pinned Nixpkgs source for System binaries,
without adopting NixOS or deciding a production System release format.
Mojt supplies the early-boot assembly and service configuration. Host-capability
checks and reconciliation of direct Nix changes remain unimplemented.

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
during an otherwise idle boot.

### Recorded step 1 acceptance

On the next boot of the same disk (journal beginning 2026-10-23T19:11:11),
`mojt-system-check boot` passed again. The direct text-marker check above passed
twice: both persistent files held the same nonempty ID, different from the
current kernel boot ID. `systemctl --failed --no-pager` reported `0 loaded units
listed`, without the earlier bus-connection error.

This establishes the initial boot/service-health and two-boot state acceptance
for step 1. The owner ran the direct equivalent because this retained image
still contains the old `cmp`-dependent check. Full storage detachment, the prior
shutdown-time bus errors and recurring clocksource watchdog timeouts remain
follow-up items; no power-loss durability guarantee is inferred. Proceed to
step 2 with a new payload/image and retain this step 1 disk.

## Step 2: networking

Shut down the step 1 VM with `systemctl poweroff`. On the Debian host, enter
the existing Nix Distrobox with `distrobox enter mojt-mpm-nix`. Inside it, update
the checkout and prepare a new payload:

```sh
cd "$HOME/mpm-system-test/mojt-system-adapter"
git pull --ff-only

python3 tools/mojt-system-prepare.py \
  --step 2 --output "$HOME/mpm-system-test/system-step2" --dry-run

python3 tools/mojt-system-prepare.py \
  --step 2 --output "$HOME/mpm-system-test/system-step2" -y

exit
```

Back on the Debian host, update its separate checkout and build a new VM:

```sh
cd "$HOME/mojt-lab/mojt-system-adapter"
git pull --ff-only

TARGET="$HOME/mojt-lab/root-test-013"
PAYLOAD="$HOME/mojt-lab/mpm-nix-home/mpm-system-test/system-step2"
KREL="$(uname -r)"
VM="$HOME/mojt-lab/vm/system-step2-$(date +%Y%m%d-%H%M%S)"

sudo python3 tools/mojt-vm-build.py \
  --target "$TARGET" \
  --kernel "/boot/vmlinuz-$KREL" \
  --system-payload "$PAYLOAD" \
  --disk-size-mib 4096 \
  --login-mode password --root-shell /bin/sh \
  --output "$VM"

"$VM/run-qemu.sh"
```

The launcher supplies a QEMU user-network VirtIO NIC without inbound port
forwarding; matching `virtio_net` dependencies are added to the initramfs.

Inside that VM:

```sh
. /run/mojt-system/environment
mojt-system-check network
```

The check observes autoconnection without reactivating the device. It polls
kernel IPv4 address and default-route state on the selected Ethernet interface
for up to 30 seconds before testing DNS and HTTPS over IPv4. A timeout prints
NetworkManager's device state and remains a failure.

NetworkManager uses its internal DHCP client, keyfile configuration, and an
explicit regular `/etc/resolv.conf`. Existing resolver symlinks or conflicting
experiment configuration stop image construction rather than being overwritten.
The copied connection/network state can evolve normally inside the VM.

The D-Bus service has its own sysusers-created account and socket activation.
This initial bus policy permits root management; NetworkManager uses root-only
authorization without a Polkit agent. It is not a desktop or multiuser policy.
Wi-Fi, VPNs, DNS caching and service activation beyond these explicit units
are not acceptance targets.

### First step 2 VM and probe correction

The owner exported 119 store objects and built System 0.2-step2 / Base 0.1.3
at 2026-10-23T19:18:11Z with kernel 7.2.9+deb13-amd64. Boot/service health,
including D-Bus and NetworkManager 1.58.1, passed. The original probe then ran
`nmcli device connect eth0` and immediately read `IP4.ADDRESS`; that readout
was empty and stopped the check.

The supplied diagnostic log shows that the internal DHCP client had already
obtained `10.0.2.15/24` at 19:18:23. The probe caused a new activation at
19:18:51, with another successful lease in the same second. Later kernel and
NetworkManager output agree on the address, gateway `10.0.2.2`, and DHCP-provided
DNS server `10.0.2.3`. Both IPv4/IPv6 methods are `auto` with `may-fail=yes`.
The exact reason for the earlier empty readout is unconfirmed; it is not
evidence that DHCP is broken or that the initial boot only configured IPv6.

The corrected probe avoids that extra activation and waits for kernel address
and route state. Simulated shell regressions cover an already-ready interface,
delayed address/route publication, and bounded failure when either is absent;
DNS/HTTPS are reached only after both appear.

Complete the remaining checks directly in the retained VM:

```sh
. /run/mojt-system/environment
ip -4 route show default dev eth0
getent hosts cache.nixos.org
curl --ipv4 --fail --show-error --silent --max-time 30 \
  https://cache.nixos.org/nix-cache-info
systemctl --failed --no-pager
```

Expect a default route through `10.0.2.2`, successful name lookup and cache-info
response, and no failed units. The installed probe in this older image still
contains the reconnect/readout behavior; a future image built from the updated
host checkout includes the correction without re-exporting the same payload.

### Recorded step 2 acceptance

The owner completed the direct checks in the retained step 2 VM. The kernel
reported `default via 10.0.2.2 proto dhcp src 10.0.2.15 metric 100`.
`getent hosts cache.nixos.org` resolved the name and returned IPv6 addresses;
the separate `curl --ipv4` request successfully resolved/used IPv4 and verified
HTTPS, returning `StoreDir: /nix/store`, `WantMassQuery: 1`, and `Priority: 40`.
`systemctl --failed --no-pager` reported zero loaded units.

Together with the earlier service and DHCP diagnostics, these results pass
the initial step 2 networking acceptance. The corrected combined network probe
subsequently passed in the fresh step 3 VM, as recorded below.
This does not extend acceptance to Wi-Fi, VPNs, desktop
authorization or general service activation.

## Step 3: MPM/Nix inside Mojt

Shut down the step 2 VM with `systemctl poweroff`. On the Debian host, enter
the existing Nix Distrobox with `distrobox enter mojt-mpm-nix`. Prepare another
new payload inside it:

```sh
cd "$HOME/mpm-system-test/mojt-system-adapter"
git pull --ff-only

python3 tools/mojt-system-prepare.py \
  --step 3 --output "$HOME/mpm-system-test/system-step3" --dry-run

python3 tools/mojt-system-prepare.py \
  --step 3 --output "$HOME/mpm-system-test/system-step3" -y

exit
```

Step 3 includes Nix, management Python and the pinned Nixpkgs source in addition
to all step 2 inputs. Source export can take longer and occupy more space.
Back on the Debian host, update its checkout and build a new 6144 MiB VM disk:

```sh
cd "$HOME/mojt-lab/mojt-system-adapter"
git pull --ff-only

TARGET="$HOME/mojt-lab/root-test-013"
PAYLOAD="$HOME/mojt-lab/mpm-nix-home/mpm-system-test/system-step3"
KREL="$(uname -r)"
VM="$HOME/mojt-lab/vm/system-step3-$(date +%Y%m%d-%H%M%S)"

sudo python3 tools/mojt-vm-build.py \
  --target "$TARGET" \
  --kernel "/boot/vmlinuz-$KREL" \
  --system-payload "$PAYLOAD" \
  --disk-size-mib 6144 \
  --login-mode password --root-shell /bin/sh \
  --output "$VM"

"$VM/run-qemu.sh"
```

Increase the launcher's memory if needed for Nixpkgs evaluation. Inside the VM:

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

### Recorded step 3 acceptance (2026-10-23)

The owner exported 162 store objects and booted System 0.2-step3 / Base 0.1.3
with host kernel 7.2.9+deb13-amd64 (VM built 2026-10-23T19:31:14Z). Both
`mojt-system-check network` and `mojt-system-check ports` passed in Mojt.
The network probe observed `10.0.2.15/24` and its default route without
reactivating the connection, then completed DNS and HTTPS over IPv4.

The Ports test evaluated the retained Nixpkgs source at revision
`5adc50831c259f87faeb09ddf930d43597197473`, imported binary outputs from
`cache.nixos.org`, and produced these results:

| Check | Result inside the Mojt VM |
| --- | --- |
| First application | hello 2.12.3 imported, activated and printed `Hello, world!` |
| Parallel versions | Python 3.12.15 and 3.13.16 installed under one Ports name |
| Installation policy | Installing 3.13 preserved the existing active 3.12 |
| Runtime dependencies | Both interpreters loaded `ssl` and `zlib` |
| Retention | Both interpreter outputs had MPM GC-root registrations |
| Activation policy | Explicit activation selected 3.13 while the captured generation still executed 3.12 |
| Repeat installation | Printed `No changes.` and preserved the profile and project reference |

Hello state remains at `/var/lib/mojt/ports`. The Python experiment remains at
`/var/lib/mojt/python-acceptance-f3b8eea1-091a-4d70-9594-2e8ce50f6dad`, with its
captured reference in `test-project/pin.json`. This is evidence of the narrow
adapter running inside a booted Mojt system, beyond the earlier Distrobox run.
Production project profiles/locks, upgrades, removal and GC policy remain open.

This completes the three initial System steps. It does not establish a
production System release format, general service integration or power-loss
durability. A post-import guest reboot has not yet been reported. The earlier
shutdown read-only fallback and recurring clocksource watchdog timeout still
need separate investigation; the timeout did not prevent these checks passing.

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

Recorded checks after the network-probe fix: all 25 System regressions and all 27
existing VM-builder regressions passed, including shell syntax checks. The earlier
combined suite passed 88 of 89 tests; the unchanged Base root-ownership test
cannot perform chown to UID/GID 1000 in this workspace (EINVAL). Separately,
the owner has now passed all three initial real VM acceptance steps above.

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
