<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Minimal MBT: first executable interface proposal

2026-11-10. Experimental syntax for owner review, built over the already tested
tools. This first slice starts delivery 2 of the shorter consolidation route.
It does not settle a general recipe language, implement bootstrap or complete
physical installation. MPM's public syntax is unchanged.

## Three operations first

| Proposed command | Existing implementation | Actual effect |
| --- | --- | --- |
| `mbt env` | `mojt-build-env.py` | Create a new private pinned image/Kernel tool environment |
| `mbt build kernel` | `mojt-kernel-build.py` | Build a separate versioned Kernel and matching modules |
| `mbt package` | `mojt-artifact-pack.py` | Package retained inputs or verify a native archive |

There is no separate `plan` verb. Environment creation and Kernel compilation
retain their existing `--dry-run`, refusal of existing outputs, frozen input
checks and explicit continuation rules. Package creation has no dry-run yet;
`mbt package verify` reads an existing archive. MBT does not install, activate,
select next boot or reboot. Those operations belong to MPM.

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

`MBT_FILES` is an explicit additional source-file list; normal System assemblies
need not carry these entrypoints. The complete System manifest inventories their
bytes. `mbt-runtime.json` version 1 describes the file set, interpreter and scope;
it is not a second package database. The installed launcher uses pinned System
Python with `-I -B` and a fixed helper/System/Base PATH, excluding Ports.
The build environment separately retains its tools and their library closure.

Base runtime gains no Python requirement. The Nix adapter remains the initial
environment-acquisition backend; the frontend itself only delegates. Existing
ELF loader/library closure probes stay in that helper. Neither the build
environment nor MBT changes Base libc or claims arbitrary plugin ABI safety.

## What is deliberately still open

- Approve/refine this small syntax before treating it as the stable user contract.
- Join new-target native-v2 bootstrap to the shared MPM installation/deployment
  functions. The existing image builder is not exposed as `mbt bootstrap` yet:
  wrapping an older boot layout would not finish this joined workflow.
- Carry one physical hardware profile's console, storage modules and firmware
  through that same bootstrap path. Do not introduce a generic partitioner first.
- Run one bounded VM journey with the delivered MPM/MBT, then a dedicated physical
  disk installation, update, Kernel build/boot and return.

These remain within the same second delivery, not one PR per helper or command.
Remote signing, physical collection, generic migration hooks, named registries
and rebuilding all third-party sources are not prerequisites for this milestone.

## Focused validation

Five frontend/delivery tests cover scoped help without provider loading, refusal
of root compilation, a real Kernel dry-run with frozen config validation, optional
System delivery and real native packaging/verification through the copied
installed frontend without a source checkout. Existing build-environment, Kernel
and System assembly tests continue to own their implementation checks. This is
not a new real compiler or VM boot acceptance run.
