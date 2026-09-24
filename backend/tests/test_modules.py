from datetime import date
from pathlib import Path

import requests

from app import modules
from app.modules import (
    ABSENCES,
    AVAILABLE,
    CONFERENCES,
    LETTERS,
    MESSENGER,
    MISSING,
    MODULES,
    PINBOARD,
    TIMETABLE,
    UNKNOWN,
)

START_PAGE = """
<html><head><meta charset="utf-8"><title>Start</title></head><body>
<nav><ul>
  <li><a href="/iserv/time-table/">Stundenplan <span class="badge">2</span></a></li>
  <li><div><a href="/iserv/parentletter/parent/index"> Elternbriefe </a></div></li>
  <li><a href="/iserv/mail/"><i class="icon"></i>E-Mail</a></li>
  <li><a href="/iserv/mail/inbox">Posteingang</a></li>
  <li><a href="/iserv/file/-/Groups">Dateien</a></li>
  <li><a href="https://school.example/iserv/videoconference/">Videokonferenzen</a></li>
  <li><a href="/iserv/auth/logout">Abmelden</a></li>
  <li><a href="/iserv/profile/">Profil</a></li>
  <li><a href="/iserv/"></a></li>
  <li><a href="/other/thing">Elsewhere</a></li>
  <li><a href="/iserv/exercise/"></a></li>
  <li><a href="/iserv/mystery/">Mystery</a></li>
</ul></nav>
<footer>IServ 3.2.1 · School</footer>
</body></html>
"""

DOCUMENTED_PAGE = """
<html><body><nav>
  <a href="/iserv/dsa-classregister/">Klassenbuch</a>
  <a href="/iserv/calendar/">Kalender</a>
  <a href="/iserv/mystery/">Mystery</a>
</nav></body></html>
"""


FIXTURES = Path(__file__).parent / "fixtures"
MESSENGER_PAGE = (FIXTURES / "messenger_page.html").read_text(encoding="utf-8")
MESSENGER_PAGE_WITHOUT_CREDENTIALS = (FIXTURES / "messenger_page_without_credentials.html").read_text(encoding="utf-8")
MESSENGER_CONTINUATION = '<html><head><meta http-equiv="refresh" content="0;url=/iserv/messenger/?step=2"></head></html>'
MESSENGER_PAGE_WITHOUT_DATA = "<html><body><div id='app'></div></body></html>"
MESSENGER_PATH = modules.PROBES[MESSENGER][0]
AUTHENTICATE_PATH = "/iserv/messenger/authenticate"
AUTHENTICATE_ANSWER = {
    "messenger_authentication": {
        "access_token": "tok-x",
        "device_id": "dev-x",
        "home_server": "srv-x",
        "user_id": "@me:srv-x",
        "iserv_token": "it-x",
        "iserv_cryptkey": "ck-x",
    }
}


class Response:
    def __init__(self, status_code=200, url="https://school.example/iserv/time-table/", text="", json_data=None):
        self.status_code = status_code
        self.url = url
        self.text = text
        self.json_data = json_data

    def json(self):
        if self.json_data is None:
            raise ValueError("no json")
        return self.json_data


def probe_map(answers):
    calls = []

    def fetch(path, params=None):
        calls.append((path, params))
        answer = answers.get(path)
        if isinstance(answer, Exception):
            raise answer
        if answer is None:
            return Response(200, f"https://school.example{path}")
        return answer

    fetch.calls = calls
    return fetch


def all_available():
    return probe_map({modules.PROBES[MESSENGER][0]: messenger_page(MESSENGER_PAGE)})


def messenger_page(text):
    return Response(200, "https://school.example/iserv/messenger/", text)


def failing_everywhere():
    return probe_map({path: requests.ConnectionError("down") for path, _ in modules.PROBES.values()})


def test_the_module_map_names_the_segments_the_clients_use():
    assert modules.SEGMENTS["time-table"] == (TIMETABLE,)
    assert modules.SEGMENTS["parentletter"] == (LETTERS,)
    assert modules.SEGMENTS["parentconference"] == (CONFERENCES,)
    assert modules.SEGMENTS["messenger"] == (MESSENGER,)
    assert modules.SEGMENTS["dieschulapp"] == (PINBOARD, ABSENCES)
    assert set(modules.PROBES) == set(MODULES)


def test_every_documented_slug_carries_an_official_name_a_label_and_an_edition():
    assert len(modules.CATALOGUE) == 56
    for slug, (name, label, edition) in modules.CATALOGUE.items():
        assert slug == slug.strip().lower(), slug
        assert name.strip() == name and name, slug
        assert label.strip() == label and label, slug
        assert edition in (modules.CURRENT, modules.OBSOLETE, modules.NEW), slug
    assert modules.official_name("dsa-classregister") == "Klassenbuch"
    assert modules.english_label("dsa-classregister") == "Class register"
    assert modules.official_name("nothing") == ""
    assert modules.english_label("nothing") == ""
    assert modules.edition_of("nothing") == ""


def test_the_two_editions_of_timetable_and_absences_are_told_apart():
    assert modules.edition_of("timetable") == modules.OBSOLETE
    assert modules.edition_of("dsa-timetable") == modules.NEW
    assert modules.edition_of("absence") == modules.CURRENT
    assert modules.edition_of("absence_obsolete") == modules.OBSOLETE
    assert modules.official_name("timetable") == "Stundenplan (veraltet)"
    assert modules.official_name("dsa-timetable") == "Stunden- und Vertretungsplan (neu)"
    assert modules.official_name("absence_obsolete") == "Abwesenheiten (veraltet)"


def test_every_supported_segment_is_documented_or_is_the_school_app_host():
    for segment in modules.SEGMENTS:
        assert modules.slug_of(segment) or segment == "dieschulapp", segment
    assert set(modules.SEGMENT_SLUGS.values()) <= set(modules.CATALOGUE)
    for slug in ("timetable", "dsa-timetable", "absence", "absence_obsolete", "dsa-pinboard", "parentletter", "parentconference", "messenger"):
        assert slug in modules.CATALOGUE, slug


def test_a_segment_resolves_to_its_documented_slug_or_to_nothing():
    assert modules.slug_of("time-table") == "timetable"
    assert modules.slug_of("dsa-absences") == "absence"
    assert modules.slug_of("dsa-timetable") == "dsa-timetable"
    assert modules.slug_of("dsa-pinboard") == "dsa-pinboard"
    assert modules.slug_of("Calendar") == "calendar"
    assert modules.slug_of("dieschulapp") == ""
    assert modules.slug_of("mystery") == ""
    assert modules.slug_of("") == ""
    assert modules.slug_of(None) == ""
    assert modules.is_known_segment("calendar") is True
    assert modules.is_known_segment("mystery") is False

DSA_START_PAGE = """
<html><body><nav>
  <a href="/iserv/dsa-timetable/">Stundenplan</a>
  <a href="/iserv/dsa-pinboard/">Pinnwände</a>
  <a href="/iserv/dsa-absences/">Abwesenheiten</a>
  <a href="/iserv/mail/">E-Mail</a>
</nav></body></html>
"""


def test_the_school_app_modules_are_linked_under_their_own_segments():
    assert modules.SEGMENTS["dsa-timetable"] == (TIMETABLE,)
    assert modules.SEGMENTS["dsa-pinboard"] == (PINBOARD,)
    assert modules.SEGMENTS["dsa-absences"] == (ABSENCES,)
    registry = modules.detect(DSA_START_PAGE, failing_everywhere(), None)
    assert registry["modules"][TIMETABLE] is True
    assert registry["modules"][PINBOARD] is True
    assert registry["modules"][ABSENCES] is True
    assert registry["unknown"] == []
    assert [entry["segment"] for entry in registry["unsupported"]] == ["mail"]


def test_link_harvest_is_structure_agnostic_and_dedupes_by_first_segment():
    links = modules.harvest_links(START_PAGE)
    assert links == [
        {"segment": "time-table", "label": "Stundenplan 2"},
        {"segment": "parentletter", "label": "Elternbriefe"},
        {"segment": "mail", "label": "E-Mail"},
        {"segment": "file", "label": "Dateien"},
        {"segment": "videoconference", "label": "Videokonferenzen"},
        {"segment": "auth", "label": "Abmelden"},
        {"segment": "profile", "label": "Profil"},
        {"segment": "exercise", "label": "exercise"},
        {"segment": "mystery", "label": "Mystery"},
    ]


def test_documented_segments_are_listed_as_not_supported_and_the_rest_as_unknown():
    registry = modules.detect(START_PAGE, all_available(), None)
    assert registry["unsupported"] == [
        {"segment": "mail", "slug": "mail", "label": "E-Mail", "name": "E-Mail"},
        {"segment": "file", "slug": "file", "label": "Dateien", "name": "Dateien"},
        {"segment": "videoconference", "slug": "videoconference", "label": "Videokonferenzen", "name": "Videokonferenzen"},
        {"segment": "exercise", "slug": "exercise", "label": "exercise", "name": "Aufgaben"},
    ]
    assert registry["unknown"] == [{"segment": "mystery", "label": "Mystery"}]


def test_present_but_not_supported_is_told_apart_from_unknown():
    unsupported, unknown = modules.split_links(modules.harvest_links(DOCUMENTED_PAGE))
    assert [entry["slug"] for entry in unsupported] == ["dsa-classregister", "calendar"]
    assert unsupported[0] == {"segment": "dsa-classregister", "slug": "dsa-classregister", "label": "Klassenbuch", "name": "Klassenbuch"}
    assert unknown == [{"segment": "mystery", "label": "Mystery"}]
    assert modules.split_links([{"segment": "time-table", "label": "Stundenplan"}]) == ([], [])
    assert modules.split_links([{"segment": "profile", "label": "Profil"}]) == ([], [])


def test_the_iserv_version_comes_from_the_footer_or_stays_empty():
    assert modules.iserv_version(START_PAGE) == "3.2.1"
    assert modules.iserv_version('<meta name="generator" content="IServ 4.0.7">') == "4.0.7"
    assert modules.iserv_version("<html><body>nothing</body></html>") == ""


def test_the_iserv_version_is_read_in_every_wording_a_page_may_use():
    assert modules.iserv_version("<footer>IServ Schulserver 3.9.1</footer>") == "3.9.1"
    assert modules.iserv_version("<footer>IServ v3.9</footer>") == "3.9"
    assert modules.iserv_version("<div>Version: 2026.09.1</div>") == "2026.09.1"
    assert modules.iserv_version("<footer>IServ 2026.9</footer>") == "2026.9"
    assert modules.iserv_version('<script>window.iserv = {"version": "3.10.2"}</script>') == "3.10.2"
    assert modules.iserv_version('<script src="/iserv/app.js?v=9"></script>') == ""
    assert modules.iserv_version("<div>Termin am 15.09.2026</div>") == ""
    assert modules.iserv_version("<footer>IServ, since 2020</footer>") == ""


def test_the_login_page_is_the_second_source_of_the_iserv_version():
    login_page = "<html><body><form></form><footer>IServ 3.7.4</footer></body></html>"
    registry = modules.detect("<html><body><a href='/iserv/mail/'>Mail</a></body></html>", all_available(), None, login_html=login_page)
    assert registry["iserv_version"] == "3.7.4"
    assert modules.detect(START_PAGE, all_available(), None, login_html=login_page)["iserv_version"] == "3.2.1"
    assert modules.detect("", all_available(), None, login_html="")["iserv_version"] == ""


def test_classify_reads_status_and_final_url():
    assert modules.classify(Response(200), "/iserv/time-table/") == AVAILABLE
    assert modules.classify(Response(403), "/iserv/time-table/") == MISSING
    assert modules.classify(Response(404), "/iserv/time-table/") == MISSING
    assert modules.classify(Response(200, "https://school.example/iserv/"), "/iserv/time-table/") == MISSING
    assert modules.classify(Response(200, "https://school.example/iserv/auth/login"), "/iserv/time-table/") == MISSING
    assert modules.classify(Response(302, "https://school.example/iserv/login"), "/iserv/time-table/") == MISSING
    assert modules.classify(Response(500), "/iserv/time-table/") == UNKNOWN
    assert modules.classify(None, "/iserv/time-table/") == UNKNOWN


def _timetable_answers(school_app, native):
    return probe_map({
        modules.DSA_TIMETABLE_PATH: school_app,
        modules.PROBES[TIMETABLE][0]: native,
    })


NATIVE_MISSING = Response(403, "https://school.example/iserv/time-table/")
NATIVE_UNKNOWN = requests.ConnectionError("down")


def test_the_timetable_is_available_when_the_school_app_serves_it_even_without_the_native_page():
    fetch = _timetable_answers(None, NATIVE_MISSING)
    registry = modules.detect(START_PAGE, fetch, None)
    assert registry["modules"][TIMETABLE] is True
    assert modules.PROBES[TIMETABLE][0] not in [path for path, _ in fetch.calls]


def test_the_timetable_is_available_when_only_the_native_page_answers():
    fetch = _timetable_answers(Response(404, "https://school.example" + modules.DSA_TIMETABLE_PATH), None)
    registry = modules.detect(START_PAGE, fetch, None)
    assert registry["modules"][TIMETABLE] is True


def test_the_timetable_is_missing_only_when_both_sources_are_missing():
    fetch = _timetable_answers(Response(404, "https://school.example" + modules.DSA_TIMETABLE_PATH), NATIVE_MISSING)
    registry = modules.detect(START_PAGE, fetch, None)
    assert registry["modules"][TIMETABLE] is False


def test_the_timetable_stays_as_it_was_when_both_sources_are_unreachable():
    previous = modules.detect(START_PAGE, _timetable_answers(
        Response(404, "https://school.example" + modules.DSA_TIMETABLE_PATH), NATIVE_MISSING
    ), None)
    registry = modules.detect(START_PAGE, _timetable_answers(NATIVE_UNKNOWN, NATIVE_UNKNOWN), previous)
    assert registry["modules"][TIMETABLE] is False
    fresh = modules.detect(START_PAGE, _timetable_answers(NATIVE_UNKNOWN, NATIVE_UNKNOWN), None)
    assert fresh["modules"][TIMETABLE] is True


def test_a_missing_school_app_timetable_next_to_an_unreachable_native_page_is_not_a_verdict():
    previous = modules.detect(START_PAGE, all_available(), None)
    fetch = _timetable_answers(Response(404, "https://school.example" + modules.DSA_TIMETABLE_PATH), NATIVE_UNKNOWN)
    assert modules.detect(START_PAGE, fetch, previous)["modules"][TIMETABLE] is True


def test_the_school_app_timetable_probe_asks_for_the_week_of_the_day_without_substitutions():
    fetch = all_available()
    modules.detect(START_PAGE, fetch, None, clock=lambda: 1_788_000_000)
    calls = dict(fetch.calls)
    assert calls[modules.DSA_TIMETABLE_PATH] == {"date": "2026-08-29", "week": "true", "substitutions": "false"}


def _authenticate_calls(fetch):
    return [path for path, _ in fetch.calls if "authenticate" in path]


def _messenger_probe(page, authenticate=None):
    answers = {MESSENGER_PATH: messenger_page(page)}
    for path in ("/iserv/messenger/authenticate", "/messenger/authenticate"):
        answers[path] = authenticate if authenticate is not None else Response(404, "https://school.example" + path)
    return probe_map(answers)


def test_a_messenger_page_with_embedded_credentials_counts_without_any_further_call():
    fetch = _messenger_probe(MESSENGER_PAGE)
    assert modules.detect(START_PAGE, fetch, None)["modules"][MESSENGER] is True
    assert _authenticate_calls(fetch) == []


def test_a_messenger_page_whose_credentials_iserv_withholds_is_still_the_messenger():
    fetch = _messenger_probe(MESSENGER_PAGE_WITHOUT_CREDENTIALS)
    assert modules.detect(START_PAGE, fetch, None)["modules"][MESSENGER] is True
    assert _authenticate_calls(fetch) == []


def test_a_messenger_page_without_data_counts_when_the_authenticate_call_hands_out_credentials():
    fetch = _messenger_probe(MESSENGER_PAGE_WITHOUT_DATA, Response(200, "https://school.example" + AUTHENTICATE_PATH, json_data=AUTHENTICATE_ANSWER))
    assert modules.detect(START_PAGE, fetch, None)["modules"][MESSENGER] is True
    assert _authenticate_calls(fetch) == [AUTHENTICATE_PATH]


def test_a_messenger_page_without_data_whose_authenticate_call_refuses_is_missing():
    fetch = _messenger_probe(MESSENGER_PAGE_WITHOUT_DATA)
    assert modules.detect(START_PAGE, fetch, None)["modules"][MESSENGER] is False
    html_answer = _messenger_probe(MESSENGER_PAGE_WITHOUT_DATA, Response(200, "https://school.example" + AUTHENTICATE_PATH, text="<html></html>"))
    assert modules.detect(START_PAGE, html_answer, None)["modules"][MESSENGER] is False


def test_an_unreachable_authenticate_call_keeps_the_earlier_messenger_verdict():
    available = modules.detect(START_PAGE, all_available(), None)
    unreachable = _messenger_probe(MESSENGER_PAGE_WITHOUT_DATA, requests.ConnectionError("down"))
    assert modules.detect(START_PAGE, unreachable, available)["modules"][MESSENGER] is True
    missing = modules.detect(START_PAGE, _messenger_probe(MESSENGER_PAGE_WITHOUT_DATA), None)
    assert modules.detect(START_PAGE, unreachable, missing)["modules"][MESSENGER] is False
    broken = _messenger_probe(MESSENGER_PAGE_WITHOUT_DATA, Response(503, "https://school.example" + AUTHENTICATE_PATH))
    assert modules.detect(START_PAGE, broken, available)["modules"][MESSENGER] is True


def test_a_messenger_page_that_still_continues_elsewhere_is_no_verdict():
    previous = modules.detect(START_PAGE, all_available(), None)
    continuing = probe_map({modules.PROBES[MESSENGER][0]: messenger_page(MESSENGER_CONTINUATION)})
    assert modules.detect(START_PAGE, continuing, previous)["modules"][MESSENGER] is True
    assert modules.detect("", continuing, None)["modules"][MESSENGER] is True


def test_detect_marks_every_module_from_its_probe():
    fetch = probe_map({
        modules.PROBES[ABSENCES][0]: Response(403, "https://school.example" + modules.PROBES[ABSENCES][0]),
        modules.PROBES[MESSENGER][0]: Response(200, "https://school.example/iserv/"),
    })
    registry = modules.detect(START_PAGE, fetch, None)
    assert registry["modules"] == {
        TIMETABLE: True,
        LETTERS: True,
        PINBOARD: True,
        ABSENCES: False,
        CONFERENCES: True,
        MESSENGER: False,
    }
    assert registry["iserv_version"] == "3.2.1"
    assert registry["checked_at"] > 0
    assert len(fetch.calls) == len(MODULES)


def test_detect_probes_each_module_once_with_the_lightweight_parameters():
    fetch = all_available()
    modules.detect(START_PAGE, fetch, None, clock=lambda: 1_788_000_000)
    expected = [modules.probes_of(name, date(2026, 8, 29))[0] for name in MODULES]
    assert sorted(fetch.calls, key=str) == sorted(expected, key=str)
    assert len(fetch.calls) == len(MODULES)


def test_a_network_error_keeps_the_last_known_state():
    previous = modules.detect(START_PAGE, probe_map({
        modules.PROBES[LETTERS][0]: Response(404, "https://school.example" + modules.PROBES[LETTERS][0]),
    }), None)
    assert previous["modules"][LETTERS] is False
    registry = modules.detect(START_PAGE, failing_everywhere(), previous)
    assert registry["modules"] == previous["modules"]
    assert registry["checked_at"] >= previous["checked_at"]


def test_without_any_earlier_state_an_unreachable_probe_falls_back_to_the_start_page_links():
    registry = modules.detect(START_PAGE, failing_everywhere(), None)
    assert registry["modules"][TIMETABLE] is True
    assert registry["modules"][LETTERS] is True
    assert registry["modules"][CONFERENCES] is False
    assert registry["modules"][MESSENGER] is False


def test_without_any_earlier_state_and_without_a_start_page_everything_stays_shown():
    registry = modules.detect("", failing_everywhere(), None)
    assert registry["modules"] == {name: True for name in MODULES}


def test_a_session_that_lost_its_login_does_not_wipe_the_registry():
    previous = modules.detect(START_PAGE, all_available(), None)
    logged_out = probe_map({
        path: Response(200, "https://school.example/iserv/auth/login?target=x") for path, _ in modules.PROBES.values()
    })
    registry = modules.detect("", logged_out, previous)
    assert registry["modules"] == previous["modules"]
    assert registry["unsupported"] == previous["unsupported"]
    assert registry["unknown"] == previous["unknown"]


def test_a_lost_login_is_read_from_the_pages_even_when_the_school_app_api_refuses():
    previous = modules.detect(START_PAGE, all_available(), None)
    answers = {
        path: Response(200, "https://school.example/iserv/auth/login?target=x")
        for name in MODULES
        for path, _ in modules.probes_of(name, date(2026, 8, 29))
        if not path.startswith(modules.DSA_API)
    }
    answers.update({
        path: Response(403, "https://school.example" + path)
        for name in MODULES
        for path, _ in modules.probes_of(name, date(2026, 8, 29))
        if path.startswith(modules.DSA_API)
    })
    registry = modules.detect("", probe_map(answers), previous)
    assert registry["modules"] == previous["modules"]


def test_the_default_registry_shows_everything_and_was_never_checked():
    registry = modules.default_registry()
    assert registry["modules"] == {name: True for name in MODULES}
    assert registry["unsupported"] == []
    assert registry["unknown"] == []
    assert registry["checked_at"] == 0
    assert registry["iserv_version"] == ""


def test_summary_line_names_available_missing_unsupported_and_unknown_segments_without_labels():
    registry = modules.detect(START_PAGE, probe_map({
        modules.PROBES[ABSENCES][0]: Response(403, "https://school.example/x"),
        modules.PROBES[MESSENGER][0]: messenger_page(MESSENGER_PAGE),
    }), None)
    line = modules.summary(registry)
    assert line == (
        "modules available: timetable, letters, pinboard, conferences, messenger; "
        "missing: absences; not supported: 4 (mail, file, videoconference, exercise); unknown: 1 (mystery)"
    )
    assert "E-Mail" not in line
    assert "Aufgaben" not in line


def test_changed_compares_modules_and_segments_but_not_the_check_time():
    first = modules.detect(START_PAGE, all_available(), None)
    second = dict(first, checked_at=first["checked_at"] + 100)
    assert modules.changed(first, second) is False
    assert modules.changed(None, first) is True
    third = dict(first, modules=dict(first["modules"], letters=False))
    assert modules.changed(first, third) is True
    fourth = dict(first, unsupported=[])
    assert modules.changed(first, fourth) is True


def test_registry_of_falls_back_to_the_default_for_a_service_without_the_reader():
    class Bare:
        pass

    class Reader:
        def modules(self):
            return {"modules": {name: name == LETTERS for name in MODULES}, "unknown": [], "checked_at": 5}

    assert modules.registry_of(Bare()) == modules.default_registry()
    assert modules.registry_of(Reader())["modules"][LETTERS] is True
    assert modules.registry_of(Reader())["modules"][TIMETABLE] is False


def test_normalize_fills_missing_fields_and_drops_foreign_ones():
    registry = modules.normalize({
        "modules": {LETTERS: False, "other": True},
        "unsupported": [{"segment": "calendar"}, {"segment": ""}],
        "unknown": [{"segment": "mystery"}],
    })
    assert registry["modules"] == {name: name != LETTERS for name in MODULES}
    assert registry["unsupported"] == [{"segment": "calendar", "slug": "calendar", "label": "calendar", "name": "Kalender"}]
    assert registry["unknown"] == [{"segment": "mystery", "label": "mystery"}]
    assert registry["checked_at"] == 0
    assert registry["iserv_version"] == ""
    assert modules.normalize(None) == modules.default_registry()


def test_a_registry_stored_before_the_catalogue_keeps_its_unknown_list():
    registry = modules.normalize({"modules": {}, "unknown": [{"segment": "mail", "label": "E-Mail"}], "checked_at": 3})
    assert registry["unknown"] == [{"segment": "mail", "label": "E-Mail"}]
    assert registry["unsupported"] == []
