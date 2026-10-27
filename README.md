# Railway Reservation System

A railway ticket reservation web application built as a **three-tier application**
(frontend, backend, database) with the train information loaded from CSV **datasets**.

```
 Browser (user)
      |
      v
+--------------------+      HTML pages + JSON (REST API)      +----------------------+
|  FRONTEND          |  <----------------------------------> |  BACKEND (Flask)     |
|  frontend/         |    fetch('/api/trains?...')            |  backend/            |
|  HTML, CSS, JS     |                                        |  routes, API, logic  |
+--------------------+                                        +----------+-----------+
                                                                         | SQL
                                                                         v
                                              +--------------------------+-----------+
                                              |  DATABASE (SQLite)                   |
                                              |  database/schema.sql                 |
                                              |  filled from datasets/*.csv          |
                                              +--------------------------------------+
```

## Project structure

| Folder / file | Layer | What it contains |
|---|---|---|
| `frontend/templates/` | Frontend | Jinja2 HTML pages (home, view trains, fare enquiry, tickets, ...) |
| `frontend/static/` | Frontend | `style.css` and `js/main.js` (calls the REST API with `fetch`) |
| `backend/routes.py` | Backend | Page routes (login, booking, cancel, PNR status, ...) |
| `backend/api.py` | Backend | REST API under `/api` (JSON) |
| `backend/services.py` | Backend | Validation, train lookup, PNR generation, login helpers |
| `backend/database.py` | Backend | Every SQL query and the dataset loader |
| `database/schema.sql` | Database | Tables: users, stations, trains, train_classes, bookings |
| `datasets/stations.csv` | Dataset | Station code, name, state, railway zone |
| `datasets/trains.csv` | Dataset | Train number, name, type, route, timings, distance, fares and seats per class |
| `app.py` | Entry point | Creates the Flask app (`python app.py`) |
| `test_app.py` | Tests | pytest tests for pages, bookings, datasets and the API |
| `Dockerfile`, `Jenkinsfile`, `deployment.yaml`, `service.yaml` | DevOps | Container image, CI/CD pipeline and Kubernetes manifests |

## How the datasets are used

On start-up the backend runs `database/schema.sql` and then reloads `stations.csv` and
`trains.csv` into the `stations`, `trains` and `train_classes` tables. Users and bookings
are never touched, so accounts and tickets survive a restart.

To use a different train dataset (for example one downloaded from Kaggle), keep the same
column names as `datasets/trains.csv` and restart the app:

`train_no, name, train_type, source, destination, departure, arrival, duration, distance_km,
runs_on, fare_SL, fare_3A, fare_2A, fare_1A, seats_SL, seats_3A, seats_2A, seats_1A`

> The sample data in `datasets/` is illustrative (timings and fares are not official).

## REST API

| Endpoint | Description |
|---|---|
| `GET /api/health` | App and database status (for Docker/Kubernetes health checks) |
| `GET /api/stations` | All stations |
| `GET /api/trains?source=&destination=&type=&q=&date=` | Search trains; with `date` it adds seats left per class |
| `GET /api/trains/<train_no>` | One train |
| `GET /api/fare?source=&destination=&class=` | Fare for a route and class |
| `GET /api/availability?train_no=&date=&class=` | Seats left on a date |
| `GET /api/bookings` | Bookings of the signed-in user (401 if not signed in) |

## Run locally

```
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 (set `FLASK_DEBUG=1` for auto-reload while developing).

## Run the tests

```
pytest test_app.py
```

## Docker

```
docker build -t railway_reserve .
docker run -d --name railway-web -p 5001:5000 railway_reserve
```

The database file is created inside the container. Environment variables:
`SECRET_KEY`, `DATABASE_PATH`, `DATASET_DIR`.
