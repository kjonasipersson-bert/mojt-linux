<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MPM and MBT: the user's model

Review proposal, 2026-11-06. This guide brings existing decisions together and
links the remaining interface decisions. It does not add commands to the runtime.
In particular, [Base install/status](mpm-base-contract.md) were agreed on 2026-11-06,
and [MBT spellings](mbt-interface-proposal.md) remain a discussion proposal.

## Two tools, one installation model

**MPM manages the content and choices of an installation. MBT creates build
results and new installation targets using MPM's rules.** Neither tool needs
the user to understand which provider supplies a package to understand an action.
Exact providers, dependencies and trust are visible in inspection and previews.

| User's question | Responsible tool and operation | Result |
| --- | --- | --- |
| What is available? | MPM search/show/versions | Local accepted catalog information |
| Can I refresh that information? | MPM source/area metadata update | Accepted metadata; existing package choices stay put |
| Can I have this release available here? | MPM install | Verified retained content; a Base also has a validated runtime tree |
| What do I have, and what will be used? | MPM status | Separate installed, next-boot/active and running identities |
| Can I use different installed boot content? | MPM deployment preparation and selection | A complete compatible next-boot choice; the running system keeps running |
| Can my tracked packages advance? | MPM upgrade | Only the requested policies/area advance after approval |
| Can I obtain a pinned build environment? | MBT environment creation using MPM acquisition/retention | A private exact tool set; no global compiler change |
| Can I compile this source? | MBT build | Build output and evidence in an owned workspace |
| Can I distribute that result? | MBT package | A verified native package; no installation or publication to a repository |
| Can I create a new machine/image? | MBT bootstrap using MPM install/deploy | A new target, explicitly initialized for its chosen profile |

This is a responsibility map, not a command-availability table. In particular,
current source update and finite Ports metadata inputs are two implemented paths,
not yet one configured-catalog frontend. See [current MPM support](mpm.md#6-implementation-status).

## Four words that must keep their meaning

**Available** means an accepted catalog offers exact content. **Cached** means
verified transport bytes have been retained. **Installed** means an area's
verified content is retained in its supported local representation. **Selected**
means a profile or the next boot will use an exact installed choice.
Running content is a fifth observation: it can differ from the selected content.

For Base, installation includes the validated rootfs realization; merely caching
its nested archive is insufficient. Kernel installation retains matching modules.
System installation will produce one coherent immutable userspace generation.
The same `install` verb keeps these units available without changing the running
machine. The established Ports convenience remains explicit: the first direct
application install may also establish its default, and the preview says so.
Later installs preserve the existing default.

One boot choice binds a compatible Base, System and Kernel plus its boot files.
Choosing a Base is not independently flipping `base/current` beneath the running
machine. Status shows the complete deployment behind each component choice.
Installed content does not itself become a moving upgrade request.

## A predictable journey

On an existing machine, inspect local metadata, preview an installation, retain
the exact content, and inspect status. For a boot change, prepare and verify the
complete candidate deployment, inspect its differences, then select it for the
next boot. Restart deliberately. Inspect the exact running result afterward.
Retained previous content remains available for compatible recovery.

For a source build, obtain a private pinned environment, plan/build in a workspace,
package the completed result, then use the same normal MPM install/deploy path.
Building and packaging do not install the result. Acquisition does not silently
compile a missing binary or move another package selection.

For a new installation, MBT adds explicit target creation, formatting where
appropriate, composition and initial machine-state policy. It calls those same
MPM functions; it does not maintain another package database or updater.
An existing machine update is never implemented as replacing it with a fresh
bootstrap image. `/etc`, `/var`, `/home` and `/root` retain machine state.

## Readable output and deliberate effects

Human output leads with the outcome and next useful action. It shows meaningful
release labels beside artifact identities, so matching labels cannot conceal
different builds. Complete IDs remain available in inspection/machine output.
Users do not need to copy hashes between ordinary named operations; explicit
hash arguments remain useful for local-file import and reproducible automation.
Name resolution must still disclose exactly which snapshot/build was chosen.

Every preview states the target, scope, exact content, required downloads and
storage when known, state effects, selection effects and restart implications.
Unknown prerequisites/sizes are visible. A preview cannot be mistaken for a
completed import, integrity scrub or permission to execute a changed plan.
`-y` accepts the displayed scope; it never disables checks or broadens that scope.

Status is read-only. Missing state is not created, damaged/unsupported state is
not silently treated as an empty installation, and a missing running record is
reported as unknown. Read-only inspection works without a provider, network
refresh, source checkout or writable registry.

Preparation, selection and lifecycle readiness are distinct results. A selected
deployment is not automatically a successfully booted or initialized one.
Failures explain what was published, what remains incomplete and which previous
choice remains intact. Booting older code does not undo changed persistent data.

## Review and implementation boundary

The [Base command contract](mpm-base-contract.md) was agreed on 2026-11-06.
The [first implementation](base-installation.md) merged in PR #40.
[Base staging/selection/return](base-boot-staging.md) is implemented in draft PR #41,
with [owner boot acceptance](base-boot-acceptance.md) pending. MBT reuses the agreed meanings
regardless of its final spelling.
Detailed behavior remains in the [distribution contract](distribution-contract.md),
open choices in the [decision register](distribution-decisions.md), and delivery
order in the [six-step plan](mpm-consolidation-plan.md). This workflow does not authorize unknown schema adoption, automatic cleanup
or an additional component cross-product VM matrix.
