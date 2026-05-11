"""Screen 2 — Admin Panel.

Endpoints:
    /admin/login          — password prompt
    /admin/logout
    /admin/dashboard      — tabbed UI (default tab = register)
    /admin/voters         — voters list tab
    /admin/candidates     — candidates tab
    /admin/register   POST — create voter from face capture
    /admin/voters/<id>/delete  POST
    /admin/candidates  POST — create candidate
    /admin/candidates/<id>/delete POST
    /admin/reset      POST — clear votes + has_voted flags
"""
from __future__ import annotations

import uuid
from pathlib import Path

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from config import Config
from core.auth import admin_required
from core.db import (
    admin_face_count,
    election_summary,
    execute,
    fetch_all,
    fetch_one,
    get_conn,
    is_voting_open,
    log_event,
    now_iso,
    set_voting_open,
)
from core.esp32 import esp32
from core.face import (
    FaceError,
    blob_to_encoding,
    decode_data_url,
    encode_face,
    encoding_to_blob,
    match_face,
)

bp = Blueprint("admin", __name__)

ALLOWED_IMG_EXT = {"png", "jpg", "jpeg", "gif", "webp"}


@bp.route("/")
def root():
    return redirect(url_for("admin.dashboard") if session.get("is_admin") else url_for("admin.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == Config.ADMIN_PASSWORD:
            session["is_admin"] = True
            esp32.send("ADMIN_LOGIN")
            return redirect(url_for("admin.dashboard"))
        flash("Wrong password.", "danger")
    return render_template("admin/login.html")


@bp.route("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("home.index"))


@bp.route("/dashboard")
@admin_required
def dashboard():
    return render_template(
        "admin/dashboard.html",
        voting_open=is_voting_open(),
        admin_face_enrolled=admin_face_count() > 0,
    )


# -------- Admin face enrollment ------------------------------------------

@bp.route("/face_enroll", methods=["GET", "POST"])
@admin_required
def face_enroll():
    if request.method == "GET":
        return render_template("admin/face_enroll.html")

    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "Admin").strip()
    data_url = payload.get("image", "")
    if not data_url:
        return jsonify(status="error", message="No image received."), 400
    try:
        encoding = encode_face(decode_data_url(data_url))
    except FaceError as exc:
        return jsonify(status="fail", message=str(exc))
    except Exception as exc:  # noqa: BLE001
        return jsonify(status="error", message=f"Image error: {exc}"), 400

    execute(
        "INSERT INTO admin_faces (name, face_encoding, enrolled_at) VALUES (?,?,?)",
        (name, encoding_to_blob(encoding), now_iso()),
    )
    log_event("ADMIN_FACE_ENROLL", name=name)
    return jsonify(status="ok", message=f"Admin face for '{name}' enrolled.")


# -------- Start / stop voting (face-gated) -------------------------------

@bp.route("/start_voting", methods=["GET", "POST"])
@admin_required
def start_voting():
    if request.method == "GET":
        return render_template(
            "admin/start_voting.html",
            voting_open=is_voting_open(),
            admin_face_enrolled=admin_face_count() > 0,
        )

    if admin_face_count() == 0:
        return jsonify(
            status="error",
            message="No admin face enrolled yet. Enroll one first.",
        ), 400

    payload = request.get_json(silent=True) or {}
    data_url = payload.get("image", "")
    if not data_url:
        return jsonify(status="error", message="No image received."), 400

    try:
        encoding = encode_face(decode_data_url(data_url))
    except FaceError as exc:
        log_event("ADMIN_FACE_FAIL", reason=str(exc))
        esp32.send("ADMIN_FACE_FAIL", reason=str(exc))
        return jsonify(status="fail", message=str(exc))
    except Exception as exc:  # noqa: BLE001
        return jsonify(status="error", message=f"Image error: {exc}"), 400

    rows = fetch_all("SELECT id, name, face_encoding FROM admin_faces")
    known = [(r["id"], blob_to_encoding(r["face_encoding"])) for r in rows]
    matched = match_face(encoding, known)
    if matched is None:
        log_event("ADMIN_FACE_FAIL", reason="No match")
        esp32.send("ADMIN_FACE_FAIL", reason="No match")
        return jsonify(status="fail", message="Face not recognized as admin.")

    admin_row = next((r for r in rows if r["id"] == matched), None)
    admin_name = admin_row["name"] if admin_row else "Admin"

    set_voting_open(True)
    log_event("VOTING_OPEN", admin_id=matched, admin_name=admin_name)
    esp32.send("VOTING_OPEN", admin=admin_name)
    return jsonify(
        status="ok",
        message=f"Welcome {admin_name}. Voting is now OPEN.",
        redirect=url_for("admin.dashboard"),
    )


@bp.post("/stop_voting")
@admin_required
def stop_voting():
    set_voting_open(False)
    log_event("VOTING_CLOSED")
    esp32.send("VOTING_CLOSED")
    flash("Voting closed.", "info")
    return redirect(url_for("admin.dashboard"))


# -------- Register voter --------------------------------------------------

@bp.post("/register")
@admin_required
def register_voter():
    name = (request.form.get("name") or "").strip()
    cnic = (request.form.get("cnic") or "").strip()
    image_data_url = request.form.get("image", "")

    if not name or not cnic or not image_data_url:
        flash("Name, CNIC and a captured photo are all required.", "danger")
        return redirect(url_for("admin.dashboard"))

    if fetch_one("SELECT id FROM voters WHERE cnic = ?", (cnic,)):
        flash(f"A voter with CNIC {cnic} is already registered.", "danger")
        return redirect(url_for("admin.dashboard"))

    try:
        image_bytes = decode_data_url(image_data_url)
        encoding = encode_face(image_bytes)
    except FaceError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("admin.dashboard"))
    except Exception as exc:  # noqa: BLE001
        flash(f"Could not process the photo: {exc}", "danger")
        return redirect(url_for("admin.dashboard"))

    photo_name = f"{uuid.uuid4().hex}.png"
    photo_path = Config.FACES_DIR / photo_name
    photo_path.write_bytes(image_bytes)

    voter_id = execute(
        """INSERT INTO voters (name, cnic, face_encoding, photo_path, has_voted, registered_at)
           VALUES (?, ?, ?, ?, 0, ?)""",
        (name, cnic, encoding_to_blob(encoding), str(photo_path.relative_to(Config.DATA_DIR)), now_iso()),
    )
    log_event("REGISTER", voter_id=voter_id, name=name, cnic=cnic)

    total_voters = fetch_one("SELECT COUNT(*) AS n FROM voters")["n"]
    esp32.send("VOTER_REGISTERED", voter_id=voter_id, name=name, total=total_voters)

    flash(f"Voter '{name}' registered successfully.", "success")
    return redirect(url_for("admin.voters"))


# -------- Voters tab ------------------------------------------------------

@bp.route("/voters")
@admin_required
def voters():
    rows = fetch_all(
        "SELECT id, name, cnic, has_voted, registered_at FROM voters ORDER BY registered_at DESC"
    )
    return render_template("admin/voters.html", voters=rows)


@bp.post("/voters/<int:voter_id>/delete")
@admin_required
def delete_voter(voter_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM votes  WHERE voter_id = ?", (voter_id,))
        conn.execute("DELETE FROM voters WHERE id = ?", (voter_id,))
    log_event("DELETE_VOTER", voter_id=voter_id)
    flash("Voter deleted.", "success")
    return redirect(url_for("admin.voters"))


# -------- Candidates tab --------------------------------------------------

@bp.route("/candidates", methods=["GET", "POST"])
@admin_required
def candidates():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        party = (request.form.get("party") or "").strip()
        if not name or not party:
            flash("Name and party are required.", "danger")
            return redirect(url_for("admin.candidates"))

        symbol_path = ""
        file = request.files.get("symbol")
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext not in ALLOWED_IMG_EXT:
                flash("Symbol must be a PNG/JPG/JPEG/GIF/WEBP.", "danger")
                return redirect(url_for("admin.candidates"))
            safe = secure_filename(file.filename)
            target = Config.CANDIDATES_DIR / f"{uuid.uuid4().hex}_{safe}"
            file.save(target)
            symbol_path = str(target.relative_to(Config.DATA_DIR))

        execute(
            "INSERT INTO candidates (name, party, symbol_path, created_at) VALUES (?,?,?,?)",
            (name, party, symbol_path, now_iso()),
        )
        log_event("ADD_CANDIDATE", name=name, party=party)
        flash(f"Candidate '{name}' added.", "success")
        return redirect(url_for("admin.candidates"))

    rows = fetch_all("SELECT * FROM candidates ORDER BY created_at DESC")
    return render_template("admin/candidates.html", candidates=rows)


@bp.post("/candidates/<int:cid>/delete")
@admin_required
def delete_candidate(cid: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM votes      WHERE candidate_id = ?", (cid,))
        conn.execute("DELETE FROM candidates WHERE id = ?", (cid,))
    log_event("DELETE_CANDIDATE", candidate_id=cid)
    flash("Candidate deleted.", "success")
    return redirect(url_for("admin.candidates"))


# -------- Show results on ESP32 ------------------------------------------

@bp.post("/show_results")
@admin_required
def show_results():
    summary = election_summary()
    log_event("SHOW_RESULTS", **summary)
    esp32.send(
        "RESULTS",
        totals=summary["totals"],
        candidates=summary["candidates"],
        total_votes=summary["total_votes"],
        winner=summary["winner"] or "",
        winner_party=summary["winner_party"] or "",
        tie=summary["tie"],
    )
    if summary["total_votes"] == 0:
        flash("No votes cast yet — sent empty results to ESP32.", "info")
    elif summary["tie"]:
        flash(f"Sent results to ESP32 (tie at top, {summary['total_votes']} votes).", "info")
    else:
        flash(f"Sent results to ESP32 — winner: {summary['winner']}.", "success")
    return redirect(url_for("admin.dashboard"))


# -------- Reset election --------------------------------------------------

@bp.post("/reset")
@admin_required
def reset_election():
    with get_conn() as conn:
        conn.execute("DELETE FROM votes")
        conn.execute("UPDATE voters SET has_voted = 0")
    log_event("RESET")
    esp32.send("RESET")
    flash("Election reset. All votes cleared, voters retained.", "success")
    return redirect(url_for("admin.dashboard"))


# -------- Serve uploaded images ------------------------------------------

@bp.route("/file/<path:relpath>")
def data_file(relpath: str):
    """Serve images stored in ./data (face snapshots, candidate symbols)."""
    from flask import send_from_directory
    return send_from_directory(Config.DATA_DIR, relpath)
