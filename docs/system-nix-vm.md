<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# System assembly from pinned binary inputs

The System assembly tools obtain binaries from an explicitly pinned Nixpkgs
source and compose an immutable System profile separately from Base. System
owns systemd, runtime dependencies, networking, accounts, administration and MPM;
Base remains a small userspace release without an init or Python requirement.

The step-based export/assembly interface is a construction interface. Later
steps add tools/services cumulatively; selecting an earlier step constructs a
smaller profile rather than upgrading the running machine. See `--help` for
`tools/mojt-system-prepare.py` and `tools/mojt-vm-build.py` for their input/options.

## Inputs, outputs and mutation scope

- Export uses a pinned source and records exact output/closure inventories.
  Binary substitutes are explicit inputs, not a general source rebuild.
- Assembly checks the exported inventory and builds a System profile with unit
  files, management tools, defaults and a manifest. Existing Base releases and
  the source machine's persistent state are not modified.
- Fresh VM/image construction copies the supplied machine state and stages the
  chosen System, Kernel/modules and boot inputs. New output publication is
  separate from selecting next boot on an existing installation.
- Native System packaging produces a generation and exact components. The
  running MPM installs them through the [System package path](system-packaging.md)
  and the [boot-update workflow](system-transition.md).

The current interactive shell, diagnostics, console/time, manuals and account
contracts are in [Bash](system-bash.md), [diagnostics](system-diagnostics.md),
[console/time](system-console-time.md), [environment/manuals](system-environment.md)
and [accounts](system-accounts.md). The
[Handbook](../doc/handbook/README.md) describes normal administration.

Nix is the current System/Ports binary provider, not a required backend for the
Mojt artifact model. Base/System releases combine within actual ABI, Kernel and
state requirements. Full source self-hosting, broad service migration and signed
native distribution remain separate work.
