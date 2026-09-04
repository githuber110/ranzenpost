# Changelog

Version scheme: `YYMM.RR.MM` - YYMM is year+month, RR is the public release number (MM resets to
00 at release time), MM is an internal pre-beta counter incremented until the next release.

## 2609.01.05

- The overview opens what you tap: a noticeboard post now unfolds in place over the overview and
  a parent letter opens its page with a back button that leads back to the overview instead of
  stranding you in the Post tab. Chat rows still jump into the room, because that is where the
  conversation continues.
- The timetable can be paged week by week with a horizontal swipe. Hairline arrows sit in the
  margin beside the grid, appear only in a direction that actually exists, and mirror themselves
  in Arabic; the grid itself keeps its full width. Swiping never interferes with scrolling, with
  pull-to-refresh, or with tapping a lesson.
- Tapping a lesson now also spotlights that subject across the whole week: the other cells dim
  while the subject keeps its colour and gains a fine outline, without any pulsing. The detail
  sheet still opens as before and stays; closing it keeps the spotlight, tapping an empty slot
  clears it, tapping another subject moves it, and switching tabs resets it. The spotlight
  follows the subject when the week is swiped, and the sheet quietly says which of the week's
  occurrences you are looking at.
- The overview no longer highlights the running or the next lesson. Lessons that are over stay
  greyed out as before, and the entry position when the overview opens still follows the current
  hour.
- The "until HH:MM" in the overview head is gone. Instead the last lesson that actually takes
  place shows its time as a span, which answers the question parents really ask - when is school
  out. If the last lesson is cancelled, the span moves to the one before it.
- The chapter head of the overview lost its bullet. It was reading like a list entry next to the
  subject dots below it; heading and entries are now told apart typographically instead.
- "Upcoming" only appears when there is something upcoming. With content it sits directly behind
  "Today", its duplicate "Report" button is gone - that function lives in the Absence tab and
  nowhere else - and an empty chapter no longer takes up a screen. A load failure is still shown
  rather than swallowed.
- The overview sorts itself: sections with something new move up behind "Today", which always
  stays the anchor. The order is settled when the overview is entered, never while a thumb is
  scrolling. The peek arrow at the bottom carries the same counter pill as the tab badges, from
  the same source, and only when there is something to count.
- The notification settings were cleared out. The "Notification in Home Assistant" row and the
  free-text field for a custom target are gone - the app can only send to notify entities, so it
  now says so by offering exactly those, in a selection dialog with search, grouped and with
  their friendly names. Chosen targets appear as removable chips. Without a target nothing is
  pushed any more instead of disappearing into an invisible default.
- The spinner on the test button no longer spins wrongly the first time. There is now a single
  spinner definition with one fixed rotation, and it can no longer be squashed out of round by
  its surroundings; spinners outside a button had in fact not been animated at all.
- Timetable pushes close two gaps. A rebuilt timetable without any marked change now sends a
  plain "timetable changed", and when the last change is withdrawn the app says so instead of
  going quiet - the very message that prevents a missed lesson. The signature behind it is built
  from the IServ fields alone, so recolouring a subject never triggers a push.
- Subscribing to the calendar no longer asks for an address. The app asks Home Assistant where
  it lives and builds the address itself; a previously typed address is cleaned up. This also
  fixes the dead "add to calendar" button, which came from an address that carried a port twice
  and therefore produced an invalid link. The feed port is opened automatically on the first
  subscription, and the restart it needs is one button in the sheet: the app says plainly that
  it will be unreachable for a few seconds, restarts on the tap, waits until it answers again,
  reloads and puts the subscription sheet back on screen. It never restarts by itself - a guard
  refuses any restart that does not come from that button, and a tripwire keeps every background
  module away from the endpoint. A Nabu Casa address still cannot work here, because the remote
  connection only
  forwards the Home Assistant port and no add-on ports - the address therefore stays local, and
  the existing note about home network and VPN stays as it is.
- Navigation rework decided by the design round: parent letters and the noticeboard share one
  "Post" tab with a segment that carries a separate unread counter per side, the letter archive
  moved from a second segment into a folder row, and the freed place became a "Chat" tab. The
  provisional header entry for the messenger is gone; the tab bar derives its column count from
  the number of tabs, which also fixes the gap when the school has no timetable.
- The overview shows unread chat rooms in a chapter of their own, but only while something is
  unread, and each row jumps straight into that room.
- Create a room with a teacher: search over the IServ autocomplete (debounced, older requests
  cancelled), child selection when there is more than one, an optional invitation for the other
  parents that stays switched off by default, a duplicate check against the local room list, an
  explicit summary with the teacher's name as the dominant element, and a single form POST with
  a freshly fetched CSRF token. A failed attempt re-syncs and re-checks for duplicates before it
  offers a retry; the POST is never repeated on its own.
- "Mark as read" per room: one deliberate action sends the Matrix read marker up to the newest
  message. It is the only sanctioned way the app may ever touch a receipt route - the guard now
  allows exactly one path from exactly one function, and the tripwires prove it stays that way.
- Marking a parent letter as read no longer reports success for letters that still wait for a
  read confirmation; IServ does not accept the read there. The app now checks the answer instead
  of assuming it, names the blocked letters, and offers the confirmation instead of a mark that
  cannot work.

## 2609.01.04

- School messenger (read and reply): room list with filter and unread badges, chronological room
  view with day separators, images opening in the file viewer, attachments via the regular
  attachment flow, paging into older messages, and a compose bar that only ever sends on an
  explicit tap. The app never emits read receipts - teachers never see a read status you did not
  cause yourself. Entry point is provisional (header action) while the navigation rework decided
  by the design round ships with the next release together with room creation.

## 2609.01.03

- In-app file viewer: images open in a full-screen overlay with pinch and double-tap zoom, PDFs
  try the platform's inline renderer and fall back to the download automatically when it is not
  available; other file types download as before. This replaces the new-window approach that the
  Home Assistant companion app does not support.
- Groundwork for the school messenger (Matrix-based): backend client that reads rooms and
  messages without ever emitting read receipts, encrypted token handling, and a send endpoint
  that only ever fires on an explicit user action. No UI yet - it ships with the next release.

## 2609.01.02

- Read confirmations for parent letters: letters that request a confirmation are marked in the
  list, the detail view explains what is asked and sends the confirmation after an explicit
  prompt, and the push notification mentions an outstanding confirmation. Accept/decline replies
  and questionnaires are shown as requiring IServ directly - their submit format is not verifiable
  yet and nothing is guessed.

## 2609.01.01

- Attachments and the sick-note PDF now open directly in a viewer where the platform allows it
  (PDF and images); anything else, blocked pop-ups and failures fall back to the download.
- Absence wizard polish: dependent inputs (lesson range for a part-day sick note, pick-up time for
  daycare) reveal inline below the choice instead of forming an extra step; the notifiable-disease
  notice on the review page opens in full instead of being truncated; date and time fields are
  clamped so native WebKit widths cannot overflow the step.
- The settings screen uses the same compact header as every other screen.
- README with feature overview and example screens (fictional fixture data only).

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
