<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# First own-built kernel: native build and VM acceptance

The owner accepted native kernel compilation, image assembly and a focused VM
boot/module/network test on 2026-10-28. Mojt built and ran Linux
`6.12.107-mojt1`, retaining the working Debian reference kernel and the accepted
image toolset. The build helper stages a separate Kernel input; it does not
activate it on the build VM or implement `mpm kernel` commands.

## Locked first target

[The plan](../manifests/kernel-first-build.json) fixes upstream stable Linux
6.12.107, tag v6.12.107, commit
`f717995cb7dcd8998ab15516b8006aea09cfde0d`, fetched from the kernel.org stable
repository. The tag-to-commit mapping was checked against the stable maintainer's
mirror; the helper independently refuses a fetched commit mismatch. It does not
perform local OpenPGP key/trust management or claim signature verification.
Accepted first release: `6.12.107-mojt1`.

Start with the configuration from the retained Debian 6.12.107 package, supplied
as a separate frozen file and SHA256. Upstream source is not Debian's patched
source package; sharing the version/config starting point does not imply the
same binary or identical patch set. Obtain the package's config explicitly;
using an arbitrary running-machine config or an inferred default is not a pin.

The policy keeps the Debian starting point, disables debug information/BTF,
Rust and GCC plugins for the first build, removes distribution certificate and
embedded firmware/initramfs file references, and disables module signing in this
unsigned VM experiment. It enables VM-critical storage/network/console/EFI and
filesystem facilities built-in, chooses gzip for the kernel and uncompressed
modules. This avoids changing Base/System while testing the kernel and reduces
debug/toolchain requirements. The complete before/after config diff is retained;
olddefconfig must leave all required symbols set as requested or the build stops.
The policy is for a VM experiment, not a production Secure Boot policy.

In this unsigned experiment the policy also disables the lockdown LSM and its
early-init option: upstream `SECURITY_LOCKDOWN_LSM` selects `MODULE_SIG` when
modules are enabled, overriding a direct request to turn verification off.
It disables IMA's module-style signature appraisal support as well, avoiding a
second module-signing-key dependency. Other security facilities are retained.
The owner's second attempt successfully built the Kconfig host programs before
the strict policy check caught the lockdown/signature conflict. The corrected
policy subsequently passed the native build and focused boot acceptance below.
The Binder `m`-to-bool warning from the Debian starting config was separate from
that fatal policy mismatch.

## Separate compiler environment

The accepted image environment remains unchanged. Prepare a **new** directory:

```sh
python3 tools/mojt-build-env.py --profile kernel \
  --source-manifest /run/mojt-system/ports.toml \
  --output /NEW/KERNEL-ENV --dry-run
```

The kernel profile adds pinned GCC 14, GNU make, flex, bison, bc, Perl,
pkg-config, gzip, diffutils and assembler/linker/binutils commands. It selects
explicit dev/lib outputs for elfutils and OpenSSL. PKG_CONFIG_LIBDIR names only
the pinned development metadata; no global loader path is added. GCC 14 is an
initial conservative recipe choice, not a claim that every newer GCC fails.
The owner verified binary availability and a successful native C compile/link/run
probe with GCC 14.4, libelf and OpenSSL. The measured probe loader and libc were
inside the pinned glibc 2.44 closure. No build-from-source fallback is enabled
during tool acquisition.

The first kernel attempt then exposed a missing `mv` command in the private
PATH, before compilation. The kernel profile now exports it and the surrounding
core utilities; image-profile commands stay unchanged. A regression test runs
the exact pinned upstream `scripts/config` with only declared commands, and
confirms that removing `mv` reproduces the failure. The build driver checks
required command executability before fetching source, including for dry-run.
Prepare a new compiler environment and use a fresh build output after this fix;
retain the incomplete attempt for inspection instead of editing its recorded
environment or treating it as a completed build.

The next native attempt reached kernel compilation and stopped at the x86 vDSO
recipe's explicit `sh .../checkundef.sh`: only `bash` had been exported. The
kernel profile now exports both names from the same pinned Bash output, audits
both executables and exercises a Bash recipe calling `sh` through the private
PATH. A regression test runs the actual upstream vDSO checker against a tiny
compiled shared object and reproduces the missing-command failure without `sh`.
The image profile remains unchanged. This is a command-export issue, not observed
evidence of a libc incompatibility.

After import, the preparer compiles, links, executes and inspects a small C probe
using libelf and OpenSSL. The probe's ELF loader/libraries must resolve inside
the retained compiler closure. Existing direct-tool/script and Python runtime
checks also run for this separate environment. This exercises new compiler,
header and link dependencies before the large kernel build; it does not repeat
unrelated account/generation/network acceptance.

The kernel itself is not a glibc userspace program. Host build helpers are,
so their compiler/runtime closure matters. Source shell scripts may still use
Base-provided shebangs; not every subprocess in arbitrary upstream scripts is
traced. The measured compiler and helper probes are bounded evidence, not a
general proof of all NSS/PAM/plugin compatibility. No Base libc replacement or
universal LD_LIBRARY_PATH/LD_PRELOAD workaround is introduced.

## Build command and records

Use the private 64-GiB workspace and initially two jobs on the 4-GiB build VM.
Check real available space before compiling; large Debian configurations still
produce many modules even without debug information. Keep new kernel source,
objects and outputs outside the previous frozen image-build input tree.

```sh
/NEW/KERNEL-ENV/run python3 -I -B tools/mojt-kernel-build.py \
  --plan manifests/kernel-first-build.json \
  --config /FROZEN/DEBIAN.config --config-sha256 ACTUAL_SHA256 \
  --environment /NEW/KERNEL-ENV --output /NEW/KERNEL-BUILD \
  --jobs 2 --dry-run
```

The helper is backend-independent at build time: it consumes the prepared
compiler environment/commands and invokes Kbuild, without Nix package resolution.
Its backend-neutral mojt-build-env-v1 record must identify the kernel profile
and successful C probe. The current producer is Nix-specific; the build helper
does not inspect its backend source/dependency identities. The existing image
environment format and directory remain readable and are not converted.
Dry-run validates inputs but fetches nothing and executes no compiler. A real
build fetches the fixed source, uses O= for a separate object tree, and passes
explicit shell/host compiler/target tool paths. It applies scripts/config and
olddefconfig, checks the config and release, builds bzImage plus modules, then
uses INSTALL_MOD_PATH and depmod in a new staging root. It never runs make install
or writes the running machine's /lib/modules or /boot.

After a preparation failure, `--source /EXISTING/CLEAN/CHECKOUT` reuses the
already fetched source in place, while keeping objects and staging in a new
output directory. Before config/build it verifies the exact pinned HEAD,
expected origin URL and a clean Git tree; it checks source cleanliness again
after building. It does not fetch, reset or check out anything in this mode.
Dry-run only validates local paths and inputs, and does not run Git verification.
Do not delete the reused checkout while the build needs it. This is source
reuse, not resumption of an incomplete object/staging tree.

`--resume --source /EXISTING/CLEAN/CHECKOUT` can reuse objects in an existing
incomplete output **before module staging**. It requires the `.building` marker,
no ready `kernel.json`, a matching copied Debian config hash, regular object/root
directories, and an empty staging root. Input separation, tool checks, exact
source commit/origin and source cleanliness are checked again. The helper
regenerates config from the frozen Debian input plus current plan, validates it,
then lets Kbuild decide what must rebuild; a different compiler-environment path
can invalidate command lines and recompile objects. It neither clears the object
tree nor adopts partially installed modules. Completed outputs are rejected.
Dry-run checks resume prerequisites but does not execute Git or regenerate config.

Make receives an explicit empty `LOCALVERSION` command-line suffix, retaining
the plan's `CONFIG_LOCALVERSION`. This prevents an unrecorded `+` from an absent
local tag ref in a shallow checkout; commit and cleanliness checks remain strict.
The full config diff is written before policy validation and all mismatches are
reported together, so a failed check retains useful evidence.

Successful output contains:

- `root/boot/vmlinuz-<release>`, config and System.map.
- `root/lib/modules/<same-release>/`, stripped modules and dependency indexes.
- `debian.config`, `config.diff`, object/source trees and `kernel.json`.

Scratch build/source links are removed from the staged module tree. The helper
records file hashes/modes, source/plan/base/final config identity, compiler
report identity, module count and a sampled module vermagic matching the release.
A kernel content ID covers that manifest. `.building` remains on failure; no
ready manifest/activation is claimed. Deterministic KBUILD user/host/timestamp
settings reduce incidental variation but do not establish reproducible binaries.

## Native acceptance: 2026-10-28

The owner completed the chain from the private compiler environment through
a bootable image assembled on Mojt, then ran the new image under QEMU on the
Debian host. The tested functional source revision was
`61eb034819d481b2254d7096bc24b2f63a53c37c`.

| Stage | Observed result |
| --- | --- |
| Compiler/runtime | GCC 14.4 compiled, linked and ran the libelf/OpenSSL probe; its ELF loader and libc resolved inside the pinned glibc 2.44 closure. |
| Kernel build | The helper reached `READY` for `6.12.107-mojt1`, with matching staged modules, dependency indexes, sampled vermagic, config diff and `kernel.json`. |
| Image assembly | Mojt built a new UEFI image from frozen Base 0.1.3 and the existing step-10 System payload. Frozen input verification passed across assembly. |
| Runtime module staging | The existing hardware profile copied the complete matching module tree and retained firmware/licenses. The image builder's reported 17 modules refer to early initramfs inputs. |
| Boot/login | The new image booted as `system-kernel-A`, with authenticated root serial login and `uname -r` reporting `6.12.107-mojt1`. |
| Matching runtime driver | `/lib/modules` listed only the new release. `e1000e.ko` came from that tree, had vermagic `6.12.107-mojt1 SMP preempt mod_unload modversions`, and was loaded in `/proc/modules`. |
| Network integration | `ethtool -i eth0` reported e1000e with version `6.12.107-mojt1`; certificate-verified HTTPS returned the expected Nix cache information. |
| Service health | `systemctl --failed` reported zero failed units. |

The original frozen input inventory still names the retained Debian kernel:
that inventory was preserved, while the separately staged own-built kernel was
explicitly selected for the new image. The build VM's running kernel and the
known-good reference disks were not replaced. The fixed 1970 build timestamp in
`uname` is intentional build metadata, not a runtime clock reading or proof of
bit-for-bit reproducibility.

Focused automated coverage includes 18 kernel/environment tests, including the
real upstream config and vDSO shell scripts, missing-command rejection, config
policy checks, source mismatch rejection, private staging and pre-staging resume
guards. The complete source build and boot evidence above is owner-run native
acceptance, separate from the mocked driver tests.

Two operational details from image preparation matter when reproducing it:

- Password-mode image assembly requires terminal stdin. If its command is
  inside a heredoc, append `</dev/tty` to the builder invocation.
- On the Debian host, expose administrative tool directories before serial
  conversion: `export PATH="/usr/sbin:/sbin:$PATH"`. A successful image export
  can be retained if conversion stops at this prerequisite check.

This accepts the first native kernel build, matching runtime module use and
basic VM integration. It does not establish a self-hosted source build of all
System packages, own-kernel physical-hardware acceptance, production Secure Boot,
general libc/ABI compatibility, reproducible binaries or existing-disk Kernel
publication/rollback. Retain the working reference and the successful result.
Further A/B/A/account loops are unnecessary without a relevant behavior change.

## Primary references

- [Linux 6.12 build requirements](https://www.kernel.org/doc/html/v6.12/process/changes.html).
- [Kbuild output/module staging variables](https://docs.kernel.org/kbuild/kbuild.html).
- [Stable source tag](https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/tag/?h=v6.12.107).
