# Docker Configuration for IDRANTI SICURI

This directory contains all Docker-related configuration files for the IDRANTI SICURI backend application.

## Files Overview

### `docker-compose.yml`
**Purpose:** Orchestrates all services (API, Auth, Log and database)

**What it does:**
- Defines 4 services: PostgreSQL database, API server, Auth server and log server
- Sets up networking so services can communicate
- Manages volumes for data persistence
- Configures environment variables
- Sets up health checks and startup dependencies

**Key concepts explained:**
- **Services:** Each service is a separate container only with its respective depencies
- **Networks:** Custom bridge network allows services to reach each other by name (e.g., `db` instead of localhost)
- **Volumes:** Persist data across container restarts
- **depends_on:** Controls startup order and waits for dependencies
- **environment:** Inject configuration from `.env` file

---

### `Dockerfile.api`
**Purpose:** Blueprint for building the API server Docker image

**What it does:**
- Starts with Python 3.11 slim base image
- Installs system dependencies (PostgreSQL client, C compiler, etc.)
- Installs Python packages from api_requirements.txt
- Copies application code
- Sets up health check
- Configures startup command

**When it's used:**
- Docker Compose builds this when you run `docker-compose up` for the first time
- Each service gets its own Dockerfile (named Dockerfile.{service}: Dockerfile.api, Dockerfile.auth, Dockerfile.log)

---

### `Dockerfile.auth`
**Purpose:** Blueprint for building the Auth server Docker image

**Structure:** Same as Dockerfile.api, differing only in:
- Input: Installs Python packages from `auth_requirements.txt`
- Output: Creates image for auth server instead of API
- Startup command: Runs `auth_server.py` instead of `api_server.py`

---

### `Dockerfile.log`
**Purpose:** Blueprint for building the Log server Docker image

**Structure:** Same as Dockerfile.api, differing only in:
- Startup command: Runs `log_server.py` instead of `api_server.py`

---

### `.dockerignore`
**Purpose:** Specifies which files to exclude from Docker image builds

**Why it matters:**
- Keeps images lean and fast to build
- Excludes development artifacts (__pycache__, .git, etc.)
- Prevents sensitive files from being included (.env, virtual environments)
- Similar to .gitignore but for Docker

**What's excluded:**
- Python cache files (`__pycache__`, `*.pyc`)
- Git repository (`.git/`)
- Development environments (`venv/`, `env/`)
- Test files
- Local `.env` file (security!)

---

### `.env.example`
**Purpose:** Template for environment variables needed by all services

**What it contains:**
- Database credentials (username, password, connection URL)
- API server settings (host, port, debug mode)
- JWT/authentication configuration (secret key, expiry times)
- Optional settings (SSL, logging, rate limiting)

**How to use:**
```bash
# Copy to .env (in project root or docker/ folder)
cp docker/.env.example .env

# Edit .env with actual values for your environment
# Never commit .env to git!
# Add to .gitignore: echo ".env" >> .gitignore
```

---

## Quick Start Guide

### Prerequisites
- Docker Desktop installed on your machine
- Project cloned with all source files

### 1. Setup Environment Variables
```bash
# Copy template to actual .env file
cp docker/.env.example .env

# Edit .env with your environment-specific values
# Critical changes:
# - POSTGRES_PASSWORD: Change from "change_me_in_production" to a strong password
# - JWT_SECRET_KEY: Generate a random key (see .env.example for how)
```

### 2. Build and Start Services
```bash
# Navigate to docker folder
cd docker

# Build images and start all services in background
docker-compose up -d

# Verify all services are running
docker-compose ps

# Expected output: All services should show "Up" status
```

### 3. Verify Services
```bash
# Check API server is healthy
curl http://localhost:5000/api/v1/health

# Check Auth server is healthy
curl http://localhost:5001/health

# Check Log server is healthy
curl http://localhost:5002/health

# Expected response: {"status": "ok"}
```

### 4. View Logs
```bash
# Follow API server logs in real-time
docker-compose logs -f api

# Follow all services
docker-compose logs -f

# View only recent logs (switch to different service)
docker-compose logs api          # API logs
docker-compose logs auth         # Auth logs
docker-compose logs log          # Log logs
docker-compose logs db           # Database logs
```

### 5. Stop Services
```bash
# Stop all services (keeps data/logs)
docker-compose down

# Stop and remove all data (fresh start next time)
docker-compose down -v
```

---

## Common Docker Compose Commands

| Command | Purpose |
|---------|---------|
| `docker-compose up -d` | Start all services in background |
| `docker-compose down` | Stop all services (data persists) |
| `docker-compose down -v` | Stop and delete all volumes (fresh start) |
| `docker-compose logs -f` | Follow all logs in real-time |
| `docker-compose logs -f api` | Follow specific service logs |
| `docker-compose ps` | Show status of all services |
| `docker-compose exec api python` | Run Python REPL inside API container |
| `docker-compose exec db psql -U user -d dbname` | Access database CLI |
| `docker-compose restart api` | Restart single service |
| `docker-compose build` | Rebuild all images |

---

## Accessing Services

### From Outside Docker (Your Host Machine)
- **API Server:** http://localhost:5000
- **Auth Server:** http://localhost:5001
- **Log Server:** http://localhost:5002
- **Database:** localhost:5432 (use psql client)

### From Inside Docker (Between Containers)
Services use service names defined in docker-compose.yml:
- **API Server:** http://api:5000
- **Auth Server:** http://auth:5000
- **Log Server:** http://log:5000
- **Database:** postgresql://user:pass@db:5432/dbname

Example: In API code, connect to DB using `db` instead of `localhost`:
```python
DATABASE_URL = "postgresql://user:password@db:5432/idranti_db"
```

---

## Development vs Production

### Development Setup (Current)
✓ Good for:
- Local testing and debugging
- Rapid code iteration
- See logs in real-time

Features:
- `volumes: - ..:/app` mounts code for live reload
- `API_SERVER_DEBUG_MODE=False` (set to True for hot reload)
- Database can be inspected easily

### Production Setup (Different)
Would differ in these ways:
- Remove volume mounts (use built image, not live code)
- Set `DEBUG_MODE=False`
- Use production WSGI server (gunicorn, waitress)
- Add reverse proxy (nginx) for SSL
- Add secrets manager instead of .env file
- Use managed database (RDS, etc.) outside Docker

---

## Troubleshooting

### Services fail to start
```bash
# View detailed error logs
docker-compose logs api

# Rebuild images fresh
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Database connection errors
```bash
# Verify database is healthy
docker-compose ps db

# Check database logs
docker-compose logs db

# Connect directly to test
docker-compose exec db psql -U idranti_user -d idranti_db
```

### Port conflicts (port already in use)
```bash
# Find what's using the port
netstat -ano | findstr :5000

# Export different ports
docker-compose -e API_PORT=5010 up -d

# Or edit docker-compose.yml ports manually
```

### Image build issues
```bash
# Rebuild without cache
docker-compose build --no-cache

# Check Docker image sizes
docker images

# Clean up unused images
docker image prune
```

---

## Volume and Data Persistence

### Named Volumes
```bash
# List all volumes
docker volume ls

# Inspect a volume
docker volume inspect docker_postgres_data

# Remove specific volume
docker volume rm docker_postgres_data

# Remove all unused volumes
docker volume prune
```

PostgreSQL data is stored in `postgres_data` volume. Even after `docker-compose down`, data persists. Only `docker-compose down -v` deletes it.

---

## Environment Variable Reference

See `.env.example` for complete documentation of all variables.

**Critical variables:**
- `POSTGRES_PASSWORD` - Database security
- `JWT_SECRET_KEY` - Authentication security
- `DATABASE_URL` - Connection string (format: protocol://user:pass@host:port/db)

**Service configuration:**
- `API_SERVER_HOST` - Should be `0.0.0.0` in Docker
- `API_SERVER_PORT` - Container internal port
- Actual host port mapped in `docker-compose.yml` ports section
