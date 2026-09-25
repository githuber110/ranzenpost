# Contributing to Ranzenpost

Thanks for helping. Bug reports, translations and pull requests are all welcome.

Missing an IServ module your school uses? That is the most useful contribution.

## Before you start

- **Every school is one connection.** The store keeps a list of connections; children, letters,
  posts and settings are addressed by the connection id and the child key `<connection>:<child>`.
  Fixtures use invented schools such as `school-one.example` and `school-two.example`.
- **Keep personal data out.** No real school domains, names, letters, timetables or credentials.
  Not in code, not in fixtures, not in screenshots, not in issue text. The test suite refuses
  tracked files that carry personal data.
- **Write actions need a confirmation.** Anything that sends something to IServ (absences,
  archiving, read confirmations) is shown to the user and confirmed explicitly. Do not add a write
  path that runs on its own.
- **Only the parent's own children.** The client reads the child IDs IServ lists for the signed-in
  account and never probes others.

## Development setup

No build step for the frontend. It is vanilla JS served as-is.

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

### Home Assistant integration tests

The integration and the dashboard card have their own suites, separate from the add-on's. They
need Home Assistant's test harness, which only runs on Linux:

```bash
pip install -r requirements-integration-dev.txt
pytest tests/components/ranzenpost -q -p no:cacheprovider
npm run test:card
```

CI runs these in the `integration-tests` job. `npm test` and `npm run test:card` fail when a test file did not
run at all. For a single card file use `npm run test:card:focused -- tests/card/<name>.test.js`.

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
- `docs/screenshots/` — the images used in the README. `node scripts/capture_screenshots.js`
  regenerates all of them from the fixture server in English, light and dark.
- `custom_components/ranzenpost/` — the Home Assistant integration (devices, entities, config
  flow, the dashboard card it serves) and `tests/components/ranzenpost/` for its tests.
- `tests/card/` — vitest suite for the dashboard card, run with `npm run test:card`.
- `scripts/` — small standalone helpers, such as `extract_changelog_section.py`, that both CI and
  the test suite call so there is one implementation of each.

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
- The README exists twice: `README.md` in English and `README.de.md` in German. Every change goes
  into both, with the same headings, images and links in the same order; a test compares the two.
  The module table in both must name every module in `backend/app/modules.py`. No dash inside a
  sentence in either file.

## Keeping the build reproducible

- `backend/requirements.lock.txt` pins every runtime dependency of `backend/requirements.txt` to an
  exact version, with the sha256 hashes of its linux/amd64 and linux/arm64 wheels for Python 3.12.
  `Dockerfile` installs from it with `pip install --require-hashes`, and CI's `tests` job installs
  it the same way before the loose ranges in `requirements-dev.txt`, so both resolve the same
  versions. Regenerate it after bumping a version in `requirements.txt`:

  ```bash
  pip download --no-deps --dest amd64 --platform manylinux2014_x86_64 \
      --python-version 312 --implementation cp --abi cp312 --only-binary=:all: <pkg>==<version>
  pip download --no-deps --dest arm64 --platform manylinux2014_aarch64 \
      --python-version 312 --implementation cp --abi cp312 --only-binary=:all: <pkg>==<version>
  pip hash amd64/*.whl arm64/*.whl
  ```

  Repeat for every runtime package (direct and transitive; `pip show <pkg>` lists `Requires`), then
  merge the resulting `--hash=sha256:...` lines under each `name==version` entry in the lock file.
  Pick versions that satisfy the ranges declared in `requirements.txt`.
- The Dockerfile pins the base image to an exact patch tag and its digest
  (`python:3.12.14-slim@sha256:...`), so a floating `3.12-slim` tag cannot change the image under
  us between builds. To update it, look up the new patch tag's digest and change both the tag and
  the digest together:

  ```bash
  curl -s https://hub.docker.com/v2/repositories/library/python/tags/3.12.<patch>-slim | python3 -c \
      "import sys, json; d = json.load(sys.stdin); print(d['name'], d['digest'])"
  ```

  The digest from that response is the multi-arch manifest list digest, valid for both
  `linux/amd64` and `linux/arm64`.

## Layout rules

- Two breakpoints only: 900px switches the tab bar for a navigation rail and turns sheets into
  centred dialogs; 1280px opens letters, posts, absences, chat rooms and the timetable's children
  side by side in a pane instead of a full page. Below 900px the phone layout is unchanged. Do not
  add a third breakpoint or touch the phone styles for a desktop feature.
- Every new layout rule uses logical CSS properties (see Conventions above) so it mirrors under
  `[dir="rtl"]` without extra work.

## Credit

The release notes credit every contributor of a release, by the name or handle they want credited.
Add yours under `### Thanks` in the changelog section of the coming release, in the same pull request
as your change, and add the heading if it is not there yet.

## Translations

Copy the key you want to improve from `frontend/i18n/de.json`, change the value in the language
file, keep the `{placeholders}` exactly as they are, and run `npm test`.

## Versioning and releases

Versions follow `YYMM.N.P` like Home Assistant: year and month, then the feature release and the fix number,
without leading zeros (`2609.2.1`). Test builds carry a `b` suffix (`2609.2.1b0`); Home Assistant and HACS sort
them below the release. `iserv_connector/config.yaml`, `package.json` and
`custom_components/ranzenpost/manifest.json` always carry the same version; a test guards that.

A release is a tag `vYYMM.N.P`, e.g. `v2609.2.1`. CI checks the tag against
`config.yaml`, builds and pushes the image, then creates the GitHub release from that version's
section of `iserv_connector/CHANGELOG.md` (`scripts/extract_changelog_section.py`).

## Pull requests

Small and focused, with the tests that prove the change. If the change touches the login, the
setup wizard or a write action, say so in the description. Those get a closer look.
