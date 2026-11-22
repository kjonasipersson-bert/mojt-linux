<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# System profile placement: many-file diagnostic

## Scope and implementation

Native System installation unpacks exact inputs, builds a private profile,
retains immutable objects and publishes a realization under the existing locks.
The previous final-profile placement copied all files and synced them again.
Same-filesystem placement now moves the already synced private profile into the
unpublished realization stage and syncs both parents. A different-filesystem
workspace keeps the durable copy path. Required content, compatibility and
publication checks remain; `--verify` still audits the final profile.

This diagnostic isolates one profile materialization. It does not measure
unpacking, retained-object placement, initramfs construction or provider queries.
Use the [combined install diagnostic](system-install-profile.md) to measure those
phases and the complete command. Existing releases and persistent state are unchanged. Failure before
publication can leave retained inputs for retry; post-publication uncertainty
continues to preserve potentially committed content.

## Short target-side test

Use the reviewed checkout as root, with the system idle enough for an I/O sample:

```sh
python3 -I -B tests/benchmark-system-profile.py
```

The default input has 2,000 small 4 KiB files, two 16 MiB files and a symlink. The
helper imports the reviewed checkout implementation and creates/syncs these
synthetic inputs outside placement timings. It
then runs the actual durable-copy fallback followed by actual same-filesystem
placement, with in-process timing/call observers. EXDEV is injected only for the
copy case, to select the existing copy path on the same disk. It does not change
manager files or construct/install/select a System. No reboot is needed.

The default workspace is `/var/lib/mojt/system-profile-benchmark`; `--workspace`
can select another protected directory. Each invocation has a private new run
directory. Synthetic trees are removed on success or failure; successful runs
retain counts, source checksum, device, timing and scope in `result.json`. No existing directory
is cleaned or overwritten. Peak synthetic file content is about 80 MiB by default.

Inspect the final copy/move rows and PASS result. The copy row should report
2,002 file copies and file syncs; same-filesystem placement should report zero
file copies/syncs and two directory syncs. The helper checks complete contents,
modes, links, inode preservation and absence of hardlink sharing. This is not a
full install, boot acceptance test, cold-cache benchmark or an installation-time
speedup claim. The copy runs first; cache effects and concurrent filesystem work
affect timings. Do not add fsync time to wall time: it is included.

For more small files without more large content:

```sh
python3 -I -B tests/benchmark-system-profile.py --files 10000 --large-files 0
```

## Local observations and regression coverage

In a local Linux development environment on 2026-11-22, the default diagnostic
matched the expected counts: 2,002 copies/file syncs for the copy path and zero
copies/file syncs plus two directory syncs for promotion. These are synthetic
observations, not results from a physical Mojt installation. Local timings do not
represent target SSD throughput.

Focused regressions cover preserved inode/modes/symlinks, real and injected
cross-filesystem fallback, non-EXDEV failure, existing-target refusal, failure
after the move but before publication and explicit retry. Existing System tests
cover final `--verify` damage detection and preservation of a complete
realization after a publication-directory flush failure. No durability flush is
removed from a file that still needs to be written.
