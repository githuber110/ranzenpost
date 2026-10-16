from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import absence_routes, modules, reportfacts
from app.identifiers import UNKNOWN_CHILD_KEY
from app.iserv.older_absence_form import (
    ROLE_FROM,
    ROLE_FROM_TIME,
    ROLE_KIND,
    ROLE_PERIOD,
    ROLE_PROFILE,
    ROLE_REASON,
    ROLE_TILL,
    ROLE_TILL_TIME,
    ROLE_WHOLE_DAY,
    OlderFormError,
    answer_errors,
    attachment_key,
    change_log,
    create_path,
    form_pairs,
    form_schema,
    form_values,
    offered_profiles,
    parse_create_form,
)
from app.iserv.errors import DataError
from app.older_absence_actions import (
    ATTACH_UNCERTAIN_KEY,
    ATTACH_UNSUPPORTED_KEY,
    ATTACHED_KEY,
    ATTACHMENT_KEPT_KEY,
    ATTACHMENT_LOCKED_KEY,
    ATTACHMENT_REMOVED_KEY,
    owned_csv,
    BUSY_KEY,
    LOCKED_KEY,
    NO_FORM_KEY,
    NO_PROFILE_KEY,
    PENDING_KEY,
    PENDING_STATUS,
    REJECTED_KEY,
    SENT_KEY,
    UNCERTAIN_KEY,
    UNSUPPORTED_KEY,
    WITHDRAW_UNCERTAIN_KEY,
)
from app.poller import Poller
from app.service import IServService
from app.store import Store
from tests.support import DEFAULT_SECRETS, Response

SCHOOL = "https://older-school.example"
LIST = modules.OLDER_ABSENCE_PATH
START_PAGE = '<html><body><nav><a href="/iserv/absence/">Abwesenheiten</a></nav></body></html>'
CHILDREN = [{"child_id": "c-mia", "name": "Mia Muster"}, {"child_id": "c-tom", "name": "Tom Beispiel"}]
FORM_GERMAN_SELECT = """<html><body><form method="post" action="/iserv/absence/add" name="absence">
<div class="form-group"><label for="absence_student" class="required">Schüler/in</label>
<select id="absence_student" name="absence[student]" required><option value="">Bitte wählen</option>
<option value="11">Muster, Mia</option><option value="12">Beispiel, Tom</option><option value="13">Fremd, Fritz</option></select></div>
<div class="form-group"><label for="absence_start" class="required">Beginn</label><input type="date" id="absence_start" name="absence[start]" required></div>
<div class="form-group"><label for="absence_end" class="required">Ende</label><input type="date" id="absence_end" name="absence[end]" required></div>
<div class="form-group"><label for="absence_reason">Bemerkung</label><textarea id="absence_reason" name="absence[reason]"></textarea></div>
<input type="hidden" id="absence__token" name="absence[_token]" value="tok-1">
<button type="submit" name="absence[submit]" value="">Speichern</button> <a href="/iserv/absence/">Abbrechen</a>
</form></body></html>"""
FORM_ENGLISH_RADIO = """<form method="post" action="https://older-school.example/iserv/absence/create">
<label for="report_child" class="required">Student</label>
<div id="report_child"><input type="radio" id="report_child_0" name="report[child]" value="7" required><label for="report_child_0">Mia Muster</label>
<input type="radio" id="report_child_1" name="report[child]" value="8" required><label for="report_child_1">Tom Beispiel</label></div>
<label for="report_from">From</label><input type="datetime-local" id="report_from" name="report[from]" required>
<label for="report_until">Until</label><input type="datetime-local" id="report_until" name="report[until]" required>
<label><input type="checkbox" name="report[allDay]" value="1"> All day</label>
<label for="report_type">Type</label><select id="report_type" name="report[type]" required><option value="ill">Illness</option><option value="other">Other</option></select>
<label for="report_phone">Phone number for questions</label><input type="text" id="report_phone" name="report[phone]" required>
<input type="hidden" name="report[_token]" value="tok-2">
<input type="submit" value="Report">
</form>"""
FORM_SPLIT_DATE_TIME = """<form method="post" action="/iserv/absence/add">
<label for="a_student">Schüler</label><select id="a_student" name="a[student]"><option value="5">Mia Muster</option><option value="6">Max Mustermann</option></select>
<label for="a_start_date">Abwesend ab</label><input type="text" id="a_start_date" name="a[start][date]" placeholder="TT.MM.JJJJ" required>
<input type="time" name="a[start][time]" required>
<label for="a_end_date">Abwesend bis</label><input type="text" id="a_end_date" name="a[end][date]" placeholder="TT.MM.JJJJ" required>
<input type="time" name="a[end][time]" required>
<label><input type="checkbox" name="a[confirm]" value="1" required> Ich bestätige die Angaben</label>
<input type="hidden" name="a[_token]" value="tok-3">
<button type="submit">Absenden</button>
</form>"""
FORM_AS_DOCUMENTED = """<form method="post" action="/iserv/absence/add" name="absence">
<label for="absence_person" class="required">Schüler/in</label><select id="absence_person" name="absence[person]"><option value="11">Muster, Mia</option></select>
<label for="absence_period" class="required">Zeitraum</label><input type="text" id="absence_period" name="absence[period]" required>
<label><input type="checkbox" name="absence[allDay]" value="1" checked> Ganztägig</label>
<label for="absence_comment">Kommentar</label><textarea id="absence_comment" name="absence[comment]"></textarea>
<input type="hidden" name="absence[_token]" value="tok-4">
<button type="submit" name="save">Speichern</button><button type="submit" name="saveAndNew">Speichern und weiter</button>
<a href="/iserv/absence/">Abbrechen</a></form>"""
CONFIRM_PAGE = """<form method="post" action="/iserv/absence/{id}/delete"><input type="hidden" name="form[_token]" value="tok-d">
<button type="submit" name="form[cancel]">Abbrechen</button><button type="submit" name="form[delete]" class="btn btn-danger">Löschen</button></form>"""
UPLOAD_FORM = """<form method="post" action="/iserv/absence/{id}/attachment/add" enctype="multipart/form-data">
<input type="file" name="attachment[file]"><input type="hidden" name="attachment[_token]" value="tok-a">
<button type="submit" name="attachment[submit]">Hochladen</button></form>"""
REMOVE_CONFIRM = """<form method="post" action="/iserv/absence/{id}/attachment/{index}/delete"><input type="hidden" name="_token" value="tok-x">
<button type="submit" name="confirm">Ja, löschen</button></form>"""
STATUS_WORDS = {"open": "offen", "accepted": "entschuldigt"}


def file_id(name):
    return name.lower().replace(".", "-")


def german(day):
    return "%s.%s.%s" % (day[8:10], day[5:7], day[:4])


class FakeSchool:
    def __init__(self, form_html=FORM_GERMAN_SELECT, add_link='<a href="/iserv/absence/add">Hinzufügen</a>'):
        self.form_html = form_html
        self.add_link = add_link
        self.rows = [{"id": "481", "name": "Muster, Mia", "from": "2026-09-14", "till": "2026-09-16", "delete": False}]
        self.names = {"11": "Muster, Mia", "12": "Beispiel, Tom", "13": "Fremd, Fritz", "7": "Mia Muster", "8": "Tom Beispiel", "5": "Mia Muster"}
        self.reads = []
        self.posts = []
        self.store_posted = True
        self.reject_with = ""
        self.post_status = 200
        self.files = {}
        self.upload = "inline"
        self.removable = ""
        self.log = False
        self.export = ""

    def list_page(self):
        rows = []
        for row in self.rows:
            link = '<a href="/iserv/absence/%s/delete">x</a>' % row["id"] if row["delete"] else ""
            link += '<a href="/iserv/absence/%s/show">i</a>' % row["id"] if row.get("detail") else ""
            rows.append(
                '<tr><td><input type="checkbox" value="%s"></td><td>%s - %s</td><td>%s</td><td>offen</td><td>%s</td></tr>'
                % (row["id"], german(row["from"]), german(row["till"]), row["name"], link)
            )
        return (
            '<html><body>%s<table id="crud-table"><thead><tr><th></th><th>Zeitraum</th><th>Name</th><th>Status</th><th></th></tr></thead>'
            "<tbody>%s</tbody></table>%s</body></html>" % (self.add_link, "".join(rows), '<a href="/iserv/absence/export">Exportieren</a>' if self.export else "")
        )

    def get(self, path):
        self.reads.append(path)
        if path.startswith(modules.DSA_API):
            return Response(403, SCHOOL + path)
        if path == "/iserv/":
            return Response(200, SCHOOL + path, START_PAGE)
        if path == LIST:
            return Response(200, SCHOOL + path, self.list_page())
        if path == "/iserv/absence/export" and self.export:
            answer = Response(200, SCHOOL + path, "", content_type="text/csv")
            answer.content = self.export
            return answer
        if path in ("/iserv/absence/add", "/iserv/absence/create"):
            return Response(200, SCHOOL + path, self.form_html)
        for row in self.rows:
            files = self.files.setdefault(row["id"], [])
            if path == "/iserv/absence/%s/show" % row["id"] and row.get("detail"):
                return Response(200, SCHOOL + path, self.detail_page(row["id"], files))
            if path == "/iserv/absence/%s/attachment/add" % row["id"] and self.upload == "page":
                return Response(200, SCHOOL + path, UPLOAD_FORM.format(id=row["id"]))
            for index, name in enumerate(files):
                if path == "/iserv/absence/%s/attachment/%s/delete" % (row["id"], file_id(name)) and self.removable == "link":
                    return Response(200, SCHOOL + path, REMOVE_CONFIRM.format(id=row["id"], index=file_id(name)))
                if path == "/iserv/absence/%s/attachment/%s/download" % (row["id"], file_id(name)):
                    return Response(200, SCHOOL + path, "PDF-" + name, content_type="application/pdf")
            if path == "/iserv/absence/%s/delete" % row["id"] and row["delete"]:
                return Response(200, SCHOOL + path, CONFIRM_PAGE.format(id=row["id"]))
        return Response(404, SCHOOL + path)

    def detail_page(self, entry_id, files):
        links = "<ul>%s</ul>" % "".join(
            "<li>%s%s</li>" % ('<a href="/iserv/absence/%s/attachment/%s/download">%s</a>' % (entry_id, file_id(name), name), self.remove_control(entry_id, file_id(name)))
            for name in files
        )
        if self.log:
            links += ("<h3>Änderungsprotokoll</h3><table><tr><th>Datum</th><th>Änderung</th></tr>"
                      "<tr><td>13.09.2026 07:12</td><td>Erstellt</td></tr><tr><td>14.09.2026 08:00</td><td>Status: entschuldigt</td></tr></table>")
        add_link = '<a href="/iserv/absence/%s/attachment/add">Anhang hinzufügen</a>' % entry_id
        upload = {"inline": UPLOAD_FORM.format(id=entry_id), "page": add_link}.get(self.upload, "")
        nav = '<nav><a href="/iserv/file/">Dateien</a><a href="/iserv/absence/">Abwesenheiten</a></nav>'
        return "<html><body>%s<h1>Abwesenheit</h1>%s%s</body></html>" % (nav, links, upload)

    def remove_control(self, entry_id, index):
        path = "/iserv/absence/%s/attachment/%s/delete" % (entry_id, index)
        if self.removable == "link":
            return '<a href="%s">Löschen</a>' % path
        if self.removable == "form":
            return '<form method="post" action="%s"><input type="hidden" name="_token" value="tok-r"><button type="submit">Löschen</button></form>' % path
        return ""

    def post(self, url, data, headers, files=None):
        self.posts.append((url, list(data), dict(headers or {})) + ((files,) if files else ()))
        path = urlsplit(url).path
        fields = dict(data)
        if "/attachment/" in path and path.endswith("/delete"):
            parts = path.split("/")
            entry_id, removed = parts[3], parts[5]
            if fields.get("_token") in ("tok-r", "tok-x") and self.store_posted:
                self.files[entry_id] = [name for name in self.files[entry_id] if file_id(name) != removed]
            return Response(200, SCHOOL + "/iserv/absence/%s/show" % entry_id, self.detail_page(entry_id, self.files[entry_id]))
        if path.endswith("/attachment/add"):
            entry_id = path.split("/")[3]
            if fields.get("attachment[_token]") == "tok-a" and self.store_posted:
                self.files.setdefault(entry_id, []).append(files["attachment[file]"][0])
            return Response(200, SCHOOL + "/iserv/absence/%s/show" % entry_id, self.detail_page(entry_id, self.files.get(entry_id, [])))
        if path.endswith("/delete"):
            entry_id = path.split("/")[-2]
            if fields.get("form[_token]") == "tok-d" and "form[delete]" in fields and self.store_posted:
                self.rows = [row for row in self.rows if row["id"] != entry_id]
            return Response(200, SCHOOL + LIST, self.list_page())
        if self.post_status != 200:
            return Response(self.post_status, url, "")
        if self.reject_with:
            return Response(200, url, self.reject_with)
        if self.store_posted:
            student = next((value for name, value in data if name.endswith(("[student]", "[child]"))), "5")
            start = next(value for name, value in data if name.endswith(("[start]", "[from]", "[start][date]")))
            end = next(value for name, value in data if name.endswith(("[end]", "[until]", "[end][date]")))
            self.rows.append({"id": "9%02d" % len(self.rows), "name": self.names[student], "from": iso(start), "till": iso(end), "delete": False})
        return Response(200, SCHOOL + LIST, self.list_page())


def iso(value):
    value = value[:10] if "-" in value[:10] else value
    if "." in value:
        day, month, year = value[:10].split(".")
        return "%s-%s-%s" % (year, month, day)
    return value[:10]


class SchoolClient:
    def __init__(self, url, school):
        self.url = url
        self.school = school
        self.authed = False

    def login(self, username, password, code_provider):
        self.authed = True
        return self

    def is_authenticated(self):
        return self.authed

    def fetch(self, path, params=None):
        return self.school.get(path)

    def fetch_live(self, path, params=None):
        return self.school.get(path)

    def fetch_file(self, path, limit, timeout=60):
        response = self.fetch(path)
        headers = dict(getattr(response, "headers", None) or {"content-type": "application/pdf"})
        content = getattr(response, "content", None)
        if content is None:
            content = (getattr(response, "text", "") or "").encode("utf-8")
        return SimpleNamespace(status_code=response.status_code, url=response.url, headers=headers, content=content, truncated=False)

    def fetch_or_raise(self, path, params=None):
        from app.iserv.errors import DataError

        response = self.fetch(path, params)
        if response.status_code != 200:
            raise DataError("request failed: %s" % response.status_code)
        return response

    def post_absolute(self, url, data, timeout=30, follow_redirects=True, headers=None):
        return self.school.post(url, data, headers)

    def post_form(self, url, data, files=None, headers=None, timeout=60):
        return self.school.post(url, data, headers, files)


def older_school(tmp_path, school=None, children=CHILDREN):
    school = school or FakeSchool()
    store = Store(tmp_path / "data")
    entry = store.add_connection(SCHOOL, setup_complete=True, children=children)
    store.save_secrets(entry["id"], dict(DEFAULT_SECRETS))
    service = IServService(store, client_factory=lambda url: SchoolClient(url, school))
    connection = service.known_connection(entry["id"])
    connection.store.save_modules(modules.detect(START_PAGE, lambda path, params=None: school.get(path), None))
    connection._login()
    school.reads.clear()
    return service, connection, school


def report(service, connection, **fields):
    payload = {"type": "absence", "student_id": "c-mia", "from_date": "2026-10-20", "till_date": "2026-10-21"}
    payload.update(fields)
    return service.report_absence(connection.id, payload)


def test_the_create_page_is_found_by_its_path_or_its_label_and_never_by_a_row_action():
    page_url = SCHOOL + LIST
    assert create_path('<a href="/iserv/absence/481/delete">x</a><a href="/iserv/absence/add">+</a>', page_url) == "/iserv/absence/add"
    assert create_path('<a href="/iserv/absence/report-form">Neue Abwesenheit</a>', page_url) == "/iserv/absence/report-form"
    assert create_path('<a href="/iserv/absence/481/edit">Neu</a><a href="/iserv/absence/delete">Neu</a>', page_url) == ""
    assert create_path('<a href="https://elsewhere.example/iserv/absence/add">x</a><a href="/iserv/mail/add">x</a>', page_url) == ""


def test_a_german_select_form_maps_every_role_and_offers_only_known_profiles():
    form = parse_create_form(FORM_GERMAN_SELECT, SCHOOL + "/iserv/absence/add", CHILDREN)
    assert {role: control.name for role, control in form.roles.items()} == {
        ROLE_PROFILE: "absence[student]", ROLE_FROM: "absence[start]", ROLE_TILL: "absence[end]", ROLE_REASON: "absence[reason]",
    }
    assert form.action == SCHOOL + "/iserv/absence/add"
    assert form.submit == ("absence[submit]", "")
    schema = form_schema(form, CHILDREN)
    assert schema["profiles"] == [{"id": "c-mia", "name": "Mia Muster"}, {"id": "c-tom", "name": "Tom Beispiel"}]
    assert (schema["till"], schema["times"], schema["whole_day"], schema["extras"]) == (True, False, False, [])
    assert schema["reason"]["label"] == "Bemerkung" and schema["reason"]["required"] is False


def test_an_english_radio_form_with_datetime_whole_day_kind_and_an_extra_required_field():
    form = parse_create_form(FORM_ENGLISH_RADIO, SCHOOL + "/iserv/absence/create", CHILDREN)
    assert {role: control.name for role, control in form.roles.items()} == {
        ROLE_PROFILE: "report[child]", ROLE_FROM: "report[from]", ROLE_TILL: "report[until]",
        ROLE_WHOLE_DAY: "report[allDay]", ROLE_KIND: "report[type]",
    }
    assert form.roles[ROLE_PROFILE].label == "Student"
    schema = form_schema(form, CHILDREN)
    assert (schema["times"], schema["whole_day"]) == (True, True)
    assert schema["kind"]["options"] == [{"value": "ill", "label": "Illness"}, {"value": "other", "label": "Other"}]
    assert [(extra["name"], extra["type"], extra["label"], extra["required"]) for extra in schema["extras"]] == [
        ("report[phone]", "text", "Phone number for questions", True)
    ]
    payload = {"from_date": "2026-10-20", "till_date": "2026-10-20", "from_time": "08:00", "till_time": "12:30", "kind": "ill", "extra": {"report[phone]": "0123"}}
    values, sent = form_values(form, payload, "c-tom", offered_profiles(form, CHILDREN))
    assert values["report[child]"] == "8"
    assert (values["report[from]"], values["report[until]"], values["report[allDay]"]) == ("2026-10-20T08:00", "2026-10-20T12:30", False)
    whole, _sent = form_values(form, dict(payload, whole_day=True, from_time="", till_time=""), "c-tom", offered_profiles(form, CHILDREN))
    assert (whole["report[from]"], whole["report[until]"], whole["report[allDay]"]) == ("2026-10-20T00:00", "2026-10-20T23:59", True)
    pairs = form_pairs(form, whole)
    assert ("report[allDay]", "1") in pairs and ("report[_token]", "tok-2") in pairs
    with pytest.raises(OlderFormError) as missing:
        form_values(form, dict(payload, extra={}), "c-tom", offered_profiles(form, CHILDREN))
    assert missing.value.field_key == "report[phone]"
    with pytest.raises(OlderFormError) as untimed:
        form_values(form, dict(payload, from_time=""), "c-tom", offered_profiles(form, CHILDREN))
    assert untimed.value.field_key == ROLE_FROM_TIME


def test_separate_date_and_time_fields_with_a_german_text_date_and_a_required_checkbox():
    form = parse_create_form(FORM_SPLIT_DATE_TIME, SCHOOL + "/iserv/absence/add", CHILDREN)
    assert {role: control.name for role, control in form.roles.items()} == {
        ROLE_PROFILE: "a[student]", ROLE_FROM: "a[start][date]", ROLE_FROM_TIME: "a[start][time]",
        ROLE_TILL: "a[end][date]", ROLE_TILL_TIME: "a[end][time]",
    }
    schema = form_schema(form, CHILDREN)
    assert schema["profiles"] == [{"id": "c-mia", "name": "Mia Muster"}]
    assert schema["times"] is True
    assert [(extra["name"], extra["type"]) for extra in schema["extras"]] == [("a[confirm]", "checkbox")]
    payload = {"from_date": "2026-10-20", "till_date": "2026-10-22", "from_time": "08:00", "till_time": "13:00", "extra": {"a[confirm]": True}}
    values, _sent = form_values(form, payload, "c-mia", offered_profiles(form, CHILDREN))
    assert form_pairs(form, values) == [
        ("a[student]", "5"), ("a[start][date]", "20.10.2026"), ("a[start][time]", "08:00"),
        ("a[end][date]", "22.10.2026"), ("a[end][time]", "13:00"), ("a[confirm]", "1"), ("a[_token]", "tok-3"),
    ]
    with pytest.raises(OlderFormError):
        form_values(form, payload, "c-tom", offered_profiles(form, CHILDREN))


def test_the_documented_form_with_one_period_field_and_a_whole_day_box():
    form = parse_create_form(FORM_AS_DOCUMENTED, SCHOOL + "/iserv/absence/add", CHILDREN)
    assert {role: control.name for role, control in form.roles.items()} == {
        ROLE_PROFILE: "absence[person]", ROLE_PERIOD: "absence[period]", ROLE_WHOLE_DAY: "absence[allDay]", ROLE_REASON: "absence[comment]",
    }
    schema = form_schema(form, CHILDREN)
    assert (schema["till"], schema["times"], schema["whole_day"]) == (True, False, True)
    payload = {"from_date": "2026-10-20", "till_date": "2026-10-21", "whole_day": True, "reason": "Fieber"}
    values, sent = form_values(form, payload, "c-mia", offered_profiles(form, CHILDREN))
    assert form_pairs(form, values) == [
        ("absence[person]", "11"), ("absence[period]", "20.10.2026 - 21.10.2026"), ("absence[allDay]", "1"),
        ("absence[comment]", "Fieber"), ("absence[_token]", "tok-4"), ("save", ""),
    ]
    assert (sent["from_date"], sent["till_date"]) == ("2026-10-20", "2026-10-21")
    unchecked, _sent = form_values(form, dict(payload, whole_day=False), "c-mia", offered_profiles(form, CHILDREN))
    assert ("absence[allDay]", "1") not in form_pairs(form, unchecked)


def test_a_profile_field_whose_options_match_no_known_profile_offers_nobody():
    form = parse_create_form(FORM_GERMAN_SELECT.replace("Muster, Mia", "Anders, Anna").replace("Beispiel, Tom", "Weiter, Willi"), SCHOOL + "/iserv/absence/add", CHILDREN)
    assert form.roles[ROLE_PROFILE].name == "absence[student]"
    assert form_schema(form, CHILDREN)["profiles"] == []


def test_a_validation_answer_is_mapped_back_to_the_field_and_the_form():
    form = parse_create_form(FORM_GERMAN_SELECT, SCHOOL + "/iserv/absence/add", CHILDREN)
    answer = FORM_GERMAN_SELECT.replace(
        '<div class="form-group"><label for="absence_start"',
        '<div class="alert alert-danger">Das Formular enthält Fehler.</div><div class="form-group has-error"><label for="absence_start"',
    ).replace(
        'name="absence[start]" required></div>',
        'name="absence[start]" required><span class="help-block"><ul><li>Das Datum liegt in der Vergangenheit.</li></ul></span></div>',
    )
    present, fields, general = answer_errors(answer, form)
    assert present is True
    assert fields == {ROLE_FROM: "Das Datum liegt in der Vergangenheit."}
    assert general == ["Das Formular enthält Fehler."]
    plain_help = FORM_GERMAN_SELECT.replace('name="absence[end]" required>', 'name="absence[end]" required><span class="help-block">TT.MM.JJJJ</span>')
    assert answer_errors(plain_help, form) == (True, {}, [])
    assert answer_errors("<html><div class='alert alert-danger'>x</div></html>", form)[0] is False


def test_a_report_is_sent_with_token_and_submit_and_succeeds_only_once_the_list_shows_it(tmp_path):
    service, connection, school = older_school(tmp_path)
    result = report(service, connection, reason="Fieber")
    assert result["ok"] is True and result["message_key"] == SENT_KEY
    assert len(school.posts) == 1
    url, data, headers = school.posts[0]
    assert url == SCHOOL + "/iserv/absence/add"
    assert data == [
        ("absence[student]", "11"), ("absence[start]", "2026-10-20"), ("absence[end]", "2026-10-21"),
        ("absence[reason]", "Fieber"), ("absence[_token]", "tok-1"), ("absence[submit]", ""),
    ]
    assert headers["Referer"] == SCHOOL + "/iserv/absence/add" and headers["Origin"] == SCHOOL
    assert school.reads == [LIST, "/iserv/absence/add", LIST]
    assert connection.store.load_older_absence_pending() == {}


def test_a_school_validation_error_is_returned_per_field_and_nothing_is_retried(tmp_path):
    school = FakeSchool()
    school.reject_with = FORM_GERMAN_SELECT.replace(
        '<div class="form-group"><label for="absence_end"', '<div class="form-group has-error"><label for="absence_end"'
    ).replace('name="absence[end]" required></div>', 'name="absence[end]" required><div class="invalid-feedback">Ende vor Beginn.</div></div>')
    service, connection, school = older_school(tmp_path, school)
    result = report(service, connection)
    assert result["ok"] is False and result["message_key"] == REJECTED_KEY
    assert result["field_errors"] == {ROLE_TILL: "Ende vor Beginn."}
    assert len(school.posts) == 1
    assert connection.store.load_older_absence_pending() == {}


def test_an_unconfirmed_report_is_not_retried_and_shows_as_unconfirmed_in_the_list_until_it_appears(tmp_path):
    school = FakeSchool()
    school.store_posted = False
    service, connection, school = older_school(tmp_path, school)
    result = report(service, connection)
    assert result["ok"] is False and result["uncertain"] is True and result["message_key"] == UNCERTAIN_KEY
    assert len(school.posts) == 1
    overview = service.absences_overview(connection.id)
    pending = [entry for entry in overview["entries"] if entry.get("unconfirmed")]
    assert len(pending) == 1
    entry = pending[0]
    assert (entry["student_id"], entry["from_date"], entry["till_date"], entry["status"]) == ("c-mia", "2026-10-20", "2026-10-21", PENDING_STATUS)
    assert entry["deletable"] is False and entry["locked_reason_key"] == PENDING_KEY
    assert service.delete_absence(connection.id, {"type": "absence", "id": entry["id"]})["message_key"] == LOCKED_KEY
    school.rows.append({"id": "990", "name": "Mia Muster", "from": "2026-10-20", "till": "2026-10-21", "delete": False})
    later = service.absences_overview(connection.id)
    assert [entry for entry in later["entries"] if entry.get("unconfirmed")] == []
    assert connection.store.load_older_absence_pending() == {}


def test_a_refused_post_is_a_failure_not_an_unconfirmed_entry(tmp_path):
    school = FakeSchool()
    school.post_status = 403
    service, connection, school = older_school(tmp_path, school)
    result = report(service, connection)
    assert result["ok"] is False and result.get("uncertain") is None
    assert result["message_vars"] == {"status": 403}
    assert connection.store.load_older_absence_pending() == {}


def test_unconfirmed_entries_do_not_reach_home_assistant():
    class NoSchools:
        store = None

        def connections(self):
            return []

    entry = {"id": "older:pending:x", "student_id": "c-mia", "from_date": "2026-10-20", "till_date": "2026-10-20", "status": PENDING_STATUS, "unconfirmed": True}
    overview = {"children": [{"id": "c-mia", "name": "Mia Muster"}], "entries": [entry]}
    snapshot = {}
    Poller(NoSchools(), clock=lambda: 1_788_000_000)._store_absences("s1", snapshot, {"s1:c-mia"}, CHILDREN[:1], overview)
    assert snapshot["children"]["s1:c-mia"]["absences"] == []


@pytest.mark.parametrize(
    ("fields", "key"),
    [
        ({"student_id": "c-unknown"}, UNKNOWN_CHILD_KEY),
        ({"from_date": "2026-10-22", "till_date": "2026-10-21"}, "api.absence.error.range"),
        ({"from_date": "20.10.2026"}, "api.absence.error.date"),
    ],
)
def test_a_report_the_form_cannot_take_is_refused_before_anything_is_sent(tmp_path, fields, key):
    service, connection, school = older_school(tmp_path)
    result = report(service, connection, **fields)
    assert result["ok"] is False and result["message_key"] == key
    assert school.posts == []


def test_a_profile_the_form_does_not_offer_is_refused(tmp_path):
    school = FakeSchool(form_html=FORM_SPLIT_DATE_TIME)
    service, connection, school = older_school(tmp_path, school)
    result = report(service, connection, student_id="c-tom", from_time="08:00", till_time="12:00", extra={"a[confirm]": True})
    assert result["message_key"] == UNKNOWN_CHILD_KEY
    assert school.posts == []


def test_the_form_route_describes_the_fields_and_says_when_nobody_or_nothing_fits(tmp_path):
    service, connection, school = older_school(tmp_path)
    app = FastAPI()
    absence_routes.register_routes(app, service)
    body = TestClient(app).get("/api/absences/older-form", params={"connection": connection.id}).json()
    assert body["ok"] is True
    assert [profile["id"] for profile in body["form"]["profiles"]] == ["c-mia", "c-tom"]
    school.form_html = FORM_GERMAN_SELECT.replace("Muster, Mia", "Anders, Anna").replace("Beispiel, Tom", "Weiter, Willi")
    assert service.older_absence_form(connection.id)["message_key"] == NO_PROFILE_KEY
    school.form_html = FORM_GERMAN_SELECT.replace("<textarea", '<input type="file" name="absence[file]" required><textarea')
    assert service.older_absence_form(connection.id)["form"]["files"] == {"required": True, "multiple": False}
    school.form_html = FORM_GERMAN_SELECT.replace("<textarea", '<input type="file" name="absence[a]" required><input type="file" name="absence[b]"><textarea')
    assert service.older_absence_form(connection.id)["message_key"] == UNSUPPORTED_KEY
    school.add_link = ""
    body = TestClient(app).get("/api/absences/older-form", params={"connection": connection.id}).json()
    assert body["message_key"] == NO_FORM_KEY
    assert school.posts == []


def test_a_second_report_while_one_is_sending_is_refused(tmp_path):
    service, connection, school = older_school(tmp_path)
    actions = connection._absences().older_actions
    actions._busy.acquire()
    try:
        assert report(service, connection)["message_key"] == BUSY_KEY
    finally:
        actions._busy.release()
    assert school.posts == []


def test_an_entry_with_a_delete_link_is_withdrawn_through_the_confirm_form_and_checked_in_the_list(tmp_path):
    school = FakeSchool()
    school.rows[0]["delete"] = True
    service, connection, school = older_school(tmp_path, school)
    overview = service.absences_overview(connection.id)
    entry = overview["entries"][0]
    assert entry["deletable"] is True and entry["locked_reason_key"] == ""
    result = service.delete_absence(connection.id, {"type": "absence", "id": entry["id"]})
    assert result["ok"] is True and result["message_key"] == "api.absence.withdrawn"
    assert school.posts == [(SCHOOL + "/iserv/absence/481/delete", [("form[_token]", "tok-d"), ("form[delete]", "")], {"Referer": SCHOOL + "/iserv/absence/481/delete", "Origin": SCHOOL})]


def test_a_withdraw_the_school_ignores_is_reported_as_still_listed(tmp_path):
    school = FakeSchool()
    school.rows[0]["delete"] = True
    school.store_posted = False
    service, connection, school = older_school(tmp_path, school)
    result = service.delete_absence(connection.id, {"type": "absence", "id": "older:481"})
    assert result["ok"] is False and result["message_key"] == WITHDRAW_UNCERTAIN_KEY
    assert len(school.posts) == 1


class DeletingOnGet(FakeSchool):
    def __init__(self, page_after):
        super().__init__()
        self.page_after = page_after
        self.rows[0]["delete"] = True

    def get(self, path):
        if path == "/iserv/absence/481/delete":
            self.reads.append(path)
            self.rows = [row for row in self.rows if row["id"] != "481"]
            if self.page_after is None:
                return Response(404, SCHOOL + path)
            return Response(200, SCHOOL + LIST, self.list_page())
        return super().get(path)


@pytest.mark.parametrize("page_after", ["list", None])
def test_an_entry_the_delete_link_already_removed_is_reported_as_withdrawn(tmp_path, page_after):
    service, connection, school = older_school(tmp_path, DeletingOnGet(page_after))
    result = service.delete_absence(connection.id, {"type": "absence", "id": "older:481"})
    assert result["ok"] is True and result["message_key"] == "api.absence.withdrawn"
    assert school.posts == []


def test_a_delete_link_without_a_confirm_form_that_removes_nothing_stays_locked(tmp_path):
    school = FakeSchool()
    school.rows[0]["delete"] = True
    original = school.get

    def get(path):
        if path == "/iserv/absence/481/delete":
            school.reads.append(path)
            return Response(200, SCHOOL + path, "<html><body><p>Nicht erlaubt</p></body></html>")
        return original(path)

    school.get = get
    service, connection, school = older_school(tmp_path, school)
    result = service.delete_absence(connection.id, {"type": "absence", "id": "older:481"})
    assert result["ok"] is False and result["message_key"] == LOCKED_KEY
    assert school.posts == []


def test_an_entry_without_a_delete_link_stays_read_only(tmp_path):
    service, connection, school = older_school(tmp_path)
    entry = service.absences_overview(connection.id)["entries"][0]
    assert entry["deletable"] is False and entry["locked_reason_key"] == LOCKED_KEY
    assert service.delete_absence(connection.id, {"type": "absence", "id": "older:481"})["message_key"] == LOCKED_KEY
    assert school.posts == []
    assert not any("delete" in path for path in school.reads)


def test_the_report_records_the_form_structure_and_row_actions_without_values():
    school = FakeSchool()
    school.rows[0]["delete"] = True
    page = school.get(LIST)
    lines = reportfacts.older_form_lines(SchoolClient(SCHOOL, school), page, CHILDREN)
    text = "\n".join(lines)
    assert "- Older absence row actions: delete links some, edit links none" in text
    assert "- Older absence create page: /iserv/absence/add answer 200" in text
    assert "POST, hidden 1, token yes, submit named" in text
    assert "profile absence[student] (select, required, options 3, matching profiles some)" in text
    assert "from absence[start] (date, required)" in text
    assert "reason absence[reason] (textarea)" in text
    assert "tok-1" not in text and "Mia" not in text and "Muster" not in text
    assert not any("delete" in path for path in school.reads)


def attachment_school(tmp_path, upload="inline", files=()):
    school = FakeSchool()
    school.rows[0]["detail"] = True
    school.upload = upload
    school.files["481"] = list(files)
    return older_school(tmp_path, school)


UPLOAD = {"filename": "attest.pdf", "content": b"%PDF-1", "content_type": "application/pdf"}


def test_the_detail_page_lists_attachments_offers_upload_and_serves_a_listed_file(tmp_path):
    service, connection, school = attachment_school(tmp_path, files=["Attest.pdf"])
    entry = service.absences_overview(connection.id)["entries"][0]
    assert entry["detail"] is True
    detail = service.older_absence_detail(connection.id, entry["id"])
    key = attachment_key("/iserv/absence/481/attachment/attest-pdf/download")
    assert detail == {"ok": True, "attachments": [{"key": key, "name": "Attest.pdf", "deletable": False}], "can_upload": True, "log": []}
    answer = service.older_absence_attachment(connection.id, entry["id"], key)
    assert answer.content == b"PDF-Attest.pdf"
    with pytest.raises(DataError):
        service.older_absence_attachment(connection.id, entry["id"], "0" * 16)
    assert school.posts == []


@pytest.mark.parametrize("upload", ["inline", "page"])
def test_an_attachment_is_uploaded_through_the_school_form_and_checked_on_the_detail_page(tmp_path, upload):
    service, connection, school = attachment_school(tmp_path, upload=upload)
    result = service.attach_older_absence(connection.id, "older:481", UPLOAD)
    assert result["ok"] is True and result["message_key"] == ATTACHED_KEY
    assert len(school.posts) == 1
    url, data, headers, files = school.posts[0]
    assert url == SCHOOL + "/iserv/absence/481/attachment/add"
    assert data == [("attachment[_token]", "tok-a"), ("attachment[submit]", "")]
    assert files == {"attachment[file]": ("attest.pdf", b"%PDF-1", "application/pdf")}
    assert headers["Origin"] == SCHOOL


def test_an_attachment_the_school_does_not_list_afterwards_is_reported_as_unconfirmed(tmp_path):
    service, connection, school = attachment_school(tmp_path)
    school.store_posted = False
    result = service.attach_older_absence(connection.id, "older:481", UPLOAD)
    assert result["ok"] is False and result["message_key"] == ATTACH_UNCERTAIN_KEY
    assert len(school.posts) == 1


def test_without_an_upload_form_nothing_is_sent_and_an_unknown_profile_is_refused(tmp_path):
    service, connection, school = attachment_school(tmp_path, upload="none")
    assert service.older_absence_detail(connection.id, "older:481")["can_upload"] is False
    assert service.attach_older_absence(connection.id, "older:481", UPLOAD)["message_key"] == ATTACH_UNSUPPORTED_KEY
    school.rows.append({"id": "777", "name": "Fremd, Fritz", "from": "2026-10-01", "till": "2026-10-01", "delete": False, "detail": True})
    assert service.attach_older_absence(connection.id, "older:777", UPLOAD)["message_key"] == UNKNOWN_CHILD_KEY
    assert service.older_absence_detail(connection.id, "older:777")["message_key"] == UNKNOWN_CHILD_KEY
    assert school.posts == []


def test_the_attachment_routes_take_one_file_and_serve_the_listed_one(tmp_path):
    service, connection, school = attachment_school(tmp_path, files=["Attest.pdf"])
    app = FastAPI()
    absence_routes.register_routes(app, service)
    client = TestClient(app)
    key = attachment_key("/iserv/absence/481/attachment/attest-pdf/download")
    got = client.get("/api/absences/older-attachment", params={"connection": connection.id, "id": "older:481", "key": key})
    assert got.status_code == 200 and got.content == b"PDF-Attest.pdf"
    assert client.get("/api/absences/older-attachment", params={"connection": connection.id, "id": "older:481", "key": "x"}).status_code == 502
    body = {"data": '{"connection_id": "%s", "id": "older:481"}' % connection.id}
    sent = client.post("/api/absences/older-attachment", data=body, files={"files": ("brief.pdf", b"%PDF", "application/pdf")}).json()
    assert sent["ok"] is True
    assert school.files["481"] == ["Attest.pdf", "brief.pdf"]


def test_the_report_records_the_detail_page_and_its_upload_form_without_values():
    school = FakeSchool()
    school.rows[0]["detail"] = True
    school.files["481"] = ["Attest-Mia.pdf"]
    lines = reportfacts.older_form_lines(SchoolClient(SCHOOL, school), school.get(LIST), CHILDREN)
    text = "\n".join(lines)
    assert "detail links some" in text
    assert "- Older absence detail page: /iserv/absence/481/show answer 200" in text
    assert "- Older absence attachments: links some, removable none, upload form POST, hidden 1, token yes, submit named" in text
    assert "file field attachment[file]" in text
    assert "Mia" not in text and "tok-a" not in text


@pytest.mark.parametrize("removable", ["form", "link"])
def test_an_own_attachment_is_removed_through_the_school_control_and_checked_afterwards(tmp_path, removable):
    service, connection, school = attachment_school(tmp_path, files=["Attest.pdf", "Brief.pdf"])
    school.removable = removable
    detail = service.older_absence_detail(connection.id, "older:481")
    assert [item["deletable"] for item in detail["attachments"]] == [True, True]
    result = service.delete_older_attachment(connection.id, "older:481", detail["attachments"][0]["key"])
    assert result["ok"] is True and result["message_key"] == ATTACHMENT_REMOVED_KEY
    assert school.files["481"] == ["Brief.pdf"]
    assert len(school.posts) == 1
    assert school.posts[0][0] == SCHOOL + "/iserv/absence/481/attachment/attest-pdf/delete"


def test_an_attachment_without_a_remove_control_or_still_listed_is_not_reported_as_removed(tmp_path):
    service, connection, school = attachment_school(tmp_path, files=["Attest.pdf"])
    key = attachment_key("/iserv/absence/481/attachment/attest-pdf/download")
    assert service.delete_older_attachment(connection.id, "older:481", key)["message_key"] == ATTACHMENT_LOCKED_KEY
    assert school.posts == []
    school.removable = "form"
    school.store_posted = False
    result = service.delete_older_attachment(connection.id, "older:481", key)
    assert result["ok"] is False and result["message_key"] == ATTACHMENT_KEPT_KEY
    assert len(school.posts) == 1


def test_the_change_log_is_read_as_the_school_shows_it(tmp_path):
    service, connection, school = attachment_school(tmp_path)
    school.log = True
    detail = service.older_absence_detail(connection.id, "older:481")
    assert detail["log"] == ["13.09.2026 07:12 · Erstellt", "14.09.2026 08:00 · Status: entschuldigt"]
    assert change_log("<h2>Verlauf</h2><ul><li>angelegt</li><li>geändert</li></ul>") == ["angelegt", "geändert"]
    assert change_log("<h2>Anhänge</h2><ul><li>x</li></ul>") == []


EXPORT_CSV = "Zeitraum;Name;Status\r\n14.09.2026;Muster, Mia;entschuldigt\r\n15.09.2026;Fremd, Fritz;offen\r\n"


def test_the_export_keeps_only_rows_of_known_profiles_and_is_served_as_a_download(tmp_path):
    school = FakeSchool()
    school.export = EXPORT_CSV.encode("cp1252")
    service, connection, school = older_school(tmp_path, school)
    assert service.absences_overview(connection.id)["export"] is True
    app = FastAPI()
    absence_routes.register_routes(app, service)
    answer = TestClient(app).get("/api/absences/older-export", params={"connection": connection.id})
    assert answer.status_code == 200
    assert answer.headers["content-disposition"] == 'attachment; filename="absences.csv"'
    text = answer.content.decode("utf-8-sig")
    assert text == "Zeitraum;Name;Status\r\n14.09.2026;Muster, Mia;entschuldigt\r\n"
    assert school.posts == []


def test_an_export_without_a_name_column_or_link_is_refused(tmp_path):
    assert owned_csv("Datum,Status\n14.09.2026,offen\n".encode("utf-8"), CHILDREN) is None
    content, withheld = owned_csv('Vorname,Nachname\nMia,Muster\n"Tom",Beispiel\nAnna,Anders\n'.encode("utf-8"), CHILDREN)
    assert content.decode("utf-8-sig") == "Vorname,Nachname\r\nMia,Muster\r\nTom,Beispiel\r\n" and withheld == 1
    service, connection, school = older_school(tmp_path)
    assert service.absences_overview(connection.id)["export"] is False
    with pytest.raises(DataError):
        service.older_absence_export(connection.id)


def test_the_report_names_export_removable_attachments_and_the_change_log():
    school = FakeSchool()
    school.rows[0]["detail"] = True
    school.files["481"] = ["Attest.pdf"]
    school.removable = "link"
    school.log = True
    school.export = b"x"
    text = "\n".join(reportfacts.older_form_lines(SchoolClient(SCHOOL, school), school.get(LIST), CHILDREN))
    assert "detail links some, export yes" in text
    assert "- Older absence attachments: links some, removable some, upload form" in text
    assert "- Older absence change log: rows some" in text
    assert not any("delete" in path for path in school.reads)
