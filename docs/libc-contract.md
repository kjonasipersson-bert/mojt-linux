<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Libc and shared runtime contract, version 1

This contract defines ownership and producer requirements for Base, System and
Ports. The implementation-status table distinguishes delivered mechanisms from
requirements still awaiting implementation. It introduces no new command,
automatic migration, dependency substitution or installation-time audit.

The [runtime map](mpm-libc-policy.md) explains the existing linkage model; the
[integration map](libc-integration.md) identifies concrete shared resources and
their present suppliers.

## 1. Runtime ownership and independent releases

Base supplies a coherent loader, libc and supporting runtime for its own Unix
programs. System and Ports preserve the exact provider references belonging to
their respective executable builds. Different libc builds can coexist,
including different builds with the same upstream version number. A version
label alone is not a dependency identity.

A Base change must not retarget an unchanged Port or System binary. Installing
a different libc does not repair or upgrade existing consumers; changing their
runtime requires a replacement consumer artifact/closure. Sharing identical
objects is permitted only with their complete retained lifetime; one global
active libc is not required.

Compatibility concerns actual interfaces: Kernel/platform requirements, Base
commands/ABI, supported configuration and state. Base/System release labels
do not create compulsory version pairs. Existing declaration checks remain;
their conservative Base ABI minimum is not a measured ELF symbol floor. See
[System/Base requirements](system-manifest.md#base-abi-requirements).

## 2. Shared service and protocol tables belong to Base

Base is the supplier of the standard text service/protocol databases. The
planned first delivery is **Base 0.2.1**:

- Release defaults: `/usr/etc/services` and `/usr/etc/protocols`.
- Machine-visible configuration: `/etc/services` and `/etc/protocols`.
- The producer must select a versioned upstream dataset and record its source,
  integrity hash and applicable license notices.

Machine initialization or supported missing-default preparation copies these
defaults only when absent. Existing machine files must not be silently replaced
or removed. A later Base release can carry newer defaults without automatically
refreshing existing `/etc` copies. Changing Base back does not roll back those
machine files. An explicit refresh/merge policy is separate future work.

These are shared text interfaces, independent of one particular libc build.
Ports may use their provider's declared equivalent mechanism where necessary;
each Port does not need a private duplicate of the ordinary machine tables.
The contract does not promise that arbitrary administrator table contents
satisfy every application's requested service or protocol name.

## 3. Locale selection is shared; required locale data follows the runtime

Mojt keeps its C/C.UTF-8 Base baseline and default `LANG=C.UTF-8` when no nonempty
user value is supplied. User `LANG`/`LC_*` settings express desired behavior;
they do not select another libc or establish compatible locale data.

A retained old Port/toolchain may keep its older libc. No extra locale archive
is required merely because the runtime is old. When the consumer needs
additional or version-sensitive locale data, its packaging must identify and
retain compatible data with that runtime. Prefer the provider's existing
packaging and locale-selection mechanisms rather than a new Mojt framework.

Any required locale environment must be scoped to the declared application or
toolchain context, including helpers which inherit that environment. One global
`LOCALE_ARCHIVE`, `LOCPATH` or `GCONV_PATH` must not be used to force all retained
runtimes to consume one data build. Base's per-locale data is not a universal
binary archive for historical provider libcs.

C/POSIX-only operation is an explicit compatibility choice for a tool whose
requirements permit it. It must not silently downgrade other applications or
the user's whole session, and it does not promise UTF-8 behavior for that tool.
Unsupported requested locales need a documented per-consumer arrangement;
retaining the correct executable closure alone is not proof of locale support.

## 4. Shared machine configuration and loaded modules

Account identities, resolver configuration and authentication policy remain
machine state. Release changes preserve them. The current local NSS files/DNS
arrangement and System-owned PAM/sudo implementations remain the initial
integration scope. Publishing a Base with a newer libc does not choose new PAM
modules for an unchanged System.

Loading a module/plugin into a process requires a compatible ABI/runtime
arrangement for that process. Separate executable startup is a different
boundary. External NSS/PAM providers and application plugins need a concrete
supported integration before broader compatibility is claimed. A global
`LD_LIBRARY_PATH` or `LD_PRELOAD` must not merge Base/System/Ports runtimes.

## 5. Compiler runtime and target runtime are separate

An older GCC may run using its own retained libc. Its generated programs target
the headers, startup objects, libc, compiler libraries and loader chosen by the
complete toolchain, wrapper/sysroot and link settings. GCC's release selector
alone does not specify a Mojt Base SDK.

Future MBT toolchain environments must identify and retain those target inputs
alongside the compiler/helper inputs so that ordinary Base/System/Ports updates
cannot silently change a pinned project's build target. The existing private
Base producer's staged sysroot is one implemented build path, not a general
SDK-selection interface.

## 6. Retention and checking boundaries

Consumers protect their complete declared runtime dependencies, including
needed compatible data. Future GC must respect running/next-boot deployments,
explicitly retained recovery content, retained application/toolchain choices and
their references. It must not discard an older libc or data output by comparing
version numbers. Administrator references into provider storage need an explicit
retention arrangement; ELF dependencies alone do not describe every config/data
reference. This specifies GC requirements, not an implemented collector.

Producer/release acceptance checks the declared target and supported integration.
Focused diagnostics settle concrete failures or changed boundaries. Ordinary
installation, preparation and selection retain their required input/path,
compatibility, locking and publication checks; this contract adds no mandatory
DNS/locale probe, process-map inventory or repeated full-content audit. Existing
explicit verification remains available.

## Implementation status

| Requirement | Status |
| --- | --- |
| Independent Base and retained provider runtimes | Implemented for the current source Base and native System/Ports mechanisms |
| Base C/C.UTF-8 and System locale default | Implemented; not a promise of richer locales for every historical runtime |
| Base-owned service/protocol defaults | Decided; targeted for Base 0.2.1, not yet delivered by the current 0.2.0 producer |
| Runtime-scoped additional locale data | Decided policy; existing package arrangements can supply it, but general automatic Mojt matching/import/wrapping is not implemented |
| General pinned Mojt target SDK | Future MBT work; installing a GCC Port does not create it |
| Reference-aware runtime/data GC | Future work; no collection command is introduced |
