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


def election_summary() -> dict:
    """Compute totals + winner for the live results event.

    Returns:
        {
          "totals":      {"PTI": 12, "PMLN": 8, ...},   # sorted desc
          "total_votes": 20,
          "winner":      "PTI",        # None if no votes
          "tie":         False,        # True if top two parties are tied
        }
    """
    totals = party_totals()
    total_votes = sum(totals.values())
    winner = None
    tie = False
    if total_votes > 0:
        ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        winner = ranked[0][0]
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            tie = True
    return {
        "totals": totals,
        "total_votes": total_votes,
        "winner": winner,
        "tie": tie,
    }
