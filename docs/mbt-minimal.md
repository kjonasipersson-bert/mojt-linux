<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Minimal MBT: first executable interface proposal

2026-11-10. Experimental syntax for owner review, built over the already tested
tools. This first slice starts delivery 2 of the shorter consolidation route.
It includes fresh native-v2 image bootstrap, but does not settle a general recipe
language or complete physical installation. MPM's public syntax is unchanged.

## Four bounded operations

| Proposed command | Existing implementation | Actual effect |
| --- | --- | --- |
| `mbt env` | `mojt-build-env.py` | Create a new private pinned image/Kernel tool environment |
| `mbt build kernel` | `mojt-kernel-build.py` | Build a separate versioned Kernel and matching modules |
| `mbt package` | `mojt-artifact-pack.py` | Package retained inputs or verify a native archive |
| `mbt bootstrap` | `mojt_bootstrap.py` and the existing constructor | Install exact inputs and select the first native-v2 deployment on a new image or prepared mounted partitions |

There is no separate `plan` verb. Environment creation and Kernel compilation
retain their existing `--dry-run`, refusal of existing outputs, frozen input
checks and explicit continuation rules. Package creation has no dry-run yet;
`mbt package verify` reads an existing archive. Building and packaging never install
or activate their result. Bootstrap uses MPM's installation and deployment
libraries on its new target; updates to an existing installation belong to MPM.
No command implicitly reboots.

The frontend loads only fixed sibling helper modules. It does not discover
program implementations through PATH, load candidate package code, invoke shell
command strings or translate backend-specific identities. Helpers keep their
existing flags/records and direct script entrypoints. The `--plan` Kernel flag
names the existing versioned build recipe; it is not an MBT planning operation.

Filesystem paths name environments and workspaces. No global environment-name
registry, automatic compiler activation or saved-plan execution is needed.
Compilation through MBT requires an ordinary user; root may preview, but the
frontend does not silently run a build through sudo or change workspace ownership.
A private environment is not a security sandbox. Tool acquisition uses the
provider's store permissions: on Mojt's current root-owned single-user Nix store,
an administrator imports the tools into a directory traversable/readable by the
builder, and the ordinary user then compiles with it. MBT does not grant ordinary
users shared-store write access or silently start a provider daemon.

## Concrete journey

These commands become available in a builder-enabled System. Inputs must already
be present: the System's explicit source pin, a reviewed Kernel recipe, a frozen
x86-64 Kernel configuration and its SHA256. The included recipe is an example
pinned to the earlier accepted upstream build, not a moving latest-Kernel policy.

```sh
mbt env --profile kernel --source-manifest /run/mojt-system/ports.toml \
  --output "$HOME/build/kernel-env" --dry-run
# Repeat without --dry-run after reviewing the exact tool imports.

mbt build kernel \
  --plan /run/mojt-system/share/mbt/kernel-first-build.json \
  --config "$HOME/build/kernel.config" --config-sha256 CONFIG_SHA256 \
  --environment "$HOME/build/kernel-env" \
  --output "$HOME/build/kernel-result" --dry-run
# Repeat without --dry-run to compile as this ordinary user.

mbt package kernel --build "$HOME/build/kernel-result" \
  --revision 1 --output "$HOME/packages/kernel"
mbt package verify "$HOME/packages/kernel/EXACT_ARCHIVE.tar.zst" \
  --expected-id sha256:EXACT_ARTIFACT_ID
```

The packager reports the exact archive path and artifact ID; placeholders above
must be replaced with those reported results. Kernel build identity/provenance
and packaging revision remain separate. Ordinary MPM Kernel install/activation
consumes that archive; building and packaging never select it automatically.
Root-only installation is a separate administrative action, not a reason to run
the compiler as root.

`--source DIRECTORY` reuses a clean source checkout at the pinned commit.
`--resume` only continues the existing eligible incomplete build with its same
inputs and explicit source. It does not adopt arbitrary or partially staged
results. The existing environment's `run` launcher remains available for manual
commands without adding another MBT command family.

## Delivery in System

`--with-build-tools` on the existing VM/native image builders opts into MBT in
the new System. The corresponding `mojt_system.install` argument defaults false.
System step 3+ supplies its existing management Python; step 9+ also exposes
`man mbt`. No new provider payload or compiler is added by this flag.

`MBT_FILES` and `MBT_SOURCE_FILES` explicitly list the additional code and assembly
assets. An installed builder can assemble another builder without a source
checkout; the assets include the account helper, diagnostic script, recipe,
example metadata and manual sources at their expected relative paths. Normal
System assemblies need not carry these extra inputs. The System manifest inventories their
bytes. `mbt-runtime.json` version 1 describes the file set, interpreter and scope;
it is not a second package database. The installed launcher uses pinned System
Python with `-I -B` and preserves the invoking tool PATH, so an explicit private
environment's `run` launcher can supply the image/Kernel tools. Bootstrap refuses
tools selected from the shared `/var/lib/mojt/ports` profile. MPM's own fixed
management PATH is unchanged. The build environment separately retains its tools
and their library closure.

Before importing manager libraries, public MBT operations copy their fixed code
and assembly assets into a private execution directory. Files receive explicit
`0644` modes, directories `0755`, the enclosing directory `0700`, and the closed
inventory is checked before a new isolated Python process starts. A development
checkout with group-writable files is an input, not the runtime measured by MPM;
MBT changes neither its modes nor the caller's home. Changed or linked resources
are rejected. The temporary copy lives until the operation finishes, then is
removed. It is not another installation or registry.

`mojt-mbt-execution-v1` records the exact relative paths, modes and SHA256 values.
Its ID covers those resources; the source location is separate provenance.
A successful bootstrap retains this record as `builder-runtime.json`. This is
content evidence, not authentication of the checkout or release signing.

Base runtime gains no Python requirement. The Nix adapter remains the initial
environment-acquisition backend; the frontend itself only delegates. Existing
ELF loader/library closure probes stay in that helper. Neither the build
environment nor MBT changes Base libc or claims arbitrary plugin ABI safety.

## Fresh native-v2 bootstrap

The [mounted installation increment](mounted-installation.md) adds the same
construction path for an empty mounted ext4 root and FAT32 ESP on one prepared
GPT disk. USB is used for startup/installation; SSD installation precedes the
physical compiler/performance session. `--with-installer-inputs` carries reusable
local data, and `--inputs DIRECTORY` consumes it without a checkout. The mounted
path does not partition, format or overwrite an existing installation.

The default profile is x86-64, serial console, UEFI/GPT and VirtIO. Bootstrap requires
an account-enabled step-10 System payload and interactive password login. With
`--output`, it creates a new regular disk image; this mode accepts no physical
target device. Neither mode adopts an existing installation or resumes a failed
preparation.

```sh
mbt bootstrap --base-package BASE.tar.zst --base-artifact sha256:BASE_ID \
  --base-context base-context.json --kernel-registry KERNEL_REGISTRY \
  --kernel-artifact sha256:KERNEL_ID --system-payload SYSTEM_PAYLOAD \
  --system-generation system-builder-A --system-version 0.2 \
  --system-revision 1 --with-build-tools --output NEW_IMAGE_DIRECTORY --dry-run
```

Paths and IDs are placeholders for already retained, verified inputs. Preview
validates them without creating a tool environment, registry or image. It uses
temporary execution files; root also creates a disposable static-BusyBox jail
to exercise the real private PID/mount namespace and host `chroot` entry with
a guest-only PATH. It neither starts the candidate System nor asks for a
password. The versioned `preflight` report distinguishes a passed privileged
probe from an ordinary-user preview where that probe has not run.
Actual image
creation requires root and an interactive terminal for the new guest password;
repeat the same command without `--dry-run` in that context. No password flags or
automatic privilege escalation are provided. `mbt env --profile image` supplies
the image tools, including the namespace/mount helpers; use its existing `run`
launcher if these tools are not already available on the builder.

Both preview and image creation check the prepared manager, required host tool
locations and static BusyBox applets. For actual creation, the privileged probe
runs before Base extraction, password entry and VM assembly. Preflight does not
claim that the complete constructor or a guest boot has passed; those remain
separate acceptance gates.

The assembler first creates a private directory tree and initializes fresh state.
Before formatting the new image, a private mount/PID namespace runs fixed
manager-owned code using the accepted System's pinned Python and Nix. It imports
registration into the new target's private store database, installs the exact
Base and packaged System through MPM, retains the exact Kernel, freezes bootstrap
Python and constructs, admits and selects one native-v2 deployment through the
existing MPM handover/constructor/selection libraries. It does not execute archive
hooks, candidate Python or host-side Nix database mutations. Namespaces contain
helper lifetimes and mounts; they are not a sandbox for untrusted package code.

Privileged input/assembly work uses a root-controlled private directory under
the resolved `/var/tmp`, independently of the output's owner or `TMPDIR`.
MPM's target ancestry checks remain unchanged. The completed image is staged
beside its destination only after MPM verification; a cross-filesystem transfer
uses sparse/reflink-aware copying and rechecks the boot result before ownership
handoff and the final same-filesystem publication rename. A caller-owned home
is an output location, never the privileged MPM working target.

The same verified tree is then packed into a new disk image. No loop mapping or
mounting/finalizing of an existing image is required. Failure before publication
leaves no advertised output image. The selected deployment, boot files and
result sidecars must agree before publication. No direct-Kernel boot launcher
bypasses that selection. `bootstrap.json` and `bootstrap-request.json` are
versioned result/provenance records, not a second installation database; the
temporary legacy assembly seed is not the published boot contract. System
packaging version/revision are explicit and distinct from provider versions.
SHA256 verifies integrity/identity, not publisher authentication; signing remains
future work. Normal boot retains its existing bounded checks, without full
payload scans.

This bootstraps an installation from prebuilt inputs. It is not a complete source
rebuild of Base, the Kernel or third-party System packages. A resulting builder
can separately acquire a private compiler environment, build/package a Kernel,
and install/activate it with MPM.

### ThinkPad image profile

`--hardware-profile thinkpad-x1-carbon-3 --firmware-root EXTRACTED_FIRMWARE_ROOT`
selects the existing ThinkPad X1 Carbon 3 hardware policy: UEFI, local `tty1`
password login, USB/SATA/ext4 and keyboard modules in the initramfs, and explicit
runtime graphics/Ethernet/Wi-Fi drivers. It uses the same native-v2 bootstrap;
it does not turn the output path into a physical disk target.

The selected native Kernel artifact supplies the complete module tree. It is not
duplicated inside System. Firmware and upstream licenses are packaged into the
native System component, inventoried with that profile and mounted read-only at
the resolved `/lib/firmware` before drivers start. `hardware.json` version 2 records
the extraction/build provenance and declares `modules_location=native-kernel`;
the deployment remains the authority for the active Kernel's exact identity.
The native-v2 `firmware` list stays empty because there is no independently
installed firmware artifact in this profile.

The firmware input is the extracted Debian root described in
[the ThinkPad guide](thinkpad-usb-boot.md#2-prepare-debian-trixie-kernel-and-firmware-inputs).
Its Intel 7265 firmware, signed regulatory database and required upstream licenses
must be present. Bootstrap freezes only those firmware/license trees and their
provenance, not an unrelated extracted distribution kernel. Source and copied
input identities are checked before use. Plain hashes are not authentication.

The boot record binds local console and `thinkpad-x1-carbon-3-v1`. Menus cannot
mix it with the VM profile. MPM updates preserve that machine policy; each new
Kernel construction resolves both early and runtime driver dependencies. Normal
boot checks paths and small hardware metadata without scanning firmware content.
Firmware is covered by the System content proof for explicit full verification.
Its mount remains until the existing static exitrd teardown. General service or
firmware changes through System upgrade still need a supported transition policy;
the unchanged-startup gate is not bypassed by this profile.

The local-console launcher offers SATA or USB emulation via `QEMU_DISK_BUS`.
Use `QEMU_MEMORY_MIB=4096 QEMU_CPUS=8` for a builder VM instead of editing its
launcher. These affect QEMU resources, not the build recipe's explicit job count.

## What is deliberately still open

- Approve/refine this small syntax before treating it as the stable user contract.
- Run one bounded VM journey with the delivered MPM/MBT, then a dedicated physical
  disk installation, update, Kernel build/boot and return.

These remain within the same second delivery, not one PR per helper or command.
Remote signing, physical collection, generic migration hooks, named registries
and rebuilding all third-party sources are not prerequisites for this milestone.

## Focused validation

Frontend/delivery tests cover scoped help without provider loading, refusal
of root compilation, a real Kernel dry-run with frozen config validation, optional
System delivery and real native packaging/verification through the copied
installed frontend and successor System assembly without a source checkout.
The runtime regression makes a real Git checkout under umask `0002` below a
`0700` home and runs the public package and bootstrap-preview commands with
isolated Python. It checks the unchanged checkout, deterministic resource ID,
strict prepared-file permissions and rejection of altered/extra resources.
Root coverage exercises actual namespace/chroot entry and the existing joined
construction fixture checks the execution receipt survives publication/handoff.
Bootstrap tests cover read-only exact-input preview, namespace boundaries,
failure before disk creation/publication, and one shared synthetic native
install/stage/select fixture, including result/boot-file agreement. A joined
hardware-image fixture also covers account-enabled builder assembly, firmware
freezing, exact package installation, construction, selection and final output.
Injected mount checks cover read-only firmware and exitrd ordering. Existing build-environment, Kernel
and System assembly tests continue to own their implementation checks. This is
not a new real compiler or VM boot acceptance run. A joined real VM acceptance
remains before physical rollout. The public preview does not substitute for a
complete public bootstrap using the retained real System export. The next
acceptance is one explicitly authorized fresh public bootstrap with those
retained inputs, followed by guest boot. #51 remains draft until it passes.

## One joined acceptance journey

For the subsequent lightweight physical measurement session, see
[ordinary MPM/MBT command performance](physical-performance.md). It reuses the
accepted builder and records command timings without repeating the VM matrix.

For terminal-only testing of a stopped local-console native-v2 image, the
existing `tools/mojt-vm-serial.py --source IMAGE --output NEW_SERIAL_COPY`
helper adds an authenticated serial service in a separate copy's persistent
`/etc`. It retains the native deployment/selection, boot files and builder
sidecars; it does not reconstruct the installation or change its hardware
profile. The local console remains available. Start the copy's launcher with
`QEMU_DISPLAY=none` and use the invoking terminal for login/paste. The source
must be stopped; QEMU image locking is never bypassed.
The helper first replays the ext4 journal and runs preen on the **private
extracted partition**, accepting only clean/safely corrected outcomes. A
read-only check alone can return zero while committed transactions still need
replay, so it is insufficient before raw `debugfs` writes. After console setup,
the filesystem must pass read-only verification and have no recovery/error
flags. The reconstructed partition is compared byte-for-byte before publication.
Phase messages and disk-copy progress are printed. Neither the source image nor
an existing failed copy is repaired or overwritten.

After focused CI/review, exercise public construction by creating one **new** sufficiently sized builder image (for example
`--disk-size-mib 32768`) from retained exact inputs using this public command.
For the hardware profile, boot that image once with USB emulation in QEMU on the
Debian desktop. Check native-v2 selected/running agreement, no failed units,
accounts, network and the installed `mpm`/`mbt` manuals. Confirm modules and
firmware are read-only and `/home`, `/root`, `/etc`, `/var` are persistent.

Inside that installation, acquire a pinned Kernel environment with the store's
required permissions and run its existing compiler/libelf/OpenSSL/loader probe.
Keep the tool environment readable by the builder; compile and package one
versioned Kernel through MBT as an ordinary user. As administrator, install that exact package
with MPM, preview its activation, activate it and reboot the same image. Check
the new exact running artifact, modules, identities and one persistent marker;
then return to the retained prior deployment. Exercise one Ports install/use.
Do not repeat every old component/version cross-product.

That proves the joined VM workflow, not real hardware. Then use a separately
identified dedicated physical disk for the same profile. Choosing and writing
that destination is a separate explicit operation, outside `mbt bootstrap`.
