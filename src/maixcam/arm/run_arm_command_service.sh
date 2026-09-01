#!/bin/sh
# Start the arm endpoint only after proving that launcher currently owns UART0.
# The trap resumes the verified launcher supervisor on every exit path.
set -eu

UART_DEVICE=/dev/ttyS0
LAUNCHER_EXE=/maixapp/apps/launcher/launcher
SUPERVISOR_EXE=/maixapp/apps/launcher/launcher_daemon
SERVICE=/root/robot-platform/arm/arm_command_server.py
supervisor_pid=""

restore_supervisor() {
    if [ -n "$supervisor_pid" ] && kill -0 "$supervisor_pid" 2>/dev/null; then
        kill -CONT "$supervisor_pid" 2>/dev/null || true
    fi
}

trap restore_supervisor EXIT HUP INT TERM

supervisor_pid="$(pidof launcher_daemon 2>/dev/null || true)"
set -- $supervisor_pid
if [ "$#" -ne 1 ] || [ "$(readlink "/proc/$1/exe" 2>/dev/null || true)" != "$SUPERVISOR_EXE" ]; then
    echo '{"ok":false,"error_code":"launcher_supervisor_unverified","motion_enabled":false}'
    exit 1
fi
supervisor_pid="$1"

owner_pids="$(fuser "$UART_DEVICE" 2>/dev/null || true)"
set -- $owner_pids
if [ "$#" -ne 1 ] || [ "$(readlink "/proc/$1/exe" 2>/dev/null || true)" != "$LAUNCHER_EXE" ]; then
    echo '{"ok":false,"error_code":"uart_owner_unverified","motion_enabled":false}'
    exit 1
fi
owner_pid="$1"

kill -STOP "$supervisor_pid"
kill -TERM "$owner_pid"
attempt=0
while fuser "$UART_DEVICE" >/dev/null 2>&1 && [ "$attempt" -lt 20 ]; do
    sleep 0.1
    attempt=$((attempt + 1))
done
if fuser "$UART_DEVICE" >/dev/null 2>&1; then
    echo '{"ok":false,"error_code":"uart_release_failed","motion_enabled":false}'
    exit 1
fi

python3 "$SERVICE"
