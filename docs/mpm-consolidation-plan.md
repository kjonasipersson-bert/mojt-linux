<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# MPM integration boundaries

MPM uses the same native content, preparation and selection APIs in the installed
frontend and build/bootstrap tools. The current [roadmap](roadmap.md) tracks
remaining work; this page defines the integration responsibilities.

| Responsibility | Current boundary |
| --- | --- |
| Installed runtime | System delivers a complete management code/helper cohort; publishing repository code does not patch a running installation |
| Sources and acquisition | Explicit local source policy, accepted metadata snapshots and retained native cache; authenticated remote native publication remains separate |
| Area installation | Base/System/Kernel retain exact content and origin; normal live System install includes boot preparation |
| Choices and status | Exact compatible native-v2 deployments, metadata-only activation, distinct running/next/prepared observations |
| Build and bootstrap | MBT coordinates retained tool environments, explicit builds, packaging and fresh-image creation through MPM APIs |
| Persistent state | Independent machine configuration/data, compatible readers/writers and bounded initialization; unsupported migrations refuse |

The ordinary live System flow is install, activate, then deliberate reboot.
Offline/content-only import, Base/Kernel preparation and the advanced stage API
remain explicit. Moving-policy boot-area acquisition, general service/schema
migrations, native Port publication and cleanup require their own supported
contracts. Do not infer those features from a successful exact boot selection.

Complete native source self-hosting requires building Base and Mojt-owned System
components from pinned sources on Mojt. Importing binary closures, assembling an
image and compiling one Kernel are distinct capabilities. New integration work
must preserve exact recovery choices, configuration/data and unrelated pins.

See [management workflow](management-workflow.md), [MPM operations](mpm.md),
[boot updates](system-transition.md), and the [MBT chapter](../doc/handbook/part-i/mbt.md).
