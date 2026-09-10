#!/bin/sh
# Own the launcher handoff for a headless video-only runtime. If another
# project wrapper already stopped the launcher supervisor, preserve that state.
set -eu

video_dir=/root/robot-platform/video
service="$video_dir/rtsp_server.py"
launcher_exe=/maixapp/apps/launcher/launcher
supervisor_exe=/maixapp/apps/launcher/launcher_daemon
supervisor_pid=""
service_pid=""
owns_supervisor_stop=0

find_pid_by_exe() {
    target_exe=$1
    for proc_path in /proc/[0-9]*; do
        if [ "$(readlink "$proc_path/exe" 2>/dev/null || true)" = "$target_exe" ]; then
            echo "${proc_path#/proc/}"
            return 0
        fi
    done
    return 1
}

restore_supervisor() {
    if [ "$owns_supervisor_stop" = 1 ] \
        && [ -n "$supervisor_pid" ] \
        && kill -0 "$supervisor_pid" 2>/dev/null; then
        kill -CONT "$supervisor_pid" 2>/dev/null || true
    fi
}

terminate_service() {
    if [ -n "$service_pid" ] && kill -0 "$service_pid" 2>/dev/null; then
        kill -TERM "$service_pid" 2>/dev/null || true
        wait "$service_pid" 2>/dev/null || true
        service_pid=""
    fi
    exit 0
}

trap restore_supervisor EXIT
trap terminate_service HUP INT TERM

supervisor_pid="$(find_pid_by_exe "$supervisor_exe" || true)"
set -- $supervisor_pid
if [ "$#" -ne 1 ] || [ "$(readlink "/proc/$1/exe" 2>/dev/null || true)" != "$supervisor_exe" ]; then
    echo "VIDEO_START_REFUSED launcher_supervisor_unverified" >&2
    exit 3
fi
supervisor_pid=$1

supervisor_state=$(awk '{print $3}' "/proc/$supervisor_pid/stat")
case "$supervisor_state" in
    T|t)
        # Another verified runtime owner already holds the supervisor stopped.
        # Do not resume it when this video service exits.
        ;;
    *)
        kill -STOP "$supervisor_pid"
        owns_supervisor_stop=1
        ;;
esac

launcher_pid="$(find_pid_by_exe "$launcher_exe" || true)"
if [ -n "$launcher_pid" ]; then
    set -- $launcher_pid
    if [ "$#" -ne 1 ] || [ "$(readlink "/proc/$1/exe" 2>/dev/null || true)" != "$launcher_exe" ]; then
        echo "VIDEO_START_REFUSED launcher_owner_ambiguous" >&2
        exit 3
    fi
    launcher_pid=$1
    kill -TERM "$launcher_pid"
    attempt=0
    while kill -0 "$launcher_pid" 2>/dev/null && [ "$attempt" -lt 100 ]; do
        sleep 0.1
        attempt=$((attempt + 1))
    done
    if kill -0 "$launcher_pid" 2>/dev/null; then
        echo "VIDEO_START_REFUSED launcher_release_failed" >&2
        exit 3
    fi
fi

python3 -u "$service" &
service_pid=$!
if wait "$service_pid"; then
    result=0
else
    result=$?
fi
service_pid=""
exit "$result"
