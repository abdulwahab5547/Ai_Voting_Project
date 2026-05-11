"""SQLite connection helper + automatic schema creation."""
import json
import sqlite3
from datetime import datetime
from typing import Any, Iterable, Optional

from config import Config

SCHEMA = """
CREATE TABLE IF NOT EXISTS voters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    cnic            TEXT UNIQUE NOT NULL,
    face_encoding   BLOB NOT NULL,
    photo_path      TEXT,
    has_voted       INTEGER NOT NULL DEFAULT 0,
    registered_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    party           TEXT NOT NULL,
    symbol_path     TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS votes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    voter_id        INTEGER NOT NULL,
    candidate_id    INTEGER NOT NULL,
    voted_at        TEXT NOT NULL,
    FOREIGN KEY(voter_id)     REFERENCES voters(id)    ON DELETE CASCADE,
    FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event       TEXT NOT NULL,
    voter_id    INTEGER,
    details     TEXT,
    ts          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_faces (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    face_encoding   BLOB NOT NULL,
    enrolled_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_votes_candidate ON votes(candidate_id);
CREATE INDEX IF NOT EXISTS idx_voters_cnic    ON voters(cnic);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the database file and tables if they do not exist yet."""
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def log_event(event: str, voter_id: Optional[int] = None, **details: Any) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO audit_log (event, voter_id, details, ts) VALUES (?,?,?,?)",
            (event, voter_id, json.dumps(details) if details else None, now_iso()),
        )


def fetch_all(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(sql, tuple(params)).fetchall()


def fetch_one(sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(sql, tuple(params)).fetchone()


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Run a write statement; returns lastrowid."""
    with get_conn() as conn:
        cur = conn.execute(sql, tuple(params))
        return cur.lastrowid


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    row = fetch_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def is_voting_open() -> bool:
    return get_setting("voting_open", "0") == "1"


def set_voting_open(open_: bool) -> None:
    set_setting("voting_open", "1" if open_ else "0")


def admin_face_count() -> int:
    row = fetch_one("SELECT COUNT(*) AS n FROM admin_faces")
    return row["n"] if row else 0


def party_totals() -> dict[str, int]:
    rows = fetch_all(
        """
        SELECT c.party AS party, COUNT(v.id) AS votes
        FROM candidates c
        LEFT JOIN votes v ON v.candidate_id = c.id
        GROUP BY c.party
        ORDER BY votes DESC
        """
    )
    return {r["party"]: r["votes"] for r in rows}


def candidate_totals() -> dict[str, int]:
    rows = fetch_all(
        """
        SELECT c.name AS name, COUNT(v.id) AS votes
        FROM candidates c
        LEFT JOIN votes v ON v.candidate_id = c.id
        GROUP BY c.id, c.name
        ORDER BY votes DESC, c.name ASC
        """
    )
    return {r["name"]: r["votes"] for r in rows}


def election_summary() -> dict:
    """Compute totals + winner for the live results event.

    Returns:
        {
          "totals":      {"PTI": 12, "PMLN": 8, ...},      # per party, sorted desc
          "candidates":  {"Imran": 12, "Bilawal": 8, ...}, # per candidate
          "total_votes": 20,
          "winner":      "Imran",      # winning candidate name; None if no votes
          "winner_party":"PTI",        # party of winning candidate; None if no votes
          "tie":         False,        # True if top two candidates are tied
        }
    """
    totals = party_totals()
    cand_totals = candidate_totals()
    total_votes = sum(totals.values())
    winner = None
    winner_party = None
    tie = False
    if total_votes > 0:
        ranked = sorted(cand_totals.items(), key=lambda kv: kv[1], reverse=True)
        winner = ranked[0][0]
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            tie = True
        row = fetch_one("SELECT party FROM candidates WHERE name = ?", (winner,))
        if row is not None:
            winner_party = row["party"]
    return {
        "totals": totals,
        "candidates": cand_totals,
        "total_votes": total_votes,
        "winner": winner,
        "winner_party": winner_party,
        "tie": tie,
    }
