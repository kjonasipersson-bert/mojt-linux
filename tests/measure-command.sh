#!/usr/bin/env bash
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
# Time one explicit command without redirecting its terminal or changing PATH.
set -euo pipefail

if (( $# < 3 )) || [[ $2 != -- ]]; then
    echo 'usage: bash measure-command.sh NEW_REPORT -- COMMAND [ARGUMENT ...]' >&2
    exit 2
fi
report=$1
shift 2
if [[ -e $report || -L $report ]]; then
    echo "Refusing existing report: $report" >&2
    exit 2
fi
previous_umask="$(umask)"
umask 077
set -o noclobber
exec {report_fd}>"$report"
set +o noclobber
umask "$previous_umask"
exec {console_error}>&2

printf 'format=mojt-command-time-v1\nstarted_utc=%s\nuid=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$EUID" >&"$report_fd"
printf 'command=' >&"$report_fd"
printf '%q ' "$@" >&"$report_fd"
printf '\n' >&"$report_fd"

# Bash writes its timing to the enclosing group's stderr. The command keeps
# the original stderr, stdin and stdout, including interactive terminal input.
TIMEFORMAT=$'wall_s=%3R\nuser_s=%3U\nsystem_s=%3S'
set +e
{ time "$@" 2>&"$console_error"; } 2>&"$report_fd"
status=$?
set -e
printf 'exit_status=%s\n' "$status" >&"$report_fd"
exec {report_fd}>&-
exec {console_error}>&-
printf '\nTiming report: %s (exit %s)\n' "$report" "$status" >&2
exit "$status"
