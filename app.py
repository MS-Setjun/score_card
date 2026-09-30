import json
import os
import sqlite3
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_from_directory, g

DB_PATH = os.environ.get("DB_PATH", "/data/scorecard.db")

app = Flask(__name__, static_folder="static", static_url_path="")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


DEFAULT_DIVISIONS = [
    "Mixed Premier", "Mixed Division 1", "Mixed Division 2", "Mixed Division 3",
    "Mixed Division 4", "Mixed Division 5", "Mixed Division 6",
    "Open Premier", "Open Division 1", "Open Division 2", "Open Division 3",
    "Open Division 4", "Open Division 5", "Open Division 6", "Open Division 7",
    "Open Division 8",
    "Womens Premier", "Womens Division 1", "Womens Division 2",
]

DEFAULT_TEAMS = [
    "Arboretum", "Beeston Braves", "Beeston Fields", "Beeston Valley",
    "Bilborough", "Bingham", "Byron", "Carlton", "Chilwell", "Crusader",
    "David Lloyd Aspley", "DSD", "East Leake", "Falcon Feathers", "Forest",
    "Freddie's", "Mansfield Oaktree", "Mapperley Park", "North Notts Social",
    "Radcliffe Knights", "Rolls-Royce", "Rushcliffe Arena", "Safari Badminton",
    "Southwell", "University of Nottingham", "West Bridgford",
]

DEFAULT_VENUES = [
    "Bilborough College", "Bluecoat Trent Academy", "Carlton Forum Leisure Centre",
    "Chilwell Olympia Sports Centre", "Cotgrave Leisure Centre",
    "David Lloyd Leisure Centre", "East Leake Leisure Centre", "Etwall Leisure Centre",
    "Harvey Hadden Sports Village", "Jubilee Campus Sports Centre",
    "Kimberley Leisure Centre", "Kirkby Leisure Centre", "Lee Westwood Sports Village",
    "Nottingham Emmanuel School", "Nottingham Girls' High School",
    "Nottingham High School", "Ravenshead Leisure Centre", "Rushcliffe Arena",
    "South Nottinghamshire Academy", "Southwell Leisure Centre", "The Bemrose School",
    "Toot Hill Sports Centre",
]


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            home_team TEXT,
            away_team TEXT,
            division TEXT,
            match_date TEXT,
            venue TEXT,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS divisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS venues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
        """
    )
    # Merge in the current default lists on every startup (INSERT OR IGNORE is a
    # no-op for names that already exist), so redeploying with an updated list
    # never wipes anything already saved.
    conn.executemany(
        "INSERT OR IGNORE INTO divisions (name) VALUES (?)",
        [(d,) for d in DEFAULT_DIVISIONS],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO teams (name) VALUES (?)",
        [(t,) for t in DEFAULT_TEAMS],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO venues (name) VALUES (?)",
        [(v,) for v in DEFAULT_VENUES],
    )
    conn.commit()
    conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/manifest.webmanifest")
def manifest():
    return send_from_directory(
        app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json"
    )


@app.route("/sw.js")
def service_worker():
    # served from the root scope (not /static/sw.js) so it can control the whole app
    return send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")


@app.route("/api/matches", methods=["GET"])
def list_matches():
    db = get_db()
    rows = db.execute(
        "SELECT id, home_team, away_team, division, match_date, venue, updated_at "
        "FROM matches ORDER BY updated_at DESC LIMIT 200"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/matches", methods=["POST"])
def create_match():
    payload = request.get_json(force=True, silent=True) or {}
    state = payload.get("state")
    if state is None:
        return jsonify({"error": "missing state"}), 400
    db = get_db()
    ts = now_iso()
    cur = db.execute(
        "INSERT INTO matches (home_team, away_team, division, match_date, venue, data, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            state.get("homeTeam", ""),
            state.get("awayTeam", ""),
            state.get("division", ""),
            state.get("date", ""),
            state.get("venue", ""),
            json.dumps(state),
            ts,
            ts,
        ),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/matches/<int:match_id>", methods=["GET"])
def get_match(match_id):
    db = get_db()
    row = db.execute("SELECT data FROM matches WHERE id = ?", (match_id,)).fetchone()
    if row is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(json.loads(row["data"]))


@app.route("/api/matches/<int:match_id>", methods=["PUT"])
def update_match(match_id):
    payload = request.get_json(force=True, silent=True) or {}
    state = payload.get("state")
    if state is None:
        return jsonify({"error": "missing state"}), 400
    db = get_db()
    row = db.execute("SELECT id FROM matches WHERE id = ?", (match_id,)).fetchone()
    if row is None:
        return jsonify({"error": "not found"}), 404
    db.execute(
        "UPDATE matches SET home_team=?, away_team=?, division=?, match_date=?, venue=?, data=?, updated_at=? "
        "WHERE id=?",
        (
            state.get("homeTeam", ""),
            state.get("awayTeam", ""),
            state.get("division", ""),
            state.get("date", ""),
            state.get("venue", ""),
            json.dumps(state),
            now_iso(),
            match_id,
        ),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/matches/<int:match_id>", methods=["DELETE"])
def delete_match(match_id):
    db = get_db()
    db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/divisions", methods=["GET"])
def list_divisions():
    db = get_db()
    rows = db.execute("SELECT id, name FROM divisions ORDER BY name").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/divisions", methods=["POST"])
def add_division():
    payload = request.get_json(force=True, silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "missing name"}), 400
    db = get_db()
    try:
        cur = db.execute("INSERT INTO divisions (name) VALUES (?)", (name,))
        db.commit()
        return jsonify({"id": cur.lastrowid, "name": name}), 201
    except sqlite3.IntegrityError:
        row = db.execute("SELECT id, name FROM divisions WHERE name = ?", (name,)).fetchone()
        return jsonify(dict(row)), 200


@app.route("/api/divisions/<int:division_id>", methods=["DELETE"])
def delete_division(division_id):
    db = get_db()
    db.execute("DELETE FROM divisions WHERE id = ?", (division_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/teams", methods=["GET"])
def list_teams():
    db = get_db()
    rows = db.execute("SELECT id, name FROM teams ORDER BY name").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/teams", methods=["POST"])
def add_team():
    payload = request.get_json(force=True, silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "missing name"}), 400
    db = get_db()
    try:
        cur = db.execute("INSERT INTO teams (name) VALUES (?)", (name,))
        db.commit()
        return jsonify({"id": cur.lastrowid, "name": name}), 201
    except sqlite3.IntegrityError:
        row = db.execute("SELECT id, name FROM teams WHERE name = ?", (name,)).fetchone()
        return jsonify(dict(row)), 200


@app.route("/api/teams/<int:team_id>", methods=["DELETE"])
def delete_team(team_id):
    db = get_db()
    db.execute("DELETE FROM teams WHERE id = ?", (team_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/venues", methods=["GET"])
def list_venues():
    db = get_db()
    rows = db.execute("SELECT id, name FROM venues ORDER BY name").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/venues", methods=["POST"])
def add_venue():
    payload = request.get_json(force=True, silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "missing name"}), 400
    db = get_db()
    try:
        cur = db.execute("INSERT INTO venues (name) VALUES (?)", (name,))
        db.commit()
        return jsonify({"id": cur.lastrowid, "name": name}), 201
    except sqlite3.IntegrityError:
        row = db.execute("SELECT id, name FROM venues WHERE name = ?", (name,)).fetchone()
        return jsonify(dict(row)), 200


@app.route("/api/venues/<int:venue_id>", methods=["DELETE"])
def delete_venue(venue_id):
    db = get_db()
    db.execute("DELETE FROM venues WHERE id = ?", (venue_id,))
    db.commit()
    return jsonify({"ok": True})


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
