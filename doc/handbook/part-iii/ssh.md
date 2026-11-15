<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# 6. Remote administration with SSH

A System assembled with OpenSSH support exports `sshd`, `ssh-keygen` and
`mojt-sshd`. Merely installing that System does not create host keys, change
accounts or start a listener. Older Systems without these tools need an explicit
System update before this procedure.

## 6.1. Configure one account and public key

On the client, create or choose an SSH key. Copy **only the public `.pub` file**
to Mojt, for example by USB. Keep the private key on the client. On Mojt, as root:

```sh
mojt-sshd configure --user root --authorized-key /root/client.pub
```

The named account must already exist and have an installed executable shell.
The helper permits one explicit account, public-key authentication and SFTP.
Passwords and keyboard-interactive login are disabled; root is permitted only
with a public key. PAM supplies account/session handling through System's retained
modules. No password is created, replaced or unlocked.

The default listener is IPv4 `0.0.0.0:22`. Supply `--listen ADDRESS` and `--port N`
when a different explicit binding is wanted. Configuration does not change the
firewall or router. Agent/TCP forwarding and user-supplied environment files are
disabled; remote command PATH includes System, Ports and local/Base utilities.

Configuration creates a locked privilege-separation account through
`systemd-sysusers`, verifies an empty root-owned `/var/empty`, generates a host
key only if missing, validates the configuration and reloads unit definitions.
Existing different configuration is refused rather than overwritten. Individual
completed setup effects remain after failure and can be inspected/retried.

## 6.2. Enable and connect

`configure` prints the host-key fingerprint. Compare it with the fingerprint
shown by the client on the first connection. Then explicitly start the service:

```sh
mojt-sshd enable
mojt-sshd status
```

This starts `mojt-sshd.service` now and enables it for subsequent boots. From the
client, substituting the target address:

```sh
ssh root@MOJT_ADDRESS
ssh root@MOJT_ADDRESS 'mpm system status'
sftp root@MOJT_ADDRESS
```

The client must use the private key corresponding to the configured public key.
With a custom port use `ssh -p PORT` or `sftp -P PORT`. Inspect service diagnostics
with `journalctl -u mojt-sshd.service -b`. Disable remote access explicitly with:

```sh
mojt-sshd disable
```

This stops the listener and its boot enablement. Existing authenticated sessions
are not automatically terminated; log out or use the account/session tools to
close them explicitly.

## 6.3. What persists

| Path | Purpose |
| --- | --- |
| `/etc/ssh/mojt/ssh_host_ed25519_key` and `.pub` | Machine host identity; private key mode 0600 |
| `/etc/ssh/mojt/authorized_keys/USER` | Explicit authorized public key, root-owned |
| `/etc/ssh/mojt/sshd_config` | Local listener/account/authentication settings |
| `/etc/pam.d/sshd` | Local session/account policy using retained System PAM modules |
| `/etc/systemd/system/mojt-sshd.service` and its enable link | Local service configuration |
| `/run/sshd` | Temporary runtime directory, recreated by systemd |

These `/etc` files and host keys survive compatible System/Kernel changes.
Repeating the same setup preserves the host key. Deliberate key rotation or
settings changes require inspecting/managing the local files; the helper does
not silently replace them. An older System lacking OpenSSH cannot run this
service; retaining a recovery entry does not add SSH support to that entry.

## 6.4. Long Kernel builds

Compile as an ordinary user in a separate workspace, as described in the
[MBT chapter](../part-i/mbt.md#43-build-a-kernel-as-an-ordinary-user). A transient
system service can run the build independently of the SSH session. Start it as
an administrator with explicit user, home, environment and input/output paths;
follow its journal and inspect `kernel.json` only after successful completion.
Disconnecting SSH does not cancel such a service. Installation and next-boot
selection remain separate administrator operations after the build.
