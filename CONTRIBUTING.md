# Contributing to Ranzenpost

Thanks for helping. Bug reports, translations and pull requests are all welcome.

## Before you start

- **Keep personal data out.** No real school domains, names, letters, timetables or credentials —
  not in code, not in fixtures, not in screenshots, not in issue text. The test suite refuses
  tracked files that carry personal data.
- **Write actions need a confirmation.** Anything that sends something to IServ (absences,
  archiving, read confirmations) is shown to the user and confirmed explicitly. Do not add a write
  path that runs on its own.
- **Only the parent's own children.** The client reads the child IDs IServ lists for the signed-in
  account and never probes others.

## Development setup

No build step for the frontend — it is vanilla JS served as-is.

```bash
python -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
npm ci
npx playwright install chromium webkit
```

Run the suites:

```bash
cd backend && ../.venv/bin/python -m pytest -q     # backend and repository guards
npm test                                           # frontend unit tests
npx playwright test                                # end-to-end against the fixture server
```

CI runs all three on every push (`.github/workflows/build.yml`).

## Layout

- `iserv_connector/` — the Home Assistant add-on manifest (`config.yaml`, `DOCS.md`, changelog,
  translations of the option names).
- `Dockerfile` — builds the add-on image, published to `ghcr.io` on a `v*` tag.
- `backend/`
  - `app/iserv/` — the IServ client: form login with TOTP, children, timetable, absences, letters.
  - `app/` — config store, encryption, mapping, poller, calendar feed, the FastAPI Ingress service.
  - `tests/` — pytest against anonymised fixtures, plus repository guards (personal data, i18n
    parity, logical CSS properties, commit hygiene).
- `frontend/` — the Ingress web UI (vanilla JS).
  - `i18n/` — the string database, one flat `key -> text` file per language.
- `e2e/` — Playwright specs; the fixture IServ server they run against is
  `backend/tests/e2e_fixture_app.py`.
- `docs/screenshots/` — the images used in the README.

## Conventions

- Code is English and comment-free.
- No user-visible text lives in the code. German (`frontend/i18n/de.json`) is the source of truth;
  the UI reads every string through `t(key, vars)`, the API answers with a `message_key`. A new
  string needs all six languages (de, en, ar, tr, ru, uk) or the parity test goes red.
- CSS uses logical properties only (`margin-inline-start`, `text-align: start`, …) so the Arabic
  layout mirrors correctly. Direction-dependent icons get a class and a `[dir="rtl"]` rule.
- Dates, times and numbers go through `Intl` with the active language; the school timezone stays
  `Europe/Berlin`.
- Commit subjects are one short English sentence. No trailers, no ticket numbers, no references to
  anything outside this repository.

## Translations

Copy the key you want to improve from `frontend/i18n/de.json`, change the value in the language
file, keep the `{placeholders}` exactly as they are, and run `npm test`.

## Pull requests

Small and focused, with the tests that prove the change. If the change touches the login, the
setup wizard or a write action, say so in the description — those get a closer look.
