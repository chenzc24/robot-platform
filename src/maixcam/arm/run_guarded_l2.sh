#!/bin/sh
set -eu

UART_DEVICE=/dev/ttyS0
LAUNCHER_EXE=/maixapp/apps/launcher/launcher
SUPERVISOR_EXE=/maixapp/apps/launcher/launcher_daemon
PROBE=/root/robot-platform/arm/l2_probe.py
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
    echo '{"ok":false,"state":"fault","error_code":"launcher_supervisor_unverified","motion_enabled":false}'
    exit 1
fi
supervisor_pid="$1"

owner_pids="$(fuser "$UART_DEVICE" 2>/dev/null || true)"
set -- $owner_pids
if [ "$#" -ne 1 ]; then
    echo '{"ok":false,"state":"fault","error_code":"uart_owner_unverified","motion_enabled":false}'
    exit 1
fi
owner_pid="$1"
if [ "$(readlink "/proc/$owner_pid/exe" 2>/dev/null || true)" != "$LAUNCHER_EXE" ]; then
    echo '{"ok":false,"state":"fault","error_code":"uart_owner_not_launcher","motion_enabled":false}'
    exit 1
fi

kill -STOP "$supervisor_pid"
kill -TERM "$owner_pid"

attempt=0
current_owner="$(fuser "$UART_DEVICE" 2>/dev/null || true)"
while [ -n "$current_owner" ] && [ "$attempt" -lt 10 ]; do
    sleep 0.1
    attempt=$((attempt + 1))
    current_owner="$(fuser "$UART_DEVICE" 2>/dev/null || true)"
done
set -- $current_owner
if [ "$#" -gt 0 ]; then
    if [ "$#" -ne 1 ] || [ "$1" != "$owner_pid" ]; then
        echo '{"ok":false,"state":"fault","error_code":"uart_owner_changed","motion_enabled":false}'
        exit 1
    fi
    if [ "$(readlink "/proc/$owner_pid/exe" 2>/dev/null || true)" != "$LAUNCHER_EXE" ]; then
        echo '{"ok":false,"state":"fault","error_code":"launcher_identity_changed","motion_enabled":false}'
        exit 1
    fi
    kill -KILL "$owner_pid"
    attempt=0
    current_owner="$(fuser "$UART_DEVICE" 2>/dev/null || true)"
    while [ -n "$current_owner" ] && [ "$attempt" -lt 20 ]; do
        sleep 0.1
        attempt=$((attempt + 1))
        current_owner="$(fuser "$UART_DEVICE" 2>/dev/null || true)"
    done
fi
if [ -n "$current_owner" ]; then
    echo '{"ok":false,"state":"fault","error_code":"launcher_did_not_stop","motion_enabled":false}'
    exit 1
fi
if fuser "$UART_DEVICE" >/dev/null 2>&1; then
    echo '{"ok":false,"state":"fault","error_code":"uart_still_busy","motion_enabled":false}'
    exit 1
fi

python3 "$PROBE" --device "$UART_DEVICE" --baud 115200 --timeout 1.0
