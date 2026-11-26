<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# 6. Remote administration with SSH

The System included in the current installation image provides OpenSSH's
`sshd` and `ssh-keygen`. Remote login is disabled until you configure the
server and enable `sshd.service`. The password chosen during installation
is for the local console unless you explicitly allow password login over SSH.

Boot the installed system, log in locally as root, and follow
[Network configuration](networking.md) to bring up the network. Check that the
running System provides both OpenSSH commands.

```sh
ls -l /run/mojt-system/bin/sshd /run/mojt-system/bin/ssh-keygen
```

If these paths are missing, boot a System that includes OpenSSH before
continuing. Use the steps below for a fresh SSH setup. On a machine that
already has SSH configured, review its configuration and keep its host keys.

## 6.1. Prepare the account, host key and PAM

As root, prepare the directories used by the server. OpenSSH requires
`/var/empty` to be empty and owned by root.

```sh
install -d -m 0755 /etc/ssh /etc/pam.d /etc/sysusers.d /etc/systemd/system /var/empty
```

Save this line in `/etc/sysusers.d/sshd.conf`.

```text
u sshd - "OpenSSH privilege separation" /var/empty /bin/false
```

Create the locked privilege-separation account.

```sh
systemd-sysusers /etc/sysusers.d/sshd.conf
```

If the machine has no Ed25519 host key yet, generate one.

```sh
/run/mojt-system/bin/ssh-keygen -t ed25519 -N '' -f /etc/ssh/ssh_host_ed25519_key
```

The host key identifies the machine to clients. Keep its private file at
mode 0600 and retain the key across generation changes.

Save the following as `/etc/pam.d/sshd` to use the running System's PAM modules.

```text
auth required /run/mojt-system/pam/pam_unix.so
account required /run/mojt-system/pam/pam_unix.so
session required /run/mojt-system/pam/pam_loginuid.so
session required /run/mojt-system/pam/pam_unix.so
session required /run/mojt-system/pam/pam_systemd.so
```

## 6.2. Choose authentication in sshd_config

This example allows root to log in with a public key. On the client, use an
existing key pair or generate one with `ssh-keygen -t ed25519`. On Mojt, create
the account's `.ssh` directory, then add the contents of the client's `.pub`
file as a line in `/root/.ssh/authorized_keys`. Keep the private key on the
client.

```sh
install -d -m 0700 /root/.ssh
vi /root/.ssh/authorized_keys
chmod 0600 /root/.ssh/authorized_keys
```

Save the following as `/etc/ssh/sshd_config`.

```text
Port 22
ListenAddress 0.0.0.0
HostKey /etc/ssh/ssh_host_ed25519_key
AllowUsers root
PermitRootLogin prohibit-password
PubkeyAuthentication yes
AuthenticationMethods publickey
AuthorizedKeysFile .ssh/authorized_keys
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
UsePAM yes
SetEnv PATH=/run/mojt-system/bin:/var/lib/mojt/ports/current/bin:/usr/local/bin:/usr/bin:/bin
Subsystem sftp internal-sftp
```

For an ordinary local account, set `AllowUsers` to that account and set
`PermitRootLogin no`. Put `authorized_keys` in that account's home directory
with the same permissions and ensure the account owns both `.ssh` and the file.
The account must have an executable login shell.

For password login as root on a trusted local test network, replace the four
authentication settings below. Use the existing root password chosen during
installation.

```text
PermitRootLogin yes
PubkeyAuthentication no
AuthenticationMethods password
PasswordAuthentication yes
```

The example listens on all IPv4 interfaces. To restrict where SSH accepts
connections, see the [sshd_config manual](https://man.openbsd.org/sshd_config.5).

## 6.3. Install the service and connect

Save this unit as `/etc/systemd/system/sshd.service`.

```ini
[Unit]
Description=OpenSSH server
After=network.target mojt-setup.service systemd-logind.service

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

Create the temporary runtime directory for the first configuration check.
If the check passes, enable the service for future boots and start it now.

```sh
install -d -m 0755 /run/sshd
/run/mojt-system/bin/sshd -t -f /etc/ssh/sshd_config &&
  systemctl daemon-reload &&
  systemctl enable --now sshd.service
systemctl status --no-pager sshd.service
/run/mojt-system/bin/ssh-keygen -l -f /etc/ssh/ssh_host_ed25519_key.pub
ip -4 -brief address
```

From the client, use the IPv4 address of Mojt's network interface. Compare the
fingerprint on the first connection with the one printed at the local console.

```sh
ssh root@MOJT_ADDRESS
ssh root@MOJT_ADDRESS 'mpm system status'
sftp root@MOJT_ADDRESS
```

Replace `root` if you configured another account. With a custom port use
`ssh -p PORT` or `sftp -P PORT`. To select a client key at a custom path, use
`ssh -i PATH_TO_PRIVATE_KEY`. Inspect logs with `journalctl -u sshd.service -b`.

After editing the configuration, validate it before restarting the service.

```sh
/run/mojt-system/bin/sshd -t -f /etc/ssh/sshd_config &&
  systemctl restart sshd.service
```

Use `systemctl disable --now sshd.service` to stop the listener and disable it
at boot. With `KillMode=process`, existing authenticated sessions continue
running when the listener stops.

## 6.4. Persistent files and long builds

Host keys and configuration under `/etc/ssh`, `/etc/pam.d/sshd`,
`/etc/sysusers.d/sshd.conf`, the service unit and its enable link persist across
compatible generation changes. The login account's `authorized_keys` is also
persistent. Systemd recreates `/run/sshd` each time the service starts.

Compile Kernels under your existing account in a separate workspace, as described in
the [MBT chapter](../part-i/mbt.md#43-build-a-kernel-as-an-ordinary-user).
A transient system service can run a long build independently of the SSH
session. Installation and next-boot selection remain administrator operations.
