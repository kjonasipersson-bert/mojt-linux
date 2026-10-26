<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# System step 7: diagnostics

Step 7 extends the existing cumulative step 6 payload. It retains the pinned
Nixpkgs source and adds six explicit package roles. Base, earlier payload
definitions, account state and service configuration are unchanged.

| Nixpkgs attribute | System commands |
| --- | --- |
| `iputils` | `ping`, `tracepath`, `arping` |
| `bind.dnsutils` | `dig`, `nslookup` |
| `ethtool` | `ethtool` |
| `pciutils` | `lspci` |
| `usbutils` | `lsusb` |
| `strace` | `strace` |
| Existing `iproute2` | additionally export `ss` |
| Existing `kmod` | additionally export `modinfo` |

The exporter evaluates the explicit `bind.dnsutils` output, retains its runtime
closure and validates dig/nslookup before publication. This does not enable a
DNS server. All commands are linked from the selected System profile into
`/run/mojt-system/bin`. Complete runtime dependencies, including any Nix glibc,
are retained without replacing Base libraries or setting LD_LIBRARY_PATH.
The exporter also compiles udev's hardware database from the selected systemd
package's `lib/udev/hwdb.d` using that package's `systemd-hwdb`. Compilation uses
a private root, not host configuration. Its hash is checked with the payload,
and its bytes are copied into the immutable System profile. A missing
persistent `/etc/udev/hwdb.bin` becomes a link to
`/run/mojt-system/hwdb.bin`, selecting the running generation's database.
Existing administrator-owned regular database files are preserved; conflicting
links/directories are refused. No database generation runs at guest boot.
No new daemon, sysctl setting, setuid wrapper or file capability is installed.
Initial ping/arping acceptance is root-operated; ordinary-user privilege policy
is a separate account-integration step.

## Export in the existing Nix Distrobox

Enter `distrobox enter mojt-mpm-nix` on the Debian host, then run the following
inside that container, as the ordinary user. The checkout and payload paths
must be new; retain step 6 and earlier completed VM images.

```bash
bash <<'MOJT_DIAGNOSTICS' || printf '%s\n' 'Diagnostic preparation stopped; see the error above.' >&2
set -euo pipefail
mkdir -p "$HOME/mpm-system-test"
SOURCE="$HOME/mpm-system-test/mojt-system-diagnostics"
PAYLOAD="$HOME/mpm-system-test/system-step7"
test ! -e "$SOURCE"
test ! -e "$PAYLOAD"
test ! -L "$PAYLOAD"
git clone --single-branch --branch feature/system-diagnostics \
  https://github.com/kjonasipersson-bert/mojt-linux.git "$SOURCE"
git -C "$SOURCE" rev-parse HEAD
python3 "$SOURCE/tools/mojt-system-prepare.py" \
  --step 7 --output "$PAYLOAD" --dry-run
python3 "$SOURCE/tools/mojt-system-prepare.py" \
  --step 7 --output "$PAYLOAD" -y
MOJT_DIAGNOSTICS
```

The preview evaluates the exact package outputs and checks realization with
the configured binary-only backend. Export verifies store contents and requires
all listed executables. A missing substitute or command must stop preparation;
do not proceed from partial output. No claim is made that a package definition
alone establishes signed binary-cache availability. After success, exit the
container to the Debian host.

## Build with the retained two kernel sets

The following paths are those retained by the owner's completed kernel test.
The Distrobox home is mounted from `$HOME/mojt-lab/mpm-nix-home` on Debian.
Adjust that mapping if the container configuration differs. The build creates
a fresh image from the original directory installation; it does not import
later state changes from the earlier VM disks. Save the printed test directory.

```bash
bash <<'MOJT_DIAGNOSTIC_VM' || printf '%s\n' 'Diagnostic VM build stopped; see the error above.' >&2
set -euo pipefail
export PATH="/usr/sbin:/sbin:$PATH"
PREVIOUS="$HOME/mojt-generations.9eMyMQ"
. "$PREVIOUS/experiment.env"
. "$PREVIOUS/hardware.env"
. "$HOME/mojt-kernel-test.2csGdx/kernel.env"
SOURCE="$HOME/mojt-lab/mpm-nix-home/mpm-system-test/mojt-system-diagnostics"
PAYLOAD="$HOME/mojt-lab/mpm-nix-home/mpm-system-test/system-step7"
test -f "$SOURCE/tools/mojt-vm-serial.py"
test -f "$PAYLOAD/system.json"
test -f "$KERNEL"
test -d "$MODULES"
test -d "$INPUTS/root"
test -f "$KWORK/root/boot/vmlinuz-$KREL"
test -d "$KWORK/root/lib/modules/$KREL"
TEST_VM="$(mktemp -d "$HOME/mojt-diagnostics.XXXXXX")"
printf 'Test directory: %s\n' "$TEST_VM"
git -C "$SOURCE" rev-parse HEAD >"$TEST_VM/source-commit"
python3 - "$TEST_VM" "$BASE_A" "$KWORK" "$KREL" <<'PY'
import json
from pathlib import Path
import sys
work, base, inputs, release = sys.argv[1:]
fields = dict(base=base, system="system-tools-B",
              kernel=str(Path(inputs) / "root/boot" / f"vmlinuz-{release}"),
              modules_dir=str(Path(inputs) / "root/lib/modules" / release))
Path(work, "generations.toml").write_text(
    "format = 1\n\n[[boot]]\n" +
    "".join(f"{key} = {json.dumps(value)}\n" for key, value in fields.items()))
PY
sudo python3 "$SOURCE/tools/mojt-vm-build.py" \
  --target "$TARGET" --output "$TEST_VM/image" \
  --kernel "$KERNEL" --modules-dir "$MODULES" \
  --firmware-root "$INPUTS/root" --system-payload "$PAYLOAD" \
  --boot-mode uefi --hardware-profile thinkpad-x1-carbon-3 \
  --base-generation "$BASE_A" --system-generation system-tools-A \
  --additional-generations "$TEST_VM/generations.toml" \
  --disk-size-mib 8192 --login-mode password \
  --root-shell /run/mojt-system/bin/bash </dev/tty
python3 "$SOURCE/tools/mojt-vm-serial.py" \
  --source "$TEST_VM/image" --output "$TEST_VM/serial-image"
printf '\nREADY: %s/serial-image/run-qemu.sh\n' "$TEST_VM"
MOJT_DIAGNOSTIC_VM
```

Start the printed launcher separately in the interactive SSH terminal. Select
Base 0.1.3 / system-tools-A first and log in with the new VM password.
Expected kernel A is `6.12.107+deb13-amd64`; B is `7.2.9+deb13-amd64`.
Both choices contain the same step 7 userspace and firmware input.

## Acceptance inside the Mojt guest

```sh
cat /run/mojt-system/version
grep '^VERSION_ID=' /usr/lib/os-release
uname -r
ls -1 /lib/modules/
mojt-system-check diagnostics
mojt-system-check diagnostics-network
mojt-system-check admin
```

The local diagnostic check uses System-first PATH even if Ports shadows a
command. It checks loopback ping/tracepath, tool startup, PCI/USB enumeration,
socket inspection, ext4 module metadata for the running kernel and a traced
BusyBox command in a private temporary directory. The trace is removed on
success or failure. A runtime module tree is required, hence the hardware
profile in the recipe. No public-host ping success is required: QEMU user
networking and external ICMP filtering are separate from tool correctness.

The explicit network check runs the existing boot/DHCP/DNS/HTTPS check, then
dig/nslookup and read-only network driver inspection with ethtool. Set
`MOJT_TEST_INTERFACE` explicitly for a non-Ethernet interface. Driver inspection
may need separate interpretation on devices without ethtool support. The
arping executable is version-checked only; no unsolicited ARP probes or NIC
configuration changes are made. Physical Wi-Fi/USB hardware is not validated
by a QEMU enumeration result.

Inspect remaining Base commands without installing duplicate providers:

```sh
for name in id groups getent hostname; do command -v "$name" || :; done
getent passwd root
getent hosts localhost
id root
```

Write test markers and install a small Ports application under A:

```sh
mojt-system-check persistence-write
mpm ports update -y && mpm ports install hello -y && hash -r && hello
readlink -f "$(command -v hello)" >/var/lib/mojt/diagnostic-hello-path
mpm ports list --exact
```

Power off inside Mojt, start the same launcher and select system-tools-B.
Repeat identity/module, diagnostics, diagnostics-network and admin checks.
Then run:

```sh
mojt-system-check persistence-check
hello
test "$(readlink -f "$(command -v hello)")" = \
     "$(cat /var/lib/mojt/diagnostic-hello-path)" && echo 'PASS: same Ports artifact'
```

Return to system-tools-A and repeat those checks. Keep the earlier step 6
kernel-test VM as a separate reference. This test exercises new userspace on
both kernels, not an in-place System upgrade or automatic boot fallback.

## Validation status

Synthetic regressions cover cumulative roles, unchanged earlier exports,
preserved Base/account data, exact command links, missing DNS command rejection,
and executed local-check success/failure cleanup. They do not establish real
Nix evaluation, signed binary availability or guest behavior of these tools.
The corrected owner-side export and full-Mojt boot acceptance are recorded below.

## Initial owner run and USB correction

The owner exported 191 objects and booted a fresh two-pair serial VM at
`/home/jonasp/mojt-diagnostics.BELV3c`. On the initial tools-A run the network
and admin probes passed. Local ping/tracepath, module metadata and strace also
ran successfully, and hello was imported and activated. However, lsusb emitted
`unable to initialize usb spec` while returning zero, causing the initial local
probe to report a false overall PASS for USB. That initial PASS did not establish USB acceptance; the corrected run below supersedes it.

The owner's strace showed missing compiled hwdb files at all searched paths,
including `/etc/systemd/hwdb/hwdb.bin` and `/etc/udev/hwdb.bin`. The corrected
exporter supplies the database, and the checker treats lsusb stderr as failure
as well as checking its exit status. An empty USB tree is permitted when the
VM has no USB controller; it is not evidence of physical USB device operation.
Re-export to a fresh payload directory, for example `system-step7-hwdb`, and
build toward a new VM output. Retain the initial disk and its test markers.

Synthetic tests cover private compilation, missing compiler output, digest
changes, unsafe persistent configuration, the generation-specific link and
zero-exit USB warnings. Corrected owner acceptance is recorded below.

## Corrected owner VM acceptance (2026-10-26)

The owner exported `system-step7-hwdb` successfully (191 store objects), then
built a new two-pair image and authenticated serial copy at
`/home/jonasp/mojt-diagnostics-hwdb.mIVQjJ/serial-image`. The VM assembly
timestamp was `2026-10-26T14:49:05Z`. Base remained 0.1.3 and both pairs
used the same corrected step 7 userspace and firmware input.

| Boot | Kernel/module release | Result |
| --- | --- | --- |
| system-tools-A | 6.12.107+deb13-amd64 | Supplied full output confirms System identity, database link/presence and successful diagnostics, network and admin checks |
| system-tools-B | 7.2.9+deb13-amd64 | Supplied full output confirms System/kernel/module identity, diagnostics, network/admin, persistent markers and the same hello executable |
| Return to system-tools-A | 6.12.107+deb13-amd64 expected | Owner confirmed the requested return/check sequence succeeded; supplied final excerpt confirms admin, persistence, hello and same-artifact PASS |

The A log shows `/etc/udev/hwdb.bin -> /run/mojt-system/hwdb.bin` and a
nonempty selected System database. The corrected lsusb check passed on A
and B without the earlier initialization warning. USB tree output was empty;
this verifies tool/database startup, not actual USB device enumeration or
physical USB hardware compatibility.

Local checks exercised loopback ping/tracepath, arping version, DNS-tool
startup, ethtool version, PCI listing, socket inspection, running-kernel ext4
module metadata and syscall tracing. Network checks showed DHCP/default route,
DNS/HTTPS, dig/nslookup and e1000e driver inspection with the matching release.
The admin check covered process/memory/disk/mount tools, journal, pager and
temporary vi editing. No new ordinary-user or privileged ping policy was tested.

The owner created the persistent markers and installed hello under A before
switching to B. B and the return to A both reported retained /etc and /var
markers, `Hello, world!` and `PASS: same Ports artifact`, comparing the
resolved executable with the path saved under A. The return excerpt does not
repeat identity or diagnostic output; those checks are owner-confirmed.

This completes manual full-Mojt A → B → A acceptance for the corrected
diagnostic toolset on both kernel/module sets. It is owner-host evidence,
not an agent-run VM test. In-place boot-disk updates, automatic fallback,
physical-device coverage and state rollback remain outside this experiment.
