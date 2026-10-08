# Key Terms teacher site

A small Flask app that sits alongside the game. Teachers use it to:

- **Add terms** through a form. Terms collect as drafts; "Send for review" opens a GitHub pull request with a CSV in `banks/inbox/<subject>/`. Nothing reaches students until the PR is merged. The GitHub Action then checks and rebuilds `banks/banks.js`.
- **Create classes** with anonymous codes like `9B-K7R`. Students type the code into the game once; each finished set is sent here.
- **See progress**: sets per week, most-missed terms, and a grid of codes by topic. Names can be typed in on the teacher's own computer and are stored only in that browser, never on the server.

The game keeps working offline and without this site. If `config.js` has no `resultsUrl`, the game never sends anything.

## What is stored

Teacher accounts (hashed passwords), drafts, classes, codes, and for each finished set: code, subject, topic, time, and for each term whether the word was solved and the question answered correctly. **No student names, emails or device details.** Results older than `RESULTS_KEEP_DAYS` (default 400) can be removed with `flask purge-results`.

## Set up on PythonAnywhere (free account)

The EU-hosted site (`eu.pythonanywhere.com`) keeps the data in Europe.

1. **Make a GitHub token.** GitHub → Settings → Developer settings → Fine-grained tokens → Generate. Resource owner: **Computing-Hub**. Repository access: **only `wordletsubjects`**. Permissions: **Contents: read and write**, **Pull requests: read and write**. Set an expiry (a year) and a calendar reminder to renew it.
2. **Get the code.** Open a Bash console on PythonAnywhere:
   ```
   git clone https://github.com/Computing-Hub/wordletsubjects.git
   cd wordletsubjects/server
   mkvirtualenv keyterms --python=python3.12
   pip install -r requirements.txt
   ```
3. **Create the web app.** Web tab → Add a new web app → Manual configuration → Python 3.12. Set:
   - Source code: `/home/YOURNAME/wordletsubjects/server`
   - Virtualenv: `/home/YOURNAME/.virtualenvs/keyterms`
   - Force HTTPS: on
4. **Edit the WSGI file** (link on the Web tab). Replace everything with:
   ```python
   import os, sys
   sys.path.insert(0, "/home/YOURNAME/wordletsubjects/server")
   os.environ["SECRET_KEY"] = "paste a long random string here"
   os.environ["KEYTERMS_GITHUB_TOKEN"] = "github_pat_..."
   os.environ["ALLOWED_ORIGINS"] = "https://computing-hub.github.io"
   os.environ["GAME_URL"] = "https://computing-hub.github.io/wordletsubjects/"
   from wsgi import app as application
   ```
   For the secret key, run `python -c "import secrets; print(secrets.token_hex(32))"` in a console.
5. **Create your admin account** in the Bash console (same environment variables aren't needed for this):
   ```
   cd ~/wordletsubjects/server
   workon keyterms
   flask --app wsgi create-admin jose --name "Head of CS"
   ```
6. **Reload** the web app, open `https://YOURNAME.eu.pythonanywhere.com` and log in.
7. **Switch the game on.** In the repo, set `resultsUrl` in `config.js` to that address (no slash at the end), run `python build_banks.py`, commit and push.
8. **Nightly backup.** Tasks tab → daily task:
   ```
   cd ~/wordletsubjects/server && ~/.virtualenvs/keyterms/bin/flask --app wsgi backup
   ```
   Backups go to `server/instance/backups/`, keeping the last 14.

Free accounts must click "Run until 3 months from today" on the Web tab every few months, and only allow outbound requests to approved sites (api.github.com is on the list).

## Day to day

- **Add teachers:** Admin → Add a teacher. Tick the subjects they may add terms to. You'll see a temporary password once; they choose their own on first login.
- **Review terms:** Admin lists open pull requests. On GitHub, a green tick means the build accepted the file. Merge to publish; the Action rebuilds the site.
- **Tidy the workbook:** now and then, pull, run `python merge_inbox.py` to move approved inbox files into `terms.xlsx`, then commit. Until then the build reads them from the inbox, so students already see them.
- **Update the site code:** `git pull` in the console, then Reload on the Web tab.

## Running it locally

```
cd server
pip install -r requirements.txt
FLASK_DEBUG=1 flask --app wsgi create-admin jose
FLASK_DEBUG=1 flask --app wsgi run
```

Without `KEYTERMS_GITHUB_TOKEN`, sent terms are saved under `server/instance/outbox/` instead of opening a PR. To try class codes locally, serve the game with `python -m http.server 8000` from the repo root, set `resultsUrl` to `http://localhost:5000` in your local `config.js`, and start the site with `ALLOWED_ORIGINS=http://localhost:8000`.

Tests: `cd server && python -m pytest -q`

## Settings

| Variable | Default | |
|---|---|---|
| `SECRET_KEY` | (must set) | Signs login cookies |
| `KEYTERMS_GITHUB_TOKEN` | empty | Fine-grained token, see above |
| `GITHUB_REPO` | `Computing-Hub/wordletsubjects` | |
| `GITHUB_BRANCH` | `main` | |
| `ALLOWED_ORIGINS` | `https://computing-hub.github.io` | Where the game is hosted, comma-separated |
| `DATABASE_URL` | SQLite in `server/instance/` | Any SQLAlchemy URL, e.g. Postgres |
| `GAME_URL` | the GitHub Pages address | Shown on the codes sheet |
| `SCHOOL_NAME` | Le Rocquier School | |
| `RESULTS_KEEP_DAYS` | 400 | Used by `flask purge-results` |

SQLite runs in WAL mode with a 5-second busy timeout, which comfortably handles a whole class finishing sets at once.
