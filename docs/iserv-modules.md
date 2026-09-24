# IServ modules and what Ranzenpost does with them

This page maps the IServ modules from the official user documentation to what Ranzenpost reads and
writes. It is the source for the module registry in `backend/app/modules.py` and for the module
section of the README. Everything marked "unverified" could not be confirmed from the documentation
or from the code. Facts about a real instance come from the owner's own school and carry no school
name.

Sources, all public:

- Module index with slugs: <https://doku.iserv.de/modules/> (56 entries, read on 2026-09-19).
  Two modules are marked "(veraltet)", obsolete: `timetable` and `absence_obsolete`.
  One is marked "(neu)", new: `dsa-timetable`.
- Parent quick start, PDF "IServ-Schnelleinstieg für Eltern", 14 pages, dated July 2026:
  <https://iserv.de/downloads/f6f70b2cfbb635b07609196a30eb34af/IServ_Akademie_Schnelleinstieg_Eltern_RZ-005.pdf>
- Brochure "Einfach mit Eltern kommunizieren", 11 pages, dated January 2025:
  <https://iserv.de/downloads/29998666a590f5a114411d45e22f50ea/IServ-Einfach-mit-Eltern-kommunizieren-190x270mm_RZ_SCREEN.pdf>
- Parent login: <https://doku.iserv.de/web/> (section "Anmeldung für Eltern") and
  <https://doku.iserv.de/manage/user/parentmanagement/>.
- The parent communication overview <https://doku.iserv.de/parentinformationsystem/> answered 404
  on 2026-09-19. Search engines still list it. Its content is not cited here.

## What the parent documents say in general

The quick start and the brochure agree on these points.

- Parents need their own parent account. A child's account does not show the parent modules.
- A parent account is linked to one or more children of one school. A second school means a
  second account.
- Parents log in with the e-mail address they registered with, not with a user name.
- The start page shows tiles for the central modules, the module list in the left navigation and
  the linked children.
- Not every module exists at every school. The school decides which ones are installed and which
  ones parents may see.
- Notifications reach parents by e-mail, as push messages in the IServ app and as a bell icon in
  the web interface. Parents can switch the e-mail notifications per module.
- Parents never see the data of the child's own account, for example the child's messenger rooms.
- The brochure lists these modules for parents: parent letters, messenger, translation of parent
  letters, absences, parent-teacher conference days, timetable with substitutions, class money and
  the calendar. The calendar is marked as "in planning for parents".

## Module table

Status values: supported (Ranzenpost reads or writes it), detected only (Ranzenpost names it in
the settings hint when the start page links it, nothing more), not supported (no code path and no
name yet), unverified (the documents do not settle the question).

| Module (official German name) | Slug | Edition | Parent functions per docs | Ranzenpost reads | Ranzenpost writes | Status | Source page |
|---|---|---|---|---|---|---|---|
| Stundenplan (veraltet) | `timetable` | obsolete | Parents see the timetable and substitutions of their children when the child has the right "Eigenen Stundenplan einsehen". A child selector lists all children. | Child list from the selector on `/iserv/time-table/`, the week as JSON from `/iserv/time-table/data`. Used only when the child carries no course ids from the Schul-App record. | Nothing. | supported | <https://doku.iserv.de/modules/timetable/> |
| Stunden- und Vertretungsplan (neu) | `dsa-timetable` | new | Parents and students see timetable and substitutions when the module settings allow it. The quick start says the app shows the child's substitution plan. The brochure says push messages inform parents about changes and that a school can switch this off. | Children, classes and course ids from `users/me`, the week from `current-timetable/`, lesson slots and the guardian setting from the Schul-App API `/iserv/dieschulapp/api/1.0/`. Observed start page segment: `dsa-timetable`, label "Stundenplan". | Nothing. | supported | <https://doku.iserv.de/modules/dsa-timetable/> |
| Abwesenheiten | `absence` | current | Parents report a child sick, request leave and deregister from bus, all-day care or lunch, depending on the school settings. They can add a comment and attachments and see the state of each entry. A school may set a cut-off time for same-day sick notes. The quick start mentions a generated PDF for a written confirmation. With the class register installed, parents can see past absences under "Statistik". | Children, settings, sick notes and requests from the Schul-App API (`sickNotes/`, `userSelection/`, `school-settings/`, the request lists). Observed start page segment: `dsa-absences`, label "Abwesenheiten". | Sick notes, leave requests, deregistrations and all-day care cancellations, with attachments, and the deletion of own entries. Every write needs a confirmation in the app. | supported | <https://doku.iserv.de/modules/absence/> |
| Abwesenheiten (veraltet) | `absence_obsolete` | obsolete | Parents create and view absences for their children, upload attachments and set notification preferences. Entries do not migrate to the new module. Full shutdown is announced for 30 September 2027. | Nothing. The start page segment of this edition is unverified, so the registry cannot name it yet. | Nothing. | unverified | <https://doku.iserv.de/modules/absence_obsolete/> |
| Elternbriefe | `parentletter` | current | Parents read letters addressed to the class or to them, confirm reading, answer with agree or decline, write a free text answer when allowed, download attachments, archive and restore letters. The quick start adds a translation button per letter. | Letter list, letter detail, attachments and the confirmation forms from `/iserv/parentletter/parent/`. | Read confirmation, choice answer, text answer, archive and restore. | supported | <https://doku.iserv.de/modules/parentletter/> |
| Elternsprechtage | `parentconference` | current | Parents book slots with the teachers of their child once the booking period is open, pick the child the meeting is about, change or cancel bookings during the booking period and see their bookings on the module start page. | The attendee overview from `/iserv/parentconference/attendee/`. | Nothing. Booking stays in IServ. | supported | <https://doku.iserv.de/modules/parentconference/> |
| Pinnwände | `dsa-pinboard` | current | Parents see the boards of the classes and groups of their children. A board can allow students and parents to add and edit own tiles. | Boards, columns, tiles and attachments from the Schul-App API `pinboards/`. Observed start page segment: `dsa-pinboard`, label "Pinnwände". | Nothing. Own tiles are not supported. | supported | <https://doku.iserv.de/modules/dsa-pinboard/> |
| Messenger | `messenger` | current | Parents write with teachers in rooms. They may open a room with a teacher only when the school allows it, must name the child the room is about and may add the other parent. They cannot message other parents or students and cannot create group rooms. Teachers invite parents into rooms. | Rooms, messages and media through the Matrix backend behind `/iserv/messenger/`. | Send a message, mark a room as read, open a teacher room. | supported | <https://doku.iserv.de/modules/messenger/> |
| Kalender | `calendar` | current | The module page does not mention parents. The brochure says parents can see the calendar of their children, the class calendar and the school calendar, and marks this as "in planning for parents". | Nothing. | Nothing. | detected only | <https://doku.iserv.de/modules/calendar/> |
| News | `news` | current | The module page does not mention parents. Students see published news and can filter by category. | Nothing. | Nothing. | detected only | <https://doku.iserv.de/modules/news/> |
| Pläne | `plan` | current | Plan files such as substitution plans from timetable software. Parents are mentioned only as readers of plans a school publishes without login. | Nothing. | Nothing. | detected only | <https://doku.iserv.de/modules/plan/> |
| Klausurplan | `exam-plan` | current | The module page does not mention parents. Students see their exams of the next 14 days on the start page. | Nothing. | Nothing. | detected only | <https://doku.iserv.de/modules/exam-plan/> |
| Klassenbuch | `dsa-classregister` | current | Parents see the absences of their children when the school enables "Zugriff der Eltern und volljähriger Schüler auf Abwesenheiten". Sick notes, notes on sick notes, absences by lesson and leave requests are configured here and used by the absences module. Homework and grades are not mentioned for parents. | Nothing directly. The absences module reads what this module configures. | Nothing. | detected only | <https://doku.iserv.de/modules/dsa-classregister/> |
| Aufgaben | `exercise` | current | The module page does not mention parents. Students see tasks, submit files or text and read feedback. | Nothing. | Nothing. | detected only | <https://doku.iserv.de/modules/exercise/> |
| Dateien | `file` | current | The module page does not mention parents. Users manage own files and group folders. | Nothing. | Nothing. | detected only | <https://doku.iserv.de/modules/file/> |
| E-Mail | `mail` | current | The module page does not mention parents. The quick start says parents receive notification e-mails at their external address, not in this module. | Nothing. | Nothing. | detected only | <https://doku.iserv.de/modules/mail/> |
| To-do | `todo` | current | The module page does not mention parents. | Nothing. | Nothing. | detected only | <https://doku.iserv.de/modules/todo/> |
| Umfragen | `poll` | current | The module page does not mention parents. Users answer open polls. | Nothing. | Nothing. | detected only | <https://doku.iserv.de/modules/poll/> |

The other 38 slugs of the index are in the catalogue as well, with their official name and an
English label, so the settings hint can name them. None of them is read or written.

## Which edition each Ranzenpost source belongs to

- `/iserv/time-table/` with its child selector and the JSON at `/iserv/time-table/data` is the
  obsolete module `timetable`. The documentation of that module describes the child selector for
  parents and the right "Eigenen Stundenplan einsehen". The URL path itself is not in the
  documentation. It is verified in the code (`backend/app/iserv/client.py`, `get_children` and
  `get_timetable`) and on the owner's instance, where this path answers 403 since the school moved
  to the new module.
- The Schul-App API `/iserv/dieschulapp/api/1.0/` belongs to the new `dsa-*` modules. The
  `current-timetable/` endpoint is the new module `dsa-timetable`. The documentation of that
  module says the module settings decide whether parents and students may see timetable and
  substitutions. The code reads exactly that switch as `timetable_availableForGuardiansAndStudents`
  from `school-settings/` (`backend/app/service.py`, `TIMETABLE_SETTING`). The start page of the
  owner's instance links `/iserv/dsa-timetable/timetable`.
- The absences endpoints `sickNotes/` and `requestToSchools/` of the same API are the current
  module `absence`. The school settings the code reads, for example the note on a sick note, the
  report by lesson and the cut-off time, are the settings the documentation of the current module
  describes. The start page links `/iserv/dsa-absences/absence-parents`.
- External confirmation (`docs/2026-09-23-iserv-github-recherche.md`, sick-note API research): the reverse
  engineering project [chenning42/iserv-mcp](https://github.com/chenning42/iserv-mcp) independently
  names `GET /iserv/dieschulapp/api/1.0/sickNotes/userSelection/` (child list for a sick note) and
  `POST /iserv/dieschulapp/api/1.0/sickNotes/` (submit) as "the verified DieSchulApp guardian API".
  Ranzenpost already calls exactly these two paths (`backend/app/iserv/dsa.py`,
  `sick_note_children`/`sick_note_children_or_raise` and `sick_notes`; `backend/app/iserv/absences.py`,
  `SICK_NOTES_PATH` used by `_sick_request` for the same `POST sickNotes/`). No deviation, no code
  change needed.
- `pinboards/` of the same API is `dsa-pinboard`. The start page links `/iserv/dsa-pinboard/pinboard`.
- The obsolete `absence_obsolete` has no known path. Unverified.
- The `dsa` prefix of the documented slugs and the `dieschulapp` API host both point at DieSchulApp,
  which IServ integrated. The documentation of `dsa-timetable` lists "DieSchulApp" among its import
  interfaces, but does not name the API path. That link is inferred, not documented.

## How module detection works

After every login Ranzenpost reads the start page `/iserv/` and sends one light request per
supported module (`backend/app/modules.py`, `PROBES`). A probe counts as missing when it answers
403 or 404, lands on the login page or lands back on `/iserv/`. A probe counts as available when it
answers 200 on its own path. Any other answer keeps the last stored state, or the start page links
decide when there is no stored state, or everything stays shown when there is no start page either.
The timetable flag is also switched off when the Schul-App school settings deny the timetable to
guardians.

The start page links are read as URL segments, the first path element after `/iserv/`. A segment
that belongs to a supported module is done. A segment that is a documented slug, or a known
spelling of one (`time-table` for `timetable`, `dsa-absences` for `absence`), goes to the list
"present but not supported" with its official name. Any other segment, except infrastructure links
such as `auth` or `profile`, goes to the list "unknown" with the link text as label. The settings
show both lists in one hint and put both into the prefilled GitHub issue, documented modules by slug
and official name, unknown ones by segment and link text.

A missing module is a state, not an error. Its view, its tab, its notification toggle and its
integration entities are absent. Nothing polls it. When it appears later, the next login or a manual
recheck in the settings picks it up. A school without any supported module shows one calm empty
screen with the settings entry and the hint.

## Promising for parents, not supported yet

- Kalender (`calendar`): the brochure promises the calendar of the children, the class calendar
  and the school calendar for parents, still marked as in planning. The module page does not
  mention parents. Ranzenpost has its own calendar feed and could merge such a calendar once a
  parent account can read one.
- Klassenbuch (`dsa-classregister`): parents may see the absences of their children under
  "Statistik" when the school enables it. Ranzenpost shows the absences it reported itself, not
  the ones the school recorded.
- Klausurplan (`exam-plan`): students see exams of the next 14 days on the start page. The
  documentation does not mention parents. Ranzenpost has its own exam marks on the timetable.
- Klassengeld (`klassengeld`): the brochure says parents pay class money through a payment request
  sent as a parent letter. Nothing in the documentation describes a parent view beyond the letter.
- Pläne (`plan`): plan files such as substitution plans. Parents are mentioned only as readers
  without login. A school that publishes its substitution plan this way is not covered.
- Ganztag (`dsa-daycare`): the all-day care module behind the day-care cancellation that the
  absences module already writes. No parent view is documented.
