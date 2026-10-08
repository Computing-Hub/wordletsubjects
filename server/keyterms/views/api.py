"""The two calls the game makes: check a class code, and send finished sets.

No logins and no names: a set is only accepted for a code that exists and is
switched on, and only from the sites listed in ALLOWED_ORIGINS.
"""
import re
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request

from .. import banks
from ..models import Attempt, AttemptItem, StudentCode, db, now

bp = Blueprint("api", __name__, url_prefix="/api")
MAX_BATCH, MAX_ITEMS, MAX_PER_HOUR = 20, 30, 60


@bp.after_request
def cors(resp):
    origin = (request.headers.get("Origin") or "").rstrip("/")
    if origin and origin in current_app.config["ALLOWED_ORIGINS"]:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Max-Age"] = "86400"
    resp.headers["Vary"] = "Origin"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/<path:_any>", methods=["OPTIONS"])
def preflight(_any):
    return "", 204


def norm_code(code):
    return re.sub(r"[^A-Z0-9-]", "", (code or "").upper().replace(" ", ""))[:12]


def live_code(code):
    sc = StudentCode.query.filter_by(code=norm_code(code)).first()
    if sc and sc.active and not sc.school_class.archived:
        return sc
    return None


@bp.route("/code/<code>")
def check_code(code):
    sc = live_code(code)
    if not sc:
        return jsonify(ok=False, error="That code isn't recognised. Check it with your teacher."), 404
    return jsonify(ok=True, code=sc.code, class_name=sc.school_class.name)


def _when(s):
    """The time the set was played, as naive UTC; falls back to now if odd."""
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if t.tzinfo:
            t = t.astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        return now()
    return t if now() - timedelta(days=60) <= t <= now() + timedelta(minutes=5) else now()


def _text(v, n=120):
    return str(v or "").strip()[:n]


@bp.route("/results", methods=["POST"])
def results():
    data = request.get_json(silent=True, force=True)
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        return jsonify(ok=False, error="Expected {results: [...]}"), 400
    accepted, rejected = [], []
    for r in data["results"][:MAX_BATCH]:
        if not isinstance(r, dict):
            continue
        cid = _text(r.get("client_id"), 40)
        if not re.fullmatch(r"[A-Za-z0-9-]{8,40}", cid):
            rejected.append({"client_id": cid, "reason": "bad id", "retry": False})
            continue
        if Attempt.query.filter_by(client_id=cid).first():
            accepted.append(cid)  # already have it: resending is harmless
            continue
        sc = live_code(r.get("code"))
        if not sc:
            rejected.append({"client_id": cid, "reason": "code", "retry": False})
            continue
        sid = _text(r.get("subject"), 60)
        items = r.get("items") if isinstance(r.get("items"), list) else []
        items = [i for i in items[:MAX_ITEMS] if isinstance(i, dict) and _text(i.get("term"))]
        if not banks.subject(sid) or not items:
            rejected.append({"client_id": cid, "reason": "data", "retry": False})
            continue
        recent = Attempt.query.filter(Attempt.code_id == sc.id,
                                      Attempt.received_at >= now() - timedelta(hours=1)).count()
        if recent >= MAX_PER_HOUR:
            rejected.append({"client_id": cid, "reason": "busy", "retry": True})
            continue
        a = Attempt(client_id=cid, code_id=sc.id, class_id=sc.class_id, subject_id=sid,
                    topic_choice=_text(r.get("topic")), played_at=_when(r.get("played_at")))
        for i in items:
            a.items.append(AttemptItem(term=_text(i.get("term")), topic=_text(i.get("topic")),
                                       solved=bool(i.get("solved")), follow=bool(i.get("follow"))))
        db.session.add(a)
        db.session.commit()
        accepted.append(cid)
    return jsonify(ok=True, accepted=accepted, rejected=rejected)
