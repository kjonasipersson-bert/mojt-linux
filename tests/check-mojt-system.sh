#!/bin/sh
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
# Explicitly run inside the NEW Mojt VM, never on the Debian/Distrobox host.
set -eu
[ "$(id -u)" = 0 ] || [ "${1-}" = user ] || { echo "Run at the Mojt VM root console (or use user for an ordinary session)" >&2; exit 1; }
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
    diagnostics)
        PATH=/run/mojt-system/bin:/usr/bin:/bin
        LC_ALL=C
        export PATH LC_ALL
        boot_check
        [ -r /run/mojt-system/diagnostic-commands ] || fail "requires a step 7 VM"
        for name in $(cat /run/mojt-system/diagnostic-commands); do
            [ "$(command -v "$name")" = "/run/mojt-system/bin/$name" ] ||
                fail "$name is not available from System"
        done
        # Local checks do not depend on Internet ICMP forwarding in QEMU user networking.
        ping -n -c 2 -W 2 127.0.0.1
        tracepath -n -m 2 127.0.0.1
        arping -V
        dig -v
        nslookup -version
        ethtool --version
        lspci -nn
        probe="$(mktemp -d /tmp/mojt-diagnostics.XXXXXX)"
        cleanup_diagnostics() { rm -f "$probe/trace" "$probe/usb-error"; rmdir "$probe"; }
        trap cleanup_diagnostics 0
        trap 'exit 1' HUP INT TERM
        if ! lsusb -t 2>"$probe/usb-error"; then
            cat "$probe/usb-error" >&2
            fail "USB enumeration failed"
        fi
        if [ -s "$probe/usb-error" ]; then
            cat "$probe/usb-error" >&2
            fail "USB enumeration emitted diagnostics"
        fi
        ss -lntu
        release="$(uname -r)"
        [ -d "/lib/modules/$release" ] || fail "matching runtime modules missing; use hardware-profile build"
        modinfo -k "$release" ext4
        strace -o "$probe/trace" /run/mojt-system/busybox true
        grep -q 'execve(' "$probe/trace" || fail "strace did not record execve"
        grep -Fq '+++ exited with 0 +++' "$probe/trace" || fail "traced command did not exit successfully"
        cleanup_diagnostics
        trap - 0 HUP INT TERM
        echo "PASS: System diagnostics, loopback ICMP, hardware enumeration, modules and syscall tracing" ;;
    diagnostics-network)
        PATH=/run/mojt-system/bin:/usr/bin:/bin
        LC_ALL=C
        export PATH LC_ALL
        [ -r /run/mojt-system/diagnostic-commands ] || fail "requires a step 7 VM"
        /run/mojt-system/bin/mojt-system-check network
        answer="$(dig +time=3 +tries=1 +short cache.nixos.org A)"
        [ -n "$answer" ] || fail "DNS returned no answer"
        printf '%s\n' "$answer"
        nslookup -timeout=3 -retry=1 cache.nixos.org
        device="${MOJT_TEST_INTERFACE:-$(nmcli -t -f DEVICE,TYPE device status | sed -n 's/:ethernet$//p' | head -n 1)}"
        [ -n "$device" ] || fail "no interface for driver inspection"
        ethtool -i "$device"
        echo "PASS: DNS tools and network driver inspection" ;;
    accounts)
        PATH=/run/mojt-system/bin:/usr/bin:/bin
        export PATH
        boot_check
        systemctl is-active --quiet mojt-privileged.service systemd-logind.service \
            systemd-user-sessions.service mojt-account-sysctl.service || fail "account services not ready"
        visudo -c
        loginctl list-sessions --no-pager
        for name in sudo passwd; do
            [ "$(stat -c '%u:%g:%a' "/run/mojt-privileged/$name")" = 0:0:4755 ] ||
                fail "incorrect privileged helper mode: $name"
        done
        [ "$(stat -c '%u:%g:%a' /root)" = 0:0:700 ] || fail "root home is not private"
        echo "PASS: account service integration and privileged runtime (interactive authentication still required)" ;;
    user)
        PATH=/run/mojt-system/bin:/usr/bin:/bin
        export PATH
        [ "$(id -u)" -ge 1000 ] || fail "use an ordinary account, logged in through getty"
        [ -n "${XDG_SESSION_ID-}" ] || fail "missing login session"
        /run/mojt-system/bin/python3 - <<'PYTHON'
import os
from pathlib import Path
import stat
uid = os.getuid()
home = Path.home()
assert home.parent == Path("/home") and not home.is_symlink()
assert home.stat().st_uid == uid and stat.S_IMODE(home.stat().st_mode) == 0o700
runtime = Path(os.environ["XDG_RUNTIME_DIR"])
assert str(runtime) == f"/run/user/{uid}" and not runtime.is_symlink()
assert runtime.stat().st_uid == uid and stat.S_IMODE(runtime.stat().st_mode) == 0o700
assert not os.access("/etc/shadow", os.R_OK)
assert not os.access("/root", os.R_OK)
PYTHON
        loginctl show-session "$XDG_SESSION_ID" -p User -p State -p Type --no-pager
        ping -c 1 -W 2 127.0.0.1
        echo "PASS: ordinary user home, runtime, session and loopback ping (sudo tests are separate)" ;;
    environment)
        PATH=/run/mojt-system/bin:/usr/bin:/bin
        export PATH
        [ -r /run/mojt-system/manual-path ] || fail "requires a step 9 VM"
        MANPATH="$(cat /run/mojt-system/manual-path)"
        MANPAGER=cat
        export MANPATH MANPAGER
        for page in man systemctl curl ping; do
            man -w "$page" || fail "missing manual: $page"
        done
        work="$(mktemp -d /tmp/mojt-environment.XXXXXX)"
        trap 'rm -rf -- "$work"' 0 HUP INT TERM
        man --pager=cat ping >"$work/ping.txt"
        [ -s "$work/ping.txt" ] || fail "manual rendering produced no text"
        /run/mojt-system/bin/python3 - <<'PYTHON'
import datetime
import locale
from pathlib import Path
from zoneinfo import ZoneInfo
locale.setlocale(locale.LC_ALL, "C.UTF-8")
assert locale.nl_langinfo(locale.CODESET).upper() == "UTF-8"
root = Path("/run/mojt-system/zoneinfo-path").read_text().strip()
with (Path(root) / "Europe/Stockholm").open("rb") as stream:
    zone = ZoneInfo.from_file(stream)
assert datetime.datetime(2026, 1, 15, tzinfo=zone).utcoffset() == datetime.timedelta(hours=1)
assert datetime.datetime(2026, 7, 15, tzinfo=zone).utcoffset() == datetime.timedelta(hours=2)
PYTHON
        rm -rf -- "$work"
        trap - 0 HUP INT TERM
        echo "PASS: System UTF-8, Stockholm timezone data and readable manuals" ;;
    clock)
        PATH=/run/mojt-system/bin:/usr/bin:/bin
        export PATH
        boot_check
        systemctl is-active --quiet systemd-timesyncd.service || fail "timesyncd is not active"
        timedatectl timesync-status --no-pager
        [ -e /run/systemd/timesync/synchronized ] || fail "no confirmed NTP synchronization yet"
        echo "PASS: timesyncd active and synchronization confirmed" ;;
    journal-write)
        boot_check
        [ ! -e /var/lib/mojt/journal-probe-boot ] || fail "journal probe already exists"
        [ ! -L /var/lib/mojt/journal-probe-boot ] || fail "journal probe is a symlink"
        mkdir -p /var/lib/mojt
        cat /proc/sys/kernel/random/boot_id >/var/lib/mojt/journal-probe-boot
        printf 'Mojt journal persistence probe\n' | /run/mojt-system/bin/systemd-cat -t mojt-journal-probe
        journalctl --sync
        echo "Journal marker written. Power off and boot the same disk, then journal-check." ;;
    journal-check)
        boot_check
        old="$(cat /var/lib/mojt/journal-probe-boot)" || fail "journal probe missing"
        [ "$old" != "$(cat /proc/sys/kernel/random/boot_id)" ] || fail "another boot is required"
        old="$(printf '%s' "$old" | tr -d '-')"
        [ "${#old}" -eq 32 ] || fail "invalid saved journal boot ID"
        case "$old" in *[!0-9a-f]*) fail "invalid saved journal boot ID" ;; esac
        text="$(journalctl --boot="$old" --identifier=mojt-journal-probe --no-pager --output=cat)"
        printf '%s\n' "$text" | grep -Fxq 'Mojt journal persistence probe' || fail "previous boot's journal marker missing"
        journalctl --list-boots --no-pager
        journalctl --disk-usage
        echo "PASS: previous boot journal retained" ;;
    homes-write|homes-check)
        for name in home root; do
            [ "$(findmnt -n -o FSROOT -T "/$name")" = "/state/$name" ] ||
                fail "/$name is not mounted from persistent state"
        done
        if [ "$1" = homes-write ]; then
            for name in home root; do
                [ ! -e "/$name/.mojt-home-probe" ] && [ ! -L "/$name/.mojt-home-probe" ] ||
                    fail "home probe already exists in /$name"
            done
            cat /proc/sys/kernel/random/boot_id >/root/.mojt-home-probe
            cp /root/.mojt-home-probe /home/.mojt-home-probe
            sync
            echo "Home markers written. Boot the same disk again, then homes-check."
        else
            saved="$(cat /root/.mojt-home-probe)" || fail "root home probe missing"
            [ -n "$saved" ] && [ "$saved" = "$(cat /home/.mojt-home-probe)" ] ||
                fail "home markers differ"
            [ "$saved" != "$(cat /proc/sys/kernel/random/boot_id)" ] ||
                fail "another boot is required"
            echo "PASS: /home and /root markers survived a different boot"
        fi ;;
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
    *) fail "use boot, network, ports, programs, admin, diagnostics, diagnostics-network, accounts, user, environment, clock, journal-write, journal-check, homes-write, homes-check, persistence-write or persistence-check" ;;
esac
