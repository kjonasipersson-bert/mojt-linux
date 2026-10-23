#!/bin/sh
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
# Explicitly run inside the NEW Mojt VM, never on the Debian/Distrobox host.
set -eu
[ "$(id -u)" = 0 ] || { echo "Run at the Mojt VM root console" >&2; exit 1; }
[ -f /run/mojt-system/record.json ] || { echo "Not the System experiment VM" >&2; exit 1; }
. /run/mojt-system/environment
fail() { echo "FAIL: $*" >&2; exit 1; }
boot_check() {
    [ "$(cat /proc/1/comm)" = systemd ] || fail "PID 1 is not systemd"
    for service in mojt-setup.service mojt-console.service \
        systemd-journald.service systemd-udevd.service; do
        systemctl is-active --quiet "$service" || fail "$service is not active"
    done
    failed="$(systemctl --failed --no-legend --plain)"
    [ -z "$failed" ] || { printf '%s\n' "$failed"; fail "failed units"; }
    test -w /etc && test -w /var || fail "persistent state is not writable"
    journalctl -b -n 5 --no-pager
    echo "PASS: systemd PID 1, console, udev and journal"
}
action=boot
if [ "$#" -gt 0 ]; then action="$1"; fi
case "$action" in
    boot) boot_check ;;
    network)
        boot_check
        for service in dbus.service NetworkManager.service; do
            systemctl is-active --quiet "$service" || fail "$service is not active"
        done
        device="$(nmcli -t -f DEVICE,TYPE device status | sed -n 's/:ethernet$//p' | head -n 1)"
        [ -n "$device" ] || fail "no Ethernet device"
        nmcli --wait 30 device connect "$device"
        address="$(nmcli -g IP4.ADDRESS device show "$device")"
        [ -n "$address" ] || fail "no IPv4 address"
        route="$(ip -4 route show default)"
        [ -n "$route" ] || fail "no default route"
        printf '%s\n%s\n' "$address" "$route"
        getent hosts cache.nixos.org
        curl --fail --show-error --silent --max-time 30 \
            https://cache.nixos.org/nix-cache-info
        echo "PASS: NetworkManager, IPv4, routing, DNS and HTTPS" ;;
    ports)
        boot_check
        command -v mpm >/dev/null || fail "requires a step 3 VM"
        mpm update --manifest /run/mojt-system/ports.toml --dry-run
        mpm update --manifest /run/mojt-system/ports.toml -y
        mpm install --dry-run
        mpm install -y
        /var/lib/mojt/ports/current/bin/hello
        lab="/var/lib/mojt/python-acceptance-$(cat /proc/sys/kernel/random/uuid)"
        python3 /run/mojt-system/tests/run-mpm-nix-python.py \
            --root "$lab" --source-manifest /run/mojt-system/ports.toml
        echo "PASS: MPM binary import, parallel Python versions and captured profile" ;;
    persistence-write)
        [ ! -e /etc/mojt-system-persistence-test ] || fail "test marker already exists"
        [ ! -L /etc/mojt-system-persistence-test ] || fail "test marker is a symlink"
        [ ! -e /var/lib/mojt/system-persistence-test ] || fail "test marker already exists"
        [ ! -L /var/lib/mojt/system-persistence-test ] || fail "test marker is a symlink"
        mkdir -p /var/lib/mojt
        cat /proc/sys/kernel/random/boot_id >/etc/mojt-system-persistence-test
        cp /etc/mojt-system-persistence-test /var/lib/mojt/system-persistence-test
        sync
        echo "Markers written. Run systemctl poweroff, start the SAME disk, then persistence-check." ;;
    persistence-check)
        cmp /etc/mojt-system-persistence-test /var/lib/mojt/system-persistence-test
        old="$(cat /etc/mojt-system-persistence-test)"
        current="$(cat /proc/sys/kernel/random/boot_id)"
        [ "$old" != "$current" ] || fail "a second boot is required"
        echo "PASS: both /etc and /var markers survived a different boot" ;;
    *) fail "use boot, network, ports, persistence-write or persistence-check" ;;
esac
