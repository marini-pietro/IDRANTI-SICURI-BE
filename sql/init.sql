BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis; -- Adds geospatial capabilities to the database
CREATE EXTENSION IF NOT EXISTS citext; -- Adds case-insensitive text type, useful for email fields to ensure uniqueness regardless of case
-- email are not case sensitive so just using UNIQUE would allow duplicates like "abc@def.com" and "ABC@DEF.COM" where as in reality they are the same email

-- ENUM TYPES

CREATE TYPE hydrant_status_enum AS ENUM ('Nuovo', 'Discreto', 'Pessimo', 'Sconosciuto');
CREATE TYPE surface_type_enum AS ENUM ('Asfalto', 'Erba', 'Terra base pietra', 'Altro');
CREATE TYPE positioning_enum AS ENUM ('Soprassuolo', 'Sottosuolo');
CREATE TYPE maintenance_status_enum AS ENUM ('Buona', 'Discreta', 'Assente');
CREATE TYPE connection_diameter_enum AS ENUM ('UNI 45', 'UNI 70', 'UNI 100');
CREATE TYPE maintenance_type_enum AS ENUM ('Controllo periodico di manutenzione ordinaria','Manutenzione straordinaria');
CREATE TYPE role_enum AS ENUM ('amministratore', 'ente', 'visualizzatore');

-- TABLES

-- Table: users
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    email CITEXT UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    surname VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    role role_enum NOT NULL DEFAULT 'visualizzatore',
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE -- Users will login with a temporary password and will be forced to change it on first access
);

-- Table: entities
CREATE TABLE entities (
    entity_id SERIAL PRIMARY KEY,
    denomination VARCHAR(255) UNIQUE NOT NULL,
    manager_email CITEXT NOT NULL
);

-- Table: user_entities
CREATE TABLE user_entities (
    user_email CITEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    PRIMARY KEY (user_email, entity_id)
);

-- Table: hydrants
CREATE TABLE hydrants (
    hydrant_id SERIAL PRIMARY KEY,
    latitude NUMERIC(9, 6) NOT NULL CHECK (latitude >= -90  AND latitude <= 90),
    longitude NUMERIC(9, 6) NOT NULL CHECK (longitude >= -180 AND longitude <= 180),
    address VARCHAR(255) NOT NULL,    -- Da API OpenStreetMap
    status hydrant_status_enum NOT NULL DEFAULT 'Sconosciuto',
    functioning BOOLEAN NOT NULL DEFAULT FALSE,
    positioning positioning_enum NOT NULL,
    surface_type surface_type_enum NOT NULL,
    leaks BOOLEAN NOT NULL DEFAULT FALSE,
    has_sump BOOLEAN NOT NULL DEFAULT FALSE,
    accessible_firetruck BOOLEAN NOT NULL DEFAULT FALSE,
    maintenance_status maintenance_status_enum NOT NULL DEFAULT 'Assente',
    entity_id INTEGER NOT NULL,

    -- geom column will be automatically generated from latitude and longitude at insert/update time
    -- and stored in the database (i.e. not need to explicity insert in INSERT INTO queries)
    -- to update the geom column, just update latitude and longitude and the geom will be automatically updated accordingly
    -- 4326 is the SRID for WGS 84, the standard coordinate system for GPS coordinates
    geom geometry(Point, 4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)) STORED
);

-- Table: connectors
CREATE TABLE connectors (
    hydrant_id INTEGER NOT NULL,
    diameter connection_diameter_enum NOT NULL,
    cap_missing BOOLEAN NOT NULL DEFAULT FALSE,
    chain_missing BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (hydrant_id, diameter)
);

-- Table: photo
CREATE TABLE photo (
    id_foto SERIAL PRIMARY KEY,
    hydrant_id INTEGER NOT NULL,
    path VARCHAR(1024) NOT NULL
);

-- Table: maintenance
CREATE TABLE maintenance (
    maintenance_id SERIAL PRIMARY KEY,
    hydrant_id INTEGER NOT NULL,
    user_email CITEXT NOT NULL,
    -- timestamps are stored in UTC WITHOUT timezone indicator to match the log server format
    -- default uses now() AT TIME ZONE 'UTC' to produce a timestamp without time zone in UTC
    maintenance_timestamp TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    type maintenance_type_enum NOT NULL,
    outcome BOOLEAN NOT NULL,
    notes TEXT
);

-- Validate incoming timestamps: we cannot detect their original timezone after parsing,
-- so enforce a sensible range to catch accidental non-UTC or malformed values.
-- This check ensures the timestamp is within [1970-01-01, now_utc + 1 hour].
ALTER TABLE maintenance
    ADD CONSTRAINT chk_manutenzioni_timestamp_range
    CHECK (
        maintenance_timestamp >= TIMESTAMP '1970-01-01'
        AND maintenance_timestamp <= (now() AT TIME ZONE 'UTC') + INTERVAL '1 hour'
    );


-- INDEXES

CREATE INDEX idx_idranti_geom ON hydrants USING GIST (geom);

CREATE INDEX idx_enti_emailResponsabile ON entities(manager_email);
CREATE INDEX idx_utenti_enti_email_utente ON user_entities(user_email);
CREATE INDEX idx_utenti_enti_id_ente ON user_entities(entity_id);
CREATE INDEX idx_idranti_id_ente ON hydrants(entity_id);
CREATE INDEX idx_idranti_stato ON hydrants(status);
CREATE INDEX idx_attacchi_id_idrante ON connectors(hydrant_id);
CREATE INDEX idx_foto_id_idrante ON photo(hydrant_id);
CREATE INDEX idx_manutenzioni_id_idrante ON maintenance(hydrant_id);
CREATE INDEX idx_manutenzioni_email_utente ON maintenance(user_email);


-- FOREIGN KEYS

-- Each ente has a responsible user.
-- RESTRICT avoids deleting a user that is still configured as responsible for an ente.
-- UPDATE CASCADE keeps references consistent when a user's email changes.
ALTER TABLE entities
    ADD CONSTRAINT fk_enti_responsabile
    FOREIGN KEY (manager_email) REFERENCES users(email)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;

-- user_entities is a pure association table between users and entities.
-- CASCADE on delete cleans up memberships automatically when parent records are removed.
-- UPDATE CASCADE keeps links aligned when user emails change.
ALTER TABLE user_entities
    ADD CONSTRAINT fk_utenti_enti_utente
    FOREIGN KEY (user_email) REFERENCES users(email)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
    ADD CONSTRAINT fk_utenti_enti_ente
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
    ON DELETE CASCADE
    ON UPDATE CASCADE;

-- hydrants are operational assets; deleting an ente while hydrants still exist should be blocked.
-- UPDATE CASCADE preserves referential integrity on key updates.
ALTER TABLE hydrants
    ADD CONSTRAINT fk_idranti_ente
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;

-- connectors cannot exist without their parent idrante.
-- CASCADE delete removes dependent rows automatically to prevent orphans.
-- UPDATE CASCADE keeps dependencies synchronized.
ALTER TABLE connectors
    ADD CONSTRAINT fk_attacchi_idrante
    FOREIGN KEY (hydrant_id) REFERENCES hydrants(hydrant_id)
    ON DELETE CASCADE
    ON UPDATE CASCADE;

-- photo are dependent assets tied to one idrante.
-- CASCADE delete removes related media when the parent idrante is removed.
-- UPDATE CASCADE keeps references valid.
ALTER TABLE photo
    ADD CONSTRAINT fk_foto_idrante
    FOREIGN KEY (hydrant_id) REFERENCES hydrants(hydrant_id)
    ON DELETE CASCADE
    ON UPDATE CASCADE;

-- maintenance are historical records and should be preserved.
-- RESTRICT blocks parent deletions that would destroy maintenance history.
-- UPDATE CASCADE keeps references consistent when user emails change.
ALTER TABLE maintenance
    ADD CONSTRAINT fk_manutenzioni_idrante
    FOREIGN KEY (hydrant_id) REFERENCES hydrants(hydrant_id)
    ON DELETE RESTRICT
    ON UPDATE CASCADE,
    ADD CONSTRAINT fk_manutenzioni_utente
    FOREIGN KEY (user_email) REFERENCES users(email)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;

COMMIT;