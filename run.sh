#!/bin/bash

# Define the process name to check
process_name="main.py"

# Define PID file path
pid_file="run.pid"

# Check if a process with the name is already running
if pgrep -f "$process_name" > /dev/null 2>&1; then
    # Check if pid file exists
    if [ -f "$pid_file" ]; then
        # Read PID from file and attempt to kill process
        pid=$(cat "$pid_file")
        if kill -0 "$pid" > /dev/null 2>&1; then
            echo "Killing process '$process_name' with PID $pid"
            kill "$pid"
            # Restart main.py after successful kill (unchanged)
            echo "Restarting '$process_name'"
            python3 "$process_name" &
            new_pid=$!
            echo "Process '$process_name' restarted with PID $new_pid"
            echo "$new_pid" > "$pid_file"
        else
            # PID file exists but process not found (stale PID)
            echo "Process with PID $pid not found. Removing stale pid file."
            rm "$pid_file"
            # Since PID file is removed, run main.py
            echo "Starting '$process_name'"
            python3 "$process_name" &
            new_pid=$!
            echo "Process '$process_name' started with PID $new_pid"
            echo "$new_pid" > "$pid_file"
        fi
    else
        echo "Process '$process_name' is not running."
    fi
else
    # Run the Python script and save PID (unchanged)
    python3 "$process_name" &
    pid=$!
    echo "Process '$process_name' started with PID $pid"
    echo "$pid" > "$pid_file"
fi
