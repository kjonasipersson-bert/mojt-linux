<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Shared libc integration boundaries

The [runtime map](mpm-libc-policy.md) identifies who supplies each executable's
loader and libraries. This document identifies the machine resources that those
otherwise independent runtimes share. It describes current source-built Base
and generated System behavior. Existing administrator configuration can differ
from initial defaults; publishing a new release does not replace that state.
The [version 1 contract](libc-contract.md) records the decided ownership rules
and distinguishes pending delivery from current behavior.

## Resource and responsibility map

| Resource | Initial supplier or runtime writer | Consumers and boundary |
| --- | --- | --- |
| `/etc/passwd`, `group`, `shadow`, `gshadow`, `shells` | Base seeds minimal defaults; System account provisioning/tools extend the machine databases | Base and provider programs see the same identities; credentials and UID/GID assignments persist independently of code releases |
| `/etc/nsswitch.conf`, `/etc/hosts` | Base supplies `files` account defaults and `hosts: files dns`; administrators own persistent edits | Each libc interprets the shared lookup configuration with its own supported services |
| `/etc/resolv.conf` | NetworkManager in System, using the generated `dns=default`, `rc-manager=file` configuration | Libc-based hostname resolution uses machine resolver configuration; the generated profile requires a regular file, not a silently adopted resolver symlink |
| `/etc/pam.d/*`, `/etc/sudo.conf` | System supplies initial service configuration; administrators retain persistent policy | Module/plugin references use `/run/mojt-system/pam/` and `/run/mojt-system/sudo/`; implementations belong to the running System, not Base |
| `LANG`, `LC_*` and locale data | Base builds C/C.UTF-8 data; Base profile and System environment default empty/unset `LANG` to `C.UTF-8` | The receiving libc must support the selected locale and its data; an inherited `LC_ALL`/`LC_*` can override `LANG` |
| Timezone data and `/etc/localtime` | System retains tzdata and supplies a default `TZDIR`; the administrator chooses machine timezone state | Programs consult their configured timezone inputs; a copied TZif file is persistent data, while a store symlink remains a reference to one particular output |
| Certificate trust data | System retains `cacert` and exports `SSL_CERT_FILE`/`NIX_SSL_CERT_FILE` | Programs honoring those settings use that bundle; this is a data/library-specific interface, not a libc loader choice |
| `/etc/services`, `/etc/protocols` | Base 0.2.1 supplies pinned IANA defaults under `/usr/etc` | Missing-only installation into `/etc` preserves machine copies; consumer/provider overrides remain possible |
| `/bin/sh` and basic Unix commands | Base; System wrappers/start scripts invoke them before executing provider programs | Process launch and command interfaces join the layers without combining the two processes' libc implementations |
| Kernel system-call interface | Selected Kernel and its supported features | All runtimes use the same Kernel; retaining a libc object does not supply a different Kernel or establish every program's feature requirements |

Configuration supplied during fresh assembly uses missing-default rules and
can reject incompatible existing setup. Live update preparation has separate
checks/default handling. Neither mechanism authorizes replacing arbitrary
administrator configuration. See [persistent state](state-layout.md),
[account configuration](system-accounts.md#configuration-and-compatibility) and
[native handover](native-system-handover.md).

## What already has a concrete arrangement

### Identity, networking and authentication

Account setup requires local NSS `files` entries for passwd/group/shadow. It
does not provide a general LDAP/SSSD/NSS module integration policy, or establish
that every external service added to nsswitch works with all retained libcs.
The generated network profile uses one machine resolver configuration rather
than a separate DNS configuration for each Port. Administrator NetworkManager
configuration can change that policy.

PAM and sudo are supplied by System, including their modules, plugins and
privileged helper setup. Persistent configuration names the running profile's
stable paths; the profile selects the exact retained provider implementations.
Base does not supply an alternative authentication stack. This avoids choosing
PAM code from a new Base merely because its libc version changed, but it is not
a general compatibility promise for arbitrary administrator-supplied modules.

These are different kinds of interface: reading passwd or resolver text is
shared-data integration; loading a PAM/NSS/plugin library introduces an
in-process ABI requirement. An external DNS failure can also be a network or
configuration failure, independently of binary linkage.

### Environment and data

System start and the delivered login-profile hook source the selected System
environment. Programs launched elsewhere need not inherit it. The environment
chooses retained certificate paths and supplies defaults for `TZDIR` and `LANG`;
it does not set a global `LC_ALL`, `TZ`, `LOCALE_ARCHIVE`, `LOCPATH` or
`GCONV_PATH`. Base's profile sources the `/etc/profile.d` hooks without rewriting
an existing machine profile.

The Base producer generates C.UTF-8 with its own newly built localedef, using
`--no-archive`. This supplies per-locale data for Base, not a machine-wide binary
archive guaranteed to suit historical Nix glibc builds. An older toolchain can
run with its own retained libc while still inheriting the machine's `LANG`;
matching that setting and any required locale data is a separate question from
which loader starts its compiler.

The source Base does not deliver a CA bundle or full timezone database; System
supplies those inputs. Base 0.2.1 supplies the IANA service/protocol tables as
plain-text defaults. Fresh initialization or explicit missing-default preparation
adds `/etc/services` and `/etc/protocols` when absent. Existing copies remain
persistent machine configuration, as specified by the
[contract](libc-contract.md#2-shared-service-and-protocol-tables-belong-to-base).

Machine-local timezone selection is independent of selecting code. The
documented [timezone procedure](system-environment.md) copies a TZif file into
`/etc/localtime`, keeping that chosen data snapshot until explicitly refreshed.
An administrator-created reference into a store output needs its own retained
lifetime; replacing code or eventually collecting generations cannot infer all
such references from ELF dependencies alone.

## Contract decisions and implementation limits

| Area | Decision and remaining implementation |
| --- | --- |
| Richer locales and old provider runtimes | Compatible data follows the consumer when needed; C/POSIX fallback is explicit and scoped. General automatic matching/import remains unimplemented |
| Service/protocol databases | Implemented in the Base 0.2.1 producer: pinned defaults under `/usr/etc`, added to `/etc` only when missing |
| External NSS/PAM/application modules | Support is feature-specific; local accounts do not imply arbitrary identity-provider/module support |
| Compiling for Mojt Base | A target SDK must identify compiler/binutils, headers/startup objects/libc and compiler-runtime inputs; the general MBT interface remains future work |
| Retention/GC | Retain consumer closures and declared data references; the collector remains future work |

The [contract](libc-contract.md) defines these requirements; it adds no new
commands, migrations or normal-install audits. Kernel/platform requirements and state-format compatibility remain
separate existing boundaries. No support for migrating a Void-built Base layout
is implied by this map.

## Evidence and checking scope

The responsibility map comes from these implementation entry points:

- [`mojt-base-build.py`](../tools/mojt-base-build.py): `defaults`,
  `build_projects`, `target_environment` and output pruning.
- [`mojt_system.py`](../tools/mojt_system.py): `ROLES`, generated NetworkManager
  configuration, environment, login hook, provider references and defaults.
- [`mojt_accounts.py`](../tools/mojt_accounts.py): local NSS requirements, account
  defaults and explicit PAM/sudo module paths.
- [`mpm_boot_handover.py`](../tools/mpm_boot_handover.py): persistent state mounts
  and separate immutable runtime projections.
- [`mpm_defaults.py`](../tools/mpm_defaults.py): explicit missing-default effects.

This is a source-level integration inventory, not a new full runtime acceptance
claim. Optional [DNS/locale diagnostics](libc-inventory.md) are useful when a
relevant runtime, resolver policy, module or locale-data arrangement changes.
Unchanged Nix package references do not require a new test round. A test is
needed to settle a concrete unsupported behavior or changed boundary, not to
re-prove every library reference on each installation or boot.
