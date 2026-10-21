<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt Linux Manifesto

*Simple by design. Flexible by nature.*

## Vision

Mojt is a Linux distribution built around a simple idea: **the operating system, system services, and applications should be able to evolve, be installed, and be updated independently.**

Inspired by the clear separation between the base system and ports in BSD, Mojt combines a small, coherent Unix foundation with modern application management, versioned environments, and optional isolation.

Mojt should be understandable, dependable, and practical to build, operate, and maintain. It should feel equally natural as a minimal container root filesystem, a server, a virtual machine, or a desktop workstation.

## Principles

### 1. The operating system is not the application collection

Mojt has three distinct layers:

- **Base** provides the smallest useful, coherent Unix userspace.
- **System** supplies the kernel, init system, firmware, hardware support, networking, and system services appropriate to a machine or deployment profile.
- **Ports** supplies applications, development tools, and their dependencies.

Each layer has a defined responsibility and its own release and update lifecycle. A minimal Base does not require a desktop, a kernel, or even an init process when used in a container.

### 2. Base is a product, not a package repository

Base is delivered as a complete, versioned filesystem image. It can be installed, verified, upgraded, and rolled back as a unit. Its build process may use existing distribution packages or source builds; the running Base does not need the package manager used to assemble it.

Small, complete updates are a reasonable starting point. Incremental distribution can be introduced later if it solves a real problem.

### 3. Installation and activation are separate operations

Multiple versions of an application and its dependencies must be able to coexist. Installing a version makes it available; activating it selects where and for whom it is used.

Profiles and project environments should select explicit installed versions without globally replacing programs or libraries. Switching a profile should be simple and reversible.

### 4. Updates must be deliberate and predictable

A normal system or application update must not silently replace the toolchain used by an existing project. Development environments should be lockable to exact versions, including transitive dependencies, until the user explicitly updates them.

Ordinary applications may follow update channels; pinned environments remain pinned. Security issues in pinned software should be visible even when automatic updates are disabled.

### 5. Dependency isolation is not the same as sandboxing

Programs should be able to carry or refer to their own versioned libraries without interfering with other software. Library selection must not depend on mutable global profiles.

Security sandboxing is a separate choice. It can be valuable for graphical applications, untrusted workloads, and builds, but must not be mandatory for every command-line tool. A tool such as `curl` should remain a normal Unix program unless a policy explicitly constrains it.

### 6. The distribution owns defaults; the machine owns state

Versioned defaults belong to the distribution, preferably under `/usr`. Local configuration belongs under persistent `/etc`; mutable application and service state belongs under persistent `/var`.

Base upgrades must preserve local configuration and data. The initial configuration policy is deliberately conservative: add missing defaults, never silently overwrite locally present files, and never silently delete them on rollback. More sophisticated merging may be added when justified.

### 7. Buildability is part of the design

Mojt should ultimately be self-hosting: its own toolchain and build environment should be capable of rebuilding Base from documented sources and pinned inputs. A compiler does not need to be installed in every running Base image to meet this goal.

Bootstrap implementations may use Void, Debian, or other sources, provided they produce an image that satisfies the same Mojt Base contract. Reproducible builds are a goal to be verified, not assumed.

### 8. Prefer existing Linux and Unix mechanisms

Use ordinary processes, ELF binaries, dynamic linking, symlinks, standard filesystem layouts, and proven Linux security features wherever practical. Reuse existing tools for packaging, builds, service management, and isolation rather than inventing new subsystems without a compelling reason.

### 9. Minimalism serves simplicity, not the other way around

The smallest system is not automatically the easiest system to operate. A slightly larger, well-understood component is preferable to a complicated custom replacement that saves a few megabytes.

Mojt favors transparent behavior, readable tools, sensible defaults, and low maintenance costs over architectural purity.

## The goal

A Mojt user should be able to run a small, stable operating system; install current software; keep older toolchains available; choose which versions are active; and update or roll back the system without unexpected changes to applications, projects, configuration, or data.

**Make simple things simple and complicated things possible, without making everything complicated.**
