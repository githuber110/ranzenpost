# Ranzenpost (IServ)

Your children's school day from IServ in Home Assistant: the timetable with substitutions,
parent letters, pinboards, absences and chat, as an app in the sidebar, a dashboard card and
entities for automations.

## What it does

- **Timetable** per child, with substitutions and cancellations marked and week navigation.
  Lesson times come from IServ or from a page per school where each period gets a start and a
  duration. Own breaks, clubs and appointments repeat up to the summer holidays; a lesson always
  comes first, and an entry it covers is shortened, never deleted. Parallel courses can be narrowed
  to the ones each child attends.
- **Parent letters**: current and archived, with a read/unread state the app maintains itself
  (IServ does not expose one per letter), attachments, and archiving.
- **Pinboards**: one merged newest-first feed across all boards with a source badge per post,
  jump navigation into a single board (with its swimlanes), full-text search, attachments and an
  app-side read state.
- **Absences**: view and report, covering all four IServ types (sick note, leave request,
  deregistration from bus/kindergarten/lunch, and day-care deregistration), with your school's
  phone numbers one tap away. Leave requests can carry file attachments; a sick-note report can be
  saved or printed as a confirmation PDF.
- **Parent-teacher conference days**, an overview dashboard with unread badges, and settings for
  subject/teacher names and colours, lesson times, phone numbers and notifications.
- **Six languages**: German, English, Arabic (right-to-left), Turkish, Russian and Ukrainian.
  Pick one in the setup wizard or under Settings; the default follows your device.
- **Calendar subscription**: set up per child from Settings: pick lessons, school holidays,
  public holidays, marked exams, approved absences and own entries, then subscribe your calendar
  app to the generated link.
- **Help**: **Settings → Help → Report a problem → Save report** writes `ranzenpost-report.zip`
  with versions, module states and the log, names and secrets removed, to attach to a GitHub issue.

## Which IServ modules are supported

Ranzenpost reads the timetable ("Stunden- und Vertretungsplan"), parent letters, pinboards,
absences, parent-teacher conference days and the messenger. If the Schul-App timetable lists no
lessons and the school has no lesson slots there, Ranzenpost reads the older timetable module at
`/iserv/time-table/` instead and remembers that for the school. A week in which IServ lists no
lessons shows a short note instead of an empty grid. A school with only the older
"Stundenplan" module at `/iserv/timetable/` sees it listed as present but not supported yet. It writes letter confirmations, letter replies and archiving, absence reports and messenger messages,
each only after you confirm. After every login it checks which of these modules your account
offers and hides the rest. Modules it does not support yet are named in the settings by their
official IServ name, with a button that opens a prefilled GitHub issue. The full map of modules,
what parents can do in each according to the IServ documentation, and what Ranzenpost reads and
writes is in
[docs/iserv-modules.md](https://github.com/githuber110/ranzenpost/blob/master/docs/iserv-modules.md).

## Setup

Everything happens in the app's own UI. No YAML, no tokens to copy:

1. Enter your school's address.
2. Sign in with your own parent account (username or e-mail plus password).
3. If your school uses two-factor authentication, type **one** current code from the authenticator
   app you already use. The app registers its own token invisibly; your existing app keeps working.
4. Pick your child, optionally store the school's phone numbers. Done.

Every step has **Back** and **Start over**, so you can never get stuck. If the app later loses
access (token removed in IServ, password changed), it detects this on startup and offers to set up
again.

The app can hold several schools or IServ accounts at once. Each one keeps its own login, children,
subject names, lesson times, phone numbers and holiday region; the children of every school appear
side by side. The same school address may be connected twice with two accounts.

## Install

1. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add this
   repository's URL.
2. Install **Ranzenpost (IServ)** and open it. Setup runs entirely in the app's own UI.

The app image is published per release; the version in `config.yaml` and the pushed image tag are
verified against each other in CI.

## Notifications

Pick where notifications go (a Home Assistant notify service, or type an entity yourself, e.g.
`notify.mobile_app_...`) and which events should notify you. Every timetable change is reported,
substitutions and cancellations alike. A test button confirms the service works.

## Home Assistant integration

The add-on serves a small read-only API on its own port (8099, the same one Ingress uses) for the
Ranzenpost integration, which turns the data into devices and entities in Home Assistant. The API
needs a bearer token that the add-on creates on its first start and keeps in `/data/integration_token`
(owner-only file permissions). On every start and after every rotation the add-on announces itself
to the Supervisor (discovery), so the integration finds the host, port and token without any typing.
Without a Supervisor, copy the token from **Settings → Home Assistant** in the app and enter it in the
integration by hand.

**Settings → Home Assistant** shows whether the integration has called in, when it last did, the
token with a copy button, a **Regenerate** button that invalidates the old token after a confirmation,
and the install link for the integration. Calls through the Ingress proxy cannot use the API, a wrong
or missing token answers 401, and ten failed attempts a minute from one source are answered 429.

Install the integration itself through HACS: add this repository as a custom repository (category
**Integration**) or use the button in the main
[README](https://github.com/githuber110/ranzenpost#3-add-the-integration), then
**Settings → Devices & services → Add integration → Ranzenpost**. With a Supervisor it is found and
set up automatically; otherwise enter the host, port and token shown above by hand.

The integration creates one device per school and one per child. Every entity carries its facts as
attributes, so an automation or a template can read them without a second call. Empty means empty:
a counter reads `0` with an empty list, a text sensor reads `none`, and a timestamp sensor stays
`unknown` only while no such moment exists (no school today, no timetable stamp yet). Times are
ISO 8601 in Europe/Berlin, dates are `YYYY-MM-DD`, weekdays are English names such as `monday`.

Entity IDs use the child's first name, with the school added only when two children at different
schools share it. With several schools the school entities carry the school's name, for example
`sensor.ranzenpost_school_riverside_primary_next_holiday`.

Per child:

- `sensor.ranzenpost_<child>_current_lesson` and `sensor.ranzenpost_<child>_next_lesson`: the subject as state. The next
  lesson looks up to 14 days ahead, so on a Saturday it names the first lesson on Monday.
  Attributes: `date`, `weekday`, `period`, `subject`, `subject_code`, `teacher`, `room`, `start`,
  `end`, `substitution`, `cancelled`, `kind` (`substitution`, `cancellation`, `room_change`,
  `new_lesson` or empty), `before` and `after` (the changed fields), `note`, `minutes_until`,
  `minutes_left`.
- `sensor.ranzenpost_<child>_school_end_today`: the end of the last lesson today. Attribute `school_day`.
- `sensor.ranzenpost_<child>_next_school_day`: the start of the first held lesson on the next day with lessons.
  Today counts while that lesson has not started yet; `days_until` is then `0`. A day whose lessons are all
  cancelled does not count as a school day. Attributes `date`, `weekday`, `days_until`, `end`, `lessons`,
  `first_lesson`.
- `sensor.ranzenpost_<child>_changes_today`: the number of changes today, the list under `changes`.
- `sensor.ranzenpost_<child>_next_exam`: the subject of the next mark from the app's timetable. Attributes
  `date`, `weekday`, `days_until`, `period`, `subject`, `subject_code`, `name`, `start`, `end`,
  `teacher`, `room`.
- `sensor.ranzenpost_<child>_exams_upcoming`: the number of marks in the next 30 days, the list under `exams`.
- `sensor.ranzenpost_<child>_unread_letters` and `sensor.ranzenpost_<child>_unread_posts`: the count, and under `letters`
  or `posts` up to ten entries with `title`, `sender`, `date` and the `child` a letter names.
- `sensor.ranzenpost_<child>_open_absences`: the count, and under `absences` each with `kind`, `summary`,
  `start`, `end`, `status`, `days_until`.
- `sensor.ranzenpost_<child>_next_absence`: the date of the next open or upcoming absence, `none` without
  one. Attributes `kind`, `summary`, `start`, `end`, `status`, `days_until`.
- `sensor.ranzenpost_<child>_timetable_last_updated`: IServ's own stamp when the timetable page shows one,
  otherwise the app's last successful fetch; the attribute `source` says which (`iserv` or `app`).
- `binary_sensor.ranzenpost_<child>_school_day_today`, `binary_sensor.ranzenpost_<child>_timetable_changed_today`.
- `calendar.ranzenpost_<child>_lessons`, `calendar.ranzenpost_<child>_exams`, `calendar.ranzenpost_<child>_absences`: on while an
  event runs, and the next event under `summary`, `start`, `end`, `subject`, `subject_code`, the
  exam `name` or the absence `kind`.
- `calendar.ranzenpost_<child>_own_entries`: own clubs and appointments, only while the school's switch on the
  lesson times page is on. Breaks never leave the app.
- `event.ranzenpost_<child>_timetable_changed`: fires with `child`, `summary`, `date`, `period`.

Per school:

- `sensor.ranzenpost_school_next_holiday`: the name, with `start`, `end`, `days_until` (0 while running).
- `sensor.ranzenpost_school_next_conference`: the date, with `title`, `details` (every cell of the IServ row
  except the date) and `days_until`.
- `sensor.ranzenpost_school_connection`: `ok`, `error`, `unconfigured`, `unreachable` or
  `auth_failed`, with `last_poll`, `last_success`, `version`, `modules`, `modules_disabled`,
  `feed_port_open` and `ingress_path`.
- `calendar.ranzenpost_school_holidays`: school and public holidays.

The exact JSON shapes behind these entities are in `custom_components/ranzenpost/contract.json`.

Automations can use device triggers without YAML. A child's device offers **Timetable changed**,
**Lesson cancelled**, **Substitution**, **New letter**, **New noticeboard post** and **Absence status
changed**; a school's device offers **School unreachable**, **School reachable again** and **Login
needed**. The conditions **Is a school day** and **A lesson is running** check a child. When a
school's login needs you, a repair names the school and clears once the login works again.

## Dashboard card

The integration registers `custom:ranzenpost-card`. Add it from the card picker and set it up in the
visual editor: a title, the children, the blocks (`today`, `next_lesson`, `week`, `changes`,
`letters`, `noticeboard`, `absences`, `conferences`, `holidays`) and a size per block, `compact` or
`normal`. Only blocks of modules your school has are offered, and a block without content is not
drawn. After installing or updating the integration, restart Home Assistant and reload the page so
the browser loads the new card.

## Desktop and tablet

From 900 pixels wide the app shows a navigation rail instead of a tab bar, sheets become centred
dialogs, and the overview lays its chapters out as a grid. From 1280 pixels, letters, posts,
absences and chat rooms open in a pane beside their list, and the timetable shows every child side
by side instead of one at a time. Below 900 pixels nothing changes from the phone layout, and in
Arabic the rail and the pane mirror to the other side.

## Calendar port

Calendar feeds are served by a second, token-protected port (8100) so they can be reached directly
by calendar apps, separate from the app's own Ingress UI. It is **off by default**. To turn it on:
Home Assistant → **Settings → Add-ons → Ranzenpost (IServ) → Configuration → Network**, then
enable **"Show disabled ports"** and map port 8100.

A subscription link on this port shows that child's timetable to anyone who has the link, without
a password. Treat the link itself as the secret, and revoke/rotate it in Settings if it leaks.
Nabu Casa remote access does **not** forward add-on ports: reaching port 8100 from outside your home
network needs your own home network access or a VPN.

## Privacy & secrets

Your school URL, login and the app's own 2FA key stay on your Home Assistant instance (`/data`).
The connector only ever reads your own authorized children's data, and write actions (reporting an
absence, archiving a letter, changing your password) always require an explicit confirmation.

**Disconnect** (Settings) attempts to remove the app's 2FA token from IServ, then deletes that
school's URL, children, phone numbers and login/2FA secrets from this app. When the last school is
gone you land back at the setup wizard.

Your school logins and 2FA keys are encrypted at rest (Fernet), one file per school under
`secrets/`. Each calendar subscription gets its
own random token, stored in plain `calendar_subscriptions.json` (owner-only file permissions),
since it must be readable by external calendar apps; a token grants access to that one subscription
only and can be rotated or revoked from Settings. For stronger protection of the encrypted secrets, set a **passphrase** in the
app options: the encryption key is then derived from it at runtime (scrypt) and never written to
disk. Only a salt is stored. A snapshot of the `/data` folder alone can then no longer be
decrypted without the passphrase. Note: a *full* Home Assistant backup also contains the app
options (including the passphrase), so treat full backups as trusted, the same as Home Assistant's
own stored credentials.

Not affiliated with IServ GmbH.
