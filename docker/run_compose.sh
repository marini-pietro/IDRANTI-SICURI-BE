#!/usr/bin/env bash
set -e

# Go to project root (parent of this script's directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# Use .env from project root and compose file from docker/
docker compose --env-file .env -f docker/docker-compose.yml "$@"
# docker-compose --env-file .env -f docker/docker-compose.yml "$@" (for Docker compose v1)
