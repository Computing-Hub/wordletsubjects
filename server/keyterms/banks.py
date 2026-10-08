"""Read the live word banks (banks/banks.js) so the term form knows which
subjects, topics and terms already exist.

The copy on GitHub is the one students see, so it is preferred. If GitHub isn't
configured or can't be reached, the copy in this repo folder is used instead.
"""
import json
import time
from pathlib import Path

import requests
from flask import current_app

_cache = {"at": 0.0, "banks": None}
CACHE_SECONDS = 600


def parse(js_text):
    start, end = js_text.index("["), js_text.rindex("]")
    return json.loads(js_text[start:end + 1])


def _from_github():
    cfg = current_app.config
    if not (cfg.get("GITHUB_TOKEN") and cfg.get("GITHUB_REPO")):
        return None
    r = requests.get(
        f"https://api.github.com/repos/{cfg['GITHUB_REPO']}/contents/banks/banks.js",
        params={"ref": cfg["GITHUB_BRANCH"]},
        headers={"Authorization": f"Bearer {cfg['GITHUB_TOKEN']}",
                 "Accept": "application/vnd.github.raw+json"},
        timeout=10,
    )
    r.raise_for_status()
    return parse(r.text)


def _from_disk():
    path = Path(current_app.config["BANKS_JS_PATH"])
    return parse(path.read_text(encoding="utf-8")) if path.exists() else []


def load(force=False):
    if not force and _cache["banks"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["banks"]
    try:
        banks = _from_github()
    except Exception as e:  # network trouble shouldn't stop teachers working
        current_app.logger.warning("Couldn't read banks.js from GitHub: %s", e)
        banks = None
    if banks is None:
        banks = _from_disk()
    _cache.update(at=time.time(), banks=banks)
    return banks


def subjects():
    """[(id, name, department)] in bank order."""
    return [(b["id"], b["subject"], b.get("department", "")) for b in load()]


def subject(sid):
    return next((b for b in load() if b["id"] == sid), None)


def subject_name(sid):
    b = subject(sid)
    return b["subject"] if b else sid


def topics(sid):
    b = subject(sid)
    return list(dict.fromkeys(i["topic"] for i in b["items"])) if b else []


def terms(sid):
    b = subject(sid)
    return [i["term"] for i in b["items"]] if b else []
