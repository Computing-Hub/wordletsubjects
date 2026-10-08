# Key Terms teacher site

A small Flask app that sits alongside the game. Teachers use it to:

- **Add terms** through a form. Terms collect as drafts; "Send for review" opens a GitHub pull request with a CSV in `banks/inbox/<subject>/`. Nothing reaches students until the PR is merged. The GitHub Action then checks and rebuilds `banks/banks.js`.
- **Create classes** with anonymous codes like `9B-K7R`. Students type the code into the game once; each finished set is sent here.
- **See progress**: sets per week, most-missed terms, and a grid of codes by topic. Names can be typed in on the teacher's own computer and are stored only in that browser, never on the server.

The game keeps working offline and without this site. If `config.js` has no `resultsUrl`, the game never sends anything.

## What is stored

Teacher accounts (hashed passwords), drafts, classes, codes, and for each finished set: code, subject, topic, time, and for each term whether the word was solved and the question answered correctly. **No student names, emails or device details.** Results older than `RESULTS_KEEP_DAYS` (default 400) can be removed with `flask purge-results`.

## Set up on Railway

Railway runs the site from this repo and redeploys it when `server/` changes on `main`. The settings it needs are in `server/railway.json`. Expect to pay a few dollars a month on the Hobby plan; check Railway's current pricing.

1. **Make a GitHub token.** GitHub → Settings → Developer settings → Fine-grained tokens → Generate. Resource owner: **Computing-Hub**. Repository access: **only `wordletsubjects`**. Permissions: **Contents: read and write**, **Pull requests: read and write**. Set an expiry (a year) and a calendar reminder to renew it.
2. **Create the service.** In Railway: New project → Deploy from GitHub repo → `Computing-Hub/wordletsubjects`. Then open the service's **Settings**:
   - **Root directory:** `/server`
   - **Config file path:** `/server/railway.json` (if Railway doesn't pick it up by itself)
   - **Region:** an EU region, so the data stays in Europe
3. **Add a volume.** Right-click the service (or Command palette → "Volume") → attach a volume with mount path **`/data`**. The database lives there. **Without a volume, everything is wiped on each redeploy.** The site finds the volume by itself through `RAILWAY_VOLUME_MOUNT_PATH`.
4. **Add the variables** (service → Variables):
   ```
   SECRET_KEY=<long random string>
   KEYTERMS_GITHUB_TOKEN=github_pat_...
   ALLOWED_ORIGINS=https://computing-hub.github.io
   ADMIN_USERNAME=jose
   ADMIN_NAME=Head of CS
   ADMIN_PASSWORD=<a temporary password, 10+ characters>
   ```
   For the secret key, run `python -c "import secrets; print(secrets.token_hex(32))"`.
5. **Give it an address.** Settings → Networking → Generate domain. You'll get something like `keyterms-production.up.railway.app`. (A custom domain such as `keyterms.coderra.je` can be added here too.)
6. **Log in** with `ADMIN_USERNAME` and `ADMIN_PASSWORD`. It asks you to choose a new password. Then **delete `ADMIN_PASSWORD` from the variables**. It's only used when there are no accounts yet, so leaving it is harmless, but there's no reason to keep it.
7. **Switch the game on.** In the repo, set `resultsUrl` in `config.js` to the Railway address (with `https://`, no slash at the end), run `python build_banks.py`, commit and push.
8. **Backups.** Admin → **Download a backup** saves a copy of the database to your computer; do it at the end of each half term. Railway can also back up the volume on a schedule from the volume's settings, if your plan includes it.

The site runs one gunicorn process with several threads. Keep it at one process (and one replica): SQLite and the login lockout both assume a single process.

## Set up on PythonAnywhere instead

A free alternative. In a Bash console: clone the repo, `mkvirtualenv keyterms --python=python3.12`, `pip install -r server/requirements.txt`. Add a web app (manual configuration), point it at `server/` and the virtualenv, and in the WSGI file set the same variables as above with `os.environ[...]` before `from wsgi import app as application`. Create your admin with `flask --app wsgi create-admin jose`. Free accounts must be renewed on the Web tab every few months.

## Day to day

- **Add teachers:** Admin → Add a teacher. Tick the subjects they may add terms to. You'll see a temporary password once; they choose their own on first login.
- **Review terms:** Admin lists open pull requests. On GitHub, a green tick means the build accepted the file. Merge to publish; the Action rebuilds the site.
- **Tidy the workbook:** now and then, pull, run `python merge_inbox.py` to move approved inbox files into `terms.xlsx`, then commit. Until then the build reads them from the inbox, so students already see them.
- **Update the site code:** merge to `main`; Railway redeploys when anything in `server/` changes. Pushes that only change word banks don't restart the site.

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
| `DATA_DIR` | the Railway volume, else `server/instance/` | Where the database, backups and outbox go |
| `DATABASE_URL` | SQLite in `DATA_DIR` | Any SQLAlchemy URL (Postgres also needs a driver such as `psycopg2-binary`) |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_NAME` | empty | Creates the first admin, only while there are no accounts |
| `GAME_URL` | the GitHub Pages address | Shown on the codes sheet |
| `SCHOOL_NAME` | Le Rocquier School | |
| `RESULTS_KEEP_DAYS` | 400 | Used by `flask purge-results` |

SQLite runs in WAL mode with a 5-second busy timeout, which comfortably handles a whole class finishing sets at once.
