-- ============================================================
-- OSTELLO RIDES — Database Schema
-- SQLite (MVP) | Upgrade path: PostgreSQL + PostGIS
-- ============================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ── USERS ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    phone       TEXT    NOT NULL UNIQUE,
    room_number TEXT,
    role        TEXT    NOT NULL DEFAULT 'resident',  -- resident | driver | admin
    pin_hash    TEXT,                                  -- bcrypt hash of 4-digit PIN
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── VEHICLES ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vehicles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_name TEXT    NOT NULL,
    plate       TEXT    NOT NULL UNIQUE,
    capacity    INTEGER NOT NULL DEFAULT 10,
    active      INTEGER NOT NULL DEFAULT 1             -- 1=available 0=off-duty
);

-- ── BOOKINGS ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bookings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    type            TEXT    NOT NULL CHECK(type IN ('pickup','drop')),
    lat             REAL    NOT NULL,
    lon             REAL    NOT NULL,
    location_label  TEXT    NOT NULL,
    preferred_time  TEXT    NOT NULL,   -- "HH:MM"
    scheduled_time  TEXT,               -- set after clustering
    group_id        INTEGER REFERENCES ride_groups(id),
    status          TEXT    NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','scheduled','assigned','in_progress','completed','cancelled')),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── RIDE GROUPS (one group = one vehicle dispatch) ─────────
CREATE TABLE IF NOT EXISTS ride_groups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id      INTEGER REFERENCES vehicles(id),
    type            TEXT    NOT NULL CHECK(type IN ('pickup','drop')),
    scheduled_time  TEXT    NOT NULL,
    route_data      TEXT,               -- JSON: OSRM response
    ordered_stops   TEXT,               -- JSON: [{booking_id, lat, lon, label}, ...]
    status          TEXT    NOT NULL DEFAULT 'open'
                    CHECK(status IN ('open','assigned','in_progress','completed')),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── SAVED LOCATIONS (per user) ────────────────────────────
CREATE TABLE IF NOT EXISTS saved_locations (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    label   TEXT    NOT NULL,   -- "College", "Home", "Metro"
    lat     REAL    NOT NULL,
    lon     REAL    NOT NULL
);

-- ── SYSTEM LOCATIONS (admin-defined landmarks) ─────────────
CREATE TABLE IF NOT EXISTS system_locations (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    label   TEXT    NOT NULL,
    icon    TEXT    NOT NULL DEFAULT '📍',
    lat     REAL    NOT NULL,
    lon     REAL    NOT NULL,
    active  INTEGER NOT NULL DEFAULT 1
);

-- ── SEED: DEFAULT DATA ────────────────────────────────────

INSERT OR IGNORE INTO system_locations (label, icon, lat, lon) VALUES
  ('Ostello (Belapur)',         '🏠', 19.0176,  73.0360),
  ('CBD Belapur Station',       '🚆', 19.0213,  73.0386),
  ('Belapur Bus Depot',         '🚌', 19.0200,  73.0370),
  ('Vashi Station',             '🚆', 19.0730,  72.9987),
  ('Kharghar Station',          '🚆', 19.0471,  73.0697),
  ('Panvel Station',            '🚆', 18.9894,  73.1175),
  ('Seawoods Station',          '🚆', 19.0043,  73.0175),
  ('Nerul Station',             '🚆', 19.0363,  73.0175),
  ('Palm Beach Road',           '🏖', 19.0100,  73.0050),
  ('Inorbit Mall Vashi',        '🛍', 19.0630,  73.0049),
  ('DY Patil College',          '🎓', 19.0440,  73.0705),
  ('NMIMS Navi Mumbai',         '🎓', 19.0430,  73.0200),
  ('Reliance Corporate Park',   '🏢', 19.0300,  73.0150),
  ('Mindspace Airoli',          '🏢', 19.1490,  72.9975),
  ('Navi Mumbai Airport (future)','✈', 18.9953,  73.1289);

INSERT OR IGNORE INTO vehicles (driver_name, plate, capacity) VALUES
  ('Ramesh Kumar',   'MH-43-AB-1234', 10),
  ('Suresh Yadav',   'MH-43-CD-5678', 10),
  ('Anil Patil',     'MH-43-EF-9012',  6);

INSERT OR IGNORE INTO users (name, phone, room_number, role, pin_hash) VALUES
  ('Admin',  '9999999999', NULL, 'admin',  '$2b$12$dummy_admin_hash'),
  ('Driver1','9888888881', NULL, 'driver', '$2b$12$dummy_driver_hash');
