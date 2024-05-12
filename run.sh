#!/bin/bash

get_script_dir() {
    script_dir=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
}

# Call the function to get the script directory
get_script_dir

# Define the process name to check
process_name="$script_dir/main.py"

# Define PID file path
pid_file="$script_dir/run.pid"

# Function to start the process and write PID
start_process() {
    # Activate the virtual environment
    source "$script_dir/env/bin/activate"
    
    # Run the Python script within the activated venv
    python "$process_name" &
    new_pid=$!
    echo "Process '$process_name' started with PID $new_pid"
    echo "$new_pid" > "$pid_file"
    
    # Deactivate the virtual environment
    deactivate
}

# Check if process with the name is already running
if pgrep -f "$process_name" > /dev/null 2>&1; then
    # Check PID file and handle stale PID
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        if ! kill -0 "$pid" > /dev/null 2>&1; then
            echo "Process with PID $pid not found. Removing stale pid file."
            rm "$pid_file"
            # Call start_process here to launch the process after removing stale PID
            start_process
        fi
    fi
    
    # Process already running (or stale PID removed)
    echo "Process '$process_name' is already running."
else
    # Start the process using the function
    start_process
fi
