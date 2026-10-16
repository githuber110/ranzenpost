from app.iserv.conferences import first_time, form_signature, module_path, page_errors, parse_conference_page, parse_conferences
from tests.conference_school import DETAIL_PATH, TEACHER_PATH, ConferenceSchool

BASE = "https://school.example"


def test_parse_conferences_empty_page(fixture):
    result = parse_conferences(fixture("conferences_empty.html"), BASE)
    assert result == {"empty": True, "items": []}


def test_parse_conferences_without_table_is_a_parse_error_not_empty():
    result = parse_conferences("<div><p>Elternsprechtage</p></div>", BASE)
    assert result == {"error": "parse_failed", "items": []}


def test_parse_conferences_empty_table_body_is_empty():
    html = "<table><tbody></tbody></table>"
    result = parse_conferences(html, BASE)
    assert result == {"empty": True, "items": []}


def test_parse_conferences_empty_phrase_wins_over_table():
    html = "<p>Derzeit sind KEINE Elternsprechtage verfügbar.</p><table><tbody><tr><td>x</td></tr></tbody></table>"
    result = parse_conferences(html, BASE)
    assert result == {"empty": True, "items": []}


def test_parse_conferences_list(fixture):
    result = parse_conferences(fixture("conferences_list.html"), BASE)
    assert result["empty"] is False
    assert len(result["items"]) == 2
    first = result["items"][0]
    assert first["cells"] == ["15.09.2026", "Frau Muster", "Raum 101", "Termin buchen"]
    assert first["links"] == ["https://school.example/iserv/parentconference/attendee/1/book"]
    second = result["items"][1]
    assert second["cells"] == ["22.09.2026", "Herr Beispiel", "Raum 202", "Termin buchen"]
    assert second["links"] == ["https://school.example/iserv/parentconference/attendee/2/book"]


def test_parse_conferences_drops_unsafe_link_schemes():
    html = (
        "<table><tbody><tr>"
        "<td>15.09.2026</td>"
        "<td><a href=\"javascript:alert(1)\">Termin buchen</a></td>"
        "</tr></tbody></table>"
    )
    result = parse_conferences(html, BASE)
    assert result["items"][0]["links"] == []



def test_parse_conferences_reads_panels_with_and_without_a_booking_link(fixture):
    result = parse_conferences(fixture("conference_overview.html"), BASE + "/iserv/parentconference/attendee/")
    assert result["empty"] is False
    first, second = result["items"]
    assert first["cells"] == [
        "Elternsprechtag Herbst",
        "Donnerstag, 05.11.2026, 14:00 - 18:00 Uhr",
        "Buchungszeitraum: 20.10.2026 - 03.11.2026",
    ]
    assert first["paths"] == ["/iserv/parentconference/attendee/conference/7"]
    assert second["cells"][0] == "Elternsprechtag Frühjahr"
    assert second["paths"] == []


def test_parse_conferences_keeps_table_headers_and_module_paths(fixture):
    result = parse_conferences(fixture("conferences_list.html"), BASE)
    assert result["items"][0]["headers"] == ["Datum", "Lehrkraft", "Raum", "Aktionen"]
    assert result["items"][0]["paths"] == ["/iserv/parentconference/attendee/1/book"]


def test_parse_conferences_ignores_tab_links_and_other_modules():
    html = (
        "<div id='content'><ul class='nav nav-tabs'><li><a href='/iserv/parentconference/attendee/archive'>Archiv</a></li></ul>"
        "<div class='card'><h3>Sprechtag</h3><a href='/iserv/mail/'>Post</a>"
        "<a href='https://other.example/iserv/parentconference/attendee/9'>x</a></div></div>"
    )
    result = parse_conferences(html, BASE + "/iserv/parentconference/attendee/")
    assert [item["cells"][0] for item in result["items"]] == ["Sprechtag"]
    assert result["items"][0]["paths"] == []


def school_page(path, **changes):
    school = ConferenceSchool()
    for key, value in changes.items():
        setattr(school, key, value)
    response = school.page(path)
    return parse_conference_page(response.text, response.url)


def test_the_detail_page_keeps_notices_facts_tables_and_row_forms_in_order():
    school = ConferenceSchool()
    school.bookings["31"] = "101"
    response = school.page(DETAIL_PATH)
    page = parse_conference_page(response.text, response.url)
    assert page["title"] == "Elternsprechtag Herbst"
    assert [block["kind"] for block in page["blocks"]] == ["notice", "facts", "heading", "table", "heading", "table"]
    assert page["notices"] == [{"tone": "info", "text": "Buchungen sind bis zum 03.11.2026 möglich."}]
    assert page["blocks"][1]["facts"][2] == {"label": "Termindauer", "value": "10 Minuten"}
    bookings = page["blocks"][3]
    assert bookings["headers"] == ["Zeit", "Lehrkraft", "Raum", "Kind", "Aktionen"]
    assert bookings["rows"][0]["cells"] == ["14:00 - 14:10", "Frau Muster", "R 101", "Kim", ""]
    assert bookings["rows"][0]["forms"] == [0]
    cancel = page["forms"][0]
    assert cancel["action"] == "/iserv/parentconference/attendee/booking/31/delete"
    assert cancel["destructive"] is True
    assert cancel["submits"][0]["label"] == "Absagen"
    teachers = page["blocks"][5]
    assert teachers["rows"][0]["links"] == [{"label": "Frau Muster", "path": TEACHER_PATH}]


def test_the_teacher_page_turns_the_booking_form_into_fields():
    page = school_page(TEACHER_PATH)
    assert page["title"] == "Frau Muster"
    assert page["blocks"] == [
        {"kind": "text", "text": "Raum R 101, Elternsprechtag Herbst am 05.11.2026"},
        {"kind": "form", "form": 0},
    ]
    form = page["forms"][0]
    assert form["method"] == "post"
    assert form["action"] == TEACHER_PATH + "/book"
    hidden, slot, child, note = form["fields"]
    assert hidden == {"key": "booking[_token]", "name": "booking[_token]", "kind": "hidden", "value": "token-book-1"}
    assert slot["kind"] == "radio" and slot["label"] == "Zeit" and slot["required"] is True
    assert [(option["value"], option["label"], option["disabled"]) for option in slot["options"]] == [
        ("101", "14:00 - 14:10", False),
        ("102", "14:10 - 14:20 (belegt)", True),
        ("103", "14:20 - 14:30", False),
    ]
    assert child["kind"] == "select" and child["label"] == "Kind" and child["required"] is True
    assert [option["value"] for option in child["options"]] == ["", "501"]
    assert note["kind"] == "textarea" and note["label"] == "Anmerkung" and note["maxlength"] == 500
    assert form["submits"] == [{"name": "booking[submit]", "value": "", "label": "Buchen", "destructive": False}]
    assert form["destructive"] is False


def test_the_upward_link_back_to_the_conference_is_not_offered_as_a_page():
    page = school_page(TEACHER_PATH)
    assert not [block for block in page["blocks"] if block["kind"] == "links"]


def test_form_errors_name_the_page_problem_and_the_field_problem():
    school = ConferenceSchool()
    response = school.page(TEACHER_PATH)
    html = school.teacher_page(invalid=True)
    page = parse_conference_page(html, response.url)
    form = page["forms"][0]
    assert form["errors"] == ["Das Formular enthält Fehler.", "Bitte wählen Sie ein Kind aus."]
    assert form["fields"][2]["error"] == "Bitte wählen Sie ein Kind aus."
    assert page_errors(page) == ["Das Formular enthält Fehler.", "Bitte wählen Sie ein Kind aus."]


def test_forms_outside_the_conference_module_are_not_offered():
    html = (
        "<div id='content'><h1>T</h1><form method='post' action='/iserv/auth/logout'><button>x</button></form>"
        "<form method='post' action='https://other.example/iserv/parentconference/x'><button>y</button></form></div>"
    )
    page = parse_conference_page(html, BASE + "/iserv/parentconference/attendee/conference/7")
    assert page["forms"] == []


def test_the_form_signature_ignores_token_values_but_not_field_names():
    first = school_page(TEACHER_PATH)["forms"][0]
    second = parse_conference_page(
        ConferenceSchool().teacher_page().replace("token-book-1", "token-book-2"), BASE + TEACHER_PATH
    )["forms"][0]
    assert form_signature(first) == form_signature(second)
    renamed = parse_conference_page(
        ConferenceSchool().teacher_page().replace("booking[note]", "booking[comment]"), BASE + TEACHER_PATH
    )["forms"][0]
    assert form_signature(first) != form_signature(renamed)



def test_a_time_is_never_read_from_a_date_or_a_room_number():
    assert first_time(["05.11.2026 14:00"]) == "14:00"
    assert first_time(["Raum 1.12", "05.11.2026"]) == ""
    assert first_time(["05.11.26"]) == ""
    assert first_time(["14.30 Uhr"]) == "14:30"
    assert first_time(["ab 9 Uhr"]) == "09:00"
    assert first_time(["2:30 pm"]) == "14:30"
    assert first_time(["12:05 am"]) == "00:05"
    assert first_time(["Raum 1.12", "14:00 - 14:10"]) == "14:00"


PAGE_URL = BASE + "/iserv/parentconference/attendee/conference/7"


def test_encoded_dots_slashes_and_backslashes_never_leave_the_module():
    for href in (
        "/iserv/parentconference/%2e%2e/mail/",
        "/iserv/parentconference/%2E%2E/mail/",
        "/iserv/parentconference/attendee%2f..%2fmail",
        "/iserv/parentconference/attendee\..\mail",
        "/iserv/parentconference/../mail/",
        "javascript:alert(1)",
        "mailto:x@school.example",
    ):
        assert module_path(href, PAGE_URL) is None, href


def test_relative_links_and_actions_resolve_against_the_page():
    assert module_path("teacher/12", PAGE_URL + "/") == "/iserv/parentconference/attendee/conference/7/teacher/12"
    assert module_path("?page=2", PAGE_URL) == "/iserv/parentconference/attendee/conference/7?page=2"
    html = "<div id='content'><h1>T</h1><form method='post' action='book/12'><button>Buchen</button></form><a href='teacher/14'>Herr Beispiel</a></div>"
    page = parse_conference_page(html, PAGE_URL + "/")
    assert page["forms"][0]["action"] == "/iserv/parentconference/attendee/conference/7/book/12"
    assert page["blocks"][-1]["links"][0]["path"] == "/iserv/parentconference/attendee/conference/7/teacher/14"


def test_one_helper_builds_the_browser_headers_for_letters_and_conferences():
    from app import conference_service, letter_service
    from app.iserv.forms import browser_headers

    assert browser_headers(BASE + "/iserv/x") == {"Referer": BASE + "/iserv/x", "Origin": BASE}
    assert browser_headers("") == {}
    assert letter_service._browser_headers is browser_headers
    assert conference_service.browser_headers is browser_headers
