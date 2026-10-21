<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt Architecture (experimental)

This document records **current decisions and open questions**, not stable promises. For the enduring design goals, see [the manifesto](manifesto.md).

## Layers

| Layer | Purpose | Intended lifecycle |
| --- | --- | --- |
| Base | Minimal glibc-based Unix userspace; shell, core tools, standard system files | Whole-image releases, versioned and rollback-capable |
| System | Kernel, init, firmware, networking, drivers, services and deployment profiles | Independent, but tested for Base ABI compatibility |
| Ports | Applications, libraries, developer toolchains and profiles | Independent versions, pinned environments, optional sandbox execution |
| State | Local configuration, service data and user data | Persists across Base upgrades and rollbacks |

The current Base prototype has no kernel, init, or desktop. The choice of a future System init implementation is not yet frozen. Standardizing on a single supported init system is preferable to maintaining multiple init stacks by default.

## Existing prototype pipeline

```text
bootstrap/void.sh
       |
       v
rootfs (from selected Void packages)
       |
       v
tools/mojt-base-pack + manifests/base-0.1.1.toml
       |
       v
versioned release (rootfs.tar.zst, manifest.toml, optional packages.txt)
       |
       v
tools/mojt-base-install
       |
       +--> base/<version>/
       +--> base/current -> <version>
       +--> state/etc/
       +--> state/var/
```

The prototype bootstrap currently selects eleven Void packages and uses a pinned static XBPS utility as a host-side construction tool. The assembled runtime image strips XBPS executables and package databases. The release is **not yet a bootable OS**.

## Configuration and state

The Base image carries package defaults in `/usr/etc`. During installation, missing defaults are added to a persistent `state/etc` tree. Existing entries are preserved. `/etc/os-release` is a relative symlink to `/usr/lib/os-release`, which the Base packer generates from its version manifest.

Persistent `state/var` is kept across Base generations. For testing, the two state directories are bind-mounted over `/etc` and `/var` in the selected rootfs inside a separate mount namespace. A future boot process must implement this arrangement before starting services.

Rollback does **not** revert persistent state or database formats. Future compatibility checks and explicit state migrations will be necessary.

## Ports direction

Ports should support:

- multiple installed versions and version-specific dependencies;
- profiles that activate selected versions via links or a similarly simple mechanism;
- project lockfiles that protect compilers and build dependencies from ordinary updates;
- native execution by default for ordinary command-line tools;
- optional security sandboxes for programs or build processes where useful.

This remains a design direction, not an implemented Mojt Ports manager. We should evaluate mature components before creating our own resolver or content-addressed store.

## Explicitly unresolved

- Source-based/self-hosted Base build and verifiable reproducibility
- Signature verification and trusted release channels
- Crash-safe activation and `fsync` durability guarantees
- Boot integration, state mounts, and kernel/module versioning
- ABI policy between Base, System, and Ports
- State migration/rollback guarantees for system services
- Alternative bootstrap backends and platform support
