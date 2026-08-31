#!/bin/sh
set -eu

video_dir=/root/robot-platform/video
pid_file="$video_dir/rtsp.pid"

if ! test -f "$pid_file"; then
    echo "RTSP_NOT_RUNNING"
    exit 0
fi

pid=$(cat "$pid_file")
if kill -0 "$pid" 2>/dev/null; then
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
