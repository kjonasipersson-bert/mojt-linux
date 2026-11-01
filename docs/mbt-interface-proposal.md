<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MBT interface: concrete proposal for discussion

Draft 1, 2026-11-01. Proposed commands, not implemented or approved syntax.
Existing MPM syntax remains unchanged. D1/D5 in the
[decision register](distribution-decisions.md) remain open until interfaces and
formats are settled. The [behavior contract](distribution-contract.md) defines
guarantees; this proposal makes the user journey concrete.

## Command shape

Recommend `mbt <object> <action>`, following MPM's readable shape:

| Object | Meaning | Proposed operations |
| --- | --- | --- |
| `env` | Named pinned build environment; no global compiler selection | `plan`, `create`, `show`, `run` |
| `build` | Owned workspace with frozen recipe/source/config and exact environment | `plan`, `run`, `show`, `resume` |
| `package` | Export/verify complete results as native artifacts | `plan`, `create`, `verify` |
| `bootstrap` | Create a new directory, image or explicitly approved physical installation | `plan`, `create` |

`plan` reads metadata and emits a proposal, optionally on machine-readable
stdout. User redirection does not authorize MBT to create registries, workspaces
or roots. Plans execute no recipe or payload acquisition; missing prerequisite
metadata is reported. Execution revalidates/freezes inputs under the original
approval policy. A preview does not authorize changed scope or baseline.

Environment names live in an explicitly owned registry; build/output paths name
workspaces/results. Names are not content IDs; `show` displays both. Registry
selection, saved-plan approval and machine output flags remain D1 deliverables.

## Worked journey

Illustrative commands, NOT runnable against today's CLI. TOML files are editable
specifications; schemas and resolved records remain D2/D5 work. `kernel.toml`
describes a recipe, not a program run by the planner.

```sh
mbt env plan toolchain.toml
mbt env create toolchain.toml --name kernel-dev
mbt env show kernel-dev

mbt build plan kernel.toml --env kernel-dev --workspace "$HOME/build/linux"
mbt build run kernel.toml --env kernel-dev --workspace "$HOME/build/linux"
mbt build show "$HOME/build/linux"
# After validating unchanged frozen inputs:
mbt build resume "$HOME/build/linux"

mbt package plan "$HOME/build/linux" --revision 1 --output "$HOME/packages/kernel"
mbt package create "$HOME/build/linux" --revision 1 --output "$HOME/packages/kernel"
mbt package verify "$HOME/packages/kernel/EXACT-ARCHIVE.tar.zst"

mbt bootstrap plan machine.toml --target image --output "$HOME/images/mojt"
mbt bootstrap create machine.toml --target image --output "$HOME/images/mojt"
```

Normal MPM Kernel install/stage/select consumes the verified result. Build and
package commands never install on the running machine, select next boot or
publish a repository entry. Results report full ID, archive path/digest and
provenance; callers do not guess filenames. MBT adds no install/select command.

`mbt env run kernel-dev -- COMMAND ...` explicitly runs an exploratory command
without changing the interactive shell globally. It grants neither recorded
build provenance nor completion status and is not a sandbox claim. Traceable
builds use the frozen recipe/workspace path above.

## Targets, profiles and delivery

Propose `--target directory|image|disk`. Directory/image take an output path;
physical disk instead requires stable `--device` identity with its own preflight
and approval. Physical support is a separate implementation/acceptance gate.
Never infer a device from enumeration order. `create` is not an updater or an
implicit permission to format an existing installation.

Minimal/normal/builder/recovery are composition profiles, not target kinds.
`machine.toml` selects content, hardware/console and initialization policy.
All use MPM installation/deployment libraries; target creation cannot bypass
their checks.

Recommended first delivery: MBT and pinned Python/dependencies in an optional
builder System composition using the existing assembly route. Ordinary machines
need MPM but need not carry all builder tools. This avoids making a generic
native Ports backend a prerequisite for M1. MBT retains exact runtime/helper
references; no imports from a mutable PATH. Build tools remain in private envs.

## Input/output and execution

An editable specification contains wishes. A resolved execution record binds
exact sources/artifacts, recipe/config, environment, target identity and allowed
effects. A receipt records actual evidence/results. These are distinct versioned
objects; a receipt cannot retroactively authorize execution.

| Operation | Required outcome |
| --- | --- |
| Environment create | MPM acquisition/retention of exact tools, private pin, unchanged global selections; same name/different content is a conflict |
| Build run | Frozen inputs, ordinary-user execution in a new owned workspace, retained source/tool evidence; existing output is not overwritten |
| Build resume | Check exact recipe/source/config/environment/ownership; follow recipe resume protocol; changed inputs need a new workspace/plan |
| Package create | Verify complete output, preserve original build identity, apply explicit packaging revision and verify archive |
| Bootstrap create | Freeze composition/target, use shared MPM install/deploy, initialize only new target, publish complete validated image |

Environment creation may need authorized shared import before returning control
to its ordinary owner. Do not run the entire build as root to make imports work.
Target provisioning has a separate checked privileged boundary. Secrets belong
in neither arguments nor plans/logs.

Human output explains scope, prerequisites, progress, exact result and next step.
Machine output should distinguish success/no-op/blocked/failed/publication-
uncertain through a versioned envelope. Exact MBT flags, exit codes and envelope
must be specified before implementation; existing MPM conventions do not change.
No destructive cleanup/prune command is proposed for M1.

## Recommendation awaiting discussion

Adopt four objects, `build run` for compilation, explicit `build resume` and
`bootstrap create` for new targets. Preserve build/package/install/select
separation. Deliver MBT in an optional builder System composition, with private
per-build tools.

Still decide saved-plan/lockfile schemas/options, registry selection, machine
envelope/exit classes and recipe/composition schemas. This proposal does not
authorize implementing new verbs before discussion. See
[the review record](distribution-review.md).
