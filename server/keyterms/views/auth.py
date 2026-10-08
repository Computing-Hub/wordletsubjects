"""Logging in and out, and changing your password."""
import time
from collections import defaultdict

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..models import Teacher, db

bp = Blueprint("auth", __name__)

# Slow down password guessing: 5 failures for a username locks it for 15 minutes.
_failures = defaultdict(list)
LOCK_AFTER, LOCK_SECONDS = 5, 15 * 60


def _locked(username):
    recent = [t for t in _failures[username] if time.time() - t < LOCK_SECONDS]
    _failures[username] = recent
    return len(recent) >= LOCK_AFTER


def _safe_next(target):
    return target if target and target.startswith("/") and not target.startswith("//") else None


@bp.before_app_request
def require_new_password():
    """Teachers given a temporary password must choose their own first."""
    if (current_user.is_authenticated and current_user.must_change_password
            and request.endpoint not in ("auth.account", "auth.logout", "static")):
        return redirect(url_for("auth.account"))


@bp.route("/", methods=["GET"])
def home():
    if current_user.is_authenticated:
        return redirect(url_for("terms.index"))
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("terms.index"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        if _locked(username):
            flash("Too many attempts. Wait 15 minutes and try again.", "error")
            return render_template("login.html", username=username), 429
        t = Teacher.query.filter_by(username=username).first()
        if t and t.active and t.check_password(password):
            _failures.pop(username, None)
            login_user(t, remember=bool(request.form.get("remember")))
            return redirect(_safe_next(request.args.get("next")) or url_for("terms.index"))
        _failures[username].append(time.time())
        flash("That username and password don't match.", "error")
        return render_template("login.html", username=username), 401
    return render_template("login.html", username="")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        current = request.form.get("current") or ""
        new, again = request.form.get("new") or "", request.form.get("again") or ""
        if not current_user.check_password(current):
            flash("Your current password isn't right.", "error")
        elif len(new) < 10:
            flash("Use at least 10 characters for the new password.", "error")
        elif new != again:
            flash("The two new passwords don't match.", "error")
        elif new == current:
            flash("Choose a password different from the current one.", "error")
        else:
            current_user.set_password(new)
            current_user.must_change_password = False
            db.session.commit()
            flash("Password changed.", "ok")
            return redirect(url_for("terms.index"))
    return render_template("account.html")
