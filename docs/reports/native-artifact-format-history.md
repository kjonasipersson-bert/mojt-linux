<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native artifact packaging acceptance

Historical test record from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
The fixtures and observations below are not the current command contract.

## Owner native package acceptance: 2026-10-29

The owner exported the already built and boot-tested `6.12.107-mojt1` kernel
inside the Mojt build VM using functional source revision
`ca25807f117afb56ff77ef6b7a63f69a020fa2b3`. No kernel recompilation occurred.
The resulting distribution release is `6.12.107-r1`, with package revision 1
and upstream version `6.12.107`. The actual kernel/module release remains
`6.12.107-mojt1`.

Exact accepted native artifact:

```text
sha256:eed451b5497d078b8de4c098539cf63a4551aa0a46864fe7550b59066fe26250
```

| Check | Observed result |
| --- | --- |
| Mojt packaging | The ready-build adapter produced the package and completed its archive verification. |
| Input preservation | Checksums of the original kernel build record, seed config, config diff and workspace input-inventory record were unchanged. |
| Version identity | Package release `6.12.107-r1` and kernel release `6.12.107-mojt1` remained distinct and explicit. |
| Export | After powering off the build VM, the workspace was read through a read-only mount without journal replay; the package and pinned verifier files were copied out. |
| Verifier provenance | Debian-side SHA256 checks matched all three copied verifier/core files to the pinned functional revision before importing the verifier. |
| Transfer integrity | Archive checksum and byte size matched the exported transport record; the full expected artifact ID matched. |
| Independent verification | The copied verifier streamed and verified the package on Debian without the build environment, original source-tree locations or Nix provider commands. |
| Metadata copies | The embedded descriptor and detached `artifact.json` were byte-identical. |
| Build provenance | The retained build ID matched the original build record; the inventory-bound embedded record hash matched an independently copied original. |

This accepts real native Kernel packaging and portable content verification.
It does not register an installed kernel, publish a catalog entry, validate a
new deployment or change boot selection. Real Base/System/Port exports remain
separate from their successful synthetic format fixtures. Repository trust,
production import/extraction and boot deployment remain separate work. The
first [local Kernel install/status prototype](../mpm-kernel.md) now consumes this
accepted format with a conservative regular-file/directory subset. Another
kernel build or unrelated VM account/generation cycle is not required.

