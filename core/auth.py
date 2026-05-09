"""Session-based access control."""
from functools import wraps

from flask import flash, redirect, session, url_for


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)

    return wrapper


def voter_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("voter_id"):
            flash("Please scan your face first.", "warning")
            return redirect(url_for("voter.login"))
        return view(*args, **kwargs)

    return wrapper
