<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Working on Mojt Linux

Speak Swedish with the project owner unless asked otherwise. Write code,
documentation, comments and commit messages in English. Mojt-owned files use
`Copyright (C) 2026 Jonas Persson` and `SPDX-License-Identifier: GPL-2.0-only`;
preserve upstream licenses.

## Engineering principles

- Preserve the independent Base, System, Kernel upgrade scope, Ports and
  persistent-state lifecycles. Base is a whole versioned userspace release.
- Prefer existing Unix mechanisms and tools, small changes and explicit effects.
  Installing, preparing a boot entry, selecting next boot and running code are
  distinct states; reflect the implemented command flow accurately.
- Read the current source and relevant tests before changing behavior. Repository
  source is authoritative; `MOJT_HANDOFF.md` is historical context.
- Preserve existing releases and persistent configuration/data. Never silently
  overwrite local configuration, migrate schemas, remove recovery content or
  change unrelated active selections.
- Validate archive paths and symlinks. SHA256 provides integrity, not publisher
  authentication. Keep build/bootstrap providers separate from Mojt's model.
- Run checks appropriate to the change. Distinguish local, CI, VM and physical
  machine results; never claim to have run commands on the owner's machine.

## Documentation is a current interface contract

- The Handbook, README, architecture and operational/reference documentation
  describe how the code works **at the same commit**. Write for a reader with no
  access to project conversations or private test machines.
- Document commands, preconditions, effects, persistent state, compatibility and
  concrete implemented limits. Clearly label proposed behavior as a proposal;
  keep future priorities in the roadmap rather than presenting them as commands.
- Do not put conversation summaries, owner/agent commentary, PR/merge narratives,
  PASS announcements, stopwatch results, private machine paths or unexplained
  test-generation labels into current user/reference documentation. Explain a
  necessary compatibility distinction in terms of supported behavior or formats.
- Keep test procedures, dated observations, logs, measured performance and
  acceptance evidence in clearly identified test reports. Put extracted/new
  historical reports under `docs/reports/`; existing dedicated test/acceptance
  guides can remain at their documented paths. Explain their fixtures, revision,
  environment and limits. A report is evidence, not the product contract.
- A test result alone does not require editing the Handbook. Update the behavior
  description when the interface or its verified limits actually change.
- When moving historical material, preserve useful evidence and fix relative
  links and fragment targets. Do not leave superseded "next" or "not implemented"
  statements as descriptions of current code.
- Review nearby documentation when changing a command or format. Prefer one
  authoritative explanation with links over multiple conflicting status summaries.
