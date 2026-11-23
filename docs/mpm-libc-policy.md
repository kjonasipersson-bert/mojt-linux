<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Libc runtime ownership

The [libc/shared runtime contract, version 1](libc-contract.md) defines the
decided requirements and their implementation status. This page describes the
current mechanisms and runtime map.

Base, System and Ports have independent runtime ownership. Mojt does not select
one machine-wide active glibc for all programs. The source-built Base and the
retained Nix objects can contain different glibc builds, including different
builds with the same upstream version number.

## The current runtime map

| Consumer | Loader/libc ownership | What identifies it |
| --- | --- | --- |
| Native programs in source Base 0.2.0 | Mojt-built glibc 2.44 under `/usr/lib`, exposed through the standard x86-64 loader paths | Whole Base artifact and its source/build provenance |
| Nix-provided System executables | Exact provider loader and libraries retained with their respective programs | Imported output identities, references and ELF interpreter/library paths |
| Nix-provided Ports executables | The same mechanism, independently for each installed application/toolchain build | Exact application artifact and retained provider closure |
| Static BusyBox in early/final boot | Self-contained executable, supplied separately from Base | Retained boot/System input; no external glibc |

The [Base producer](base-source-build.md) builds its Unix programs and supporting
libraries against its own staged runtime, and rejects accidental runtime
references to Nix or the build workspace. Its initial `libgcc_s.so.1` is an
explicit bootstrap binary input, recorded separately from glibc source inputs.
The Base runtime does not contain a compiler SDK or libc development headers.

For an exact dynamic ELF executable, its declared interpreter and library search
references determine normal loader resolution under its configured environment.
The Nix package origin alone does not identify a universal libc version. A
closure can contain multiple libc objects for different executables, and shell
wrappers can launch programs with their own runtime references.

Changing Base does not relink retained Nix programs or redirect their loader.
Conversely, installing another libc as a Port does not repair programs which
still reference an older object. Their consumer artifacts must change. Provider
dependencies stay retained with their consumers; cleanup cannot choose one libc
by newest version and remove the others.

This map describes the runtime ownership model. Exact store hashes belong to
the selected artifacts and installation records; they are not distribution-wide
constants. Optional [ELF/process inventory](libc-inventory.md) can investigate an
unknown reference or a suspected runtime problem. Repeating live process maps
is not required for every unchanged imported program or Base selection.

## An older compiler is two different runtime questions

A request for an older GCC release selects a package release from the configured
catalog; the exact accepted provider build determines its dependencies. GCC's
version number alone does not fix a glibc version, and an old GCC build can have
a different runtime from the current Base without replacing Base.

Distinguish:

1. **Running the compiler:** GCC and its helper programs use their retained
   executable/library references, just as other Ports do.
2. **Running its output:** the linked program uses the target headers, startup
   objects, libc, compiler runtime libraries and loader selected by the complete
   build toolchain. Compiler configuration, Nix wrappers, sysroot and link flags
   participate in that selection.

Installing GCC does not itself promise that its output targets Mojt Base's libc.
The existing Base producer deliberately uses a plain native GCC with an explicit
staged target sysroot instead of assuming that a Nix compiler wrapper targets
Base. A general selectable Mojt SDK/toolchain contract remains future MBT work;
this document introduces no new compiler selector, automatic retargeting or
normal-install compatibility scan.

## Shared configuration and module boundaries

The [resource/responsibility map](libc-integration.md) records concrete shared
inputs, their current suppliers and the remaining integration decisions.

Separate executable/library references do not make separate host environments.
The following are integration boundaries, not evidence that two libc objects
are linked into the same process:

| Boundary | Shared input or interaction | Mojt's present arrangement |
| --- | --- | --- |
| Host/user lookup | `/etc/nsswitch.conf`, `/etc/hosts`, resolver configuration and account databases | Persistent machine files; account setup requires local NSS `files` entries |
| Authentication/modules | PAM configuration selects code loaded into the login process | System supplies explicit `/run/mojt-system/pam/` module paths; Base supplies no PAM runtime |
| Locale selection/data | `LANG`/`LC_*` select behavior; libc locates its supported locale data | Base supplies C/C.UTF-8 data; System defaults unset `LANG` to `C.UTF-8` |
| Time and TLS data | Programs consult configured timezone and certificate paths | System exports its retained `TZDIR` and certificate references |

Configured external NSS services, PAM modules and application plugins need a
compatible arrangement for the process loading them. They are different from
starting a separate executable. Mere presence in a shared directory is not a
module compatibility contract. Mojt does not merge the runtimes with a global
`LD_LIBRARY_PATH`, `LD_PRELOAD`, `LOCPATH` or `GCONV_PATH`.

DNS and C.UTF-8 are useful small diagnostic examples when these boundaries
change, not mandatory tests for every Nix import. A libc-based hostname lookup
can check the resolver/NSS configuration used by that consumer. A direct DNS
query tool need not exercise that path. DNS success is not a general ELF ABI
guarantee; network failure alone does not establish a libc problem.

C.UTF-8 is relevant because it is the delivered default when the user has not
chosen another locale. Acceptance can check that an affected runtime supports
that setting. This neither establishes identical collation between runtimes nor
proves that every retained glibc can read one common binary locale archive.
Nixpkgs documents consumer-dependent locale data on non-NixOS hosts. Broader
locale/module support requires a separate, explicit contract. These checks
belong to focused build/release acceptance or diagnosis, not the ordinary
installation/activation path.

## References

- [System/Base ABI requirements](system-manifest.md#base-abi-requirements)
- [GNU libc NSS configuration](https://sourceware.org/glibc/manual/2.44/html_node/NSS-Configuration-File.html)
- [GNU libc locale names/data](https://sourceware.org/glibc/manual/2.44/html_node/Locale-Names.html)
- [Nixpkgs locales and toolchain wrappers](https://nixos.org/manual/nixpkgs/unstable/)
- [GCC directory/sysroot options](https://gcc.gnu.org/onlinedocs/gcc/Directory-Options.html)
- [Historical mixed-libc policy proposal](reports/libc-policy-proposal-2026-10.md)
