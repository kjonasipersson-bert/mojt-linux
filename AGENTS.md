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
- Use standard tools through their upstream commands, configuration files and
  conventional service names. Do not add Mojt-specific management wrappers around
  tools such as OpenSSH. Bootstrap/test setup scripts may write ordinary config.
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

## Normal operation boundaries

- Keep the normal command path a small, explicit transaction. State which checks
  belong to input acceptance, locked preparation and final publication.
- Pass checked immutable inputs through the operation. Do not reconstruct the
  entire plan at every internal layer. Independently supplied saved plans still
  need validation at their entry boundary; never treat JSON as write authority.
- Recheck mutable state and selection at publication boundaries. Keep expensive
  full-content audits explicit (`--verify`); normal mode still validates incoming
  archives, paths, dependencies, compatibility and transaction results.
- Keep profiling, fixture comparisons and acceptance orchestration in diagnostic
  tools/tests. Product code should enforce supported contracts and report errors,
  rather than reproduce a development test sequence.

## Bulk I/O and durability

- Distinguish disposable scratch copies from content that must survive a crash.
  Identify the final durable representation and commit/publication point before
  adding `fsync` to a bulk file loop; document why each flush is required.
- Prefer promoting already synced private trees on the same filesystem over
  copying and syncing the same bytes again. Sync changed parent directories;
  retain a durable copy fallback for cross-filesystem workspaces.
- Preserve archive validation, required file/metadata durability, locking, atomic
  publication and post-publication uncertainty. Do not disable syncs globally,
  assume directory sync flushes file data, or share mutable release inodes.
- Test with many small files as well as large content. Measure copy bytes,
  file/directory sync counts and complete operation time, and report nested
  timings without double counting. Include interruption/retry and fallback tests.

## Installer development

- Use the [installation guide](docs/mounted-installation.md) for media builds
  and mounted bootstrap. The [installer acceptance report](docs/reports/installer-test.md)
  describes the offline two-disk VM procedure and physical coverage.
- Exercise partitioning on a new disposable virtual disk. Keep the installer
  image separate and disconnect it before testing the target's first boot.
  Physical disk erasure requires explicit authorization for the identified disk.

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
