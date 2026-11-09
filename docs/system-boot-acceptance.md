<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# One native-v2 System A/B/A owner test

This is the next acceptance gate for [System selection](native-system-selection.md),
not another Base/Kernel combination matrix. It proves a real firmware/Kernel/PID1
handover to a changed exact System, installed-MPM selection and return, persistent
state and the static shutdown exitrd. Preparation is implemented; owner boot
acceptance is pending. CI checks preparation boundaries, records and the existing
actual-archive/chroot path; it does not run this Nix-backed VM journey.

## Inputs and isolation

Run preparation as the ordinary Debian user, directly in an interactive terminal.
Clone with `umask 077`. Measured manager source files must be regular, single-link
and not group/other writable; a clone created under `umask 002` can contain 0664
files even inside a private test directory. The preparer checks this before
packaging or invoking sudo and reports the exact unsafe file/mode. It does not
silently change permissions or relax installed-code checks. For an owner-controlled
private clone, remove group/other write bits on its regular `tools` files while
preserving executable bits. No content change or provider re-export is needed.
Use the current pinned source checkout for the image/preparation tools and all
delivered MPM code. An already retained, verified step-10 provider payload with
GNU tar can be reused: that export contains provider binaries, not the MPM source
code assembled by the current checkout. Reuse the accepted Base release and exact native Kernel package;
neither input nor any previous VM disk is modified or attached.

The fresh System assembler uses a scoped `022` creation mask for its public
runtime and restores the caller's mask even on failure. Public module/bin/unit
directories must be readable/searchable regardless of a private workspace's
`077` mask. Root history, credentials and homes retain their explicit private
modes. Copied `/nix` and `/nix/store` namespace directories become 0755, without
changing any provider output object's inventoried modes/content. Symlinked
namespace roots are refused. Before writing a System manifest, the assembler
refuses private/writable runtime directories instead of publishing an unusable
profile. Native install still rejects private management modules; it does not
silently broaden imported component modes.

The existing native image builder creates a new private `.unpublished-image` and
asks for a new VM root password. A root helper in a private mount namespace mounts
only that new disk. A temporary execution root runs the explicitly supplied
bootstrap System Python/Nix against the new disk's own `/nix`, with its actual
registration and accepted NAR hashes. Host Nix is not used; candidates do not
execute during staging. Only the fixed registration load is performed, not the
bootstrap setup script or arbitrary package hooks.
The root-only loop mapping uses the GPT's validated byte offset and length, then
checks the ext4 UUID against the exact bootstrap deployment. It needs no
asynchronously created `/dev/loopXp2` node, udev wait or guessed filesystem offset.
After detach, preparation waits up to five seconds for its exact mapping to
disappear; kernel loop teardown may be deferred. Other mappings are neither
detached nor waited for. A timeout retains evidence and refuses publication.
The constructor also runs as init of its own PID namespace, with matching private
procfs. Its exit (including failure) terminates only its descendant helpers before
the parent unmounts the store. No host Nix process is killed and no lazy/forced
unmount is used. This prevents a helper from retaining a failed chroot/store.

The provider's complete executable-basename inventory is independent of public
Ports alias syntax. Names such as `[` and hidden wrapped executables are valid
inventory entries; path traversal, slash and control characters remain refused.
An inventory entry does not automatically publish a public command alias.

Both native candidates preserve the bootstrap startup/services/provider closure.
Their labels, version file, harmless tooling marker and exact artifacts differ.
The same manager constructor builds and admits both complete slots before the
initial hook/menu is published. Only after successful unmount/detach does the
preparer rename `image` and publish its outer `run-qemu.sh` and path file. A
failure retains private evidence and publishes no READY launcher. Do not launch
an internal `.unpublished-image` or use the finalizer on an existing installation.
The final image's `native-v2-acceptance.json` records the prepared A/B identities.
Earlier external image-builder sidecars describe bootstrap assembly only;
installed MPM and the v2 GRUB menu are the runtime/selection authority. The
bootstrap direct-boot launcher is removed so it cannot bypass that menu.

This is fresh-image preparation, not live v1 migration or active-v2 staging.
The trusted bootstrap interpreter is explicitly taken from the supplied System's
verified Python output. Its private initramfs closure does not change Base libc.
Normal Nix import/closure checks are retained; executable inventory uses basename
validation independently of public alias policy. Hashes are integrity evidence,
not publisher authentication.

## Debian preparation

The host needs the same native-image prerequisites as the earlier Base test,
plus `losetup`, `mount`, `umount`, `unshare` and `chroot`. Nix is needed only when
preparing the System payload (the existing Distrobox route is sufficient).

```bash
PREPARE=(python3 -I -B "$SOURCE/tests/prepare-system-boot.py"
  --base-release /home/jonasp/mojt-lab/releases/base-0.1.3-x86_64
  --kernel-package /home/jonasp/mojt-kernel-package.MMLKo3/package/kernel-linux-6.12.107-r1-x86_64-linux-eed451b5497d.tar.zst
  --expected-kernel sha256:eed451b5497d078b8de4c098539cf63a4551aa0a46864fe7550b59066fe26250
  --system-payload /home/jonasp/mojt-lab/mpm-nix-home/mojt-base-deployment.k3eJaO/system-step10
  --output "$LAB/vm-reviewed"
  --path-file /home/jonasp/mojt-system-boot-test-path)
"${PREPARE[@]}" --check-inputs
```

`SOURCE` is the pinned checkout and `LAB` its separate new private test directory;
the payload is the retained result of `mojt-system-prepare.py --step 10`. The
older `mpm-system-test/system-step10` export is not interchangeable: it predates
the retained `tar` role. The closed role check reports its full metadata path,
missing and unexpected roles before scanning its store. Do not edit that
descriptor or borrow host tar; use the current export above or re-export it.

`--check-inputs` performs the same input/source/host checks as a build, verifies
the Base manifest/hash and exact Kernel archive, and scans the System closure.
It prints full selected paths, content identities and roles. It invokes no sudo,
imports or image builder, creates no output/registry and leaves an existing path
file unchanged. It does not authorize boot or replace owner acceptance. After
the check succeeds, execute `"${PREPARE[@]}"` in the same interactive terminal;
the build rechecks the inputs instead of trusting a stale report. This uses one
argument array for both operations, avoiding a different payload path on retry.
Only the build writes `input-check.json` into its new private output directory.
Preparation can
take several minutes because complete provider trees are verified and two real
initramfs archives are built. Progress messages identify these phases. Do not
retry into the same output or interrupt just because hashing is quiet.

Start only the final launcher (it uses the serial console):

```sh
QEMU_DISPLAY=none bash "$(cat /home/jonasp/mojt-system-boot-test-path)/run-qemu.sh"
```

## Three boots, one checkpoint

Log in as root. The test runner/checkpoint is already on persistent storage;
there is no need to remount the read-only input disk after each reboot.

On A:

```sh
python3 -I -B /var/lib/mojt/system-boot-acceptance/run.py baseline
python3 -I -B /var/lib/mojt/system-boot-acceptance/run.py select
systemctl poweroff
```

Restart the **same final launcher**. Accept the default B entry. On B:

```sh
python3 -I -B /var/lib/mojt/system-boot-acceptance/run.py check
python3 -I -B /var/lib/mojt/system-boot-acceptance/run.py rollback
systemctl poweroff
```

Restart the same launcher again; accept the default A entry:

```sh
python3 -I -B /var/lib/mojt/system-boot-acceptance/run.py check-old
```

The runner checks exact deployment/artifact IDs and System marker, unchanged
Base/Kernel/installation, selected/running agreement, read-only root/System/module
mounts, account/machine/timezone data, the existing Ports profile (including an
empty baseline), all four persistent mount markers, the A journal and no failed
units. It uses the installed `mpm` frontend for preview, selection, status and
rollback. A real changed boot ID is required each way. It does not install extra
Ports just to repeat the previously accepted Ports suite.

At both shutdowns retain the serial-console ending. Require:

```text
Mojt shutdown: entered static exitrd
Mojt shutdown: old root and backing filesystem fully unmounted
```

Busy unmount errors or the exitrd ERROR/read-only fallback are not clean-shutdown
acceptance even if the machine powers off. Runtime A/B/A actions use their
checkpoint and the same successfully prepared disk. Offline preparation has a
different rule: a failed preparation is discarded as a build attempt and must
not be resumed. A busy cleanup from an older preparer requires
identifying any remaining process rooted in that exact private chroot before
signalling it; broad host Nix process cleanup is not part of this test.

Preparation is fresh-only. There is no resume option. A failed preparation is
never a candidate for another attempt: choose a new output directory and reuse
only the original verified release inputs. Do not patch a measured System or
descriptor in place. Cleanup still refuses to delete through a failed mount;
abandoned files are not opened or attached by the next build.

Fresh native image construction also scopes its generated defaults to umask
022 and restores the caller's mask on every exit. The preparer intentionally
uses 077 for its host lab; that must not make newly created guest `/etc`, `/var`
or `/home` private. Temporary workspaces and `/root` retain their explicit
private modes. The existing root image-input pipeline runs under 077 and checks
these state modes before disk publication; it uses a synthetic disk writer,
so successful execution is not guest boot acceptance.

Boot evidence uses its own bounded canonical record writer, not the Ports
request writer's 4096-entry object limit. A native Kernel or provider file map
can legitimately exceed that request limit: boot maps use the no-follow tree
reader's 100000-node bound. The complete metadata document remains below 16 MiB;
depth, list, scalar, Unicode and record-identity checks remain enforced. The
canonical encoding and IDs of previously accepted small records are unchanged.
Ports request limits are unchanged. A real 4097-file module inventory is captured,
saved, independently read and reverified, including a changed-module refusal.
Preparation prints the transition, handover and constructor phase separately so
a failure no longer reports only the enclosing System label.

## Scope after acceptance

This closes the prepared-candidate boot/return proof only. Public installed
System staging from an active v2 baseline, request/configuration-to-boot joins,
v2 Base/Kernel boot updates and MBT reuse remain separate roadmap work. Native
self-hosting still requires pinned Base and Mojt-owned System source recipes;
assembling this test from prebuilt inputs does not meet that milestone.
