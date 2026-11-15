<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Accounts and session shutdown acceptance

Historical test/development record preserved from commit `d9197b19aa02d6cf75f4ac6f757064aaef6d1c14`.
Generation letters, private paths and dates identify these test fixtures and
observations. They do not define current commands or supported release names.

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
working administrator authentication after return. The owner subsequently
explicitly confirmed the password test: the change made under B survived the
return to A, the new password worked and the superseded password was rejected.
This is an owner-confirmed negative test, distinct from the command transcript
showing successful authentication. The earlier A run established ordinary-user
authorization denials and own-password changes. A separate
account-stage network/NTP regression, configured local-timezone persistence,
local graphical-VT resize behavior and deliberate recovery/mount-failure probes
are not established by these account transcripts. Root remains unlocked.
