-- =========================
-- Dummy data inserts
-- =========================

-- =========================
-- Plain text passwords for reference:
-- 'admin@comune.it': 'adminpass'
-- 'user1@comune.it':'userpass1'
-- 'user2@comune.it': 'userpass2'
-- 'operator1@comune.it': 'opass1'
-- 'viewer1@comune.it': 'vpass1'
-- =========================

-- Utenti
INSERT INTO utenti (email, comune, nome, cognome, password, ruolo) VALUES
('admin@comune.it', 'Roma', 'Mario', 'Rossi', '_A5eStQhatA-Vom5xGebmg==:HV8FXpnHn-rTghqkre3xo7DiGgv-TqzVKN-3y-Y3Okw=', 'admin'),
('user1@comune.it', 'Roma', 'Luigi', 'Bianchi', '8pNtVxfyAAI-CHLHFO_VRA==:OQ9BBJPtYB916jflt1I4aEPGlYu5aY2MhH3Za0jKLfo=', 'operator'),
('user2@comune.it', 'Milano', 'Anna', 'Verdi', 'x7Rh8hi7kHL1NztkEbyo8g==:hX_FZIq15oct9AXF6EsOAb9Km6XbcCKX2TaVYh7r95c=', 'viewer'),
('operator1@comune.it', 'Napoli', 'Giovanni', 'Neri', 'V34JhnknyfbQ12wpP8VF8A==:a2q2x2lCvWyboNHAxzIk25_0jP24qrrY0b96o58Zylw=', 'operator'),
('viewer1@comune.it', 'Torino', 'Laura', 'Gialli', 'Nh-uHcQr6LxAWsI8GMs_VA==:mf11NcvEwRkL9FBmcb32NTPI4XrB9XZ-SQR2GHu5y6k=', 'viewer');

-- Operatori
INSERT INTO operatori (CF, nome, cognome) VALUES
('RSSMRA80A01H501U', 'Marco', 'Rossi'),
('BNCLGU85B12F205X', 'Luca', 'Bianchi'),
('VRDANN90C41F205Z', 'Anna', 'Verdi');

-- Idranti
INSERT INTO idranti (
  stato, latitudine, longitudine, comune, via, area_geo, tipo, accessibilità, email_ins
) VALUES
('utilizzabile', 41.9028, 12.4964, 'Roma', 'Via Nazionale', 'Centro', 'a', 'fruibile da autobotte', 'admin@comune.it'),
('non utilizzabile', 41.8902, 12.4922, 'Roma', 'Via dei Fori Imperiali', 'Centro Storico', 'b', 'strada stretta', 'user1@comune.it'),
('tappi presenti', 45.4642, 9.1900, 'Milano', 'Corso Buenos Aires', 'Nord', 'a', 'privato ma accessibile', 'user2@comune.it');

-- Controlli
INSERT INTO controlli (data, tipo, esito, id_idrante) VALUES
('2025-01-10', 'periodico', TRUE, 1),
('2025-01-15', 'periodico', FALSE, 2),
('2025-01-20', 'periodico', TRUE, 3);

-- Controllo_Operatore (relazione molti-a-molti)
INSERT INTO controllo_operatore (id_controllo, CF) VALUES
(1, 'RSSMRA80A01H501U'),
(1, 'BNCLGU85B12F205X'),
(2, 'BNCLGU85B12F205X'),
(3, 'VRDANN90C41F205Z');

-- Foto
INSERT INTO foto (data, id_idrante, posizione) VALUES
('2025-01-10', 1, '/foto/idrante1_1.jpg'),
('2025-01-15', 2, '/foto/idrante2_1.jpg'),
('2025-01-20', 3, '/foto/idrante3_1.jpg');