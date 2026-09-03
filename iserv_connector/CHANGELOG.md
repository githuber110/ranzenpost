# Changelog

Version scheme: `YYMM.RR.MM` - YYMM is year+month, RR is the public release number (MM resets to
00 at release time), MM is an internal pre-beta counter incremented until the next release.

## 2609.01.00

- Subscribable calendar: per-child feeds (timetable, school holidays, public holidays, exam marks,
  approved absences) served token-protected on a separate, off-by-default port, with a QR code and
  webcal link in the timetable view; cancelled lessons are included and labelled, never hidden.
- Holiday calendar for all 16 German federal states with a suggestion derived from the school's
  postal code where available; full holiday weeks replace the timetable grid, single free days are
  shown by their full name; lessons are only ever overridden when the source proves the day is
  school-free.
- Exam marks: tap a lesson to mark it as a test with a free-form name and self-learning name chips;
  marks are highlighted in the timetable and today view, and a clarification panel handles
  cancelled, moved or substituted lessons instead of silently guessing.
- Guided step-by-step flows: absence reporting rebuilt as a wizard for all four types (4 taps for
  the common sick-note case, no scrolling on any step, honest progress dots), and the setup wizard
  moved onto the same scaffold; password and 2FA fields are never retained when navigating back.
- Overview rebuilt as four fixed chapters with snapping pages, per-child pills, a now-anchor and a
  self-disabling fallback to free scrolling; every lesson row is provably on exactly one page.
- New subject colour palette (14 colours, colour-blind-checked) and a fix for user-chosen colours
  being silently overwritten by the auto-assignment.
- Full script coverage for the shipped UI fonts: Cyrillic and Arabic faces load on demand, a guard
  test compares every language bundle against the shipped font tables.
- Sick-note PDF now embeds a Unicode font subset so non-Latin names render correctly; unsupported
  scripts are refused instead of printing replacement characters.
- Attachments and the sick-note PDF open reliably under Home Assistant ingress (same-context
  download instead of a new tab).
- Notification settings rebuilt: targets grouped by category with friendly device names and a
  per-target test button; push messages are localised into all six languages with correct plurals.
- Unified API error responses distinguishing auth, configuration and network failures; the UI
  routes expired sessions to reconnect instead of showing empty screens.
- Crash-safe persistence: every settings write is atomic, corrupted files are quarantined instead
  of wiping user data.
- Sidebar entry is visible to all household users (was admin-only by default).
- Accessibility and i18n hardening: logical CSS everywhere, direction-safe rendering of school
  content, complete plural categories for Arabic, Russian and Ukrainian, larger tap targets and
  WCAG-checked text contrast in both themes.

## 2609.00.02

- Multilingual UI: German, English, Arabic (RTL), Turkish, Russian and Ukrainian, with a language
  picker in the setup wizard and Settings; dates, times and numbers follow the active language.
- Leave-request attachments: upload with a per-file and a total-size limit, enforced both in the
  UI and on the server.
- Sick-note confirmation as a printable PDF.
- Disconnect now also clears the stored school URL, children, phone numbers and credentials from
  the app, not only its local caches.
- Responsive-layout guard (Playwright) across the app's breakpoints, larger tap targets.

## 2609.00.01

First release under the Ranzenpost name.

- Guided setup: school address, parent login, invisible two-factor registration (one code from the
  authenticator app you already use), child selection, optional school phone numbers. Back and
  start-over available in every step; the app re-checks its access on every launch and offers to
  set up again when it was revoked.
- Timetable per child with substitutions and cancellations marked, week navigation, lesson times
  read from IServ, and configurable subject/teacher names and colours.
- Parent letters: current and archived, app-side read/unread state with swipe, attachments,
  archiving.
- Pinboards: merged newest-first feed with source badges, per-board view with swimlanes, full-text
  search, attachments, app-side read state.
- Absences: all four IServ types, calendar range picker, notifiable-disease hint, school phone
  numbers as tap-to-call.
- Parent-teacher conference days, overview dashboard with unread badges.
- Notifications for every timetable change, with a freely configurable notify service and a test
  button.
