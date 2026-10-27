-- Railway Reservation System - database schema (SQLite)
-- Safe to run on every start-up: nothing here drops data.

-- Registered users (created through the Register page)
CREATE TABLE IF NOT EXISTS users (
    email         TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    member_id     TEXT NOT NULL UNIQUE,
    phone         TEXT NOT NULL DEFAULT '',
    city          TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL,
    password_hash TEXT NOT NULL
);

-- Reference data loaded from datasets/stations.csv
CREATE TABLE IF NOT EXISTS stations (
    station_code TEXT PRIMARY KEY,
    station_name TEXT NOT NULL UNIQUE,
    state        TEXT NOT NULL,
    zone         TEXT NOT NULL DEFAULT ''
);

-- Reference data loaded from datasets/trains.csv
CREATE TABLE IF NOT EXISTS trains (
    train_no    TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    train_type  TEXT NOT NULL,
    source      TEXT NOT NULL,
    destination TEXT NOT NULL,
    departure   TEXT NOT NULL,
    arrival     TEXT NOT NULL,
    duration    TEXT NOT NULL,
    distance_km INTEGER NOT NULL,
    runs_on     TEXT NOT NULL DEFAULT 'Daily'
);

-- Fare and seat capacity of every class on every train (from trains.csv)
CREATE TABLE IF NOT EXISTS train_classes (
    train_no    TEXT NOT NULL,
    class_code  TEXT NOT NULL,
    fare        INTEGER NOT NULL,
    total_seats INTEGER NOT NULL,
    PRIMARY KEY (train_no, class_code)
);

-- Reservations made by users
CREATE TABLE IF NOT EXISTS bookings (
    pnr          TEXT PRIMARY KEY,
    owner_email  TEXT NOT NULL,
    name         TEXT NOT NULL,
    age          INTEGER NOT NULL,
    gender       TEXT NOT NULL,
    phone        TEXT NOT NULL,
    email        TEXT NOT NULL,
    source       TEXT NOT NULL,
    destination  TEXT NOT NULL,
    journey_date TEXT NOT NULL,
    train_no     TEXT NOT NULL,
    train_name   TEXT NOT NULL,
    train_class  TEXT NOT NULL,
    passengers   INTEGER NOT NULL,
    fare         INTEGER NOT NULL,
    status       TEXT NOT NULL DEFAULT 'CONFIRMED',
    booked_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trains_route     ON trains (source, destination);
CREATE INDEX IF NOT EXISTS idx_bookings_owner   ON bookings (owner_email);
CREATE INDEX IF NOT EXISTS idx_bookings_seats   ON bookings (train_no, journey_date, train_class, status);
