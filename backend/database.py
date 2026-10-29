"""Database layer: connection, schema, dataset loading and every SQL query."""
import csv
import os
import sqlite3
from contextlib import closing

import psycopg2
from psycopg2.extras import DictCursor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_FILE = os.path.join(BASE_DIR, "database", "schema.sql")
DATASET_DIR = os.environ.get("DATASET_DIR", os.path.join(BASE_DIR, "datasets"))

CLASS_CODES = ["SL", "3A", "2A", "1A"]

_app = None


def init_app(app):
    global _app
    _app = app


def get_db_connection():
    database_url = _app.config.get("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url, cursor_factory=DictCursor)

    connection = sqlite3.connect(_app.config["DATABASE"])
    connection.row_factory = sqlite3.Row
    return connection


def _is_postgres():
    return bool(_app.config.get("DATABASE_URL"))


def _execute(connection, sql, params=()):
    if _is_postgres():
        cursor = connection.cursor()
        cursor.execute(sql.replace("?", "%s"), params)
        return cursor
    return connection.execute(sql, params)


# ----------------------------------------------------------------- setup
def init_db():
    """Create the tables (if missing) and refresh train data from the CSV datasets.

    Users and bookings are never touched, so accounts survive a restart.
    """
    if not _is_postgres():
        path = _app.config["DATABASE"]
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with closing(get_db_connection()) as connection:
        with open(SCHEMA_FILE, encoding="utf-8") as schema:
            if _is_postgres():
                cursor = connection.cursor()
                cursor.execute(schema.read())
                cursor.close()
            else:
                connection.executescript(schema.read())
        load_datasets(connection)


def _read_csv(filename):
    with open(os.path.join(DATASET_DIR, filename), newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load_datasets(connection):
    """Replace the stations / trains / train_classes tables with the CSV contents."""
    stations = _read_csv("stations.csv")
    trains = _read_csv("trains.csv")
    with connection:
        _execute(connection, "DELETE FROM train_classes")
        _execute(connection, "DELETE FROM trains")
        _execute(connection, "DELETE FROM stations")
        for row in stations:
            _execute(connection,
                "INSERT INTO stations (station_code, station_name, state, zone) VALUES (?, ?, ?, ?)",
                (row["station_code"].strip(), row["station_name"].strip(),
                 row["state"].strip(), row.get("zone", "").strip()),
            )
        for row in trains:
            _execute(connection,
                """INSERT INTO trains (train_no, name, train_type, source, destination,
                                       departure, arrival, duration, distance_km, runs_on)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (row["train_no"].strip(), row["name"].strip(), row["train_type"].strip(),
                 row["source"].strip(), row["destination"].strip(), row["departure"].strip(),
                 row["arrival"].strip(), row["duration"].strip(), int(row["distance_km"]),
                 row.get("runs_on", "Daily").strip() or "Daily"),
            )
            for code in CLASS_CODES:
                fare = int(row.get(f"fare_{code}") or 0)
                seats = int(row.get(f"seats_{code}") or 0)
                if fare > 0 and seats > 0:
                    _execute(connection,
                        "INSERT INTO train_classes (train_no, class_code, fare, total_seats) "
                        "VALUES (?, ?, ?, ?)",
                        (row["train_no"].strip(), code, fare, seats),
                    )


# ----------------------------------------------------------------- stations
def get_station_names():
    with closing(get_db_connection()) as connection:
        rows = _execute(connection,
            "SELECT station_name FROM stations ORDER BY station_name"
        ).fetchall()
    return [row["station_name"] for row in rows]


def get_stations():
    with closing(get_db_connection()) as connection:
        rows = _execute(connection,
            "SELECT station_code, station_name, state, zone FROM stations ORDER BY station_name"
        ).fetchall()
    return [dict(row) for row in rows]


# ----------------------------------------------------------------- trains
def _build_trains(connection, train_rows):
    classes = {}
    for row in _execute(connection,
        "SELECT train_no, class_code, fare, total_seats FROM train_classes"
    ).fetchall():
        classes.setdefault(row["train_no"], {})[row["class_code"]] = (row["fare"], row["total_seats"])

    trains = []
    for row in train_rows:
        offered = classes.get(row["train_no"], {})
        trains.append({
            "train_no": row["train_no"],
            "name": row["name"],
            "train_type": row["train_type"],
            "source": row["source"],
            "destination": row["destination"],
            "departure": row["departure"],
            "arrival": row["arrival"],
            "duration": row["duration"],
            "distance_km": row["distance_km"],
            "runs_on": row["runs_on"],
            "classes": {code: offered[code][0] for code in CLASS_CODES if code in offered},
            "seats": {code: offered[code][1] for code in CLASS_CODES if code in offered},
        })
    return trains


def get_trains(source="", destination="", train_type="", search=""):
    """Return trains (as dictionaries) matching the optional filters."""
    sql = "SELECT * FROM trains WHERE 1 = 1"
    params = []
    if source:
        sql += " AND source = ?"
        params.append(source)
    if destination:
        sql += " AND destination = ?"
        params.append(destination)
    if train_type:
        sql += " AND LOWER(train_type) = LOWER(?)"
        params.append(train_type)
    if search:
        sql += " AND (LOWER(name) LIKE ? OR train_no LIKE ? OR LOWER(source) LIKE ? OR LOWER(destination) LIKE ?)"
        like = f"%{search.lower()}%"
        params.extend([like, f"%{search}%", like, like])
    sql += " ORDER BY source, destination, departure"
    with closing(get_db_connection()) as connection:
        return _build_trains(connection, _execute(connection, sql, params).fetchall())


def get_train(train_no):
    if not train_no:
        return None
    with closing(get_db_connection()) as connection:
        rows = _execute(connection, "SELECT * FROM trains WHERE train_no = ?", (train_no,)).fetchall()
        trains = _build_trains(connection, rows)
    return trains[0] if trains else None


def count_trains():
    with closing(get_db_connection()) as connection:
        return _execute(connection, "SELECT COUNT(*) FROM trains").fetchone()[0]


# ----------------------------------------------------------------- seats
def get_seats_available(train_no, journey_date, train_class):
    """Seats left = total seats of the class minus confirmed passengers on that date."""
    with closing(get_db_connection()) as connection:
        return _seats_left(connection, train_no, journey_date, train_class)


def _seats_left(connection, train_no, journey_date, train_class):
    row = _execute(connection,
        "SELECT total_seats FROM train_classes WHERE train_no = ? AND class_code = ?",
        (train_no, train_class),
    ).fetchone()
    if row is None:
        return 0
    booked = _execute(connection,
        """SELECT COALESCE(SUM(passengers), 0) FROM bookings
           WHERE train_no = ? AND journey_date = ? AND train_class = ? AND status = 'CONFIRMED'""",
        (train_no, journey_date, train_class),
    ).fetchone()[0]
    return max(row["total_seats"] - booked, 0)


# ----------------------------------------------------------------- users
def get_user(email):
    if not email:
        return None
    with closing(get_db_connection()) as connection:
        row = _execute(connection, "SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    return dict(row) if row else None


def create_user(user):
    with closing(get_db_connection()) as connection:
        with connection:
            _execute(connection,
                """INSERT INTO users (email, name, member_id, phone, city, status, password_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user["email"], user["name"], user["member_id"], user["phone"],
                 user["city"], user["status"], user["password_hash"]),
            )


# ----------------------------------------------------------------- bookings
BOOKING_COLUMNS = (
    "pnr", "owner_email", "name", "age", "gender", "phone", "email", "source", "destination",
    "journey_date", "train_no", "train_name", "train_class", "passengers", "fare", "status",
    "booked_at",
)


def create_booking(booking):
    """Insert a booking only if enough seats are left. Returns (created, seats_left)."""
    connection = get_db_connection()
    try:
        _execute(connection, "BEGIN" if _is_postgres() else "BEGIN IMMEDIATE")
        if _is_postgres():
            _execute(
                connection,
                "SELECT train_no FROM train_classes WHERE train_no = ? AND class_code = ? FOR UPDATE",
                (booking["train_no"], booking["train_class"]),
            )
        left = _seats_left(connection, booking["train_no"], booking["journey_date"], booking["train_class"])
        if booking["passengers"] > left:
            _execute(connection, "ROLLBACK")
            return False, left
        _execute(connection,
            f"INSERT INTO bookings ({', '.join(BOOKING_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in BOOKING_COLUMNS)})",
            [booking[column] for column in BOOKING_COLUMNS],
        )
        _execute(connection, "COMMIT")
        return True, left - booking["passengers"]
    except Exception:
        if connection.in_transaction:
            _execute(connection, "ROLLBACK")
        raise
    finally:
        connection.close()


def pnr_exists(pnr):
    with closing(get_db_connection()) as connection:
        return _execute(connection, "SELECT 1 FROM bookings WHERE pnr = ?", (pnr,)).fetchone() is not None


def find_booking(pnr):
    with closing(get_db_connection()) as connection:
        row = _execute(connection, "SELECT * FROM bookings WHERE pnr = ?", (pnr,)).fetchone()
    return dict(row) if row else None


def get_bookings(owner_email):
    with closing(get_db_connection()) as connection:
        rows = _execute(connection,
            "SELECT * FROM bookings WHERE owner_email = ? ORDER BY booked_at DESC, pnr",
            (owner_email,),
        ).fetchall()
    return [dict(row) for row in rows]


def cancel_booking_record(pnr):
    """Mark a confirmed booking as cancelled; its seats become available again."""
    with closing(get_db_connection()) as connection:
        with connection:
            _execute(connection,
                "UPDATE bookings SET status = 'CANCELLED' WHERE pnr = ? AND status = 'CONFIRMED'",
                (pnr,),
            )
