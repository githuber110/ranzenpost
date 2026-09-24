[English](README.md) | [Deutsch](README.de.md)

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.svg">
    <img src="assets/banner-light.svg" width="1280" height="400" alt="Ranzenpost. Deine IServ-Schule in Home Assistant. Stundenplan, Elternbriefe, Pinnwand, Abwesenheiten.">
  </picture>
</p>

<p align="center"><b>Der Schultag deiner Kinder in Home Assistant.</b><br>Stundenplan, Vertretungen, Elternbriefe, Pinnwand und Krankmeldungen aus dem <a href="https://iserv.de">IServ</a> deiner Schule, als App in der Seitenleiste, als Dashboard-Karte und als Entitäten für deine Automationen.</p>

<p align="center">
  <a href="https://github.com/githuber110/ranzenpost/actions/workflows/build.yml"><img src="https://github.com/githuber110/ranzenpost/actions/workflows/build.yml/badge.svg" alt="Build"></a>
  <a href="https://github.com/githuber110/ranzenpost/releases"><img src="https://img.shields.io/github/v/release/githuber110/ranzenpost?label=release" alt="Release"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2025.6%2B-41BDF5.svg" alt="Home Assistant 2025.6 oder neuer"></a>
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-custom-41BDF5.svg" alt="HACS Custom Repository"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT-Lizenz"></a>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/hero-dark.png">
    <img src="docs/screenshots/hero.png" width="900" alt="Die Ranzenpost-App auf einem Handy mit einer bunten Schulwoche, einer Pausenlinie und einer Schach-AG, daneben die Dashboard-Karte mit den heutigen Stunden zweier Kinder, ungelesenen Briefen und den nächsten Ferien">
  </picture>
</p>

<p align="center"><sub>Alle Screenshots stammen vom Test-Fixture-Server. Kinder, Lehrkräfte, Schulen und Briefe sind erfunden.</sub></p>

<table>
  <tr>
    <td width="33%" valign="top"><b>Eine Karte für jedes Dashboard</b><br>Heute, die nächste Stunde, die Woche, Briefe, Ferien und mehr. Bausteine, Größe und Kinder wählst du im visuellen Editor.</td>
    <td width="33%" valign="top"><b>Jedes Kind ist ein Gerät</b><br>Kalender, Sensoren und ein Ereignis je Kind: die nächste Stunde, das Schulende, die nächste Arbeit, ungelesene Briefe, offene Abwesenheiten.</td>
    <td width="33%" valign="top"><b>Automationen ohne YAML</b><br>Geräte-Auslöser wie „Stunde fällt aus“ oder „Neuer Elternbrief“ und Bedingungen wie „Ist ein Schultag“, direkt im Automationseditor.</td>
  </tr>
  <tr>
    <td valign="top"><b>Krankmeldung in wenigen Schritten</b><br>Melde eine Abwesenheit so, wie deine Schule es will, mit einem Prüfschritt, bevor etwas rausgeht.</td>
    <td valign="top"><b>Mehrere Schulen, eine App</b><br>Zwei Kinder an zwei Schulen oder zwei Konten. Ein Posteingang, eine Übersicht, jede Schule mit eigener Anmeldung.</td>
    <td valign="top"><b>Bleibt zu Hause</b><br>Läuft auf deinem Home Assistant. Keine Cloud, kein Konto, kein Server dazwischen. Zugangsdaten liegen verschlüsselt.</td>
  </tr>
</table>

> [!NOTE]
> Ranzenpost ist ein Hobbyprojekt eines Elternteils und gehört nicht zur IServ GmbH. Es entstand mit einem Elternkonto an einer Schule und liest die weiter unten genannten IServ-Module. Fehlt ein Modul deiner Schule, öffnet die Einstellungsseite dafür ein vorausgefülltes Issue.

## Installation

Du brauchst beide Teile. Das Add-on meldet sich bei IServ an und zeigt die App in der Seitenleiste. Die Integration macht aus denselben Daten Entitäten und die Dashboard-Karte.

### 1. Repository hinzufügen

[![Das Ranzenpost-Repository zu deinem Home Assistant hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fgithuber110%2Franzenpost)

Home Assistant öffnet sich und fragt, ob du das Repository hinzufügen willst.

### 2. Add-on installieren und Einrichtung durchlaufen

**Ranzenpost (IServ)** erscheint jetzt im Add-on-Store. Öffne es, klicke **Installieren**, dann **Starten**. Öffne **Ranzenpost** in der Seitenleiste. Die Einrichtung fragt nach der Adresse deiner Schule, deinem Elternlogin und, falls deine Schule das nutzt, nach einem Code aus der Authenticator-App, die du schon hast. Dein Authenticator funktioniert weiter. Dann wählst du deine Kinder. Fertig.

### 3. Integration hinzufügen

[![Die Ranzenpost-Integration über HACS hinzufügen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=githuber110&repository=ranzenpost&category=integration)

Installiere **Ranzenpost** in HACS und starte Home Assistant neu. Dann **Einstellungen, Geräte & Dienste, Integration hinzufügen** und nach **Ranzenpost** suchen. Das laufende Add-on wird von selbst gefunden. Fängst du mit der Integration an, bietet sie an, das Add-on für dich zu installieren.

### Voraussetzungen

- Home Assistant 2025.6 oder neuer, als Home Assistant OS oder Supervised. Der Add-on-Store braucht den Supervisor.
- Ein Rechner mit `amd64` oder `aarch64`, zum Beispiel ein Raspberry Pi 4 oder 5, ein Home Assistant Green oder Yellow oder ein x86-Rechner.
- Ein IServ-Elternkonto an einer Schule, die die Elternmodule eingeschaltet hat.
- Ranzenpost wurde mit Zwei-Faktor-Anmeldung gebaut und getestet. Die Anmeldung ohne Zwei-Faktor ist eingebaut, an einer echten Schule aber noch nicht bestätigt.
- HACS für die Integration.

<details>
<summary>Von Hand installieren, aktualisieren, Home Assistant ohne Supervisor</summary>

**Add-on von Hand:** **Einstellungen, Add-ons, Add-on-Store**, das Menü oben rechts, **Repositories**, `https://github.com/githuber110/ranzenpost` einfügen.

**Integration von Hand:** **HACS**, das Menü oben rechts, **Benutzerdefinierte Repositories**, `https://github.com/githuber110/ranzenpost` einfügen, **Integration** wählen.

**Ohne Supervisor:** Die Integration fragt nach Host, Port und Token des Add-ons. Das Token steht in der App unter **Einstellungen, Home Assistant**, mit einem Kopierknopf.

**Aktualisieren:** Das Add-on aktualisierst du unter **Einstellungen, Add-ons, Ranzenpost (IServ)**, die Integration in HACS. Installiere Add-on und Integration aus demselben Release, starte dann Home Assistant neu und lade die Seite neu. Ein Reparaturhinweis meldet, wenn einer der beiden ein Release zurückliegt. Einstellungen und die Verbindung zur Schule bleiben bei einem Update erhalten.

Die Dokumentation in Home Assistant ist [`iserv_connector/DOCS.md`](iserv_connector/DOCS.md).

</details>

## Home Assistant

### Dashboard-Karte

Die Integration registriert `custom:ranzenpost-card`. Füge sie über die Kartenauswahl hinzu und richte sie im visuellen Editor ein: Titel, Kinder, Bausteine und eine Größe je Baustein. Die Karte folgt Sprache und Design des Dashboards. Sie besteht aus denselben Bausteinen wie die Übersicht der App: `today`, `next_lesson`, `week`, `changes`, `letters`, `noticeboard`, `absences`, `conferences` und `holidays`. Angeboten werden nur Bausteine der Module, die deine Schule hat. Ein Baustein ohne Inhalt wird nicht gezeichnet, und jeder Baustein öffnet mit „Alle ansehen“ die App. Bei mehreren Kindern stehen die Tagesbausteine nebeneinander und die Familienbausteine einmal.

```yaml
type: custom:ranzenpost-card
title: Schule
blocks:
  - key: today
    size: compact
  - letters
  - holidays
children:
  - mia
  - tom
```

<details>
<summary>Weitere Kartenbeispiele</summary>

Ein Wandtablet im Flur, ein Kind, die Woche auf einen Blick:

```yaml
type: custom:ranzenpost-card
blocks:
  - next_lesson
  - key: week
    size: compact
children:
  - mia
```

Ohne Tagesbausteine, für ein Handy-Dashboard:

```yaml
type: custom:ranzenpost-card
blocks:
  - changes
  - letters
  - absences
  - conferences
```

`children` nimmt Vornamen, Vornamen mit der Schule in Klammern oder die Schlüssel der Kinder aus dem Add-on. Lässt du es weg, zeigt die Karte alle Kinder. Jeder Baustein ist ein Schlüssel oder ein Schlüssel mit `size`, `compact` oder `normal`. Die älteren Schlüssel `view` und `child` funktionieren weiter.

</details>

### Was jedes Kind mitbringt

Die Integration legt ein Gerät pro Schule und eines pro Kind an. Entitäts-IDs tragen den Vornamen, zum Beispiel `sensor.ranzenpost_mia_next_lesson`. Teilen sich zwei Kinder an verschiedenen Schulen einen Vornamen, kommt die Schule dazu. Entitäten gibt es nur für die Module, die deine Schule hat.

| Entität | Was sie enthält | Attribute |
| --- | --- | --- |
| `calendar.ranzenpost_mia_lessons` | Stunden, mit Vertretungen und Ausfällen | Die nächste Stunde: `summary`, `start`, `end`, `subject`, `subject_code` |
| `calendar.ranzenpost_mia_exams` | Markierte Arbeiten | Die nächste Arbeit: `summary`, `start`, `end`, `subject`, `subject_code`, `name` |
| `calendar.ranzenpost_mia_absences` | Genehmigte Abwesenheiten | Die nächste Abwesenheit: `summary`, `start`, `end`, `kind` |
| `calendar.ranzenpost_mia_own_entries` | Eigene AGs und Termine, solange der Schalter der Schule auf der Stundenzeiten-Seite an ist. Pausen nie | Der nächste Eintrag: `summary`, `start`, `end`, `kind` |
| `sensor.ranzenpost_mia_current_lesson` | Das Fach der gerade laufenden Stunde, `none` außerhalb der Stunden | `date`, `weekday`, `period`, `subject`, `subject_code`, `teacher`, `room`, `start`, `end`, `substitution`, `cancelled`, `kind`, `before`, `after`, `note`, `minutes_until`, `minutes_left` |
| `sensor.ranzenpost_mia_next_lesson` | Das Fach der nächsten Stunde, auch über Wochenende und Ferien hinweg | Dieselben Felder wie die aktuelle Stunde |
| `sensor.ranzenpost_mia_school_end_today` | Wann die letzte Stunde heute endet, an einem freien Tag unknown | `school_day` |
| `sensor.ranzenpost_mia_next_school_day` | Wann die erste Stunde des nächsten Schultags beginnt | `date`, `weekday`, `days_until`, `end`, `lessons`, `first_lesson` |
| `sensor.ranzenpost_mia_changes_today` | Zahl der Stundenplanänderungen heute | `changes`, eine Liste von Stunden mit den Feldern oben |
| `sensor.ranzenpost_mia_next_exam` | Das Fach der nächsten markierten Arbeit, `none` ohne eine | `date`, `weekday`, `days_until`, `period`, `subject`, `subject_code`, `name`, `start`, `end`, `teacher`, `room` |
| `sensor.ranzenpost_mia_exams_upcoming` | Zahl der markierten Arbeiten in den nächsten 30 Tagen | `exams`, eine Liste mit den Feldern oben, und `days` |
| `sensor.ranzenpost_mia_unread_letters` | Zahl der ungelesenen Elternbriefe | `letters`, bis zu zehn mit `title`, `sender`, `date`, `child` |
| `sensor.ranzenpost_mia_unread_posts` | Zahl der ungelesenen Pinnwandbeiträge | `posts`, bis zu zehn mit `title`, `sender`, `date`, `child` |
| `sensor.ranzenpost_mia_open_absences` | Zahl der Abwesenheiten, die auf eine Entscheidung warten | `absences`, je mit `kind`, `summary`, `start`, `end`, `status`, `days_until` |
| `sensor.ranzenpost_mia_next_absence` | Das Datum der nächsten offenen oder anstehenden Abwesenheit, `none` ohne eine | `kind`, `summary`, `start`, `end`, `status`, `days_until` |
| `sensor.ranzenpost_mia_timetable_last_updated` | Wann der Stundenplan zuletzt aktualisiert wurde | `source`: `iserv` für den Stempel, den IServ zeigt, `app` für den letzten erfolgreichen Abruf |
| `binary_sensor.ranzenpost_mia_school_day_today` | Ob heute ein Schultag ist | |
| `binary_sensor.ranzenpost_mia_timetable_changed_today` | Ob sich der heutige Stundenplan geändert hat | |
| `event.ranzenpost_mia_timetable_changed` | Feuert bei Vertretung, Ausfall, Raumwechsel oder neuer Stunde | `child`, `summary`, `date`, `period` |

Jede Schule bringt ein eigenes Gerät mit. Bei mehreren Schulen kommt der Name der Schule in die ID, zum Beispiel `sensor.ranzenpost_school_riverside_primary_next_holiday`.

| Entität | Was sie enthält | Attribute |
| --- | --- | --- |
| `calendar.ranzenpost_school_holidays` | Schulferien und Feiertage | Die nächsten Ferien: `summary`, `start`, `end` |
| `sensor.ranzenpost_school_next_holiday` | Der Name der nächsten Ferien | `start`, `end`, `days_until` |
| `sensor.ranzenpost_school_next_conference` | Das Datum des nächsten Elternsprechtags | `date`, `title`, `details`, `days_until` |
| `sensor.ranzenpost_school_connection` | `ok`, `error`, `unconfigured`, `unreachable` oder `auth_failed` | `last_poll`, `last_success`, `version`, `modules`, `modules_disabled`, `feed_port_open`, `ingress_path` |

Ein Zähler zeigt `0` und eine leere Liste, wenn nichts da ist, ein Textsensor zeigt `none`, und ein Zeitstempel-Sensor bleibt nur `unknown`, solange es diesen Moment nicht gibt. Zeiten sind ISO 8601 in der Zeitzone der Schule, Daten `YYYY-MM-DD`, Wochentage englische Namen wie `monday`. Die Integration fragt das Add-on alle 60 Sekunden und spricht nie selbst mit IServ. Die Kalender erscheinen auch im Kalender von Home Assistant.

### Automationen

Wähle im Automationseditor das Gerät eines Kindes und dann einen Auslöser: **Stundenplan geändert**, **Stunde fällt aus**, **Vertretung**, **Neuer Elternbrief**, **Neuer Pinnwandbeitrag** oder **Status einer Abwesenheit geändert**. Das Gerät einer Schule bietet **Schule nicht erreichbar**, **Schule wieder erreichbar** und **Anmeldung erforderlich**. Zwei Bedingungen prüfen ein Kind: **Ist ein Schultag** und **Eine Stunde läuft**. Ganz ohne YAML.

Für alles Weitere tragen die Sensoren genug. Vier Ideen zum Übernehmen:

<details>
<summary>Das Kinderzimmer nur an Schultagen wecken</summary>

```yaml
triggers:
  - trigger: time
    at: "06:30:00"
conditions:
  - condition: state
    entity_id: binary_sensor.ranzenpost_mia_school_day_today
    state: "on"
actions:
  - action: light.turn_on
    target:
      area_id: kinderzimmer
    data:
      brightness_pct: 60
```

</details>

<details>
<summary>Morgenansage auf dem Küchenlautsprecher</summary>

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

</details>

<details>
<summary>Die Änderung pushen, wenn sich der Stundenplan bewegt</summary>

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

</details>

<details>
<summary>Am Vorabend an eine Arbeit erinnern</summary>

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

</details>

### Push-Nachrichten und Reparaturen

Das Add-on schickt für jede Stundenplanänderung, jeden neuen Brief, jeden neuen Beitrag und jeden neuen Sprechtag eine Nachricht an die Notify-Dienste, die du auswählst, zum Beispiel die Home Assistant App auf deinem Handy. Jedes Ziel hat einen Testknopf, und die Texte gibt es in allen sechs Sprachen. Braucht die Anmeldung bei einer Schule dich, zeigt Home Assistant einen Reparaturhinweis mit dem Namen der Schule und dem nächsten Schritt. Er verschwindet von selbst, sobald die Anmeldung wieder klappt.

## Die App

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/overview-today-dark.png">
    <img src="docs/screenshots/overview-today.png" width="250" alt="Die Übersicht auf einem Handy: die heutigen Stunden eines Kindes, die laufende Stunde markiert, eine Vertretung und ein Ausfall">
  </picture>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/two-schools-post-dark.png">
    <img src="docs/screenshots/two-schools-post.png" width="250" alt="Der Post-Reiter mit Briefen aus zwei Schulen, einem Schul-Chip an jeder Zeile, einer Filterzeile und einem Suchfeld">
  </picture>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/absence-wizard-review-dark.png">
    <img src="docs/screenshots/absence-wizard-review.png" width="250" alt="Der letzte Schritt der Krankmeldung: Kind, Art, Zeitraum und Kommentar stehen noch einmal über dem Senden-Knopf">
  </picture>
</p>

<p align="center"><b>Heute</b> öffnet auf dem aktuellen Tag und markiert die laufende Stunde. <b>Post</b> führt die Briefe beider Schulen zusammen. <b>Eine Krankmeldung</b> braucht wenige Schritte, und der letzte Schritt zeigt alles noch einmal, bevor etwas rausgeht.</p>

### Stundenplan

Die Woche je Kind, Vertretungen und Ausfälle markiert, nie weggelassen. Tippe eine Stunde an, um eine Arbeit zu markieren. Jede Schule hat eine Seite für Stundenzeiten: Jede Stunde bekommt Beginn und Dauer, aus IServ oder von Hand. Eigene Pausen, AGs und Termine wiederholen sich täglich, wöchentlich oder alle paar Wochen bis zu den Sommerferien, für ein Kind oder alle. Stunden gehen vor: Ein Eintrag, den eine Stunde überdeckt, wird gekürzt, nie gelöscht. Fächer bekommen eine von 24 Farben oder eine eigene, hell wie dunkel. Ein Klassenstundenplan mit parallelen Kursen zeigt eine Zelle für die Gruppe; wähle einmal, welche Kurse jedes Kind besucht, und nur diese erscheinen.

### Abwesenheiten

Alle vier IServ-Arten: Krankmeldung, Beurlaubung, Abmeldung von Bus, Mittagessen oder Kindergarten und Abmeldung von der Ganztagsbetreuung. Die Regeln deiner Schule gelten: der Stichzeitpunkt für eine Krankmeldung am selben Tag, die Mindestfrist für eine Beurlaubung, die Pflichtfelder und ob einzelne Stunden meldbar sind. Beurlaubungen können Anhänge tragen. Eine Krankmeldung lässt sich als PDF speichern oder drucken, und die Telefonnummern der Schule sind einen Fingertipp entfernt.

### Elternbriefe, Pinnwand und Chat

Elternbriefe, aktuell und archiviert, mit Anhängen. Verlangt ein Brief eine Lesebestätigung, schickt die App sie so, wie es die IServ-Webseite tun würde, mit einer optionalen Nachricht an die Schule, wenn der Brief ein Feld dafür hat. Die Pinnwände laufen in einem Posteingang mit Volltextsuche zusammen. Der Chat läuft über den IServ-Messenger, wo die Schule ihn für Eltern freigibt.

### Mehrere Schulen

Jede Schule und jedes Konto behält Anmeldung, Kinder, Namen und Stundenzeiten für sich. Briefe und Beiträge laufen in einem Posteingang zusammen, mit einem Schul-Chip an jeder Zeile und einem Filter je Schule. Kinder stehen schulübergreifend nach Vornamen sortiert. Klappt die Anmeldung einer Schule nicht, wird nur sie markiert, die anderen laufen weiter.

### Die Stunden im Kalender deines Handys

Ein Feed je Kind, den deine Kalender-App abonniert: Stunden, Schulferien, Feiertage, markierte Arbeiten, genehmigte Abwesenheiten und eigene Einträge, jeweils abschaltbar. Als Link oder QR-Code. Der Link lässt sich jederzeit erneuern oder löschen.

Der Feed läuft auf einem zweiten Port, 8100, der **standardmäßig aus** ist. Schalte ihn unter **Einstellungen, Add-ons, Ranzenpost (IServ), Konfiguration, Netzwerk** ein. Wer den Link hat, sieht den Stundenplan dieses Kindes, behandle den Link also wie ein Geheimnis. Der Fernzugriff von Nabu Casa leitet keine Add-on-Ports weiter, unterwegs braucht der Feed also deinen eigenen Fernzugriff oder ein VPN.

### Sprachen und Designs

Deutsch, Englisch, Arabisch, Türkisch, Russisch und Ukrainisch. Arabisch läuft von rechts nach links. Datum, Uhrzeit und Zahlen folgen der Sprache. Helles und dunkles Design, dem Gerät folgend oder festgelegt. Große Systemschriften werden berücksichtigt. Schaltet deine Schule später eine Pflicht zur Zwei-Faktor-Anmeldung ein, sagt Ranzenpost das offen und führt dich hindurch.

## Tablet und Laptop

Ab 900 Pixel Breite ersetzt eine Navigationsleiste die Tab-Leiste. Ab 1280 Pixel öffnen Briefe, Beiträge, Abwesenheiten, Chats und Einstellungen in einem Bereich neben ihrer Liste, und der Stundenplan zeigt alle Kinder nebeneinander.

<p align="center"><img src="docs/screenshots/desktop-timetable.png" width="900" alt="Der Stundenplan in Laptop-Breite: links eine Navigationsleiste, daneben die Woche zweier Kinder"></p>

## Unterstützte IServ-Module

IServ liefert manche Module in einer alten und einer neuen Ausgabe. Ranzenpost liest die hier genannten Ausgaben. Die Einstellungsseite zeigt die Module, die dein Konto anbietet, und blendet die Bereiche der anderen aus. Der Name in Klammern ist die Adresse des Moduls hinter `/iserv/` auf dem Server deiner Schule; öffne sie dort, um zu prüfen, ob deine Schule das Modul hat.

| Modul | IServ-Ausgabe, die Ranzenpost liest | Liest | Schreibt |
| --- | --- | --- | --- |
| Stundenplan (`dsa-timetable`, `time-table`) | Der Stundenplan der Schul-App | Stunden, Vertretungen, Ausfälle, Stundenzeiten | Nichts. Markierte Arbeiten bleiben in der App |
| Elternbriefe (`parentletter`) | Elternbriefe | Aktuelle und archivierte Briefe, Anhänge | Archivieren, Lesebestätigung mit optionaler Nachricht |
| Pinnwände (`dieschulapp`) | Pinnwände (Schul-App) | Alle Pinnwände, Beiträge, Anhänge | Nichts. Der Lesestatus bleibt in der App |
| Abwesenheiten (`dieschulapp`) | Abwesenheiten (Schul-App). Das ältere Abwesenheitsmodul ist ungeprüft | Gemeldete Abwesenheiten und ihr Status, die Regeln der Schule | Krankmeldung, Beurlaubung mit Anhängen, Abmeldung, Abmeldung von der Ganztagsbetreuung |
| Elternsprechtage (`parentconference`) | Elternsprechtage | Termine und Titel | Nichts |
| Chat (`messenger`) | Messenger, wo die Schule ihn für Eltern freigibt | Räume und Nachrichten | Nachricht senden, als gelesen markieren, Raum mit einer Lehrkraft öffnen |

Bietet eine Schule nur das ältere Stundenplan-Modul unter `/iserv/timetable/` an, zeigt die Einstellungsseite es als vorhanden, aber noch nicht unterstützt, statt den Stundenplan als fehlend zu melden. Module, die Ranzenpost noch nicht kennt, erscheinen in den Einstellungen unter ihrem IServ-Namen, mit einem Knopf, der ein vorausgefülltes Issue öffnet.

## Datenschutz

- Alles läuft auf deinem Home Assistant. Es gibt kein Konto bei uns und keinen Server von uns.
- Drei Ziele nach außen: der IServ-Server deiner Schule, `openholidaysapi.org` für Feriendaten und einmalig `openplzapi.org`, um die Postleitzahl der Schule einem Bundesland zuzuordnen. Diese beiden Anfragen tragen ein Bundesland und ein Jahr oder eine Postleitzahl, sonst nichts.
- Schuladresse, Login und der eigene Zwei-Faktor-Schlüssel der App bleiben im Ordner `/data` des Add-ons. Login und Zwei-Faktor-Schlüssel liegen verschlüsselt. Mit einer **Passphrase** in den Add-on-Optionen wird der Schlüssel beim Start daraus abgeleitet und nie auf die Platte geschrieben.
- Gelesen werden nur Kinder, die dein Konto aufführt. Andere IDs probiert die App nie.
- Jeder Schreibzugriff auf IServ fragt vorher nach. Nichts wird in deinem Namen verschickt.
- **Trennen** versucht, das Zwei-Faktor-Token der App aus IServ zu entfernen, und löscht dann die Daten der Schule lokal.
- Das Repository enthält keine personenbezogenen Daten. Alle Testdaten sind erfunden.

## Hilfe bekommen

1. Öffne in der App **Einstellungen, Hilfe, Problem melden** und tippe auf **Bericht speichern**. Er bündelt Versionen, den Zustand jedes Moduls und das Add-on-Log in `ranzenpost-report.zip`, ohne Namen, Adressen und Geheimnisse. Nichts wird von selbst verschickt.
2. Öffne ein [Issue](https://github.com/githuber110/ranzenpost/issues) und hänge die Datei an. Deutsch ist willkommen.
3. Bei einem Sicherheitsproblem bitte kein öffentliches Issue öffnen. Siehe [SECURITY.md](SECURITY.md).

Das [Changelog](iserv_connector/CHANGELOG.md) nennt, was sich in jedem Release geändert hat.

## Mitmachen

Fehlerberichte, Übersetzungen und Pull Requests sind willkommen. [CONTRIBUTING.md](CONTRIBUTING.md) beschreibt die Entwicklungsumgebung, die Testsuiten und die Code-Konventionen. Die Release Notes nennen alle, die beitragen.

## Lizenz

MIT, siehe [LICENSE](LICENSE). Die mitgelieferten Schriften stehen unter der SIL Open Font License 1.1.

<details>
<summary>Schriften</summary>

- **Archivo**, The Archivo Project Authors, [github.com/Omnibus-Type/Archivo](https://github.com/Omnibus-Type/Archivo)
- **Schibsted Grotesk**, Schibsted Media, [github.com/schibsted/schibsted-grotesk](https://github.com/schibsted/schibsted-grotesk)
- **Inter**, The Inter Project Authors, [github.com/rsms/inter](https://github.com/rsms/inter)
- **Noto Sans Arabic**, The Noto Project Authors, [github.com/notofonts/arabic](https://github.com/notofonts/arabic)

Die Lizenztexte liegen in [`frontend/fonts/`](frontend/fonts/).

</details>

## Das Projekt unterstützen

Ranzenpost entsteht abends bei einem Elternteil und bleibt kostenlos. Wenn es dir ein paar Wege auf die IServ-Webseite erspart:

<a href="https://buymeacoffee.com/githuber110"><img src="https://img.shields.io/badge/Buy%20me%20a%20coffee-FFDD00.svg?style=for-the-badge&logoColor=black" alt="Buy me a coffee"></a>
