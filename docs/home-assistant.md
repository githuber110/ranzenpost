[English](home-assistant.md) | [Deutsch](home-assistant.de.md)

# Home Assistant reference

Every entity the Ranzenpost integration creates, the triggers and conditions for the automation editor, and four automations to copy. Installing the integration is described in the [README](../README.md#3-add-the-integration), the dashboard card in the [README](../README.md#dashboard-card).

## Entities

The integration creates one device per school and one per child. Entity IDs use the first name, for example `sensor.ranzenpost_mia_next_lesson`. When two children at different schools share a first name, the school is added. Entities exist only for the modules your school has.

### Per child

| Entity | What it holds | Attributes |
| --- | --- | --- |
| `calendar.ranzenpost_mia_lessons` | Lessons, with substitutions and cancellations | The next lesson: `summary`, `start`, `end`, `subject`, `subject_code`, `name`, `kind` |
| `calendar.ranzenpost_mia_exams` | Marked exams | The next exam: `summary`, `start`, `end`, `subject`, `subject_code`, `name`, `kind` |
| `calendar.ranzenpost_mia_absences` | Approved absences | The next absence: `summary`, `start`, `end`, `subject`, `subject_code`, `name`, `kind` |
| `calendar.ranzenpost_mia_own_entries` | Own clubs and appointments, while the school's switch on the lesson times page is on. Breaks never | The next entry: `summary`, `start`, `end`, `subject`, `subject_code`, `name`, `kind` |
| `sensor.ranzenpost_mia_current_lesson` | The subject of the lesson running now, `none` outside lessons | `date`, `weekday`, `period`, `subject`, `subject_code`, `teacher`, `room`, `start`, `end`, `substitution`, `cancelled`, `kind`, `before`, `after`, `note`, `minutes_until`, `minutes_left` |
| `sensor.ranzenpost_mia_next_lesson` | The subject of the next lesson, also across the weekend and the holidays | The same fields as the current lesson |
| `sensor.ranzenpost_mia_school_end_today` | When the last lesson ends today, unknown on a free day | `school_day` |
| `sensor.ranzenpost_mia_next_school_day` | When the first lesson of the next school day starts, including today until its first lesson | `date`, `weekday`, `days_until`, `end`, `lessons`, `first_lesson` |
| `sensor.ranzenpost_mia_changes_today` | Number of timetable changes today | `changes`, a list of lessons with the fields above |
| `sensor.ranzenpost_mia_next_exam` | The subject of the next marked exam, `none` without one | `date`, `weekday`, `days_until`, `period`, `subject`, `subject_code`, `name`, `start`, `end`, `teacher`, `room` |
| `sensor.ranzenpost_mia_exams_upcoming` | Number of marked exams in the next 30 days | `exams`, a list with the fields above, and `days` |
| `sensor.ranzenpost_mia_unread_letters` | Number of unread parent letters | `letters`, up to ten with `title`, `sender`, `date`, `child` |
| `sensor.ranzenpost_mia_unread_posts` | Number of unread noticeboard posts | `posts`, up to ten with `title`, `sender`, `date`, `child` |
| `sensor.ranzenpost_mia_open_absences` | Number of absences waiting for a decision | `absences`, each with `kind`, `summary`, `start`, `end`, `status`, `days_until` |
| `sensor.ranzenpost_mia_next_absence` | The date of the next open or upcoming absence, `none` without one | `kind`, `summary`, `start`, `end`, `status`, `days_until` |
| `sensor.ranzenpost_mia_timetable_last_updated` | When the timetable was last updated | `source`: `iserv` for the stamp IServ shows, `app` for the last successful fetch |
| `binary_sensor.ranzenpost_mia_school_day_today` | Whether today is a school day | |
| `binary_sensor.ranzenpost_mia_timetable_changed_today` | Whether today's timetable changed | |
| `event.ranzenpost_mia_timetable_changed` | Fires on a substitution, cancellation, room change or new lesson | `child`, `summary`, `date`, `period` |

### Per school

Each school adds its own device. With several schools, the school's name joins the ID, for example `sensor.ranzenpost_school_riverside_primary_next_holiday`.

| Entity | What it holds | Attributes |
| --- | --- | --- |
| `calendar.ranzenpost_school_holidays` | School holidays and public holidays | The next holiday: `summary`, `start`, `end`, `subject`, `subject_code`, `name`, `kind` |
| `calendar.ranzenpost_school_school_events` | Events from the school calendar, only when the school offers the calendar module | The next event: `summary`, `start`, `end`, `subject`, `subject_code`, `name`, `kind` |
| `sensor.ranzenpost_school_next_holiday` | The name of the next school holidays | `start`, `end`, `days_until` |
| `sensor.ranzenpost_school_next_free_day` | The name of the next day off, school holidays or a public holiday | `start`, `end`, `days_until` |
| `sensor.ranzenpost_school_next_conference` | The date of the next parent-teacher conference | `date`, `title`, `details`, `days_until` |
| `sensor.ranzenpost_school_unread_letters` | Number of unread parent letters of the school, also for an account without a linked profile | `letters`, up to ten with `title`, `sender`, `date`, `child` |
| `sensor.ranzenpost_school_unread_posts` | Number of new noticeboard posts of the school | `posts`, up to ten with `title`, `sender`, `date` |
| `sensor.ranzenpost_school_open_tasks` | Number of open tasks of the account, only when the school offers tasks; past tasks and tasks marked done do not count | `tasks`, up to ten with `title`, `sender` (empty), `date` (due date), `child` (empty) and `id` |
| `sensor.ranzenpost_school_news` | Number of news items IServ lists, only when the school offers news; the archive and the package news do not count | `news`, up to ten with `title`, `sender` (the category), `date`, `child` (empty), `id` and `text` (the start of the news) |
| `sensor.ranzenpost_school_unread_forum_posts` | Number of unread forum posts of the account, only when the school offers forums | `forums`, up to ten forums with unread posts, each with `title`, `sender` (the section), `date` (the last post), `child` (empty), `id` and `text` (the last post) |
| `sensor.ranzenpost_school_texts` | Number of texts the account sees, only when the school offers texts | `texts`, up to ten with `title`, `sender` (the owner), `date` (the change, otherwise the creation), `child` (empty) and `id` |
| `sensor.ranzenpost_school_unread_e_mails` | Unread emails in the IServ mailbox of the account, only when the school offers IServ email; `unknown` when the count could not be read | none |
| `sensor.ranzenpost_school_connection` | `ok`, `error`, `unconfigured`, `unreachable` or `auth_failed` | `last_poll`, `last_success`, `version`, `modules`, `modules_disabled`, `feed_port_open`, `ingress_path`, `profiles` |

### Values and units

A counter reads `0` and an empty list when there is nothing, a text sensor reads `none`, and a timestamp sensor stays `unknown` only while no such moment exists. Times are ISO 8601 with the Europe/Berlin offset, dates are `YYYY-MM-DD`, weekdays are English names such as `monday`. The integration asks the app every 60 seconds and never talks to IServ itself. The calendars also show up in Home Assistant's calendar panel.

- `next_lesson` looks up to 14 days ahead, so on a Saturday it names the first lesson on Monday.
- `kind` is `substitution`, `cancellation`, `room_change`, `new_lesson` or empty. `before` and `after` hold the changed fields.
- `next_school_day` skips a day whose lessons are all cancelled. Today counts until its first lesson has started, and `days_until` is then `0`.
- `next_holiday` reports `days_until` as `0` while the holidays run.
- `details` of `next_conference` holds every cell of the IServ row except the date.
- In `letters`, `child` names the child a letter is addressed to.
- A calendar is `on` while one of its events runs.

The exact JSON shapes behind the entities are in [`custom_components/ranzenpost/contract.json`](../custom_components/ranzenpost/contract.json).

## Triggers and conditions

In the automation editor, pick a child's device and choose a trigger: **Timetable changed**, **Lesson cancelled**, **Substitution**, **New letter**, **New noticeboard post** or **Absence status changed**. A school's device offers **School unreachable**, **School reachable again**, **Login needed**, **New letter**, **New noticeboard post**, **New task**, **New news item**, **New forum post** and **New text**, each only where the school has the module. These four triggers fire for exactly the entries the app pushes for, once each. Their event data carries `id`, for news and forum posts also `text`. Two conditions check a child: **Is a school day** and **A lesson is running**. No YAML needed.

## Automation recipes

The sensors carry enough for the rest. Four ideas to copy:

### Wake up one hour before the first lesson

```yaml
triggers:
  - trigger: time
    at:
      entity_id: sensor.ranzenpost_mia_next_school_day
      offset: "-01:00:00"
actions:
  - action: light.turn_on
    target:
      area_id: kids_room
    data:
      brightness_pct: 60
```


### Morning briefing on the kitchen speaker

```yaml
triggers:
  - trigger: time
    at: "07:00:00"
conditions:
  - condition: template
    value_template: "{{ states('sensor.ranzenpost_mia_school_end_today') not in ['unknown', 'unavailable'] }}"
actions:
  - action: tts.speak
    target:
      entity_id: tts.home_assistant_cloud
    data:
      media_player_entity_id: media_player.kitchen
      message: >
        Mia starts with {{ states('sensor.ranzenpost_mia_next_lesson') }}
        and school ends at {{ as_timestamp(states('sensor.ranzenpost_mia_school_end_today')) | timestamp_custom('%H:%M') }}.
```


### Push the change when the timetable moves

```yaml
triggers:
  - trigger: state
    entity_id: event.ranzenpost_mia_timetable_changed
    not_from:
      - unavailable
      - unknown
actions:
  - action: notify.mobile_app_my_phone
    data:
      title: Timetable change
      message: "{{ trigger.to_state.attributes.summary }}"
```


### Remind the evening before an exam

```yaml
triggers:
  - trigger: time
    at: "18:00:00"
conditions:
  - condition: template
    value_template: "{{ state_attr('sensor.ranzenpost_mia_next_exam', 'days_until') == 1 }}"
actions:
  - action: notify.mobile_app_my_phone
    data:
      title: Exam tomorrow
      message: "{{ states('sensor.ranzenpost_mia_next_exam') }}: {{ state_attr('sensor.ranzenpost_mia_next_exam', 'name') }}"
```
