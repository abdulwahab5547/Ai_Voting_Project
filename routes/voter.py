"""Screen 3 — Voter Face Login.

GET  /voter/login        — page with live webcam
POST /voter/login        — JSON {image: dataURL} -> match result
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request, session, url_for

from core.db import fetch_all, fetch_one, log_event
from core.esp32 import esp32
from core.face import FaceError, blob_to_encoding, decode_data_url, encode_face, match_face

bp = Blueprint("voter", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("voter_login.html")

    payload = request.get_json(silent=True) or {}
    data_url = payload.get("image", "")
    if not data_url:
        return jsonify(status="error", message="No image received."), 400

    try:
        encoding = encode_face(decode_data_url(data_url))
    except FaceError as exc:
        log_event("LOGIN_FAIL", reason=str(exc))
        esp32.send("LOGIN_FAIL", reason=str(exc))
        return jsonify(status="fail", message=str(exc))
    except Exception as exc:  # noqa: BLE001
        return jsonify(status="error", message=f"Image error: {exc}"), 400

    rows = fetch_all("SELECT id, face_encoding FROM voters")
    known = [(r["id"], blob_to_encoding(r["face_encoding"])) for r in rows]

    voter_id = match_face(encoding, known)
    if voter_id is None:
        log_event("LOGIN_FAIL", reason="No match")
        esp32.send("LOGIN_FAIL")
        return jsonify(status="fail", message="You are not a registered voter.")

    voter = fetch_one("SELECT id, name, has_voted FROM voters WHERE id = ?", (voter_id,))
    if voter["has_voted"]:
        log_event("ALREADY_VOTED", voter_id=voter["id"])
        esp32.send("ALREADY_VOTED", name=voter["name"])
        return jsonify(
            status="already_voted",
            message=f"{voter['name']}, you have already cast your vote.",
        )

    session["voter_id"] = voter["id"]
    session["voter_name"] = voter["name"]
    log_event("LOGIN_OK", voter_id=voter["id"])
    esp32.send("LOGIN_OK", name=voter["name"])
    return jsonify(
        status="ok",
        message=f"Welcome, {voter['name']}.",
        redirect=url_for("booth.booth"),
    )
