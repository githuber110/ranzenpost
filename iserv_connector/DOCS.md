# Ranzenpost (IServ)

Your children's school day from IServ in Home Assistant: the timetable with substitutions,
parent letters, noticeboards, absences, chat, school events, tasks, news, email and files, as an app
in the sidebar, a dashboard card and entities for automations.

## What it does

- **Timetable** per child, with substitutions and cancellations marked and week navigation.
  Lesson times come from IServ or from a page per school where each period gets a start and a
  duration. Own breaks, clubs and appointments repeat up to the summer holidays; a lesson always
  comes first, and an entry it covers is shortened, never deleted. Parallel courses can be narrowed
  to the ones each child attends.
- **Parent letters**: current and archived, with a read/unread state the app maintains itself
  (IServ does not expose one per letter), attachments, and archiving.
- **Noticeboards**: one merged newest-first feed across all boards with a source badge per post,
  jump navigation into a single board (with its swimlanes), full-text search, attachments and an
  app-side read state.
- **Absences**: view and report, covering all four IServ types (sick note, leave request,
  deregistration from bus/kindergarten/lunch, and day-care deregistration), with your school's
  phone numbers one tap away. Leave requests can carry file attachments; a sick-note report can be
  saved or printed as a confirmation PDF.
- **Chat** through the IServ messenger, where the school opens it to parents.
- **School events** from every IServ calendar the account sees, its personal calendar included, in
  their own view and as an overview block.
- **Parent-teacher conferences**: current and archived days, your bookings, teachers, rooms and free
  slots. Book, change and cancel a slot after a confirmation. Push messages tell you when booking
  opens, when a booking is cancelled, three days before and shortly before an appointment.
- **Tasks and news**: open and past tasks, and every news item with its text, files and links. News can
  be filtered by category and searched. The archive and the package news are read when you pick them in
  the filter. A task opens with what its IServ page shows, read only when you open it: text, files, the
  own hand-in, feedback and model solutions. Hand in files or text, remove handed-in files and mark a
  task as done in the app, each after a confirmation.
- **Forums, texts, info screens and whiteboards**: forums with their unread posts, where marking
  everything as read asks first. Every text the account sees, with filter, tags and search. The info
  screens the account sees. The whiteboards the account sees, with owner and dates. Each appears only
  where the account has the module.
- **Email**: the IServ mailbox with folders, search, reading, replying, forwarding, drafts,
  attachments, read receipts, tags, sender addresses and recipient search. An email can become an event
  in your IServ calendar. Out-of-office note, forwarding, filter rules and signatures are edited in the
  app. Mark as spam moves an email to the spam folder, with undo. Sending, deleting for good and every
  settings change ask first.
- **Files and contacts**: your own files and group folders with search, open and save. An upload asks
  first. The school address book, and mailing lists with their addresses. A list is imported from a
  text or CSV file or deleted, each after a confirmation.
- **Overview and settings**: an overview dashboard with unread badges, and settings for subject and
  teacher names and colours, lesson times, phone numbers and notifications.
- **Accounts without a linked profile** finish the setup and use what the account offers, for
  example chat, noticeboards, holidays and school events.
- **Six languages**: German, English, Arabic (right-to-left), Turkish, Russian and Ukrainian.
  Pick one in the setup wizard or under Settings; the default follows your device.
- **Calendar subscription**: set up per child from Settings: pick lessons, school holidays,
  public holidays, marked exams, approved absences, own entries and school events, then subscribe
  your calendar app to the generated link. An account without a linked profile gets one per school with
  holidays and school events.
- **Help**: **Settings → Help → Report a problem → Save report** writes `ranzenpost-report.zip`
  with versions, the structure of each IServ module and the log. Names, amounts and secrets are
  removed. For modules run by another provider, such as Klassengeld, the report signs in there once.
  It opens no letter and no single entry. Attach the file to a GitHub issue.

## Which IServ modules are supported

Ranzenpost reads the timetable ("Stunden- und Vertretungsplan"), parent letters, noticeboards,
absences, parent-teacher conferences, the messenger, the school calendar, tasks, news, forums, texts,
info screens, the mailbox, files, the address book and mailing lists. If the Schul-App timetable lists no
lessons and the school has no lesson slots there, Ranzenpost reads the older timetable module at
`/iserv/time-table/` instead and remembers that for the school. A week in which IServ lists no
lessons shows a short note instead of an empty grid. A school with only the older
"Stundenplan" module at `/iserv/timetable/` sees it listed as present but not supported yet.

Ranzenpost writes letter confirmations, letter replies and archiving, absence reports,
messenger messages, conference bookings, task hand-ins, emails, mailbox settings, file uploads and
mailing list changes. What sends, books, hands in, uploads or deletes asks you first. After every login it checks which of these modules your account
offers and hides the rest. Modules it does not support yet are named in the settings by their
official IServ name, with a button that opens a prefilled GitHub issue. The full map of modules,
what parents can do in each according to the IServ documentation, and what Ranzenpost reads and
writes is in
[docs/iserv-modules.md](https://github.com/githuber110/ranzenpost/blob/master/docs/iserv-modules.md).

## Setup

Everything happens in the app's own UI. No YAML, no tokens to copy:

1. Enter your school's address.
2. Sign in with your own parent account (username or email plus password).
3. If your school uses two-factor authentication, type **one** current code from the authenticator
   app you already use. The app registers its own token invisibly; your existing app keeps working.
   If your school requires two-factor and the account has none yet, the app sets it up with you:
   it shows the key as a QR code and as text for your authenticator app and activates it with the
   code you enter.
4. Pick your child, optionally store the school's phone numbers. Done.

Every step has **Back** and **Start over**, so you can never get stuck. If the app later loses
access (token removed in IServ, password changed), it detects this on startup and offers to set up
again.

The app can hold several schools or IServ accounts at once. Each one keeps its own login, children,
subject names, lesson times, phone numbers and holiday region; the children of every school appear
side by side. The same school address may be connected twice with two accounts. A school that lists
no children for the account still brings its letters, posts and chat; where no child decides the
school, the app asks which one.

## Install

1. In Home Assistant: **Settings → Apps → App store → ⋮ → Repositories** and add this
   repository's URL.
2. Install **Ranzenpost (IServ)** and open it. Setup runs entirely in the app's own UI.

The app image is published per release; the version in `config.yaml` and the pushed image tag are
verified against each other in CI.

## Updating

Keep the app and the integration on the same release.

- App: **Settings → Apps → App store** (the **Install app** button) **→ ⋮ → Check for updates**, then
  **Ranzenpost (IServ) → Update**.
- Integration: open **Ranzenpost** in HACS and install the update, then restart Home Assistant and
  reload the browser page.

The integration sends its version with every call, so both sides can tell when the other one is
behind. Home Assistant then shows a repair with the steps above: the app is behind, the integration
is behind, or a newer integration is installed but Home Assistant has not restarted yet (that repair
offers the restart). The app shows the same hint under **Settings** and on the help page, and the
problem report lists both versions. A dashboard card that still runs older code asks to reload the
page. The hints disappear on their own once both sides match.

Turn on **Watchdog** on the app page. Home Assistant then restarts the app on its own if it stops
answering.

## Notifications

Pick where notifications go (a Home Assistant notify service, or type an entity yourself, e.g.
`notify.mobile_app_...`) and which events should notify you: timetable changes, new letters, new
noticeboard posts, new parent-teacher days, new chat messages, new tasks, new news items, new forum
posts, new texts and IServ outages. Every timetable
change is reported, substitutions and cancellations alike. A hint that a school's login needs you
is always sent. A test button confirms the service works.

## Home Assistant integration

The app serves a small read-only API on its own port (8099, the same one Ingress uses) for the
Ranzenpost integration, which turns the data into devices and entities in Home Assistant. The API
needs a bearer token that the app creates on its first start and keeps in `/data/integration_token`
(owner-only file permissions). On every start and after every rotation the app announces itself
to the Supervisor (discovery), so the integration finds the host, port and token without any typing.
Without a Supervisor, copy the token from **Settings → Home Assistant** in the app and enter it in the
integration by hand.

**Settings → Home Assistant** shows whether the integration has called in, when it last did, the
token with a copy button, a **Regenerate** button that invalidates the old token after a confirmation,
and the install link for the integration. Calls through the Ingress proxy cannot use the API, a wrong
or missing token answers 401, and ten failed attempts a minute from one source are answered 429.
Every other route on that port only answers the Supervisor's Ingress proxy.

Install the integration itself through HACS: search for **Ranzenpost** in HACS, which lists it in its
default store, or use the button in the main
[README](https://github.com/githuber110/ranzenpost#3-add-the-integration), then
**Settings → Devices & services → Add integration → Ranzenpost**. With a Supervisor it is found and
set up automatically; otherwise enter the host, port and token shown above by hand.

The integration creates one device per school and one per child. Entity IDs use the child's first
name, for example `sensor.ranzenpost_mia_next_lesson`. Every entity carries its facts as
attributes, so an automation or a template can read them without a second call.

- **Per child:** calendars for lessons, exams, absences and own entries. Sensors for the current and
  next lesson, the end of school, the next school day, changes today, the next exam, unread letters
  and posts, open absences and the timetable stamp. The binary sensors `school_day_today` and
  `timetable_changed_today`. The event `timetable_changed`.
- **Per school:** calendars for holidays and school events. Sensors for the next holiday, the next
  free day, the next parent-teacher conference, unread letters, posts and emails, open tasks, news,
  unread forum posts, texts and the connection.

Every entity with its attributes, the values and units, the triggers, four automation recipes, the
options, help for common problems and how to remove Ranzenpost are
in the
[Home Assistant reference](https://github.com/githuber110/ranzenpost/blob/master/docs/home-assistant.md).
The exact JSON shapes behind the entities are in `custom_components/ranzenpost/contract.json`.

Automations can use device triggers without YAML. A child's device offers **Timetable changed**,
**Lesson cancelled**, **Substitution**, **New letter**, **New noticeboard post** and **Absence status
changed**; a school's device offers **School unreachable**, **School reachable again**, **Login
needed**, **New letter**, **New noticeboard post**, **New task**, **New news item**, **New forum post**
and **New text**. The conditions **Is a school day** and **A lesson is running** check a child. When a
school's login needs you, a repair names the school and clears once the login works again.

## Dashboard card

The integration registers `custom:ranzenpost-card`. Add it from the card picker and set it up in the
visual editor: a title, the children, the blocks (`today`, `next_day`, `next_lesson`, `week`, `changes`,
`letters`, `noticeboard`, `absences`, `conferences`, `holidays`, `school_events`, `tasks`, `news`,
`forums`, `texts`) and a size per block, `compact` or `normal`. The `today` block also takes `switch`:
`end` shows the next school day after the last lesson, a time such as `"15:00"` from that time on. Only blocks of modules your school has are offered, and a block without
content is not drawn. An account without a linked profile still gets letters, noticeboard, conferences,
holidays, school events, tasks, news, forums and texts of its school. After installing or updating the integration, restart
Home Assistant and reload the page so the browser loads the new card.

## Desktop and tablet

From 900 pixels wide the app shows a navigation rail instead of a tab bar, sheets become centred
dialogs, and the overview lays its chapters out as a grid. From 1280 pixels, letters, posts,
absences and chat rooms open in a pane beside their list, and the timetable shows every child side
by side instead of one at a time. Below 900 pixels nothing changes from the phone layout, and in
Arabic the rail and the pane mirror to the other side.

## Calendar port

Calendar feeds are served by a second, token-protected port (8100) so they can be reached directly
by calendar apps, separate from the app's own Ingress UI. It is **off by default**. To turn it on:
Home Assistant → **Settings → Apps → Ranzenpost (IServ) → Configuration → Network**, then
enable **"Show disabled ports"** and map port 8100.

A subscription link on this port shows what its calendar contains, a child's timetable or a
school's holidays and events, to anyone who has the link, without a password. Treat the link itself as the secret, and revoke/rotate it in Settings if it leaks.
Nabu Casa remote access does **not** forward app ports: reaching port 8100 from outside your home
network needs your own home network access or a VPN.

Google Calendar and Outlook.com fetch subscriptions from the internet and never reach port 8100.
For them, choose **Everywhere** when you create the calendar. The Ranzenpost integration then
serves that feed as a Home Assistant webhook: through Home Assistant Cloud (Nabu Casa) when you
have a subscription, otherwise under your external URL from Settings → System → Network. Anyone
with that address sees the feed without a password. Renewing or deleting the link ends it.
Home Assistant writes that address into its own log when a request other than GET reaches it, so
remove it before you share a Home Assistant log.

## Privacy & secrets

Your school URL, login and the app's own 2FA key stay on your Home Assistant instance (`/data`).
The connector only ever reads your own authorized children's data, and write actions (reporting an
absence, handing in a task, sending an email, uploading a file, changing your password and more)
always require an explicit confirmation.

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
