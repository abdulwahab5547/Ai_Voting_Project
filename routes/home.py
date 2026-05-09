"""Screen 1 — Home Dashboard."""
from flask import Blueprint, render_template

from core.db import fetch_one

bp = Blueprint("home", __name__)


@bp.route("/")
def index():
    voters = fetch_one("SELECT COUNT(*) AS n FROM voters")["n"]
    voted = fetch_one("SELECT COUNT(*) AS n FROM voters WHERE has_voted = 1")["n"]
    candidates = fetch_one("SELECT COUNT(*) AS n FROM candidates")["n"]
    return render_template(
        "home.html",
        total_voters=voters,
        total_voted=voted,
        total_candidates=candidates,
    )
