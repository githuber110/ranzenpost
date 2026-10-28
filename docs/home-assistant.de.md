[English](home-assistant.md) | [Deutsch](home-assistant.de.md)

# Home-Assistant-Referenz

Jede Entität, die die Ranzenpost-Integration anlegt, die Auslöser und Bedingungen für den Automationseditor und vier Automationen zum Übernehmen. Die Installation der Integration steht in der [README](../README.de.md#3-integration-hinzufügen), die Dashboard-Karte ebenfalls in der [README](../README.de.md#dashboard-karte).

## Wofür Familien es nutzen

- Eine Morgenansage auf dem Küchenlautsprecher mit erster Stunde, Ausfällen und Arbeiten.
- Ein Wecker, der sich nach der ersten Stunde richtet und an freien Tagen und in den Ferien still bleibt.
- Eine Push-Nachricht, wenn sich der Stundenplan ändert oder ein neuer Elternbrief kommt.
- Eine Dashboard-Karte an der Haustür, die heute zeigt und nach der Schule den nächsten Schultag.
- Eine Erinnerung am Vorabend einer Arbeit oder eines Elternsprechtags.

## Entitäten

Die Integration legt ein Gerät pro Schule und eines pro Kind an. Entitäts-IDs tragen den Vornamen, zum Beispiel `sensor.ranzenpost_mia_next_lesson`. Teilen sich zwei Kinder an verschiedenen Schulen einen Vornamen, kommt die Schule dazu. Entitäten gibt es nur für die Module, die deine Schule hat.

### Pro Kind

| Entität | Was sie enthält | Attribute |
| --- | --- | --- |
| `calendar.ranzenpost_mia_lessons` | Stunden, mit Vertretungen und Ausfällen | Die nächste Stunde: `summary`, `start`, `end`, `subject`, `subject_code`, `name`, `kind` |
| `calendar.ranzenpost_mia_exams` | Markierte Arbeiten | Die nächste Arbeit: `summary`, `start`, `end`, `subject`, `subject_code`, `name`, `kind` |
| `calendar.ranzenpost_mia_absences` | Genehmigte Abwesenheiten | Die nächste Abwesenheit: `summary`, `start`, `end`, `subject`, `subject_code`, `name`, `kind` |
| `calendar.ranzenpost_mia_own_entries` | Eigene AGs und Termine, solange der Schalter der Schule auf der Stundenzeiten-Seite an ist. Pausen nie | Der nächste Eintrag: `summary`, `start`, `end`, `subject`, `subject_code`, `name`, `kind` |
| `sensor.ranzenpost_mia_current_lesson` | Das Fach der gerade laufenden Stunde, `none` außerhalb der Stunden | `date`, `weekday`, `period`, `subject`, `subject_code`, `teacher`, `room`, `start`, `end`, `substitution`, `cancelled`, `kind`, `moved`, `before`, `after`, `note`, `minutes_until`, `minutes_left` |
| `sensor.ranzenpost_mia_next_lesson` | Das Fach der nächsten Stunde, auch über Wochenende und Ferien hinweg | Dieselben Felder wie die aktuelle Stunde |
| `sensor.ranzenpost_mia_school_end_today` | Wann die letzte Stunde heute endet, an einem freien Tag unknown | `school_day` |
| `sensor.ranzenpost_mia_next_school_day` | Wann die erste Stunde des nächsten Schultags beginnt, heute noch bis zur ersten Stunde | `date`, `weekday`, `days_until`, `end`, `lessons`, `first_lesson` |
| `sensor.ranzenpost_mia_changes_today` | Zahl der Stundenplanänderungen heute | `changes`, eine Liste von Stunden mit den Feldern oben |
| `sensor.ranzenpost_mia_next_exam` | Das Fach der nächsten markierten Arbeit, `none` ohne eine | `date`, `weekday`, `days_until`, `period`, `subject`, `subject_code`, `name`, `start`, `end`, `teacher`, `room` |
| `sensor.ranzenpost_mia_exams_upcoming` | Zahl der markierten Arbeiten in den nächsten 30 Tagen | `exams`, eine Liste mit den Feldern oben, und `days` |
| `sensor.ranzenpost_mia_unread_letters` | Zahl der ungelesenen Elternbriefe | `letters`, bis zu zehn mit `title`, `sender`, `date`, `child` |
| `sensor.ranzenpost_mia_unread_posts` | Zahl der ungelesenen Pinnwandbeiträge | `posts`, bis zu zehn mit `title`, `sender`, `date`, `child` |
| `sensor.ranzenpost_mia_open_absences` | Zahl der Abwesenheiten, die auf eine Entscheidung warten | `absences`, je mit `kind`, `summary`, `start`, `end`, `status`, `days_until` |
| `sensor.ranzenpost_mia_next_absence` | Das Datum der nächsten offenen oder anstehenden Abwesenheit, `unknown` ohne eine | `kind`, `summary`, `start`, `end`, `status`, `days_until` |
| `sensor.ranzenpost_mia_timetable_last_updated` | Wann der Stundenplan zuletzt aktualisiert wurde | `source`: `iserv` für den Stempel, den IServ zeigt, `app` für den letzten erfolgreichen Abruf |
| `binary_sensor.ranzenpost_mia_school_day_today` | Ob heute ein Schultag ist | |
| `binary_sensor.ranzenpost_mia_timetable_changed_today` | Ob sich der heutige Stundenplan geändert hat | |
| `event.ranzenpost_mia_timetable_changed` | Feuert bei Vertretung, Ausfall, Raumwechsel oder neuer Stunde | `child`, `summary`, `date`, `period` |

### Pro Schule

Jede Schule bringt ein eigenes Gerät mit. Bei mehreren Schulen kommt der Name der Schule in die ID, zum Beispiel `sensor.ranzenpost_school_riverside_primary_next_holiday`.

| Entität | Was sie enthält | Attribute |
| --- | --- | --- |
| `calendar.ranzenpost_school_holidays` | Schulferien und Feiertage | Die nächsten Ferien: `summary`, `start`, `end`, `subject`, `subject_code`, `name`, `kind` |
| `calendar.ranzenpost_school_school_events` | Termine aus dem Schulkalender, nur wenn die Schule das Kalendermodul anbietet | Der nächste Termin: `summary`, `start`, `end`, `subject`, `subject_code`, `name`, `kind` |
| `sensor.ranzenpost_school_next_holiday` | Der Name der nächsten Schulferien | `start`, `end`, `days_until` |
| `sensor.ranzenpost_school_next_free_day` | Der Name des nächsten freien Tags, Schulferien oder Feiertag | `start`, `end`, `days_until` |
| `sensor.ranzenpost_school_next_conference` | Das Datum des nächsten Elternsprechtags | `date`, `title`, `details`, `days_until` |
| `sensor.ranzenpost_school_unread_letters` | Zahl der ungelesenen Elternbriefe der Schule, auch für ein Konto ohne verknüpftes Profil | `letters`, bis zu zehn mit `title`, `sender`, `date`, `child` |
| `sensor.ranzenpost_school_unread_posts` | Zahl der neuen Pinnwandbeiträge der Schule | `posts`, bis zu zehn mit `title`, `sender`, `date` |
| `sensor.ranzenpost_school_open_tasks` | Zahl der offenen Aufgaben des Kontos, nur wenn die Schule Aufgaben anbietet; vergangene und erledigte Aufgaben zählen nicht | `tasks`, bis zu zehn mit `title`, `sender` (leer), `date` (Abgabe), `child` (leer) und `id` |
| `sensor.ranzenpost_school_news` | Zahl der News, die IServ listet, nur wenn die Schule News anbietet; Archiv und Paketnews zählen nicht | `news`, bis zu zehn mit `title`, `sender` (die Kategorie), `date`, `child` (leer), `id` und `text` (der Anfang der News) |
| `sensor.ranzenpost_school_unread_forum_posts` | Zahl der ungelesenen Forenbeiträge des Kontos, nur wenn die Schule Foren anbietet | `forums`, bis zu zehn Foren mit ungelesenen Beiträgen, jeweils mit `title`, `sender` (der Bereich), `date` (der letzte Beitrag), `child` (leer), `id` und `text` (der letzte Beitrag) |
| `sensor.ranzenpost_school_texts` | Zahl der Texte, die das Konto sieht, nur wenn die Schule Texte anbietet | `texts`, bis zu zehn mit `title`, `sender` (der Besitzer), `date` (die Änderung, sonst die Erstellung), `child` (leer) und `id` |
| `sensor.ranzenpost_school_unread_e_mails` | Ungelesene E-Mails im IServ-Postfach des Kontos, nur wenn die Schule IServ-E-Mail anbietet; `unknown`, wenn die Zahl nicht lesbar war | keine |
| `sensor.ranzenpost_school_connection` | `ok`, `error`, `unconfigured`, `unreachable` oder `auth_failed` | `last_poll`, `last_success`, `version`, `modules`, `modules_disabled`, `feed_port_open`, `ingress_path`, `profiles` |

### Werte und Einheiten

Ein Zähler zeigt `0` und eine leere Liste, wenn nichts da ist, ein Textsensor zeigt `none`, und ein Zeitstempel-Sensor bleibt nur `unknown`, solange es diesen Moment nicht gibt. Zeiten sind ISO 8601 mit dem Offset von Europe/Berlin, Daten `YYYY-MM-DD`, Wochentage englische Namen wie `monday`. Die Integration fragt die App alle 60 Sekunden und spricht nie selbst mit IServ. Die Kalender erscheinen auch im Kalender von Home Assistant.

- `next_lesson` schaut bis zu 14 Tage voraus, an einem Samstag nennt sie also die erste Stunde am Montag.
- `kind` ist `substitution`, `cancellation`, `room_change`, `new_lesson` oder leer. `before` und `after` enthalten die geänderten Felder.
- `moved` ist `away` für eine Stunde, die woandershin verlegt wird, `here` für ihren neuen Platz und sonst leer. `kind` bleibt wie bisher, bestehende Automationen laufen also weiter.
- `next_school_day` überspringt einen Tag, dessen Stunden alle ausfallen. Heute zählt, bis die erste Stunde begonnen hat, und `days_until` ist dann `0`.
- `next_holiday` meldet `days_until` als `0`, solange die Ferien laufen.
- `details` von `next_conference` enthält jede Zelle der IServ-Zeile außer dem Datum.
- In `letters` nennt `child` das Kind, an das ein Brief gerichtet ist.
- Ein Kalender steht auf `on`, solange eines seiner Ereignisse läuft.

Die genauen JSON-Formen hinter den Entitäten stehen in [`custom_components/ranzenpost/contract.json`](../custom_components/ranzenpost/contract.json).

## Auslöser und Bedingungen

Wähle im Automationseditor das Gerät eines Kindes und dann einen Auslöser: **Stundenplan geändert**, **Stunde fällt aus**, **Vertretung**, **Neuer Elternbrief**, **Neuer Pinnwandbeitrag** oder **Status einer Abwesenheit geändert**. Das Gerät einer Schule bietet **Schule nicht erreichbar**, **Schule wieder erreichbar**, **Anmeldung erforderlich**, **Neuer Elternbrief**, **Neuer Pinnwandbeitrag**, **Neue Aufgabe**, **Neue News**, **Neuer Forenbeitrag** und **Neuer Text**, jeweils nur, wo die Schule das Modul hat. Diese vier Auslöser feuern genau für die Einträge, für die auch die App eine Nachricht schickt, jeweils einmal. Ihre Ereignisdaten enthalten `id`, bei News und Forenbeiträgen auch `text`. Zwei Bedingungen prüfen ein Kind: **Ist ein Schultag** und **Eine Stunde läuft**. Ganz ohne YAML.

## Automationen zum Übernehmen

Für alles Weitere tragen die Sensoren genug. Vier Ideen zum Übernehmen:

### Eine Stunde vor Unterrichtsbeginn wecken

```yaml
triggers:
  - trigger: time
    at:
      entity_id: sensor.ranzenpost_mia_next_school_day
      offset: "-01:00:00"
actions:
  - action: light.turn_on
    target:
      area_id: kinderzimmer
    data:
      brightness_pct: 60
```


### Morgenansage auf dem Küchenlautsprecher

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
      media_player_entity_id: media_player.kueche
      message: >
        Mia beginnt mit {{ states('sensor.ranzenpost_mia_next_lesson') }}
        und die Schule endet um {{ as_timestamp(states('sensor.ranzenpost_mia_school_end_today')) | timestamp_custom('%H:%M') }} Uhr.
```


### Die Änderung pushen, wenn sich der Stundenplan bewegt

```yaml
triggers:
  - trigger: state
    entity_id: event.ranzenpost_mia_timetable_changed
    not_from:
      - unavailable
      - unknown
actions:
  - action: notify.mobile_app_mein_handy
    data:
      title: Stundenplanänderung
      message: "{{ trigger.to_state.attributes.summary }}"
```


### Am Vorabend an eine Arbeit erinnern

```yaml
triggers:
  - trigger: time
    at: "18:00:00"
conditions:
  - condition: template
    value_template: "{{ state_attr('sensor.ranzenpost_mia_next_exam', 'days_until') == 1 }}"
actions:
  - action: notify.mobile_app_mein_handy
    data:
      title: Morgen ist eine Arbeit
      message: "{{ states('sensor.ranzenpost_mia_next_exam') }}: {{ state_attr('sensor.ranzenpost_mia_next_exam', 'name') }}"
```

## Optionen

**Einstellungen, Geräte & Dienste, Ranzenpost, Konfigurieren** enthält drei Einstellungen.

| Option | Vorgabe | Wirkung |
| --- | --- | --- |
| Abfrageintervall | 60 Sekunden | Wie oft die Integration die App fragt. Zwischen 30 und 3600 Sekunden. Die App fragt IServ nach eigenem Takt. |
| Profile | alle | Welche Kinder Geräte und Entitäten bekommen. Leer lassen für alle. |
| App automatisch aktualisieren | an, wenn die Integration die App installiert hat | Home Assistant installiert neue Versionen der Ranzenpost-App selbst. Nur mit Supervisor sichtbar. |

Um Host, Port oder Token zu ändern, ohne etwas zu löschen, öffne die drei Punkte am Ranzenpost-Eintrag und wähle **Neu konfigurieren**.

## Fehlerbehebung

| Was du siehst | Was zu tun ist |
| --- | --- |
| Alle Ranzenpost-Entitäten sind nicht verfügbar | Die App ist gestoppt oder nicht erreichbar. Starte sie unter Einstellungen, Apps. Das Protokoll der Integration nennt den Grund. Schalte auf der Seite der App **Watchdog** ein, dann startet Home Assistant eine hängende App selbst neu. |
| Home Assistant will eine erneute Anmeldung | Der Token wurde in der App neu erzeugt. Kopiere den neuen aus der App unter Einstellungen, Home Assistant. |
| Die App läuft auf einem neuen Host oder Port | Wähle **Neu konfigurieren** am Ranzenpost-Eintrag. Mit Supervisor passiert das von selbst. |
| Ein Sensor zeigt Unbekannt | Die App hat noch keinen sicheren Wert, zum Beispiel fehlen Ferientermine oder die Schule hat nicht geantwortet. Die App zeigt, welcher Bereich betroffen ist. |
| Eine Reparatur bittet um Anmeldung | Öffne Ranzenpost in der Seitenleiste und melde dich bei dieser Schule neu an. Die Reparatur verschwindet von selbst. |
| Nichts davon hilft | Speichere in der App unter Einstellungen, Hilfe, Problem melden einen Bericht und hänge ihn an ein Issue. |

## Bekannte Grenzen

- Die Integration spricht nur mit der App. Solange die App gestoppt ist, sind die Entitäten nicht verfügbar.
- Entitäten gibt es nur für die Module, die deine Schule deinem Konto anbietet.
- Ferientermine brauchen das Bundesland in den App-Einstellungen. Ohne es werden Stunden in den Ferien nicht ausgeblendet.
- Meldet IServ ein neues Kind oder eine neue Schule, lädt die Integration einmal neu und ihre Entitäten sind kurz nicht verfügbar.
- Eine Verlegung erscheint nur dann als Verlegung, wenn das IServ der Schule sie markiert. Sonst erscheint sie als Entfall und Vertretung.

## Ranzenpost entfernen

1. Entferne die Ranzenpost-Karten aus deinen Dashboards.
2. Öffne unter Einstellungen, Geräte & Dienste den Eintrag Ranzenpost, dann die drei Punkte und wähle **Löschen**. Damit verschwinden Geräte und Entitäten.
3. Öffne in HACS Ranzenpost und wähle **Entfernen**.
4. Öffne in der App unter Einstellungen jede Schule und wähle **Diese Schule trennen**. Das entfernt den Sicherheits-Token der App aus IServ.
5. Öffne unter Einstellungen, Apps die App Ranzenpost und wähle **Deinstallieren**. Ihre Daten werden mit gelöscht.
