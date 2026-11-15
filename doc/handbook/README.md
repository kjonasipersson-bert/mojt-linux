<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt Handbook

Welcome to the Mojt Handbook. This book explains how Mojt is organized and how
to use it, from choosing program versions to building a new Kernel.
It takes inspiration from the FreeBSD Handbook's progression from concepts to
practical tasks. The text and examples describe Mojt itself.

Mojt is experimental. This first edition documents the current repository
implementation; interfaces and supported transitions can still change.
Implemented workflows and future intentions are identified where they differ.
The handbook is a user guide; the technical documents in [`docs/`](../../docs/)
remain the references for formats, implementation details and acceptance evidence.

## Part I. Getting started

1. [Introduction](part-i/introduction.md)
2. [Installing Mojt](part-i/installing-mojt.md) — reserved; not written yet
3. [mpm — Mojt package manager](part-i/mpm.md)
4. [mbt — Mojt build/bootstrap tool](part-i/mbt.md)

## Part II. Common tasks

[TBD](part-ii/README.md). Chapters will be added as workflows become established.

## Part III. System administration

[TBD](part-iii/README.md). Chapters will be added as workflows become established.

## Part IV. Development

[TBD](part-iv/README.md). Chapters will be added as workflows become established.

## Reading the examples

Commands use an installed Mojt System unless a section explicitly says otherwise.
MPM is supplied by System. MBT is optional and requires a builder-enabled System.
For local manuals and command-specific options, use:

```sh
man mpm
man mbt
mpm ports install --help
mbt build kernel --help
```

Inspection normally needs no administrator privileges. Changes to the shared
installation require an administrator; Kernel compilation runs as an ordinary
user. Each chapter states its additional prerequisites. Examples omit shell
prompt characters so they can be copied directly.

Uppercase values such as `FULL_ARTIFACT_ID` and paths such as
`/packages/kernel.tar.zst` are placeholders. Replace them with the exact values
from your own accepted inputs and command output. SHA256 identifies and checks
content; it does not authenticate a publisher. Native release signing remains
future work.

## Extending the handbook

Keep chapters in English, with a short explanation before each workflow and
examples that match the delivered CLI. Explain the result of an operation,
its prerequisites and how to inspect it. Link to technical references rather
than duplicating format specifications or historical test logs. Keep unwritten
chapters marked as such; a proposed command must not look like a working one.
Update this contents page and chapter navigation when adding chapters.
