# Changelog

Version scheme: `YYMM.N.P`, following Home Assistant. YYMM is year and month, N counts feature releases, P counts
fixes. Test builds carry a `b` suffix, for example `2609.2.1b0`, and sort below the release.

## 2610.6.0

### New

- Moved lessons show as moves. When the school's IServ marks a move, the app, the calendar, the dashboard card and Home
  Assistant name the old and the new place. When only one half is visible, they say the lesson was moved. Lessons in
  Home Assistant have a new attribute `moved`.
- The Today block of the app overview can switch to the next school day, after the last lesson or from a set time.
- The connection to the app can be changed in Home Assistant without deleting anything. Open the three dots of the
  Ranzenpost entry and pick Reconfigure.
- Home Assistant can restart a hung app on its own. Turn on Watchdog on the app page.
- The dashboard card follows the language, the date and time format and the number format set in Home Assistant.

### Changed

- Sensors show `unknown` instead of a wrong value while data is missing. This affects the next absence and the next
  parent-teacher conference, the holiday sensors while holiday dates are missing, and unread letters and posts after a
  failed read. Automations that check these sensors for `none` need to check for `unknown`.
- Devices of children you deselect in the integration options are removed.
- Errors of the integration are translated.
- The problem report reads more modules and the change codes of the timetable.
- The Home Assistant guide covers the options, troubleshooting, known limits and removal.

### Fixed

- The next lesson and the changes in the app overview no longer show lessons on holidays.
- Each school uses its own holidays. A lesson on a holiday no longer fires a timetable change in Home Assistant.
- Each timetable change fires once in Home Assistant.
- The card shows true counts, keeps working when one calendar fails, and shows all-day notices as notes.
- Entities stay when the module list of a school cannot be read.
- The current and next lesson follow the clock between two updates.

## 2610.5.0

### New

- Updates in one click. When the app or the integration is behind, the repair notice in Home Assistant has a button that
  installs the update. A restart notice follows where needed.
- The app shows when a newer version is waiting, with a button to the update.
- A new setup switches on automatic updates for the app. The integration options have a switch for it.

### Changed

- A problem report names a newer app version when one is waiting, and the report page asks to update first.
- The problem report shows the shape of plugin calendars such as the exam plan.
- HACS counts downloads of the integration.

### Fixed

- An app installed again or from another source took a second integration entry. The integration now keeps its entry,
  devices and automations.
- An ignored update notice comes back when the versions change.

## 2610.4.0

### New

- A "Next school day" block for the overview and the dashboard card. It shows the next day with lessons, with the known
  substitutions and cancellations, under "Tomorrow" or the weekday and date.
- The "Today" block of the card can switch to the next school day after the last lesson or from a set time.
- Whiteboards from IServ as a list with title, owner and dates.

### Changed

- Ranzenpost is in the HACS default store. Search for Ranzenpost in HACS to install it.
- New cards start with the blocks Today and Next school day.
- The family view of the card shows the next school day instead of the next calendar day.
- The problem report shows the visible text of each explored page with names masked, and skips the mail rules when
  their port is closed.

### Fixed

- Parallel lessons on the card showed the subject of the first one, for example "G" twice instead of "G" and "GB".
- Normal lessons on the card showed "Datum: ..." instead of the teacher and room.
- Substitutions show on every day of the card, not only today.
- Plugin calendars such as the exam plan are read. 2610.3.0 listed them but did not request them.
- The integration looks up its devices per config entry. Home Assistant drops the old lookup in 2027.8.
- Mail connections require TLS 1.2 or newer.

## 2610.3.0

### New

- Tasks from IServ in their own view: open and past tasks with text, files, feedback and model solutions, read when
  you open a task. Hand in files or text, remove a handed-in file and mark a task done, each after a confirmation.
- News from IServ with full text, files and images. Archive and package news come through the filter, with search.
- IServ email inside Ranzenpost: folders, search, reading, replying, forwarding, drafts, attachments, read receipts,
  tags, sender addresses, recipient and group search, and an event from a mail. Out-of-office note, forwarding,
  filter rules and signatures are edited in the app through IServ's own settings forms.
- Parent-teacher conferences inside the app: teachers, rooms, free slots and your bookings. Book, change and cancel a
  slot after a confirmation. Push messages when booking opens, when a booking is cancelled, three days before and
  shortly before.
- Letters that ask for a choice are answered in Ranzenpost, and a sent answer can be changed.
- Schools that still use IServ's older absence page can report absences with attachments, read the change log,
  export the list and withdraw entries in the app.
- When a school requires two-factor sign-in and the account has none yet, the setup sets it up with you: QR code,
  key and code. Old Ranzenpost entries left in IServ can be removed from the setup.
- School events include every calendar the account sees in IServ, plugin calendars such as an exam plan and the
  account's personal calendar included.
- Task and news blocks on the overview and the card. Home Assistant sensors and triggers for new tasks and news.
- Forums: every forum with its unread posts, a push and a Home Assistant sensor and trigger for new posts, and
  marking everything as read after a confirmation. The forums block is on the overview by default. Forums appear
  only where the account has the module.
- Texts: every text the account sees in IServ, hidden ones too, with filter, tags and search. A push and a Home
  Assistant sensor and trigger for new texts.
- Info screens: the list of info screens the account sees.
- Files: your own files and group folders. Search, open and save files, and upload into a folder after a
  confirmation.
- Contacts: search the school address book and write an email to a person. See mailing lists, import one from a text
  or CSV file, or delete one, each after a confirmation.
- Mail can mark an email as spam, with undo, and move it back with Not spam. Recipients can come from the address
  book or a mailing list.

### Changed

- Ranzenpost no longer sends you to IServ. Everything that opened IServ before now happens in the app.
- Pages the school refuses or does not have are asked for again once a day, after sign-in or when you check the
  modules again. Each page is read once per refresh.
- Disconnecting keeps the school until its Ranzenpost entry in IServ is removed. You can try again or disconnect
  anyway.
- The problem report records the structure of more IServ pages: calendar sources, task and news pages, mail settings,
  forms and the lesson slot numbers. It explores forums, course selection, polls, files, to-do, texts, whiteboards,
  mailing lists, printing, video conferences, info screens and connected services more deeply. It still records no
  content.
- Settings show how many calendars you subscribed to. Notifications have one name in the settings and in their
  sheet. The card editor lists each block once. In English the letters tab is called "Letters".
- The school subscription hint no longer promises "no names".

### Fixed

- The week timetable shows period 0, for example an 08:00 first lesson, as its own row.
- A sick note sent to a slow school is no longer shown as failed, and it is not sent twice.
- A password change interrupted by the connection no longer leaves the old password stored.
- One failed school answer no longer hides a module for a day.
- On the day summer time starts, times between 01:00 and 02:00 are no longer shown an hour late.
- Letters, noticeboard posts and absence answers can no longer carry hidden code into the app. School files download
  as files unless they are images or PDFs. Mail bodies are shown in a closed frame.
- Updated source-map-js in the test tools to close a security alert. The app itself does not use it.
- The app refuses write requests that another website sends to it.

### Note

- Before you go back to an older version, delete the school calendar subscriptions in the settings. Older versions do
  not remove them when you disconnect a school.

## 2610.2.0

### New

- School events from the IServ calendar: their own view in the app, an optional overview block, a Home Assistant
  calendar per school and a card block. They appear once the school's calendar answers. The account's personal
  calendar is left out.
- Accounts without a linked profile work fully. The setup finishes without an error. The app hides timetable and
  absences and shows the holidays on the overview.
- Home Assistant gets sensors for the school's unread letters and noticeboard posts, with matching triggers on the
  school device. `profiles` on the school's connection sensor counts the linked profiles, so 0 shows up without a
  repair.
- The card shows the school's blocks without a linked profile. Cards still set to the today, week or family view show
  the school's letters, noticeboard and holidays instead of "no profiles". The holidays block stays for a school
  without a timetable, as in the app.
- Unread IServ e-mails show on the overview with a link to IServ, and as a sensor on the school device. Ranzenpost
  only reads the count and never opens a mail.
- Calendar subscriptions work without a linked profile, as a school feed with holidays and school events.
  Subscriptions for a profile can add the school events.
- Push messages for new chat messages get a switch in the settings, like the other kinds.
- The problem report reads more of IServ. It follows redirects inside the school, reads a few known module interfaces
  and records how long values are. It still records only structure, never content.

### Fixed

- A timetable page without a child choice no longer leaves the account in a permanent error when the school app
  confirms there is no child.
- A school without the parent letters module no longer logs a warning on every refresh.
- An open sheet no longer slides in a second time when its data arrives.
- When writing to a teacher, the search field keeps what you type while the list of children loads, and new hits
  show again after a teacher was chosen.
- The unread mail count refreshes with a pull to refresh and names the school whenever there are several.
- The phone numbers setting only shows where sick notes can be sent.

### Note

- Before you go back to an older version, delete the school calendar subscriptions in the settings. The older
  version does not remove them when you disconnect a school.

## 2610.1.1

### Fixed

- Updated urllib3 to 2.8.0, which closes three security issues in how HTTP responses and proxies are handled.

## 2610.1.0

### New

- When you create a calendar subscription you choose Local or Internet. Internet also works in Google Calendar and
  Outlook.com, through Home Assistant Cloud or your own external URL. The page shows no addresses, only add, copy and QR.
- Own appointments on Saturday or Sunday appear in the week, which then shows the weekend.
- The start time of an own entry can be typed.

### Fixed

- Marking a messenger chat as read works again. Before, it always failed and the unread count stayed.

## 2609.4.1

### New

- Home Assistant shows a repair when the app or the integration is behind, with the exact update steps. An integration
  that is installed but not loaded yet offers a restart of Home Assistant.
- The app shows under Settings and on the help page which side still needs its update. The problem report names the
  integration version.
- Settings offer an "Open in IServ" link for Klassengeld, which Ranzenpost recognises but does not support. It no longer
  appears in the request to report unknown modules.

### Changed

- Home Assistant texts and the docs say "app" instead of "add-on". A dashboard card older than the integration asks you
  to reload the page.
- Cover lessons show their room next to the cover label in tiles that are big enough, in the app and on the card.
- The problem report names the fields a school uses to mark cover and cancelled lessons.

### Fixed

- When a school does not release the timetable to your account, Ranzenpost says so calmly instead of showing an error,
  and the log no longer fills with warnings.

## 2609.4.0

### New

- Lesson tiles show the subject name, the room and the teacher when the tile has room for them. Tablets and laptops show
  the name and room, wide screens also the teacher, with taller rows. Phones keep the short code. Your own subject names
  from the settings come first. Today's rows name room and teacher. The dashboard card does the same.
- Timetables from the school app mark cover lessons, cancelled lessons and moved lessons when the school releases
  substitutions, and send the usual change notification.
- The card editor sets the order of the blocks with up and down buttons, so no YAML is needed.
- The card's links open the right place in the app: "Open the timetable" the timetable, the letters and pinboard blocks
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

- "Open the timetable", "Show all" and the device link open the app again on Home Assistant versions that call add-ons
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
