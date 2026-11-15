<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MPM usability I/J hardware acceptance

Start as root on the accepted SSD with writable-root **G or H running and
selected**, and keep `/var/lib/mojt/writable-root-60/state.json`. This test
retains Base, Kernel, firmware, provider/startup policy, persistent data and the
original recovery entries. It does not format a disk or reboot automatically.
No physical acceptance is claimed until the owner completes these steps.

Use the exact reviewed delivery's **`tools/mojt-usability-test.py`**, retaining
that filename. Copy it by USB to **`/root/mojt-usability-test.py`**. Its functional
inputs are pinned to `969a747a5fd550c44098298fcc3b626d93aee799`, with 17 file
checksums and a checksum of the earlier native package/evidence driver. This is
reviewed maintenance delivery, not a signed release.

## 1. Enter the new manager

```sh
python3 /root/mojt-usability-test.py prepare
python3 /root/mojt-usability-test.py enter
```

Confirm with `y`. `prepare` downloads checked inputs, copies a complete compatible
code cohort and packages I/J. It adds the owned `man`/`manpath` wrappers while
preserving their retained provider targets. Native packages are verified without
changing running or next boot. `enter` installs I through the old public manager,
prepares I with its checked complete installed code in a fresh isolated process,
and selects I. No running manager files are patched. Bootstrap preparation can
still take time; this is not another performance benchmark.

On `READY: I selected`, reboot deliberately, then:

```sh
python3 /root/mojt-usability-test.py check
python3 /root/mojt-usability-test.py install
```

`check` shows readable System/Base/Kernel status. `install` installs J with the
new **normal System installation**, including boot preparation. No separate
stage command is issued. Expect phase starts/completions followed by `PASS`:
**Running I, Next boot I, Prepared J**. Base and Kernel must be unchanged.

## 2. Complete and read existing Ports manuals

```sh
python3 /root/mojt-usability-test.py manuals
man git
man neovim
man nvim
man ncdu
```

The helper repeats existing interactive pinned-provider wishes for whichever of
neovim/git/ncdu/mdbook are active. It checks that exact binaries, version wishes,
installation/activation order and active choices remain unchanged. It locates
and renders available probe manuals through the public wrapper without a new
login. Confirm that normal paging works; press `q` to leave a manual.
`mdbook` may supply only help/HTML, so absence of `mdbook(1)` is not a failure.
Missing binary/manual substitutes must fail without changing the Ports profile.

## 3. Exercise the real chooser and reboot

First inspect and cancel the public chooser:

```sh
mpm system activate
```

Enter `q`. This intentionally returns a cancellation error. Then inspect:

```sh
mpm system status
python3 /root/mojt-usability-test.py choose
```

Choose **system-ux-J** by its listed number. Before confirming, expect concrete
old/new System names and short IDs, unchanged Base/Kernel and a reboot-required
message. Confirm with `y`. The helper checks the exact J deployment was selected.
Expect **Running I, Next boot J**. Reboot deliberately, then:

```sh
python3 /root/mojt-usability-test.py check
```

Expect `PASS`: **Running J, Next boot J**, no pending reboot, preserved writable
root/local mounts and working manuals after reboot. Keep a screenshot of the
status/preview and note any confusing messages or failed manual queries.

Evidence is stored under `/var/lib/mojt/usability-61`. On failure, stop and retain
that directory; do not remove checkpoints, force preparation or replace an
installed manager. The old G/H and earlier F recovery entries are retained.
An older System's original man wrapper will not gain the new search behavior,
although the added documentation and Ports state remain retained.
