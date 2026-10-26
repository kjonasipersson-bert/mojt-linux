<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# System step 10: local accounts and administration

Status: owner A/B/A account, home and Ports evidence recorded below.
Explicit rejection of the superseded administrator password awaits confirmation.
The owner accepted local-account preparation and separate persistent
`state/home` and `state/root` storage. See [state layout](state-layout.md).
Synthetic tests do not establish working PAM authentication or setuid behavior.

## Scope and inputs

The only new binary package roles are shadow, Linux-PAM (`pam`) and sudo, plus
their separate manual outputs. Existing systemd supplies logind, loginctl,
pam_systemd, the user runtime helper and systemd-sysctl. The pinned package
definitions were inspected for paths and privilege assumptions; actual payload
validation must still confirm every executable/module/plugin in the export.
The binary-only preparation backend does not build replacement packages.

Shadow's PAM-enabled login replaces BusyBox login on authenticated consoles.
BusyBox still supplies getty and boot/shutdown support. Local NSS files remain
the account authority. UIDs/GIDs 1000–60000 are the initial human allocation
range; shadow tools allocate IDs and user-private primary groups. Existing
identities and passwords are not reset. New human homes are mode 0700 under
`/home`, backed by `state/home`; `/root` is backed by `state/root`.

PAM authenticates nonempty passwords through pam_unix, performs account checks
and registers actual console sessions with required pam_systemd. Initial
password changes use SHA-512 crypt, including the existing builder-provisioned
root password. No shared password or password in command arguments is used.
The initial stack is intentionally small; lockout/rate-limit policy, external
identity providers and richer password policy are not supplied here.

Root password login remains enabled during acceptance. Administrators are
explicit members of group sudo and authenticate with their own password for
each sudo invocation. The initial secure_path contains System/Base directories,
not personal or shared Ports. Unauthorized users receive no sudo grant.
The user manager and private `/run/user/<uid>` are integrated, with prompt
cleanup after the last session. No session D-Bus, desktop, SSH server, linger
policy or personal Ports installation is claimed. KillUserProcesses=yes is
an explicit initial policy for ordinary sessions; background jobs are not
promised to survive logout.

## Privilege boundary

Nixpkgs removes setuid bits from the store's sudo and shadow binaries. Its
Linux-PAM build also expects unix_chkpwd at `/run/wrappers/bin/unix_chkpwd`.
Merely exporting commands would not make ordinary-user authentication work.

At boot, a root oneshot verifies the selected sudo, passwd and unix_chkpwd ELF
files against hashes recorded when the payload was assembled. It requires the
persistent home mounts, creates a dedicated suid-capable tmpfs at
`/run/mojt-privileged`, writes root-owned mode-0600 copies, checks sudoers with
visudo, then grants only those three copies mode 4755. A compatibility link
provides the exact PAM helper path. Normal command links point at the running
generation's volatile copies.

The store and persistent System profiles receive no setuid/setgid bits. Thus
retained older profiles do not expose a second set of privileged copies through
the backing disk. The runtime is reconstructed at boot, not switched underneath
existing sessions. Console units require successful privilege and logind setup;
configuration or staging failure blocks normal login. Reboot to reconstruct
this runtime rather than restarting it while sessions are active.

This is an explicit prototype integration, not the full NixOS wrapper system.
Integrity hashes detect input changes; they do not replace signed boot/release
verification. Actual ELF relocation, helper execution, PAM and sudo authorization
must pass the guest acceptance below before this can be considered usable.

## Configuration and compatibility

Initial `/etc/pam.d`, login.defs, useradd defaults, sudoers, sudo.conf and logind
configuration are installed only if missing or byte-identical. An existing
different administrator configuration stops fresh image assembly for review;
it is never overwritten. PAM module and sudo plugin paths in persistent config
refer to the selected `/run/mojt-system` profile, not one obsolete store output.
Missing shadow/gshadow are provisioned by the existing authenticated builder.

Linux ICMP datagram ping sockets are allowed for groups 1000–60000 through a
specific sysctl default and a scoped systemd-sysctl invocation. ping receives
no setuid bit or raw-socket capability. Administrator sysctl drop-ins can change
this policy; inspect the effective value when interpreting a ping failure.

Only account-enabled System profiles can share this test image. The builder
refuses a mix with legacy root-only profiles. Selecting an older compatible
profile preserves current users, passwords and homes; it must not revive an
old password or delete a newer user. The earlier step 9 image remains a
separate recovery reference. No in-place conversion of its disk is performed.

Shared Ports remain administrator-managed. The step 10 MPM wrapper uses umask
022 for readable shared profiles and lets ordinary users run `mpm ports list`.
Mutation commands require an administrator; filesystem ownership remains the
actual write boundary even if the wrapper is bypassed. No multiuser Nix daemon
or user-writable shared store/profile/database is introduced.

## Prepare in the existing Nix container

From Debian, enter `distrobox enter mojt-mpm-nix`, then run without sudo:

```sh
bash <<'MOJT_ACCOUNTS'
set -euo pipefail
SOURCE="$HOME/mpm-system-test/mojt-system-accounts"
PAYLOAD="$HOME/mpm-system-test/system-step10"
git clone --single-branch --branch feature/system-accounts \
  https://github.com/kjonasipersson-bert/mojt-linux.git "$SOURCE"
python3 "$SOURCE/tools/mojt-system-prepare.py" \
  --step 10 --output "$PAYLOAD" --dry-run
MOJT_ACCOUNTS
```

Review the exact binary outputs/cache availability, then export:

```sh
python3 "$HOME/mpm-system-test/mojt-system-accounts/tools/mojt-system-prepare.py" \
  --step 10 --output "$HOME/mpm-system-test/system-step10" -y
```

Exit the container. Follow the retained two-kernel fresh-image recipe from
[diagnostics](system-diagnostics.md#build-with-the-retained-two-kernel-sets)
with the new source/payload host paths, a fresh `mojt-accounts.XXXXXX` directory
and labels system-accounts-A/B. Both profiles must use step 10. Use password
login and `/run/mojt-system/bin/bash` for root as before. Keep the stopped
reference images. New images use the original directory installation as input,
not state subsequently created on another VM disk.

## Guest acceptance: root preparation

Start A and authenticate normally as root. If login fails, retain the boot
output and stop the test image for diagnosis; do not delete reference images
or disable authentication to obtain a passing result.

```sh
mojt-system-check accounts
mojt-system-check environment
findmnt -T /home -o TARGET,SOURCE,FSTYPE
findmnt -T /root -o TARGET,SOURCE,FSTYPE
findmnt -T /run/mojt-privileged -o TARGET,SOURCE,FSTYPE,OPTIONS
useradd -m -U -G sudo -s /run/mojt-system/bin/bash mojtadmin
passwd mojtadmin
useradd -m -U -s /run/mojt-system/bin/bash mojtuser
passwd mojtuser
id mojtadmin
id mojtuser
mpm ports update -y
mpm ports install hello -y
readlink -f "$(command -v hello)" >/var/lib/mojt/account-hello-path
mojt-system-check homes-write
mojt-system-check journal-write
mojt-system-check persistence-write
```

Create passwords interactively; never paste them into a script or logs. Log
out with exit and authenticate as each new user through getty, rather than
using a root shell to impersonate a user and calling that a login test.

## Guest acceptance: ordinary session and privileges

For each user:

```sh
mojt-system-check user
printf 'home-persistence\n' >"$HOME/account-marker"
passwd
hello
mpm ports list --exact
test "$(readlink -f "$(command -v hello)")" = "$(cat /var/lib/mojt/account-hello-path)"
```

Verify a wrong login password fails and only the newly changed password works.
As mojtadmin, `sudo -k` followed by `sudo id -u` must request that user's password
and print 0. A wrong sudo password must fail. Set PATH to a private directory
containing a fake id command, then invoke `/run/mojt-system/bin/sudo id -u`:
trusted secure_path must still resolve the real command.

As mojtuser, sudo must deny authorization even with the correct own password.
Confirm reading `/etc/shadow`, listing another private home, changing another
user's password and `mpm ports install hello -y` all fail. Ordinary self-password
change must succeed. Do not report a root-issued password change as proof of
the unprivileged helper path. Confirm interactive man paging, Bash history,
console geometry and clean logout for both users.

## Reboot and compatible-generation regression

After logging out, root should see the former user's sessions disappear and
its user@ service/runtime directory removed after the last session closes.
No lingering user manager is expected. Check this before reusing the UID.

Power off with `systemctl poweroff` to verify login1 integration. Boot the same
disk into B. Check homes-check, journal-check, persistence-check, accounts,
environment, diagnostics, diagnostics-network and clock after NTP replies.
Reapply the explicit Stockholm selection in this fresh image before claiming
its timezone persisted; step 9's VM state was not imported.

Authenticate again as both users and check IDs/groups, home markers/history,
new passwords and the same Ports artifact. Under B create a third account and
change a password, then return to A. The new account, new password and all
home data must remain valid; the obsolete password must stay invalid.

Before any later decision to lock root, exercise a stopped-image recovery
procedure and a deliberately missing-home-mount failure on a disposable copy.
Those failure/recovery tests are not provided by synthetic assembly checks.

## Console size: local versus serial

Run `tty`, `stty size` and `printf '%s\n' "$TERM"` when reporting dimensions.
On a Linux virtual console such as tty1, mojt-console-size reads the kernel's
existing grid through ioctls; it does not send the unsupported CSI 18 t query.
Changing QEMU's GTK window size/zoom does not necessarily change that grid.

For ttyS0 through QEMU stdio, terminal geometry is not automatically forwarded.
Run mojt-console-size at an idle prompt if the outer terminal supports its
query. Otherwise supply the real rows/columns explicitly. After resizing the
outer terminal, run it again and unset stale LINES/COLUMNS. Automatic resize
propagation is still future work; do not call this local-VT detection an
automatic QEMU window-resize feature.

## Sources checked against the pinned inputs

- [Shadow packaging](https://github.com/NixOS/nixpkgs/blob/5adc50831c259f87faeb09ddf930d43597197473/pkgs/by-name/sh/shadow/package.nix)
- [Linux-PAM packaging and helper path](https://github.com/NixOS/nixpkgs/blob/5adc50831c259f87faeb09ddf930d43597197473/pkgs/by-name/li/linux-pam/package.nix)
- [sudo packaging](https://github.com/NixOS/nixpkgs/blob/5adc50831c259f87faeb09ddf930d43597197473/pkgs/by-name/su/sudo/package.nix)
- [NixOS PAM helper integration](https://github.com/NixOS/nixpkgs/blob/5adc50831c259f87faeb09ddf930d43597197473/nixos/modules/security/pam.nix)
- [Upstream user runtime unit](https://github.com/systemd/systemd/blob/v262/units/user-runtime-dir@.service.in)

## Initial owner acceptance and user-manager shutdown correction

The owner exported 206 store objects and built
`/home/jonasp/mojt-accounts.Vxdthq/serial-image`. On system-accounts-A with
kernel 6.12.107+deb13-amd64, root PAM login, logind, the separate home mounts,
volatile privileged runtime and environment checks passed. mojtadmin (UID 1000)
and mojtuser (UID 1001) both passed real login/session/runtime and loopback ping
checks, and both changed their own password. mojtadmin authenticated through
sudo and obtained UID 0. mojtuser was denied sudo, another user's password
change, shadow/private home reads and shared Ports mutation. Root imported and
ran hello successfully. Per-user shared Ports reads remain to be confirmed.

Logout exposed an incomplete minimal user unit set: exit.target was missing.
The user manager could start but could not enqueue its shutdown transaction,
so PID 1 killed it after a 90-second stop timeout. Runtime-directory cleanup
then succeeded, explaining its temporary presence after logout. This was not
a successful cleanup acceptance. Home probes were written; journal-write
stopped at the failed-unit check and persistence-write was not reached.

The builder now exposes the selected systemd output's upstream exit.target,
systemd-exit.service and shutdown.target together. Their default-dependency
and ordering settings are retained verbatim; systemd 262 uses SuccessAction=
exit-force in its final user exit service. No stop timeout is shortened to hide
failure. The explicit user unit search path also includes root-managed
/etc/systemd/user for administrative corrections. Payload validation requires
all three upstream shutdown units, already present in the existing export.

Logind's unit now follows upstream FileDescriptorStoreMax=768 and
RuntimeDirectoryPreserve=yes, addressing the observed FDSTORE warnings without
restarting logind during active-session testing.

For the existing disposable test VM, copy those three files from the selected
`systemd` output's `example/systemd/user` into `/etc/systemd/user`, and add a
persistent user@ service drop-in selecting
`SYSTEMD_UNIT_PATH=/etc/systemd/user:/run/mojt-system/user-units`. A logind drop-in
sets the two properties above. Reload PID 1's unit configuration. Captured old
user-manager failures may then be reset, but that reset is not acceptance.
The already-running root user manager still has its old search path; an
explicit `systemctl --user --force exit` exits only that minimal user manager
through its private management interface before logout, without waiting for
the missing target. The console login remains a separate session scope.

Authenticate anew and log out as a real ordinary user, then verify from a fresh
root session that user@ ends with Result=success and /run/user/<uid> disappears.
The subsequent clean logout and generation results are recorded below.
The correction changes builder/units only; the exported payload can be reused.

References for the selected release:
[exit.target](https://github.com/systemd/systemd/blob/v262/units/user/exit.target),
[systemd-exit.service](https://github.com/systemd/systemd/blob/v262/units/user/systemd-exit.service),
[shutdown.target](https://github.com/systemd/systemd/blob/v262/units/user/shutdown.target),
[logind service](https://github.com/systemd/systemd/blob/v262/units/systemd-logind.service.in).

## Owner A/B/A acceptance after the correction

On the same stopped/restarted disk, the owner completed system-accounts-A
(kernel 6.12.107+deb13-amd64) → system-accounts-B (7.2.9+deb13-amd64) → A,
keeping Base 0.1.3. B reported exactly its matching module release. The owner
applied the user-exit and logind correction through persistent `/etc` files;
those corrections survived the boot choices. The corrected builder itself has
not received a separate fresh-image acceptance run after that repair.

After a fresh ordinary login/logout on A, user@1000.service ended inactive with
Result=success, its runtime directory disappeared, only root remained listed
and no units were failed. The ordinary account ran the shared hello command
and listed its exact installed identity. On B, three account logouts likewise
left only root, no ordinary runtime directories and no failed units.

On B, probes confirmed stable machine ID, independent `/home` and `/root`
markers, retained previous-boot journal and matching `/etc`/`/var` markers.
Root account integration and environment/manual probes passed. mojtuser logged
in with its changed password, read its original home marker, passed the actual
user/session/runtime/ping check, ran hello and listed the shared Ports profile.
Its resolved hello path matched the saved exact artifact. mojtadmin likewise
passed the user check and authenticated sudo to UID 0.

Under B, the owner changed mojtadmin's password again and created mojtnew
(UID 1002), authenticated it and wrote a home marker. Returning to A, mojtnew
logged in, retained the complete saved id output and read its B-created marker.
mojtadmin passed the user check, authenticated sudo to UID 0 and ran the same
hello artifact. The exact shared artifact throughout was
`hello@=2.12.3-nix-pa6rydwgjxxmmvdxap7qk9c85h8jbimy`.

The transcripts prove preserved later account creation, identity, home data and
working administrator authentication after return. Rejection of the superseded
administrator password was requested but has not been explicitly confirmed;
do not describe that negative test as passed. The earlier A run established
ordinary-user authorization denials and own-password changes. A separate
account-stage network/NTP regression, configured local-timezone persistence,
local graphical-VT resize behavior and deliberate recovery/mount-failure probes
are not established by these account transcripts. Root remains unlocked.
