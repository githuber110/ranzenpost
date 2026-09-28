import json
from datetime import date
from pathlib import Path

import pytest

from app.iserv.dsa import (
    REGULAR_PLAN_SECONDS,
    REGULAR_PLAN_TIMEOUT,
    DieSchulAppClient,
    SharedReads,
    absence_rules,
    deregister_options,
    enabled_absence_types,
    normalize_class,
    parse_period_times,
    parse_pinboards,
    parse_students,
)
from app.iserv.errors import DataError

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://school.example"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, data, status_code=200, headers=None):
        self._data = data
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._data


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if "students/" in url:
            return FakeResponse(load("dsa_students.json"))
        if "school-settings/" in url:
            return FakeResponse(load("dsa_school_settings.json"))
        if "timetable-slots/" in url:
            return FakeResponse(load("dsa_timetable_slots.json"))
        if "pinboards/" in url:
            return FakeResponse(load("dsa_pinboards.json"))
        if "sickNotes/" in url:
            return FakeResponse([])
        return FakeResponse(None, status_code=404)


def test_normalize_class_strips_leading_zeros_and_reads_variants():
    assert normalize_class("02B") == "2B"
    assert normalize_class("Klasse 02B") == "2B"
    assert normalize_class("klasse.02b") == "2B"
    assert normalize_class({"externalId": "klasse.02b", "name": "Klasse 02B"}) == "2B"
    assert normalize_class("10A") == "10A"
    assert normalize_class("012A") == "12A"
    assert normalize_class("") == ""


def test_parse_students_extracts_name_and_class():
    students = parse_students(load("dsa_students.json"))
    assert students == [{
        "id": 10000001,
        "name": "Example Alex",
        "class_name": "2B",
        "class_full": "Klasse 02B",
        "class_code": "klasse.02b",
    }]


def test_parse_period_times():
    times = parse_period_times(load("dsa_timetable_slots.json"))
    assert times["1"] == "08:00"
    assert times["3"] == "10:00"


def test_parse_pinboards_with_attachments():
    boards = parse_pinboards(load("dsa_pinboards.json"))
    assert len(boards) == 1
    board = boards[0]
    assert board.title == "Klassenpinnwand 2B"
    assert len(board.attachments) == 1
    assert board.attachments[0].extension == "pdf"
    tiles = board.columns[0].tiles
    assert len(tiles) == 2
    assert tiles[1].title == "Elternabend"
    assert tiles[1].attachments[0].filename == "Einladung Elternabend.pdf"


def test_parse_pinboards_reads_author_and_create_permission():
    boards = parse_pinboards(load("dsa_pinboards.json"))
    board = boards[0]
    assert board.author == "Teacher One"
    assert board.students_can_create_tiles is False


def test_parse_pinboards_carries_attachment_timestamps_and_image_size():
    boards = parse_pinboards(load("dsa_pinboards.json"))
    attachment = boards[0].columns[0].tiles[1].attachments[0]
    assert attachment.created_at == 1700000000
    assert attachment.updated_at == 1700000000
    assert attachment.image_width is None
    assert attachment.image_height is None


def test_enabled_absence_types_and_deregister_options():
    settings = load("dsa_school_settings.json")[0]
    assert deregister_options(settings) == ["bus", "kindergarten", "lunch"]
    types = enabled_absence_types(settings)
    assert "sick" in types
    assert "deregister" in types
    assert "daycare" in types


def test_client_reads_students_and_pinboards_and_slots():
    client = DieSchulAppClient(BASE, FakeSession())
    assert client.students()[0]["class_name"] == "2B"
    assert client.pinboards()[0].title == "Klassenpinnwand 2B"
    assert client.period_times()["1"] == "08:00"
    assert client.school_settings()["requestToSchools_notAttend_bus_isActive"] is True


def test_parse_pinboards_keeps_storage_filename_for_download():
    boards = parse_pinboards(load("dsa_pinboards.json"))
    attachment = boards[0].columns[0].tiles[1].attachments[0]
    assert attachment.filename == "Einladung Elternabend.pdf"
    assert attachment.file == "stored-name.pdf"


def test_parse_pinboards_does_not_invent_a_board_timestamp():
    boards = parse_pinboards([
        {"id": 1, "title": "Ordner", "updatedAt": 1788190464, "columns": []},
    ])
    assert not hasattr(boards[0], "updated_at")


def test_absence_rules_read_the_school_switches():
    rules = absence_rules(
        {
            "requestToSchools_notAttend_afternoonCare_pickupTimes": ["15:00"],
            "requestToSchools_studentAbsence_minDays": 3,
            "dayCare_latestTimeToCancelAttendanceToday": "11:00",
            "sickNotes_guardiansCanReportByLesson": True,
        }
    )
    assert rules["daycare_pickup_times"] == ["15:00"]
    assert rules["leave_min_days"] == 3
    assert rules["daycare_cutoff"] == "11:00"
    assert rules["sick_by_lesson"] is True
    assert rules["sick_comment"] is False


def test_absence_rules_stay_empty_without_settings():
    rules = absence_rules(None)
    assert rules["daycare_pickup_times"] == []
    assert rules["leave_min_days"] == 0


class RecordingSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})

        class R:
            status_code = 201

        return R()


def test_form_requests_go_out_as_multipart_not_urlencoded():
    from app.iserv.absences import build_request

    session = RecordingSession()
    client = DieSchulAppClient("https://school.example", session)
    request = build_request("deregister", 7, {"deregister_from": "bus", "date": "2026-09-02"})
    client.send_request(request)
    call = session.calls[0]
    assert "data" not in call, "urlencoded body would make IServ answer 500"
    assert "files" in call
    parts = dict(call["files"])
    assert parts["data"][0] is None
    assert "not-attend-bus" in parts["data"][1]


def test_json_requests_still_go_out_as_json():
    from app.iserv.absences import build_request

    session = RecordingSession()
    client = DieSchulAppClient("https://school.example", session)
    request = build_request("sick", 7, {"day_from": "2026-09-01"})
    client.send_request(request)
    call = session.calls[0]
    assert "json" in call
    assert "files" not in call


def test_leave_request_attachments_go_out_as_extra_multipart_parts():
    from app.iserv.absences import ATTACHMENT_FIELD_NAME, build_request

    session = RecordingSession()
    client = DieSchulAppClient("https://school.example", session)
    request = build_request(
        "leave",
        7,
        {"subject": "Test", "body": "Text", "from_date": "2026-09-30"},
        attachments=[
            {"filename": "beleg.pdf", "content": b"%PDF-1", "content_type": "application/pdf"},
            {"filename": "beleg2.pdf", "content": b"%PDF-2", "content_type": "application/pdf"},
        ],
    )
    client.send_request(request)
    parts = session.calls[0]["files"]
    names = [name for name, _ in parts]
    assert names.count(ATTACHMENT_FIELD_NAME) == 2
    file_parts = [value for name, value in parts if name == ATTACHMENT_FIELD_NAME]
    assert file_parts[0] == ("beleg.pdf", b"%PDF-1", "application/pdf")
    assert file_parts[1] == ("beleg2.pdf", b"%PDF-2", "application/pdf")
    data_part = dict(parts)["data"]
    assert "Test" in data_part[1], "the data part must still carry the request JSON"


def test_leave_request_without_attachments_sends_no_extra_parts():
    from app.iserv.absences import ATTACHMENT_FIELD_NAME, build_request

    session = RecordingSession()
    client = DieSchulAppClient("https://school.example", session)
    request = build_request(
        "leave", 7, {"subject": "Test", "body": "Text", "from_date": "2026-09-30"}
    )
    client.send_request(request)
    names = [name for name, _ in session.calls[0]["files"]]
    assert ATTACHMENT_FIELD_NAME not in names


def test_leave_request_repeats_the_literal_file_bracket_part_name():
    from app.iserv.absences import build_request

    session = RecordingSession()
    client = DieSchulAppClient("https://school.example", session)
    one_file = build_request(
        "leave",
        7,
        {"subject": "Test", "body": "Text", "from_date": "2026-09-30"},
        attachments=[{"filename": "beleg.pdf", "content": b"%PDF-1", "content_type": "application/pdf"}],
    )
    client.send_request(one_file)
    names = [name for name, _ in session.calls[0]["files"]]
    assert names.count("file[]") == 1

    two_files = build_request(
        "leave",
        7,
        {"subject": "Test", "body": "Text", "from_date": "2026-09-30"},
        attachments=[
            {"filename": "beleg.pdf", "content": b"%PDF-1", "content_type": "application/pdf"},
            {"filename": "beleg2.pdf", "content": b"%PDF-2", "content_type": "application/pdf"},
        ],
    )
    client.send_request(two_files)
    names = [name for name, _ in session.calls[1]["files"]]
    assert names.count("file[]") == 2
    assert "file[0]" not in names and "file[1]" not in names


def test_a_429_on_a_single_dsa_fetch_backs_off_instead_of_returning_an_empty_list():
    import pytest
    from app.iserv.errors import OutageError

    class RateLimitedSession(FakeSession):
        def get(self, url, params=None, timeout=None):
            if "sickNotes/" in url:
                return FakeResponse(None, status_code=429, headers={"Retry-After": "120"})
            return super().get(url, params=params, timeout=timeout)

    client = DieSchulAppClient(BASE, RateLimitedSession())
    with pytest.raises(OutageError) as excinfo:
        client.sick_notes()
    assert excinfo.value.reason == "rate_limited"
    assert excinfo.value.retry_after == 120


def test_a_429_without_retry_after_on_a_single_dsa_fetch_still_backs_off():
    import pytest
    from app.iserv.errors import OutageError

    class RateLimitedSession(FakeSession):
        def get(self, url, params=None, timeout=None):
            if "sickNotes/" in url:
                return FakeResponse(None, status_code=429)
            return super().get(url, params=params, timeout=timeout)

    client = DieSchulAppClient(BASE, RateLimitedSession())
    with pytest.raises(OutageError) as excinfo:
        client.sick_notes()
    assert excinfo.value.reason == "rate_limited"
    assert excinfo.value.retry_after is None


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def shared_client(session, clock):
    return DieSchulAppClient(BASE, session, shared=SharedReads(clock, seconds=120))


def slot_calls(session):
    return [url for url, _params in session.calls if "timetable-slots/" in url]


def test_school_wide_reads_are_shared_between_clients_for_a_short_time():
    session, clock = FakeSession(), Clock()
    shared = SharedReads(clock, seconds=120)
    DieSchulAppClient(BASE, session, shared=shared).lesson_slots()
    DieSchulAppClient(BASE, session, shared=shared).period_times()
    DieSchulAppClient(BASE, session, shared=shared).school_settings()
    DieSchulAppClient(BASE, session, shared=shared).school_settings()
    assert len(slot_calls(session)) == 1
    assert len([url for url, _params in session.calls if "school-settings/" in url]) == 1
    clock.now += 120
    DieSchulAppClient(BASE, session, shared=shared).lesson_slots()
    assert len(slot_calls(session)) == 2


class TimetableSession(FakeSession):
    def __init__(self, status_code=200):
        super().__init__()
        self.status_code = status_code

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if "current-timetable/" in url:
            return FakeResponse({"students": [], "flag": params.get("substitutions")}, status_code=self.status_code)
        return super().get(url, params, timeout)


def test_the_regular_plan_is_the_same_week_without_substitutions_and_kept_for_a_while():
    session, clock = TimetableSession(), Clock()
    plans = SharedReads(clock, seconds=REGULAR_PLAN_SECONDS)
    reference = date(2026, 9, 9)
    first = DieSchulAppClient(BASE, session, regular_plans=plans).regular_timetable(reference, [7001, 7002])
    DieSchulAppClient(BASE, session, regular_plans=plans).regular_timetable(reference, [7001, 7002])
    DieSchulAppClient(BASE, session, regular_plans=plans).current_timetable(reference, [7001, 7002], substitutions=True)
    DieSchulAppClient(BASE, session, regular_plans=plans).current_timetable(reference, [7001, 7002], substitutions=True)
    assert first["flag"] == "false"
    assert [params["substitutions"] for _, params in session.calls] == ["false", "true", "true"]
    assert session.calls[0][1] == {
        "date": "2026-09-09",
        "week": "true",
        "substitutions": "false",
        "filterBy": "courseSubject.course:in(7001|7002)",
    }
    clock.now += REGULAR_PLAN_SECONDS
    DieSchulAppClient(BASE, session, regular_plans=plans).regular_timetable(reference, [7001, 7002])
    assert [params["substitutions"] for _, params in session.calls] == ["false", "true", "true", "false"]


def test_the_regular_plan_is_read_again_as_soon_as_the_substituted_answer_changes():
    session, clock = TimetableSession(), Clock()
    plans = SharedReads(clock, seconds=REGULAR_PLAN_SECONDS)
    reference = date(2026, 9, 9)
    client = DieSchulAppClient(BASE, session, regular_plans=plans)
    client.regular_timetable(reference, [7001], {"students": [{"entries": [{"id": 1}]}]})
    client.regular_timetable(reference, [7001], {"students": [{"entries": [{"id": 1}]}]})
    assert len(session.calls) == 1
    clock.now += 60
    client.regular_timetable(reference, [7001], {"students": [{"entries": [{"id": 1, "teacher": "XYZ"}]}]})
    assert len(session.calls) == 2


def test_the_optional_regular_plan_waits_less_than_the_shown_week():
    class Timed(TimetableSession):
        def __init__(self):
            super().__init__()
            self.timeouts = []

        def get(self, url, params=None, timeout=None):
            self.timeouts.append(((params or {}).get("substitutions"), timeout))
            return super().get(url, params, timeout)

    session, clock = Timed(), Clock()
    reference = date(2026, 9, 9)
    DieSchulAppClient(BASE, session).current_timetable(reference, [7001], substitutions=True)
    DieSchulAppClient(BASE, session).regular_timetable(reference, [7001])
    DieSchulAppClient(BASE, session, regular_plans=SharedReads(clock)).regular_timetable(reference, [7002])
    assert session.timeouts == [("true", 30), ("false", REGULAR_PLAN_TIMEOUT), ("false", REGULAR_PLAN_TIMEOUT)]
    assert REGULAR_PLAN_TIMEOUT < 30


def test_a_rate_limited_regular_plan_raises_the_outage():
    from app.iserv.errors import OutageError

    session, clock = TimetableSession(status_code=429), Clock()
    client = DieSchulAppClient(BASE, session, regular_plans=SharedReads(clock))
    with pytest.raises(OutageError) as raised:
        client.regular_timetable(date(2026, 9, 9), [7001])
    assert raised.value.reason == "rate_limited"


def test_expired_kept_reads_are_dropped_when_a_new_one_is_kept():
    clock = Clock()
    plans = SharedReads(clock, seconds=REGULAR_PLAN_SECONDS)
    plans.put("first", {"a": 1})
    clock.now += REGULAR_PLAN_SECONDS
    plans.put("second", {"b": 2})
    assert list(plans._entries) == ["second"]


def test_a_regular_plan_the_school_refuses_is_not_kept():
    session, clock = TimetableSession(status_code=500), Clock()
    plans = SharedReads(clock, seconds=REGULAR_PLAN_SECONDS)
    reference = date(2026, 9, 9)
    client = DieSchulAppClient(BASE, session, regular_plans=plans)
    assert client.regular_timetable(reference, [7001]) is None
    assert client.regular_timetable(reference, [7001]) is None
    assert len(session.calls) == 2


def test_a_failed_read_is_not_shared():
    class Refusing(FakeSession):
        def get(self, url, params=None, timeout=None):
            self.calls.append((url, params))
            return FakeResponse(None, status_code=500)

    session = Refusing()
    client = shared_client(session, Clock())
    assert client.school_settings() == {}
    assert client.school_settings() == {}
    assert len(session.calls) == 2


def test_the_raising_settings_read_reports_a_school_app_without_answer():
    class Failing(FakeSession):
        def get(self, url, params=None, timeout=None):
            self.calls.append((url, params))
            return FakeResponse(None, status_code=500)

    assert DieSchulAppClient(BASE, FakeSession()).school_settings_or_raise() == DieSchulAppClient(
        BASE, FakeSession()
    ).school_settings()
    with pytest.raises(DataError):
        DieSchulAppClient(BASE, Failing()).school_settings_or_raise()


def test_the_raising_settings_read_refuses_an_unknown_shape():
    class Odd(FakeSession):
        def get(self, url, params=None, timeout=None):
            return FakeResponse("settings")

    with pytest.raises(DataError):
        DieSchulAppClient(BASE, Odd()).school_settings_or_raise()


def test_other_reads_and_other_parameters_are_not_mixed_up():
    session, clock = FakeSession(), Clock()
    client = shared_client(session, clock)
    client._get("timetable-slots/", {"filterBy": "a"})
    client._get("timetable-slots/", {"filterBy": "b"})
    client.pinboards()
    client.pinboards()
    assert len(slot_calls(session)) == 2
    assert len([url for url, _params in session.calls if "pinboards/" in url]) == 2


def test_a_caller_changing_its_copy_does_not_change_the_shared_value():
    session = FakeSession()
    client = shared_client(session, Clock())
    first = client._get("timetable-slots/")
    first.append("changed")
    assert client._get("timetable-slots/") == load("dsa_timetable_slots.json")
