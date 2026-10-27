<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MPM libc and mixed Nix closures — proposal 1

Proposed 2026-10-27; companion to the [selector/catalog contract](mpm-selectors.md).
Facts below describe the backend; the numbered rules are proposed Mojt policy.
No loader changes, dependency substitutions or new compatibility enforcement
are implemented by this documentation change.

## Why several glibc versions are expected

Normal Nixpkgs Linux executables use store-specific linker/library references.
Nix retains runtime output closures, rather than requiring one machine-wide
library version. Base's Void-derived libc and different Nix libc objects can
therefore coexist. Different applications, helper subprocesses and System
generations may use different objects without selecting a global active glibc.

A transitive closure may contain multiple libc objects; that does not mean one
ELF process loads all of them. A launcher can start another program with its
own loader. Store references are not process isolation: kernel, configuration,
users, service protocols and some dynamically discovered modules remain shared.

**For Mojt:** a newer Nix glibc normally avoids requiring a Base glibc replacement
for an otherwise supported Nix executable. It does not establish that every
Nix package works on an older Base or Kernel.

## Proposed policy

1. **Freeze the real runtime.** An artifact records its backend output/NAR
   identity and transitive references. Where audited, record ELF interpreter,
   runtime libc object(s) and validation evidence. Do not reduce identity to
   app version plus a glibc version string: patches/build options matter too.
   Do not infer an application's libc from whichever getconf/ldd is on PATH.

2. **No global substitution.** Do not overwrite Base's libc/loader, create a
   machine-wide symlink to the newest Nix libc, rewrite ELF interpreters on
   activation, or merge libraries into a shared search directory. A Ports
   glibc import cannot alter System service execution or Base ABI ownership.

3. **Controlled integration, not arbitrary in-process mixing.** Plugins,
   Python native extensions, PAM/NSS modules and graphics drivers are loaded
   into a host process and need a compatible runtime/ABI arrangement.
   Nix-store coexistence alone does not prove that arrangement. Preserve the
   package's declared module environment and audit external module boundaries.
   Sharing an IPC protocol or starting another executable is a separate boundary;
   it still needs protocol/configuration checks, but does not itself link the
   two processes' libc objects into one ELF process.

4. **No global library-path fix.** Mojt profiles do not set a universal
   LD_LIBRARY_PATH or LD_PRELOAD to combine Base/System/Ports libraries.
   Do not add global GCONV_PATH or LOCPATH as a workaround either.
   Necessary application-specific wrappers must declare and retain their exact
   references and be tested; record diagnostic environment overrides separately.
   Existing inherited user settings are not proof of a clean-runtime result.

5. **Locales must match the consumer.** Nixpkgs documents different locale archive
   formats and its LOCALE_ARCHIVE patch. Do not promise that one global archive
   works with every libc object. Keep the tested C.UTF-8 baseline; richer locale
   support needs compatible, closure-owned data and per-application handling
   where necessary. Test both libc families. LANG/LC_* choosing a locale does
   not supply or verify its binary data. Locale/collation changes can also affect
   application data such as database indexes; switching executables is not a
   data-format rollback.

6. **Audit shared identity/configuration services.** /etc/passwd, group, resolver
   and nsswitch configuration are shared state. An NSS module selected there
   can be dynamically loaded into programs using different libc builds.
   Initially verify local files/DNS behavior for each tested runtime, including
   non-root lookup, and do not add a global NSS/PAM module merely because its
   executable works. In particular, an older Base process must not accidentally
   consume a Nix module requiring an incompatible newer libc ABI.

7. **Check the actual host boundary.** Record declared platform, CPU and kernel/
   feature requirements plus verified/incompatible/unknown status. Reject known
   incompatibility without changing another area. Unknown requirements must
   remain visible; an ELF ABI note or a libc version alone is not complete proof.
   How to enforce experimental versus production unknown-capability policy is
   separate work, not an extra approval mechanism added by this proposal.

8. **Security repair follows consumers.** Importing a patched glibc beside an old
   one leaves old consumers on their old runtime. A selected catalog can prefer
   a replacement application build with a different dependency closure even
   when its upstream release is unchanged. Propose that as an artifact/closure
   upgrade for following requests. Keep exact artifact locks unchanged; report
   affected pins and available repair targets without calling them patched.
   System repairs publish a new System generation; Base repairs use a new Base
   release. Dependency reuse never merges those activation scopes.

9. **Retain until all references are released.** Installed artifacts, retained
   deployments and future project locks protect their complete closures.
   A retained old libc still takes disk space and may remain vulnerable.
   GC cannot choose a single newest libc and delete others by name/version.
   Running-process safety and store-root release need a separate GC design;
   a live memory mapping alone is not assumed to be a sufficient store root.

## Worked dependency-only replacement

Illustrative catalog records, not measured glibc versions from the hello test:

| Artifact | Application release | Runtime | Role |
| --- | --- | --- | --- |
| A | hello 2.12.3 | libc object L1 | Retained exact pin or old installed build |
| B | hello 2.12.3 | patched/rebuilt libc object L2 | Explicitly preferred build in a new view |

A and B must have distinct artifact/closure records when their exact runtime
references differ. Approved upgrade may move a following request A -> B without
changing its release selector. An exact request or exact active artifact remains
on A. System's reference to L1 remains until a System operation changes its
own composition. The Nix store can reuse identical dependencies across all of
these consumers without merging their policies.

The owner already tested real hello 2.12.1 -> 2.12.3, exact recovery and VM A/B/A.
Those tests did not capture interpreter/libc identities and do not establish
this same-release/different-libc scenario.

## Evidence required for the next runtime test

- Two real consumers backed by different measured libc objects, with source
  pins, output paths, NAR hashes and complete output closures retained.
- Read-only ELF interpreter/needed-library inspection and trusted-program
  execution under a recorded clean environment; distinguish build metadata
  from the objects actually loaded. Preserve diagnostic loader output.
- Simultaneous availability and execution after following upgrade and exact
  recovery; byte-for-byte identical pinned artifact/reference records.
- Identity/group lookup, DNS/HTTPS, C.UTF-8 and separately provisioned richer
  locales; then an explicit compatible module/plugin integration case.
- A same-release replacement case where closure/artifact changes; if binary
  substitutes do not provide one, record that gap rather than invent a rebuild
  or trigger an unapproved source build.
- The next VM round checks these alongside retained System/Base choices and
  kernel compatibility. Destructive GC and arbitrary plugin mixing are not
  part of this acceptance test.

## Primary sources checked

- [Nix 2.35 output closures and store addressing](https://nix.dev/manual/nix/2.35/glossary).
- [Nixpkgs purity and toolchain](https://nixos.org/manual/nixpkgs/unstable/#chap-stdenv).
- [Nixpkgs locales and LOCALE_ARCHIVE](https://nixos.org/manual/nixpkgs/unstable/#locales).
- [GNU libc dynamic linker hardening](https://sourceware.org/glibc/manual/2.43/html_node/Dynamic-Linker-Hardening.html).
- [GNU libc NSS services](https://sourceware.org/glibc/manual/2.43/html_node/Adding-another-Service-to-NSS.html).
- [GNU libc locale names/data](https://sourceware.org/glibc/manual/2.43/html_node/Locale-Names.html).

Backend behavior supports coexistence; it is not an upstream guarantee of Mojt
host integration. The rules and tests above are Mojt's proposed consequences.
