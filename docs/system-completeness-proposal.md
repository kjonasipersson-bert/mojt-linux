<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Proposal: a useful System and ordinary user accounts

Status: account integration proposal, 2026-10-26. The owner accepted the
separate state/home and state/root storage layout; see [state layout](state-layout.md).
Other account details remain the proposed next integration. This document
itself adds no packages or authentication changes.
The [roadmap](roadmap.md) records the agreed work order; the
[kernel acceptance](boot-generations.md#owner-different-kernel-acceptance-2026-10-26)
establishes the starting point.

## Measured progress after the original proposal

Diagnostics and the clean console/time/journal A → B → A experiment passed.
The owner also accepted step 9 timezone, UTF-8 and manual checks after correcting
console SIGPIPE handling, deferring a separate step 9 A/B run to the next stage.
Homes in that guest still reside in Base; persistent home mounting is now being
prepared as the foundation for accounts. Optional SSH and personal Ports remain
later work. Historical starting-point descriptions below refer to step 6.

## Goal and current foundation

A user should be able to diagnose the machine, maintain it and work from a
normal account without first building an administrative environment in Ports.
Keep Base as a complete release. System owns machine services, their management
tools and authentication integration. Applications and development toolchains
remain independently selectable in Ports.

The current step 6 System already supplies systemd, D-Bus, NetworkManager,
udev, kernel/modules/firmware, curl/CA certificates, Nix/MPM, Bash, procps,
selected util-linux commands, less and nvi. It has authenticated root console
login via BusyBox and persistent root history. Ordinary-user provisioning,
persistent home mounts, PAM sessions, sudo and personal MPM scope have not
been established. A package in the Nix closure is not proof that its command,
service, privilege mechanism or configuration is integrated.

## Small implementation stages

| Stage | Proposed scope | Acceptance before moving on |
| --- | --- | --- |
| 1. Diagnostics | Add iputils `ping`; inspect/export `ss`, `getent`, `id`, `groups`, `hostname`, `modinfo`, `lsmod` where absent; retain existing ip/nmcli/curl and journalctl/systemctl | Exact providers and closures recorded; commands usable after login; DNS, HTTPS and controlled local ICMP checks; Base unchanged |
| 2. Console and time | Terminal-size query tool with manual fallback; useful UTF-8/TERM defaults; accessible man pages for supplied tools; verify persistent journal and time synchronization | Full-screen tools match actual terminal size; logs survive reboot with a bounded retention policy; selected time service synchronizes without competing with another |
| 3. Accounts and administration | Persistent homes, shadow tools, PAM-aware console login, session setup and sudo as one tested integration | Ordinary/admin user tests, password changes, isolation, logout, reboot and compatible generation return |
| 4. Optional remote access | OpenSSH server as an explicit System service choice, after account integration | Key login, persistent host keys, ordinary user plus sudo, and no root SSH login by default |
| 5. Personal Ports | Separate user selections after a reviewed multiuser Nix/MPM model | Independent selections, concurrent operation and inability to mutate another user's or the machine's profile |

Do an inventory before adding packages: export already available commands when
appropriate, and avoid duplicating working Base commands just for completeness.
Keep each stage small enough for its own PR and VM acceptance. Larger disk,
partitioning, filesystem repair and firewall toolsets can follow explicit use
cases. Desktop selection, automatic boot fallback and self-hosting are separate
tracks; this proposal does not choose a desktop.

For `ping`, first validate root use, then ordinary-user ICMP echo using Linux
ping sockets and a deliberate `ping_group_range` policy. Prefer that over a
setuid ping or blanket raw-socket privileges. Verify the pinned iputils build
supports the intended mode and both supported kernels accept it. QEMU user
networking and external ICMP filtering make a failed public-host ping ambiguous;
use loopback/a known responder and retain HTTPS as a separate network check.

Proposed System reports should list direct component selections, exact builds,
dependency closure, enabled services and changes against a previous generation.
Reuse existing manifest/boot records first; do not create a second package
database. This is how a larger System remains understandable.

## Recommended account model

Use traditional local Unix accounts. Adopt established shadow tools
(`useradd`, `usermod`, `userdel`, `groupadd`, `gpasswd`, `passwd`, `pwck`, `grpck`)
and a PAM-aware login implementation. Select the actual login provider after
checking the pinned package outputs. Integrate Linux-PAM and systemd-logind
with explicit configuration; do not assume the existing static BusyBox login
will start using PAM when packages are added.

| Concern | Proposed policy |
| --- | --- |
| Account authority | Persistent `/etc/passwd`, `/etc/group`, `/etc/shadow`, `/etc/gshadow`; standard locking-aware tools modify them |
| Human identities | Allocate from 1000 through 60000 by default after checking existing IDs; one primary group per user; never renumber existing owners on upgrade |
| Service identities | Separate reserved range and local registry; use systemd-sysusers for missing service accounts, preserve existing IDs, reject conflicting assignments |
| Home directories | Persist in `state/home`, bind mounted at `/home`; `/home/<name>` is the user-facing path |
| Home privacy | New homes mode 0700; user-controlled files and history; shared project directories are explicit group-owned exceptions |
| Root home | Persist at `state/root`, mounted at `/root`; explicitly migrate any existing root files and preserve current history |
| Login shell | System Bash through a stable System-owned path, listed in `/etc/shells`; preserve explicit local choices |
| Administrators | Explicit `sudo` group, password-authenticated sudo by default; ordinary accounts get no administrative membership automatically |
| Root access | Retain current VM root recovery during migration; lock direct root password login only after an administrative account and recovery path have been tested |
| Account deletion | Explicit administrator action; retain home data by default, handle sessions/ownership separately; no generation-driven deletion |

The accepted storage choice uses separate state directories on the existing
filesystem, mounted at conventional paths. A later filesystem/subvolume method
can preserve this runtime contract. Inspect and reject conflicting nonempty
mountpoints; never hide existing home files silently. Mount homes before logins
and stop normal login if mounting fails. Existing images require an explicit
migration and backup; see [state layout](state-layout.md).

For new installation, explicitly offer creation of a named administrative
account, set its password interactively, and test sudo. No shared default
password or password in command arguments/manifests. Use the same local account
tools for later users; a Mojt-specific account command is unnecessary initially.
Do not enable automatic login. Keep service accounts non-interactive, with
locked passwords and a suitable nologin shell.

Configure NSS local account/group lookup, compatible password hashing, PAM
authentication/account/password/session stacks and logind together. The session
path must provide correct supplementary groups, HOME, ownership and a private
`/run/user/<uid>`; verify creation/cleanup and systemd user sessions explicitly.
All ordinary users need to be able to change their own password without access
to another user's credentials. Integrate the required privileged helpers from
the selected packages rather than merely exporting their binaries.

Nix store binaries alone do not establish working sudo or passwd privileges.
Audit the pinned packages' helper paths and privilege assumptions. Propose a
small root-owned runtime installation of required privileged executables from
verified System outputs, with explicit owners/modes and generation binding.
Never put setuid bits on scripts or mutate shared store objects. Validate
sudoers with visudo, use a trusted System/Base search path and sanitized
environment, and keep user-writable Ports paths out of privileged resolution.
The exact helper layout is an implementation decision requiring review.

## Accounts across System and Base changes

Creating a user or changing a password changes machine state; it does not
require rebuilding System. Selecting an older System does not restore an old
password, undo group membership or delete a newer user/home. Service accounts
created by a newer generation also remain; do not reclaim their IDs during
ordinary rollback or pruning.

An older generation must still support the current account database, password
hash format, PAM configuration, login shell path and home mounts to qualify as
a working login fallback. Today's root-only images do not automatically meet
this requirement. First establish two compatible account-enabled generations
and test A → B → A with user state created/changed under B. Retain the earlier
VM separately as a recovery reference, not as proof of account compatibility.

Preserve administrator-owned `/etc` files under the add-missing policy. New
release defaults belong in release-owned default content; an upgrade requiring
a PAM/sudo configuration migration needs an explicit plan. Never overwrite
authentication configuration on every boot. Avoid switching privileged helpers
to the next selected System while the previous one is still running.

## Shared and personal Ports

Start with the existing machine-wide Ports profile: administrators install and
activate, ordinary users execute. Verify directory traversal/read permissions
on the profile, store and roots; keep profile/database writes root-owned.
Expose a read-only list of installed versions to ordinary users without giving
them write access to MPM state. Per-user account support can ship before
unprivileged package installation.

Later, add an explicit personal scope, for example `mpm ports --user ...`
(proposed syntax, not runnable today). Personal request/selection/history state
would live in the user's persistent home. A user's changes must affect only
their scope. Interactive lookup could be personal Ports → shared Ports →
System → Base, with `list`/`info` clearly identifying scope and command shadowing.
Service units and administrative tools must use exact/trusted System paths.

Keep one protected shared Nix store. A multiuser daemon is a candidate for
unprivileged imports; it does not by itself implement MPM's per-user permissions,
profile publication, GC roots, locking or disk-use policy. Do not make the store
or machine MPM database group-writable, or grant ordinary users Nix trusted-user
status. Defer this integration until the root-operated path and account tests
are stable. Installing a Port must not implicitly create machine users, enable
services or grant privileges.

## Acceptance for the account stage

- Create one administrator and one ordinary account; confirm IDs, groups,
  homes, shell, password change, serial login and logout.
- Confirm the ordinary account cannot read private homes/shadow, change
  machine Ports or administer the machine; admin sudo succeeds, unauthorized
  sudo fails, and personal PATH changes cannot redirect privileged commands.
- Confirm the user can run the shared hello artifact and list its exact identity.
- Reboot; check home contents, ownership, shell history, credentials and session
  runtime cleanup. Check console geometry and journal/time diagnostics separately.
- Boot a second compatible account-enabled System, create a third user and
  change an existing password, then return to the first. Verify new credentials,
  IDs, groups and all home data persist; the obsolete password stays invalid.
- Exercise a missing-home-mount failure, invalid account/configuration inputs,
  and a recovery procedure before disabling password login for root.

No account integration or new account acceptance is claimed by this proposal.

## Upstream references

- [Shadow account tools](https://github.com/shadow-maint/shadow) and
  [login defaults](https://github.com/shadow-maint/shadow/blob/master/etc/login.defs).
- [Linux-PAM](https://github.com/linux-pam/linux-pam).
- [systemd-sysusers](https://www.freedesktop.org/software/systemd/man/latest/systemd-sysusers.html)
  for service identities and [UID/GID conventions](https://github.com/systemd/systemd/blob/main/docs/UIDS-GIDS.md).
- [pam_systemd](https://www.freedesktop.org/software/systemd/man/latest/pam_systemd.html)
  for login sessions and runtime directories.
- [Linux ping_group_range](https://kernel.org/doc/html/latest/networking/ip-sysctl.html)
  for ICMP datagram socket policy.

These references describe upstream mechanisms. Available features and defaults
must be checked against Mojt's pinned builds before implementation.
