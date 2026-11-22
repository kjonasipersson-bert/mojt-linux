<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Component System acceptance and total command measurement

Use the reviewed checkout as root on native installed Mojt. Running and next boot
must identify the same exact deployment. Keep the current working generation,
Kernel and Base. This procedure creates new packages, generations, prepared
entries and reports; it does not remove recovery content or rebuild the Kernel.

```sh
python3 -I -B tools/mojt-system-components-test.py prepare
```

The helper freezes the complete reviewed resource cohort and its support scripts,
then uses the retained running Python in a fresh isolated process. It builds and
installs component generation A, builds a Runtime successor B from A and installs
B. Both use ordinary automatic boot preparation. Firmware is retained by exact
reference and is not supplied as a new dependency archive.

The installation measurement uses the public MPM frontend with that reviewed
code and normal defaults. The helper separately reports each build, installation
and boot preparation, then reports **WHOLE COMMAND** from script entry, including
code freezing, both builds/installations, startup of the retained child and status
checks. Python interpreter startup before script entry is outside that clock.
Nested phase durations are not added to totals. The first boot payload can need
rebuilding after producer-code changes; the second must reuse the same payload.

Python file-open guards refuse access to retained firmware/license data and
containing archives during both builds and installs. Descriptor/receipt metadata
reads remain allowed. Profile copy counters must remain zero, and firmware
references must be identical. These are in-process boundaries, not a disk trace
of provider subprocesses or a power-loss experiment.

Preparation does not select either generation or reboot. On success:

```sh
python3 -I -B tools/mojt-system-components-test.py activate
reboot
```

After logging in:

```sh
python3 -I -B /root/mbt-prov/tools/mojt-system-components-test.py after
```

Use the actual checkout path if different. This checks the running/selected
component generation, unchanged Base/Kernel/boot policy, MPM status, MBT packaging
help, thin Runtime links and the read-only firmware mount. Persistent account,
layout/Ports selection evidence and a private `/var` marker are checked. Avoid
unrelated state/Ports changes during this bounded test.

Select the original generation and return:

```sh
python3 -I -B /root/mbt-prov/tools/mojt-system-components-test.py back
reboot
```

Then:

```sh
python3 -I -B /root/mbt-prov/tools/mojt-system-components-test.py check-back
```

The test keeps unique protected workspaces under
`/var/lib/mojt/system-components-test/run-*`. `current` identifies the latest
attempt, including an incomplete one; activation requires its completed record.
Failures retain reports and packages. Inspect them before starting a fresh
attempt; no automatic cleanup, resume, selection or reboot occurs.

The acceptance target is structural: one import of each new component, zero
profile payload copies and no firmware data/archive access for the Runtime
update. Initial firmware acquisition still costs its download, extraction and
durability work. Retained recovery generations can continue to consume their old
space; this procedure makes no garbage-collection or physical timing claim.
