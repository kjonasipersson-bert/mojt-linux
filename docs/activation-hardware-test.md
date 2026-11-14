<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Focused PR #54 hardware test

**Historical delivery:** this script pins the original #54 functional revision.
It installs the earlier combined preparation/activation implementation, not the
replacement described in [activation performance](activation-performance.md).
Keep existing checkpoints/evidence; do not use this delivery to measure the new
fast activation or optional installation verification paths. Use the separate [C/D successor test](activation-fast-hardware-test.md) for that
physical acceptance.

Run only after this PR's current-head CI is green. Keep the existing SSD
installation, Base and Kernel. Boot the accepted `system-ports-fix-1`, with no
pending next-boot choice. The test refuses an installer/other starting label.
Do not rebuild an image or repeat the full hardware matrix.

## Delivery and preparation

Copy `tools/mojt-system-activation-test.py` from the reviewed PR head to
`/root/activation-test.py` on the installed Mojt, as with the previous small
USB-delivered update script. Alternatively download the script by the exact
reviewed commit URL; do not use a moving branch URL for the test delivery.
Run as root with the installed Python. No Git/compiler is needed on Mojt.

```sh
python3 /root/activation-test.py prepare
python3 /root/activation-test.py status
python3 /root/activation-test.py install
```

Preparation downloads three bounded, hash-pinned tooling/manual files from
`cecbb47f4eaa6a3485249ecc0ee5bf036911f5cd` (the original #54 functional head).
The reviewed script is the trust anchor; these are not signed release packages.
It uses the same native packaging method as the accepted Ports bridge to make
A and B from the installed component, without copying/rebuilding provider
closures. Provider dependencies, state schemas and service declarations stay
unchanged; the startup tooling review must pass. A and B have different labels,
package revisions and exact IDs. `status` records both IDs and versions.

`install` confirms installation of both generations through the running old MPM.
It leaves next boot unchanged. Nothing overwrites the running System profile.
The workspace and evidence are `/var/lib/mojt/activation-test-54` on the SSD.
Existing checkpoints/packages/logs are retained; do not delete them to bypass a
failed guard. Inspect `status` and the failure first.

## Enter the new manager

```sh
python3 /root/activation-test.py activate
```

Confirm selecting **A** for next boot. This first activation uses the old running
manager and is **not** the new performance measurement. Reboot deliberately, then
check `mpm system status`. It should show `system-activation-A` running and
selected. The script does not reboot at any stage.

## Cancellation and measured activation

Use a real terminal, with the same Python script still on the SSD:

```sh
python3 /root/activation-test.py cancel
python3 /root/activation-test.py test
```

During `cancel`, enter an invalid candidate number, then `q`. Expect the chooser
to reprompt, then cancellation. The wrapper checks that selected and running
System identity are unchanged, and preserves the output in `cancel.log`.

During `test`, choose **B using the exact version/ID printed by the wrapper**.
The chooser's release list includes older installed generations too; do not
assume a fixed list number or that B is automatically latest. Confirm NEXT boot.
The wrapper verifies that A's running tools match the pinned new files, preserves
stdin as a terminal, and relays/logs all output to `test.log`. It checks successful
selection of B, unchanged running System, and the exact baseline Base/Kernel,
platform, firmware, state requirements and boot policy.

Expect timings for candidate checks, deployment preparation and final selection
verification/publication. Preparation includes a second candidate check, so do
not add all printed times as independent phases. The wrapper's overall elapsed
time includes time spent answering prompts. The old 5–10 minute report was an
estimate, not a controlled comparison; do not infer a whole-update speedup from
this single sample. The controlled code change removes one full selection audit.

## Boot acceptance and retained return path

After successful selection, reboot deliberately into B, then:

```sh
python3 /root/activation-test.py after
```

Expect `system-activation-B` running and selected, exact original Base/Kernel and
boot policy, a readable Ports list and successful
`/var/lib/mojt/ports/current/bin/nvim --version`. It saves System status to
`after.json`. The test does not install or upgrade any Ports package.

A remains the previous deployment. If a return to A is needed, inspect
`mpm system status --json`, then preview using B's exact selected deployment ID:

```sh
mpm system rollback --expected-selected sha256:B_DEPLOYMENT --dry-run
mpm system rollback --expected-selected sha256:B_DEPLOYMENT
```

Inspect the preview/confirmation, then reboot deliberately if returning.
This is optional recovery, not an additional required boot matrix. An interrupted
or refused operation should be inspected before repeating; the script never
silently resets next boot or replaces retained content.

Return `cancel.log`, `test.log`, `after.json`, and any error text. These contain
local paths and exact installation identities; inspect before sharing publicly.
No physical result is claimed by the automated archive tests.
