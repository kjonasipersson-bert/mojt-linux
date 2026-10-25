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
        device="${MOJT_TEST_INTERFACE:-$(nmcli -t -f DEVICE,TYPE device status | sed -n 's/:ethernet$//p' | head -n 1)}"
        [ -n "$device" ] || fail "no Ethernet device; set MOJT_TEST_INTERFACE for Wi-Fi"
        # Observe NetworkManager's autoconnection without restarting it.
        # An active connection need not have finished IPv4 configuration.
        tries=0
        while :; do
            address="$(ip -4 -o address show dev "$device" scope global)"
            route="$(ip -4 route show default dev "$device")"
            if [ -n "$address" ] && [ -n "$route" ]; then break; fi
            if [ "$tries" -ge 30 ]; then
                nmcli -f GENERAL,IP4,DHCP4 device show "$device" || :
                fail "IPv4 address and default route not ready on $device after 30 seconds"
            fi
            sleep 1
            tries=$((tries + 1))
        done
        printf '%s\n%s\n' "$address" "$route"
        getent hosts cache.nixos.org
        curl --ipv4 --fail --show-error --silent --max-time 30 \
            https://cache.nixos.org/nix-cache-info
        echo "PASS: NetworkManager, IPv4, routing, DNS and HTTPS" ;;
    ports)
        boot_check
        command -v mpm >/dev/null || fail "requires a step 3 VM"
        mpm ports update --dry-run
        mpm ports update -y
        mpm ports install hello --dry-run
        mpm ports install hello -y
        hello
        lab="/var/lib/mojt/python-acceptance-$(cat /proc/sys/kernel/random/uuid)"
        /run/mojt-system/bin/python3 /run/mojt-system/tests/run-mpm-nix-python.py \
            --root "$lab" --source-manifest /run/mojt-system/ports.toml
        echo "PASS: MPM binary import, parallel Python versions and captured profile" ;;
    programs)
        boot_check
        command -v mpm >/dev/null || fail "requires a step 3 VM"
        lab="/var/lib/mojt/programs-acceptance-$(cat /proc/sys/kernel/random/uuid)"
        /run/mojt-system/bin/python3 /run/mojt-system/tests/run-mpm-nix-ports.py \
            --root "$lab" --source-manifest /run/mojt-system/ports.toml
        echo "PASS: ordinary Ports, automatic exports and historical removal fallback" ;;
    admin)
        # Check the System tools even if the interactive Ports profile shadows them.
        PATH=/run/mojt-system/bin:/usr/bin:/bin
        export PATH
        boot_check
        [ -r /run/mojt-system/admin-commands ] || fail "requires a step 4 VM"
        for name in $(cat /run/mojt-system/admin-commands); do
            [ "$(command -v "$name")" = "/run/mojt-system/bin/$name" ] ||
                fail "$name is not available from System"
        done
        [ "$(ps -p 1 -o comm=)" = systemd ] || fail "ps cannot inspect systemd PID 1"
        ps -eo pid,ppid,comm --sort=pid
        top -b -n 1 -w 80
        free -h
        pgrep -x systemd
        uptime
        lsblk -o NAME,TYPE,SIZE,FSTYPE
        findmnt --noheadings --output TARGET,FSTYPE /
        blkid --version
        less --version

        probe="$(mktemp -d /tmp/mojt-admin.XXXXXX)"
        mounted=0
        mkdir "$probe/mount"
        cleanup_admin() {
            if [ "$mounted" = 1 ]; then
                /run/mojt-system/bin/umount "$probe/mount" || {
                    echo "FAIL: temporary mount cleanup failed; retained $probe" >&2
                    return 1
                }
                mounted=0
            fi
            rm -f "$probe/editor.txt" "$probe/dmesg"
            rmdir "$probe/mount" "$probe"
        }
        trap cleanup_admin 0
        trap 'exit 1' HUP INT TERM
        dmesg --color=never >"$probe/dmesg"
        tail -n 5 "$probe/dmesg"
        mount -t tmpfs -o size=1m,nosuid,nodev mojt-admin-check "$probe/mount"
        mounted=1
        [ "$(findmnt --noheadings --output FSTYPE --mountpoint "$probe/mount")" = tmpfs ] ||
            fail "temporary tmpfs mount not visible"
        /run/mojt-system/bin/umount "$probe/mount"
        mounted=0
        ex -s "$probe/editor.txt" <<'EX'
a
Mojt System vi probe
.
wq
EX
        [ "$(cat "$probe/editor.txt")" = 'Mojt System vi probe' ] || fail "vi/ex file edit failed"
        cleanup_admin
        trap - 0 HUP INT TERM
        echo "PASS: System process, memory, disk, mount, pager and vi tools" ;;
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
        old="$(cat /etc/mojt-system-persistence-test)" || fail "cannot read /etc marker"
        var="$(cat /var/lib/mojt/system-persistence-test)" || fail "cannot read /var marker"
        [ -n "$old" ] || fail "empty persistence marker"
        [ "$old" = "$var" ] || fail "/etc and /var markers differ"
        current="$(cat /proc/sys/kernel/random/boot_id)" || fail "cannot read current boot ID"
        [ "$old" != "$current" ] || fail "a second boot is required"
        echo "PASS: both /etc and /var markers survived a different boot" ;;
    *) fail "use boot, network, ports, programs, admin, persistence-write or persistence-check" ;;
esac
