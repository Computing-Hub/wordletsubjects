"""Checks for terms typed into the form. These follow the same rules as
build_banks.py, so anything the form accepts will also pass the build."""
import csv
import io
import re
import unicodedata

COLS = ["term", "clue", "image", "topic", "tier", "question",
        "correct_answer", "wrong_1", "wrong_2", "wrong_3", "explanation", "checked_by"]
FU_FIELDS = ["question", "correct_answer", "wrong_1", "wrong_2", "wrong_3", "explanation"]
FU_LABELS = {"question": "question", "correct_answer": "correct answer", "wrong_1": "wrong answer 1",
             "wrong_2": "wrong answer 2", "wrong_3": "wrong answer 3", "explanation": "explanation"}
MAX_FOLLOWUPS = 3
LIMITS = {"term": 60, "clue": 300, "topic": 80, "question": 300, "correct_answer": 200,
          "wrong_1": 200, "wrong_2": 200, "wrong_3": 200, "explanation": 400, "notes": 500}
TERM_OK = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ \-]+$")


def term_key(term):
    """Same matching as the build: ignore case, accents, spaces and hyphens."""
    plain = unicodedata.normalize("NFD", term).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", plain.lower())


def clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("\r", " ")).strip()


def check_entry(data, mode, existing, pending_new=()):
    """Validate one form entry.

    data: dict with term, clue, topic, tier, notes and followups (list of dicts)
    mode: "new" (a new term) or "extra" (more questions for a term that exists)
    existing: term keys already in the live bank
    pending_new: term keys this teacher already has as new terms in drafts
    Returns (errors, warnings). Errors block saving; warnings don't.
    """
    errors, warnings = [], []
    term = data["term"]
    for field, limit in LIMITS.items():
        if field in data and len(data[field]) > limit:
            errors.append(f"The {field.replace('_', ' ')} is too long (max {limit} characters).")

    key = term_key(term)
    if not term:
        errors.append("Enter the term.")
    elif not TERM_OK.match(term):
        errors.append("The term may only contain letters (accents are fine), spaces and hyphens.")
    elif not key:
        errors.append("The term needs at least one letter.")
    elif len(key) > 30:
        errors.append("The term is too long for the tiles (30 letters at most).")

    if mode == "new":
        if key and key in existing:
            errors.append(f"'{term}' is already in this word bank. To add questions to it, "
                          "choose 'More questions for an existing term'.")
        elif key and key in pending_new:
            errors.append(f"You already have '{term}' waiting in your drafts.")
        if not data["clue"]:
            errors.append("Enter the clue.")
        if not data["topic"]:
            errors.append("Choose or type a topic.")
        if data["tier"] not in ("F", "H"):
            errors.append("Choose Foundation or Higher.")
        if term and data["clue"] and re.search(r"\b" + re.escape(term.lower()) + r"\b", data["clue"].lower()):
            warnings.append("The clue contains the answer, which gives it away.")
    else:
        if key and key not in existing and key not in pending_new:
            errors.append(f"'{term}' isn't in this word bank yet. Add it as a new term first.")

    fus = data["followups"]
    if not fus:
        errors.append("Add at least one follow-up question.")
    for n, fu in enumerate(fus, start=1):
        label = f"Question {n}" if len(fus) > 1 else "The follow-up"
        missing = [FU_LABELS[f] for f in FU_FIELDS if not fu.get(f)]
        if missing:
            errors.append(f"{label} is missing: {', '.join(missing)}.")
            continue
        opts = [fu["correct_answer"], fu["wrong_1"], fu["wrong_2"], fu["wrong_3"]]
        if len(set(opts)) < 4:
            errors.append(f"{label}: the four answers must all be different.")
        lens = [len(o) for o in opts]
        if lens[0] > 2 * max(lens[1:]) + 10:
            warnings.append(f"{label}: the correct answer is much longer than the others, "
                            "so students may pick it for that reason alone.")
    return errors, warnings


def form_to_entry(form):
    """Read the term form (a Werkzeug MultiDict) into a plain dict."""
    data = {k: clean(form.get(k)) for k in ("term", "clue", "topic", "tier", "notes")}
    if data["topic"] == "__new__":
        data["topic"] = clean(form.get("new_topic"))
    data["tier"] = data["tier"].upper()
    fus = []
    for n in range(1, MAX_FOLLOWUPS + 1):
        fu = {f: clean(form.get(f"{f}_{n}")) for f in FU_FIELDS}
        if n == 1 or any(fu.values()):  # later blocks are optional; ignore empty ones
            fus.append(fu)
    data["followups"] = fus
    return data


def entry_rows(data, mode):
    """Turn an entry into word-bank rows: the first carries the clue (new term
    only), the rest leave it blank so the build adds them as extra questions."""
    rows = []
    for n, fu in enumerate(data["followups"]):
        first = mode == "new" and n == 0
        rows.append({
            "term": data["term"],
            "clue": data["clue"] if first else "",
            "topic": data["topic"] if first else "",
            "tier": data["tier"] if first else "",
            **fu,
        })
    return rows


def rows_to_csv(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS + ["notes"], extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") or "" for c in COLS + ["notes"]})
    return buf.getvalue()
