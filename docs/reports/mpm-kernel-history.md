<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Local Kernel installation acceptance

Historical test record from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
The fixtures and observations below are not the current command contract.

## Owner local Kernel installation acceptance, 2026-10-29

The owner ran the repository frontend at functional revision
`013cb40947243b28efc5ee6caa7f3063f600ab77` as an ordinary user on Debian,
using a dedicated private registry and the previously accepted real package:

`sha256:eed451b5497d078b8de4c098539cf63a4551aa0a46864fe7550b59066fe26250`

Empty status and installation preview created no registry or installed content.
Installation retained package version `6.12.107-r1` and actual kernel release
`6.12.107-mojt1`; `status --verify` verified the retained archive, extracted
files and metadata. No staging entries remained. Repeating installation reported
no change, preserving the complete status and original installation record.
The source archive checksum remained unchanged.

Ordinary status then reported the installed package as
`verified-at-installation`, distinct from the fresh `verified-now` scrub.
Selected deployment remained unknown, and running release was the Debian
host's `7.2.9+deb13-amd64`, with exact running artifact unknown. Installation
did not create a deployment selection or claim compatibility/boot readiness.
This accepts local import/status/idempotence for the real package; it does not
test boot activation, repository trust, shared privileged installation or
power-loss recovery. No new kernel build or VM boot cycle was required.

