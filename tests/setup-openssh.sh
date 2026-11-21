#!/bin/sh
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
# One-time test-machine setup: ordinary OpenSSH files and sshd.service.
set -eu
export PATH=/run/mojt-system/bin:/usr/local/bin:/usr/bin:/bin
[ "$(id -u)" = 0 ] || { echo "Run as root on the Mojt test machine." >&2; exit 1; }
for program in sshd ssh-keygen systemd-sysusers systemctl; do
    [ -x "/run/mojt-system/bin/$program" ] || { echo "Missing System tool: $program" >&2; exit 1; }
done
# Refuse existing local policy, including the earlier experimental setup.
for file in /etc/ssh/sshd_config /etc/pam.d/sshd /etc/sysusers.d/sshd.conf /etc/systemd/system/sshd.service /etc/ssh/mojt/managed.json; do
    if [ -e "$file" ] || [ -L "$file" ]; then
        echo "Existing SSH configuration: $file. Inspect it instead of overwriting it." >&2
        exit 1
    fi
done
umask 077
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
install -d -m 0755 /etc/ssh /etc/pam.d /etc/sysusers.d /etc/systemd/system /run/sshd /var/empty
cat >"$work/sshd.conf" <<'EOF'
u sshd - "OpenSSH privilege separation" /var/empty /bin/false
EOF
install -m 0644 "$work/sshd.conf" /etc/sysusers.d/sshd.conf
systemd-sysusers /etc/sysusers.d/sshd.conf
if [ ! -e /etc/ssh/ssh_host_ed25519_key ]; then
    [ ! -e /etc/ssh/ssh_host_ed25519_key.pub ] || { echo "Incomplete existing host key." >&2; exit 1; }
    ssh-keygen -q -t ed25519 -N '' -f /etc/ssh/ssh_host_ed25519_key
fi
cat >"$work/sshd_config" <<'EOF'
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
EOF
cat >"$work/sshd.pam" <<'EOF'
auth required /run/mojt-system/pam/pam_unix.so
account required /run/mojt-system/pam/pam_unix.so
session required /run/mojt-system/pam/pam_loginuid.so
session required /run/mojt-system/pam/pam_unix.so
session required /run/mojt-system/pam/pam_systemd.so
EOF
cat >"$work/sshd.service" <<'EOF'
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
EOF
/run/mojt-system/bin/sshd -t -f "$work/sshd_config"
install -m 0600 "$work/sshd_config" /etc/ssh/sshd_config
install -m 0644 "$work/sshd.pam" /etc/pam.d/sshd
install -m 0644 "$work/sshd.service" /etc/systemd/system/sshd.service
systemctl daemon-reload
systemctl enable --now sshd.service
ssh-keygen -l -f /etc/ssh/ssh_host_ed25519_key.pub
systemctl status --no-pager sshd.service
echo "OpenSSH ready. Connect with ssh root@ADDRESS and the existing root password."
