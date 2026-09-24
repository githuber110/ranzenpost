import io
import json
import logging
import random
import string
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import diagnostics, logfile, modules, namebook, valueshape, vocabulary
from app.poller import Poller
from app.server import create_app
from app.service import ConnectionService
from app.store import Store
from tests.support import add_school
from tests.test_diagnostics import (
    CHILD_ONE,
    PASSWORD,
    SCHOOL_ONE_URL,
    TEACHER,
    TOTP,
    USER_ONE,
    Client,
    Connection,
    Response,
    Service,
    build,
    registry_for,
    two_school_service,
)
from tests.test_no_personal_data import line_contains_forbidden_token

PLANTED = (
    "Mia Musterkind",
    "Musterkind",
    "Beispielsohn",
    "parent.one@family.example",
    "lehrerin@schule.example",
    "+49 170 1234567",
    "0170 1234567",
    "01701234567",
    "DE89 3704 0044 0532 0130 00",
    "DE89370400440532013000",
    "Hauptstraße 12",
    "12345 Musterstadt",
    "Musterstadt",
    "Frau Lehrerin",
    "Liebe Eltern, morgen faellt Sport aus.",
)
PLANTED_TOKENS = (
    "Musterkind", "Beispielsohn", "family.example", "schule.example", "lehrerin", "1234567", "0532",
    "370400440532013000", "Hauptstraße", "Musterstadt", "faellt", "morgen",
)
SCALARS = (0, 7, -3, 2.5, -0.5, True, False, None, "", "abc", "12345", "05.03.", "2026-03-05", "2026-03-05T10:00:00+02:00", "08:15")


def assert_clean(text):
    lowered = text.lower()
    for word in PLANTED + tuple(PLANTED_TOKENS):
        assert word.lower() not in lowered, word


def random_key(rng):
    choice = rng.random()
    if choice < 0.35:
        return rng.choice(PLANTED)
    if choice < 0.5:
        return str(rng.randint(1, 999999))
    return "".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(1, 8)))


def random_value(rng, depth):
    roll = rng.random()
    if depth >= 4 or roll < 0.35:
        return rng.choice(PLANTED + SCALARS + ("/iserv/file/-/" + rng.choice(PLANTED) + ".pdf", "https://school.example/iserv/profile/" + rng.choice(PLANTED)))
    if roll < 0.7:
        return {random_key(rng): random_value(rng, depth + 1) for _ in range(rng.randint(0, 5))}
    return [random_value(rng, depth + 1) for _ in range(rng.randint(0, 4))]


@pytest.mark.parametrize(
    ("value", "shape"),
    [
        (None, "null"),
        (True, "boolean"),
        (12, "int >0"),
        (0, "int 0"),
        (-4, "int <0"),
        (1.5, "float >0"),
        (-0.25, "float <0"),
        ("", "string len 0, blank"),
        ("4711", "string len 4, digits"),
        ("Mathe", "string len 5, letters"),
        ("3b", "string len 2, alphanumeric"),
        ("05.03.", "string len 6, date DD.MM."),
        ("05.03.2026", "string len 10, date DD.MM.YYYY"),
        ("2026-03-05", "string len 10, iso date"),
        ("2026-03-05T08:15:00+01:00", "string len 25, iso datetime"),
        ("08:15", "string len 5, time HH:MM"),
        ("10000000-0000-4000-8000-000000000001", "string len 36, uuid"),
        ("parent.one@family.example", "string len 25, email"),
        ("/iserv/parentletter/parent/show/10000000-0000-4000-8000-000000000001", "string len 68, path /iserv/parentletter/parent/show/<uuid>"),
        ("https://school.example/iserv/file/-/Mia Musterkind.pdf?x=1", "string len 58, url, path /iserv/file/-/<file>.pdf +query"),
        ("#a1b2c3", "string len 7, colour"),
        ("Liebe Eltern, morgen faellt Sport aus.", "string len 38, free text"),
        ("zeile eins\nzeile zwei", "string len 21, multi-line text"),
        ([], "array len 0"),
        ([{"a": 1}, {"a": 2}], "array len 2 of object"),
        (["x", "y", "z"], "array len 3 of string"),
        ({"a": 1, "b": 2}, "object keys 2"),
    ],
)
def test_every_value_is_reduced_to_its_shape(value, shape):
    assert valueshape.value_shape(value) == shape


def test_the_shape_lines_walk_objects_and_the_first_array_element_with_masked_keys():
    data = {
        "items": [{"id": 3, "title": "Elternbrief", "Mia Musterkind": 1, "Musterkind": {"x": None}, "4711": True}],
        "matrix.room_id": "!abc:school.example",
        "empty": [],
    }
    assert valueshape.shape_lines(data) == [
        "(root): object keys 3",
        "items: array len 1 of object",
        "items[]: object keys 5",
        "items[].id: int >0",
        "items[].title: string len 11, letters",
        "items[].<key>: int >0",
        "items[].<word>: object keys 1",
        "items[].<word>.x: null",
        "items[].<n>: boolean",
        "matrix.room_id: string len 19, free text",
        "empty: array len 0",
    ]


def test_link_shapes_keep_routes_and_hide_ids_files_and_name_like_segments():
    assert valueshape.link_shape("/iserv/dieschulapp/api/1.0/sickNotes/userSelection/") == "/iserv/dieschulapp/api/1.0/sickNotes/userSelection/"
    assert valueshape.link_shape("/iserv/parentletter/parent/show/10000000-0000-4000-8000-000000000001") == "/iserv/parentletter/parent/show/<uuid>"
    assert valueshape.link_shape("/iserv/profile/public/mia.musterkind") == "/iserv/profile/public/<seg>"
    assert valueshape.link_shape("/iserv/user/Musterkind") == "/iserv/user/<seg>"
    assert valueshape.link_shape("/iserv/file/-/Brief an Mia.pdf") == "/iserv/file/-/<file>.pdf"
    assert valueshape.link_shape("/iserv/x/12") == "/iserv/x/<n>"


def test_fuzzed_json_with_planted_personal_data_never_leaks_a_value():
    rng = random.Random(298)
    for _ in range(400):
        document = random_value(rng, 0)
        lines = valueshape.shape_lines(document)
        assert lines
        assert_clean("\n".join(lines))


def test_the_shape_walk_is_capped_and_says_so():
    wide = {"key_%d" % index: index for index in range(valueshape.MAX_LINES + 50)}
    block = diagnostics.shape_block(wide)
    assert len(block) == valueshape.MAX_LINES + 1
    assert block[-1] == "  - cut after %d keys" % valueshape.MAX_LINES


def fuzz_pages(rng):
    person = rng.choice(PLANTED)
    json_body = random_value(rng, 0)
    html = (
        "<html><body><nav id='main'><a href='/iserv/profile/public/{slug}'>{person}</a>"
        "<a href='/iserv/file/-/{person}.pdf'>{person}</a></nav>"
        "<form action='/iserv/x/save' method='post'><input name='title' value='{person}'>"
        "<select name='child'><option value='1'>{person}</option></select><textarea name='body'>{person}</textarea></form>"
        "<table><tr><th>Datum</th></tr><tr><td>{person}</td></tr></table>"
        "<script type='application/json' id='php-data'>{data}</script>"
        "<p>{person}</p></body></html>"
    ).format(person=person, slug=person.replace(" ", "."), data=json.dumps(json_body))
    return html, json_body


def test_a_fuzzed_report_over_planted_pages_and_json_never_leaks_a_value(tmp_path):
    rng = random.Random(2980)
    for round_index in range(12):
        store = Store(tmp_path / ("fuzz%d" % round_index))
        one = add_school(store, SCHOOL_ONE_URL, secrets={"username": USER_ONE, "password": PASSWORD, "totp_secret": TOTP},
                         children=[{"child_id": "4711", "name": CHILD_ONE, "class_name": "3b"}])
        html, json_body = fuzz_pages(rng)
        pages = {
            "/iserv/time-table/data": Response(200, SCHOOL_ONE_URL + "/iserv/time-table/data", json.dumps(json_body), "application/json", json_data=json_body),
            "/iserv/": Response(200, SCHOOL_ONE_URL + "/iserv/x", html),
        }
        client = Client(SCHOOL_ONE_URL, pages)
        registry = registry_for(SCHOOL_ONE_URL, pages)
        service = Service(store, [Connection(store, one, client, registry, {"has_2nd_factor_active": True})])
        report = build(service, structure=True, log_lines=[])
        assert "- JSON value shapes:" in report
        assert "- Embedded JSON #php-data:" in report
        assert_clean(report)


def test_the_embedded_json_of_a_page_is_shown_as_shapes():
    html = '<script type="application/json" id="php-data">{"messenger_authentication": null, "messenger_routing_basepath": "/iserv/messenger"}</script><script type="application/json">{oops</script>'
    lines = diagnostics.html_skeleton(html)
    assert "- Embedded JSON #php-data:" in lines
    assert "  - messenger_authentication: null" in lines
    assert "  - messenger_routing_basepath: string len 16, path /iserv/messenger" in lines
    assert "- Embedded JSON (no id): unreadable" in lines


def test_the_redactor_covers_names_hosts_mails_phones_tokens_and_keeps_the_rest():
    words = diagnostics.RedactionWords(
        children=["Mia Musterkind"], schools=["Gymnasium Nord"], teachers=["Frau Lehrerin"],
        users=["parent.one"], hosts=["gymnasium-nord.example"], secrets=["SuperSecretPass1"], phones=["0511 123456"],
    )
    redactor = diagnostics.Redactor(words)
    line = "Mia at gymnasium-nord.example, parent.one mailed x@y.example Bearer abc.def IServSession=zzz; call 0511 123456 SuperSecretPass1 Gymnasium Nord Lehrerin"
    redacted = redactor(line)
    for word in ("Mia", "gymnasium-nord", "parent.one", "x@y.example", "abc.def", "zzz", "0511 123456", "SuperSecretPass1", "Gymnasium Nord", "Lehrerin"):
        assert word not in redacted, word
    assert "<phone>" in redacted and "<child>" in redacted and "<teacher>" in redacted and "<school>" in redacted
    assert "mailed" in redacted and "call" in redacted
    assert redactor(line) == diagnostics.redact(line, words)
    assert diagnostics.scrub_line("mail a@b.example token=abc") == "mail <email> token=<secret>"


def test_the_redactor_handles_a_long_log_in_one_pass():
    words = diagnostics.RedactionWords(children=["Mia Musterkind"], users=["parent.one"])
    log = "\n".join("2026-09-19 10:00:%02d,000 INFO app.poller: poll of Mia for parent.one line %d" % (index % 60, index) for index in range(20000))
    redacted = diagnostics.Redactor(words)(log)
    assert "Mia" not in redacted
    assert "parent.one" not in redacted
    assert redacted.count("\n") == 19999


def file_logger(tmp_path, name, max_bytes=2000, backups=3):
    target = logging.getLogger(name)
    target.propagate = False
    target.setLevel(logging.INFO)
    handler = logfile.install(tmp_path, scrub=diagnostics.scrub_line, target=target, max_bytes=max_bytes, backups=backups)
    return target, handler


def test_the_log_file_rotates_within_its_limit_and_reads_back_oldest_first(tmp_path):
    target, handler = file_logger(tmp_path, "rotation-test")
    try:
        for index in range(400):
            target.info("line %04d of the rotation test", index)
        paths = logfile.files(handler)
        assert len(paths) == 4
        assert all(path.stat().st_size <= 2000 + 100 for path in paths)
        lines = logfile.lines(handler)
        numbers = [int(line.rsplit("line ", 1)[1].split()[0]) for line in lines]
        assert numbers == sorted(numbers)
        assert numbers[-1] == 399
        assert numbers[0] > 0
        assert logfile.capacity(handler) == (4, 2000)
    finally:
        target.removeHandler(handler)
        handler.close()


def test_the_default_log_keeps_about_twenty_megabytes():
    assert (logfile.BACKUPS + 1) * logfile.MAX_BYTES == 20 * 1024 * 1024


def test_the_log_file_scrubs_mails_tokens_and_hosts_when_it_writes(tmp_path):
    target, handler = file_logger(tmp_path, "scrub-test", max_bytes=100000)
    try:
        target.info("login of parent.one@family.example at https://gymnasium-nord.example/iserv with Bearer abc.def")
        text = (tmp_path / logfile.DIR_NAME / logfile.FILE_NAME).read_text(encoding="utf-8")
        assert "family.example" not in text
        assert "gymnasium-nord" not in text
        assert "abc.def" not in text
        assert "<email>" in text and "https://<host>" in text and "Bearer <secret>" in text
    finally:
        target.removeHandler(handler)
        handler.close()


def test_every_start_is_marked_and_a_new_version_is_marked_as_a_change(tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="timeline"):
        logfile.mark_start(lambda: "2609.01.33", tmp_path)
        logfile.mark_start(lambda: "2609.01.33", tmp_path)
        logfile.mark_start(lambda: "2609.02.00", tmp_path)
        logfile.mark_start(lambda: (_ for _ in ()).throw(RuntimeError("no supervisor")), tmp_path)
    messages = [record.getMessage() for record in caplog.records if record.name == "timeline"]
    assert messages == [
        "=== add-on start, version 2609.01.33 ===",
        "=== add-on start, version 2609.01.33 ===",
        "=== add-on start, version 2609.02.00 ===",
        "=== version change 2609.01.33 -> 2609.02.00 ===",
        "=== add-on start, version unknown ===",
    ]
    assert (tmp_path / logfile.DIR_NAME / logfile.VERSION_FILE).read_text(encoding="utf-8") == "2609.02.00"


TIMELINE = [
    "2026-09-01 08:00:00,000 INFO timeline: === add-on start, version 2609.01.33 ===",
    "2026-09-01 08:30:00,000 INFO timeline: poll start: 1 schools (all)",
    "2026-09-01 08:30:02,000 INFO timeline: poll end after 2000ms: 1 schools, 0 errors, 0 changes",
    "  Traceback line without a stamp",
    "2026-09-20 07:00:00,000 INFO timeline: === add-on start, version 2609.02.00 ===",
    "2026-09-20 07:00:00,100 INFO timeline: === version change 2609.01.33 -> 2609.02.00 ===",
    "2026-09-20 07:05:00,000 INFO app.service: login of Mia Musterkind for parent.one@family.example",
]


def test_the_log_header_names_the_covered_range_starts_and_version_changes():
    summary = logfile.summarize(TIMELINE)
    assert summary["first"] == "2026-09-01 08:00:00"
    assert summary["last"] == "2026-09-20 07:05:00"
    header = logfile.header(summary)
    assert header[:3] == ["# Ranzenpost log", "- Covered: 2026-09-01 08:00:00 to 2026-09-20 07:05:00", "- Lines: 7"]
    assert "- Add-on starts: 2" in header
    assert "  - 2026-09-01 08:00:00 start, version 2609.01.33" in header
    assert "- Version changes: 1" in header
    assert "  - 2026-09-20 07:00:00 2609.01.33 -> 2609.02.00" in header
    assert logfile.covered_line(logfile.summarize([])) == "- Covered: no timestamped lines"


def open_bundle(content):
    archive = zipfile.ZipFile(io.BytesIO(content))
    assert sorted(archive.namelist()) == [diagnostics.LOG_FILE, diagnostics.REPORT_FILE]
    return archive.read(diagnostics.REPORT_FILE).decode("utf-8"), archive.read(diagnostics.LOG_FILE).decode("utf-8")


def test_the_bundle_holds_the_report_and_the_whole_redacted_log(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    long_log = TIMELINE + ["2026-09-20 08:%02d:00,000 INFO app.poller: filler %d for %s" % (index % 60, index, TEACHER) for index in range(400)]
    content = diagnostics.build_bundle(service, log_lines=long_log, clock=lambda: 1_788_000_000, versions={"app": "2609.02.00", "home_assistant": "2026.9.1"})
    report, log = open_bundle(content)
    assert report.startswith("# Ranzenpost report")
    assert "- Full log: log.txt in ranzenpost-report.zip" in report
    assert "- Lines: 407" in report
    assert "- Shown below: the last %d lines" % diagnostics.REPORT_LOG_TAIL in report
    assert "- Covered: 2026-09-01 08:00:00 to 2026-09-20 08:39:00" in report
    assert log.startswith("# Ranzenpost log\n- Covered: 2026-09-01 08:00:00 to 2026-09-20 08:39:00\n- Lines: 407\n")
    assert "  - 2026-09-20 07:00:00 2609.01.33 -> 2609.02.00" in log
    assert "poll end after 2000ms" in log
    assert "filler 399" in log and "filler 0 " in log
    for text in (report, log):
        lowered = text.lower()
        for word in ("musterkind", "family.example", "lehrerin", "gymnasium-nord"):
            assert word not in lowered, word
        for number, line in enumerate(text.splitlines(), 1):
            assert not line_contains_forbidden_token(line.lower()), f"line {number}"


def test_the_zip_endpoint_serves_a_download_and_reuses_the_report_it_just_built(tmp_path):
    service, first, _second = two_school_service(tmp_path)
    client = TestClient(create_app(service))
    body = client.get("/api/diagnostics").json()
    assert set(body["facts"]) == {"app", "home_assistant", "iserv"}
    assert body["facts"]["iserv"] == "3.9.1"
    fetched = len(first.client.capped_calls)
    answer = client.get("/api/diagnostics/report.zip")
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "application/zip"
    assert answer.headers["content-disposition"] == 'attachment; filename="ranzenpost-report.zip"'
    assert "no-store" in answer.headers["cache-control"]
    report, log = open_bundle(answer.content)
    assert report == body["report"]
    assert log.startswith("# Ranzenpost log")
    assert len(first.client.capped_calls) == fetched


def test_the_report_cache_rebuilds_when_it_is_stale_or_asked_for_another_scope(tmp_path):
    service, first, _second = two_school_service(tmp_path)
    now = [1_788_000_000]
    cache = diagnostics.ReportCache(clock=lambda: now[0], max_age=60)
    cache.build(service)
    reads = len(first.client.capped_calls)
    cache.bundle(service)
    assert len(first.client.capped_calls) == reads
    now[0] += 61
    cache.bundle(service)
    assert len(first.client.capped_calls) > reads
    reads = len(first.client.capped_calls)
    cache.bundle(service, module="letters")
    report, _log = open_bundle(cache.bundle(service, module="letters"))
    assert "- Structure module: letters" in report


def test_both_timetable_paths_are_read_with_status_skeleton_and_the_own_child(tmp_path):
    service, first, _second = two_school_service(tmp_path)
    data = {"entries": [{"subject": "D", "start": "08:00"}]}
    first.client.pages = dict(
        {"/iserv/time-table/data": Response(200, SCHOOL_ONE_URL + "/iserv/time-table/data", "{}", "application/json", json_data=data)},
        **first.client.pages,
    )
    first.client.pages["/iserv/timetable/"] = Response(200, SCHOOL_ONE_URL + "/iserv/timetable/", "<html><form action='/iserv/timetable/' method='get'><select name='child'></select></form></html>")
    calls = []
    fetch = first.client.fetch

    def recording(path, params=None):
        calls.append((path, params))
        return fetch(path, params)

    first.client.fetch = recording
    report = build(service, structure=True)
    assert "#### timetable (Stundenplan (veraltet))" in report
    assert "#### timetable-legacy (Stundenplan (veraltet))" in report
    legacy = report.split("#### timetable-legacy (", 1)[1].split("\n#### ", 1)[0]
    assert "- Page: /iserv/timetable/ -> 200 text/html" in legacy
    assert "- Form: /iserv/timetable/ (get)" in legacy
    assert "- Page: /iserv/timetable/data -> " in legacy
    modern = report.split("#### timetable (", 1)[1].split("\n#### ", 1)[0]
    assert "- Page: /iserv/time-table/ -> 403" in modern
    assert "- Page: /iserv/time-table/data -> 200 application/json" in modern
    assert "  - entries[].start: string len 5, time HH:MM" in modern
    data_calls = [params for path, params in calls if path.endswith("/data")]
    assert len(data_calls) == 2
    assert all(params["childId"] == "4711" for params in data_calls)
    assert "4711" not in report


def test_the_report_names_has_2fa_for_every_connection(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    report = build(service, structure=False)
    assert "- Two-factor: has_2fa=yes, totp stored=yes, IServ says=yes" in report
    assert "- Two-factor: has_2fa=no, totp stored=no, IServ says=unknown" in report


def test_a_school_without_the_timetable_we_read_lists_the_old_module_as_present_but_not_supported():
    pages = {
        "/iserv/time-table/": Response(404, SCHOOL_ONE_URL + "/iserv/time-table/", ""),
        modules.LEGACY_TIMETABLE_PATH: Response(200, SCHOOL_ONE_URL + modules.LEGACY_TIMETABLE_PATH, "<html>plan</html>"),
    }
    registry = registry_for(SCHOOL_ONE_URL, pages)
    assert registry["modules"][modules.TIMETABLE] is False
    entry = next(entry for entry in registry["unsupported"] if entry["segment"] == "timetable")
    assert entry["slug"] == "timetable"
    assert entry["name"] == "Stundenplan (veraltet)"
    assert registry["probes"][modules.LEGACY_TIMETABLE]["status"] == 200
    assert modules.normalize(registry)["probes"][modules.LEGACY_TIMETABLE]["verdict"] == modules.AVAILABLE
    assert "not supported: 2 (calendar, timetable)" in modules.summary(registry)
    rows = diagnostics.module_rows(modules.normalize(registry))
    legacy = next(row for row in rows if row["slug"] == diagnostics.LEGACY_TIMETABLE)
    assert legacy["status"] == diagnostics.STATUS_UNSUPPORTED
    assert legacy["name"] == "Stundenplan (veraltet)"
    assert legacy["edition"] == "obsolete"
    assert [row["slug"] for row in rows].count("timetable") == 1


def test_a_school_whose_timetable_we_read_keeps_its_states_and_never_probes_the_old_path():
    requested = []
    pages = {
        modules.LEGACY_TIMETABLE_PATH: Response(200, SCHOOL_ONE_URL + modules.LEGACY_TIMETABLE_PATH, "<html>plan</html>"),
        "/iserv/time-table/": Response(200, SCHOOL_ONE_URL + "/iserv/time-table/", "<html>ok</html>"),
    }

    def fetch(path, params=None):
        requested.append(path)
        for prefix, response in pages.items():
            if path.startswith(prefix):
                return response
        return Response(404, SCHOOL_ONE_URL + path, "")

    registry = modules.detect("<html></html>", fetch, None, clock=lambda: 1_788_000_000)
    assert registry["modules"][modules.TIMETABLE] is True
    assert modules.LEGACY_TIMETABLE_PATH not in requested
    assert modules.LEGACY_TIMETABLE not in registry["probes"]
    assert registry["unsupported"] == []
    rows = diagnostics.module_rows(modules.normalize(registry))
    assert next(row for row in rows if row["slug"] == diagnostics.LEGACY_TIMETABLE)["status"] == diagnostics.STATUS_NOT_PROBED


def test_a_school_without_either_timetable_stays_missing_without_an_extra_entry():
    registry = registry_for(SCHOOL_ONE_URL, {"/iserv/time-table/": Response(404, SCHOOL_ONE_URL + "/iserv/time-table/", "")})
    assert registry["modules"][modules.TIMETABLE] is False
    assert registry["probes"][modules.LEGACY_TIMETABLE]["verdict"] == modules.MISSING
    assert [entry["segment"] for entry in registry["unsupported"]] == ["calendar"]
    legacy = next(row for row in diagnostics.module_rows(modules.normalize(registry)) if row["slug"] == diagnostics.LEGACY_TIMETABLE)
    assert legacy["status"] == diagnostics.STATUS_MISSING


def test_the_registry_history_records_every_change_and_version_and_the_report_lists_it(tmp_path):
    store = Store(tmp_path)
    one = add_school(store, SCHOOL_ONE_URL, secrets={"username": USER_ONE, "password": PASSWORD})
    service = ConnectionService(store.connection_store(one))
    first = dict(modules.default_registry(), checked_at=1_788_000_000, iserv_version="3.9.1")
    service._store_registry(first)
    service._store_registry(dict(first, checked_at=1_788_000_100))
    second = dict(first, checked_at=1_788_000_200, modules=dict(first["modules"], letters=False))
    service._store_registry(second)
    service._store_registry(dict(second, checked_at=1_788_000_300, iserv_version="3.10.0"))
    history = modules.history_of(store.connection_store(one).load_modules())
    assert [entry["at"] for entry in history] == [1_788_000_000, 1_788_000_200, 1_788_000_300]
    assert "missing: letters" in history[1]["summary"]
    assert history[2]["iserv_version"] == "3.10.0"
    assert modules.normalize(store.connection_store(one).load_modules()).keys() == modules.default_registry().keys()
    lines = diagnostics.history_lines(Connection(store, one, None, second))
    assert lines[:2] == ["### Registry history", "- Entries: 3"]
    assert lines[3].endswith("IServ 3.9.1: " + history[1]["summary"])
    many = {"history": [{"at": index, "summary": "s"} for index in range(1, 50)]}
    assert len(modules.history_of(many)) == modules.HISTORY_LIMIT


class EmptyService:
    store = None

    def connections(self):
        return []


def test_every_poll_logs_a_start_and_an_end_line_with_its_duration(caplog):
    with caplog.at_level(logging.INFO, logger="timeline"):
        Poller(EmptyService(), clock=lambda: 1_788_000_000).poll_once()
        Poller(EmptyService(), clock=lambda: 1_788_000_000).poll_once(connection_id="abc")
    lines = [record.getMessage() for record in caplog.records if record.name == "timeline"]
    assert lines[0] == "poll start: 0 schools (all)"
    assert lines[1].startswith("poll end after ") and lines[1].endswith("ms: 0 schools, 0 errors, 0 changes")
    assert lines[2] == "poll start: 0 schools (school#abc)"
    assert lines[3].startswith("poll end after ")


FORMER_NAMES = ("Mia Musterkind", "Tom Beispielsohn", "Jürgen Müller-Lüdenscheid", "Frau Lehrerin", "Ayşe Yılmaz")
FORMER_TOKENS = (
    "mia", "musterkind", "tom", "beispielsohn", "jürgen", "juergen", "jurgen", "müller", "mueller", "muller",
    "lüdenscheid", "luedenscheid", "ludenscheid", "frau", "lehrerin", "ayşe", "ayse", "yılmaz", "yilmaz",
)


def output_tokens(text):
    return {token.casefold() for token in vocabulary.TOKEN.findall(text)}


def assert_no_former_name(text):
    leaked = output_tokens(text) & set(FORMER_TOKENS)
    assert leaked == set(), leaked
    lowered = text.casefold()
    for token in FORMER_TOKENS:
        if len(token) >= 5:
            assert token not in lowered, token


def name_forms(name):
    parts = name.split()
    forms = [name, name.lower(), "-".join(parts).lower(), "_".join(parts).lower(), ".".join(parts).lower(), parts[-1].lower(), parts[0].lower()]
    folded = name.lower().replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")
    forms.extend([folded, folded.replace(" ", "-"), name.upper()])
    return forms


def test_the_name_book_matches_folded_split_and_cased_tokens_and_keeps_route_words(tmp_path):
    book = namebook.NameBook(tmp_path / "namebook.json")
    book.learn(["Jürgen Müller-Lüdenscheid", "IServ Gymnasium"], ["3b"], ["https://gymnasium-nord.example"])
    for token in ("Jürgen", "juergen", "JURGEN", "müller", "Mueller", "muller", "lüdenscheid", "3B", "nord", "gymnasium"):
        assert book.knows(token), token
    for token in ("iserv", "example", "timetable", "time", "parent", "de", "12"):
        assert not book.knows(token), token
    assert book.mask("/iserv/x/juergen-mueller and key mueller_x at 3b") == "/iserv/x/<name>-<name> and key <name>_x at <name>"
    stored = (tmp_path / "namebook.json").read_text(encoding="utf-8").casefold()
    for plain in ("jürgen", "juergen", "müller", "mueller", "nord"):
        assert plain not in stored
    again = namebook.NameBook(tmp_path / "namebook.json")
    assert again.salt == book.salt
    assert again.knows("Müller")
    other = namebook.NameBook(tmp_path / "elsewhere.json")
    assert other.salt != book.salt
    assert not other.knows("Müller")


def test_the_name_book_follows_the_config_file_and_keeps_names_after_they_are_removed(tmp_path):
    store = Store(tmp_path)
    one = add_school(store, SCHOOL_ONE_URL, children=[{"child_id": "4711", "name": "Mia Musterkind", "class_name": "3b"}],
                     teachers={"LEH": {"label": "Frau Lehrerin", "surname": "Lehrerin"}}, school_name="Gymnasium Nord")
    now = [0.0]
    book = namebook.NameBook(tmp_path / namebook.FILE_NAME, store.config_path, clock=lambda: now[0])
    assert book.scrub("poll for Mia and Lehrerin at nord") == "poll for <name> and <name> at <name>"
    store.update_connection(one, children=[{"child_id": "4712", "name": "Tom Beispielsohn", "class_name": "1a"}])
    now[0] += namebook.REFRESH_SECONDS + 1
    assert book.scrub("Tom and Mia") == "<name> and <name>"
    restarted = namebook.NameBook(tmp_path / namebook.FILE_NAME, store.config_path)
    assert restarted.mask("mia tom beispielsohn musterkind") == "<name> <name> <name> <name>"


def test_the_log_file_already_masks_names_the_store_knows_when_it_writes(tmp_path, monkeypatch):
    store = Store(tmp_path)
    add_school(store, SCHOOL_ONE_URL, children=[{"child_id": "4711", "name": "Mia Musterkind", "class_name": "3b"}])
    monkeypatch.setattr(namebook, "BOOK", None)
    namebook.install(tmp_path, store)
    target, handler = file_logger(tmp_path, "names-at-write", max_bytes=100000)
    try:
        target.info("timetable of Mia Musterkind (3b) read for parent.one@family.example")
        text = (tmp_path / logfile.DIR_NAME / logfile.FILE_NAME).read_text(encoding="utf-8")
        assert "Mia" not in text and "Musterkind" not in text and "3b" not in text
        assert "timetable of <name> <name> (<name>) read for <email>" in text
    finally:
        target.removeHandler(handler)
        handler.close()


def test_visible_texts_keep_iserv_words_and_mask_everything_else():
    assert diagnostics.visible_text("Titel | Kind | Absender 05.03.2026") == "Titel | Kind | Absender <date>"
    assert diagnostics.visible_text("Stunde 1 Montag") == "Stunde 1 Montag"
    assert diagnostics.visible_text("Ergebnis von mia musterkind") == "<word> von <word> <word>"
    assert diagnostics.code_text("main-nav Musterkind childId") == "main-nav <word> childId"


def test_hyphenated_name_like_segments_and_keys_are_masked_unless_they_are_route_words():
    assert valueshape.link_shape("/iserv/x/mia-musterkind") == "/iserv/x/<seg>"
    assert valueshape.link_shape("/iserv/time-table/data") == "/iserv/time-table/data"
    assert valueshape.link_shape("/iserv/dsa-pinboard/") == "/iserv/dsa-pinboard/"
    assert valueshape.safe_key("mia-musterkind") == "<key>"
    assert valueshape.safe_key("time-table") == "time-table"


def former_name_school(tmp_path):
    store = Store(tmp_path)
    one = add_school(
        store, SCHOOL_ONE_URL, secrets={"username": USER_ONE, "password": PASSWORD},
        children=[{"child_id": "4711", "name": name, "class_name": "3b"} for name in FORMER_NAMES[:3]],
        teachers={"LEH": {"label": FORMER_NAMES[3], "surname": "Lehrerin"}, "YIL": {"label": FORMER_NAMES[4]}},
    )
    book = namebook.NameBook(tmp_path / namebook.FILE_NAME)
    book.learn_store(store)
    old_lines = []
    for index, name in enumerate(FORMER_NAMES):
        for form in name_forms(name):
            old_lines.append("2026-09-0%d 10:00:%02d,000 INFO app.poller: timetable of %s read" % (index + 1, len(old_lines) % 60, form))
            old_lines.append("2026-09-0%d 10:01:%02d,000 INFO iserv: timetable GET /iserv/x/%s/data 200" % (index + 1, len(old_lines) % 60, form.replace(" ", "-")))
    store.update_connection(one, children=[{"child_id": "4799", "name": "Ida Neu", "class_name": "1a"}], teachers={})
    return store, one, book, old_lines


def former_name_pages(rng):
    names = [form for name in FORMER_NAMES for form in name_forms(name)]
    rng.shuffle(names)
    data = {form.replace(" ", "_"): {"href": "/iserv/profile/%s" % form.replace(" ", "-"), form.lower(): random_value(rng, 2)} for form in names[:12]}
    data["items"] = [{names[12].lower(): names[13], "url": "/iserv/file/-/%s/%s.pdf" % (names[14].replace(" ", "-"), names[15])}]
    headers = "".join("<th>%s</th>" % form for form in names[16:22])
    links = "".join('<a href="/iserv/profile/public/%s">x</a>' % form.replace(" ", "-") for form in names[22:28])
    html = (
        '<html><body><nav id="%s" class="%s">%s</nav><table><tr>%s</tr></table>'
        '<form action="/iserv/x/%s" method="post" id="%s"><input name="%s"></form>'
        '<script type="application/json" id="%s">%s</script></body></html>'
    ) % (names[28].replace(" ", "-"), names[29].replace(" ", "_"), links, headers, names[30].replace(" ", "-"),
         names[31].replace(" ", "-"), names[32].replace(" ", "_"), names[33].replace(" ", "-"), json.dumps(data))
    return html, data


def test_fuzzed_names_that_the_store_no_longer_knows_never_reach_report_or_log(tmp_path):
    rng = random.Random(29802)
    for round_index in range(6):
        store, one, book, old_lines = former_name_school(tmp_path / ("round%d" % round_index))
        html, data = former_name_pages(rng)
        pages = {
            "/iserv/time-table/data": Response(200, SCHOOL_ONE_URL + "/iserv/time-table/data", json.dumps(data), "application/json", json_data=data),
            "/iserv/": Response(200, SCHOOL_ONE_URL + "/iserv/x", html),
        }
        client = Client(SCHOOL_ONE_URL, pages)
        registry = registry_for(SCHOOL_ONE_URL, pages)
        registry["unknown"].append({"segment": "extra", "label": rng.choice(FORMER_NAMES)})
        service = Service(store, [Connection(store, one, client, registry, {"has_2nd_factor_active": False})])
        content = diagnostics.build_bundle(service, log_lines=old_lines, clock=lambda: 1_788_000_000,
                                           versions={"app": "x", "home_assistant": "y"}, book=book)
        report, log = open_bundle(content)
        assert "- JSON value shapes:" in report
        assert "- Table headers:" in report
        assert "timetable of <name>" in log
        for text in (report, log):
            assert_no_former_name(text)
            assert book.salt not in text
            assert not any(digest in text for digest in list(book.hashes)[:50])
