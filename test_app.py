import os
from datetime import date, timedelta

import pytest

os.environ.pop("DATABASE_URL", None)

from app import app, init_db, validate_booking
from backend import database

app.config["TESTING"] = True


@pytest.fixture(autouse=True)
def isolate_data(tmp_path):
    app.config["DATABASE"] = str(tmp_path / "railway-test.db")
    init_db()


def create_account(client):
    return client.post("/register", data={
        "name": "Test User",
        "email": "test@example.com",
        "password": "test-password-123",
        "phone": "1234567890",
        "city": "Hyderabad",
    })


def all_bookings():
    return database.get_bookings("test@example.com")


# ----------------------------------------------------------------- database + datasets
def test_datasets_are_loaded_into_the_database():
    assert database.count_trains() >= 30
    stations = database.get_station_names()
    assert "Hyderabad" in stations and "Delhi" in stations
    train = database.get_train("12603")
    assert train["name"] == "Telangana Express"
    assert train["classes"]["3A"] == 890
    assert train["seats"]["3A"] == 20


def test_every_train_runs_between_known_stations_and_has_fares():
    stations = set(database.get_station_names())
    for train in database.get_trains():
        assert train["source"] in stations and train["destination"] in stations
        assert train["classes"], f"{train['train_no']} has no classes"


# ----------------------------------------------------------------- validation
def test_validate_booking_rejects_invalid_values():
    form = {
        "name": "John Doe",
        "age": "30",
        "gender": "Male",
        "phone": "1234567890",
        "email": "john@example.com",
        "source": "Hyderabad",
        "destination": "Hyderabad",
        "journey_date": (date.today() - timedelta(days=1)).isoformat(),
        "train_class": "2A",
        "passengers": "2",
    }

    errors = validate_booking(form)
    assert any("cannot be the same" in error.lower() for error in errors)
    assert any("past" in error.lower() for error in errors)


def test_validate_booking_rejects_train_on_other_route():
    form = {
        "name": "John Doe", "age": "30", "gender": "Male", "phone": "1234567890",
        "email": "john@example.com", "source": "Hyderabad", "destination": "Delhi",
        "journey_date": (date.today() + timedelta(days=2)).isoformat(),
        "train_class": "SL", "passengers": "1", "train_no": "12603",
    }
    assert any("does not run between" in error for error in validate_booking(form))


# ----------------------------------------------------------------- booking flow (stored in SQLite)
def test_book_and_cancel_booking():
    client = app.test_client()
    create_account(client)
    journey = (date.today() + timedelta(days=5)).isoformat()
    payload = {
        "name": "Alice Smith",
        "age": "28",
        "gender": "Female",
        "phone": "9876543210",
        "email": "alice@example.com",
        "source": "Hyderabad",
        "destination": "Bengaluru",
        "journey_date": journey,
        "train_class": "3A",
        "passengers": "2",
    }

    response = client.post("/book", data=payload, follow_redirects=True)
    assert response.status_code == 200
    assert b"Booking" in response.data or b"PNR" in response.data

    booking = all_bookings()[0]
    assert booking["train_no"] == "12603"
    assert booking["fare"] == 890 * 2
    assert database.get_seats_available("12603", journey, "3A") == 18

    cancel_response = client.post(f"/bookings/{booking['pnr']}/cancel")
    assert cancel_response.status_code == 302
    assert all_bookings()[0]["status"] == "CANCELLED"
    assert database.get_seats_available("12603", journey, "3A") == 20


def test_cannot_book_more_seats_than_available():
    client = app.test_client()
    create_account(client)
    payload = {
        "name": "Seat Hog", "age": "30", "gender": "Male", "phone": "9876543210",
        "email": "hog@example.com", "source": "Hyderabad", "destination": "Bengaluru",
        "journey_date": (date.today() + timedelta(days=6)).isoformat(),
        "train_class": "1A", "passengers": "5",   # 1A has 5 seats in the dataset
    }
    assert client.post("/book", data=payload).status_code == 302
    second = client.post("/book", data={**payload, "passengers": "1"})
    assert second.status_code == 400
    assert b"Only 0 seats" in second.data
    assert len(all_bookings()) == 1


def test_bookings_page_supports_filters():
    client = app.test_client()
    create_account(client)
    payload = {
        "name": "Bob Singh",
        "age": "40",
        "gender": "Male",
        "phone": "9988776655",
        "email": "bob@example.com",
        "source": "Delhi",
        "destination": "Mumbai",
        "journey_date": (date.today() + timedelta(days=3)).isoformat(),
        "train_class": "SL",
        "passengers": "1",
    }
    client.post("/book", data=payload)

    response = client.get("/bookings?status=CONFIRMED&search=Bob")
    assert response.status_code == 200
    assert b"Bob Singh" in response.data


def test_booking_survives_database_reinitialization():
    client = app.test_client()
    create_account(client)
    client.post("/book", data={
        "name": "Persist Me", "age": "33", "gender": "Other", "phone": "9876543210",
        "email": "p@example.com", "source": "Hyderabad", "destination": "Bengaluru",
        "journey_date": (date.today() + timedelta(days=4)).isoformat(),
        "train_class": "SL", "passengers": "1",
    })
    init_db()   # reloads the CSV datasets but must keep users and bookings
    assert len(all_bookings()) == 1


# ----------------------------------------------------------------- pages
def test_portal_pages_and_fare_enquiry():
    client = app.test_client()

    home = client.get("/")
    assert home.status_code == 200
    assert b"Railway Reservation System" in home.data

    trains = client.get("/view-trains")
    assert trains.status_code == 200
    assert b"Swarna Jayanti Express" in trains.data

    fare = client.get("/fare-enquiry?source=Hyderabad&destination=Delhi&class=2A")
    assert fare.status_code == 200
    assert b"1850" in fare.data

    profile = client.get("/profile")
    assert profile.status_code == 302
    create_account(client)
    profile = client.get("/profile")
    assert profile.status_code == 200
    assert b"Profile" in profile.data

    logout = client.get("/logout")
    assert logout.status_code == 302


def test_registration_login_and_protected_routes():
    client = app.test_client()
    assert client.get("/bookings").status_code == 302
    create_account(client)
    client.get("/logout")

    login = client.post("/login", data={
        "email": "test@example.com",
        "password": "test-password-123",
    })
    assert login.status_code == 302
    assert client.get("/profile").status_code == 200

    invalid_login = client.post("/login", data={
        "email": "test@example.com",
        "password": "wrong-password",
    })
    assert b"incorrect" in invalid_login.data


def test_registered_account_survives_database_reinitialization():
    client = app.test_client()
    create_account(client)
    client.get("/logout")

    init_db()
    login = client.post("/login", data={
        "email": "test@example.com",
        "password": "test-password-123",
    })
    assert login.status_code == 302
    assert client.get("/profile").status_code == 200


def test_pnr_status_is_limited_to_signed_in_owner():
    owner = app.test_client()
    create_account(owner)
    payload = {
        "name": "Passenger One",
        "age": "30",
        "gender": "Other",
        "phone": "1234567890",
        "email": "passenger@example.com",
        "source": "Hyderabad",
        "destination": "Bengaluru",
        "journey_date": (date.today() + timedelta(days=4)).isoformat(),
        "train_class": "SL",
        "passengers": "1",
    }
    owner.post("/book", data=payload)
    pnr = all_bookings()[0]["pnr"]
    assert b"CONFIRMED" in owner.get(f"/pnr-status?pnr={pnr}").data

    other_user = app.test_client()
    other_user.post("/register", data={
        "name": "Another User",
        "email": "another@example.com",
        "password": "another-password-123",
    })
    response = other_user.get(f"/pnr-status?pnr={pnr}")
    assert b"No booking was found" in response.data


# ----------------------------------------------------------------- REST API used by the frontend
def test_api_health_and_stations():
    client = app.test_client()
    health = client.get("/api/health").get_json()
    assert health["status"] == "ok" and health["trains"] >= 30
    stations = client.get("/api/stations").get_json()["stations"]
    assert any(s["station_name"] == "Hyderabad" and s["station_code"] == "HYB" for s in stations)


def test_api_trains_search_with_seats():
    client = app.test_client()
    journey = (date.today() + timedelta(days=2)).isoformat()
    data = client.get(f"/api/trains?source=Hyderabad&destination=Bengaluru&date={journey}").get_json()
    assert data["count"] >= 1
    train = next(t for t in data["trains"] if t["train_no"] == "12603")
    assert train["seats_available"]["SL"] == 40
    assert client.get("/api/trains?date=not-a-date").status_code == 400


def test_api_fare_availability_and_train_detail():
    client = app.test_client()
    fare = client.get("/api/fare?source=Hyderabad&destination=Delhi&class=2A").get_json()
    assert fare["fare"] == 1850
    assert client.get("/api/fare?source=Delhi&destination=Delhi").status_code == 404

    journey = (date.today() + timedelta(days=2)).isoformat()
    seats = client.get(f"/api/availability?train_no=12603&date={journey}&class=3A").get_json()
    assert seats["seats_available"] == 20 and seats["total_seats"] == 20

    assert client.get("/api/trains/12603").get_json()["name"] == "Telangana Express"
    assert client.get("/api/trains/00000").status_code == 404


def test_api_bookings_requires_login():
    client = app.test_client()
    assert client.get("/api/bookings").status_code == 401
    create_account(client)
    assert client.get("/api/bookings").get_json()["count"] == 0
