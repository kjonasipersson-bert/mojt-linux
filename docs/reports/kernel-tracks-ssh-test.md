<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Kernel-track and SSH acceptance procedure

This test starts on the accepted writable-root I/J installation, with its
`/var/lib/mojt/usability-61/state.json` checkpoint and no pending boot choice.
It delivers a new System named `system-build-K`, retaining the original Base,
Kernel, startup/services and provider dependencies, plus the exact pinned
OpenSSH binary. It never formats a disk, edits a running manager or reboots
without a separate command. K is a local test label, not a public release name.

Functional inputs are pinned to `8e5b39c0ab0f8da7b601d0d16ceaa15740f41285`.
The helper pins a complete 84-resource MPM/MBT cohort and the earlier native
package/evidence driver. Matching installed files are reused; only missing or
changed inputs are downloaded. OpenSSH is acquired from the running System's
existing Nixpkgs pin with binary substitutes only. This maintenance delivery is
not a signed distribution release. Physical acceptance is not yet recorded.

## 1. Deliver SSH/build support

Copy the reviewed **`tools/mojt-kernel-ssh-test.py`** to
**`/root/mojt-kernel-ssh-test.py`**. As root on Mojt:

```sh
python3 /root/mojt-kernel-ssh-test.py prepare
python3 /root/mojt-kernel-ssh-test.py enter
```

Confirm the printed operations. `prepare` creates a new native System package;
`enter` imports it content-only, stages it through its checked complete installed
code using the old runtime, then selects its admitted entry. This private-code
bootstrap avoids mixed old/new imports. It does not start SSH or create keys.
On `READY`, reboot deliberately, then:

```sh
python3 /root/mojt-kernel-ssh-test.py check
```

Expect `system-build-K` running/selected and the original Kernel, with writable
root and the delivered code/resources verified.

## 2. Configure and test SSH

On the client, choose an existing SSH key or create one with OpenSSH:

```sh
ssh-keygen -t ed25519 -f mojt-test
```

Retain the private `mojt-test` file on the client. Copy only `mojt-test.pub` to
`/root/client.pub` on Mojt, for example by USB. On Mojt:

```sh
mojt-sshd configure --user root --authorized-key /root/client.pub
mojt-sshd enable
mojt-sshd status
ip -brief address
```

The helper prints the host-key fingerprint. Compare it on first connection.
From the client, replacing the address:

```sh
ssh -i mojt-test root@MOJT_ADDRESS
ssh -i mojt-test root@MOJT_ADDRESS 'mpm system status'
sftp -i mojt-test root@MOJT_ADDRESS
```

Check interactive login, the remote MPM command and one harmless file transfer.
No password login is enabled. If an ordinary administrative account is preferred,
configure that existing account instead and use sudo for privileged test actions.
Keep console access available while first establishing remote administration.

## 3. Create a build user and compiler environment

Kernel compilation runs as an ordinary user; acquisition/installation remain
administrator actions. Choose an existing user with a home, or explicitly create
a dedicated locked-password build account as root:

```sh
useradd -m -U -s /run/mojt-system/bin/bash mojtbuild
```

Do not repeat user creation if the account already exists. It needs no new login
password or SSH authorization: systemd runs the build under that UID.
Then, as root:

```sh
python3 /root/mojt-kernel-ssh-test.py environment --user mojtbuild
```

This freezes the original retained `provenance/debian.config` from the current
Kernel when available and imports the private compiler environment. If that
seed is absent, copy a reviewed x86-64 Debian `/boot/config-VERSION` to Mojt and
supply `--config /path/to/debian.config` to this action. The seed is copied with
its SHA256; it is not silently substituted by a different running configuration.
Tools are retained separately from Ports defaults. The environment is prepared
once and shared read-only by the ordinary build user. Keep ample free workspace
for source, objects and both Kernel results.

## 4. Build LTS in the background

```sh
python3 /root/mojt-kernel-ssh-test.py build --user mojtbuild --track linux-kernel-lts --jobs 2
journalctl -fu mojt-kernel-lts-build
```

Expect `STARTED`, not a completed-build PASS. The transient service runs the
public `mbt build kernel` as the chosen ordinary UID. SSH disconnect does not
cancel it. Ctrl-C leaves the journal viewer; it does not stop the build. Full
Debian configuration builds can take substantial time. Use `--jobs 1` if a lower
CPU/memory concurrency is needed. No percentage estimate is provided.

When the service finishes:

```sh
python3 /root/mojt-kernel-ssh-test.py result --track linux-kernel-lts
```

Expect build-evidence validation for **`6.18.63-mojt-lts1`**, with its Kernel and
matching modules staged together. The current Kernel is still running.
On failure, retain the workspace and journal. An eligible pre-module-staging
interruption can be continued explicitly with the original inputs:

```sh
systemctl reset-failed mojt-kernel-lts-build
python3 /root/mojt-kernel-ssh-test.py build --user mojtbuild --track linux-kernel-lts --jobs 2 --resume
```

A completed result or unsupported partial module staging is refused. Do not
remove checkpoints or force an interrupted result into installation.

## 5. Package, install and choose the built Kernel

```sh
python3 /root/mojt-kernel-ssh-test.py install --track linux-kernel-lts
python3 /root/mojt-kernel-ssh-test.py choose --track linux-kernel-lts
```

`install` packages verified build evidence and imports the exact Kernel through
public MPM. It leaves next boot unchanged. `choose` prepares/selects the new
Kernel, preserving System, Base content and the previous Kernel.

An early installation may declare an upper Kernel bound below the new recipes.
If so, the helper separately prints and requests approval for an explicit local
Base compatibility context, retaining its minimum and setting the maximum to
`7.3.999`. It uses the existing Base preparation/selection API with the **same
Base artifact**. This authorizes the requested test range; it does not prove all
versions in it or modify Base bytes. This selection can be immediately followed
by the Kernel choice without a separate policy-only reboot. Declining makes no
compatibility-policy change. Do not bypass other preflight failures.

On `READY`, reboot deliberately. Reconnect over SSH and run:

```sh
python3 /root/mojt-kernel-ssh-test.py check --track linux-kernel-lts
uname -r
mpm kernel status
mpm system status
man git
```

Expect **`6.18.63-mojt-lts1`**, exact selected/running agreement, matching modules,
unchanged System/Base content, writable root, retained SSH fingerprint/key access
and working Ports/manuals. Record actual behavior; no full new Kernel build or
physical SSH session is claimed by the automated packaging/configuration tests.

## Optional stable track and retained LTS return

After LTS works, repeat `build`, `result`, `install`, `choose`, reboot and `check`
with `--track linux-kernel`. Its separate output/service is named `stable` /
`mojt-kernel-stable-build`; expect **`7.3.4-mojt1`**. Reuse the same compiler
and seed. To return to the already prepared LTS without rebuilding:

```sh
python3 /root/mojt-kernel-ssh-test.py activate --track linux-kernel-lts
```

Reboot deliberately and run the LTS check again. Retained earlier boot entries
remain recovery choices. Older Systems without the new SSH tooling cannot serve
SSH through this local service; Kernel changes under K keep its SSH tools.

Evidence is under `/var/lib/mojt/kernel-ssh-63`; build outputs are under the
chosen user's `mojt-kernel-build` home directory. Stop on unexpected failures and
retain these files. This procedure changes no automatic upgrade wishes and
performs no garbage collection or data/schema rollback.
