BEGIN;

-- ENUM types
CREATE TYPE tipo_controllo_enum AS ENUM ('periodico');
CREATE TYPE stato_idrante_enum AS ENUM ('utilizzabile','non utilizzabile','tappi presenti','tappi assenti');
CREATE TYPE tipo_idrante_enum AS ENUM ('a','b');
CREATE TYPE accessibilità_enum AS ENUM ('strada stretta','fruibile da autobotte','privato ma accessibile');
CREATE TYPE ruolo_enum AS ENUM ('admin', 'operator', 'viewer');

-- Table: controlli
CREATE TABLE controlli (
  id_controllo SERIAL PRIMARY KEY,
  data DATE NOT NULL,
  tipo tipo_controllo_enum NOT NULL,
  esito BOOLEAN NOT NULL,
  id_idrante INTEGER NOT NULL
);

-- Table: controllo_operatore
CREATE TABLE controllo_operatore (
  id_controllo INTEGER NOT NULL,
  CF CHAR(16) NOT NULL,
  PRIMARY KEY (id_controllo, CF)
);

-- Table: foto
CREATE TABLE foto (
  id_foto SERIAL PRIMARY KEY,
  data DATE NOT NULL,
  id_idrante INTEGER NOT NULL,
  posizione VARCHAR(255) NOT NULL
);

-- Table: idranti
CREATE TABLE idranti (
  id SERIAL PRIMARY KEY,
  stato stato_idrante_enum NOT NULL,
  latitudine FLOAT NOT NULL CHECK (latitudine >= -90 AND latitudine <= 90),
  longitudine FLOAT NOT NULL CHECK (longitudine >= -180 AND longitudine <= 180),
  comune VARCHAR(255) NOT NULL,
  via VARCHAR(255) NOT NULL,
  area_geo VARCHAR(255) NOT NULL,
  tipo tipo_idrante_enum NOT NULL,
  accessibilità accessibilità_enum NOT NULL,
  email_ins VARCHAR(255) NOT NULL
);

-- Table: operatori
CREATE TABLE operatori (
  CF CHAR(16) PRIMARY KEY,
  nome VARCHAR(255) NOT NULL,
  cognome VARCHAR(255) NOT NULL
);

-- Table: utenti
CREATE TABLE utenti (
  email VARCHAR(255) PRIMARY KEY,
  comune VARCHAR(255) NOT NULL,
  nome VARCHAR(255) NOT NULL,
  cognome VARCHAR(255) NOT NULL,
  password VARCHAR(255) NOT NULL,
  ruolo ruolo_enum NOT NULL
);

-- Indexes
CREATE INDEX idx_controlli_id_idrante ON controlli(id_idrante);
CREATE INDEX idx_controllo_operatore_CF ON controllo_operatore(CF);
CREATE INDEX idx_foto_id_idrante ON foto(id_idrante);
CREATE INDEX idx_idranti_email_ins ON idranti(email_ins);

-- Foreign Keys
ALTER TABLE controlli
  ADD CONSTRAINT fk_controlli_idrante FOREIGN KEY (id_idrante) REFERENCES idranti(id);

ALTER TABLE controllo_operatore
  ADD CONSTRAINT fk_controllo_operatore_controllo FOREIGN KEY (id_controllo) REFERENCES controlli(id_controllo),
  ADD CONSTRAINT fk_controllo_operatore_operatore FOREIGN KEY (CF) REFERENCES operatori(CF);

ALTER TABLE foto
  ADD CONSTRAINT fk_foto_idrante FOREIGN KEY (id_idrante) REFERENCES idranti(id);

ALTER TABLE idranti
  ADD CONSTRAINT fk_idranti_email_ins FOREIGN KEY (email_ins) REFERENCES utenti(email);

COMMIT;