# Key Terms

Le Rocquier School. A word-guessing revision game: students read a clue or look at a diagram, guess the term, then answer a follow-up question. Sets of 10, with a retry option for missed terms. Installable as a PWA and works offline after the first visit.

Banks so far: exam command words (all subjects), English (language devices, literary terms, structure, poetry), Design and Technology, AQA separate Biology, Chemistry and Physics, Spanish, French, and KS3 Geography, History and Religious Studies.

## Files
- `index.html` – introduction page, lists subjects by department
- `play.html` – the game (subject, topic, tier and question-type choices)
- `banks/source/*.csv` – the word banks, one per subject. **Edit these.**
- `banks/source/subjects.csv` – the list of subjects and their departments
- `banks/banks.js` – generated from the CSVs. Don't edit by hand.
- `images/` – diagrams for picture questions (SVG or PNG)
- `build_banks.py` – checks the CSVs and builds `banks/banks.js`
- `manifest.json`, `sw.js`, `icons/` – PWA files

## Adding or changing terms
1. Open the subject's CSV in `banks/source/` in Excel or Google Sheets.
2. Add a row. Columns:
   - `term` – the answer. Letters, spaces and hyphens only. Accents are allowed (árbol, être): students type the plain letters and the game shows the correct spelling afterwards. Ñ is typed as N.
   - `clue` – the definition, or an instruction such as "Name this circuit symbol." for picture questions. Don't include the answer.
   - `image` – leave blank, or a path such as `images/sym-diode.svg`
   - `topic` – use the AQA topic name so it groups correctly
   - `tier` – `F` (everyone) or `H` (Higher only)
   - `question`, `correct_answer`, `wrong_1`, `wrong_2`, `wrong_3`, `explanation` – the follow-up. The game shuffles the options.
   - **Extra follow-ups:** add another row with the same `term`, leave `clue`, `image`, `topic` and `tier` blank, and fill in the follow-up columns. Each time the term comes up, one of its follow-ups is picked at random (never the same one twice in a row). Keep a term's rows together so they're easy to find.
3. In Excel, save as **CSV UTF-8**, so symbols like ₂, ° and → survive.
4. Run `python build_banks.py`. It lists any problems and writes nothing until they're fixed.
5. Commit and push.

The build script also updates the version in `sw.js`, so installed copies pick up the new terms automatically.

## Adding a subject
Add a line to `subjects.csv` (id, subject name, heading for the home page such as "Department of Science"), create `<id>.csv` with the same columns, and run the build. The subject appears on the home page under its department.

## Host on GitHub Pages
Push everything to the repo root, then Settings → Pages → Deploy from a branch → `main` / root. The site appears at `https://<username>.github.io/<repo>/`.

© 2026 Le Rocquier School.
