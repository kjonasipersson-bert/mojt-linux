<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Fresh image from native Base and installed Kernel artifacts

This experimental builder connects the merged [deployment planner](kernel-deployment-plan.md)
to fresh serial UEFI image assembly. It consumes exact local Base/Kernel content,
generates and inspects an initramfs, and records a complete deployment for the
new disk. It never updates an existing installation or schedules a running
machine's next boot. Owner acceptance of the new full-Mojt boot path is pending.

Building a Kernel, packaging it, installing it and assembling/selecting a boot
deployment remain separate operations. `mpm kernel install/status` is unchanged.
The new builder is an explicit source-checkout tool, not an implicit build or
activation inside MPM and not yet a general `mpm kernel activate` implementation.

## Inputs and invocation

Required inputs:

- A verified native `base`/`mojt` package and its full artifact ID. Its payload
  contains the existing `manifest.toml`, unchanged `rootfs.tar.zst` and optional
  regular release-local provenance/checksum files. Dependencies/requirements,
  wrapper links, nested payload directories and other platforms are rejected.
- A locally installed native `kernel`/`linux` artifact and its full ID, in a
  readable Kernel registry. Source builds, catalogs and Nix acquisition are not
  consulted. The retained files and archive are freshly verified.
- Explicit `mpm-kernel-base-context-v1` bounds naming that exact Base artifact,
  original Base release label and platform. No Base 0.1.3 support range is inferred
  from its name or the host kernel. A locally constrained experiment is not a
  distribution-wide compatibility claim.
- A previously exported and verified System step 6+ payload, keeping the current
  optional Nix/System adapter and pinned userspace objects. Another System
  provider is future work; no Nix commands/daemon or source compiler run here.
- A trusted static x86_64 BusyBox and the existing VM/EFI archive/disk tools.

For a Base that currently exists only as an older release directory, use the
native packer's Base adapter on that unchanged release directory first. It
derives `kind: base`, `name: mojt`, the original architecture/Linux platform,
upstream release, explicit native revision and provenance hashes directly from
the existing release metadata. Numeric labels retain dotted ordering; other
legacy labels are preserved verbatim as opaque exact-only versions.
Dependencies/requirements are empty in this initial adapter. This wraps the
existing archive; it does not compile or replace Base's libc.
The package release (for example `0.1.3-r1`) and the installed Base label
(`0.1.3`) are distinct, both bound by the exact package ID.

```sh
python3 -I -B tools/mojt-artifact-pack.py base \
  --release /LOCAL/EXISTING-BASE-RELEASE --revision 1 \
  --output /NEW/NATIVE-BASE-PACKAGE
```

Preview can run as the ordinary owner of readable inputs:

```sh
python3 -I -B tools/mojt-native-image.py \
  --base-package /LOCAL/base.tar.zst --base-artifact sha256:FULL_BASE_ID \
  --base-context /LOCAL/base-kernel-bounds.json \
  --kernel-registry /LOCAL/KERNEL-REGISTRY --kernel-artifact sha256:FULL_KERNEL_ID \
  --system-payload /LOCAL/SYSTEM-PAYLOAD --system-generation system-native-A \
  --output /NEW/IMAGE --dry-run
```

The IDs above are placeholders. Preview verifies the real package/registry and
System input declarations without creating an image, output directory or private
import. It does need zstd for package inspection. It does not prove every build
tool is installed or run BusyBox/EFI assembly. For the actual build, run the same
command through `sudo` without `--dry-run`, directly in an interactive terminal.
Password login is the default; keep its terminal attached for the root-password
prompt. No password or hash flag is provided. An explicitly unsafe
`--login-mode development` is available only for isolated fixtures.
Password mode always creates fresh machine credentials/serial-console access
in the new image's private state; it does not inherit a publisher's password or
console allowlist. Original release defaults and existing machines are untouched.

`--disk-size-mib` defaults to 8192; `--busybox` defaults to `/usr/bin/busybox`.
This first native path supports one explicit x86_64 serial UEFI pair, VirtIO disk
and networking. Hardware profiles, firmware acquisition, additional generations,
copying existing account state and existing-disk updates are outside the subset.
Existing legacy builder modes remain available and unchanged.

## Snapshot, verification and publication

1. Freeze/reverify the exact Base archive in a private workspace. Extract only
   bounded regular native wrapper files; use the existing audited Base installer
   for the inner release archive into a new private target. Package wrapper
   ownership/special privilege bits are not applied; inner Base metadata follows
   the existing Base installer contract. No package hook is executed.
2. Reimport the exact retained Kernel archive into a private build registry. Copy
   and reverify the System payload. Existing source registries and release files
   remain untouched; missing or changed identities fail without fallback.
3. Build a new System profile from those pinned inputs. Copy the complete private
   Kernel registry to the disk's `kernel/` directory and verify it after copying.
   Mount `/lib/modules` read-only from
   `kernel/installed/FULL_KERNEL_HEX/payload/lib/modules`, not `System/kernel`.
   Early boot checks the actual running release against the native selection.
4. Resolve early module dependencies only within that exact module tree. Generate
   the Base/System/root-specific init script and actual gzip/newc initramfs.
   Compare each early module's decompressed bytes with its selected package file.
   Independently parse the final newc archive and compare its entire inventory,
   file/link contents, modes, owners and device numbers with the private init tree.
5. Verify the completed System profile and every copied provider object. Compare
   Base before/after copying: original files, symlinks, hardlink topology, modes,
   owners and xattrs/ACLs must match. Only additive mountpoint directories are
   allowed. Base libc files are never replaced and no global library paths added.
   Record both Base inventory digests and the exact added scaffolding, rather
   than pretending the assembled VM tree is a byte-identical release archive.
6. Bind the actual initramfs checksum/size to the exact Base, System manifest,
   Kernel/image/module inventory, filesystem UUID and console. Reuse the planner's
   Base limits and System ABI/state/Ports/shell gates against this new private
   image's facts. Its bootstrap selection is a newly assembled disk's choice,
   not an inferred or adopted existing-machine selection.
7. Build only a regular-file GPT/ext4/FAT/GRUB image. Rerun the portable planner
   on the resulting sidecars and retained private registry, then rename the
   completed output into a previously absent directory. A failure before this
   final publication leaves no output and preserves all source inputs. Temporary
   stages are removed on normal exceptions, not silently recovered after crashes.

The existing format-1 `boot.json` continues to describe GRUB's generated paths.
Separate `mojt-boot-deployment-v1`/binding records carry exact native identities;
they do not silently redefine that older format. Both kernel/initramfs hashes
must agree before disk assembly. There is no self-reference: initramfs names a
fixed sidecar location, not a deployment digest that includes its own checksum.

## Output and focused acceptance

The new output contains `disk.img`, serial `run-qemu.sh`, `build.json`, the actual
`initramfs.cpio.gz`/`vmlinuz`, exact Base/Kernel descriptors, System manifest,
deployment/binding records, planner request/evidence and
`native-build-inputs.json`. Matching sidecars are retained inside the boot pair
on the disk. The receipt records verified input identities, Base scaffolding
differences, initramfs inventory and early-module evidence. The guest receives
`/run/mojt/deployment.json` and `/run/mojt/native-kernel-artifact` from that image.
It is not a signed boot attestation or a new authoritative MPM state database.

For the next owner acceptance, reuse the already built/installed Kernel, wrap
the unchanged Base release and export no new System packages. Preview, build one
new disk, boot it once, and check:

- Running release and recorded full Kernel artifact match the intended inputs.
- `/lib/modules` is read-only and sourced from the exact native registry object;
  module filenames/vermagic/driver release agree with the running Kernel.
- The generated deployment records name the intended Base/System, no systemd
  units failed, and the existing network/HTTPS path works.

No repeated account or A/B/A test is needed for this fresh-image integration.
The first owner boot found a BusyBox remount lookup failure with Base's
`/lib -> usr/lib` layout. The native module remount now supplies both source and
target explicitly, bypassing a literal-path lookup in `/proc/mounts` while
retaining read-only protection. Focused BusyBox tests cover argument handling
and, where mount namespaces are available, read-only behavior through that link.
Acceptance remains pending a boot of the corrected image.
The automated tests use real native tar/zstd packages, audited Base installation,
System fixture assembly and actual cpio serialization/independent inspection,
but synthetic guest programs/disk output and simulated initramfs device creation.
Character-device header validation has a separate fixture. CI protects the new
boundaries; it is not full-Mojt runtime acceptance of this new path.

The standalone planner still reports `boot_ready: false`: successful assembly is
not general hardware/firmware, Secure Boot, libc/desktop ABI, power-cut recovery
or publisher authentication evidence. Keep the accepted reference images until
the focused native result boot passes. Production acquisition, policy tracking,
transactional activation/rollback and durable existing-disk updates remain future
work. The new image does not modify the running Kernel/Base/System/Ports state.

