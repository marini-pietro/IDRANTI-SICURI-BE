@echo off
setlocal

REM Go to project root (parent of this script's directory)
cd /d "%~dp0.."

REM Use .env from project root and compose file from docker/
docker compose --env-file .env -f docker\docker-compose.yml %*
REM # docker-compose --env-file .env -f docker/docker-compose.yml "$@" (for Docker compose v1)

endlocal
