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
| `mbt bootstrap` | `mojt_bootstrap.py` and the existing image assembler | Install exact inputs and select the first native-v2 deployment on a new image |

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
A private environment is not a security sandbox.

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
Python with `-I -B` and a fixed helper/System/Base PATH, excluding Ports.
The build environment separately retains its tools and their library closure.

Base runtime gains no Python requirement. The Nix adapter remains the initial
environment-acquisition backend; the frontend itself only delegates. Existing
ELF loader/library closure probes stay in that helper. Neither the build
environment nor MBT changes Base libc or claims arbitrary plugin ABI safety.

## Fresh native-v2 bootstrap

The first public profile is x86-64, serial console, UEFI/GPT and VirtIO. It requires
an account-enabled step-10 System payload and interactive password login. It
creates a new regular disk image; it accepts no physical target device and cannot
adopt an existing installation or resume a failed preparation.

```sh
mbt bootstrap --base-package BASE.tar.zst --base-artifact sha256:BASE_ID \
  --base-context base-context.json --kernel-registry KERNEL_REGISTRY \
  --kernel-artifact sha256:KERNEL_ID --system-payload SYSTEM_PAYLOAD \
  --system-generation system-builder-A --system-version 0.2 \
  --system-revision 1 --with-build-tools --output NEW_IMAGE_DIRECTORY --dry-run
```

Paths and IDs are placeholders for already retained, verified inputs. Preview
validates them without writing an environment, registry or image. Actual image
creation requires root and an interactive terminal for the new guest password;
repeat the same command without `--dry-run` in that context. No password flags or
automatic privilege escalation are provided. `mbt env --profile image` supplies
the image tools, including the namespace/mount helpers; use its existing `run`
launcher if these tools are not already available on the builder.

The assembler first creates a private directory tree and initializes fresh state.
Before formatting the new image, a private mount/PID namespace runs fixed
manager-owned code using the accepted System's pinned Python and Nix. It imports
registration into the new target's private store database, installs the exact
Base and packaged System through MPM, retains the exact Kernel, freezes bootstrap
Python and constructs, admits and selects one native-v2 deployment through the
existing MPM handover/constructor/selection libraries. It does not execute archive
hooks, candidate Python or host-side Nix database mutations. Namespaces contain
helper lifetimes and mounts; they are not a sandbox for untrusted package code.

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

## What is deliberately still open

- Approve/refine this small syntax before treating it as the stable user contract.
- Carry one physical hardware profile's console, storage modules and firmware
  through that same bootstrap path. Do not introduce a generic partitioner first.
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
Bootstrap tests cover read-only exact-input preview, namespace boundaries,
failure before disk creation/publication, and one shared synthetic native
install/stage/select fixture, including result/boot-file agreement. Existing build-environment, Kernel
and System assembly tests continue to own their implementation checks. This is
not a new real compiler or VM boot acceptance run. A joined real VM acceptance
remains before physical rollout.
