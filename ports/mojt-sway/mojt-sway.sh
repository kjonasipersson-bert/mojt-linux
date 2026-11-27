#!@shell@
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only

if [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ] ||
   { [ -n "${XDG_RUNTIME_DIR:-}" ] && [ -S "$XDG_RUNTIME_DIR/bus" ]; }; then
    exec @sway@ "$@"
fi

exec @dbus@/bin/dbus-run-session \
    --config-file=@dbus@/share/dbus-1/session.conf -- @sway@ "$@"
