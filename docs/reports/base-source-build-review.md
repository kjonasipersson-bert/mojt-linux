<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Source-built Base: proposed contents and preliminary libc review

Reviewed 2026-11-23, using Mojt runtime sources from
`ea033084b8997e980943cc01591ab6f669af4473` and the
[saved 29-package inventory](base-content-inventory.md#2-observed-bootstrap-package-inventory).
This is a design/evidence report, not an implemented build interface or a claim
that a new Base has booted with an existing System.

## Result

A small independent Base build is feasible to scope from the existing inputs.
The initial proposal has thirteen upstream runtime source projects, Mojt-owned
layout/defaults and separately selected data. This count is a proposed starting
set, not a proven minimum or a complete build-tool dependency closure.

glibc 2.44 is a reasonable candidate for the new build. Matching Nixpkgs' upstream
version is neither required to run its existing programs nor sufficient to
replace their runtime. A current metadata equality rule also blocks a Base
libc-version change before runtime compatibility is considered.

The next implementation should establish the exact running System's runtime
boundaries with one bounded read-only diagnostic, then build the chosen content
into a new private Base tree. Existing content/selection must remain intact.

## 1. Proposed initial build contents

Preserve the familiar command implementations and useful features first. Avoid
combining the Void removal with replacing GNU commands by different applets or
silently disabling their library-backed features.

| Upstream source project | Proposed delivered role | Reason to keep initially |
| --- | --- | --- |
| glibc | Loader, runtime libraries, required runtime tools and locale/conversion support | Coherent C runtime for Base programs |
| dash | POSIX shell, including `/bin/sh` | Current System start and management wrappers use it |
| coreutils | Existing basic Unix command family | Startup uses commands such as `mkdir`, `cp`, `ln`, `basename`, `chown`, `touch`, `chgrp` and `chmod` |
| grep | Text searching | Preserve the current command interface and PCRE feature choice |
| sed | Stream editing | Preserve existing Unix userspace functionality |
| findutils | File search and xargs | Preserve existing command/alternative names where applicable |
| tar | GNU archive handling | Preserve standalone Base functionality; System also supplies a private GNU tar helper |
| gzip | Gzip command family | Preserve existing Base functionality |
| attr | Extended-attribute library support | Keep observed supporting functionality during initial reconstruction |
| acl | ACL library support | Preserve the selected core/file/archive tools' ACL feature policy |
| libcap | Capability library support | Preserve existing capability-aware command behavior |
| gmp | Arithmetic support | Preserve the current coreutils feature/dependency choice |
| pcre2 | Required PCRE2 runtime library output | Preserve the chosen GNU grep functionality, including `-P` if confirmed in the baseline |

The five supporting library projects are conservative inclusions inferred from
the observed packages and reviewed recipes. Exact per-program links must be
measured in the new build. PCRE2's auxiliary programs, libcap's administration
programs and development outputs are separate delivery choices; building a
source project does not require shipping all its products.

### Mojt-owned files and data

- Generate layout, identity, license/provenance records and release defaults
  explicitly, instead of installing Void's `base-files` and subtracting files.
- Preserve the current Base top-level projections and empty mountpoints for the
  first compatible installation. The writable-root installation marker binds
  those projections; arbitrary layout changes require a separate migration.
- Supply conservative local `passwd`/`group` seeds, shell/profile defaults,
  `hosts`, `nsswitch.conf` and appropriate loader configuration under `/usr/etc`.
  Preserve System account provisioning and persistent-state ownership.
- Keep a tested `C`/`C.UTF-8` baseline with data generated for the intended
  runtime. Additional locales are an explicit content choice.
- Prefer retaining a pinned CA bundle as data for a useful standalone Base.
  Decide its paths/configuration separately from shipping OpenSSL and the
  `update-ca-certificates` maintenance program. Nix-provided consumers may use
  their own bundle.
- Full timezone data and IANA service/protocol tables are explicit data choices.
  Current System supplies a pinned `TZDIR`; removing that context must not
  accidentally break the intended standalone Base use case. The Nixpkgs manual
  also identifies `/etc/services` and `/etc/protocols` as host integration inputs.

These are proposed contents/defaults, not instructions to rewrite a machine's
current `/etc`. Existing local configuration survives Base changes under the
add-missing policy, including old distribution-derived files. Cleaning a new
release cannot silently clean persistent configuration on existing machines.

### Existing inputs not in the proposed core

| Existing input/content | Proposed treatment | Condition |
| --- | --- | --- |
| `xbps`, `libxbps`, `xbps-triggers` | Omit from the new build/output | Replace the construction backend; generate final links/defaults explicitly |
| Void `base-files` helpers/identity, dracut/udev/modprobe/sysctl policy | Do not copy into the new Base | Recreate required layout/defaults and keep device/service policy with System |
| `libarchive`, `bzip2`, `liblz4`, `liblzma`, `libzstd`, `zlib` | Exclude from the initial core unless a retained feature needs them | Their old presence is not proof that all are required by the proposed rebuilt programs; verify the actual output closure |
| `openssl`, `libcrypto3`, `libssl3`, `run-parts` | Separate from the core; retain only for a chosen Base feature | Certificate data can be produced during the build; current System uses its own CA reference |
| `libxcrypt-compat` | Keep unresolved until consumer inspection | Do not treat Base's absence of login/PAM tools as proof that no retained binary requires `libcrypt.so.1` |
| GNU/Void package documentation and miscellaneous utilities | Explicit delivery list | Preserve useful manuals and required licenses; don't import distribution maintenance payloads accidentally |

None of these exclusions remove or relink the corresponding Nix store objects
needed by the retained System or Ports. No already installed release is pruned.

## 2. Actual System-to-Base dependencies visible in source

| Boundary | Source evidence | Consequence for the Base proposal |
| --- | --- | --- |
| Shell/startup | `mojt_system.py` produces `start`, `setup`, MPM/MBT/manual wrappers with `#!/bin/sh` | A usable Base shell and its loader/runtime are still on the boot path |
| Basic commands | `start` uses `mkdir`/`cp`; setup scripts use core commands with `/run/mojt-system/bin:/usr/bin:/bin` | System's Nix payload does not replace every Base command requirement |
| PID 1 and management | `start` execs the exact exported systemd path; MPM execs the retained Python | These programs retain their provider runtimes; they do not become Base-libc consumers solely by using the Base shell as a launcher |
| Archive helpers | System assembly records private retained `tar`/`zstd` paths under `libexec/mpm/bin` | Their dependencies need not be supplied by Base; Base's own archive commands remain a separate usability choice |
| TLS | System environment exports `SSL_CERT_FILE` and `NIX_SSL_CERT_FILE` from its `cacert` role | System HTTPS support is not evidence that Base's OpenSSL package is necessary |
| Time/locales | System exports `TZDIR` and defaults `LANG` to `C.UTF-8` | Preserve behavior in both Base and Nix consumers; a shared locale name is not shared binary data compatibility |
| Authentication | `mojt_accounts.py` uses exact System PAM module paths and local NSS `files` requirements | Shared persistent identity/configuration is an integration boundary; it does not justify replacing PAM modules with Base libraries |
| Root layout | `mpm_boot_handover.writable_root` binds a real Base `/usr`, reserved mountpoints and a projection marker | Keep the supported layout while changing the producer |
| Early/final boot | Static BusyBox is provided by initramfs/System | It does not force BusyBox into the new Base product |

Source review does not enumerate every service subprocess, shared object or
module loaded on the physical target. A report of thirteen source projects
must not be presented as demonstrated full System compatibility yet.

## 3. Current ABI metadata is stricter than the intended lifecycle

`mojt_system.finalize_manifest` copies `base_record['abi']` into the System's
requirements. `mojt_system_manifest.check` compares that whole dictionary with
the selected Base facts using equality. This is not a minimum glibc requirement
or a measured ELF symbol requirement.

A local synthetic check using the existing `tests/test_system_manifest.py`
fixtures gives:

| System declaration | Candidate Base facts | Current metadata result |
| --- | --- | --- |
| glibc 2.41 | glibc 2.41 | Compatible |
| glibc 2.41 | glibc 2.44 | Refused: `declared Base ABI differs` |

The nine existing `ManifestTests` also pass locally. These are pure metadata
checks, not physical runtime/boot tests. A numerically equal version is not an
ELF/loader/library compatibility proof either.

Before admitting Base 2.44 with current System binaries, define how to express
their actual Base requirements and test the result. Preserve the meaning of
existing serialized declarations: do not silently reinterpret an old exact
requirement as a lower bound, erase the version field or relabel glibc 2.44 as
2.41. A reviewed System metadata successor may be needed even when its service
binaries remain the same. New capability/requirement semantics need an explicit
supported representation and older-reader behavior.

Base staging also requires Kernel bounds bound to the candidate Base artifact,
and checks persistent state and shell/layout compatibility. Correcting the
libc equality rule must not bypass these separate requirements.

## 4. Preliminary libc analysis

### Version choice

The GNU project lists 2.44 as stable. Arch's checked package page also uses
2.44. The independently reviewed Nixpkgs revision
[`804068b712dc9794d8d25d7af3912c5f45d14d9d`](https://github.com/NixOS/nixpkgs/tree/804068b712dc9794d8d25d7af3912c5f45d14d9d)
declares `2.44` plus patch suffix `-57` in its glibc recipe. This does not
establish every NixOS channel's or the target's exact runtime.

Recommendation: make glibc 2.44 the candidate new Base runtime, pinned to a
reviewed source revision/patch set when implementing the recipe. Keep the
existing 2.41 Base as the working reference. Version 2.41 can also serve as a
controlled comparison if a regression requires it; two full builds are not an
automatic acceptance requirement.

### Three runtime boundaries

| Consumer | Intended runtime ownership | Effect of a new Base |
| --- | --- | --- |
| Rebuilt native Base commands | Matching Mojt-built loader/libc and selected support libraries | Change together with the complete Base release |
| Retained Nix System programs | Exact provider objects named by their ELF/runtime references | Keep those objects; Base replacement does not retarget them |
| Retained Nix Ports programs | Each accepted provider reference/closure | Different programs can retain different objects; updates remain independent |

A Base shell executing a Nix binary creates a new program image. This is a
different boundary from loading an extension into an existing process. Shared
NSS/PAM/plugin configuration, locale/conversion data and service protocols
still need integration checks. Store references alone are not a sandbox or a
proof that all late-loaded dependencies remain inside the closure.

### Equal upstream versions do not make the libc builds interchangeable

The pinned Nixpkgs glibc sources include concrete behavioral patches:

- `dont-use-system-ld-so-cache.patch` moves cache/config paths into the package
  prefix, avoiding the host's ordinary `/etc/ld.so.cache`.
- `dont-use-system-ld-so-preload.patch` changes the preload file to
  `/etc/ld-nix.so.preload`.
- `nix-locale-archive.patch` adds `LOCALE_ARCHIVE_2_27`/`LOCALE_ARCHIVE` selection
  and fallback paths including the host's `/usr/lib/locale/locale-archive`.
- `nix-nss-open-files.patch` adds `NIX_ETC_PROTOCOLS` and `NIX_ETC_SERVICES`
  overrides for those data files; it does not isolate all `/etc` configuration.
- The recipe binds IDN support to a retained `libidn2` path and adds other
  build/compatibility changes.

These are observed upstream recipe facts, not evidence that every loaded
target libc has precisely this patch set. Measure target identity separately.

Rebuilding Base with upstream 2.44 gives control of Base's runtime. It does not
make the Nix `2.44-57` runtime redundant, apply Base security fixes to its
consumers, or justify patching their interpreters/library references in place.

### Proposed initial integration policy

1. Build Base's loader/libc, shell, programs and support libraries as a coherent
   target. Reject accidental `/nix/store` interpreter/`NEEDED`/RPATH/RUNPATH or
   script references in the deliverable. Build tools may themselves use Nix.
2. Retain the exact Nix runtime references for System and Ports. Use no global
   `LD_LIBRARY_PATH`, `LD_PRELOAD`, `LOCPATH` or `GCONV_PATH` to merge runtimes.
3. Start with local NSS files/DNS in both runtime families. Preserve System's
   exact PAM/module paths; external NSS/PAM/plugin support is not implied by
   their files merely existing in a common directory.
4. Test the intended locale names in both families with their actual data.
   Avoid claiming that a host-wide generated locale archive works for every
   retained Nix libc. Nixpkgs' locale patch can consult host data even while its
   loader avoids the host's normal cache.
5. Record CPU baseline, exported Linux API headers and supported Kernel floor
   separately from the glibc version. Headers are build inputs; a new header
   export is not a request to replace the running Kernel.

These are proposed constraints, not new runtime audits at every MPM invocation.
ELF closure/producer checks and upstream regression suites belong to build and
release acceptance; normal installation keeps its bounded transaction.

## 5. Next bounded implementation

### First: observe the actual installed boundary

One diagnostic should read the running Base/System identities and inspect only
the selected examples: Base `sh`/core tools/getent, System systemd/Python/Bash/
sshd/login and representative Ports such as Git/Neovim. Use standard ELF tools
for interpreter/needed paths/version requirements and runtime probes/maps for
what actually loads. Do not infer a libc from whichever `ldd` is first on PATH
or count every libc in a transitive store closure as loaded in one process.

Record local identity and DNS lookup, UTF-8 locale handling, certificate/time
data references and known module boundaries. Mark unavailable tools or untested
features explicitly. Do not compile, relink, change configuration, start a new
service, scan all installed generations or modify selection for this diagnostic.

### Then: one small source builder

Use a pinned external bootstrap toolchain initially. Produce a target sysroot
with exported Linux API headers, glibc and necessary compiler runtime support;
then compile the selected support libraries and Unix tools against that target.
A Nix compiler wrapper's normal defaults are not a Mojt target contract.
Use standard upstream configure/make/install mechanisms and private staging,
with explicit versions/checksums/patches, declared features and a deterministic
assembly list. Keep build-only compilers, headers, static archives and tests
outside the ordinary Base payload unless explicitly selected for delivery.

Generate Mojt-owned defaults/layout and the normal Base release artifact. Keep
existing release/install interfaces where possible. A future short
`mbt build base` frontend can coordinate this, but no such command is implemented
by this report. Byte-identical reproducibility must be measured; pinned inputs
alone do not prove it.

The acceptance step uses the unchanged System service binaries, the supported
metadata declaration, the existing Kernel and persistent-state policy. Check
shell/startup, login/SSH, local users, DNS/HTTPS, MPM/Ports and deliberate boot.
Only failures or changed contracts justify broadening the matrix. No full
compiler bootstrap or repeated complete Kernel build is required for this scope.

## Sources and validation limits

Mojt evidence: `mojt_system.py` (ROLES, start/setup/environment, private helpers,
`finalize_manifest`), `mojt_accounts.py`, `mpm_man.py`,
`mojt_system_manifest.py:check`, `mpm_base_transition.py:candidate_checks`,
`mpm_system_transition.py:_prepare`, `mpm_boot_handover.py:writable_root` and
`mpm_base_boot.py:boot_tree`. The source inventory links the exact saved package
versions and separate Void snapshot.

Primary upstream sources checked on the review date:

- [GNU glibc status and compatibility objective](https://sourceware.org/glibc/libc.html)
- [Arch glibc package](https://archlinux.org/packages/core/x86_64/glibc/)
- [GNU glibc build configuration](https://sourceware.org/glibc/manual/2.44/html_node/Configuring-and-compiling.html)
- [GNU dynamic linking considerations](https://www.sourceware.org/glibc/manual/latest/html_node/Dynamic-Linker-Hardening.html)
- [Linux userspace header export](https://docs.kernel.org/kbuild/headers_install.html)
- [GCC sysroot configuration](https://gcc.gnu.org/install/configure.html)
- [Nixpkgs glibc recipe](https://github.com/NixOS/nixpkgs/blob/804068b712dc9794d8d25d7af3912c5f45d14d9d/pkgs/development/libraries/glibc/common.nix),
  [cache patch](https://github.com/NixOS/nixpkgs/blob/804068b712dc9794d8d25d7af3912c5f45d14d9d/pkgs/development/libraries/glibc/dont-use-system-ld-so-cache.patch),
  [preload patch](https://github.com/NixOS/nixpkgs/blob/804068b712dc9794d8d25d7af3912c5f45d14d9d/pkgs/development/libraries/glibc/dont-use-system-ld-so-preload.patch),
  [locale patch](https://github.com/NixOS/nixpkgs/blob/804068b712dc9794d8d25d7af3912c5f45d14d9d/pkgs/development/libraries/glibc/nix-locale-archive.patch) and
  [NSS data-file patch](https://github.com/NixOS/nixpkgs/blob/804068b712dc9794d8d25d7af3912c5f45d14d9d/pkgs/development/libraries/glibc/nix-nss-open-files.patch)
- [Nixpkgs locales and host data](https://nixos.org/manual/nixpkgs/unstable/#locales)

Only source review and the local synthetic metadata checks were performed.
No target ELF/runtime audit, native Base build, physical boot, complete package
dependency graph or general cross-libc/plugin compatibility is claimed.
