<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native Kernel build and packaging acceptance

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

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

## Native distribution package acceptance: 2026-10-29

The already accepted kernel output was subsequently packaged inside Mojt with
the [native artifact prototype](native-artifact-format-history.md#owner-native-package-acceptance-2026-10-29),
without rebuilding. The new package release `6.12.107-r1` explicitly retains
the actual kernel/module release `6.12.107-mojt1`, original build record and
configuration evidence. Input-record checksums remained unchanged. After export
from the powered-off workspace, independent Debian verification passed against
the full artifact ID, archive hash/size, embedded/detached descriptors and
original build provenance. This is packaging/content verification, separate from
the boot acceptance above; Kernel installation and boot selection remain future work.



## Build-attempt context

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

