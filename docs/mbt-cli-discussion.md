<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MBT command syntax: discussion before implementation

The owner clarified that the requested syntax discussion concerns **mbt**, the
Mojt Build/Bootstrap Tool. The existing MPM syntax is satisfactory and remains
in place. The earlier spelling `mpt` was not a request to rename MPM or create
an alias. Existing `mojt-*.py` tools are implementation inputs, not a settled
public MBT interface.

The [concrete MBT interface proposal](mbt-interface-proposal.md) now supplies a
four-object command family and worked journey for discussion: `env`, `build`,
`package` and `bootstrap`. MPM syntax and build/package/install/select separation
remain intact. These are not implemented or approved verbs; see
[the first consistency review](distribution-review.md).

The proposed [behavior contract](distribution-contract.md) now specifies MBT's
target/bootstrap, build/environment, packaging, resume and self-hosting behavior
without selecting verb spellings. [D1 and D5](distribution-decisions.md) remain
explicit design gates. MPM acquires/installs content; MBT executes recipes in an
owned workspace and submits results through that same installation path.

| Question | Boundary to decide |
| --- | --- |
| Responsibilities | MPM acquires/verifies/installs/retains content and selects deployments. MBT prepares targets/workspaces and builds/packages using those same libraries |
| Bootstrap targets | Define directory, regular disk-image and explicit physical-disk adapters; distinguish target from minimal/normal/builder/rescue composition profiles |
| Plans and locked inputs | Specify a human-editable plan and a resolved inventory with exact Base/System/Kernel/Ports/source/toolchain references |
| Build environments | Choose create/inspect/run/retain interfaces, workspace ownership and pinning; avoid replacing a globally active compiler |
| Build/package | Keep source compilation, native packaging, installation and next-boot selection separate, even when a higher-level workflow composes them |
| Repeat/resume/failure | Define no-op, incomplete result, explicit resume, output publication and interrupted-build reporting |
| Privileges | Acquire/install as authorized, compile as an ordinary user, and keep formatting/boot mutation at explicit target boundaries |

Do not implement new verbs from these examples without the discussion. MBT
must not grow a competing installer, catalog authority, dependency solver or
selection database. See the [MPM gap matrix](mpm-gap-matrix.md) for implementation
dependencies and acceptance criteria.

