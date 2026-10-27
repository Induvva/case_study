"""Business logic: validation, train lookup, PNR generation and login helpers."""
import random
from datetime import date
from functools import wraps

from flask import redirect, request, session, url_for

from . import database

CLASS_LABELS = {"SL": "Sleeper", "3A": "AC 3 Tier", "2A": "AC 2 Tier", "1A": "First AC"}
VALID_GENDERS = ["Male", "Female", "Other"]
BOOKING_STATUSES = ["CONFIRMED", "CANCELLED", "COMPLETED"]
MAX_PASSENGERS = 6


# ----------------------------------------------------------------- trains
def get_available_trains(source, destination):
    if not source or not destination or source == destination:
        return []
    return database.get_trains(source=source, destination=destination)


def resolve_train_for_route(form):
    """Return the train chosen in the form, or the first train on the route."""
    train_no = form.get("train_no", "")
    if train_no:
        train = database.get_train(train_no)
        if train:
            return train
    trains = get_available_trains(form.get("source", ""), form.get("destination", ""))
    return trains[0] if trains else None


# ----------------------------------------------------------------- validation
def validate_booking(form):
    """Return a list of error messages (empty list means the data is valid)."""
    errors = []
    name = form.get("name", "").strip()
    age = form.get("age", "").strip()
    phone = form.get("phone", "").strip()
    email = form.get("email", "").strip()
    source = form.get("source", "")
    destination = form.get("destination", "")
    journey_date = form.get("journey_date", "")
    train_class = form.get("train_class", "")
    train_no = form.get("train_no", "")
    passengers = form.get("passengers", "").strip()
    gender = form.get("gender", "Other")

    if not name:
        errors.append("Passenger name is required.")
    elif len(name) < 2:
        errors.append("Passenger name must contain at least 2 characters.")

    if not age.isdigit() or not (1 <= int(age) <= 120):
        errors.append("Age must be a number between 1 and 120.")

    if not (phone.isdigit() and len(phone) == 10):
        errors.append("Phone number must be exactly 10 digits.")

    if "@" not in email or "." not in email:
        errors.append("Enter a valid email address.")

    stations = database.get_station_names()
    if source not in stations or destination not in stations:
        errors.append("Select valid stations.")
    elif source == destination:
        errors.append("From and To stations cannot be the same.")

    if not journey_date:
        errors.append("Journey date is required.")
    else:
        try:
            journey_date_obj = date.fromisoformat(journey_date)
        except ValueError:
            errors.append("Journey date must be a valid date.")
        else:
            if journey_date_obj < date.today():
                errors.append("Journey date cannot be in the past.")

    if gender not in VALID_GENDERS:
        errors.append("Select a valid gender.")

    train = None
    if train_no:
        train = database.get_train(train_no)
        if train is None:
            errors.append("Select a valid train.")
        elif source and destination and (train["source"], train["destination"]) != (source, destination):
            errors.append("The selected train does not run between these stations.")
    elif source in stations and destination in stations and source != destination:
        train = resolve_train_for_route(form)
        if train is None:
            errors.append("No train is available for the selected route.")

    if train_class not in CLASS_LABELS:
        errors.append("Select a valid train class.")
    elif train is not None and train_class not in train["classes"]:
        errors.append(f"Class {train_class} is not available on this train.")

    if not passengers.isdigit() or not (1 <= int(passengers) <= MAX_PASSENGERS):
        errors.append(f"Number of passengers must be between 1 and {MAX_PASSENGERS}.")

    return errors


# ----------------------------------------------------------------- helpers
def generate_pnr():
    while True:
        pnr = "".join(random.choices("0123456789", k=10))
        if not database.pnr_exists(pnr):
            return pnr


def format_currency(value):
    return f"₹{value:,.0f}"


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if database.get_user(session.get("user_email")) is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped_view


def safe_next_url(candidate):
    if candidate and candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return url_for("index")
