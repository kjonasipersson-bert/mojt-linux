<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# 1. Introduction

[Handbook](../README.md) · [Next: Installing Mojt](installing-mojt.md)

## 1.1. Why Mojt?

Mojt is an experimental Linux distribution built around independent lifecycles.
A small Unix Base, the operating System and installed applications should be
understandable and manageable separately. Updating the operating system should
leave an application's selected version and a project's pinned compiler alone.

The inspiration is FreeBSD's separation of the base operating system and Ports.
Mojt applies that idea to Linux with its own Base, System, Ports and persistent
machine state. It favors ordinary Unix mechanisms, explicit choices and reuse
of existing tools. The objective is predictable maintenance, rather than the
smallest possible disk usage or a new dependency solver.

## 1.2. Base, System, Ports and state

| Part | Responsibility | Unit of change |
| --- | --- | --- |
| Base | Small glibc-based Unix userspace | A complete versioned release |
| System | Init, services, networking, management tools, hardware integration and firmware | A coherent userspace generation; Kernel is managed separately within System's scope |
| Ports | Applications, libraries and development toolchains | Parallel installed versions and selected commands |
| Persistent state | Machine configuration, service data and user files | Explicit administrative changes and application writes |

Base is built and distributed as a complete image, with `rootfs.tar.zst` at its
core. Its installed runtime is not upgraded one library or utility at a time.
Base itself needs no Kernel, init, desktop or Python. System supplies those
facilities needed for a bootable machine, including the management Python.
The current System implementation uses systemd.

The `mpm kernel` command area manages a System-owned component: the Linux Kernel,
its matching modules and boot artifacts. Keeping it separately selectable lets
you test a new Kernel without replacing Base or System userspace. Each build
needs a distinct identity and compatible module tree.

Ports supplies applications and toolchains. The current backend uses Nix to
obtain binary packages and retain their dependency closures. System and Ports
can share immutable dependency storage while keeping their own installation
and activation choices. A Ports installation does not select a new System or
configure a service automatically. Nix is an implementation backend; independent
Mojt artifacts and installation semantics are the wider design.

## 1.3. Installing and selecting are different

An installed object is available locally. A selected object is the one a command
profile or the next boot will use. For boot components, running is another state:
choosing the next boot leaves the current processes and Kernel running.

| Observation | Meaning |
| --- | --- |
| Available | Accepted metadata offers the content |
| Cached | Verified transport bytes have been retained |
| Installed | The area's usable local representation has been retained |
| Prepared | A compatible complete boot deployment has been constructed and admitted |
| Selected | Commands, or the next boot, will use this choice |
| Running | This is the content observed in the current boot |

A boot deployment ties exact Base, System and Kernel identities to their boot
files and machine policy. This prevents selecting an arbitrary mixture merely
because all three components happen to be installed. Human labels help identify
releases; exact artifact and deployment IDs distinguish different builds with
the same label.

For example, after installing and preparing System B while running System A,
status can show A running and A selected. After activating B, it shows A running
and B selected for next boot. After a successful reboot, both should show B.
The retained A deployment remains available for a compatible return.

## 1.4. Several versions of one application

Mojt can retain multiple versions of an application at once. The default command
selects one version; keeping another version installed does not force it to
become the default. This also permits private tool environments whose compiler
and libraries stay fixed while ordinary application choices change.

The first unambiguous direct Ports installation normally establishes a default.
Installing another version preserves an existing default. You change the default
explicitly with `mpm ports activate`. [Chapter 3](mpm.md) explains exact pins,
following selections and the limits of the current catalog.

Parallel versions retain their dependencies, so an older executable can keep
using the libraries it was installed with. Application data is a separate concern:
two program versions may still read the same home directory or database.

## 1.5. What an upgrade means

Base upgrades replace the selected complete Base release. System upgrades lead
to a new coherent selected generation, retaining compatible older choices for
return. Kernel upgrades retain the new Kernel with its matching modules.
These boot changes take effect after a deliberate reboot.

Ports upgrades advance saved installation wishes within their allowed version
policies. A wish for a release series can follow that series, while an exact pin
stays fixed. Merely retaining an old version is not a request to upgrade it.
A Ports change can publish a new internal command profile and history record;
it does not create a new operating-System generation or require a reboot.

The current Base/System/Kernel upgrade interface takes an explicit installed
artifact. General moving-policy upgrades for these boot areas remain future
work. Ports already supports upgrades driven by saved wishes.

## 1.6. Configuration and return to older code

Release defaults belong under `/usr/etc`. Persistent machine `/etc` receives
missing defaults through supported initialization/preparation paths; existing
configuration is not silently overwritten or removed. An incompatible transition
or missing required preparation can block a deployment.

`/etc`, `/var`, `/home` and `/root` retain machine state across supported boot
changes. Selecting an older deployment returns to older code, without restoring
an earlier database schema, configuration or user file. Retained generations
and backups serve different purposes.

## 1.7. Where to go next

The installation chapter is reserved until the installation workflow is ready
for a general guide. Continue with [MPM](mpm.md) to manage an existing Mojt
installation, or [MBT](mbt.md) to prepare tool environments and build results.
For the project's goals and layer boundaries, see the
[manifesto](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/manifesto.md) and
[architecture](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/architecture.md).

[Previous: Handbook](../README.md) · [Next: Installing Mojt](installing-mojt.md)
