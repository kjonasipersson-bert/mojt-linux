<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Native release metadata

This directory is the publication location for signed native repository catalogs.
The Base channel path is `base/stable.json`; native package archives live in
GitHub Release assets. An official channel/key is available only after the
publisher prepares and publishes them. This source directory does not contain a
placeholder trust key or an unsigned catalog presented as a release.

See [Signed Base repository](../docs/native-repository.md) for the current
publisher/client commands, trust model and supported scope. Publication receipts
and private signing configurations/keys do not belong in this directory.
