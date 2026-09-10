#!/bin/sh
set -eu

video_dir=/root/robot-platform/video
pid_file="$video_dir/rtsp.pid"
service_runner="$video_dir/run_video_service.sh"

pid_matches_server() {
    candidate_pid=$1
    test -r "/proc/$candidate_pid/cmdline" || return 1
    tr '\000' ' ' <"/proc/$candidate_pid/cmdline" |
        grep -F -q "$service_runner"
}

if ! test -f "$pid_file"; then
    echo "RTSP_NOT_RUNNING"
    exit 0
fi

pid=$(cat "$pid_file")
case "$pid" in
    ''|*[!0-9]*)
        echo "RTSP_STOP_REFUSED invalid_pid_file" >&2
        rm -f "$pid_file"
        exit 1
        ;;
esac

if kill -0 "$pid" 2>/dev/null; then
    if ! pid_matches_server "$pid"; then
        echo "RTSP_STOP_REFUSED ownership_mismatch pid=$pid" >&2
        rm -f "$pid_file"
        exit 1
    fi
    kill "$pid"
    wait_count=0
    while kill -0 "$pid" 2>/dev/null && test "$wait_count" -lt 10; do
        sleep 1
        wait_count=$((wait_count + 1))
    done
    if kill -0 "$pid" 2>/dev/null; then
        echo "RTSP_STOP_TIMEOUT pid=$pid" >&2
        exit 1
    fi
fi

rm -f "$pid_file"
echo "RTSP_STOPPED pid=$pid"
