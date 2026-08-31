#!/bin/sh
set -eu

video_dir=/root/robot-platform/video
pid_file="$video_dir/rtsp.pid"
log_file="$video_dir/rtsp.log"

if test -f "$pid_file"; then
    old_pid=$(cat "$pid_file")
    if kill -0 "$old_pid" 2>/dev/null; then
        echo "RTSP_ALREADY_RUNNING pid=$old_pid"
        exit 0
    fi
    rm -f "$pid_file"
fi

nohup python3 "$video_dir/rtsp_server.py" >"$log_file" 2>&1 &
new_pid=$!
echo "$new_pid" >"$pid_file"
wait_count=0
while test "$wait_count" -lt 30; do
    if ! kill -0 "$new_pid" 2>/dev/null; then
        echo "RTSP_START_FAILED pid=$new_pid" >&2
        cat "$log_file" >&2
        rm -f "$pid_file"
        exit 1
    fi
    if grep -q '"event": "rtsp_started"' "$log_file" 2>/dev/null; then
        echo "RTSP_STARTED pid=$new_pid wait_seconds=$wait_count"
        tail -n 1 "$log_file"
        exit 0
    fi
    sleep 1
    wait_count=$((wait_count + 1))
done

echo "RTSP_START_TIMEOUT pid=$new_pid" >&2
cat "$log_file" >&2
kill "$new_pid" 2>/dev/null || true
rm -f "$pid_file"
exit 1
