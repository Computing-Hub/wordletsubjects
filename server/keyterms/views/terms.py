"""Adding terms: teachers fill in a form, terms collect as drafts, and
"Send for review" turns a subject's drafts into one GitHub pull request."""
import re
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, redirect, render_template,
                   request, url_for)
from flask_login import current_user, login_required

from .. import banks, github
from ..models import Draft, Submission, db, now
from ..validation import (FU_FIELDS, MAX_FOLLOWUPS, check_entry, entry_rows, form_to_entry,
                          rows_to_csv, term_key)

bp = Blueprint("terms", __name__, url_prefix="/terms")


def my_subjects():
    return [s for s in banks.subjects() if current_user.can_edit(s[0])]


def need_subject(sid):
    if not banks.subject(sid):
        abort(404)
    if not current_user.can_edit(sid):
        abort(403)


def pending_keys(sid, exclude_entry=None):
    """New terms waiting in drafts or open pull requests (any teacher)."""
    q = Draft.query.outerjoin(Submission).filter(
        Draft.subject_id == sid, Draft.clue != "",
        (Draft.submission_id.is_(None) & (Draft.teacher_id == current_user.id)) | (Submission.status == "open"))
    if exclude_entry:
        q = q.filter(Draft.entry_id != exclude_entry)
    return {term_key(d.term) for d in q}


def entries(drafts):
    """Group draft rows into entries (a term plus its questions)."""
    out = OrderedDict()
    for d in sorted(drafts, key=lambda d: (d.created_at, d.entry_id, d.position)):
        out.setdefault(d.entry_id, []).append(d)
    return list(out.values())


def refresh_statuses(subs):
    """Ask GitHub whether open pull requests have been merged, at most every 5 minutes."""
    if not github.configured():
        return
    changed = False
    for s in subs:
        if s.status == "open" and s.pr_number and (not s.checked_at or now() - s.checked_at > timedelta(minutes=5)):
            try:
                s.status = github.pull_request_status(s.pr_number)
            except github.GitHubError as e:
                current_app.logger.warning("PR status check failed: %s", e)
            s.checked_at = now()
            changed = True
    if changed:
        db.session.commit()


@bp.route("/")
@login_required
def index():
    drafts = Draft.query.filter_by(teacher_id=current_user.id, submission_id=None).all()
    by_subject = OrderedDict()
    for e in entries(drafts):
        by_subject.setdefault(e[0].subject_id, []).append(e)
    subs = (Submission.query.filter_by(teacher_id=current_user.id)
            .order_by(Submission.created_at.desc()).limit(20).all())
    refresh_statuses(subs)
    return render_template("terms_index.html", subjects=my_subjects(), by_subject=by_subject,
                           submissions=subs, github_ready=github.configured())


def _form_context(sid, mode, data, entry_id=None, errors=(), warnings=()):
    pend = Draft.query.filter(Draft.subject_id == sid, Draft.clue != "", Draft.submission_id.is_(None),
                              Draft.teacher_id == current_user.id).all()
    existing_terms = sorted(set(banks.terms(sid)) | {d.term for d in pend}, key=str.lower)
    topics = list(dict.fromkeys(banks.topics(sid) + [d.topic for d in pend if d.topic]))
    return dict(sid=sid, mode=mode, data=data, entry_id=entry_id, errors=errors, warnings=warnings,
                topics=topics, existing_terms=existing_terms, fu_fields=FU_FIELDS,
                max_followups=MAX_FOLLOWUPS)


def _blank():
    return {"term": "", "clue": "", "topic": "", "tier": "F", "notes": "",
            "followups": [dict.fromkeys(FU_FIELDS, "")]}


def _save(sid, mode, entry_id=None):
    """Validate the posted form and store it as drafts. Returns a response or None."""
    data = form_to_entry(request.form)
    existing = {term_key(t) for t in banks.terms(sid)}
    errors, warnings = check_entry(data, mode, existing, pending_keys(sid, exclude_entry=entry_id))
    if errors or (warnings and not request.form.get("confirm")):
        ctx = _form_context(sid, mode, data, entry_id, errors, warnings)
        return render_template("term_form.html", **ctx), 422 if errors else 200
    if entry_id:
        Draft.query.filter_by(entry_id=entry_id, teacher_id=current_user.id, submission_id=None).delete()
    eid = entry_id or uuid.uuid4().hex
    for pos, row in enumerate(entry_rows(data, mode)):
        db.session.add(Draft(teacher_id=current_user.id, subject_id=sid, entry_id=eid, position=pos,
                             notes=data["notes"] if pos == 0 else "", **row))
    db.session.commit()
    n = len(data["followups"])
    what = f"'{data['term']}' with {n} question{'s' if n > 1 else ''}" if mode == "new" else \
        f"{n} more question{'s' if n > 1 else ''} for '{data['term']}'"
    flash(f"Saved {what} to your drafts.", "ok")
    if request.form.get("then") == "another":
        return redirect(url_for("terms.new", subject=sid, mode="new"))
    return redirect(url_for("terms.index"))


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    sid = request.values.get("subject", "")
    need_subject(sid)
    mode = "extra" if request.values.get("mode") == "extra" else "new"
    if request.method == "POST":
        return _save(sid, mode)
    data = _blank()
    if mode == "extra":
        data["term"] = request.args.get("term", "")
    return render_template("term_form.html", **_form_context(sid, mode, data))


def _my_entry(entry_id):
    rows = (Draft.query.filter_by(entry_id=entry_id, teacher_id=current_user.id, submission_id=None)
            .order_by(Draft.position).all())
    if not rows:
        abort(404)
    return rows


@bp.route("/entry/<entry_id>/edit", methods=["GET", "POST"])
@login_required
def edit(entry_id):
    rows = _my_entry(entry_id)
    sid, first = rows[0].subject_id, rows[0]
    need_subject(sid)
    mode = "new" if first.clue else "extra"
    if request.method == "POST":
        return _save(sid, mode, entry_id)
    data = {"term": first.term, "clue": first.clue, "topic": first.topic, "tier": first.tier or "F",
            "notes": first.notes, "followups": [{f: getattr(r, f) for f in FU_FIELDS} for r in rows]}
    return render_template("term_form.html", **_form_context(sid, mode, data, entry_id))


@bp.route("/entry/<entry_id>/delete", methods=["POST"])
@login_required
def delete(entry_id):
    rows = _my_entry(entry_id)
    term = rows[0].term
    for r in rows:
        db.session.delete(r)
    db.session.commit()
    flash(f"Deleted '{term}' from your drafts.", "ok")
    return redirect(url_for("terms.index"))


@bp.route("/send/<sid>", methods=["POST"])
@login_required
def send(sid):
    need_subject(sid)
    drafts = Draft.query.filter_by(teacher_id=current_user.id, subject_id=sid, submission_id=None).all()
    if not drafts:
        flash("There's nothing to send for that subject.", "error")
        return redirect(url_for("terms.index"))
    groups = entries(drafts)
    rows = [{"term": d.term, "clue": d.clue, "topic": d.topic, "tier": d.tier, "notes": d.notes,
             **{f: getattr(d, f) for f in FU_FIELDS}} for g in groups for d in g]
    stamp = datetime.now()
    user = re.sub(r"[^a-z0-9]", "", current_user.username.lower()) or "teacher"
    path = f"banks/inbox/{sid}/{stamp:%Y-%m-%d-%H%M%S}-{user}.csv"
    name = banks.subject_name(sid)
    new_terms = [g[0].term for g in groups if g[0].clue]
    extra_terms = [g[0].term for g in groups if not g[0].clue]
    sub = Submission(teacher_id=current_user.id, subject_id=sid, rows=len(rows), path=path,
                     terms=", ".join(new_terms + extra_terms))

    if github.configured():
        title = f"{name}: {len(groups)} entr{'y' if len(groups) == 1 else 'ies'} from {current_user.display_name}"
        body = _pr_body(name, groups, request.form.get("message", "").strip())
        try:
            sub.pr_number, sub.pr_url = github.open_pull_request(
                path, rows_to_csv(rows), f"inbox/{sid}-{stamp:%Y%m%d-%H%M%S}-{user}", title, body)
        except github.GitHubError as e:
            current_app.logger.error("Sending to GitHub failed: %s", e)
            flash("Couldn't send to GitHub, so your drafts are still here. Try again later, "
                  f"or tell the site admin. ({e})", "error")
            return redirect(url_for("terms.index"))
    else:
        # No GitHub token yet (e.g. testing): keep the file on the server instead.
        out = Path(current_app.instance_path) / "outbox" / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rows_to_csv(rows), encoding="utf-8")
        sub.status = "local"
    db.session.add(sub)
    db.session.flush()
    for d in drafts:
        d.submission_id = sub.id
    db.session.commit()
    flash(f"Sent {len(groups)} entr{'y' if len(groups) == 1 else 'ies'} for {name} for review. "
          "They'll appear in the game once approved.", "ok")
    return redirect(url_for("terms.index"))


def _pr_body(subject, groups, message):
    lines = [f"Sent from the Key Terms teacher site by **{current_user.display_name}** "
             f"(`{current_user.username}`).", ""]
    if message:
        lines += ["**Message for the reviewer:**", "", "> " + message.replace("\n", "\n> "), ""]
    lines += [f"### {subject}", ""]
    for g in groups:
        first = g[0]
        n = len(g)
        if first.clue:
            lines.append(f"- **{first.term}** (new, {first.topic}, tier {first.tier}): {first.clue}")
        else:
            lines.append(f"- **{first.term}**: {n} more question{'s' if n > 1 else ''}")
        for d in g:
            lines.append(f"  - {d.question} → *{d.correct_answer}*")
        if first.notes:
            lines.append(f"  - Note: {first.notes}")
    lines += ["", "The checks below run `build_banks.py --check` on this file. "
              "Merge to publish; the site rebuilds itself. "
              "Run `merge_inbox.py` occasionally to move approved terms into `terms.xlsx`."]
    return "\n".join(lines)
