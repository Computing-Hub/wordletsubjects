"""Admin: teacher accounts and which subjects each one may add terms to."""
import re
import secrets
from functools import wraps

import sqlite3
from datetime import datetime
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request,
                   send_file, url_for)
from flask_login import current_user, login_required

from .. import banks
from ..models import Draft, Submission, Teacher, db

bp = Blueprint("admin", __name__, url_prefix="/admin")
WORDS = ["amber", "brook", "cedar", "delta", "ember", "fjord", "grove", "harbour", "islet", "jetty",
         "kelp", "lagoon", "maple", "nectar", "orchard", "pebble", "quartz", "reef", "spruce", "tide"]


def admin_required(f):
    @wraps(f)
    @login_required
    def inner(*a, **kw):
        if not current_user.is_admin:
            abort(403)
        return f(*a, **kw)
    return inner


def temp_password():
    """Easy to read out or write down; the teacher must change it on first login."""
    return f"{secrets.choice(WORDS)}-{secrets.choice(WORDS)}-{secrets.randbelow(900) + 100}"


def _subjects_from_form():
    picked = request.form.getlist("subjects")
    if "*" in picked:
        return "*"
    valid = {s[0] for s in banks.subjects()}
    return ",".join(s for s in picked if s in valid)


@bp.route("/")
@admin_required
def index():
    teachers = Teacher.query.order_by(Teacher.active.desc(), Teacher.display_name).all()
    open_subs = Submission.query.filter_by(status="open").order_by(Submission.created_at.desc()).all()
    waiting = db.session.query(Draft.teacher_id, db.func.count(db.distinct(Draft.entry_id))) \
        .filter(Draft.submission_id.is_(None)).group_by(Draft.teacher_id).all()
    return render_template("admin.html", teachers=teachers, subjects=banks.subjects(),
                           open_subs=open_subs, waiting=dict(waiting))


@bp.route("/teachers/new", methods=["POST"])
@admin_required
def new_teacher():
    username = (request.form.get("username") or "").strip().lower()
    name = re.sub(r"\s+", " ", request.form.get("display_name", "")).strip()[:80]
    if not re.fullmatch(r"[a-z0-9._-]{3,40}", username):
        flash("Usernames need 3 to 40 letters, numbers, dots, dashes or underscores.", "error")
    elif Teacher.query.filter_by(username=username).first():
        flash(f"'{username}' is already taken.", "error")
    elif not name:
        flash("Enter the teacher's name as others should see it, e.g. 'Ms Jones'.", "error")
    else:
        pw = temp_password()
        t = Teacher(username=username, display_name=name, subjects=_subjects_from_form(),
                    is_admin=bool(request.form.get("is_admin")), must_change_password=True)
        t.set_password(pw)
        db.session.add(t)
        db.session.commit()
        flash(f"Created {name}. Username: {username} · Temporary password: {pw} "
              "(shown once; they choose their own when they first log in).", "secret")
    return redirect(url_for("admin.index"))


@bp.route("/teachers/<int:tid>", methods=["POST"])
@admin_required
def update_teacher(tid):
    t = db.session.get(Teacher, tid) or abort(404)
    action = request.form.get("action")
    if action == "subjects":
        t.subjects = _subjects_from_form()
        t.is_admin = bool(request.form.get("is_admin")) if t.id != current_user.id else True
        flash(f"Updated {t.display_name}.", "ok")
    elif action == "reset":
        pw = temp_password()
        t.set_password(pw)
        t.must_change_password = True
        flash(f"New temporary password for {t.display_name} ({t.username}): {pw}", "secret")
    elif action == "toggle":
        if t.id == current_user.id:
            flash("You can't switch off your own account.", "error")
        else:
            t.active = not t.active
            flash(f"{t.display_name} {'can log in again' if t.active else 'can no longer log in'}.", "ok")
    db.session.commit()
    return redirect(url_for("admin.index"))


@bp.route("/backup")
@admin_required
def backup():
    """Download a copy of the database (SQLite only). Keep it somewhere safe:
    it has teacher accounts and class results (codes, no names)."""
    uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
    if not uri.startswith("sqlite:///"):
        abort(404)
    src = Path(uri.removeprefix("sqlite:///"))
    dest_dir = src.parent / "backups"
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / f"keyterms-{datetime.now():%Y-%m-%d-%H%M}.db"
    with sqlite3.connect(src) as s, sqlite3.connect(dest) as d:
        s.backup(d)
    for old in sorted(dest_dir.glob("keyterms-*.db"))[:-14]:
        old.unlink()
    return send_file(dest, as_attachment=True, download_name=dest.name)
