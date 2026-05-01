#!/bin/bash

SERVICE_NAMES=("log_server" "auth_server" "api_server")
TIMEOUT=1 # seconds to wait for graceful shutdown

echo "Stopping microservices..."

for SERVICE in "${SERVICE_NAMES[@]}"; do
    echo "Stopping: $SERVICE"
    
    # Send SIGTERM (graceful shutdown)
    pkill -f "python.*$SERVICE(\.py)?$" 2>/dev/null
    
    # Wait for graceful exit
    for ((i=0; i<TIMEOUT; i++)); do
        if ! pgrep -f "python.*$SERVICE(\.py)?$" >/dev/null 2>&1; then
            echo "$SERVICE stopped gracefully"
            break
        fi
        sleep 1
    done
    
    # Force kill if still running
    if pgrep -f "python.*$SERVICE(\.py)?$" >/dev/null 2>&1; then
        pkill -9 -f "python.*$SERVICE(\.py)?$" 2>/dev/null
        echo "$SERVICE force stopped"
    fi
done