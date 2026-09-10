#!/bin/sh
set -eu

video_dir=/root/robot-platform/video
pid_file="$video_dir/rtsp.pid"
log_file="$video_dir/rtsp.log"
service_runner="$video_dir/run_video_service.sh"

pid_matches_server() {
    candidate_pid=$1
    test -r "/proc/$candidate_pid/cmdline" || return 1
    tr '\000' ' ' <"/proc/$candidate_pid/cmdline" |
        grep -F -q "$service_runner"
}

if test -f "$pid_file"; then
    old_pid=$(cat "$pid_file")
    case "$old_pid" in
        ''|*[!0-9]*)
            echo "RTSP_STALE_PID invalid_pid_file" >&2
            rm -f "$pid_file"
            ;;
        *)
            if kill -0 "$old_pid" 2>/dev/null; then
                if pid_matches_server "$old_pid"; then
                    echo "RTSP_ALREADY_RUNNING pid=$old_pid"
                    exit 0
                fi
                echo "RTSP_STALE_PID ownership_mismatch pid=$old_pid" >&2
            fi
            rm -f "$pid_file"
            ;;
    esac
fi

for required_file in maix_runtime_status.py resource_guard.py video_service.py rtsp_server.py run_video_service.sh; do
    if ! test -f "$video_dir/$required_file"; then
        echo "RTSP_START_FAILED missing_file=$required_file" >&2
        exit 1
    fi
done

nohup "$service_runner" >"$log_file" 2>&1 &
new_pid=$!
echo "$new_pid" >"$pid_file"
wait_count=0
while test "$wait_count" -lt 30; do
    if ! kill -0 "$new_pid" 2>/dev/null; then
        if wait "$new_pid"; then
            result=1
        else
            result=$?
        fi
        echo "RTSP_START_FAILED pid=$new_pid" >&2
        cat "$log_file" >&2
        rm -f "$pid_file"
        exit "$result"
    fi
    if grep -q '"event": "rtsp_started"' "$log_file" 2>/dev/null; then
        echo "RTSP_STARTED pid=$new_pid wait_seconds=$wait_count"
        grep '"event": "rtsp_started"' "$log_file" | tail -n 1
        exit 0
    fi
    sleep 1
    wait_count=$((wait_count + 1))
done

echo "RTSP_START_TIMEOUT pid=$new_pid" >&2
cat "$log_file" >&2
if pid_matches_server "$new_pid"; then
    kill "$new_pid" 2>/dev/null || true
fi
cleanup_count=0
while pid_matches_server "$new_pid" && test "$cleanup_count" -lt 10; do
    sleep 1
    cleanup_count=$((cleanup_count + 1))
done
if pid_matches_server "$new_pid"; then
    # Keep ownership evidence so stop/status can still manage this process.
    echo "RTSP_STOP_TIMEOUT pid=$new_pid pid_file_retained" >&2
else
    rm -f "$pid_file"
fi
exit 1
