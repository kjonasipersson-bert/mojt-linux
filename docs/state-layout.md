<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Persistent state and generation selection

The owner accepted this home layout on 2026-10-26, before implementation of
ordinary accounts. Homes have their own state directories, not locations
beneath `/var`. This is an internal prototype storage method, not a requirement
from Linux or Nix and not a commitment to one future filesystem technology.

## Physical storage and runtime paths

The root partition contains complete `base/<version>` trees, System inputs and
one shared `state` tree. An EFI partition is separate in UEFI images. No new
home partition is required by this change.

| Directory on the root partition | Path in running Mojt | Ownership of content |
| --- | --- | --- |
| `base/<selected-version>` | `/` | Selected Base release |
| `state/etc` | `/etc` | Persistent machine configuration |
| `state/var` | `/var` | Persistent service and package state |
| `state/home` | `/home` | Persistent ordinary-user homes |
| `state/root` | `/root` | Persistent root home |

The initramfs mounts the selected Base directory as the runtime root, then
bind mounts each state directory onto its conventional path before starting
System. `/home/example/file` and `state/home/example/file` identify the same
stored file, not synchronized copies. The backing partition is currently
also reachable at `/run/mojt-disk` in a System VM; that is a prototype detail.

Generation selection changes the Base/System inputs while retaining these
state directories. It does not undo password changes, user creation, home
files or service database changes. Compatibility with an older System's
configuration, helpers and password formats still needs explicit testing.

Disk updating is separate: adding and publishing a new boot generation is
not implemented by the bind mounts. Current experiments compose fresh images;
there is no general in-place installed-disk updater in this change.

## Construction and compatibility

The directory installer creates missing `state/home` and `state/root` with
initial modes 0755 and 0700 respectively. Existing contents and permissions
are retained. Individual ordinary-user homes will be created with mode 0700
by the later account stage. No users, PAM configuration or sudo policy are
created here.

This extends prototype layout 1 additively. It does not require rebuilding
Base 0.1.3 or changing its release metadata. New VM construction copies existing
home state with ownership/modes preserved. A legacy directory installation
without home state gets empty home directories only in the private new-image
tree; the builder does not modify the source installation.

Every selected Base must have empty, real `/home` and `/root` mountpoints.
Missing points can be created in the private copy. Files, symlinks and
nonempty directories are rejected before publishing the image. Initramfs
requires both home state directories and successful mounts; it must not
silently fall back to writing homes into Base if a mount fails.

Older VM builders/initramfs did not copy or mount this home state. Do not use
them to rebuild an installation containing these homes, or assume that old
boot choices provide a working home-aware fallback. Newly assembled choices
all use the updated initramfs. Future layout migrations need explicit version
and compatibility policy; layout 1 is still a development format.

## Existing files and migration boundary

The inspected step 9 guest had `/root/.lesshst` inside Base, with `/home` empty.
That running guest is not changed by updating the builder. Keep it as a
reference. A fresh image built from the original directory target also does
not import state or files subsequently created on another VM disk.

To convert an existing image, first stop it and back it up. Inventory home
contents across all retained Base generations, copy them with ownership and
permissions into the intended state directories, resolve conflicts explicitly,
and verify the copy before emptying any underlying mountpoint. Rebuild matching
boot inputs and test recovery before activation. Never hide a nonempty home
by mounting an empty state directory over it. This change deliberately provides
no automatic disk conversion or live migration command.

Existing System root Bash history remains in `/var/lib/mojt/console/root.history`
for compatibility; moving it to the persistent root home belongs to the
account/history integration. Other root files naturally use the new `/root`.

## Acceptance with the next account image

Reuse the accepted step 9 payload or a later account payload with the updated
builder; no Nix package is needed solely for this storage change. In the new
guest, inspect the mounts and write independent home probes:

```sh
findmnt -T /home -o TARGET,SOURCE,FSTYPE
findmnt -T /root -o TARGET,SOURCE,FSTYPE
stat -c '%a %U:%G %n' /home /root
mojt-system-check homes-write
```

Power off orderly, boot the same disk into the other newly assembled choice,
and run `mojt-system-check homes-check`. Return to the first and repeat the
check. Retain the environment, journal, identity, time, network and Ports
regression checks from step 9. Account acceptance must also verify user home
ownership, privacy and credentials across compatible choices.

Local tests cover missing-state initialization, preservation of existing home
data/modes, rejection of unsafe or nonempty paths, source preservation and
installer failure cleanup. Owner VM evidence now confirms the home mounts and account/home retention
across the account A/B/A run; see the acceptance record below.

## Owner home-state acceptance

In `/home/jonasp/mojt-accounts.Vxdthq/serial-image`, the owner observed separate
ext4 binds from state/home and state/root and mode/private-owner checks through
actual PAM logins. A → B retained independent home/root probes alongside the
existing machine ID, `/etc`, `/var` and journal probes. A normal user's home
marker remained readable on B. A new user created under B returned to A with
UID 1002, the same complete id output and its B-created home marker intact.

This establishes persistent home state on the tested shared disk and compatible
boot choices, not a general disk updater or migration of an old nonempty Base
home. Account/user-manager corrections were applied to this test image's
persistent `/etc`; the full scope and remaining checks are recorded in
[account acceptance](system-accounts.md#owner-aba-acceptance-after-the-correction).
