<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native-v2 preparation review, 2026-11-09

The reviewed path is `prepare-system-boot.py` → the shared fresh-image preparer
→ `mojt-native-image.py` → isolated offline A/B construction → launcher
publication → one installed-MPM A/B/A VM journey. This review starts from the
original Base release, exact Kernel archive and System provider export. Failed
images and their checkpoints are not inputs.

## Findings and changes

| Boundary | Finding | Result |
| --- | --- | --- |
| Owner command | The last supplied command selected the older `mpm-system-test/system-step10`, although the earlier successful assembly used `mojt-base-deployment.k3eJaO/system-step10`. The older export predates the `tar` role. | Restore the documented current export and use one Bash argument array for check and build. No automatic fallback or descriptor edits. |
| Input diagnostics | A closed role-set failure did not identify the payload or missing roles. | Report the full `system.json` path and missing/unexpected role names before store scanning. |
| Preflight | Base/Kernel verification previously occurred after the test output and registry had been created. There was no read-only public entry point for the whole input set. | `--check-inputs` checks source/host requirements, original Base hash, exact Kernel archive, the System closure, tar and fresh output/path destinations. It does not create a test directory, change a start pointer, import or invoke sudo. |
| Attempt lifecycle | A separate resume path complicated the proof of what code and state an image contained. | Remove resume. Every build starts at a new output and verifies the original inputs again. Successful runtime acceptance still uses its one persistent disk. |
| Creation modes | Fresh image and System assembly scope public defaults, but the offline helper still depended on sudo's host umask policy. | The disposable helper explicitly uses 022; private workspaces and credentials retain explicit private modes. Imported content is not chmodded to bypass verification. |
| Construction and publication | Base install, two System package installs, trusted-runtime freeze, preflight, handover and measured initramfs construction are separate gates. The v2 menu is initialized only after both stage admissions; READY follows namespace cleanup. | Preserve this ordering, exact identities and the strict no-publication-on-failure rule. |
| Host resources | Root-only GPT mapping checks geometry/UUID. PID namespace teardown contains helpers; mount cleanup precedes bounded detach of only the owned loop. | Preserve these controls. No host-wide kill, guessed device, force/lazy unmount or recursive deletion through a mount. |
| Launch and boot | The outer launcher adds only the new read-only acceptance disk. Its base image path is the final renamed image; the old direct-boot bypass is removed. Early verification precedes mounts and `switch_root`; the static exitrd owns final unmount. | Keep one native-v2 boot authority and one A/B/A owner test. No prior VM disk is attached. |

## Validation and limits

One joined preflight regression uses real Base/Kernel packages and a complete
synthetic step-10 export through the public parser. It checks that output,
registry and existing path pointer remain unchanged and no build/sudo callback
runs. Host command/firmware discovery is injected in this test; it is not Debian
or QEMU acceptance. A second case uses an older-role metadata fixture and checks
the precise error before any store scan. Existing namespace, package, isolated
reader and publication checks cover their own boundaries.

The first scale regression exceeded 4096 entries but did not exceed the combined
16 MiB proof budget. Owner construction then passed preflight and handover but
failed on that aggregate size limit. The corrected proof format is v2: compact
streamed measurements include all former file/metadata integrity facts while
retaining the 16 MiB record limit. The replacement scale case has 4097 real
modules and 27000 files across nine synthetic provider trees, explicitly checks
that the old maps exceed the real size limit, and verifies that the compact
proof stays below 64 KiB and refuses changed content. Root CI also runs the
bundled reader in an independently extracted initramfs. These checks do not
execute the owner's complete Nix-backed
preparation or firmware/PID1/shutdown journey. That integration remains pending.

The next owner action is **only the read-only input check** in
[system-boot-acceptance.md](system-boot-acceptance.md). A successful report confirms
which original inputs will be used; it is not a boot-ready claim. Only afterward
should the same argument array build a new image. No old attempt is salvaged.
