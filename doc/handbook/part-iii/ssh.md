<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# 6. Remote administration with SSH

The installed System provides OpenSSH as `sshd.service`. The service is
disabled by default. Its supplied configuration accepts public-key logins for
ordinary accounts and disables password and root logins.

Boot the installed system and follow [Network configuration](networking.md).
Use `systemctl cat sshd.service` to check the installed unit. Images made
before the service was bundled supply the OpenSSH commands separately.
The current System upgrade path preserves the existing service layout.

## 6.1. Authorize a client key

Choose an ordinary local account for SSH. If the installation only has root,
create an account from the local root console. Replace `LOGIN_NAME` with the
chosen username. The password here lets the account log in at the local console.

```sh
useradd -m LOGIN_NAME
passwd LOGIN_NAME
```

On the client, use an existing key pair or create one with
`ssh-keygen -t ed25519`. At the Mojt console, log in as the chosen account and
append the contents of the client's `.pub` file as a line in
`~/.ssh/authorized_keys`. Keep the private key on the client.

```sh
install -d -m 0700 ~/.ssh
vi ~/.ssh/authorized_keys
chmod 0600 ~/.ssh/authorized_keys
```

## 6.2. Start the service and connect

From the local root console, enable the service for this boot and future boots.
The first start supplies missing configuration and creates the machine's host
key. Print its fingerprint and find the address to use from the client.

```sh
systemctl enable --now sshd.service
systemctl status --no-pager sshd.service
ssh-keygen -l -f /etc/ssh/ssh_host_ed25519_key
ip -brief address
```

From the client, use the account name and Mojt's network address. On the first
connection, compare the fingerprint with the one printed at Mojt's console.

```sh
ssh LOGIN_NAME@MOJT_ADDRESS
sftp LOGIN_NAME@MOJT_ADDRESS
```

Use `ssh -i PATH_TO_PRIVATE_KEY LOGIN_NAME@MOJT_ADDRESS` to select a key at a
custom path. Inspect server logs with `journalctl -b -u sshd.service`.

## 6.3. Change local policy

The supplied `/etc/ssh/sshd_config` reads drop-ins from
`/etc/ssh/sshd_config.d/` before its default settings. Add `AllowUsers` to a
drop-in to limit SSH to specific accounts, or set `ListenAddress` to bind to
a particular interface address. See the [sshd_config manual](https://man.openbsd.org/sshd_config.5).

On a trusted local test network that requires root password login, save the
following in `/etc/ssh/sshd_config.d/10-local-test.conf`. Create the drop-in
directory if needed. Use the root password set during installation.

```text
AllowUsers root
PermitRootLogin yes
PasswordAuthentication yes
AuthenticationMethods password
```

After changing the configuration, validate it while the service is running,
then restart it from the local console.

```sh
sshd -t -f /etc/ssh/sshd_config &&
  systemctl restart sshd.service
```

Use `systemctl disable --now sshd.service` to stop accepting new connections
and disable the service at boot. Existing authenticated sessions stay open
until closed.

## 6.4. Persistent files and long builds

Host keys, authorized keys, local configuration and boot enablement persist
across compatible generation changes. An existing local
`/etc/systemd/system/sshd.service` has priority over the System unit.
`systemctl cat sshd.service` shows which unit is in use.

Compile Kernels under your existing account in a separate workspace, as described in
the [MBT chapter](../part-i/mbt.md#43-build-a-kernel-as-an-ordinary-user).
A transient system service can run a long build independently of the SSH
session. Installation and next-boot selection remain administrator operations.
