#!/bin/bash

python3 ../log_server.py &
echo "Log service started."

python3 ../auth_server.py &
echo "Auth services started."

python3 ../api_server.py &
echo "API service started."
wait