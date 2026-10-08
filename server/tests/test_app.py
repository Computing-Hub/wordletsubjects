"""Run from the server folder:  python -m pytest -q"""
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from keyterms import create_app, github
from keyterms.models import Attempt, SchoolClass, StudentCode, Submission, Teacher, db

REPO = Path(__file__).resolve().parents[2]
ORIGIN = "https://computing-hub.github.io"


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "GITHUB_TOKEN": "",
        "SESSION_COOKIE_SECURE": False,
    })
    app.instance_path = str(tmp_path)
    with app.app_context():
        admin = Teacher(username="admin", display_name="Head of CS", is_admin=True, subjects="*",
                        must_change_password=False)
        admin.set_password("correct horse battery")
        jones = Teacher(username="sjones", display_name="Ms Jones", subjects="biology",
                        must_change_password=False)
        jones.set_password("biology rocks 123")
        db.session.add_all([admin, jones])
        db.session.commit()
    from keyterms.views import auth
    auth._failures.clear()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, user="sjones", pw="biology rocks 123"):
    return client.post("/login", data={"username": user, "password": pw})


NEW_TERM = {
    "term": "Mitochondria", "clue": "Where aerobic respiration happens in a cell.",
    "topic": "Cell biology", "tier": "F", "notes": "Paper 1",
    "question_1": "What does it release?", "correct_answer_1": "Energy",
    "wrong_1_1": "Glucose", "wrong_2_1": "Oxygen", "wrong_3_1": "Chlorophyll",
    "explanation_1": "Respiration releases energy from glucose.",
    "question_2": "Which cells have the most?", "correct_answer_2": "Muscle cells",
    "wrong_1_2": "Red blood cells", "wrong_2_2": "Xylem cells", "wrong_3_2": "Skin cells",
    "explanation_2": "Muscles need lots of energy.",
}


# ---------- logging in ----------

def test_login_and_logout(client):
    assert client.get("/terms/").status_code == 302
    assert login(client, pw="wrong").status_code == 401
    r = login(client)
    assert r.status_code == 302 and r.headers["Location"].endswith("/terms/")
    assert b"Ms Jones" in client.get("/terms/").data
    client.post("/logout")
    assert client.get("/terms/").status_code == 302


def test_lockout_after_failures(client):
    for _ in range(5):
        login(client, user="admin", pw="nope")
    assert login(client, user="admin", pw="correct horse battery").status_code == 429


def test_temporary_password_must_be_changed(app, client):
    with app.app_context():
        t = Teacher(username="temp", display_name="Temp", subjects="")
        t.set_password("temporary-pass-1")
        db.session.add(t)
        db.session.commit()
    login(client, "temp", "temporary-pass-1")
    assert client.get("/classes/").headers["Location"].endswith("/account")
    r = client.post("/account", data={"current": "temporary-pass-1", "new": "a much better one", "again": "a much better one"})
    assert r.status_code == 302
    assert client.get("/classes/").status_code == 200


# ---------- adding terms ----------

def test_add_new_term_with_two_questions(app, client):
    login(client)
    r = client.post("/terms/new?subject=biology", data={**NEW_TERM, "subject": "biology"})
    assert r.status_code == 302
    page = client.get("/terms/").data.decode()
    assert "Mitochondria" in page and "Which cells have the most?" in page


def test_cannot_add_to_other_subject(client):
    login(client)
    assert client.get("/terms/new?subject=physics").status_code == 403


def test_duplicate_and_bad_terms_are_rejected(client):
    login(client)
    r = client.post("/terms/new?subject=biology", data={**NEW_TERM, "term": "Diffusion"})
    assert r.status_code == 422 and b"already in this word bank" in r.data
    r = client.post("/terms/new?subject=biology", data={**NEW_TERM, "term": "CO2"})
    assert r.status_code == 422 and b"only contain letters" in r.data
    r = client.post("/terms/new?subject=biology", data={**NEW_TERM, "wrong_1_1": "Energy"})
    assert r.status_code == 422 and b"must all be different" in r.data


def test_warning_needs_confirmation(client):
    login(client)
    data = {**NEW_TERM, "clue": "Mitochondria are where respiration happens."}
    r = client.post("/terms/new?subject=biology", data=data)
    assert r.status_code == 200 and b"gives it away" in r.data and b"Save anyway" in r.data
    assert client.post("/terms/new?subject=biology", data={**data, "confirm": "1"}).status_code == 302


def test_extra_questions_for_existing_term(client):
    login(client)
    data = {k: v for k, v in NEW_TERM.items() if k.endswith("_1")}
    r = client.post("/terms/new?subject=biology&mode=extra", data={**data, "term": "diffusion"})
    assert r.status_code == 302
    r = client.post("/terms/new?subject=biology&mode=extra", data={**data, "term": "Ribosome"})
    assert r.status_code == 422 and b"in this word bank yet" in r.data


def test_new_topic(client):
    login(client)
    r = client.post("/terms/new?subject=biology",
                    data={**NEW_TERM, "topic": "__new__", "new_topic": "Cell structure"})
    assert r.status_code == 302
    assert b"Cell structure" in client.get("/terms/").data


def test_edit_and_delete_draft(app, client):
    login(client)
    client.post("/terms/new?subject=biology", data=NEW_TERM)
    page = client.get("/terms/").data.decode()
    eid = re.search(r"/terms/entry/([0-9a-f]+)/edit", page).group(1)
    assert b"Mitochondria" in client.get(f"/terms/entry/{eid}/edit").data
    r = client.post(f"/terms/entry/{eid}/edit", data={**NEW_TERM, "clue": "The powerhouse of the cell."})
    assert r.status_code == 302
    assert b"powerhouse" in client.get("/terms/").data
    client.post(f"/terms/entry/{eid}/delete")
    assert f"/terms/entry/{eid}/edit" not in client.get("/terms/").data.decode()


def _copy_repo(tmp_path):
    dest = tmp_path / "repo"
    dest.mkdir()
    for name in ("build_banks.py", "sw.js", "index.html", "play.html", "manifest.json", "config.js"):
        shutil.copy(REPO / name, dest / name)
    for d in ("banks", "images", "icons"):
        shutil.copytree(REPO / d, dest / d, ignore=shutil.ignore_patterns("inbox"))
    return dest


def test_send_locally_and_csv_passes_the_build(app, client, tmp_path):
    """No GitHub token: the CSV is kept on the server. Then check that the file
    the form produced is accepted by build_banks.py exactly as the action runs it."""
    login(client)
    client.post("/terms/new?subject=biology", data=NEW_TERM)
    extra = {k: v for k, v in NEW_TERM.items() if k.endswith("_1")}
    client.post("/terms/new?subject=biology&mode=extra", data={**extra, "term": "Osmosis",
                                                                "question_1": "Is osmosis passive?",
                                                                "correct_answer_1": "Yes"})
    r = client.post("/terms/send/biology", data={"message": "Two for cells"})
    assert r.status_code == 302
    with app.app_context():
        sub = Submission.query.one()
        assert sub.status == "local" and sub.rows == 3
        csv_file = Path(app.instance_path) / "outbox" / sub.path
    assert csv_file.exists()

    repo = _copy_repo(tmp_path)
    dest = repo / sub.path
    dest.parent.mkdir(parents=True)
    shutil.copy(csv_file, dest)
    out = subprocess.run([sys.executable, "build_banks.py", "--check"], cwd=repo, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "Included 3 rows" in out.stdout
    # and it merges into the workbook cleanly
    shutil.copy(REPO / "merge_inbox.py", repo / "merge_inbox.py")
    out = subprocess.run([sys.executable, "merge_inbox.py"], cwd=repo, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "Check passed" in out.stdout and not dest.exists()


def test_send_to_github(app, client, monkeypatch):
    calls = {}

    def fake_open(path, content, branch, title, body):
        calls.update(path=path, content=content, branch=branch, title=title, body=body)
        return 42, "https://github.com/Computing-Hub/wordletsubjects/pull/42"

    app.config["GITHUB_TOKEN"] = "test"
    monkeypatch.setattr(github, "open_pull_request", fake_open)
    monkeypatch.setattr(github, "pull_request_status", lambda n: "merged")
    login(client)
    client.post("/terms/new?subject=biology", data=NEW_TERM)
    client.post("/terms/send/biology", data={"message": "Also: 'osmosis' clue has a typo"})
    assert calls["path"].startswith("banks/inbox/biology/") and calls["path"].endswith("-sjones.csv")
    assert calls["content"].splitlines()[0].startswith("term,clue,image,topic,tier,question")
    assert "Ms Jones" in calls["title"] and "typo" in calls["body"] and "Mitochondria" in calls["body"]
    assert b"In the game" in client.get("/terms/").data  # status refreshed from GitHub
    with app.app_context():
        assert Submission.query.one().pr_number == 42


def test_github_failure_keeps_drafts(app, client, monkeypatch):
    app.config["GITHUB_TOKEN"] = "test"

    def boom(*a):
        raise github.GitHubError("GitHub said 401: Bad credentials")
    monkeypatch.setattr(github, "open_pull_request", boom)
    login(client)
    client.post("/terms/new?subject=biology", data=NEW_TERM)
    r = client.post("/terms/send/biology", follow_redirects=True)
    assert b"Couldn" in r.data and b"Bad credentials" in r.data
    with app.app_context():
        assert Submission.query.count() == 0


# ---------- classes and results ----------

def make_class(app, client, size=5):
    login(client)
    client.post("/classes/new", data={"name": "9B Science", "size": size, "subject": "biology"})
    with app.app_context():
        c = SchoolClass.query.one()
        return c.id, [sc.code for sc in c.codes]


def result(code, solved=(True, False), client_id=None, subject="biology"):
    return {"client_id": client_id or uuid.uuid4().hex, "code": code, "subject": subject,
            "topic": "All topics", "played_at": "2026-10-08T15:00:00Z",
            "items": [{"term": "diffusion", "topic": "Cell biology", "solved": solved[0], "follow": True},
                      {"term": "osmosis", "topic": "Cell biology", "solved": solved[1], "follow": False}]}


def test_class_codes(app, client):
    cid, codes = make_class(app, client)
    assert len(codes) == 5 and len(set(codes)) == 5
    assert all(re.fullmatch(r"9B-[ACDEFHJKMNPRTUVWXY34679]{3}", c) for c in codes)
    page = client.get(f"/classes/{cid}/codes").data.decode()
    assert all(c in page for c in codes)


def test_code_check_api(app, client):
    cid, codes = make_class(app, client)
    r = client.get(f"/api/code/{codes[0].lower()}", headers={"Origin": ORIGIN})
    assert r.status_code == 200 and r.json["class_name"] == "9B Science"
    assert r.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert client.get("/api/code/9B-ZZZ").status_code == 404
    r = client.get(f"/api/code/{codes[0]}", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in r.headers


def test_preflight(client):
    r = client.options("/api/results", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"})
    assert r.status_code in (200, 204) and r.headers["Access-Control-Allow-Origin"] == ORIGIN


def test_results_accepted_once_and_bad_ones_rejected(app, client):
    cid, codes = make_class(app, client)
    one = result(codes[0])
    payload = {"results": [one, result("9B-ZZZ"), result(codes[1], subject="nope")]}
    r = client.post("/api/results", json=payload, headers={"Origin": ORIGIN})
    assert r.json["accepted"] == [one["client_id"]]
    assert [x["reason"] for x in r.json["rejected"]] == ["code", "data"]
    r = client.post("/api/results", json={"results": [one]})  # resent from the outbox
    assert r.json["accepted"] == [one["client_id"]]
    with app.app_context():
        assert Attempt.query.count() == 1


def test_switched_off_code_is_rejected(app, client):
    cid, codes = make_class(app, client)
    with app.app_context():
        sc = StudentCode.query.filter_by(code=codes[0]).one()
        sid = sc.id
    client.post(f"/classes/{cid}/codes/{sid}/toggle")
    r = client.post("/api/results", json={"results": [result(codes[0])]})
    assert r.json["rejected"][0]["reason"] == "code"


def test_dashboard_and_export(app, client):
    cid, codes = make_class(app, client)
    client.post("/api/results", json={"results": [result(codes[0]), result(codes[0], (False, False)),
                                                  result(codes[1], (True, True))]})
    page = client.get(f"/classes/{cid}").data.decode()
    assert "3</b><span>sets finished" in page.replace("\n", "")
    assert "2/5" in page  # students who played
    assert "OSMOSIS" in page.upper() and "Cell biology" in page
    csv_text = client.get(f"/classes/{cid}/export.csv").data.decode()
    assert csv_text.startswith("code,played_at") and codes[0] in csv_text
    page = client.get(f"/classes/{cid}?subject=&period=all").data.decode()
    assert "Biology" in page


def test_other_teachers_cannot_see_class(app, client):
    cid, _ = make_class(app, client)
    with app.app_context():
        t = Teacher(username="other", display_name="Mr Other", must_change_password=False)
        t.set_password("other teacher pw")
        db.session.add(t)
        db.session.commit()
    client.post("/logout")
    login(client, "other", "other teacher pw")
    assert client.get(f"/classes/{cid}").status_code == 403
    client.post("/logout")
    login(client, "admin", "correct horse battery")
    assert client.get(f"/classes/{cid}").status_code == 200


def test_delete_class_removes_results(app, client):
    cid, codes = make_class(app, client)
    client.post("/api/results", json={"results": [result(codes[0])]})
    client.post(f"/classes/{cid}/delete", data={"confirm_name": "wrong"})
    with app.app_context():
        assert SchoolClass.query.count() == 1
    client.post(f"/classes/{cid}/delete", data={"confirm_name": "9B Science"})
    with app.app_context():
        assert SchoolClass.query.count() == 0 and Attempt.query.count() == 0


# ---------- admin ----------

def test_admin_creates_teacher(app, client):
    login(client, "admin", "correct horse battery")
    r = client.post("/admin/teachers/new", data={"username": "PBrown", "display_name": "Mr Brown",
                                                 "subjects": ["physics", "chemistry"]}, follow_redirects=True)
    m = re.search(r"Temporary password: ([a-z]+-[a-z]+-\d+)", r.data.decode())
    assert m
    with app.app_context():
        t = Teacher.query.filter_by(username="pbrown").one()
        assert t.can_edit("physics") and not t.can_edit("biology") and t.must_change_password
    client.post("/logout")
    assert login(client, "pbrown", m.group(1)).status_code == 302


def test_non_admin_blocked(client):
    login(client)
    assert client.get("/admin/").status_code == 403


def test_backup_command(app, tmp_path):
    runner = app.test_cli_runner()
    r = runner.invoke(args=["backup"])
    assert r.exit_code == 0, r.output
    assert list((Path(app.instance_path) / "backups").glob("keyterms-*.db"))


def test_github_calls_in_order(app, monkeypatch):
    """The real API sequence: read main, make a branch, add the file, open the PR."""
    import base64
    seen = []

    class Resp:
        def __init__(self, data, code=200):
            self._d, self.status_code, self.content = data, code, b"x"
        def json(self):
            return self._d

    def fake(method, url, **kw):
        seen.append((method, url.split("/wordletsubjects")[1], kw.get("json")))
        if url.endswith("/git/ref/heads/main"):
            return Resp({"object": {"sha": "abc123"}})
        if url.endswith("/pulls"):
            return Resp({"number": 7, "html_url": "https://github.com/x/pull/7"}, 201)
        return Resp({}, 201)

    monkeypatch.setattr(github.requests, "request", fake)
    app.config["GITHUB_TOKEN"] = "t"
    with app.app_context():
        n, url = github.open_pull_request("banks/inbox/biology/a.csv", "term,clue\n", "inbox/b1", "T", "B")
    assert (n, url) == (7, "https://github.com/x/pull/7")
    assert [s[:2] for s in seen] == [("GET", "/git/ref/heads/main"), ("POST", "/git/refs"),
                                     ("PUT", "/contents/banks/inbox/biology/a.csv"), ("POST", "/pulls")]
    assert seen[1][2] == {"ref": "refs/heads/inbox/b1", "sha": "abc123"}
    assert base64.b64decode(seen[2][2]["content"]).decode() == "term,clue\n"
    assert seen[3][2]["head"] == "inbox/b1" and seen[3][2]["base"] == "main"
