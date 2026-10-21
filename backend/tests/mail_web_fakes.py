import html
import json
from urllib.parse import urlsplit

SCHOOL = "https://school.example"
TOKEN = "t0ken-fixture"
USERS = [
    {"label": "Class Teacher", "email": "teacher@school.example", "type": "user"},
    {"label": "Office", "email": "office@school.example", "type": "user"},
]
CALENDARS = [("/alexa.muster/home", "Mein Kalender"), ("/eltern.3b/calendar", "Eltern 3b")]
GROUPS = [{"name": "Eltern 3b", "mail": "eltern.3b@school.example", "type": "group"}]


class Answer:
    def __init__(self, status, text, url, content_type="text/html; charset=utf-8", payload=None):
        self.status_code = status
        self.text = text
        self.url = url
        self.headers = {"Content-Type": content_type}
        self.payload = payload
        self.content = text.encode("utf-8")

    def json(self):
        if self.payload is None:
            raise ValueError("no json")
        return self.payload


def php_data(addresses=()):
    return {
        "mailbox": {"folders": {"inbox": {"mailboxId": "abc1234", "type": "inbox", "name": "Posteingang", "unreadCount": 1, "totalCount": 2}},
                    "settings": {"autoArchive": [{"path": "INBOX", "days": 90}], "hasActiveVacation": False, "identities": list(addresses)}},
        "serverConfig": {"autoCompleteUrls": {"users": "/iserv/core/api/autocomplete/users", "groups": "/iserv/core/api/autocomplete/groups"}, "domains": ["school.example"]},
        "userData": {"tags": [{"name": "Wichtig", "color": "#d33", "keyword": "$label1"}, {"name": "Elternrat", "color": "green", "keyword": "$label2"}], "listLimit": 25, "displayName": "Alexa Muster", "id": "6f1f6f8e-1111-4c2b-9b9b-111111111111"},
    }


def mail_page(addresses=()):
    return (
        '<html><head><title>E-Mail - IServ</title></head><body>'
        '<form action="/iserv/auth/logout" method="post"><input type="hidden" name="id_token" value="x"></form>'
        '<a href="/iserv/mail/help">Hilfe</a><a href="/iserv/mail/settings/vacation">Abwesenheit</a>'
        '<script type="application/json" id="php-data">%s</script></body></html>' % html.escape(json.dumps(php_data(addresses)), quote=False)
    )


def _checked(flag):
    return " checked" if flag else ""


def _selected(current, value):
    return " selected" if current == value else ""


class FakeMailWeb:
    def __init__(self, ignore_posts=False, addresses=("alexa.muster@school.example", "elternrat@school.example", "someone@else.example")):
        self.base_url = SCHOOL
        self.ignore_posts = ignore_posts
        self.addresses = addresses
        self.asked = []
        self.posts = []
        self.vacation = {"enabled": False, "subject": "", "message": "", "start": ""}
        self.forward = {"address": "", "keep": True}
        self.rules = [{"name": "Newsletter", "field": "subject", "value": "Newsletter", "action": "move", "target": "Archiv"}]
        self.signature = {"text": "Viele Grüße\nAlexa", "default": addresses[0] if addresses else ""}
        self.events = []
        self.account_settings = {"pageLimit": "25", "homepageInformation": "1"}

    def is_authenticated(self):
        return True

    def login(self, username, password, code_provider):
        return self

    def _calendar_page(self):
        data = {"routes": {"calendar_create_event": "/iserv/calendar/create", "calendar_create_event_from_mail": "/iserv/calendar/api/v1/eventFromMail", "calendar_eventsources": "/iserv/calendar/api/eventsources"}}
        return '<html><body><h1>Kalender</h1><script type="application/json" id="calendar-routes">%s</script></body></html>' % html.escape(json.dumps(data), quote=False)

    def _create_page(self):
        calendars = "".join('<option value="%s">%s</option>' % (value, label) for value, label in CALENDARS)
        return (
            '<html><body><h1>Termin erstellen</h1><form name="event" method="post" action="/iserv/calendar/create">'
            '<label for="event_subject">Titel</label><input type="text" id="event_subject" name="event[subject]" required>'
            '<label for="event_calendar">Kalender</label><select id="event_calendar" name="event[calendar]">%s</select>'
            '<label for="event_startDate">Beginn</label><input type="date" id="event_startDate" name="event[startDate]" required>'
            '<label for="event_startTime">Uhrzeit</label><input type="time" id="event_startTime" name="event[startTime]">'
            '<input type="checkbox" id="event_allDay" name="event[allDay]" value="1"><label for="event_allDay">Ganztägig</label>'
            '<label for="event_location">Ort</label><input type="text" id="event_location" name="event[location]">'
            '<label for="event_description">Beschreibung</label><textarea id="event_description" name="event[description]"></textarea>'
            '<input type="hidden" name="event[_token]" value="%s"><button type="submit" name="event[save]">Speichern</button></form></body></html>'
        ) % (calendars, TOKEN)

    def _page(self, path):
        if path == "/iserv/calendar":
            return self._calendar_page()
        if path == "/iserv/calendar/create":
            return self._create_page()
        if path == "/iserv/mail":
            return mail_page(self.addresses)
        if path == "/iserv/mail/settings":
            a = self.account_settings
            choices = "".join('<option value="%s"%s>%s</option>' % (value, _selected(a["homepageInformation"], value), label) for value, label in (("1", "Anzeigen"), ("0", "Nicht anzeigen")))
            return (
                '<html><head><title>Einstellungen</title></head><body><h1>Einstellungen</h1>'
                '<form name="settings" method="post" action="/iserv/mail/account/settings">'
                '<label for="settings_pageLimit">Anzahl der E-Mails pro Seite in der Übersicht</label>'
                '<input type="number" id="settings_pageLimit" name="settings[pageLimit]" value="%s" min="10" max="200">'
                '<label for="settings_homepageInformation">Neue E-Mails auf der Startseite anzeigen</label>'
                '<select id="settings_homepageInformation" name="settings[homepageInformation]">%s</select>'
                '<input type="hidden" name="settings[_token]" value="%s"><button type="submit" name="settings[submit]">Speichern</button></form></body></html>'
            ) % (a["pageLimit"], choices, TOKEN)
        if path == "/iserv/mail/settings/vacation":
            v = self.vacation
            return (
                '<html><head><title>Abwesenheitsnotiz</title></head><body><h1>Abwesenheitsnotiz</h1>'
                '<form name="vacation" method="post" action="/iserv/mail/settings/vacation">'
                '<div class="form-group"><input type="checkbox" id="vacation_enabled" name="vacation[enabled]" value="1"%s><label for="vacation_enabled">Abwesenheitsnotiz aktiv</label></div>'
                '<div class="form-group"><label for="vacation_subject">Betreff</label><input type="text" id="vacation_subject" name="vacation[subject]" value="%s" maxlength="120"></div>'
                '<div class="form-group"><label for="vacation_message">Nachricht</label><textarea id="vacation_message" name="vacation[message]">%s</textarea></div>'
                '<div class="form-group"><label for="vacation_start">Beginn</label><input type="date" id="vacation_start" name="vacation[start]" value="%s"></div>'
                '<input type="hidden" name="vacation[_token]" value="%s"><button type="submit" name="vacation[save]">Speichern</button></form></body></html>'
            ) % (_checked(v["enabled"]), html.escape(v["subject"]), html.escape(v["message"]), v["start"], TOKEN)
        if path == "/iserv/mail/settings/forward":
            f = self.forward
            return (
                '<html><body><h1>Weiterleitung</h1><form name="forward" method="post">'
                '<label for="forward_address">Weiterleiten an</label><input type="email" id="forward_address" name="forward[address]" value="%s">'
                '<input type="checkbox" id="forward_keep" name="forward[keep]" value="1"%s><label for="forward_keep">Kopie behalten</label>'
                '<input type="hidden" name="forward[_token]" value="%s"><button type="submit">Speichern</button></form></body></html>'
            ) % (html.escape(f["address"]), _checked(f["keep"]), TOKEN)
        if path == "/iserv/mail/settings/filter":
            rows = "".join(self._rule(index, rule) for index, rule in enumerate(self.rules))
            prototype = html.escape(self._rule("__name__", {"name": "", "field": "from", "value": "", "action": "move", "target": ""}), quote=True)
            return (
                '<html><body><h1>Filterregeln</h1><form name="filter" method="post" action="/iserv/mail/settings/filter">'
                '<label>Regeln</label><div id="filter_rules" data-prototype="%s">%s</div>'
                '<input type="hidden" name="filter[_token]" value="%s"><button type="submit" name="filter[save]">Speichern</button></form></body></html>'
            ) % (prototype, rows, TOKEN)
        if path == "/iserv/mail/settings/signature":
            s = self.signature
            options = "".join('<option value="%s"%s>%s</option>' % (address, _selected(s["default"], address), address) for address in self.addresses[:2])
            return (
                '<html><body><h1>Signaturen</h1><form name="signature" method="post">'
                '<label for="signature_text">Signatur</label><textarea id="signature_text" name="signature[text]">%s</textarea>'
                '<label for="signature_default">Standard für</label><select id="signature_default" name="signature[default]">%s</select>'
                '<input type="hidden" name="signature[_token]" value="%s"><button type="submit">Speichern</button></form></body></html>'
            ) % (html.escape(s["text"]), options, TOKEN)
        return None

    @staticmethod
    def _rule(index, rule):
        fields = "".join('<option value="%s"%s>%s</option>' % (value, _selected(rule["field"], value), value) for value in ("from", "to", "subject"))
        actions = "".join('<option value="%s"%s>%s</option>' % (value, _selected(rule["action"], value), value) for value in ("move", "reject", "discard"))
        return (
            '<fieldset><legend>Regel</legend>'
            '<label for="filter_rules_{i}_name">Name</label><input type="text" id="filter_rules_{i}_name" name="filter[rules][{i}][name]" value="{name}">'
            '<label for="filter_rules_{i}_field">Feld</label><select id="filter_rules_{i}_field" name="filter[rules][{i}][field]">{fields}</select>'
            '<label for="filter_rules_{i}_value">Enthält</label><input type="text" id="filter_rules_{i}_value" name="filter[rules][{i}][value]" value="{value}">'
            '<label for="filter_rules_{i}_action">Aktion</label><select id="filter_rules_{i}_action" name="filter[rules][{i}][action]">{actions}</select>'
            '<label for="filter_rules_{i}_target">Ordner</label><input type="text" id="filter_rules_{i}_target" name="filter[rules][{i}][target]" value="{target}">'
            '</fieldset>'
        ).format(i=index, name=html.escape(rule["name"]), fields=fields, value=html.escape(rule["value"]), actions=actions, target=html.escape(rule["target"]))

    def fetch(self, path, params=None):
        self.asked.append((path, params))
        if path == "/iserv/calendar/api/eventsources":
            return Answer(404, "", SCHOOL + path)
        if path == "/iserv/calendar/feed/calendar-multi":
            start, end = (params or {}).get("start", ""), (params or {}).get("end", "")
            listed = [event for event in self.events if start <= event["start"][:10] <= end]
            return Answer(200, json.dumps(listed), SCHOOL + path, "application/json", listed)
        if path.startswith("/iserv/core/api/autocomplete/"):
            query = (params or {}).get("query", "")
            if not query:
                return Answer(400, "{}", SCHOOL + path, "application/json", {"error": "query missing"})
            listed = USERS if path.endswith("users") else GROUPS
            found = [entry for entry in listed if query.lower() in json.dumps(entry).lower()]
            return Answer(200, json.dumps(found), SCHOOL + path, "application/json", found)
        page = self._page(path)
        if page is None:
            return Answer(200, mail_page(self.addresses), SCHOOL + "/iserv/mail")
        return Answer(200, page, SCHOOL + path)

    def fetch_or_raise(self, path, params=None):
        return self.fetch(path, params)

    def post_absolute(self, url, data, timeout=30, follow_redirects=True, headers=None):
        path = urlsplit(url).path
        self.posts.append((path, list(data)))
        values = {}
        for name, value in data:
            values.setdefault(name, []).append(value)
        one = lambda name, fallback="": values.get(name, [fallback])[0]
        if not any(name.endswith("[_token]") and value == [TOKEN] for name, value in values.items()):
            return Answer(400, "<p>Token</p>", url)
        if self.ignore_posts:
            return Answer(200, self._page(path), url)
        if path == "/iserv/mail/account/settings":
            self.account_settings = {"pageLimit": one("settings[pageLimit]"), "homepageInformation": one("settings[homepageInformation]")}
            return Answer(200, self._page("/iserv/mail/settings"), SCHOOL + "/iserv/mail/settings")
        elif path == "/iserv/mail/settings/vacation":
            self.vacation = {"enabled": one("vacation[enabled]") == "1", "subject": one("vacation[subject]"), "message": one("vacation[message]"), "start": one("vacation[start]")}
        elif path == "/iserv/mail/settings/forward":
            address = one("forward[address]")
            if address and "@" not in address:
                page = self._page(path).replace("</form>", '<div class="invalid-feedback">Diese Adresse ist ungültig.</div></form>')
                return Answer(200, page, url)
            self.forward = {"address": address, "keep": one("forward[keep]") == "1"}
        elif path == "/iserv/mail/settings/filter":
            indexes = sorted({int(name.split("][")[1]) for name in values if name.startswith("filter[rules][")})
            self.rules = [{key: one("filter[rules][%d][%s]" % (index, key)) for key in ("name", "field", "value", "action", "target")} for index in indexes]
        elif path == "/iserv/calendar/create":
            if not one("event[subject]") or not one("event[startDate]"):
                page = self._create_page().replace("</form>", '<div class="invalid-feedback">Dieser Wert sollte nicht leer sein.</div></form>')
                return Answer(200, page, url)
            start = one("event[startDate]") + ("T%s:00+02:00" % one("event[startTime]") if one("event[startTime]") and not one("event[allDay]") else "")
            self.events.append({"uid": "e%d" % len(self.events), "title": one("event[subject]"), "start": start, "allDay": not one("event[startTime]") or bool(one("event[allDay]")),
                                "calendarName": dict(CALENDARS).get(one("event[calendar]"), ""), "description": one("event[description]")})
            return Answer(200, self._calendar_page(), SCHOOL + "/iserv/calendar")
        elif path == "/iserv/mail/settings/signature":
            self.signature = {"text": one("signature[text]"), "default": one("signature[default]")}
        return Answer(200, self._page(path), url)
