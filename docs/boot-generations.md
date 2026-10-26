<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Base/System boot generation experiment

For terminal-based operation of an already built VM, see the
[SSH/serial console and interruption guide](vm-serial-console.md). It retains
the tested image's state in a separate copy and avoids graphical command entry.

The [accepted MPM update model](mpm.md#system-generations-and-boot-deployments-accepted-2026-10-26)
distinguishes complete Base releases, System userspace generations and exact
Kernel builds, combined in a boot deployment. The builder below is a
fresh-image experiment: its System labels also bind kernel inputs, and its
on-disk layout is not the final independent Kernel/deployment interface.
A subsequent owner VM test changed the kernel and matching modules and returned
to the retained pair; see [the measured result](#owner-different-kernel-acceptance-2026-10-26)
and the [roadmap](roadmap.md).

The UEFI builder can compose a **new** image containing several explicit
Base/System pairs. GRUB selects a pair; initramfs checks `root=UUID=...`,
`mojt.base=...` and `mojt.system=...` against its embedded expectations. It
never follows `base/current` or `system/current`. Missing, duplicate or
different selections stop in the early-boot recovery shell.

This is host-side image composition, not installation onto a running Mojt
machine or an existing USB disk. Keep the already verified disk image and
USB installation as the recovery reference. No existing image is opened for
writing. A failed or interrupted build cannot publish the new output directory;
SIGKILL/power loss may leave a private `.mojt-vm-*` staging directory for manual
inspection. Power-loss-safe updates to an existing boot disk are future work.

## Identity and filesystem layout

| Path on the Mojt partition | Meaning |
| --- | --- |
| `base/<base>/` | Installed Base generation, with only image-local mountpoint scaffolding |
| `system/<system>/` | Exact System profile, registration, tools and optional hardware modules/firmware |
| `boot/mojt/<system>/<base>/` | Kernel, pair-specific initramfs, input hashes and single-pair recovery config |
| `boot/mojt/grub.cfg` | Menu of verified explicit pairs; first build pair is the default |
| `state/etc`, `state/var` | Shared persistent state for every boot selection |
| `nix/store` | Shared closure; an existing store object must have identical bytes/links/modes |

System names are explicit build labels, not a finalized release format or
automatically assigned version. Reusing a System label with different profile
contents, kernel or early module inputs aborts the build. Each System receives
its own Nix registration marker and retained closure roots, including before
it is first booted. No generation removal or garbage collection is provided.

For this experiment, additional Bases must declare exactly the same glibc ABI
and state policy as the first Base. This conservative gate is not a complete
ABI analysis or a state migration policy. `/etc` and `/var` retain their
contents across all boot choices. Selecting an old pair does not undo database
changes. The image starts from the directory installation's state; it does
not import later changes from the existing booted USB installation.

## Prepare an intentionally compatible Base B

Run from this branch on the Debian build host. `TARGET` is the existing
directory installation used for the previous hardware/VM build. This creates
one new Base release from the installed Base A, changing its version and
adding a harmless marker; existing generations are retained. Installation
uses `--no-activate`, so the source `base/current` is preserved. The installer
still applies its usual add-missing configuration policy.

Paste each complete block, including its final heredoc delimiter. The blocks
run in a separate Bash process: an error stops that process and prints a
diagnostic without changing the SSH login shell's options or exiting it.
Adjust `TARGET` if the installed Base lives elsewhere. Preparation prints its
retained work directory and saves the values needed by the build, so they do
not depend on variables surviving an SSH reconnect.

```bash
bash <<'MOJT_PREPARE' || printf '%s\n' 'Base preparation stopped; see the error above.' >&2
set -euo pipefail
trap 'printf "Base preparation failed at line %s; work directory: %s\\n" "$LINENO" "${WORK:-not created}" >&2' ERR
export PATH="/usr/sbin:/sbin:$PATH"
TARGET="$HOME/mojt-lab/root-test-013"
if [ ! -L "$TARGET/base/current" ]; then
  printf 'No installed Base selection at %s/base/current; correct TARGET.\n' "$TARGET" >&2
  exit 1
fi
BASE_A="$(readlink "$TARGET/base/current")"
BASE_B="${BASE_A}-gen-b"
WORK="$(mktemp -d "$HOME/mojt-generations.XXXXXX")"
sudo cp -a -- "$TARGET/base/$BASE_A" "$WORK/rootfs"
sudo install -d "$WORK/rootfs/usr/share/mojt"
printf 'Compatible generation experiment Base B\n' |
  sudo tee "$WORK/rootfs/usr/share/mojt/generation-test" >/dev/null
python3 - "$TARGET" "$BASE_A" "$BASE_B" "$WORK/base-b.toml" <<'PY'
import json
from pathlib import Path
import sys
import tomllib
target, first, second, output = sys.argv[1:]
record = tomllib.loads((Path(target) / 'releases' / f'base-{first}.toml').read_text())
quote = json.dumps
Path(output).write_text(
    '# Mojt Linux\n# Copyright (C) 2026 Jonas Persson\n'
    '# SPDX-License-Identifier: GPL-2.0-only\nformat = 1\n[base]\nname = "mojt"\n'
    f'version = {quote(second)}\narchitecture = "x86_64"\n[abi]\n'
    f'libc = "glibc"\nlibc_version = {quote(record["abi"]["libc_version"])}\n'
    '[build]\nbackend = "generation-experiment"\n')
PY
sudo tools/mojt-base-pack "$WORK/rootfs" "$WORK/base-b.toml" "$WORK/releases"
sudo tools/mojt-base-install install "$WORK/releases/base-$BASE_B-x86_64" \
  --target "$TARGET" --no-activate
test "$(readlink "$TARGET/base/current")" = "$BASE_A"
python3 - "$TARGET" "$BASE_A" "$BASE_B" "$WORK" <<'PY'
from pathlib import Path
import shlex
import sys
target, first, second, work = sys.argv[1:]
settings = Path(work) / 'experiment.env'
settings.write_text(''.join(f'{key}={shlex.quote(value)}\n' for key, value in
                           [('TARGET', target), ('BASE_A', first), ('BASE_B', second)]))
settings.chmod(0o600)
PY
printf '\nPrepared Base B. Retained experiment directory: %s\n' "$WORK"
MOJT_PREPARE
```

## Build A/A, A/B and B/B in one new image

Use the experiment directory printed above and the retained `mojt-thinkpad-inputs.*`
directory from the [ThinkPad preparation](thinkpad-usb-boot.md). Replace the two
example paths on the first line below with those real directories. The block
reloads the experiment settings and derives the kernel/module paths again;
it does not require variables from the previous SSH session. Adjust `PAYLOAD`
if the existing step 6 payload lives elsewhere. Initially System A and B deliberately
use the same upstream components under separate profiles: this tests selection
and retention, not an upstream kernel/package upgrade.

```bash
bash -s -- "$HOME/mojt-generations.XXXXXX" "$HOME/mojt-thinkpad-inputs.YYYYYY" <<'MOJT_BUILD' || printf '%s\n' 'Image build stopped; see the error above.' >&2
set -euo pipefail
trap 'printf "Image build failed at line %s.\\n" "$LINENO" >&2' ERR
export PATH="/usr/sbin:/sbin:$PATH"
WORK="$1"
INPUTS="$2"
if [ ! -f "$WORK/experiment.env" ]; then
  printf 'Completed experiment settings missing: %s/experiment.env\n' "$WORK" >&2
  exit 1
fi
. "$WORK/experiment.env"
set -- "$INPUTS/root"/boot/vmlinuz-*
if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  printf 'Expected one retained kernel under %s/root/boot; correct the input directory.\n' "$INPUTS" >&2
  exit 1
fi
KERNEL="$1"
KREL="${KERNEL##*/vmlinuz-}"
MODULES="$INPUTS/root/usr/lib/modules/$KREL"
if [ ! -d "$MODULES" ]; then MODULES="$INPUTS/root/lib/modules/$KREL"; fi
printf 'format = 1\n\n[[boot]]\nbase = "%s"\nsystem = "system-B"\n\n[[boot]]\nbase = "%s"\nsystem = "system-B"\n' \
  "$BASE_A" "$BASE_B" >"$WORK/generations.toml"
PAYLOAD="$HOME/mojt-lab/mpm-nix-home/mpm-system-test/system-step6"
IMAGE="$WORK/image"
test -d "$MODULES"
test -d "$INPUTS/root"
test -d "$PAYLOAD"
sudo python3 tools/mojt-vm-build.py \
  --target "$TARGET" --output "$IMAGE" \
  --kernel "$KERNEL" --modules-dir "$MODULES" \
  --firmware-root "$INPUTS/root" --system-payload "$PAYLOAD" \
  --boot-mode uefi --hardware-profile thinkpad-x1-carbon-3 \
  --base-generation "$BASE_A" --system-generation system-A \
  --additional-generations "$WORK/generations.toml" \
  --disk-size-mib 8192 --login-mode password \
  --root-shell /run/mojt-system/bin/bash </dev/tty
printf '\nImage built. Launcher: %s/run-qemu.sh\n' "$IMAGE"
MOJT_BUILD
```

Start the launcher separately, using the real experiment directory again.
The hardware profile needs a graphical Debian session or working X11
forwarding for the guest's local console. Keeping the launcher outside the
build heredoc also preserves its terminal input.

```bash
bash "$HOME/mojt-generations.XXXXXX/image/run-qemu.sh" || printf '%s\n' 'QEMU stopped; see any error above.' >&2
```

The builder still prompts if the copied machine state has no root password.
The `</dev/tty` redirection gives that prompt terminal input even though Bash
is reading the surrounding block from a heredoc.
For serial-only QEMU, omit the hardware profile and firmware option; use an
appropriate System payload and matching kernel/module set. Hardware boot
continues to require password login and step 6. Ensure every selected System
provides the root shell named by the shared `/etc/passwd`.

Each additional `[[boot]]` accepts optional `kernel`, `modules_dir`,
`system_payload` and `firmware_root` paths. Relative paths are resolved against
the plan's directory. An omitted path inherits the primary command-line input.
For an actual System B upgrade, specify the second retained kernel and its
matching module directory and/or a second prepared payload in **both** B
entries. For example:

```toml
format = 1
[[boot]]
base = "0.1.3"
system = "system-B"
kernel = "/home/user/kernel-B/boot/vmlinuz-<release-B>"
modules_dir = "/home/user/kernel-B/usr/lib/modules/<release-B>"
system_payload = "/home/user/system-payload-B"
[[boot]]
base = "0.1.3-gen-b"
system = "system-B"
kernel = "/home/user/kernel-B/boot/vmlinuz-<release-B>"
modules_dir = "/home/user/kernel-B/usr/lib/modules/<release-B>"
system_payload = "/home/user/system-payload-B"
```

## Manual acceptance

1. Boot A/A. Inspect `cat /proc/cmdline`, `cat /usr/lib/os-release`,
   `cat /run/mojt-system/version`, `uname -r` and `cat /run/mojt/motd`.
2. Write a unique marker into `/etc/generation-marker` and
   `/var/generation-marker`. Inside the Mojt guest, cleanly power off with
   `systemctl poweroff`. Run that command in the guest console, not in the
   Debian host's SSH shell.
3. Select A/B in GRUB. Confirm Base A, System B, the expected kernel and both
   markers. Verify login, networking and an already installed MPM command.
4. Select B/B. Confirm Base B, System B and the new
   `/usr/share/mojt/generation-test` marker. Persistent markers remain.
5. Return to A/A. Confirm the old identity and kernel, retained state and MPM
   command. The Base B marker must be absent here.
6. Rebuild toward a different fresh output path and interrupt the builder
   while it is staging. Confirm the interrupted output was not published and
   boot the previously completed image again. Keep the original USB untouched
   until VM acceptance has passed.

Read exact boot inputs from
`/run/mojt-disk/boot/mojt/<system>/<base>/boot.json`. The Base selection in the
kernel command line must agree with `/usr/lib/os-release`, and the System
selection must agree with `/run/mojt-system/version`. Merely editing a
command-line selector cannot switch an initramfs built for a different pair.

## Automated evidence and remaining scope

`tests/test_boot_generations.py` exercises multi-pair composition, inherited
inputs, explicit default selection, retained closure roots and state, rejection
of conflicting immutable inputs/ABI, executed shell selector checks, refusal
of existing output and injected failure during the second pair. External
kernel/initramfs/filesystem commands are simulated in those assembly tests.

`tests/run-uefi-smoke.py --generations` selects A/A, A/B, B/B and A/A through
real GRUB over serial, then boots a disk-only copy using fresh firmware state.
Both `current` links deliberately point to absent generations. Its static
BusyBox guest verifies selected identities and shared `/etc`/`/var` markers;
it does not test full systemd, Nix registration or real Wi-Fi. The owner's real
Mojt VM boot acceptance is recorded below; physical hardware generation switching
remains a separate manual step.

## Owner VM boot acceptance (2026-10-25)

The owner built and booted a real Mojt image on the Debian host using the
step 6 System payload, the ThinkPad hardware profile and Debian kernel
`6.12.107+deb13-amd64` with matching modules. Authenticated root login worked
throughout this manual GRUB selection sequence:

| Boot | Base | System | Observed result |
| --- | --- | --- | --- |
| Initial A/A | `0.1.3` | `system-A` | Base identity, System identity, kernel and explicit boot parameters agreed |
| A/B | `0.1.3` | `system-B` | System selection changed; markers written under A/A remained in both `/etc` and `/var` |
| B/B | `0.1.3-gen-b` | `system-B` | Base identity changed; the Base B image marker was present; persistent markers remained |
| Return to A/A | `0.1.3` | `system-A` | Original identities and boot parameters returned; the Base B image marker was absent; persistent markers remained |

The owner supplied console captures for all four boots and confirmed success.
This establishes real Mojt boot selection and return to the retained pair,
with shared configuration/state across the sequence. It complements the
synthetic automated guest rather than replacing its failure-injection checks.

Both System labels used the same kernel and upstream payload. Base B was an
intentionally compatible image with a different version and an added marker.
A different-kernel/payload upgrade, networking and Ports behavior across these
pairs, and physical hardware generation switching were not verified by this
run. Existing automated tests cover failure during second-pair assembly;
updates to an existing boot disk and power-loss recovery remain outside this
image-composition experiment.

## Owner serial console and interruption acceptance (2026-10-26)

The owner prepared a separate serial-console copy of the completed image and
authenticated as root through `ttyS0` in the SSH terminal. The full Mojt
systemd guest reported Base `0.1.3`, System `system-A`, the expected kernel
and both existing persistent generation markers.

A fresh build was interrupted with Ctrl-C at the new root-password prompt.
The completed serial VM subsequently booted with the same Base/System
identities and both markers. A repeated interruption using the corrected
host probe reported PASS: the builder reported password-entry abort with a
nonzero exit status, no interrupted output path was published, and the
completed serial VM disk's SHA256 checksum was unchanged.

This completes the controlled build-interruption check. The commands and
measured result are in the [SSH/serial console guide](vm-serial-console.md).


## Owner different-kernel acceptance (2026-10-26)

The owner completed the sequence **6.12 → 7.2 → 6.12** on the Debian host,
using merged builder commit `e3debe601427885a092e51220164faa415953c72`
(PR #16). This was a separate fresh image with two boot pairs, followed by
an authenticated serial-console copy. The previous generation-test VM was
retained separately. Base stayed at `0.1.3`; both labels used the same step 6
System userspace payload and retained firmware input. Only the kernel/module
inputs differed (with the corresponding generated boot artifacts).

| Boot | System label | Kernel and module release | Evidence |
| --- | --- | --- | --- |
| Initial A | `system-A` | `6.12.107+deb13-amd64` | Supplied output: ttyS0, Base/System identity, cmdline, matching module directory and boot.json; DHCP route, NetworkManager, HTTPS and hello |
| B | `system-B` | `7.2.9+deb13-amd64` | Owner confirmed all requested checks succeeded; supplied excerpt shows route, NetworkManager, hello identity and identical executable path |
| Return to A | `system-A` | `6.12.107+deb13-amd64` | Supplied output: Base/System identity, kernel/module directory, both markers, HTTPS, hello identity and identical executable path |

Kernel B and its modules were copied from the owner's Debian installation
into `/home/jonasp/mojt-kernel-test.2csGdx/root`. The owner ran depmod on the
copy and successfully resolved the requested early/runtime module dependencies.
The resulting image reported two boot pairs, with A as default. Test launcher:
`/home/jonasp/mojt-kernel-test.2csGdx/serial-image/run-qemu.sh`.
The original kernel bytes are hashed in `kernel.sha256`; per-pair boot records
and the staged hardware records retain kernel/initramfs/module input metadata.

Under A the owner created `/etc/kernel-test-marker` and
`/var/kernel-test-marker`, both containing `kernel-test-2csGdx`. They initialized
MPM's existing pinned source, installed and ran hello, and saved its resolved
executable path in `/var/kernel-test-hello-path`. Exact retained artifact:

```text
hello@=2.12.3-nix-pa6rydwgjxxmmvdxap7qk9c85h8jbimy
/nix/store/pa6rydwgjxxmmvdxap7qk9c85h8jbimy-hello-2.12.3/bin/hello
```

Both B and the return to A printed `Hello, world!`, listed that same active
identity and reported `PASS: hello uses the same installed artifact`.
The final A output showed both state markers and successful HTTPS retrieval
of `https://cache.nixos.org/nix-cache-info`. The initial and B network excerpts
showed `eth0` with DHCP routing through `10.0.2.2` and a connected NetworkManager
profile. The System curl command was used for HTTPS; hello was the separate
Ports application. No reinstallation of hello was requested on B or return A.

The full B identity/marker/HTTPS output was not pasted; those checks are
owner-reported rather than independently visible in the supplied excerpt.
This is manual owner-host acceptance, not an agent-run automated test. The
module directory/boot metadata checks are not a full post-boot module-tree
hash audit, and executable-path equality is not a fresh byte-integrity audit.

This establishes the intended kernel-switch/return experiment with shared
persistent state and a retained Ports application in the full Mojt VM.
It does not establish a System userspace payload upgrade, physical-hardware
7.2 driver/firmware compatibility, ordinary-user operation, in-place boot-disk
updates, automatic fallback, power-loss recovery or persistent-data rollback.
The next proposed work is [System completeness and account integration](system-completeness-proposal.md).
