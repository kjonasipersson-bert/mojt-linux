<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Source Base producer verification

Date: 2026-11-23. This is development evidence for the standalone
[source producer](../base-source-build.md), not a boot acceptance or a published
Base release announcement. The existing Void-backed Base remains a separate
retained input.

## Environment and build

The local executor used x86-64 Linux, GCC 14.2.0-19, GNU Make 4.4.1 and eight
make jobs. Source archives were fetched and checksum checked separately; the
complete build then ran offline from that cache as an ordinary user. Its source
set is recorded in `bootstrap/base-sources.json`: thirteen userspace projects
and build-only Linux 6.18.63 UAPI headers. The glibc runtime was built directly
from GNU 2.44, independently of the existing Nix glibc 2.44-57 build.

The complete integration run compiled all projects and produced a private
`0.2.0` release. Recorded build/install/pack phases totalled 340.74 seconds;
that sum excludes downloads, unpacking and final inspection. Its compressed
rootfs was approximately 9.05 MiB. The output inspection covered 422 ELF files,
script interpreter syntax, local library resolution and build/store path leaks.

The driver supplies the bootstrap compiler's `libgcc_s` explicitly because
glibc can load its unwinder dynamically. Provenance distinguishes source and
installed runtime hashes. GPLv3/Runtime Library Exception handling, nested
upstream license paths, output protection, cache corruption, archive traversal,
failed-input publication and root-owned unprivileged packaging have regression
coverage. The committed driver also pins GMP's C99 configure mode for compilers
whose default changed to C23; the local integration compiler used pre-C23 rules.

## Runtime and packaging observations

The packaged rootfs was extracted into a disposable directory and run with
`unshare --user --map-root-user chroot`. The following checks succeeded:

- `getconf GNU_LIBC_VERSION`: glibc 2.44.
- UTF-8 locale selection/charmap, root account and localhost lookup.
- Base dash, PCRE grep, sort and a gzip round trip.
- GNU tar advertises ACL support.
- `ldd /usr/bin/ls` resolves Base libcap/libc through the standard loader paths.

Native Base archive construction and MPM import/realization also succeeded in
an isolated directory. The test filesystem emitted unsupported ACL-operation
warnings during that import; this does not establish real ACL preservation.

The focused producer and existing metadata/diagnostic suite passed 27 local
tests. The format checker accepted eight schemas/six linked examples and
rejected 29 invalid cases. `git diff --check` passed. The source-build workflow
builds and exercises the committed revision independently; its result is the
corresponding CI check, not inferred from this local report.

## Limits and next acceptance

No VM or physical machine was booted with this Base, and no running installation
or next-boot choice was changed. This does not establish PAM/SSH, external DNS,
Ports, persisted-state integration, full locale coverage, reproducibility,
security maintenance or source self-hosting of the compiler runtime. A retained
System/Kernel boot test and comparison of writable-root projections remain
required before replacing an existing machine's Base.
