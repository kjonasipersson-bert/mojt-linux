<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Build a Base from source

`tools/mojt-base-build.py` builds a complete, versioned x86-64 glibc Base
release without Void or XBPS. It is a standalone producer, intended for later
MBT integration; there is no `mbt build base` command yet. It does not install,
select or boot the result, change the host's `/etc` or touch installed releases.

## Build host and commands

Use an x86-64 Linux host with Python 3.11+ including its tarfile security updates,
a plain native GCC toolchain, and GNU build utilities. The first bootstrap is
intended for a Debian-like build host. Nix compiler wrappers are not supported
by this bootstrap: they can inject their own libc into the target.

On Debian, install the build dependencies through the normal package manager:

```sh
sudo apt install build-essential python3 gawk bison m4 perl rsync patch \
  pkg-config binutils curl zstd xz-utils bzip2 gettext texinfo
```

Build as your ordinary user. No dedicated build account or root build is needed.
From the Mojt checkout, preview the inputs and scope:

```sh
python3 -I -B tools/mojt-base-build.py --dry-run
```

Build into a **new** directory outside the checkout:

```sh
python3 -I -B tools/mojt-base-build.py --output "$HOME/mojt-base-result" --jobs 2
```

The default release version is `0.2.0`; `--version` selects another dotted Base
version. `--jobs` controls upstream make parallelism. Use a path containing only
ordinary letters, numbers, `/`, `.`, `_`, `+` and `-`.

Inputs are cached under `~/.cache/mojt/base-sources`; `--cache` changes that path.
Every reused source is checksum checked. `--offline` requires all locked sources
already in that cache and performs no downloads. A checksum is integrity
evidence, not release authentication.

## What it builds

The checked-in `bootstrap/base-sources.json` pins upstream archive versions,
HTTPS locations and SHA256 hashes. It is independent of a mutable Nixpkgs
evaluation. Initial source hashes were cross-checked against the recorded
Nixpkgs source recipes; GNU/Linux projects are built directly, without their
Nix packaging or Void patches. Dash's upstream archive is fetched from Debian's
mirror and has the same pinned upstream archive hash. GNU tar carries a small
reviewed ACL 2.4 name-conflict patch, retained in the repository.

Build order:

1. Export Linux userspace API headers. This does not build a Kernel.
2. Build and stage glibc with its upstream x86-64 Kernel baseline. Header version
   alone does not force the installed Kernel to match it.
3. Build attr, ACL, libcap, GMP and PCRE2 against that staged runtime.
4. Build dash, coreutils, grep, sed, findutils, tar and gzip against it.
5. Add Mojt defaults/licenses, remove build-only inputs and debug sections,
   inspect ELF dependencies/script interpreters, and package the Base using the
   existing packer. glibc's ldd uses the Base shell and ordinary English quoting;
   its optional Bash/Perl debugging and timezone-selection scripts are omitted.

The native host compiler runs with an explicit target sysroot; target configure
uses a distinct host triplet to avoid executing binaries against the host's
older libc. Ordinary compiler support is linked statically. glibc also loads
`libgcc_s.so.1` dynamically for unwinding/cancellation. The first bootstrap
explicitly delivers that runtime from the selected native GCC toolchain and
records its original path/hash; this is a bootstrap binary input, not a claim
that GCC itself was rebuilt. Building the compiler runtime from source belongs
to a later controlled toolchain step. Installed files must resolve
their NEEDED libraries inside Base; runtime ELF references to the workspace or Nix store
are rejected before packaging. The ELF check is a producer acceptance boundary,
not a new audit performed during normal system boot.

The intended feature set includes ACL/xattr support, capability-aware coreutils,
GMP, PCRE grep, and glibc's C/C.UTF-8 baseline. Translated message catalogs,
compiler/development files, a Kernel, Python, init, PAM, SSH and firmware are not
Base runtime inputs. This initial producer does not add a CA bundle, complete
timezone database or IANA service/protocol tables; System's separate CA/TZDIR
inputs remain unchanged. Standalone data selections can be extended explicitly.
The [runtime contract](libc-contract.md#2-shared-service-and-protocol-tables-belong-to-base)
assigns service/protocol tables to Base, with delivery planned for 0.2.1. The
current producer still defaults to 0.2.0 and does not yet implement that addition.

## Runtime and libc ownership

This first producer makes a self-contained FHS Base runtime under `/usr/lib`.
It supplies the standard x86-64 loader paths via relative directory links;
`/usr` is real and persistent/runtime mountpoints remain empty.

The generated Base contains no runtime Nix dependency. Existing System and Ports
keep their own exact library references. Sharing an identical libc build is a
permitted future optimization, not a guarantee of one libc across all retained
generations. The current Base boot contract requires an empty `/nix` mountpoint;
placing a shared store inside Base would need a separate delivery/lifetime
contract. The script does not replace or alias an existing Nix store object.

Defaults live under `/usr/etc`. Root's supplied password is locked. The installer
adds only missing machine configuration; existing `/etc`, passwords, `/var` and
user data are not overwritten. Before using this Base in an existing writable
root, compare its top-level projection with that installation: layout migration
is outside this build command.

## Outputs and failures

The output directory contains:

- `releases/base-0.2.0-x86_64/`: `rootfs.tar.zst`, checksum, manifest and inventory.
- `result.json`: source/compiler provenance, phase durations and release path.
- `logs/`: configure/build/install/pack logs, one file per phase.
- `rootfs/`: staged runtime tree; source/object directories remain for diagnosis.

Progress reports the current phase and elapsed time when it finishes, without
estimated percentages. Upstream output goes into the phase log. `INCOMPLETE`
remains after a failure; never install that workspace as a release. Existing
output directories are refused. Inspect the named failure log and retry into a
new output, retaining the download cache. No automatic resume is implemented.

The packer normalizes archive ownership to root:root without changing source
ownership. It uses the existing Base release format. Source pinning and a fixed
build epoch do not by themselves establish byte-identical reproducibility.

Building a release is not boot acceptance. First verify the producer output,
then use a separate explicit VM installation/boot test with retained recovery
content before changing an existing machine's Base.
The [first-boot procedure](reports/source-base-first-boot.md) reuses a saved
System export and Kernel in one separately constructed native-v2 VM.
