# Ranzenpost (IServ)

A friendly parent frontend for IServ school servers: timetable with
substitutions, parent letters, pinboards and absences — in one calm, mobile-first UI.

## What it does

- **Timetable** per child, with substitutions and cancellations marked, week navigation and
  lesson times read straight from IServ.
- **Parent letters** — current and archived, with a read/unread state the app maintains itself
  (IServ does not expose one per letter), attachments, and archiving.
- **Pinboards** — one merged newest-first feed across all boards with a source badge per post,
  jump navigation into a single board (with its swimlanes), full-text search, attachments and an
  app-side read state.
- **Absences** — view and report, covering all four IServ types (sick note, leave request,
  deregistration from bus/kindergarten/lunch, and day-care deregistration), with your school's
  phone numbers one tap away. Leave requests can carry file attachments; a sick-note report can be
  saved or printed as a confirmation PDF.
- **Parent-teacher conference days**, an overview dashboard with unread badges, and settings for
  subject/teacher names and colours, lesson times, phone numbers and notifications.
- **Six languages** — German, English, Arabic (right-to-left), Turkish, Russian and Ukrainian.
  Pick one in the setup wizard or under Settings; the default follows your device.
- **Calendar subscription** — set up per child from Settings: pick lessons, school holidays
  and/or public holidays, then subscribe your calendar app to the generated link.

## Setup

Everything happens in the app's own UI — no YAML, no tokens to copy:

1. Enter your school's address.
2. Sign in with your own parent account (username or e-mail plus password).
3. If your school uses two-factor authentication, type **one** current code from the authenticator
   app you already use. The app registers its own token invisibly; your existing app keeps working.
4. Pick your child, optionally store the school's phone numbers — done.

Every step has **Back** and **Start over**, so you can never get stuck. If the app later loses
access (token removed in IServ, password changed), it detects this on startup and offers to set up
again.

## Install

1. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add this
   repository's URL.
2. Install **Ranzenpost (IServ)** and open it. Setup runs entirely in the app's own UI.

The app image is published per release; the version in `config.yaml` and the pushed image tag are
verified against each other in CI.

## Notifications

Pick where notifications go (a Home Assistant notify service, or type an entity yourself, e.g.
`notify.mobile_app_...`) and which events should notify you. Every timetable change is reported —
both substitutions and cancellations. A test button confirms the service works.

## MQTT (experimental)

If you fill in **mqtt_host** (plus port/user/password as needed) in the app options, the poller
publishes Home Assistant MQTT discovery for each child plus a state topic per poll — useful for
dashboards outside this app's own UI. Off by default; leave `mqtt_host` empty to skip it entirely.

## Calendar port

Calendar feeds are served by a second, token-protected port (8100) so they can be reached directly
by calendar apps, separate from the app's own Ingress UI. It is **off by default**. To turn it on:
Home Assistant → **Settings → Add-ons → Ranzenpost (IServ) → Configuration → Network**, then
enable **"Show disabled ports"** and map port 8100.

A subscription link on this port shows that child's timetable to anyone who has the link, without
a password — treat the link itself as the secret, and revoke/rotate it in Settings if it leaks.
Nabu Casa remote access does **not** forward add-on ports: reaching port 8100 from outside your home
network needs your own home network access or a VPN.

## Privacy & secrets

Your school URL, login and the app's own 2FA key stay on your Home Assistant instance (`/data`).
The connector only ever reads your own authorized children's data, and write actions (reporting an
absence, archiving a letter, changing your password) always require an explicit confirmation.

**Disconnect** (Settings) attempts to remove the app's 2FA token from IServ, then deletes the
school URL, children, phone numbers and login/2FA secrets from this app — you land back at the
setup wizard.

Your school login and 2FA key are encrypted at rest (Fernet). Each calendar subscription gets its
own random token, stored in plain `calendar_subscriptions.json` (owner-only file permissions),
since it must be readable by external calendar apps; a token grants access to that one subscription
only and can be rotated or revoked from Settings. For stronger protection of the encrypted secrets, set a **passphrase** in the
app options: the encryption key is then derived from it at runtime (scrypt) and never written to
disk — only a salt is stored. A snapshot of the `/data` folder alone can then no longer be
decrypted without the passphrase. Note: a *full* Home Assistant backup also contains the app
options (including the passphrase), so treat full backups as trusted, the same as Home Assistant's
own stored credentials.

Not affiliated with IServ GmbH.
