BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis; -- Adds geospatial capabilities to the database
CREATE EXTENSION IF NOT EXISTS citext; -- Adds case-insensitive text type, useful for email fields to ensure uniqueness regardless of case
-- email are not case sensitive so just using UNIQUE would allow duplicates like "abc@def.com" and "ABC@DEF.COM" where as in reality they are the same email

-- ENUM TYPES

CREATE TYPE stato_idrante_enum AS ENUM ('Nuovo', 'Discreto', 'Pessimo', 'Sconosciuto');
CREATE TYPE superficie_enum AS ENUM ('Asfalto', 'Erba', 'Terra base pietra', 'Altro');
CREATE TYPE posizionamento_enum AS ENUM ('Soprassuolo', 'Sottosuolo');
CREATE TYPE stato_manutenzione_enum AS ENUM ('Buona', 'Discreta', 'Assente');
CREATE TYPE diametro_attacco_enum AS ENUM ('UNI 45', 'UNI 70', 'UNI 100');
CREATE TYPE tipo_manutenzione_enum AS ENUM ('Controllo periodico di manutenzione ordinaria','Manutenzione straordinaria');


-- TABLES

-- Table: utenti
CREATE TABLE utenti (
    id_utente SERIAL PRIMARY KEY,
    email CITEXT UNIQUE NOT NULL,
    nome VARCHAR(255) NOT NULL,
    cognome VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    cambio_password BOOLEAN NOT NULL DEFAULT TRUE
);

-- Table: enti
CREATE TABLE enti (
    id_ente SERIAL PRIMARY KEY,
    denominazione VARCHAR(255) UNIQUE NOT NULL,
    email_responsabile CITEXT NOT NULL
);

-- Table: utenti_enti
CREATE TABLE utenti_enti (
    email_utente CITEXT NOT NULL,
    id_ente INTEGER NOT NULL,
    PRIMARY KEY (email_utente, id_ente)
);

-- Table: idranti
CREATE TABLE idranti (
    id_idrante SERIAL PRIMARY KEY,
    latitudine NUMERIC(9, 6) NOT NULL CHECK (latitudine >= -90  AND latitudine <= 90),
    longitudine NUMERIC(9, 6) NOT NULL CHECK (longitudine >= -180 AND longitudine <= 180),
    indirizzo VARCHAR(255) NOT NULL,    -- Da API OpenStreetMap
    stato stato_idrante_enum NOT NULL DEFAULT 'Sconosciuto',
    funzionante BOOLEAN NOT NULL DEFAULT FALSE,
    posizionamento posizionamento_enum NOT NULL,
    superficie superficie_enum NOT NULL,
    perdite BOOLEAN NOT NULL DEFAULT FALSE,
    pozzetto_annesso BOOLEAN NOT NULL DEFAULT FALSE,
    accesso_autobotte BOOLEAN NOT NULL DEFAULT FALSE,
    stato_manutenzione stato_manutenzione_enum NOT NULL DEFAULT 'Assente',
    id_ente INTEGER NOT NULL,

    -- geom column will be automatically generated from latitudine and longitudine at insert/update time
    -- and stored in the database (i.e. not need to explicity insert in INSERT INTO queries)
    -- to update the geom column, just update latitudine and longitudine and the geom will be automatically updated accordingly
    -- 4326 is the SRID for WGS 84, the standard coordinate system for GPS coordinates
    geom geometry(Point, 4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitudine, latitudine), 4326)) STORED
);

-- Table: attacchi
CREATE TABLE attacchi (
    id_idrante INTEGER NOT NULL,
    diametro diametro_attacco_enum NOT NULL,
    tappo_mancante BOOLEAN NOT NULL DEFAULT FALSE,
    catena_mancante BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (id_idrante, diametro)
);

-- Table: Foto
CREATE TABLE foto (
    id_foto SERIAL PRIMARY KEY,
    id_idrante INTEGER NOT NULL,
    path_foto VARCHAR(1024) NOT NULL
);

-- Table: Manutenzioni
CREATE TABLE manutenzioni (
    id_manutenzione SERIAL PRIMARY KEY,
    id_idrante INTEGER NOT NULL,
    email_utente CITEXT NOT NULL,
    -- timestamps are stored in UTC WITHOUT timezone indicator to match the log server format
    -- default uses now() AT TIME ZONE 'UTC' to produce a timestamp without time zone in UTC
    timestamp_manutenzione TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    tipo tipo_manutenzione_enum NOT NULL,
    esito BOOLEAN NOT NULL,
    note TEXT
);

-- Validate incoming timestamps: we cannot detect their original timezone after parsing,
-- so enforce a sensible range to catch accidental non-UTC or malformed values.
-- This check ensures the timestamp is within [1970-01-01, now_utc + 1 hour].
ALTER TABLE manutenzioni
    ADD CONSTRAINT chk_manutenzioni_timestamp_range
    CHECK (
        timestamp_manutenzione >= TIMESTAMP '1970-01-01'
        AND timestamp_manutenzione <= (now() AT TIME ZONE 'UTC') + INTERVAL '1 hour'
    );


-- INDEXES

CREATE INDEX idx_idranti_geom ON idranti USING GIST (geom);

CREATE INDEX idx_enti_emailResponsabile ON enti(email_responsabile);
CREATE INDEX idx_utenti_enti_email_utente ON utenti_enti(email_utente);
CREATE INDEX idx_utenti_enti_id_ente ON utenti_enti(id_ente);
CREATE INDEX idx_idranti_id_ente ON idranti(id_ente);
CREATE INDEX idx_idranti_stato ON idranti(stato);
CREATE INDEX idx_attacchi_id_idrante ON attacchi(id_idrante);
CREATE INDEX idx_foto_id_idrante ON foto(id_idrante);
CREATE INDEX idx_manutenzioni_id_idrante ON manutenzioni(id_idrante);
CREATE INDEX idx_manutenzioni_email_utente ON manutenzioni(email_utente);


-- FOREIGN KEYS

-- Each ente has a responsible user.
-- RESTRICT avoids deleting a user that is still configured as responsible for an ente.
-- UPDATE CASCADE keeps references consistent when a user's email changes.
ALTER TABLE enti
    ADD CONSTRAINT fk_enti_responsabile
    FOREIGN KEY (email_responsabile) REFERENCES utenti(email)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;

-- utenti_enti is a pure association table between users and enti.
-- CASCADE on delete cleans up memberships automatically when parent records are removed.
-- UPDATE CASCADE keeps links aligned when user emails change.
ALTER TABLE utenti_enti
    ADD CONSTRAINT fk_utenti_enti_utente
    FOREIGN KEY (email_utente) REFERENCES utenti(email)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
    ADD CONSTRAINT fk_utenti_enti_ente
    FOREIGN KEY (id_ente) REFERENCES enti(id_ente)
    ON DELETE CASCADE
    ON UPDATE CASCADE;

-- Idranti are operational assets; deleting an ente while idranti still exist should be blocked.
-- UPDATE CASCADE preserves referential integrity on key updates.
ALTER TABLE idranti
    ADD CONSTRAINT fk_idranti_ente
    FOREIGN KEY (id_ente) REFERENCES enti(id_ente)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;

-- Attacchi cannot exist without their parent idrante.
-- CASCADE delete removes dependent rows automatically to prevent orphans.
-- UPDATE CASCADE keeps dependencies synchronized.
ALTER TABLE attacchi
    ADD CONSTRAINT fk_attacchi_idrante
    FOREIGN KEY (id_idrante) REFERENCES idranti(id_idrante)
    ON DELETE CASCADE
    ON UPDATE CASCADE;

-- Foto are dependent assets tied to one idrante.
-- CASCADE delete removes related media when the parent idrante is removed.
-- UPDATE CASCADE keeps references valid.
ALTER TABLE foto
    ADD CONSTRAINT fk_foto_idrante
    FOREIGN KEY (id_idrante) REFERENCES idranti(id_idrante)
    ON DELETE CASCADE
    ON UPDATE CASCADE;

-- Manutenzioni are historical records and should be preserved.
-- RESTRICT blocks parent deletions that would destroy maintenance history.
-- UPDATE CASCADE keeps references consistent when user emails change.
ALTER TABLE manutenzioni
    ADD CONSTRAINT fk_manutenzioni_idrante
    FOREIGN KEY (id_idrante) REFERENCES idranti(id_idrante)
    ON DELETE RESTRICT
    ON UPDATE CASCADE,
    ADD CONSTRAINT fk_manutenzioni_utente
    FOREIGN KEY (email_utente) REFERENCES utenti(email)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;

COMMIT;