[English](README.md) | [Deutsch](README.de.md)

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.svg">
    <img src="assets/banner-light.svg" width="1280" height="400" alt="Ranzenpost. Deine IServ-Schule in Home Assistant. Stundenplan, Elternbriefe, Pinnwand, Abwesenheiten.">
  </picture>
</p>

<p align="center"><b>Der Schultag deiner Kinder in Home Assistant.</b><br>Stundenplan, Vertretungen, Elternbriefe, Pinnwand, Chat, Schultermine, Krankmeldungen, Aufgaben, News, E-Mail und Dateien aus dem <a href="https://iserv.de">IServ</a> deiner Schule, als App in der Seitenleiste, als Dashboard-Karte und als Entitäten für deine Automationen.</p>

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
    <td width="33%" valign="top"><b>Die App in der Seitenleiste</b><br>Stundenplan mit Vertretungen, Elternbriefe, Pinnwand, Chat, Schultermine, Aufgaben, News, E-Mail, Dateien und Krankmeldungen. Eine Krankmeldung bekommt einen Prüfschritt, bevor etwas rausgeht.</td>
    <td width="33%" valign="top"><b>Eine Karte für jedes Dashboard</b><br>Heute, die nächste Stunde, die Woche, Briefe, Ferien und mehr. Bausteine, Größe und Kinder wählst du im visuellen Editor.</td>
    <td width="33%" valign="top"><b>Mehrere Schulen, eine App</b><br>Zwei Kinder an zwei Schulen oder zwei Konten. Ein Posteingang, eine Übersicht, jede Schule mit eigener Anmeldung.</td>
  </tr>
  <tr>
    <td valign="top"><b>Die Stunden im Kalender deines Handys</b><br>Ein Feed je Kind für deine Kalender-App: Stunden, Ferien, Arbeiten und Abwesenheiten. Als Link oder QR-Code.</td>
    <td valign="top"><b>Geräte, Sensoren und Automationen</b><br>Jedes Kind ist ein Gerät mit Kalendern, Sensoren und einem Ereignis. Auslöser wie „Stunde fällt aus“ und Bedingungen wie „Ist ein Schultag“ stehen im Automationseditor, ohne YAML.</td>
    <td valign="top"><b>Bleibt zu Hause</b><br>Läuft auf deinem Home Assistant. Keine Cloud, kein Konto, kein Server dazwischen. Zugangsdaten liegen verschlüsselt.</td>
  </tr>
</table>

> [!NOTE]
> Ranzenpost ist ein Hobbyprojekt eines Elternteils und gehört nicht zur IServ GmbH. Es entstand mit einem Elternkonto an einer Schule und liest die weiter unten genannten IServ-Module. Fehlt ein Modul deiner Schule, öffnet die Einstellungsseite dafür ein vorausgefülltes Issue.

## Installation

Du brauchst beide Teile. Die Ranzenpost-App (früher Add-on genannt) meldet sich bei IServ an und zeigt Ranzenpost in der Seitenleiste. Die Integration macht aus denselben Daten Entitäten und die Dashboard-Karte.

### 1. Repository hinzufügen

[![Das Ranzenpost-Repository zu deinem Home Assistant hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fgithuber110%2Franzenpost)

Home Assistant öffnet sich und fragt, ob du das Repository hinzufügen willst.

### 2. App installieren und Einrichtung durchlaufen

**Ranzenpost (IServ)** erscheint jetzt im App-Store. Öffne es, klicke **Installieren**, dann **Starten**. Öffne **Ranzenpost** in der Seitenleiste. Die Einrichtung fragt nach der Adresse deiner Schule, deinem Elternlogin und, falls deine Schule das nutzt, nach einem Code aus der Authenticator-App, die du schon hast. Dein Authenticator funktioniert weiter. Dann wählst du deine Kinder. Fertig.

Verlangt deine Schule die Zwei-Faktor-Anmeldung und hat das Konto noch keine, richtet die Einrichtung sie mit dir ein: QR-Code, Schlüssel und Code. Schaltet deine Schule sie später ein, sagt Ranzenpost das und führt dich hindurch.

### 3. Integration hinzufügen

[![Die Ranzenpost-Integration über HACS hinzufügen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=githuber110&repository=ranzenpost&category=integration)

Installiere **Ranzenpost** in HACS und starte Home Assistant neu. Dann **Einstellungen, Geräte & Dienste, Integration hinzufügen** und nach **Ranzenpost** suchen. Die laufende App wird von selbst gefunden. Fängst du mit der Integration an, bietet sie an, die App für dich zu installieren.

### Voraussetzungen

- Home Assistant 2025.6 oder neuer, als Home Assistant OS oder Supervised. Der App-Store braucht den Supervisor.
- Ein Rechner mit `amd64` oder `aarch64`, zum Beispiel ein Raspberry Pi 4 oder 5, ein Home Assistant Green oder Yellow oder ein x86-Rechner.
- Ein IServ-Elternkonto an einer Schule, die die Elternmodule eingeschaltet hat.
- Ranzenpost wurde mit Zwei-Faktor-Anmeldung gebaut und getestet. Die Anmeldung ohne Zwei-Faktor klappt auch. Eine echte Schule hat das bestätigt.
- HACS für die Integration.

<details>
<summary>Von Hand installieren, aktualisieren, Home Assistant ohne Supervisor</summary>

**App von Hand:** **Einstellungen, Apps**, unten rechts den **App-Store**, das Menü oben rechts, **Repositories**, `https://github.com/githuber110/ranzenpost` einfügen.

**Integration von Hand:** **HACS**, das Menü oben rechts, **Benutzerdefinierte Repositories**, `https://github.com/githuber110/ranzenpost` einfügen, **Integration** wählen.

**Ohne Supervisor:** Die Integration fragt nach Host, Port und Token der App. Das Token steht in der App unter **Einstellungen, Home Assistant**, mit einem Kopierknopf.

**Aktualisieren:** Bring immer beide Teile auf dasselbe Release. Die App: **Einstellungen, Apps**, den **App-Store**, das Menü oben rechts, **Nach Updates suchen**, dann **Ranzenpost (IServ)** und **Aktualisieren**. Die Integration: **Ranzenpost** in HACS öffnen und das Update installieren, dann Home Assistant neu starten und die Seite neu laden. Liegt ein Teil zurück oder fehlt der Neustart, zeigt Home Assistant einen Reparaturhinweis mit diesen Schritten, und die App zeigt denselben Hinweis in ihren Einstellungen. Einstellungen und die Verbindung zur Schule bleiben bei einem Update erhalten.

Die Dokumentation in Home Assistant ist [`iserv_connector/DOCS.md`](iserv_connector/DOCS.md).

</details>

## Die App

### Übersicht

Die Übersicht sammelt, was heute wichtig ist, in Blöcken, die du auswählst und ordnest: die Stunden von heute, die nächste Stunde, die Woche, Änderungen, Briefe, Beiträge, Abwesenheiten, Chat, Sprechtage, Ferien, die Termine der Schule, Aufgaben, News, Foren, Texte und Infobildschirme.

Schultermine haben außerdem eine eigene Ansicht: die geteilten Kalender, die das Konto in IServ sieht, für die nächsten Wochen.

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

Alle vier IServ-Arten: Krankmeldung, Beurlaubung, Abmeldung von Bus, Mittagessen oder Kindergarten und Abmeldung von der Ganztagsbetreuung. Die Regeln deiner Schule gelten: der Stichzeitpunkt für eine Krankmeldung am selben Tag, die Mindestfrist für eine Beurlaubung, die Pflichtfelder und ob einzelne Stunden meldbar sind. Beurlaubungen können Anlagen tragen. Eine Krankmeldung lässt sich als PDF speichern oder drucken, und die Telefonnummern der Schule sind einen Fingertipp entfernt.

Schulen mit der älteren Abwesenheitsseite von IServ funktionieren auch. Abwesenheit mit Anlagen melden, das Änderungsprotokoll lesen, die Liste exportieren und einen Eintrag zurückziehen, alles in der App.

### Elternbriefe, Pinnwand und Chat

Elternbriefe, aktuell und archiviert, mit Anlagen. Verlangt ein Brief eine Lesebestätigung, schickt die App sie so, wie es die IServ-Webseite tun würde, mit einer optionalen Nachricht an die Schule, wenn der Brief ein Feld dafür hat. Fragt ein Brief nach einer Auswahl, antwortest du in der App, und eine gesendete Antwort lässt sich ändern. Die Pinnwände laufen in einem Posteingang mit Volltextsuche zusammen. Der Chat läuft über den IServ-Messenger, wo die Schule ihn für Eltern freigibt.

### Sprechtage

Aktuelle und archivierte Sprechtage, deine eigenen Termine, Lehrkräfte, Räume, freie Zeiten und Hinweise, so wie IServ sie zeigt. Termin buchen, ändern und absagen läuft in der App über die Formulare der Schule, jeweils nach einer Bestätigung. Danach liest Ranzenpost die Seite neu und zeigt das Ergebnis. Push-Nachrichten melden, wann die Buchung öffnet, wenn ein Termin abgesagt wird, drei Tage vor einem Sprechtag und kurz vor einem Termin.

### Aufgaben und News

Offene Aufgaben stehen nach Abgabedatum vorn. Erledigte und vergangene folgen. Eine Aufgabe öffnet sich mit dem, was ihre IServ-Seite zeigt: Text, Termine, Schlagwörter, Dateien, die eigene Abgabe, Rückmeldung und Musterlösungen. Ranzenpost liest diese Seite nur, wenn du die Aufgabe öffnest, nie im Hintergrund. Dateien und Text gibst du in der App ab, entfernst abgegebene Dateien und markierst eine Aufgabe als erledigt, jeweils nach einer Bestätigung. Danach liest Ranzenpost die Aufgabenseite neu und zeigt das Ergebnis.

Jede News steht mit Kategorie und Datum in der Liste. News lassen sich nach Kategorie filtern und durchsuchen. Archiv und Paketnews erscheinen, wenn du sie im Filter wählst, und erst dann liest Ranzenpost sie. Eine News öffnet sich in der App mit vollem Text, Dateien und Links. Dateien öffnen und speichern sich über Ranzenpost.

### Foren, Texte und Infobildschirme

Foren listet jedes Forum, das das Konto sieht, mit Bereich und ungelesenen Beiträgen. Alles als gelesen markieren fragt vorher nach. Texte listet jeden Text, den das Konto sieht, auch ausgeblendete, mit Besitzer, Daten und Schlagwörtern. Es gibt einen Filter nach Auswahl und Schlagwort und eine Suche. Infobildschirme listet die Infobildschirme, die das Konto sieht, mit Namen. Diese drei Bereiche erscheinen nur, wenn das Konto das Modul hat.

### E-Mail

Das IServ-Postfach hat einen eigenen Bereich: Ordner, Suche mit Filtern, Lesen, Antworten, Weiterleiten, Entwürfe und Anlagen. Markierungen, Schlagwörter, Verschieben, Archivieren und Lesebestätigungen funktionieren wie in IServ. Empfänger und Gruppen kommen aus der Adresssuche der Schule, und du wählst die Absenderadresse. Aus einer E-Mail wird auf Wunsch ein Termin in deinem IServ-Kalender. Abwesenheitsnotiz, Weiterleitung, Filterregeln und Signaturen bearbeitest du in der App über die Einstellungsformulare von IServ. Senden, endgültiges Löschen und jede Änderung an den Einstellungen fragen vorher nach. Als Spam markieren verschiebt eine E-Mail nach einer Bestätigung in den Spam-Ordner des Mailservers, und Rückgängig holt sie zurück. Kein Spam holt eine E-Mail aus dem Spam-Ordner in den Posteingang. Empfänger kommen auch aus dem Adressbuch und aus einer Verteilerliste, die du wählst.

### Dateien und Kontakte

Konten mit Dateien sehen ihre eigenen Dateien und die Gruppenordner, öffnen Ordner, suchen und laden eine Datei über die App. Ein Hochladen in die eigenen Dateien oder einen Gruppenordner fragt vorher nach und zeigt danach die Liste neu. Der Bereich Kontakte sucht im Adressbuch der Schule und schreibt einer Person eine E-Mail. Verteilerlisten zeigen ihre Adressen. Eine Liste wird aus einer Text- oder CSV-Datei importiert oder gelöscht, jeweils nach einer Bestätigung.

### Mehrere Schulen

Jede Schule und jedes Konto behält Anmeldung, Kinder, Namen und Stundenzeiten für sich. Briefe und Beiträge laufen in einem Posteingang zusammen, mit einem Schul-Chip an jeder Zeile und einem Filter je Schule. Kinder stehen schulübergreifend nach Vornamen sortiert. Klappt die Anmeldung einer Schule nicht, wird nur sie markiert, die anderen laufen weiter. Eine Schule, die für dein Konto keine Kinder listet, bringt trotzdem Briefe, Beiträge und Chat. Wo kein Kind die Schule vorgibt, etwa bei der Lehrersuche, fragt die App nach der Schule.

### Die Stunden im Kalender deines Handys

Ein Feed je Kind, den deine Kalender-App abonniert: Stunden, Schulferien, Feiertage, markierte Arbeiten, genehmigte Abwesenheiten, eigene Einträge und die Termine der Schule, jeweils abschaltbar. Ein Konto ohne verknüpftes Profil bekommt je Schule einen Feed mit Ferien und Schulterminen. Als Link oder QR-Code. Der Link lässt sich jederzeit erneuern oder löschen.

Der Feed läuft auf einem zweiten Port, 8100, der **standardmäßig aus** ist. Schalte ihn unter **Einstellungen, Apps, Ranzenpost (IServ), Konfiguration, Netzwerk** ein. Wer den Link hat, sieht den Stundenplan dieses Kindes, behandle den Link also wie ein Geheimnis. Der Fernzugriff von Nabu Casa leitet keine App-Ports weiter, unterwegs braucht der Feed also deinen eigenen Fernzugriff oder ein VPN.

Beim Anlegen wählst du, wo du den Kalender nutzt. **Nur zuhause (WLAN)** geht im Heimnetz oder per VPN und verlässt es nie. **Überall** geht auch unterwegs und in Google Kalender und Outlook.com: Die Ranzenpost-Integration stellt den Feed als Home-Assistant-Webhook bereit, über Home Assistant Cloud (Nabu Casa) oder deine eigene externe Adresse. Ohne beides gibt es nur die Nutzung zuhause. Erneuern oder Löschen des Links beendet die alte Adresse sofort.

### Sprachen und Designs

Deutsch, Englisch, Arabisch, Türkisch, Russisch und Ukrainisch. Arabisch läuft von rechts nach links. Datum, Uhrzeit und Zahlen folgen der Sprache. Helles und dunkles Design, dem Gerät folgend oder festgelegt. Große Systemschriften werden berücksichtigt.

### Tablet und Laptop

Ab 900 Pixel Breite ersetzt eine Navigationsleiste die Tab-Leiste. Ab 1280 Pixel öffnen Briefe, Beiträge, Abwesenheiten, Chats und Einstellungen in einem Bereich neben ihrer Liste, und der Stundenplan zeigt alle Kinder nebeneinander.

<p align="center"><img src="docs/screenshots/desktop-timetable.png" width="900" alt="Der Stundenplan in Laptop-Breite: links eine Navigationsleiste, daneben die Woche zweier Kinder"></p>

## Home Assistant

### Dashboard-Karte

Die Integration registriert `custom:ranzenpost-card`. Füge sie über die Kartenauswahl hinzu und richte sie im visuellen Editor ein: Titel, Kinder, Bausteine und eine Größe je Baustein. Die Karte folgt Sprache und Design des Dashboards. Sie besteht aus denselben Bausteinen wie die Übersicht der App: `today`, `next_lesson`, `week`, `changes`, `letters`, `noticeboard`, `absences`, `conferences`, `holidays`, `school_events`, `tasks`, `news`, `forums` und `texts`. Angeboten werden nur Bausteine der Module, die deine Schule hat. Ein Baustein ohne Inhalt wird nicht gezeichnet, und die meisten Bausteine öffnen mit „Alle ansehen“ die App; der Ferien-Baustein hat keinen solchen Link. Bei mehreren Kindern stehen die Tagesbausteine nebeneinander und die Familienbausteine einmal. Ein Konto ohne verknüpftes Profil bekommt trotzdem Elternbriefe, Pinnwand, Elternsprechtage, Ferien, Schultermine, Aufgaben, News, Foren und Texte seiner Schule.

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

`children` nimmt Vornamen, Vornamen mit der Schule in Klammern oder die Schlüssel der Kinder aus der App. Lässt du es weg, zeigt die Karte alle Kinder. Jeder Baustein ist ein Schlüssel oder ein Schlüssel mit `size`, `compact` oder `normal`. Die älteren Schlüssel `view` und `child` funktionieren weiter.

</details>

### Geräte, Entitäten und Automationen

Die Integration legt ein Gerät pro Schule und eines pro Kind an. Entitäts-IDs tragen den Vornamen, zum Beispiel `sensor.ranzenpost_mia_next_lesson`. Entitäten gibt es nur für die Module, die deine Schule hat.

- **Pro Kind:** Kalender für Stunden, Arbeiten, Abwesenheiten und eigene Einträge. Sensoren für die aktuelle und die nächste Stunde, das Schulende, den nächsten Schultag, die Änderungen heute, die nächste Arbeit, ungelesene Briefe und Beiträge und offene Abwesenheiten. Zwei Binärsensoren, `school_day_today` und `timetable_changed_today`. Ein Ereignis, das bei Vertretung, Ausfall oder Raumwechsel feuert.
- **Pro Schule:** Kalender für Ferien und Schultermine. Sensoren für die nächsten Ferien, den nächsten freien Tag, den nächsten Elternsprechtag, ungelesene Briefe, Beiträge und E-Mails, offene Aufgaben, News, ungelesene Forenbeiträge, Texte und die Verbindung.

Wähle im Automationseditor das Gerät eines Kindes für Auslöser wie **Stundenplan geändert**, **Stunde fällt aus** oder **Neuer Elternbrief** und für Bedingungen wie **Ist ein Schultag**. Ganz ohne YAML. Die Integration fragt die App alle 60 Sekunden und spricht nie selbst mit IServ.

Die [Home-Assistant-Referenz](docs/home-assistant.de.md) nennt jede Entität mit ihren Attributen, alle Auslöser und Bedingungen und vier Automationen zum Übernehmen.

### Push-Nachrichten und Reparaturen

Die App schickt Nachrichten an die Notify-Dienste, die du auswählst, zum Beispiel die Home Assistant App auf deinem Handy. Sie melden Stundenplanänderungen, neue Briefe, neue Beiträge, neue Sprechtage, neue Chat-Nachrichten, neue Aufgaben, neue News, neue Forenbeiträge und neue Texte. Jede Art außer dem Hinweis auf eine nötige Anmeldung lässt sich in den Einstellungen abschalten. Jedes Ziel hat einen Testknopf, und die Texte gibt es in allen sechs Sprachen. Braucht die Anmeldung bei einer Schule dich, zeigt Home Assistant einen Reparaturhinweis mit dem Namen der Schule und dem nächsten Schritt. Er verschwindet von selbst, sobald die Anmeldung wieder klappt.

## Unterstützte IServ-Module

IServ liefert manche Module in einer alten und einer neuen Ausgabe. Ranzenpost liest die hier genannten Ausgaben. Die Einstellungsseite zeigt die Module, die dein Konto anbietet, und blendet die Bereiche der anderen aus. Der Name in Klammern ist die Adresse des Moduls hinter `/iserv/` auf dem Server deiner Schule; öffne sie dort, um zu prüfen, ob deine Schule das Modul hat.

| Modul | IServ-Ausgabe, die Ranzenpost liest | Liest | Schreibt |
| --- | --- | --- | --- |
| Stundenplan (`dsa-timetable`, `time-table`) | Der Stundenplan der Schul-App. Nennt er keine Stunden, das ältere Modul `time-table` | Stunden, Vertretungen, Ausfälle, Stundenzeiten | Nichts. Markierte Arbeiten bleiben in der App |
| Abwesenheiten (`dieschulapp`, `absence`) | Abwesenheiten (Schul-App) oder die ältere Abwesenheitsseite | Gemeldete Abwesenheiten und ihr Status, die Regeln der Schule; auf der älteren Seite auch das Änderungsprotokoll | Krankmeldung, Beurlaubung mit Anlagen, Abmeldung, Abmeldung von der Ganztagsbetreuung; auf der älteren Seite eine Meldung mit Anlagen und ihr Zurückziehen |
| Elternbriefe (`parentletter`) | Elternbriefe | Aktuelle und archivierte Briefe, Anlagen | Archivieren, Lesebestätigung mit optionaler Nachricht, Nachricht an die Schule bei Briefen mit Antwortmöglichkeit, die Antwort auf einen Brief mit Auswahl |
| Pinnwände (`dieschulapp`) | Pinnwände (Schul-App) | Alle Pinnwände, Beiträge, Anlagen | Nichts. Der Lesestatus bleibt in der App |
| Chat (`messenger`) | Messenger, wo die Schule ihn für Eltern freigibt | Räume und Nachrichten | Nachricht senden, als gelesen markieren, Raum mit einer Lehrkraft öffnen |
| Elternsprechtage (`parentconference`) | Elternsprechtage | Aktuelle und archivierte Sprechtage, eigene Termine, Lehrkräfte, Räume, freie Zeiten und Hinweise, so wie IServ sie zeigt | Termin buchen, ändern und absagen über die Formulare der Schule, jeweils nach einer Bestätigung |
| Schultermine (`calendar`) | Kalender, wo das Konto ihn sieht | Termine aller Kalender, die das Konto sieht, auch seines persönlichen Kalenders, für die nächsten Wochen | Ein Termin aus einer E-Mail, nach einer Bestätigung |
| Aufgaben (`exercise`) | Aufgaben | Aktuelle und vergangene Aufgaben, so wie IServ sie listet; beim Öffnen die Seite der Aufgabe: Text, Termine, Schlagwörter, Dateien, eigene Abgabe, Rückmeldung, Musterlösungen | Dateien und Text abgeben, abgegebene Dateien entfernen, als erledigt oder nicht erledigt markieren, jeweils nach einer Bestätigung |
| News (`news`) | News | Jede News der Liste mit Titel, Datum und Kategorie, dazu Text, Dateien und Links jeder News; Archiv und Paketnews, wenn du sie im Filter wählst | Nichts. Filter und Suche arbeiten in der App |
| Foren (`forums`, `forum`) | Foren | Jedes Forum der Übersicht mit Bereich, Beschreibung, ungelesenen Beiträgen und letztem Beitrag | Alles als gelesen markieren, nach einer Bestätigung |
| Texte (`etherpad`) | Texte | Jeder Text, den das Konto in einer IServ-Auswahl sieht, auch ausgeblendete, mit Besitzer, Daten und Schlagwörtern | Nichts. Filter und Suche arbeiten in der App |
| Infobildschirme (`infodisplay`) | Infobildschirm | Die Infobildschirme, die das Konto sieht, mit Namen | Nichts |
| E-Mail (`mail`) | IServ-Postfach | Ordner, E-Mails mit Anlagen, Suche, Schlagwörter, Absenderadressen, Empfänger- und Gruppensuche, die Mail-Einstellungen | Senden, Antworten, Weiterleiten, Entwürfe, Markierungen, Schlagwörter, Verschieben, Archivieren, Löschen, Ordner, Lesebestätigungen, Abwesenheitsnotiz, Weiterleitung, Filterregeln, Signaturen, als Spam und als kein Spam markieren, mit Rückgängig |
| Dateien (`file`) | Dateien | Eigene Dateien und Gruppenordner mit Name, Größe, Typ und Datum, die Suche, die Dateien selbst | Hochladen in die eigenen Dateien und Gruppenordner, nach einer Bestätigung |
| Adressbuch (`addressbook`) | Adressbuch | Personen aus einer Suche mit Adresse und Klasse, auch als E-Mail-Empfänger | Nichts |
| Verteilerlisten (`mailinglist`) | Verteilerlisten | Listen und ihre Adressen | Import aus einer Text- oder CSV-Datei, Löschen, jeweils nach einer Bestätigung |

Klassengeld erkennt Ranzenpost, unterstützt es aber noch nicht. Es läuft als eigener Dienst hinter einer Zustimmung in IServ, und die Unterstützung steht jemandem offen, dessen Schule Klassengeld nutzt und der sie selbst bauen möchte. Siehe [Issue #5](https://github.com/githuber110/ranzenpost/issues/5).

Bietet eine Schule nur das ältere Stundenplan-Modul unter `/iserv/timetable/` an, zeigt die Einstellungsseite es als vorhanden, aber noch nicht unterstützt, statt den Stundenplan als fehlend zu melden. Module, die Ranzenpost noch nicht kennt, erscheinen in den Einstellungen unter ihrem IServ-Namen, mit einem Knopf, der ein vorausgefülltes Issue öffnet.

## Datenschutz

- Alles läuft auf deinem Home Assistant. Es gibt kein Konto bei uns und keinen Server von uns.
- Drei Ziele nach außen: der IServ-Server deiner Schule, `openholidaysapi.org` für Feriendaten und einmalig `openplzapi.org`, um die Postleitzahl der Schule einem Bundesland zuzuordnen. Diese beiden Anfragen tragen ein Bundesland und ein Jahr oder eine Postleitzahl, sonst nichts.
- Schuladresse, Login und der eigene Zwei-Faktor-Schlüssel der App bleiben im Ordner `/data` der App. Login und Zwei-Faktor-Schlüssel liegen verschlüsselt. Mit einer **Passphrase** in den App-Optionen wird der Schlüssel beim Start daraus abgeleitet und nie auf die Platte geschrieben.
- Gelesen werden nur Kinder, die dein Konto aufführt. Andere IDs probiert die App nie.
- Ranzenpost schreibt nur in IServ, wenn du handelst. Senden, Buchen, Antworten, Abgeben, Hochladen, Importieren, Einstellungen ändern und endgültiges Löschen fragen vorher nach. Nichts wird in deinem Namen verschickt.
- **Trennen** entfernt das Zwei-Faktor-Token der App aus IServ und löscht dann die Daten der Schule lokal. Ist IServ nicht erreichbar, bleibt die Schule, bis du es erneut versuchst oder trotzdem trennst.
- Das Repository enthält keine personenbezogenen Daten. Alle Testdaten sind erfunden.

## Hilfe bekommen

1. Öffne in der App **Einstellungen, Hilfe, Problem melden** und tippe auf **Bericht speichern**. Er bündelt Versionen, den Aufbau jedes IServ-Moduls und das App-Log in `ranzenpost-report.zip`. Namen, Beträge, Adressen und Geheimnisse werden entfernt. Bei Modulen eines anderen Anbieters wie Klassengeld meldet sich der Bericht dort einmal an. Er öffnet keinen Brief und keinen einzelnen Eintrag. Nichts wird von selbst verschickt.
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
