<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Prepare image building on Mojt

The first milestone runs the existing Python image builder **inside Mojt** with
pinned binary tools and frozen inputs, producing a new image for a separate boot
test. It assembles existing Base/System/kernel inputs; it does not compile all
System packages, rebuild Base from source or compile a kernel. Those later
milestones need additional recipes/toolchains and evidence.

## Private tool environment

`tools/mojt-build-env.py` is a separate Nix acquisition adapter. It never changes
MPM requests, shared Ports profiles, System generations or Base libraries. It
supports the pinned x86_64-linux source used by the existing experiments, with
config={} and overlays=[], and imports substitutes only (max-jobs=0, no remote
builders). Attribute availability and cache availability are checked by the
owner-run preview/import; they are not claimed from mocked tests.

The tool roles cover Python, Bash, Git, coreutils, find/grep/sed/awk, tar, cpio,
zstd, kmod, e2fsprogs, util-linux, dosfstools, mtools, EFI GRUB, OpenSSL, binutils,
static BusyBox and CA certificates. No C compiler or nested QEMU is required for
image assembly. The EFI GRUB role must supply x86_64-efi modules via its retained
closure. Static BusyBox must have the applets required by the existing builder;
there is no fallback to a dynamic BusyBox when cache availability is missing.

Preparation creates one new directory with:

- `bin/`: explicit links to pinned executable outputs, never global aliases.
- `gcroots/`: source and tool outputs retained at their final paths. Do not move
  an initialized environment; the indirect roots and launcher bind its location.
- `environment.json`: source identity, exact package outputs, closure/NAR hashes,
  preparation-script/adapter hashes, loader evidence and execution probes.
- `run`: a launcher whose first interpreter is **static** BusyBox. It starts the
  supplied command with env -i, the private PATH, C locale and pinned CA bundle.

HOME/TERM are carried explicitly; loader, locale-archive, Python/plugin search
paths and shell startup variables are not inherited. No global LD_LIBRARY_PATH,
LD_PRELOAD, loader symlink or replacement Base libc is installed. Preparation
itself requires a shell without LD_LIBRARY_PATH/LD_PRELOAD/LD_AUDIT overrides.
It uses existing trusted System/Nix bootstrap tools to acquire the new toolset.

An incomplete import/probe leaves `.preparing` and retained objects for inspection;
no usable launcher is published. Use a fresh directory after failure. Dry-run and
cancellation create no environment, GC roots or payloads; Nix evaluation can use
its own caches. Successful preparation still requires real Mojt acceptance.

## Libc evidence and boundaries

For direct ELF programs the preparer records their interpreter, dynamic metadata
and their own loader's `--list` resolution under the clean environment. Every
resolved file must belong to the pinned tool closure. Script wrappers record
their store-specific shebang interpreter recursively; non-store interpreters
fail. This does not parse arbitrary shell code or audit all subprocesses behind
a wrapper. Version probes execute representative tools. A Python probe performs
local account lookup and records `/proc/self/maps`; mapped shared libraries,
including libc, must belong to the tool closure.

This distinguishes actual loader objects from whichever `ldd` happens to be on
PATH. Several libc objects in a transitive closure are recorded, not interpreted
as a process loading all of them. Resolution/probe failures stop preparation;
they are not repaired by widening library paths. The Base loader/libc stays as
it was. Plugin/NSS/PAM/locale and desktop compatibility are not certified by
these checks. On Mojt, confirm DNS/HTTPS with the prepared Python as part of
initial tool acceptance; local password-file lookup alone does not verify DNS.

## Owner-run first preparation

Inside Mojt, as root for its existing local Nix store, use a checkout containing
this tool and the adjacent `mpm-nix-prototype`. When no Git is available yet,
bootstrap those two files from one explicit repository commit using System curl;
record/verify their hashes, then use the prepared Git for a detached checkout of
that same commit. Do not silently download a moving branch for the actual build.
The currently tested selector VM can be used for preview/tool acceptance; retain
its disk as a reference and check free space before importing.

```sh
python3 tools/mojt-build-env.py \
  --source-manifest /run/mojt-system/ports.toml \
  --output /var/lib/mojt/build-envs/image-tools-1 --dry-run
# Same explicit inputs after reviewing the package/cache preview:
python3 tools/mojt-build-env.py \
  --source-manifest /run/mojt-system/ports.toml \
  --output /var/lib/mojt/build-envs/image-tools-1 -y
/var/lib/mojt/build-envs/image-tools-1/run python3 --version
/var/lib/mojt/build-envs/image-tools-1/run git --version
/var/lib/mojt/build-envs/image-tools-1/run python3 -I -c \
  'import ssl, urllib.request; print(ssl.OPENSSL_VERSION); print(urllib.request.urlopen("https://cache.nixos.org/nix-cache-info", timeout=30).read().decode())'
```

The preparer can also run as an ordinary user in the existing Nix Distrobox.
Its paths/roots are environment-specific; copying that directory alone into Mojt
does not transfer the store, registration or roots. Native Mojt preparation is
the first planned route, using its existing Nix and pinned source.

## Frozen build inputs and disk capacity

The later image build needs a private offline directory installation containing
Base, release metadata, state and `.install-lock`; a verified step-10 System
payload; a matching kernel/module tree; and the pinned builder checkout. Record
input digests and selected Base/System/kernel versions before building. Transfer
these as data with ownership/modes/symlinks preserved, verify after transfer, and
keep them separate from the running installation. Do not point `--target` at the
live `/run/mojt-disk` or assume the active System is an exported payload.

Use a dedicated build VM with a sparse 64-GiB disk and about 4 GiB RAM for the
first full image experiment. These are planning allocations, not measured minima.
The current 8-GiB acceptance disk should not be assumed to fit input payloads,
imported tools, staging copies and the output disk simultaneously. Check actual
free space and previewed imports. Booting the result can happen on the Debian
host; nested KVM/firmware inside Mojt is not required to construct the image.

A serial-only UEFI build can reuse the known Debian 6.12 kernel and matching
modules. Physical-hardware firmware support and a newly compiled kernel are
later tests. Pass the toolset's recorded **static** busybox path explicitly as
`--busybox`; the builder's Debian default /usr/bin/busybox is not a Mojt contract.

Example shape once the frozen inputs exist (paths are placeholders):

```sh
/var/lib/mojt/build-envs/image-tools-1/run python3 /BUILD/source/tools/mojt-vm-build.py \
  --target /BUILD/base-target --system-payload /BUILD/system-payload \
  --kernel /BUILD/kernel/vmlinuz-RELEASE --modules-dir /BUILD/kernel/lib/modules/RELEASE \
  --busybox /PINNED-STATIC-BUSYBOX/bin/busybox \
  --boot-mode uefi --base-generation 0.1.3 --system-generation system-selfbuild-A \
  --login-mode password --root-shell /run/mojt-system/bin/bash \
  --disk-size-mib 8192 --output /BUILD/new-image
```

The first real acceptance is one tool/loader/DNS check, one fresh image build,
manifest compatibility check and separate boot. Repeat earlier user/generation
checks only when a changed behavior or failure warrants it. Preparation tooling
and mock tests are not evidence that a Mojt image has already been built.


## Owner acceptance on Mojt (2026-10-27)

The owner used the pinned preparation commit
`481e43a1fa4b1252704db0ce23402dbd5a17383c` in the existing selector VM.
The source/adapter hashes matched. Preview offered binary fetches for every role,
including EFI GRUB 2.14 and static musl BusyBox 1.37.0. Native preparation reached
`Build environment ready` at
`/PRIVATE-BUILD-ENVIRONMENT`, establishing completion of the
preparer's fail-fast import, closure, loader, applet and representative execution
checks. Shared Ports/System activation was not requested.

A subsequent invocation through the actual static launcher verified its private
PATH and absence of loader/Python overrides. Python resolved cache.nixos.org,
fetched nix-cache-info using certificate-verified HTTPS, and checked all observed
mapped shared libraries after that operation against the retained tool closure.
The observed runtime libc was:

```text
<pinned-glibc-2.44-57-object>/lib/libc.so.6
```

Evidence was written to
`/PRIVATE-NETWORK-RUNTIME-REPORT.json`. This is evidence for
the measured tool runtime, not general libc/NSS/PAM/desktop compatibility.

The owner then ran the pinned `mojt_boot.build_disk` helper through the private
environment, producing a separate 512-MiB diagnostic image with placeholder
kernel/initramfs data. Real GPT, ext4, FAT and standalone EFI-GRUB creation
passed. e2fsck completed successfully, debugfs read the expected marker and the
EFI loader copied back from FAT matched the generated bytes. EFI loader SHA256:

```text
<EFI checksum retained in the local test report>
```

Diagnostic output is retained under `/PRIVATE-IMAGE-TOOL-TEST`.
This validates real tool integration on Mojt; the diagnostic image contains no
runnable Mojt installation and was not a full operating-system boot test.
The next milestone is frozen Base/System/kernel inputs, sufficient separate
workspace, one complete image build on Mojt and one boot of its result.
Repeated network, account and A/B/A acceptance is not required absent a relevant
change or failure.


The full-image milestone passed on Mojt with frozen inputs and a successful
result boot. See [measured acceptance](build-workspace.md#owner-full-image-build-and-result-boot-2026-10-27).
