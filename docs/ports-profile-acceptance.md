<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Fresh Ports / real Nix adapter acceptance

Owner-reported PASS on 2026-11-01 for code revision
`40ee0f2323c92d08cb4c4ff85b84571f9ff1a237` in PR #36.
The owner executed the real container test; this record does not claim execution
on the assistant's host.

Environment: ordinary user UID 1000 in the existing Debian Distrobox
`mojt-mpm-nix`, on the Debian host. The accepted source bundle had already been
exported from pinned, local Nix outputs.

| Evidence | Result |
| --- | --- |
| Fresh-root install preview | No registry or profile created |
| Actual binary adapter import/verification | Completed and published an exact package |
| Default, requested series and full-reference aliases | Executed hello successfully |
| Stable provider retention | Exact output's Nix GC root registered |
| Repeat installation | Same profile pointer, byte-identical state and unchanged history |

The runner's final PASS entails all of its preceding assertions completing.
The owner supplied the final registered-root, unchanged-repeat and complete
acceptance PASS lines.

Retained lab: `/home/jonasp/mojt-lab/mpm-nix-home/mojt-ports-profile.s0G1Yf`.
Successful invocation used `registry-helper-fixed` within that lab, with
`sources.json` and `tests/run-mpm-ports-profile.py` from the pinned revision.
Earlier failed registries were retained, not reset or adopted.

Focused CI for the exact code revision also passed:
[run 41342718630](https://github.com/kjonasipersson-bert/mojt-linux/actions/runs/41342718630).

This accepts the real adapter/frontend integration for this finite catalog and
existing-output lab. It does not establish a new network payload download,
changed-artifact upgrade in this fresh flow, signature-authenticated remote
catalog acquisition, VM/hardware acceptance or general libc ABI compatibility.
Native Port archives, imperative reason/version removal/reset, lifecycle/recovery
and the remaining [six-step milestones](mpm-consolidation-plan.md) remain work.
