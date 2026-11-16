<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# 6. Remote administration with SSH

A System assembled with OpenSSH support exports the upstream `sshd` and
`ssh-keygen` commands. Configure OpenSSH in `/etc/ssh/sshd_config` and manage
`sshd.service` with `systemctl`. Installing the binaries does not enable a
listener or change local authentication policy.

## 6.1. Prepare the account, host key and PAM

As root, create `/etc/sysusers.d/sshd.conf` with:

```text
u sshd - "OpenSSH privilege separation" /var/empty /bin/false
```

Run `systemd-sysusers /etc/sysusers.d/sshd.conf`. The `sshd` account is a locked
privilege-separation account, separate from the login account. Create the empty,
root-owned `/var/empty` directory with mode 0755.

Generate a machine host key if it is missing:

```sh
umask 077
mkdir -p /etc/ssh
ssh-keygen -t ed25519 -N '' -f /etc/ssh/ssh_host_ed25519_key
```

Keep an existing host key when changing generations. Its private file has mode
0600. The host key identifies the machine; it is needed for both password and
public-key login.

Create `/etc/pam.d/sshd` using System's retained PAM modules:

```text
auth required /run/mojt-system/pam/pam_unix.so
account required /run/mojt-system/pam/pam_unix.so
session required /run/mojt-system/pam/pam_loginuid.so
session required /run/mojt-system/pam/pam_unix.so
session required /run/mojt-system/pam/pam_systemd.so
```

## 6.2. Choose authentication in sshd_config

The following example explicitly permits root to log in with its existing
password. Create `/etc/ssh/sshd_config`:

```text
Port 22
ListenAddress 0.0.0.0
HostKey /etc/ssh/ssh_host_ed25519_key
AllowUsers root
PermitRootLogin yes
PasswordAuthentication yes
AuthenticationMethods password
PubkeyAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
UsePAM yes
SetEnv PATH=/run/mojt-system/bin:/var/lib/mojt/ports/current/bin:/usr/local/bin:/usr/bin:/bin
Subsystem sftp internal-sftp
```

The named login account must exist, have an executable shell and a usable
password. Change `AllowUsers` to select another existing account. No account
password is set or unlocked by writing this configuration.

For public-key login instead, use `PubkeyAuthentication yes`,
`AuthenticationMethods publickey`, `PasswordAuthentication no` and
`PermitRootLogin prohibit-password`. Put the client's public key in that
account's `~/.ssh/authorized_keys`, with the directory mode 0700 and file mode
0600 owned by the account. Client private keys stay on the client.

See the upstream [sshd_config manual](https://man.openbsd.org/sshd_config.5)
for listener and authentication settings. Configure an existing installation
deliberately; preserve local configuration and host identity.

## 6.3. Install the service and connect

Create `/etc/systemd/system/sshd.service`:

```ini
[Unit]
Description=OpenSSH server
After=network.target mojt-setup.service

[Service]
Type=simple
ExecStartPre=/run/mojt-system/bin/sshd -t -f /etc/ssh/sshd_config
ExecStart=/run/mojt-system/bin/sshd -D -e -f /etc/ssh/sshd_config
RuntimeDirectory=sshd
RuntimeDirectoryMode=0755
Restart=on-failure
KillMode=process

[Install]
WantedBy=mojt.target
```

The System binary path and boot target follow Mojt's filesystem/boot layout.
The daemon, configuration syntax and service controls are ordinary OpenSSH and
systemd. Create `/run/sshd` with mode 0755 for the initial configuration check,
then run:

```sh
sshd -t -f /etc/ssh/sshd_config
systemctl daemon-reload
systemctl enable --now sshd.service
systemctl status --no-pager sshd.service
ssh-keygen -l -f /etc/ssh/ssh_host_ed25519_key.pub
ip -brief address
```

From the client, substitute the target address:

```sh
ssh root@MOJT_ADDRESS
ssh root@MOJT_ADDRESS 'mpm system status'
sftp root@MOJT_ADDRESS
```

Compare the host-key fingerprint on first connection. For the password example,
use the existing root password. With a custom port use `ssh -p PORT` or
`sftp -P PORT`. Inspect logs with `journalctl -u sshd.service -b`.

After editing configuration, validate it with `sshd -t` and restart the service
with `systemctl restart sshd.service`. Disable its listener and boot enablement
with `systemctl disable --now sshd.service`. The unit's `KillMode=process` leaves
existing authenticated sessions running when stopping the listener; close them
explicitly when required.

## 6.4. Persistent files and long builds

Host keys and configuration under `/etc/ssh`, `/etc/pam.d/sshd`,
`/etc/sysusers.d/sshd.conf`, the service unit and its enable link persist across
compatible generation changes. `/run/sshd` is temporary and recreated by systemd.
An older System without OpenSSH cannot serve this service.

Compile Kernels as an ordinary user in a separate workspace, as described in
the [MBT chapter](../part-i/mbt.md#43-build-a-kernel-as-an-ordinary-user).
A transient system service can run a long build independently of the SSH
session. Installation and next-boot selection remain administrator operations.
