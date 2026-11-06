#!/usr/bin/env bash
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail

# Mojt Base 0.1 - self-contained Void bootstrap (x86_64, glibc)
[[ $(uname -m) == x86_64 ]] || { echo 'Only x86_64 is supported by this script.' >&2; exit 1; }

LAB="${MOJT_LAB:-$HOME/mojt-lab}"
mkdir -p "$LAB/downloads" "$LAB/tools"
LAB="$(cd "$LAB" && pwd -P)"
ROOT="$LAB/rootfs"
[[ ! -e "$ROOT" && ! -L "$ROOT" ]] || { echo "Target already exists: $ROOT" >&2; exit 1; }

# Pin the archive and hash: Void's "latest" checksum has been inconsistent.
FILE=xbps-static-static-0.60.4_1.x86_64-musl.tar.xz
SHA256=603b3c55e9cabd5af79b461b929b14e1556a443c97b5714d188681c2172d9e28
URL="https://repo-default.voidlinux.org/static/$FILE"
ARCHIVE="$LAB/downloads/$FILE"

if [[ ! -f "$ARCHIVE" ]] || ! echo "$SHA256  $ARCHIVE" | sha256sum -c --status; then
    curl -fL --retry 3 -o "$ARCHIVE" "$URL"
fi
echo "$SHA256  $ARCHIVE" | sha256sum -c -
tar -xJf "$ARCHIVE" -C "$LAB/tools"

XBPS="$LAB/tools/usr/bin/xbps-install.static"
QUERY="$LAB/tools/usr/bin/xbps-query.static"
[[ -x "$XBPS" && -x "$QUERY" ]] || { echo 'Static XBPS extraction failed.' >&2; exit 1; }

mkdir "$ROOT"
sudo env XBPS_ARCH=x86_64 "$XBPS" \
    -S -r "$ROOT" -R https://repo-default.voidlinux.org/current \
    base-files glibc dash coreutils grep sed findutils tar gzip xbps ca-certificates

sudo "$QUERY" -r "$ROOT" -l > "$LAB/base-0.1-packages.txt"
sudo chroot "$ROOT" /bin/sh -c 'echo "Mojt Base: OK"; id'
sudo du -sh "$ROOT"
echo "Package list: $LAB/base-0.1-packages.txt"
