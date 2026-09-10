#!/bin/sh
set -eu

video_dir=/root/robot-platform/video
pid_file="$video_dir/rtsp.pid"
log_file="$video_dir/rtsp.log"
service_runner="$video_dir/run_video_service.sh"

if ! test -f "$pid_file"; then
    echo "RTSP_NOT_RUNNING"
    exit 1
fi

pid=$(cat "$pid_file")
case "$pid" in
    ''|*[!0-9]*)
        echo "RTSP_NOT_RUNNING invalid_pid_file"
        exit 1
        ;;
esac

if ! kill -0 "$pid" 2>/dev/null; then
    echo "RTSP_NOT_RUNNING stale_pid=$pid"
    exit 1
fi

if ! test -r "/proc/$pid/cmdline" ||
    ! tr '\000' ' ' <"/proc/$pid/cmdline" | grep -F -q "$service_runner"; then
    echo "RTSP_NOT_RUNNING ownership_mismatch=$pid"
    exit 1
fi

echo "RTSP_RUNNING pid=$pid"
if test -f "$log_file"; then
    grep '"event": "rtsp_' "$log_file" | tail -n 1 || true
fi
