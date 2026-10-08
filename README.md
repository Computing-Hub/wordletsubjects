# Key Terms

Le Rocquier School. A word-guessing revision game: students read a clue or look at a diagram, guess the term, then answer a follow-up question. Sets of 10, with a retry option for missed terms. Installable as a PWA and works offline after the first visit.

Banks so far: exam command words (all subjects), English (language devices, literary terms, structure, poetry), Design and Technology, AQA separate Biology, Chemistry and Physics, Spanish, French, and KS3 Geography, History and Religious Studies.

## Files
- `index.html` – introduction page, lists subjects by department
- `play.html` – the game engine (subject, topic, tier and question-type choices)
- `banks/terms.xlsx` – **all word banks, one tab per subject. Edit this.**
- `banks/banks.js` – generated from the workbook. Don't edit by hand.
- `images/` – diagrams for picture questions (SVG or PNG)
- `banks/inbox/` – terms sent in from the teacher site, one CSV per batch. The build reads them as extra rows.
- `build_banks.py` – checks the workbook and inbox and builds `banks/banks.js` (`--check` to check only)
- `merge_inbox.py` – moves approved inbox files into `terms.xlsx`
- `config.js` – the teacher site's address, for class codes. Empty means class codes are off.
- `server/` – the teacher site (adding terms, classes, progress). See `server/README.md`.
- `.github/workflows/build-banks.yml` – checks pull requests and rebuilds `banks.js` after merges
- `manifest.json`, `sw.js`, `icons/` – PWA files

## Editing the word banks
Open `banks/terms.xlsx`. The **How to** tab explains everything; in short:

- **Each subject tab** has one row per term, plus grey rows below it for extra follow-up questions (same term, blank clue/image/topic/tier). One follow-up is picked at random each time the term appears.
- **Columns:** term, clue, image, topic, tier, question, correct_answer, wrong_1, wrong_2, wrong_3, explanation, checked_by.
- **Dropdowns** for tier, topic and image come from the **Lists** tab. Add a new topic there first.
- **Red cells** mark something required that's missing.
- **checked_by** is for the initials of the teacher who reviewed the row. The build reports how many terms are still unchecked.
- **Accents** are fine in terms (árbol, être): students type plain letters and the game shows the correct spelling afterwards.

Then build and publish:

```
pip install -r requirements.txt   # first time only
python build_banks.py
git add -A && git commit -m "Update word banks" && git push
```

The build lists any problems by tab and row number and writes nothing until they're fixed. It also updates the version in `sw.js`, so installed copies pick up the changes.

## Terms from other teachers
Teachers add terms through the teacher site rather than editing the workbook. Each batch arrives as a pull request containing one CSV in `banks/inbox/<subject-id>/`. The GitHub Action runs `build_banks.py --check` on it, so a green tick means it will build. Merge it and the Action rebuilds `banks.js`; the site updates on its own.

Now and then, pull and run `python merge_inbox.py` to move the inbox files into `terms.xlsx`, then commit. New topics are added to the Lists tab.

## Class codes
If `config.js` has a `resultsUrl`, the setup screen offers **Add class code**. A student types the code their teacher gave them (e.g. `9B-K7R`); after each set the code, subject, topic and right/wrong per term are sent to the teacher site. No names. Sets finished offline are queued and sent later. See `server/README.md`.

## Adding a subject
Add a row to the **Subjects** tab (id, subject, department heading), create a tab named exactly like the subject with the same column headings, and add a column for its topics in the **Lists** tab. Then run the build.

## Host on GitHub Pages
Push everything to the repo root, then Settings → Pages → Deploy from a branch → `main` / root. The site appears at `https://<username>.github.io/<repo>/`.

© 2026 Le Rocquier School.
