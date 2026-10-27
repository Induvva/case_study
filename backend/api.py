"""REST API (JSON). The frontend JavaScript calls these endpoints with fetch()."""
from datetime import date

from flask import Blueprint, jsonify, request, session

from . import database
from .services import CLASS_LABELS, resolve_train_for_route

bp = Blueprint("api", __name__, url_prefix="/api")


def _valid_date(value):
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


@bp.get("/health")
def health():
    """Used by Docker / Kubernetes to check that the app and the database are alive."""
    return jsonify(status="ok", database="connected", trains=database.count_trains())


@bp.get("/stations")
def stations():
    return jsonify(stations=database.get_stations())


@bp.get("/trains")
def trains():
    """Search trains. Optional query: source, destination, type, q (text), date (adds seats left)."""
    journey_date = request.args.get("date", "").strip()
    if journey_date and _valid_date(journey_date) is None:
        return jsonify(error="date must be in YYYY-MM-DD format"), 400

    found = database.get_trains(
        source=request.args.get("source", "").strip(),
        destination=request.args.get("destination", "").strip(),
        train_type=request.args.get("type", "").strip(),
        search=request.args.get("q", "").strip(),
    )
    if journey_date:
        for train in found:
            train["seats_available"] = {
                code: database.get_seats_available(train["train_no"], journey_date, code)
                for code in train["classes"]
            }
    return jsonify(count=len(found), trains=found)


@bp.get("/trains/<train_no>")
def train_detail(train_no):
    train = database.get_train(train_no)
    if train is None:
        return jsonify(error="Train not found"), 404
    return jsonify(train)


@bp.get("/fare")
def fare():
    """Fare for a route: /api/fare?source=Hyderabad&destination=Delhi&class=2A"""
    class_code = request.args.get("class", "SL").upper()
    train = resolve_train_for_route({
        "source": request.args.get("source", ""),
        "destination": request.args.get("destination", ""),
    })
    if train is None or class_code not in train["classes"]:
        return jsonify(error="No fare found for this route and class"), 404
    return jsonify(train_no=train["train_no"], train_name=train["name"], train_class=class_code,
                   class_name=CLASS_LABELS[class_code], fare=train["classes"][class_code])


@bp.get("/availability")
def availability():
    """Seats left: /api/availability?train_no=12603&date=2026-11-05&class=3A"""
    train_no = request.args.get("train_no", "")
    class_code = request.args.get("class", "SL").upper()
    journey_date = _valid_date(request.args.get("date", ""))
    train = database.get_train(train_no)
    if train is None or class_code not in train["classes"]:
        return jsonify(error="Train or class not found"), 404
    if journey_date is None:
        return jsonify(error="date must be in YYYY-MM-DD format"), 400
    return jsonify(train_no=train_no, date=journey_date, train_class=class_code,
                   seats_available=database.get_seats_available(train_no, journey_date, class_code),
                   total_seats=train["seats"][class_code])


@bp.get("/bookings")
def my_bookings():
    """The signed-in user's bookings (401 if not signed in)."""
    email = session.get("user_email")
    if database.get_user(email) is None:
        return jsonify(error="Login required"), 401
    bookings = database.get_bookings(email)
    for booking in bookings:
        booking.pop("owner_email", None)
    return jsonify(count=len(bookings), bookings=bookings)
