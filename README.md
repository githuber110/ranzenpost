# Ranzenpost — unofficial IServ parent client

A shareable **Home Assistant app** that brings a school's [IServ](https://iserv.de)
into a clean, mobile-first UI: timetable with substitutions, parent letters, pinboards
and absences — with a guided setup wizard (school URL, login, two-factor, children).

Not affiliated with IServ GmbH.

## Repository layout

- `iserv_connector/` — the Home Assistant app manifest (`config.yaml`, `DOCS.md`).
- `Dockerfile` — builds the app image (published to `ghcr.io`).
- `backend/` — the Python service.
  - `app/iserv/` — the IServ client (form-based login + TOTP, children, timetable).
  - `app/` — config store, mapping, Ingress web service (FastAPI).
  - `tests/` — pytest against anonymized fixtures only (no real school data).
- `frontend/` — the Ingress web UI (vanilla JS, no build step).
  - `i18n/` — the string database, one flat `key -> text` file per language.
  - `tests/` — Vitest against a jsdom-rendered app.

## Develop

```bash
cd backend
python -m venv ../.venv && ../.venv/bin/pip install -r requirements-dev.txt
../.venv/bin/pytest
```

## Languages

German is the base language and the source of truth (`frontend/i18n/de.json`); English,
Arabic, Turkish, Russian and Ukrainian sit next to it as `<lang>.json`. The UI reads every
string through `t(key, vars)`, the API answers with a `message_key`, and dates, times and
numbers are formatted with `Intl` for the active language (the school timezone stays
Europe/Berlin). Readers pick a language in the setup wizard or under Settings; the default
follows the device. No user-visible text belongs in the frontend code — a guard
(`backend/tests/test_i18n.py`) fails the build for hardcoded strings in `app.js`/`wizard.js`
and for a key that is missing from any language file. Push-notification texts (built in
`backend/app/poller.py`) are backend-only and currently always German; they are not covered
by that guard yet.

## Conventions

Code is English and comment-free. No personal data in the repository; tests use
anonymized fixtures. Write actions against IServ (report absence, archive letter) always
require explicit user confirmation.

## Third-party assets

The bundled fonts are licensed under the [SIL Open Font License 1.1](frontend/fonts/OFL.txt)
(the MIT license above covers only the code):

- `frontend/fonts/archivo-600-700.woff2` — **Archivo**, © The Archivo Project Authors
  ([github.com/Omnibus-Type/Archivo](https://github.com/Omnibus-Type/Archivo)).
- `frontend/fonts/schibsted-grotesk-400-700.woff2` — **Schibsted Grotesk**, © Schibsted Media
  ([github.com/schibsted/schibsted-grotesk](https://github.com/schibsted/schibsted-grotesk)).
