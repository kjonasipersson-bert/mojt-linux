#!/usr/bin/env bash
# Mojt Linux - Base 0.1.1 -> 0.1.2 upgrade and rollback test
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
# Test chroot only inside the privileged mount namespace.

set -euo pipefail

# Debian and other distributions may keep admin commands such as chroot
# in /usr/sbin, which is often absent from a regular user's PATH.
# The script checks for chroot in the privileged shell that actually uses it.
export PATH="/usr/local/sbin:/usr/sbin:/sbin:$PATH"

# Run as a normal user on a trusted Linux test host. sudo is used only for
# operations requiring ownership preservation or state modifications.
[[ $EUID -ne 0 ]] || { echo 'Run as a normal user, not with sudo.' >&2; exit 1; }

echo '==> Mojt Linux Base upgrade test'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
LAB="${MOJT_LAB:-$HOME/mojt-lab}"
ROOT="$LAB/rootfs"
RELEASE_011="$LAB/releases/base-0.1.1-x86_64"
RELEASE_012="$LAB/releases/base-0.1.2-x86_64"
TARGET="${MOJT_TEST_TARGET:-$LAB/upgrade-test}"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
PACK="$REPO_ROOT/tools/mojt-base-pack"
INSTALL="$REPO_ROOT/tools/mojt-base-install"
CONFIG="$REPO_ROOT/manifests/base-0.1.2.toml"

fail() { echo "mojt-base-test-upgrade: $*" >&2; exit 1; }
for tool in sudo cp tar zstd mktemp grep sha256sum; do
    command -v "$tool" >/dev/null || fail "Missing command: $tool"
done
if [[ "${MOJT_MOUNT_TEST:-1}" != 0 ]]; then
    for tool in unshare mount; do
        command -v "$tool" >/dev/null || fail "Missing command: $tool"
    done
fi
[[ -x "$PACK" && -x "$INSTALL" && -f "$CONFIG" ]] || fail 'Missing Mojt scripts or manifest beside this test script'
[[ -d "$ROOT/etc" && -f "$RELEASE_011/manifest.toml" && -f "$RELEASE_011/rootfs.tar.zst" ]] || fail 'Missing bootstrap rootfs or Base 0.1.1 release'
[[ ! -e "$TARGET" && ! -L "$TARGET" ]] || fail "Test target already exists: $TARGET (set MOJT_TEST_TARGET to use a different test directory)"

# The 0.1.2 release can be built once and reused by subsequent test runs.
if [[ ! -d "$RELEASE_012" && ! -L "$RELEASE_012" ]]; then
    echo '==> Producing Base 0.1.2 from a COPY of the bootstrap rootfs'
    TMP="$(mktemp -d "$LAB/.mojt-upgrade.XXXXXXXX")"
    cleanup() {
        if [[ -n "${TMP:-}" && "$TMP" == "$LAB"/.mojt-upgrade.* ]]; then
            sudo rm -rf -- "$TMP"
        fi
    }
    trap cleanup EXIT

    sudo mkdir -p "$TMP/rootfs"
    sudo cp -a "$ROOT/." "$TMP/rootfs/"

    # The only new vendor default in this demo: Base 0.1.1 is left untouched.
    printf 'message = "A new Mojt 0.1.2 default"\n' | \
        sudo tee "$TMP/rootfs/etc/mojt-upgrade-example.conf" >/dev/null

    extra=()
    if [[ -f "$LAB/base-0.1-packages.txt" ]]; then
        extra=(--packages "$LAB/base-0.1-packages.txt")
    fi
    sudo "$PACK" "$TMP/rootfs" "$CONFIG" "$LAB/releases" "${extra[@]}"
else
    [[ ! -L "$RELEASE_012" ]] || fail 'Refusing symlinked Base 0.1.2 release'
    echo '==> Reusing existing Base 0.1.2 release'
fi

[[ -f "$RELEASE_012/manifest.toml" && -f "$RELEASE_012/rootfs.tar.zst" ]] || fail 'Incomplete Base 0.1.2 release'
grep -Fxq 'version = "0.1.2"' "$RELEASE_012/manifest.toml" || fail 'Not a Base 0.1.2 manifest'
tar -I zstd -tf "$RELEASE_012/rootfs.tar.zst" | \
    grep -Fx './usr/etc/mojt-upgrade-example.conf' >/dev/null || fail 'Base 0.1.2 lacks the new default'
[[ ! -e "$ROOT/etc/mojt-upgrade-example.conf" ]] || fail 'Original bootstrap rootfs was modified'

echo '==> Installing Base 0.1.1 into a SEPARATE test target'
sudo "$INSTALL" install "$RELEASE_011" --target "$TARGET"

# Create two kinds of persistent state, and modify a pre-existing vendor
# default to prove the "add missing, never overwrite" /etc policy.
printf 'mojt-test-machine\n' | sudo tee "$TARGET/state/etc/hostname" >/dev/null
sudo mkdir -p "$TARGET/state/var/lib/mojt-test"
printf 'important-persistent-data\n' | sudo tee "$TARGET/state/var/lib/mojt-test/data" >/dev/null
[[ -f "$TARGET/state/etc/nsswitch.conf" ]] || fail 'Expected /etc/nsswitch.conf default missing from Base 0.1.1'
printf '# Local administrator edit: keep me\n' | \
    sudo tee -a "$TARGET/state/etc/nsswitch.conf" >/dev/null
old_hash="$(sudo sha256sum "$TARGET/state/etc/nsswitch.conf" | cut -d' ' -f1)"

check_state() {
    local expected="$1"
    [[ "$(readlink "$TARGET/base/current")" == "$expected" ]] || fail "Expected active Base $expected"
    [[ "$(cat "$TARGET/state/etc/hostname")" == 'mojt-test-machine' ]] || fail 'Hostname was changed'
    [[ "$(cat "$TARGET/state/var/lib/mojt-test/data")" == 'important-persistent-data' ]] || fail '/var state was changed'
    [[ "$(sudo sha256sum "$TARGET/state/etc/nsswitch.conf" | cut -d' ' -f1)" == "$old_hash" ]] || fail 'Locally modified nsswitch.conf was overwritten'
    [[ -f "$TARGET/state/etc/mojt-upgrade-example.conf" ]] || fail 'New vendor default missing'
    [[ "$(cat "$TARGET/state/etc/mojt-upgrade-example.conf")" == 'message = "A new Mojt 0.1.2 default"' ]] || fail 'New vendor default was modified'
}

check_chroot() {
    local expected="$1"
    if [[ "${MOJT_MOUNT_TEST:-1}" == 0 ]]; then
        echo '    Mount/chroot test skipped (MOJT_MOUNT_TEST=0)'
        return
    fi
    # Mount operations are confined to a new mount namespace. No persistent
    # host mounts are created. /etc and /var stay outside the Base generation.
    sudo unshare --mount --propagation private bash -se -- "$TARGET" "$expected" <<'INNER'
set -euo pipefail
target="$1"
expected="$2"
root="$target/base/current"
mount --bind "$target/state/etc" "$root/etc"
mount --bind "$target/state/var" "$root/var"
# chroot is only required in this root shell, not the caller's PATH.
command -v chroot >/dev/null || { echo "Missing chroot in root PATH: $PATH" >&2; exit 1; }
chroot "$root" /bin/sh -ec '
    . /etc/os-release
    test "$ID" = mojt
    test "$VERSION_ID" = "$1"
    test "$(cat /etc/hostname)" = mojt-test-machine
    test "$(cat /var/lib/mojt-test/data)" = important-persistent-data
    test -r /etc/mojt-upgrade-example.conf
' _ "$expected"
INNER
}

echo '==> Installing and activating Base 0.1.2'
sudo "$INSTALL" install "$RELEASE_012" --target "$TARGET"
check_state 0.1.2
check_chroot 0.1.2
echo '    Upgrade: PASS (/etc and /var preserved; new default added)'

echo '==> Rolling back to Base 0.1.1'
sudo "$INSTALL" activate 0.1.1 --target "$TARGET"
check_state 0.1.1
check_chroot 0.1.1
echo '    Rollback: PASS (/etc and /var still preserved)'

echo
sudo "$INSTALL" status --target "$TARGET"
echo 'Mojt Base upgrade/rollback test: PASS'
echo "Test installation: $TARGET"
echo "Release: $RELEASE_012"
