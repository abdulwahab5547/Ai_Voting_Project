"""Screen 5 — Live Results Dashboard."""
from flask import Blueprint, jsonify, render_template

from core.db import fetch_all, fetch_one

bp = Blueprint("results", __name__)


@bp.route("/")
def page():
    return render_template("results.html")


@bp.route("/data")
def data():
    rows = fetch_all(
        """
        SELECT c.id, c.name, c.party, c.symbol_path,
               COUNT(v.id) AS votes
        FROM candidates c
        LEFT JOIN votes v ON v.candidate_id = c.id
        GROUP BY c.id
        ORDER BY votes DESC, c.name ASC
        """
    )
    candidates = [dict(r) for r in rows]

    total_voters = fetch_one("SELECT COUNT(*) AS n FROM voters")["n"]
    total_voted = fetch_one("SELECT COUNT(*) AS n FROM voters WHERE has_voted = 1")["n"]
    last = fetch_one("SELECT MAX(voted_at) AS ts FROM votes")
    turnout = round((total_voted / total_voters) * 100, 1) if total_voters else 0.0

    return jsonify(
        candidates=candidates,
        total_voters=total_voters,
        total_voted=total_voted,
        turnout=turnout,
        last_vote=last["ts"] if last else None,
    )
