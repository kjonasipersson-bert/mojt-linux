<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Normal-operation structural and physical acceptance

Use a reviewed checkout as root on a native installed target. Keep the current
working generation and its recovery content. Running and next boot must agree.
The existing component helper builds two new Runtime generations with the current
firmware reference and installs/prepares them without selecting either:

```sh
python3 -I -B tools/mojt-system-components-test.py prepare
```

Read both `BUILD` / `INSTALL + PREPARE` lines and the final `WHOLE COMMAND` line.
The first run may construct a new heavy payload because producer code changed.
The second must reuse it. The first run can also populate retained interpreter
metadata. Neither report is a claim that interpreter or Kernel startup time has
been measured. Full status is not used to obtain the helper's identity snapshots.

After successful preparation, select and reboot once:

```sh
python3 -I -B tools/mojt-system-components-test.py activate
reboot
```

After logging in, use the actual checkout path:

```sh
python3 -I -B /root/mbt-prov/tools/mojt-system-components-test.py after
cat /run/mojt/boot-checks.json
```

The boot record must identify the chosen deployment and normal mode with
`content_verified=false`. `reader_ms` and `state_gates_ms` measure the early
metadata/current-state work, excluding Kernel startup and mount/exec work.
The helper checks current state and management availability. The new generation
can remain running and selected after this check.

A return boot is optional for a timing-only run. Use the helper's `back`, reboot
and `check-back` actions when testing reader/storage compatibility or when an
explicit return is wanted. This change retains the existing serialized formats;
regressions still exercise selection and recovery boundaries.

## Automated structural checks

`tests/test_system_normal_operation.py` uses retained native packages and a
simulated initramfs producer. It asserts:

- Boot reads only the chosen System and its exact dependencies, independently of
  unrelated installed generations; global history readers are forbidden.
- Preparation checks the link set once and does not replay standalone input
  acceptance inside the checked transaction.
- Reading the selected entry does not require decoding an unrelated damaged
  admission receipt; explicit complete inspection still detects that damage.
- Plain status does not reconstruct realizations or handover readiness.
- An accepted retained interpreter descriptor avoids a fresh runtime snapshot.
- Full handover checks in the isolated reader do not invoke original archive
  codecs; early content audits use the bound tree proof.
- Private runtime copies check source bytes without durability flushes or an
  independent readback; full producer verification retains that comparison.

The existing transaction, component, reader, archive and QEMU cases retain
unsafe-path, state/selection race, publication uncertainty, explicit damage audit,
read-only mount and return tests. A structural fixture is not a physical boot or
cold-start timing result.
