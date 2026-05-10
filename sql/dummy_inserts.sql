-- =========================
-- Plain text passwords for reference:
-- 'admin@comune.it': 'adminpass'
-- 'user1@comune.it':'userpass1'
-- 'user2@comune.it': 'userpass2'
-- 'operator1@comune.it': 'opass1'
-- 'viewer1@comune.it': 'vpass1'
-- =========================

-- Users
INSERT INTO users (email, name, surname, password, role, must_change_password) VALUES
('admin@comune.it', 'Mario', 'Rossi', '_A5eStQhatA-Vom5xGebmg==:HV8FXpnHn-rTghqkre3xo7DiGgv-TqzVKN-3y-Y3Okw=', 'amministratore', FALSE),
('user1@comune.it', 'Luigi', 'Bianchi', '8pNtVxfyAAI-CHLHFO_VRA==:OQ9BBJPtYB916jflt1I4aEPGlYu5aY2MhH3Za0jKLfo=', 'ente', TRUE),
('user2@comune.it', 'Anna', 'Verdi', 'x7Rh8hi7kHL1NztkEbyo8g==:hX_FZIq15oct9AXF6EsOAb9Km6XbcCKX2TaVYh7r95c=', 'ente', TRUE),
('operator1@comune.it', 'Giovanni', 'Neri', 'V34JhnknyfbQ12wpP8VF8A==:a2q2x2lCvWyboNHAxzIk25_0jP24qrrY0b96o58Zylw=', 'operatore', TRUE),
('viewer1@comune.it', 'Laura', 'Gialli', 'Nh-uHcQr6LxAWsI8GMs_VA==:mf11NcvEwRkL9FBmcb32NTPI4XrB9XZ-SQR2GHu5y6k=', 'visualizzatore', TRUE);

-- entities
INSERT INTO entities (denominazione, manager_email) VALUES
('Comune di Roma', 'admin@comune.it'),
('Comune di Milano', 'user2@comune.it'),
('Comune di Napoli', 'operator1@comune.it');

-- User associated to entities
INSERT INTO user_entities (user_email, entity_id) VALUES
('admin@comune.it', 1),
('user1@comune.it', 1),
('user2@comune.it', 2),
('operator1@comune.it', 3);

-- Hydrants
INSERT INTO hydrants (
  latitude,
  longitude,
  address,
  status,
  functioning,
  positioning,
  surface_type,
  leaks,
  has_sump,
  accessible_firetruck,
  maintenance_status,
  entity_id
) VALUES
(41.902800, 12.496400, 'Via Nazionale, Roma', 'Nuovo', TRUE, 'Soprassuolo', 'Asfalto', FALSE, TRUE, TRUE, 'Buona', 1),
(41.890200, 12.492200, 'Via dei Fori Imperiali, Roma', 'Discreto', FALSE, 'Sottosuolo', 'Altro', TRUE, FALSE, FALSE, 'Discreta', 1),
(45.464200, 9.190000, 'Corso Buenos Aires, Milano', 'Pessimo', TRUE, 'Soprassuolo', 'Asfalto', FALSE, TRUE, TRUE, 'Assente', 2);

-- Connectors
INSERT INTO connectors (hydrant_id, diameter, cap_missing, chain_missing) VALUES
(1, 'UNI 45', FALSE, FALSE),
(1, 'UNI 70', TRUE, FALSE),
(2, 'UNI 45', FALSE, TRUE),
(3, 'UNI 100', FALSE, FALSE);

-- Photos
INSERT INTO photo (hydrant_id, path) VALUES
(1, '/foto/idrante1_1.jpg'),
(2, '/foto/idrante2_1.jpg'),
(3, '/foto/idrante3_1.jpg');

-- Maintenance records
INSERT INTO maintenance (
  hydrant_id,
  user_email,
  maintenance_timestamp,
  type_manutenzione,
  outcome,
  notes
) VALUES
(1, 'admin@comune.it', '2025-01-10 10:00:00', 'Controllo periodico di manutenzione ordinaria', TRUE, 'Tutto regolare'),
(2, 'user1@comune.it', '2025-01-15 11:30:00', 'Manutenzione straordinaria', FALSE, 'Serve intervento urgente'),
(3, 'operator1@comune.it', '2025-01-20 09:15:00', 'Controllo periodico di manutenzione ordinaria', TRUE, 'Ripristinato correttamente');