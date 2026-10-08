"""Key Terms teacher site.

Teachers log in to add terms (sent to GitHub as a pull request for review),
create classes with anonymous student codes, and see how their classes are
doing. The student game itself stays a static, offline PWA on GitHub Pages;
it only talks to this site to send finished sets.

Settings come from environment variables (see server/README.md).
"""
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import click
from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .models import Attempt, Teacher, db, now

login_manager = LoginManager()
csrf = CSRFProtect()
SERVER_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = SERVER_DIR.parent


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    """WAL lets the game's writes and the dashboard's reads happen together;
    busy_timeout makes simultaneous writes wait their turn instead of failing."""
    if isinstance(dbapi_conn, sqlite3.Connection):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def create_app(test_config=None):
    app = Flask(__name__, instance_path=str(SERVER_DIR / "instance"))
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    env = os.environ.get
    app.config.update(
        SECRET_KEY=env("SECRET_KEY", "dev-only-change-me"),
        SQLALCHEMY_DATABASE_URI=env("DATABASE_URL", f"sqlite:///{Path(app.instance_path) / 'keyterms.db'}"),
        GITHUB_TOKEN=env("KEYTERMS_GITHUB_TOKEN", ""),
        GITHUB_REPO=env("GITHUB_REPO", "Computing-Hub/wordletsubjects"),
        GITHUB_BRANCH=env("GITHUB_BRANCH", "main"),
        # Sites allowed to send results, i.e. where the game is hosted.
        ALLOWED_ORIGINS=[o.strip().rstrip("/") for o in env("ALLOWED_ORIGINS", "https://computing-hub.github.io").split(",") if o.strip()],
        BANKS_JS_PATH=env("BANKS_JS_PATH", str(REPO_DIR / "banks" / "banks.js")),
        SCHOOL_NAME=env("SCHOOL_NAME", "Le Rocquier School"),
        GAME_URL=env("GAME_URL", "https://computing-hub.github.io/wordletsubjects/"),
        RESULTS_KEEP_DAYS=int(env("RESULTS_KEEP_DAYS", "400")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=env("FLASK_DEBUG", "") not in ("1", "true"),
        REMEMBER_COOKIE_DURATION=timedelta(days=14),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=256 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if app.config["SECRET_KEY"] == "dev-only-change-me" and not (app.debug or app.testing):
        app.logger.warning("SECRET_KEY is not set. Set it before going live.")

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = None

    from .views import admin, api, auth, classes, terms
    for bp in (auth.bp, terms.bp, classes.bp, admin.bp, api.bp):
        app.register_blueprint(bp)
    csrf.exempt(api.bp)  # the game can't send a CSRF token; codes and CORS protect it instead

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        return resp

    @app.context_processor
    def globals_for_templates():
        from . import banks
        return {"school_name": app.config["SCHOOL_NAME"], "subject_name": banks.subject_name}

    register_commands(app)
    with app.app_context():
        db.create_all()
    return app


@login_manager.user_loader
def _load_user(uid):
    return db.session.get(Teacher, int(uid))


def register_commands(app):
    @app.cli.command("create-admin")
    @click.argument("username")
    @click.option("--name", default="", help="Name shown to other teachers")
    def create_admin(username, name):
        """Create the first admin account (asks for a password)."""
        if Teacher.query.filter_by(username=username.lower()).first():
            raise click.ClickException(f"'{username}' already exists.")
        pw = click.prompt("Password (10+ characters)", hide_input=True, confirmation_prompt=True)
        if len(pw) < 10:
            raise click.ClickException("Use at least 10 characters.")
        t = Teacher(username=username.lower(), display_name=name or username, is_admin=True,
                    subjects="*", must_change_password=False)
        t.set_password(pw)
        db.session.add(t)
        db.session.commit()
        click.echo(f"Admin '{t.username}' created.")

    @app.cli.command("backup")
    @click.option("--keep", default=14, help="How many daily backups to keep")
    def backup(keep):
        """Copy the database to instance/backups with today's date."""
        uri = app.config["SQLALCHEMY_DATABASE_URI"]
        if not uri.startswith("sqlite:///"):
            raise click.ClickException("Backups here only handle SQLite. Use your database host's backups.")
        src = Path(uri.removeprefix("sqlite:///"))
        dest_dir = Path(app.instance_path) / "backups"
        dest_dir.mkdir(exist_ok=True)
        dest = dest_dir / f"keyterms-{datetime.now():%Y-%m-%d}.db"
        with sqlite3.connect(src) as s, sqlite3.connect(dest) as d:
            s.backup(d)  # safe while the site is running, unlike copying the file
        old = sorted(dest_dir.glob("keyterms-*.db"))[:-keep]
        for f in old:
            f.unlink()
        click.echo(f"Backed up to {dest} ({len(old)} old backup(s) removed).")

    @app.cli.command("purge-results")
    @click.option("--days", default=None, type=int, help="Delete results older than this (default RESULTS_KEEP_DAYS)")
    def purge_results(days):
        """Delete old results, so data isn't kept longer than needed."""
        days = days or app.config["RESULTS_KEEP_DAYS"]
        cutoff = now() - timedelta(days=days)
        old = Attempt.query.filter(Attempt.received_at < cutoff).all()
        for a in old:
            db.session.delete(a)
        db.session.commit()
        click.echo(f"Deleted {len(old)} sets older than {days} days.")
