"""Screen 4 — Voting Booth."""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from core.auth import voter_required
from core.db import (
    execute,
    fetch_all,
    fetch_one,
    get_conn,
    is_voting_open,
    log_event,
    now_iso,
    party_totals,
)
from core.esp32 import esp32

bp = Blueprint("booth", __name__)


@bp.route("/")
@voter_required
def booth():
    candidates = fetch_all("SELECT * FROM candidates ORDER BY name")
    return render_template(
        "booth.html",
        candidates=candidates,
        voter_name=session.get("voter_name", "Voter"),
    )


@bp.post("/vote")
@voter_required
def cast_vote():
    candidate_id = request.form.get("candidate_id", type=int)
    voter_id = session["voter_id"]

    if not is_voting_open():
        esp32.send("VOTE_FAIL", voter_id=voter_id, reason="Voting closed")
        flash("Voting is currently closed.", "danger")
        session.clear()
        return redirect(url_for("home.index"))

    candidate = fetch_one("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
    if candidate is None:
        esp32.send("VOTE_FAIL", voter_id=voter_id, reason="Invalid candidate")
        flash("Invalid candidate.", "danger")
        return redirect(url_for("booth.booth"))

    voter = fetch_one("SELECT name, has_voted FROM voters WHERE id = ?", (voter_id,))
    if voter is None or voter["has_voted"]:
        esp32.send("VOTE_FAIL", voter_id=voter_id, reason="Already voted")
        flash("Vote could not be recorded.", "danger")
        session.clear()
        return redirect(url_for("home.index"))

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO votes (voter_id, candidate_id, voted_at) VALUES (?,?,?)",
            (voter_id, candidate_id, now_iso()),
        )
        conn.execute("UPDATE voters SET has_voted = 1 WHERE id = ?", (voter_id,))

    totals = party_totals()
    log_event(
        "VOTE_CAST",
        voter_id=voter_id,
        candidate_id=candidate_id,
        candidate=candidate["name"],
        party=candidate["party"],
    )
    esp32.send(
        "VOTE_CAST",
        voter_id=voter_id,
        name=voter["name"],
        candidate=candidate["name"],
        party=candidate["party"],
        totals=totals,
    )

    voter_name = session.get("voter_name", "Voter")
    session.pop("voter_id", None)
    session.pop("voter_name", None)
    return render_template(
        "booth_done.html",
        voter_name=voter_name,
        candidate=candidate,
    )
