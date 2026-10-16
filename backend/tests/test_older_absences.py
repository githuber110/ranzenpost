from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import absence_routes, diagnostics, modules, pageshape, reportcrawl, reportfacts
from app.absence_service import OLDER_SOURCE, attach_older_rows
from app.older_absence_actions import LOCKED_KEY
from app.iserv.errors import DataError
from app.iserv.older_absences import (
    ROLE_CLASS,
    ROLE_CREATED,
    ROLE_FROM,
    ROLE_NAME,
    ROLE_PERIOD,
    ROLE_STATUS,
    ROLE_TILL,
    STATUS_ACCEPTED,
    STATUS_OPEN,
    STATUS_REJECTED,
    OlderAbsenceRow,
    OlderAbsenceShapeError,
    filter_query,
    parse_older_absences,
)
from app.poller import Poller
from app.service import IServService
from app.store import Store
from tests.support import DEFAULT_SECRETS, Response
from tests.test_refused_probes import BASE as REFUSAL_BASE
from tests.test_refused_probes import Answer, School, SchoolClient

SCHOOL = "https://older-school.example"
START_PAGE = (
    '<html><body><nav><a href="/iserv/time-table/">Stundenplan</a>'
    '<a href="/iserv/absence/">Abwesenheiten</a></nav></body></html>'
)
GERMAN_PAGE = """<html><body>
<form class="form-inline"><input type="text" name="filter[from]"></form>
<form class="form-inline list-filter"><select name="filter[status][]" multiple><option value="open">Offen</option>
<option value="excused" selected>Entschuldigt</option><option value="unexcused">Unentschuldigt</option></select>
<input type="date" name="filter[from]" value="2026-10-01"><input type="date" name="filter[to]"><button type="submit">Filtern</button></form>
<table id="crud-table" class="table table-striped">
<thead><tr><th></th><th>Zeitraum</th><th>Name</th><th>Klasse/Gruppe</th><th>Status</th><th>Erstellt am</th><th></th></tr></thead>
<tbody>
<tr><td><input type="checkbox" name="iserv_crud_multi_select[multi][]" value="481"></td>
<td>14.09.2026 - 16.09.2026</td><td>Muster, Mia</td><td>2b</td><td>entschuldigt</td><td>13.09.2026 07:12</td>
<td><a href="/iserv/absence/481/show">x</a></td></tr>
<tr><td><input type="checkbox" value="482"></td><td>02.10.2026</td><td>Tom Beispiel</td><td>4a</td><td>offen</td><td>01.10.2026</td><td></td></tr>
<tr><td><input type="checkbox" value="483"></td><td>05.10.2026</td><td>Unbekannte Person</td><td>3c</td><td>offen</td><td>05.10.2026</td><td></td></tr>
<tr><td colspan="7">Keine weiteren Einträge</td></tr>
</tbody></table>
<a href="/iserv/absence/add">Abwesenheit hinzufügen</a>
</body></html>"""
ENGLISH_PAGE = """<table id="crud-table">
<tr><th></th><th>From</th><th>To</th><th>Name</th><th>Class</th><th>Status</th><th>Created on</th></tr>
<tr><td><input type="checkbox"></td><td>14.09.2026 08:00</td><td>15.09.2026 12:30</td><td>Mia Muster</td><td>2b</td>
<td>Unexcused</td><td>2026-09-13</td></tr>
</table>"""
EMPTY_PAGE = """<table id="crud-table"><thead><tr><th></th><th>Zeitraum</th><th>Name</th><th>Klasse/Kurs</th>
<th>Status</th><th>Erstellt am</th><th></th></tr></thead><tbody></tbody></table>"""
EMPTY_STATE_PAGE = """<table id="crud-table"><thead><tr><th>Zeitraum</th><th>Name</th></tr></thead>
<tbody><tr><td colspan="2">Keine Einträge</td></tr></tbody></table>"""
ADD_PAGE = """<html><body><form method="post" action="/iserv/absence/add" name="absence">
<label for="absence_start">Beginn</label><input id="absence_start" type="date" name="absence[start]" required>
<input type="date" name="absence[end]"><select name="absence[student]"><option>a</option><option>b</option></select>
<textarea name="absence[reason]"></textarea><input type="hidden" name="absence[_token]" value="secret-token">
<button type="submit" name="absence[submit]">Speichern</button></form></body></html>"""
CHILDREN = [{"child_id": "c-mia", "name": "Mia Muster"}, {"child_id": "c-tom", "name": "Tom Beispiel"}]


def test_german_headers_map_by_name_with_a_range_a_single_day_and_an_empty_state_row():
    listed = parse_older_absences(GERMAN_PAGE)
    assert listed.roles == {ROLE_PERIOD: 1, ROLE_NAME: 2, ROLE_CLASS: 3, ROLE_STATUS: 4, ROLE_CREATED: 5}
    assert listed.unreadable == 0
    first, second, third = listed.rows
    assert (first.name, first.from_date, first.till_date) == ("Muster, Mia", "2026-09-14", "2026-09-16")
    assert (first.status, first.class_text, first.created, first.entry_id) == (STATUS_ACCEPTED, "2b", "2026-09-13", "481")
    assert (second.from_date, second.till_date, second.status) == ("2026-10-02", "2026-10-02", STATUS_OPEN)
    assert third.name == "Unbekannte Person"


def test_english_headers_with_separate_from_and_to_columns_carry_times():
    listed = parse_older_absences(ENGLISH_PAGE)
    assert listed.roles[ROLE_FROM] == 1 and listed.roles[ROLE_TILL] == 2 and listed.roles[ROLE_NAME] == 3
    row = listed.rows[0]
    assert (row.from_date, row.till_date, row.from_time, row.till_time) == ("2026-09-14", "2026-09-15", "08:00", "12:30")
    assert (row.status, row.created, row.entry_id) == (STATUS_REJECTED, "2026-09-13", "")


@pytest.mark.parametrize("page", [EMPTY_PAGE, EMPTY_STATE_PAGE])
def test_an_empty_list_is_proven_empty(page):
    listed = parse_older_absences(page)
    assert listed.rows == []
    assert listed.unreadable == 0


def test_a_missing_list_or_unknown_columns_are_unknown_not_empty():
    with pytest.raises(OlderAbsenceShapeError):
        parse_older_absences("<html><body><p>Anmelden</p></body></html>")
    with pytest.raises(OlderAbsenceShapeError):
        parse_older_absences('<table id="crud-table"><tr><th>Foo</th><th>Bar</th></tr><tr><td>a</td><td>b</td></tr></table>')


def test_a_row_without_a_date_is_counted_as_unreadable():
    page = GERMAN_PAGE.replace("<td>02.10.2026</td>", "<td>bald</td>")
    listed = parse_older_absences(page)
    assert listed.unreadable == 1
    assert len(listed.rows) == 2


def test_rows_attach_only_to_a_unique_known_profile_and_unknown_names_are_dropped():
    rows = parse_older_absences(GERMAN_PAGE).rows
    entries, withheld = attach_older_rows(rows, CHILDREN)
    assert withheld == 1
    assert [entry["student_id"] for entry in entries] == ["c-mia", "c-tom"]
    mia = entries[0]
    assert mia["source"] == OLDER_SOURCE
    assert mia["id"] == "older:481"
    assert mia["kind"] == "absence" and mia["label_key"] == "absence.entry.kind.absence"
    assert mia["deletable"] is False and mia["locked_reason_key"] == LOCKED_KEY
    assert mia["technical"] == {"id": "481", "created_at": "2026-09-13", "class_code": "2b"}


def test_a_name_shared_by_two_profiles_is_dropped():
    twins = CHILDREN + [{"child_id": "c-mia-2", "name": "Mia  Muster"}]
    entries, withheld = attach_older_rows([OlderAbsenceRow("Mia Muster", "2026-09-14", "2026-09-14")], twins)
    assert entries == []
    assert withheld == 1


class OlderClient:
    def __init__(self, url, pages):
        self.url = url
        self.pages = pages
        self.calls = []
        self.authed = False

    def login(self, username, password, code_provider):
        self.authed = True
        return self

    def is_authenticated(self):
        return self.authed

    def fetch(self, path, params=None):
        self.calls.append(path)
        if path.startswith(modules.DSA_API):
            return Response(403, self.url + path)
        if path in self.pages:
            return Response(200, self.url + path, self.pages[path])
        return Response(404, self.url + path)

    def fetch_or_raise(self, path, params=None):
        response = self.fetch(path, params)
        if response.status_code != 200:
            raise DataError("request failed: %s" % response.status_code)
        return response


def older_service(tmp_path, page=GERMAN_PAGE, children=CHILDREN, client_class=None):
    clients = []

    def factory(url):
        client = (client_class or OlderClient)(url, {"/iserv/": START_PAGE, modules.OLDER_ABSENCE_PATH: page, "/iserv/time-table/": "<html></html>"})
        clients.append(client)
        return client

    store = Store(tmp_path / "data")
    entry = store.add_connection(SCHOOL, setup_complete=True, children=children)
    store.save_secrets(entry["id"], dict(DEFAULT_SECRETS))
    service = IServService(store, client_factory=factory)
    connection = service.known_connection(entry["id"])
    connection.store.save_modules(modules.detect(START_PAGE, clients_fetch(factory, clients), None))
    return service, connection, clients


def clients_fetch(factory, clients):
    probe = factory(SCHOOL)
    clients.remove(probe)
    return lambda path, params=None: probe.fetch(path, params)


def test_detection_makes_the_older_page_the_absences_provider_when_the_school_app_refuses(tmp_path):
    _service, connection, _clients = older_service(tmp_path)
    registry = connection.modules()
    assert registry["modules"][modules.ABSENCES] is True
    assert modules.older_absences(registry) is True
    assert modules.school_app_absences(registry) is False
    assert [entry["slug"] for entry in registry["covered"]] == ["absence_obsolete"]
    assert registry["unsupported"] == []
    assert "absences read from the older page (absence_obsolete)" in modules.summary(registry)


def test_the_older_page_is_not_probed_while_the_school_app_serves_absences():
    calls = []

    def fetch(path, params=None):
        calls.append(path)
        return Response(200, SCHOOL + path, GERMAN_PAGE if path == modules.OLDER_ABSENCE_PATH else "")

    registry = modules.detect(START_PAGE, fetch, None)
    assert modules.OLDER_ABSENCE_PATH not in calls
    assert modules.older_absences(registry) is False
    assert modules.school_app_absences(registry) is True


def test_an_older_page_without_the_list_does_not_count_as_provider():
    def fetch(path, params=None):
        if path.startswith(modules.DSA_API):
            return Response(403, SCHOOL + path)
        return Response(200, SCHOOL + path, "<html><body>Start</body></html>")

    registry = modules.detect(START_PAGE, fetch, None)
    assert registry["modules"][modules.ABSENCES] is False
    assert modules.older_absences(registry) is False
    assert [entry["slug"] for entry in modules.normalize(registry)["unsupported"]] == ["absence_obsolete"]


def test_an_unreachable_school_app_keeps_the_earlier_older_provider():
    def refusing(path, params=None):
        if path.startswith(modules.DSA_API):
            return Response(403, SCHOOL + path)
        return Response(200, SCHOOL + path, GERMAN_PAGE if path == modules.OLDER_ABSENCE_PATH else "")

    def unreachable(path, params=None):
        if path.startswith(modules.DSA_API):
            raise OSError("down")
        return Response(200, SCHOOL + path, "")

    earlier = modules.detect(START_PAGE, refusing, None)
    later = modules.detect(START_PAGE, unreachable, earlier)
    assert modules.older_absences(later) is True


def test_the_overview_reads_the_older_page_and_never_the_school_app(tmp_path):
    service, connection, clients = older_service(tmp_path)
    connection._login()
    for client in clients:
        client.calls.clear()
    overview = service.absences_overview(connection.id)
    assert overview["source"] == OLDER_SOURCE
    assert "open_url" not in overview
    assert overview["withheld"] == 1
    assert [entry["student_id"] for entry in overview["entries"]] == ["c-tom", "c-mia"]
    assert {child["id"] for child in overview["children"]} == {"c-mia", "c-tom"}
    reads = [path for client in clients for path in client.calls]
    assert reads[0] == modules.OLDER_ABSENCE_PATH
    assert len(reads) == 2 and reads[1].startswith(modules.OLDER_ABSENCE_PATH + "?")


def test_an_unreadable_older_page_is_an_error_not_an_empty_list(tmp_path):
    page = '<table id="crud-table"><tr><th>Foo</th><th>Bar</th></tr><tr><td>a</td><td>b</td></tr></table>'
    service, connection, _clients = older_service(tmp_path, page=page)
    assert modules.older_absences(connection.modules()) is True
    with pytest.raises(DataError):
        service.absences_overview(connection.id)


def test_reporting_and_withdrawing_use_the_older_page_without_calling_the_school_app(tmp_path):
    service, connection, clients = older_service(tmp_path)
    connection._login()
    for client in clients:
        client.calls.clear()
    with pytest.raises(DataError):
        service.report_absence(connection.id, {"type": "sick", "student_id": "c-mia"})
    withdrawn = service.delete_absence(connection.id, {"type": "sick", "id": "1"})
    assert withdrawn["ok"] is False and withdrawn["message_key"] == LOCKED_KEY
    reads = [path for client in clients for path in client.calls]
    assert reads and all(path.startswith(modules.OLDER_ABSENCE_PATH) for path in reads)


def test_the_absences_route_serves_the_older_entries(tmp_path):
    service, connection, _clients = older_service(tmp_path)
    app = FastAPI()
    absence_routes.register_routes(app, service)
    body = TestClient(app).get("/api/absences", params={"connection": connection.id}).json()
    assert body["source"] == OLDER_SOURCE
    assert body["connection_id"] == connection.id
    assert [entry["id"] for entry in body["entries"]] == ["older:482", "older:481"]


def test_the_child_list_skips_the_school_app_while_the_older_page_serves_absences(tmp_path):
    _service, connection, _clients = older_service(tmp_path)
    assert connection._child_service._school_app_absences() is False
    assert connection._child_service._children_from_school_app() == []


def test_the_report_names_the_older_page_as_the_absences_source():
    registry = modules.detect(START_PAGE, lambda path, params=None: Response(
        403 if path.startswith(modules.DSA_API) else 200, SCHOOL + path, GERMAN_PAGE if path == modules.OLDER_ABSENCE_PATH else ""
    ), None)
    rows = {row["slug"]: row for row in diagnostics.module_rows(modules.normalize(registry))}
    assert rows["absence"]["status"] == diagnostics.STATUS_MISSING
    assert rows["absence_obsolete"]["status"] == diagnostics.STATUS_OLDER_SOURCE


def test_the_report_shows_known_header_labels_and_the_recognised_columns():
    lines = pageshape.html_skeleton(GERMAN_PAGE)
    assert "- Table headers: Zeitraum | Name | Klasse/Gruppe | Status | Erstellt am" in lines
    assert reportfacts.older_columns_line(GERMAN_PAGE) == "- Older absence columns: period, name, class, status, created"
    assert reportfacts.older_columns_line("<p></p>") == "- Older absence columns: no list table"


class CrawlClient:
    def __init__(self):
        self.read = []

    def fetch_unfollowed(self, path, limit, timeout, expired=None):
        self.read.append(path)
        if path == "/iserv/absence/add":
            return Response(200, SCHOOL + path, ADD_PAGE)
        return Response(404, SCHOOL + path)


def test_the_report_follows_the_add_page_once_and_records_only_its_form_structure():
    client = CrawlClient()
    landing = Response(200, SCHOOL + modules.OLDER_ABSENCE_PATH, GERMAN_PAGE)
    lines = reportcrawl.module_crawl(client, landing, "/iserv/absence/", reportcrawl.menu_shape, {}, "/iserv/")
    assert client.read == ["/iserv/absence/add"]
    text = "\n".join(lines)
    assert "##### Page /iserv/absence/add" in text
    assert "absence[start] (date, required" in text
    assert "absence[student] (select, options 2)" in text
    assert "absence[reason] (textarea)" in text
    assert "POST /iserv/absence/add form 'absence'" in text
    assert "secret-token" not in text
    assert "Mia" not in text and "Muster" not in text


def test_the_crawl_still_refuses_a_detail_or_delete_link_of_the_older_page():
    page = GERMAN_PAGE + '<a href="/iserv/absence/delete">x</a><a href="/iserv/absence/481/edit">y</a>'
    links, skipped = reportcrawl.crawl_links(page, SCHOOL + "/iserv/absence/", "/iserv/absence/", 5, reportcrawl.READ_ROUTES | {"add", "new", "create"}, any_text=True)
    assert [link.path for link in links] == ["/iserv/absence/add"]
    assert skipped.get(reportcrawl.SKIP_PATH) == 1


def test_a_date_column_is_read_in_dd_mm_yy_and_iso_form():
    page = ENGLISH_PAGE.replace("14.09.2026 08:00", "14.09.26").replace("15.09.2026 12:30", "2026-09-15")
    row = parse_older_absences(page).rows[0]
    assert (row.from_date, row.till_date) == ("2026-09-14", "2026-09-15")
    assert date.fromisoformat(row.created) == date(2026, 9, 13)


class NoSchools:
    store = None

    def connections(self):
        return []


def test_older_entries_reach_the_profile_snapshot_that_feeds_home_assistant():
    rows = parse_older_absences(GERMAN_PAGE).rows
    entries, _withheld = attach_older_rows(rows, CHILDREN)
    overview = {"children": [{"id": child["child_id"], "name": child["name"]} for child in CHILDREN], "entries": entries}
    poller = Poller(NoSchools(), clock=lambda: 1_788_000_000)
    snapshot = {}
    wanted = {"s1:c-mia", "s1:c-tom"}
    assert poller._store_absences("s1", snapshot, wanted, CHILDREN, overview) is True
    mia = snapshot["children"]["s1:c-mia"]["absences"]
    assert [(entry["from_date"], entry["till_date"], entry["status"]) for entry in mia] == [("2026-09-14", "2026-09-16", STATUS_ACCEPTED)]
    assert [entry["from_date"] for entry in snapshot["children"]["s1:c-tom"]["absences"]] == ["2026-10-02"]


def test_a_failed_read_of_the_older_page_keeps_the_earlier_provider():
    def refusing(path, params=None):
        if path.startswith(modules.DSA_API):
            return Response(403, SCHOOL + path)
        return Response(200, SCHOOL + path, GERMAN_PAGE if path == modules.OLDER_ABSENCE_PATH else "")

    def older_down(path, params=None):
        if path == modules.OLDER_ABSENCE_PATH:
            raise OSError("down")
        return refusing(path, params)

    earlier = modules.detect(START_PAGE, refusing, None)
    later = modules.detect(START_PAGE, older_down, earlier)
    assert later["modules"][modules.ABSENCES] is True
    assert modules.older_absences(later) is True


FILTERED_PAGE = """<table id="crud-table"><thead><tr><th></th><th>Zeitraum</th><th>Name</th><th>Status</th></tr></thead><tbody>
<tr><td><input type="checkbox" value="301"></td><td>02.03.2026 - 04.03.2026</td><td>Mia Muster</td><td>unentschuldigt</td></tr>
<tr><td><input type="checkbox" value="481"></td><td>14.09.2026 - 16.09.2026</td><td>Muster, Mia</td><td>entschuldigt</td></tr>
</tbody></table>"""
ALL_STATUSES = "filter%5Bstatus%5D%5B%5D=open&filter%5Bstatus%5D%5B%5D=excused&filter%5Bstatus%5D%5B%5D=unexcused"


def test_the_filter_form_asks_for_every_status_and_the_widest_date_range():
    pairs = filter_query(GERMAN_PAGE, modules.OLDER_ABSENCE_PATH, date(2026, 10, 14))
    assert pairs == [
        ("filter[status][]", "open"),
        ("filter[status][]", "excused"),
        ("filter[status][]", "unexcused"),
        ("filter[from]", "2000-01-01"),
        ("filter[to]", (date(2026, 10, 14) + timedelta(days=5 * 366)).isoformat()),
    ]


def test_the_filter_form_keeps_its_date_limits_and_ignores_a_form_that_posts_elsewhere():
    page = ('<form method="get"><select name="filter[status][]"><option value="a">A</option></select>'
            '<input type="date" name="filter[from]" min="2020-08-01"><input type="date" name="filter[to]" max="2027-07-31"></form>')
    assert filter_query(page, modules.OLDER_ABSENCE_PATH, date(2026, 10, 14)) == [
        ("filter[status][]", "a"), ("filter[from]", "2020-08-01"), ("filter[to]", "2027-07-31"),
    ]
    elsewhere = page.replace('method="get"', 'method="get" action="/iserv/absence/delete"')
    assert filter_query(elsewhere, modules.OLDER_ABSENCE_PATH, date(2026, 10, 14)) == []
    assert filter_query(page.replace('method="get"', 'method="post"'), modules.OLDER_ABSENCE_PATH, date(2026, 10, 14)) == []


class FilteringClient(OlderClient):
    def fetch(self, path, params=None):
        if path.startswith(modules.OLDER_ABSENCE_PATH + "?"):
            self.calls.append(path)
            if ALL_STATUSES in path and "filter%5Bfrom%5D=2000-01-01" in path:
                return Response(200, self.url + path, FILTERED_PAGE)
            return Response(200, self.url + path, EMPTY_PAGE)
        return super().fetch(path, params)


def test_entries_only_the_filter_returns_are_shown_next_to_the_default_list(tmp_path):
    service, connection, _clients = older_service(tmp_path, client_class=FilteringClient)
    overview = service.absences_overview(connection.id)
    ids = [entry["id"] for entry in overview["entries"]]
    assert ids == ["older:482", "older:481", "older:301"]
    past = overview["entries"][-1]
    assert (past["from_date"], past["till_date"], past["status"], past["student_id"]) == ("2026-03-02", "2026-03-04", STATUS_REJECTED, "c-mia")


class OlderSchool(School):
    def __init__(self):
        super().__init__()
        self.start_page = START_PAGE

    def get(self, url, params=None, timeout=None, **kwargs):
        path = url[len(REFUSAL_BASE):]
        if path.startswith(modules.OLDER_ABSENCE_PATH):
            self.hits[path.split("?", 1)[0] + ("?" if "?" in path else "")] += 1
            return Answer(200, url, FILTERED_PAGE if "?" in path else GERMAN_PAGE)
        return super().get(url, params=params, timeout=timeout, **kwargs)


def test_each_poll_reads_the_older_page_twice_and_the_refused_school_app_once_a_day(tmp_path):
    school = OlderSchool()
    now = [1_788_000_000.0]
    store = Store(tmp_path / "data")
    entry = store.add_connection(REFUSAL_BASE, setup_complete=True, children=CHILDREN)
    store.save_secrets(entry["id"], dict(DEFAULT_SECRETS))
    service = IServService(store, client_factory=lambda url: SchoolClient(url, session=school))
    connection = service.known_connection(entry["id"])
    connection.clock = lambda: now[0]
    connection.check_connection()
    plain = school.hits[modules.OLDER_ABSENCE_PATH]
    for poll in range(1, 11):
        now[0] += 30 * 60
        connection.refresh_modules()
        overview = connection.absences_overview()
        assert overview["source"] == OLDER_SOURCE
        assert school.hits[modules.OLDER_ABSENCE_PATH] == plain + poll
        assert school.hits[modules.OLDER_ABSENCE_PATH + "?"] == poll
    absence_paths = [path for path in school.hits if path.startswith(modules.DSA_API + "/sickNotes") or "requestToSchools" in path or "user-requests" in path]
    assert absence_paths == [modules.PROBES[modules.ABSENCES][0]]
    assert school.hits[modules.PROBES[modules.ABSENCES][0]] == 1


def test_a_profile_without_a_matched_row_keeps_its_earlier_absences_while_rows_are_withheld():
    rows = parse_older_absences(GERMAN_PAGE).rows
    entries, withheld = attach_older_rows(rows, CHILDREN[:1])
    assert withheld == 2
    overview = {"children": [{"id": child["child_id"], "name": child["name"]} for child in CHILDREN], "entries": entries, "withheld": withheld}
    poller = Poller(NoSchools(), clock=lambda: 1_788_000_000)
    earlier = [{"id": "older:470", "from_date": "2026-09-01", "till_date": "2026-09-01", "status": STATUS_OPEN}]
    snapshot = {"children": {"s1:c-tom": {"absences": list(earlier), "absences_fetched_at": 1_787_000_000}}}
    wanted = {"s1:c-mia", "s1:c-tom", "s1:c-new"}
    children = CHILDREN + [{"child_id": "c-new", "name": "Neu Kind"}]
    assert poller._store_absences("s1", snapshot, wanted, children, overview) is True
    assert [entry["from_date"] for entry in snapshot["children"]["s1:c-mia"]["absences"]] == ["2026-09-14"]
    assert snapshot["children"]["s1:c-tom"] == {"absences": earlier, "absences_fetched_at": 1_787_000_000}
    assert "s1:c-new" not in snapshot["children"]
    poller._store_absences("s1", snapshot, wanted, children, dict(overview, withheld=0))
    assert snapshot["children"]["s1:c-tom"]["absences"] == []
    assert snapshot["children"]["s1:c-new"]["absences"] == []


@pytest.mark.parametrize(
    ("text", "status"),
    [
        ("nicht entschuldigt", STATUS_REJECTED),
        ("Nicht genehmigt", STATUS_REJECTED),
        ("not excused", STATUS_REJECTED),
        ("Not approved", STATUS_REJECTED),
        ("noch nicht entschuldigt", STATUS_OPEN),
        ("not yet approved", STATUS_OPEN),
        ("nicht bearbeitet", STATUS_OPEN),
        ("nicht abgelehnt", ""),
        ("entschuldigt", STATUS_ACCEPTED),
        ("Unentschuldigt", STATUS_REJECTED),
        ("offen", STATUS_OPEN),
    ],
)
def test_a_negated_status_is_not_read_as_accepted(text, status):
    from app.iserv.older_absences import status_of

    assert status_of(text) == status


@pytest.mark.parametrize(
    ("header", "role"),
    [
        ("Art der Abwesenheit", "reason"),
        ("Grund der Abwesenheit", "reason"),
        ("Abwesenheitsart", "reason"),
        ("Typ", "reason"),
        ("Schülername", ROLE_NAME),
        ("Schüler", ROLE_NAME),
        ("Schüler*in", ROLE_NAME),
        ("Student name", ROLE_NAME),
        ("Students", ROLE_NAME),
        ("Name", ROLE_NAME),
        ("Klassenname", ROLE_CLASS),
        ("Zeitraum der Abwesenheit", ROLE_PERIOD),
        ("Beginn der Abwesenheit", ROLE_FROM),
        ("Start", ROLE_FROM),
        ("Status", ROLE_STATUS),
    ],
)
def test_a_header_maps_to_its_precise_role(header, role):
    from app.iserv.older_absences import header_role

    assert header_role(header) == role


def test_a_kind_column_before_the_period_does_not_take_the_dates():
    page = """<table id="crud-table"><thead><tr><th>Art der Abwesenheit</th><th>Zeitraum</th><th>Schülername</th></tr></thead>
<tbody><tr><td>Krankheit</td><td>14.09.2026 - 15.09.2026</td><td>Mia Muster</td></tr></tbody></table>"""
    row = parse_older_absences(page).rows[0]
    assert (row.name, row.from_date, row.till_date, row.reason) == ("Mia Muster", "2026-09-14", "2026-09-15", "Krankheit")


TIMED_ROWS_PAGE = """<table id="crud-table"><thead><tr><th>Name</th><th>Von</th><th>Bis</th><th>Status</th></tr></thead><tbody>
<tr><td>Mia Muster</td><td>14.09.2026 08:00</td><td>14.09.2026 09:30</td><td>offen</td></tr>
<tr><td>Mia Muster</td><td>14.09.2026 11:00</td><td>14.09.2026 12:30</td><td>offen</td></tr>
<tr><td>Mia Muster</td><td>15.09.2026</td><td>15.09.2026</td><td>offen</td></tr>
<tr><td>Mia Muster</td><td>15.09.2026</td><td>15.09.2026</td><td>entschuldigt</td></tr>
</tbody></table>"""


def test_rows_without_an_id_stay_distinct_and_the_default_list_duplicate_still_merges():
    from app.iserv.older_absences import merged_rows

    listed = parse_older_absences(TIMED_ROWS_PAGE)
    merged = merged_rows(listed, parse_older_absences(TIMED_ROWS_PAGE))
    assert len(merged.rows) == 4
    first_only = TIMED_ROWS_PAGE.split("<tr><td>Mia Muster</td><td>14.09.2026 11:00")[0] + "</tbody></table>"
    assert len(merged_rows(parse_older_absences(first_only), listed).rows) == 4
    entries, withheld = attach_older_rows(merged.rows, CHILDREN)
    assert withheld == 0
    ids = [entry["id"] for entry in entries]
    assert len(set(ids)) == 4
    assert ids[0] == "older:c-mia:2026-09-14:2026-09-14:08:00-09:30"
    assert ids[2] == "older:c-mia:2026-09-15:2026-09-15"
    assert [(entry["from_time"], entry["status"]) for entry in entries] == [
        ("08:00", STATUS_OPEN), ("11:00", STATUS_OPEN), ("", STATUS_OPEN), ("", STATUS_ACCEPTED),
    ]
