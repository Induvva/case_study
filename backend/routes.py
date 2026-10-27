"""Page routes: they read from the database and render the frontend templates."""
import random
from datetime import date, datetime

from flask import redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import database
from .services import (
    BOOKING_STATUSES, CLASS_LABELS, VALID_GENDERS, format_currency, generate_pnr,
    get_available_trains, login_required, resolve_train_for_route, safe_next_url,
    validate_booking,
)


def render_home(errors=None, form=None, available_trains=None, selected_train="", status=200):
    """Render the search + booking page (used by several routes)."""
    page = render_template(
        "index.html",
        stations=database.get_station_names(),
        classes=CLASS_LABELS,
        errors=errors or [],
        form=form or {},
        today=date.today().isoformat(),
        genders=VALID_GENDERS,
        available_trains=available_trains or [],
        selected_train=selected_train,
    )
    return page, status


# ----------------------------------------------------------------- accounts
def register_view():
    errors = []
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        city = request.form.get("city", "").strip()
        password = request.form.get("password", "")
        if not name:
            errors.append("Name is required.")
        if "@" not in email or "." not in email:
            errors.append("Enter a valid email address.")
        elif database.get_user(email):
            errors.append("An account with this email already exists.")
        if phone and (not phone.isdigit() or len(phone) != 10):
            errors.append("Phone number must be exactly 10 digits.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if not errors:
            database.create_user({
                "name": name,
                "member_id": f"IRCTC-{random.randint(10000, 99999)}",
                "email": email,
                "phone": phone,
                "city": city,
                "status": "Silver Member",
                "password_hash": generate_password_hash(password),
            })
            session.clear()
            session["user_email"] = email
            return redirect(url_for("index"))
    return render_template("register.html", errors=errors, form=form)


def login_view():
    error = None
    next_url = request.args.get("next", "")
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = database.get_user(email)
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_email"] = email
            return redirect(safe_next_url(request.form.get("next", "")))
        error = "Email or password is incorrect."
    return render_template("login.html", error=error, next_url=next_url)


def logout_view():
    session.clear()
    return redirect(url_for("index"))


@login_required
def profile_view():
    user = database.get_user(session["user_email"])
    profile_data = {key: value for key, value in user.items() if key != "password_hash"}
    return render_template("profile.html", profile=profile_data)


# ----------------------------------------------------------------- trains
def index_view():
    source = request.args.get("source", "")
    destination = request.args.get("destination", "")
    journey_date = request.args.get("journey_date", "")
    return render_home(
        form={"source": source, "destination": destination, "journey_date": journey_date},
        available_trains=get_available_trains(source, destination),
        selected_train=request.args.get("train_no", ""),
    )


def book_trains_view():
    return render_home()


def view_trains_view():
    trains = database.get_trains()
    train_types = sorted({train["train_type"] for train in trains})
    return render_template("view_trains.html", trains=trains, train_types=train_types)


def fare_enquiry_view():
    source = request.args.get("source", "")
    destination = request.args.get("destination", "")
    class_name = request.args.get("class", "SL").upper()
    train = resolve_train_for_route({"source": source, "destination": destination})
    fare = "--"
    if train and class_name in train["classes"]:
        fare = train["classes"][class_name]
    return render_template(
        "fare_enquiry.html",
        stations=database.get_station_names(),
        classes=CLASS_LABELS,
        source=source,
        destination=destination,
        selected_class=class_name,
        fare=fare,
        train=train,
    )


# ----------------------------------------------------------------- bookings
@login_required
def book_view():
    form = request.form
    errors = validate_booking(form)
    if errors:
        return render_home(errors, form, get_available_trains(form.get("source", ""), form.get("destination", "")),
                           form.get("train_no", ""), 400)

    train = resolve_train_for_route(form)
    passengers = int(form["passengers"])
    train_class = form["train_class"]
    booking = {
        "pnr": generate_pnr(),
        "owner_email": session["user_email"],
        "name": form["name"].strip(),
        "age": int(form["age"]),
        "gender": form.get("gender", "Other"),
        "phone": form["phone"].strip(),
        "email": form["email"].strip(),
        "source": form["source"],
        "destination": form["destination"],
        "journey_date": form["journey_date"],
        "train_no": train["train_no"],
        "train_name": train["name"],
        "train_class": train_class,
        "passengers": passengers,
        "fare": train["classes"][train_class] * passengers,
        "status": "CONFIRMED",
        "booked_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
    }
    created, seats_left = database.create_booking(booking)
    if not created:
        return render_home(
            [f"Only {seats_left} seats are available in {train_class} for this date."],
            form, get_available_trains(form["source"], form["destination"]), form.get("train_no", ""), 400,
        )
    return redirect(url_for("ticket", pnr=booking["pnr"]))


def _own_booking(pnr):
    booking = database.find_booking(pnr)
    if booking and booking["owner_email"] == session.get("user_email"):
        return booking
    return None


@login_required
def ticket_view(pnr):
    booking = _own_booking(pnr)
    if booking:
        return render_template("ticket.html", b=booking, format_currency=format_currency)
    return "Ticket not found", 404


@login_required
def pnr_status_view():
    pnr = request.values.get("pnr", "").strip()
    booking = _own_booking(pnr) if pnr else None
    return render_template("pnr_status.html", pnr=pnr, booking=booking)


@login_required
def all_bookings_view():
    status_filter = request.args.get("status", "").strip().upper()
    search_term = request.args.get("search", "").strip().lower()

    user_bookings = database.get_bookings(session["user_email"])
    filtered = list(user_bookings)
    if status_filter:
        filtered = [b for b in filtered if b["status"] == status_filter]
    if search_term:
        filtered = [
            b for b in filtered
            if search_term in " ".join(
                [b["pnr"], b["name"], b["train_name"], b["phone"], b["source"], b["destination"], b["email"]]
            ).lower()
        ]

    return render_template(
        "bookings.html",
        bookings=filtered,
        status_filter=status_filter,
        search_term=request.args.get("search", ""),
        total_bookings=len(user_bookings),
        total_confirmed=sum(1 for b in user_bookings if b["status"] == "CONFIRMED"),
        total_cancelled=sum(1 for b in user_bookings if b["status"] == "CANCELLED"),
        status_options=BOOKING_STATUSES,
    )


@login_required
def cancel_booking_view(pnr):
    if _own_booking(pnr) is None:
        return "Booking not found", 404
    database.cancel_booking_record(pnr)
    return redirect(url_for("all_bookings"))


# ----------------------------------------------------------------- registration of routes
def register(app):
    """Attach every page route to the app (endpoint names are used by url_for in templates)."""
    rules = [
        ("/register", "register", register_view, ["GET", "POST"]),
        ("/login", "login", login_view, ["GET", "POST"]),
        ("/logout", "logout", logout_view, ["GET"]),
        ("/profile", "profile", profile_view, ["GET"]),
        ("/", "index", index_view, ["GET"]),
        ("/home", "index", index_view, ["GET"]),
        ("/book-trains", "book_trains", book_trains_view, ["GET"]),
        ("/view-trains", "view_trains", view_trains_view, ["GET"]),
        ("/fare-enquiry", "fare_enquiry", fare_enquiry_view, ["GET"]),
        ("/book", "book", book_view, ["POST"]),
        ("/ticket/<pnr>", "ticket", ticket_view, ["GET"]),
        ("/pnr-status", "pnr_status", pnr_status_view, ["GET", "POST"]),
        ("/bookings", "all_bookings", all_bookings_view, ["GET"]),
        ("/bookings/<pnr>/cancel", "cancel_booking", cancel_booking_view, ["POST"]),
    ]
    for rule, endpoint, view, methods in rules:
        app.add_url_rule(rule, endpoint, view, methods=methods)
