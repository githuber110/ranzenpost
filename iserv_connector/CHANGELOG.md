# Changelog

Version scheme: `YYMM.N.P`, following Home Assistant. YYMM is year and month, N counts feature releases, P counts
fixes. Test builds carry a `b` suffix, for example `2609.2.1b0`, and sort below the release.

## 2609.4.0

### New

- Lesson tiles show the subject name, the room and the teacher when the tile has room for them. Tablets and laptops show
  the name and room, wide screens also the teacher, with taller rows. Phones keep the short code. Your own subject names
  from the settings come first. Today's rows name room and teacher. The dashboard card does the same.
- Timetables from the school app mark cover lessons, cancelled lessons and moved lessons when the school releases
  substitutions, and send the usual change notification.
- The card editor sets the order of the blocks with up and down buttons, so no YAML is needed.
- The card's links open the right place in the app: "Zum Stundenplan" the timetable, the letters and pinboard blocks
  their tab, absences and conferences their page.
- A new sensor names the next free day, school holidays or a public holiday. The holiday sensor is now called "Next
  school holidays", because it only counts school holidays.

### Changed

- The holidays block of the card lists free days such as public holidays as well as school holidays, like the app. It
  has no "Show all" link, because the app keeps no separate list.
- Three or more courses in the same lesson show as one course tile on the card, as they do in the app.
- The older IServ absence page no longer counts as an unsupported module when sick notes go through the school app.
- Fewer requests per update: school-wide settings and lesson times are shared for two minutes, and a timetable page
  that refuses the child list is not asked again for an hour.
- As an add-on, the app answers only through Home Assistant Ingress. The integration keeps its token access.
- Notifications reach only Home Assistant notify services, also when the service list is unavailable.
- Texts in all six languages are shorter and use one name for each thing.
- The problem report describes every entry of a list, not only the first, and reads the request page of a module.
- The problem report reads modules run by other providers, such as Klassengeld, one level deeper and still shows only
  how their data is built, within its own time limit. It names a missing timetable as missing, lists the school's
  absence settings and never counts sick notes.

### Fixed

- "Zum Stundenplan", "Alle ansehen" and the device link open the app again on Home Assistant versions that call add-ons
  apps, instead of the default dashboard.
- The card editor no longer stays empty when Home Assistant's form cannot be built; it shows simple fields instead.
- Marking a lesson as an exam or as cancelled only marks that subject when several courses share the lesson. Marks keep
  their lesson when you rename a subject code.
- Exam marks stay visible on coloured subject tiles.
- The problem report follows the Klassengeld sign-in through IServ instead of stopping at the sign-in page.
- Request lines in the log show real sizes again.
- Lesson, exam, school-end and absence times in Home Assistant follow the school's own lesson length.
- Absences show an error instead of no children when the school app does not answer. One bad date no longer breaks the
  list.
- The diagnostics download no longer carries child names in its keys.
- Removing one Ranzenpost entry keeps the dashboard card for the others.
- Notices name the given name of a child written "Surname, Given name".
- A refused password change shows the school's message.
- Switching weeks or children quickly no longer shows an older timetable.
- Going back while a letter loads, or opening another one, no longer shows the wrong letter.
- A save that ends on the sign-in screen no longer reports "Saved".
- The message at the bottom stays centred when reduced motion is on.
- The card links only to the app's own pages.
- Opening an unread letter asks the school once, so the letter opens on the first tap.

## 2609.3.0

### New

- Timetables of the IServ `time-table` module show moved lessons at both places, marked "Moved" with "to Thu 5" and
  "from Tue 6", and the school's note at its lesson. Every change is marked, including substitutes and new subjects
  whose teacher the school does not name, and classes taught together. The change notification counts the marked
  lessons.

### Changed

- The messenger asks the school server only for the data it shows. Checking for new messages loads far less data, the chat
  list about a third of what it did.
- With several schools, teacher search, new chats and absences ask which school you mean instead of using the first one.
  Settings show when a school lists no profiles for your account.
- Children are matched by name the same way everywhere, including name order, hyphens and ß. When two children share a
  name, nothing is guessed.
- The full problem report shows how each IServ module is built, including modules run by other providers such as
  Klassengeld after their sign-in. It also marks modules that only show data. It leaves out names, amounts and tokens,
  opens no letter or single entry, and stops after one minute. Requests in the log name their school.

### Fixed

- The timetable shows again when the school app does not release it to parents but the IServ `time-table` module
  does. Lessons without a teacher and changes with unknown type codes no longer break the week.
- The app no longer opens parent letters in the background to build its search. Before, this marked every letter as read
  at the school right after installation. Full-text search covers letters you opened in the app; the rest are found by
  title, sender, child and class. New letters get the normal notification.
- Room and teacher changes from the IServ `time-table` module now show in the week, with cancellations and extra
  lessons. The change notification counts only changes that affect a lesson.
- A school whose account lists no children keeps its letters, pinboard, conferences and chat updated instead of stopping.
- A short outage of the school account no longer creates a second child or a second Home Assistant device, and a child
  stored twice is merged back into one.
- The sick note PDF opens for the right school when several schools are set up.

## 2609.2.2

### New

- A letter can take a message to the school when its IServ page offers a reply, once any read confirmation is done.
  The message shows as a preview first and goes out only after you send it, never twice by itself. Letters whose
  reply form the app does not recognise offer no reply.

### Changed

- Versions follow the Home Assistant scheme from now on, for example `2609.2.2` rather than `2609.02.02`. Home
  Assistant warns about an integration that is a release behind only when the add-on brings new features, not for
  fixes.
- A week in which IServ lists no lessons now says so. The timetable shows a short note instead of an empty grid.
- After the timetable source changes, parallel courses may ask once to be chosen again.
- A new plan entry now starts and ends on the day you picked, instead of running to the end of the school year by
  default. A repeating break or club that covers only that one day shows a short hint, with a button to extend it to
  the summer holidays.
- Opening, confirming, replying to, archiving, restoring or marking a letter as read now works only for a letter in
  the letter list of its own school. Any other letter is refused with a short note before any action reaches the
  school. An attachment opens only from a letter the app has shown.
- Error lines in the log name the cause without letter ids, links or the school address. This covers letters,
  absences, chat, the noticeboard, child lists, two-factor removal and the regular check.

### Fixed

- `sensor.ranzenpost_<child>_next_school_day` now includes today while its first lesson has not started yet, so a
  time trigger with an offset on that sensor fires again instead of skipping straight to the day after.
- The timetable no longer stays empty at schools that keep their plan in the older IServ timetable module. When the
  Schul-App timetable lists no lessons, Ranzenpost reads the older module and remembers that for the school.
- The problem report now reads the older timetable module the way the app does. Chat room ids no longer show in the
  report or the log.
- HACS shows the integration with its icon and recognises the licence.
- Marking letters as read goes on at the other schools when one school does not answer, and the app now says when
  letters could not be marked instead of reporting nothing to mark.

## 2609.02.00

Ranzenpost now reaches into Home Assistant, handles several schools and knows your school's lesson times.

### Highlights

- **Home Assistant integration and dashboard card.** Install the integration through HACS. It finds the add-on or
  offers to install it. You get one device per school and one per child, with calendars for lessons, exams, absences
  and holidays, sensors, and a timetable change event. Automations get device triggers and conditions such as
  "lesson cancelled", "new letter" or "is a school day". The card `custom:ranzenpost-card` is built from the app's
  blocks, such as today, next lesson, week, letters and holidays, in a visual editor, and it registers itself.
  ![The app next to the dashboard card](https://raw.githubusercontent.com/githuber110/ranzenpost/v2609.02.00/docs/screenshots/hero.png)
- **Several schools in one app.** Add further schools or IServ accounts, each with its own login, children and
  settings. Letters, posts and chats merge into one feed with a school chip on every row. Children are sorted by name
  across schools. A school whose login fails is flagged on its own while the others keep working.
- **Lesson times and own entries.** Each school gets a lesson times page: start and duration per period, taken from
  IServ or set by you, with extra periods at the end of the day. Add breaks, clubs and appointments, once or repeating, for one child or
  all. The timetable, today, the card and the calendar feed show them. On request each child gets a Home Assistant
  calendar with them. Lessons come first: an entry that a lesson covers is shortened, never deleted. Before the summer
  holidays one button copies the series into the next school year.
- **Arrange the app yourself.** Switch the ten overview blocks on or off, choose compact or normal, and set their
  order. The bottom bar can be ordered too. One switch hides an IServ module from the app, the card and Home
  Assistant.
- **Tablets and laptops.** A navigation rail replaces the tab bar. Letters, posts, absences, chats and settings open
  beside their list, and the timetable shows every child side by side.
  ![The timetable at desktop width](https://raw.githubusercontent.com/githuber110/ranzenpost/v2609.02.00/docs/screenshots/desktop-timetable.png)

### Also new

- Class timetables with parallel courses: choose once per person which courses they attend. The timetable, the card,
  the calendar feed and Home Assistant then show only those. Until you choose, course changes send no push.
- Subject colours from a palette of 24, or any colour of your own. Each works in the light and the dark theme.
- A read confirmation with a message field lets you write to the school. You see the message before anything is sent.
- A help page with a troubleshooting report for a GitHub issue: versions, module states and the log, with names,
  addresses and secrets removed. The app sends nothing on its own.
- The settings list the IServ modules your account offers. Modules Ranzenpost does not know yet lead to a prefilled
  GitHub issue. The older timetable module shows as present but not supported yet.

### Changed

- Settings are grouped by use: Display, Notifications & Home Assistant, School, Areas, Account, Help. The calendar
  subscription and Subjects & teachers are full pages. The wording is plainer and uses names instead of role words.
- A new overview starts with six blocks. An overview you already arranged stays as it is.
- Only the modules your account offers appear, in the app and in Home Assistant.
- Calendar events carry the subject's colour, code and name. Cancelled lessons are struck through.
- When IServ sends only a subject's long name, Ranzenpost derives a short code you can edit.
- Times follow your language's format everywhere, lesson times included.
- Outage and recovery pushes have their own switch.
- Ranzenpost asks the school only about children the account lists, and sends absences only for entries the school
  offers.
- The log names every error of a check with its cause and every push with its reason. It holds no content and no
  names.

### Sign-in and outages

Ranzenpost signs in less often when something is wrong, so the school is less likely to lock the account.

- Each case has its own message instead of "wrong password" or "unreachable": a locked account, an outage or
  maintenance, a request to slow down, two-factor made mandatory later, an unknown account, a blocked default
  password, a sign-in without a session, and a refused two-factor code.
- After a refused password or a lock, Ranzenpost waits 30 minutes, then longer up to 12 hours. A new password is tried
  at once. The wait starts over after a day without a new lock.
- A refused two-factor code leads to a new setup instead of a password prompt. If it keeps failing, you get one push
  and one Home Assistant repair, and nothing more after that.
- No push goes out while IServ is down. You get one when it is back.
- After wrong passwords the setup keeps what you typed and waits briefly with a countdown instead of stopping.

### Fixed

- A subject that appears in a later week, or a week without it, no longer marks unchanged lessons as changed. The
  false "timetable changed" pushes are gone.
- Two groups of one subject with the same substitute no longer show twice or as cancelled.
- Holiday weeks load again.
- Removing an exam mark or an own cancellation reaches a subscribed calendar as fast as adding it.
- The card editor keeps a dropdown open until you choose.
- A timetable, message list or child list that cannot be read shows an error instead of an empty list.
- Settings saved at the same time no longer overwrite each other. A removed school leaves nothing behind.
- Signing in with another account forgets the old children and course choices, even while a list is still loading.
- Chats load for schools that keep the chat credentials out of the page. An expired school app session is renewed.
- The course page starts with every course ticked, so saving right away hides nothing.
- Cancelling the withdrawal of an absence returns to its details. A new sheet always starts empty.

### Removed

- The MQTT bridge. The integration replaces it, and the four `mqtt_*` options disappear.

### Upgrade notes

- Install the add-on and the integration of the same release. After installing or updating the integration, restart
  Home Assistant and reload the page. A repair tells you when one of them is a release behind.
- The first start moves children to a new internal key made of school and child. Calendar subscriptions keep working.

## Earlier test builds

Internal test builds under version 2609.00 and 2609.01, before the first public release.
Covered the initial guided setup, timetable, parent letters, absences, messenger, noticeboard
and calendar subscription features, together with a long series of small fixes to
notifications, calendar naming, module detection and the settings pages.
