<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native release metadata

This directory on the `main` branch holds the signed native release catalogs.
GitHub Releases host the referenced archives.

| Area | Signed stable catalog |
| --- | --- |
| [Base](base/README.md) | `repository/base/stable.json` |
| [Ports](ports/README.md) | `repository/ports/stable.json` |

The publisher creates the channel files when releasing them. Keep publication
receipts and private signing configurations and keys outside this directory.
