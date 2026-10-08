"""Send terms to GitHub as a pull request, so nothing reaches students until
the reviewer merges it.

Needs a fine-grained token with access to this one repository only, with
"Contents: read and write" and "Pull requests: read and write".
"""
import base64

import requests
from flask import current_app

API = "https://api.github.com"


class GitHubError(Exception):
    pass


def configured():
    cfg = current_app.config
    return bool(cfg.get("GITHUB_TOKEN") and cfg.get("GITHUB_REPO"))


def _call(method, path, **kw):
    cfg = current_app.config
    r = requests.request(
        method, f"{API}/repos/{cfg['GITHUB_REPO']}{path}",
        headers={"Authorization": f"Bearer {cfg['GITHUB_TOKEN']}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
        timeout=20, **kw)
    if r.status_code >= 400:
        try:
            msg = r.json().get("message", r.text)
        except ValueError:
            msg = r.text
        raise GitHubError(f"GitHub said {r.status_code}: {msg}")
    return r.json() if r.content else {}


def open_pull_request(path, content, branch, title, body):
    """Create a branch with one new file and open a PR. Returns (number, url)."""
    base = current_app.config["GITHUB_BRANCH"]
    sha = _call("GET", f"/git/ref/heads/{base}")["object"]["sha"]
    _call("POST", "/git/refs", json={"ref": f"refs/heads/{branch}", "sha": sha})
    _call("PUT", f"/contents/{path}", json={
        "message": title,
        "content": base64.b64encode(content.encode("utf-8")).decode(),
        "branch": branch,
    })
    pr = _call("POST", "/pulls", json={"title": title, "head": branch, "base": base, "body": body})
    return pr["number"], pr["html_url"]


def pull_request_status(number):
    pr = _call("GET", f"/pulls/{number}")
    if pr.get("merged_at"):
        return "merged"
    return "closed" if pr.get("state") == "closed" else "open"
