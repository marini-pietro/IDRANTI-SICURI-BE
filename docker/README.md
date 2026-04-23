# Docker configuration for IDRANTI SICURI backend

This directory contains all Docker-related configuration files for the IDRANTI SICURI backend application.

## Files overview

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


### `Dockerfile.auth`
**Purpose:** Blueprint for building the Auth server Docker image

**Structure:** Same as Dockerfile.api, differing only in:
- Input: Installs Python packages from `auth_requirements.txt`
- Output: Creates image for auth server instead of API
- Startup command: Runs `auth_server.py` instead of `api_server.py`


### `Dockerfile.log`
**Purpose:** Blueprint for building the Log server Docker image

**Structure:** Same as Dockerfile.api, differing only in:
- Startup command: Runs `log_server.py` instead of `api_server.py`


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

### `.env.example`
**Purpose:** Template for environment variables needed by all services

## Quick start guide

### Prerequisites
- Docker Desktop installed on your machine
- Project cloned with all source files

### 1. Setup environment variables
```bash
# Copy template to actual .env file
cp .env.example .env

# Edit .env with your environment-specific values
```

### 2. Build and start services
```bash
# From project root, build images and start all services in background
docker/run_compose.sh up -d      # Linux/macOS
docker\\run_compose.bat up -d   # Windows CMD

# Verify all services are running
docker compose ps

# Expected output: All services should show "Up" status for each container
```

### 3. Verify services health
```bash
# Check API server is healthy
curl http://localhost:5000/api/v1/health

# Check Auth server is healthy
curl http://localhost:5001/health

# Check Log server is healthy
curl http://localhost:5002/health

# Expected response: {"status": "ok"}
```

### 4. View logs (optional)
```bash
# Follow API server logs in real-time
docker/run_compose.sh logs -f api      # Linux/macOS
docker\\run_compose.bat logs -f api   # Windows CMD

# Follow all services
docker/run_compose.sh logs -f          # Linux/macOS
docker\\run_compose.bat logs -f       # Windows CMD

# View only recent logs (switch to different service)
docker/run_compose.sh logs api         # API logs (Linux/macOS)
docker/run_compose.sh logs auth        # Auth logs (Linux/macOS)
docker/run_compose.sh logs log         # Log logs (Linux/macOS)
docker/run_compose.sh logs db          # Database logs (Linux/macOS)

docker\\run_compose.bat logs api      # API logs (Windows CMD)
docker\\run_compose.bat logs auth     # Auth logs (Windows CMD)
docker\\run_compose.bat logs log      # Log logs (Windows CMD)
docker\\run_compose.bat logs db       # Database logs (Windows CMD)
```

### 5. Stop services
```bash
# Stop all services (keeps data/logs)
docker/run_compose.sh down        # Linux/macOS
docker\\run_compose.bat down     # Windows CMD

# Stop and remove all data (fresh start next time)
docker/run_compose.sh down -v     # Linux/macOS
docker\\run_compose.bat down -v  # Windows CMD
```

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

### From Outside Docker (host Machine)
- **API Server:** http://localhost:5000
- **Auth Server:** http://localhost:5001
- **Log Server:** http://localhost:5002
- **Database:** localhost:5432 (use psql client)

### From Inside Docker (between containers)
Services use service names defined in docker-compose.yml:
- **API Server:** http://api:5000
- **Auth Server:** http://auth:5000
- **Log Server:** http://log:5000
- **Database:** postgresql://user:pass@db:5432/dbname

Example: In API code, connect to DB using `db` instead of `localhost`:
```python
DATABASE_URL = "postgresql://user:password@db:5432/idranti_db"
```

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

## Volume and data persistence

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