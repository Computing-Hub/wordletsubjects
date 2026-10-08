"""Classes, anonymous student codes and the progress dashboard."""
import csv
import io
import re
from collections import OrderedDict, defaultdict
from datetime import timedelta

from flask import (Blueprint, Response, abort, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required

from .. import banks
from ..models import Attempt, AttemptItem, SchoolClass, StudentCode, db, now

bp = Blueprint("classes", __name__, url_prefix="/classes")
MAX_CODES = 40
PERIODS = [("7", "Last 7 days"), ("30", "Last 30 days"), ("90", "Last 90 days"), ("all", "All time")]


def prefix_for(name):
    """'9B Science' -> '9B'. Keeps codes short and recognisable."""
    first = re.sub(r"[^A-Za-z0-9]", "", (name.split() or [""])[0]).upper()
    return first[:4] or "C"


def get_class(cid):
    c = db.session.get(SchoolClass, cid)
    if not c:
        abort(404)
    if c.teacher_id != current_user.id and not current_user.is_admin:
        abort(403)
    return c


@bp.route("/")
@login_required
def index():
    q = SchoolClass.query if current_user.is_admin else SchoolClass.query.filter_by(teacher_id=current_user.id)
    classes = q.order_by(SchoolClass.archived, SchoolClass.name).all()
    counts = dict(db.session.query(Attempt.class_id, db.func.count(Attempt.id))
                  .filter(Attempt.received_at >= now() - timedelta(days=7)).group_by(Attempt.class_id).all())
    return render_template("classes_index.html", classes=classes, week_counts=counts)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        name = re.sub(r"\s+", " ", request.form.get("name", "")).strip()[:80]
        sid = request.form.get("subject", "")
        try:
            n = int(request.form.get("size", "0"))
        except ValueError:
            n = 0
        if not name:
            flash("Give the class a name, such as '9B Science'.", "error")
        elif not 1 <= n <= MAX_CODES:
            flash(f"Choose between 1 and {MAX_CODES} students.", "error")
        elif sid and not banks.subject(sid):
            flash("Choose a subject from the list.", "error")
        else:
            c = SchoolClass(name=name, prefix=prefix_for(name), subject_id=sid, teacher_id=current_user.id)
            db.session.add(c)
            db.session.flush()
            for _ in range(n):
                db.session.add(StudentCode(code=StudentCode.generate(c.prefix), class_id=c.id))
                db.session.flush()
            db.session.commit()
            flash(f"Created {name} with {n} codes. Print the list and write a name next to each code.", "ok")
            return redirect(url_for("classes.codes", cid=c.id))
    return render_template("class_new.html", subjects=banks.subjects(), max_codes=MAX_CODES)


@bp.route("/<int:cid>/codes")
@login_required
def codes(cid):
    return render_template("class_codes.html", c=get_class(cid))


@bp.route("/<int:cid>/codes/add", methods=["POST"])
@login_required
def add_codes(cid):
    c = get_class(cid)
    try:
        n = int(request.form.get("n", "1"))
    except ValueError:
        n = 1
    n = max(1, min(n, MAX_CODES - len(c.codes)))
    if len(c.codes) >= MAX_CODES:
        flash(f"A class can have at most {MAX_CODES} codes.", "error")
    else:
        for _ in range(n):
            db.session.add(StudentCode(code=StudentCode.generate(c.prefix), class_id=c.id))
            db.session.flush()
        db.session.commit()
        flash(f"Added {n} code{'s' if n > 1 else ''}.", "ok")
    return redirect(url_for("classes.codes", cid=cid))


@bp.route("/<int:cid>/codes/<int:code_id>/toggle", methods=["POST"])
@login_required
def toggle_code(cid, code_id):
    c = get_class(cid)
    sc = StudentCode.query.filter_by(id=code_id, class_id=c.id).first_or_404()
    sc.active = not sc.active
    db.session.commit()
    flash(f"{sc.code} {'switched back on' if sc.active else 'switched off. Results already sent are kept'}.", "ok")
    return redirect(url_for("classes.codes", cid=cid))


@bp.route("/<int:cid>/archive", methods=["POST"])
@login_required
def archive(cid):
    c = get_class(cid)
    c.archived = not c.archived
    for sc in c.codes:
        sc.active = not c.archived
    db.session.commit()
    flash(f"{c.name} {'archived: its codes no longer send results' if c.archived else 'restored'}.", "ok")
    return redirect(url_for("classes.index"))


@bp.route("/<int:cid>/delete", methods=["POST"])
@login_required
def delete(cid):
    c = get_class(cid)
    if request.form.get("confirm_name", "").strip() != c.name:
        flash("Type the class name exactly to confirm deleting it.", "error")
        return redirect(url_for("classes.dashboard", cid=cid))
    ids = db.session.query(Attempt.id).filter(Attempt.class_id == c.id)
    AttemptItem.query.filter(AttemptItem.attempt_id.in_(ids)).delete(synchronize_session=False)
    Attempt.query.filter_by(class_id=c.id).delete(synchronize_session=False)
    db.session.delete(c)
    db.session.commit()
    flash(f"Deleted {c.name} and all its results.", "ok")
    return redirect(url_for("classes.index"))


def _attempts(c, sid, period):
    q = Attempt.query.filter_by(class_id=c.id)
    if sid:
        q = q.filter_by(subject_id=sid)
    if period != "all":
        q = q.filter(Attempt.received_at >= now() - timedelta(days=int(period)))
    return q.order_by(Attempt.played_at).all()


def summarise(c, attempts, sid):
    """Work out the grid, the most-missed terms and weekly activity."""
    if sid:
        cols = list(dict.fromkeys(banks.topics(sid) + sorted({i.topic for a in attempts for i in a.items})))
        col_of = lambda a, i: i.topic
    else:
        cols = list(dict.fromkeys(banks.subject_name(a.subject_id) for a in attempts))
        col_of = lambda a, i: banks.subject_name(a.subject_id)

    cells = defaultdict(lambda: [0, 0])      # (code, col) -> [points, possible]
    per_code = defaultdict(lambda: {"sets": 0, "last": None, "points": 0, "possible": 0})
    terms = defaultdict(lambda: {"n": 0, "word": 0, "question": 0, "topic": ""})
    for a in attempts:
        pc = per_code[a.code.code]
        pc["sets"] += 1
        pc["last"] = max(pc["last"], a.played_at) if pc["last"] else a.played_at
        for i in a.items:
            pts = int(i.solved) + int(i.follow)
            cell = cells[(a.code.code, col_of(a, i))]
            cell[0] += pts
            cell[1] += 2
            pc["points"] += pts
            pc["possible"] += 2
            t = terms[(a.subject_id, i.term)]
            t["n"] += 1
            t["word"] += not i.solved
            t["question"] += not i.follow
            t["topic"] = i.topic
    used_cols = [col for col in cols if any(k[1] == col for k in cells)]

    codes = [sc.code for sc in c.codes]
    codes += sorted(k for k in per_code if k not in codes)
    rows = []
    for code in codes:
        pc = per_code.get(code, {"sets": 0, "last": None, "points": 0, "possible": 0})
        rows.append({
            "code": code,
            "active": next((sc.active for sc in c.codes if sc.code == code), False),
            "sets": pc["sets"], "last": pc["last"],
            "overall": round(100 * pc["points"] / pc["possible"]) if pc["possible"] else None,
            "cells": [(round(100 * cells[(code, col)][0] / cells[(code, col)][1]), cells[(code, col)][1] // 2)
                      if cells[(code, col)][1] else None for col in used_cols],
        })

    min_n = 3 if any(t["n"] >= 3 for t in terms.values()) else 1
    missed = sorted(
        ({"subject": banks.subject_name(s), "term": term, "topic": t["topic"], "n": t["n"],
          "word": round(100 * t["word"] / t["n"]), "question": round(100 * t["question"] / t["n"]),
          "miss": (t["word"] + t["question"]) / (2 * t["n"])}
         for (s, term), t in terms.items() if t["n"] >= min_n),
        key=lambda m: (-m["miss"], -m["n"]))
    missed = [m for m in missed if m["miss"] > 0][:15]

    today = now().date()
    start = today - timedelta(days=today.weekday())  # this Monday
    weeks = OrderedDict(((start - timedelta(weeks=w)), 0) for w in range(7, -1, -1))
    for a in attempts:
        d = a.played_at.date()
        wk = d - timedelta(days=d.weekday())
        if wk in weeks:
            weeks[wk] += 1
    active_codes = sum(1 for r in rows if r["sets"])
    return {"cols": used_cols, "rows": rows, "missed": missed, "weeks": list(weeks.items()),
            "total_sets": len(attempts), "active_codes": active_codes}


@bp.route("/<int:cid>")
@login_required
def dashboard(cid):
    c = get_class(cid)
    sid = request.args.get("subject", c.subject_id or "")
    if sid and not banks.subject(sid):
        sid = ""
    period = request.args.get("period", "30")
    if period not in dict(PERIODS):
        period = "30"
    stats = summarise(c, _attempts(c, sid, period), sid)
    return render_template("class_dashboard.html", c=c, sid=sid, period=period, periods=PERIODS,
                           subjects=banks.subjects(), s=stats)


@bp.route("/<int:cid>/export.csv")
@login_required
def export(cid):
    """Every term answered, one row each. Codes only, no names."""
    c = get_class(cid)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["code", "played_at", "subject", "topic_chosen", "term", "term_topic", "word_solved", "question_right"])
    for a in Attempt.query.filter_by(class_id=c.id).order_by(Attempt.played_at):
        for i in a.items:
            w.writerow([a.code.code, a.played_at.strftime("%Y-%m-%d %H:%M"), banks.subject_name(a.subject_id),
                        a.topic_choice, i.term, i.topic, int(i.solved), int(i.follow)])
    safe = re.sub(r"[^A-Za-z0-9]+", "-", c.name).strip("-") or "class"
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{safe}-results.csv"'})
