# IDRANTI SICURI BACKEND

This repository provides a compact microservice-style Flask application for managing the backend of the IDRANTI SICURI application and its related resources.  
This project is aimed at providing fire fighters, public workers and hydrants mantainers with a quick, reliable, secure, easy to use/access browser based platform to access and manage hydrant related data.  
Most probably the platform will also be accessible through a mobile wrapper application.

## High level architecture

Services:

- `api_server.py` — main HTTP(S) API that registers blueprints, configures JWT validation, describes OpenAPI docs (Flasgger) and adds security pre-checks (e.g. SQL injection check and rate limiting).
  
- `auth_server.py` — dedicated authentication microservice that verifies passwords and issues JWT access and refresh tokens. It contains the login, token validation and refresh endpoints.

- `log_server.py` — UDP syslog-like listener that parses incoming messages, performs rate-limiting, and writes structured output to file and console.

Shared components and important files:

- `logging_interface.py` - Streamlined logging interface for services with local file backup in the form of SQLite file databases.  
It allows tracking of log statistics, better service instance identification, unsent logs tracking and re-sending.  
Each service communicates to its own logging interface which writes to a minimal SQLite database, then, periodically, a background threat gets the logs that have not been sent yet from the database and sends them as a JSON to the syslog server.  
Services sharing an interface will most probably not be necessary but still possible with some edits to the logging interface logic.
Namely, it would be necessary to:
  - pass the service instance identifier string to the interface when logging (i.e. not at initialization like the current solution)  
  - store said string in the SQLite database (instead of using a class string variable like the current solution)  
  - edit the logic that writes, reads and formats the data as JSON data to correctly handle the service instance identifier string being inside of the database  


- `models.py` — SQLAlchemy models for database tables.  
Each model includes a `to_dict()` helper function for JSON serialization.

- `*_config.py` — centralized configuration values (JWT settings, DB URI, regex patterns, rate limit parameters, file names, ports, etc...).  
To simplify the separation of the services into different machines each service has its own config file only with the values it strictly needs.  
Because of this some parameters (e.g. ports) must be equal in different config files, during development it's recommended to edit configuration values using codebase-wise search and replace tools (common in any major IDE) (e.g. magnifying glass in the left tool bar in Visual Studio Code).
Many defaults are development-friendly; override them before production.

- `api_blueprints/` — collection of Flask blueprints and utilities.  
Each blueprint corresponds to a logical resource (hydrant, control, photo, operator, user). `blueprints_utils.py` contains common helpers (logging, rate-limiting utilities, input validation helpers).
  
- `tests/` — pytest suites covering the microservices and blueprints.

## Documentation

Endpoint documentation is available through Swagger UI at 
```xml
http(s)://{api_host}:{api_port}/docs/
``` 

(with default configuration for development):

```xml
http://locahost:5000/docs/
``` 

with the relative configuration in `api_config.py` and template in `api_server.py`.  
Each endpoint documentation is modifiable by editing the docstring of said function, all other documentation is avaible in the code itself or in the README files for high-level explanations.

N.B: Due to constraints with Swagger the documentation for the endpoints of the auth server is hardcoded inside the variable `swagger_template` in `api_server.py`.   
When making changes to `auth_server.py` it is strongly advised to change the values inside of `api_server.py`.   
A more streamlined solution will be researched and implemented in the future.

## Log messages

Due to the expected very low throughput of log messages passing through the architecture no log broker is necessary (indicatively, such solutions start to matter at 100-1000 logs per second).  
Instead the architecture features an ad-hoc solution consisting of a dedicated interface (for each service) to a small database built with SQLite, this way the process of handling unsent logs is greatly simplified and, because of the transactional nature of relational databases, losing data is very unlinkely.  
To aid in management, each microservice also includes a dedicated endpoint for admin users to clear out sent logs in the sqlite3 database (i.e. delete all rows that have the 'sent' flag set).  

Each instance of a microservice will need its own instance of the interface, this can be achieved by placing the `logging_interface.py` along with the server source code in each machine that will run the service(s) and instantiating the interface in the server source code through the provied factory function `create_interface` in `logging_interface.py`.

**N.B.:** All log-related operations use UTC time without timezone indicators. 
Log messages are written in UTC format (without timezone indicators) using this structure:
```
2026-04-16 14:05:21,442 - INFO - [log-server-1] <14>1 2026-04-16T14:05:19 api-host api-server - HYDGET [api-server@32473 endpoint="/hydrants" user_id="42"] Hydrant list retrieved successfully
```

Therefore the first timestamp is when the log is received by the syslog server and the second when the log was processed by the interface.  
In logs generated by the syslog server itself obviously only one timestamp will be present (the server-side one).  

Breakdown of the example:

- `2026-04-16 14:05:21,442` : timestamp added by the log server Python logger when the line is written.
- `INFO` : log level used by the log server logger.
- `[log-server-1]` : origin identifier of the component writing the final line.
- `<14>1` : RFC 5424 priority (`14`, facility 1 + severity 6) and version (`1`).
- `2026-04-16T14:05:19` : original event timestamp produced by the logging interface and sent in the UDP JSON payload.
- `api-host` : hostname of the machine where the originating service runs.
- `api-server` : service name (RFC 5424 APP-NAME).
- `-` : process id placeholder (PROCID, always `-` because no component sets `process_id` in outgoing log payloads as it is not useful for the objective of this codebase; the log server reads it with '-' as a fallback default).
- `HYDGET` : message id for the event type.
- `[api-server@32473 endpoint="/hydrants" user_id="42"]` : structured data (SD-ID and key/value tags).
- `Hydrant list retrieved successfully` : free-form message text.

Example of log message generated directly by the log server itself:
```
2026-04-16 14:05:30,017 - INFO - [log-server-1] Starting syslog server...
```

**Message IDs available at the end of the file.**

## Tests

The `tests/` folder contains pytest test suites for the API server, auth server, and blueprints.  
To run the tests, use the following command from the project root:
```bash
python -m pytest tests/
```

Note: Before executing the tests it is necesary to first install the pytest library (it is not included in the requirements.txt file because it is only needed for testing and not for running the application) with the following command:
```bash
pip install pytest
```

## Security measures

This project implements several security measures.  
Highlights below reference the code and the config values in `config.py`.

- Password hashing and verification
	- Passwords are stored and validated using PBKDF2-HMAC-SHA256 (`PBKDF2HMAC`), it is recommended to play around with the configuration values for better complexity if the latency budget allows it. The verification function in `auth_server.py`:
		- Expects a `salt:hash` base64-encoded format.
		- Validates base64 decoding and handles malformed inputs gracefully.
		- Uses `kdf.verify(...)` to avoid timing [side-channel attacks](https://en.wikipedia.org/wiki/Side-channel_attack) that could arise from naive comparisons. (naive byte-by-byte check returns as soon a mismatch is found, allowing an attacker to measure timing differences and potentially recover secrets. To resolve this a constant-time comparison method is needed)

- JWT authentication
	- `flask_jwt_extended` is used for issuing and validating tokens.
	- Access token lifetime is configurable (`JWT_ACCESS_TOKEN_EXPIRES`) and refresh tokens are separate (`JWT_REFRESH_TOKEN_EXPIRES`).
	- The project performs a runtime check that `JWT_SECRET_KEY` has at least 32 bytes when encoded in UTF-8, long secrets are preferable but a short one won't stop the application.
	- The application checks tokens from multiple locations (headers, query string, and JSON) but you should avoid `query_string` in production to tokens leaking in logs.

- Input validation and SQL-injection scanning
	- A precompiled regex named `SQL_PATTERN` in `config.py` is used to detect common SQL keywords and suspicious characters. Functions like `is_input_safe()` (in `auth_server.py`) and blueprint-level checks validate incoming JSON keys and values.
	- N.B: This scanning is a helpful heuristic but not a replacement for parameterized queries. All DB access should use SQLAlchemy ORM or parameterized queries (SQLAlchemy handles that by default).
	- To avoid ReDos a maximum length for a scannable string and maximum recursion depth (for scanning complex data types that may contain other contain complex data types and so on) are defined (configurable via `.env` file).

- Rate limiting
	- Implemented with a in-memory TTL (Time to live) cache utility for each service.  
	For globally shared limits, replace this with a shared solution (e.g. Redis).
	- Related settings are configurable in the `*config.py` files (through `.env`).
	- The log server also enforces its own `TTLCache` limit and, when `RETAIN_LOGS_RATE_LIMIT_TRIGGER`is set to true, pushes rate-limited messages into a bounded delayed queue (`DELAYED_LOGS_QUEUE_SIZE`) instead of dropping them immediately.

- Logging and monitoring
	- Centralized logging is handled by `log_server.py`; each service sends logs through `logging_interface.py`, which buffers logs in SQLite and forwards them asynchronously via UDP.
	- Structured logs include service name, hostname, level, message text, optional message id, and optional structured tags.

- Transport security (TLS)
	- `api_server.py` and `auth_server.py` support SSL if certificate and key paths are provided in `config.py` (`*_SSL_CERT`, `*_SSL_KEY`, and `*_SSL` flags).

## Configuration and secrets

- To streamline the process of separating the services into different machines, a config file has been created for each server.  
In a testing/development environment these virtually function as a single monolithic configuration file.  
Unavoidably, there is some overlap between some of the configuration files, these always have to match the other configuration/settings.  

- Verify and replace any default secrets and DB credentials in `*_config.py` with secure values.

- Confirm token lifetimes and locations are suited to your deployment. Avoid `query_string` token locations in public-facing environments.

- The `*.config.py` files centralize default settings. Sensitive values in the repo (like the default `JWT_SECRET_KEY` and DB credentials) are for convenience in local development only. For production, you should:
	- Replace `JWT_SECRET_KEY` with a long, randomly generated secret (recommended >= 32 bytes). Use an environment variable or secret manager.
	- Use secure DB credentials and restrict DB network access.
	- Disable `API_SERVER_DEBUG_MODE` and `AUTH_SERVER_DEBUG_MODE` in production.

Recommended environment overrides (guidelines, use a proper deployment process):

- `JWT_SECRET_KEY` — use a securely generated key (e.g., 32+ bytes from `openssl rand -base64 48`).
- `SQLALCHEMY_DATABASE_URI` — use a production DB URI rather than the local defaults.

## Security hardening checklist (recommended before production)

1. Remove any hard-coded secret or sensitive settings and put them inside of a properly managed and kept `.env` file.
2. Ensure `JWT_SECRET_KEY` >= 32 bytes, rotate periodically, and keep secrets out of source control.
3. Use real TLS certificates in `*_SSL_CERT` / `*_SSL_KEY` (`*_SSL` flags will automatically configure wether certificate and key are provided or not).
4. Use a managed database or secure DB instance with restricted network access and strong credentials.
5. Disable debug modes and remove overly permissive token locations (prefer headers over query string).

## Rough road map to move into production

Only to be used as a sort of checklist, use a proper deployment process.

- Review test coverage.
- Remove any sensitive/weak settings that may affect security (check paragraph above).
- Depending on the number of machines you are deploying to, separate each service with their relevant  `*_config.py` file and a suitable `.env` file. (If a machine runs two or more services all the relevant `*_config.py` file have to present and the `.env` file has to be the sum of all the relevant `.env` files). Here's how to separate each server:
    - The log server consists of `log_server.py`, `log_config.py` and the relevant `.env` file.
    - The auth server consists of `auth_server.py`, `auth_config.py`, `models.py` (only needs SQLAlchemy instance and User resource abstraction but, for simplicity, the file can just be copied the same way that it is for the API server) and the relevant `.env` file.
    - The API server consists of `api_server.py`, `api_config.py`, `api_blueprints` folder, `models.py` and the relevant `.env` file.
- Use admin utilities (still being worked on) test that all the security measures function properly.

## Troubleshooting pointers

- **JWT configuration mismatch**: mismatched `JWT_SECRET_KEY` or `JWT_ALGORITHM` between `auth_server.py` and `api_server.py`.  
- **User authentication failures**: verify the stored password format and PBKDF2 parameters (iterations, hash length).  
- **Log messages or requests are dropped**: check `config.py` rate limit values and the log server's delayed queue size if messages are dropped.  
- **Unable to load configuration (No .env file found)**: The suffix .example has not been removed from the .env file.  
- **Unable to execute quick start/kill scripts to run the code on Windows based machines**: Execute this command in the powershell terminal `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Unrestricted`, this will allow script execution only for the current terminal session and not affect any other sessions or system-wide settings.
- **Unable to execuite quick start/kill scripts to run the code on Linux based machines**: Ensure the scripts have the proper permission (i.e you have properly used the `chmod` command).
- **Cannot connect to database**: Often, especially with deployment and testing configurations, the name (or other configurations) of the database is not fully clear while using only CLI tools. Aiding yourself with a GUI tool like pgAdmin4 check that the target database configurations matches the .env file.  Note: it is not recommend to `postgres` database, instead just create a new one and migrate the data if, by mistake, you inserted the data into `postgres` database.
- **Cannot launch services with SSL disabled**: Match sure all the configuration values are coherent with each other and that any empty values in the env file use "", because without them the parser will interpret the comment as the value.

## Message IDs reference

Authentication & Tokens
- `MSNTOK` - API service reached without a JWT token
- `INVTOK` - API service reached with an invalid JWT token
- `EXPTOK` - API service reached with an expired JWT token
- `REVTOK` - API service reached with a revoked JWT token
- `REFTOK` - Refresh JWT token
- `TOKVALERR` - Error while validating token

Login Operations
- `LOGIN` - User login
- `LOGINERR` - Error during user login operation
- `LOGINBADREQ` - Bad request received for login operation
- `LOGINFAIL` - User login fail
- `AUTHSRVUNAVAIL` - Authentication service is unavailable

Password Operations
- `PWDVERERR` - Error during password verification
- `PWDDECOERR` - Error while decoding password
- `PWDFMTERR` - Password format error (stored password does not respect salt:hash format)

Service Management
- `SRVSTART` - Service start
- `SRVSTARTERR` - Error while starting a service
- `SRVSTOP` - Service shutdown
- `BPLOADERR` - Error in API service while loading blueprints
- `BPLOADWARN` - Warning in API service while loading blueprints
- `DBCONNERR` - Error in API service while trying to connect to database
- `CLRLOGS` - Cleared logs in SQLite database before a given timestamp
- `CLRLOGSERR` - Error while clearing logs in SQLite database

Control resource operations
- `CTRLGET`, `CTRLPOST`, `CTRLDEL`, `CTRLPATCH`

Hydrant resource operations
- `HYDGET`, `HYDPOST`, `HYDDEL`, `HYDPATCH`

Operator resource operations
- `OPRGET`, `OPRPOST`, `OPRDEL`, `OPRPATCH`

Photo resource operations
- `PHOGET`, `PHOPOST`, `PHODEL`, `PHOPATCH`

User resource operations
- `USRGET`, `USRPOST`, `USRDEL`, `USRPATCH`
