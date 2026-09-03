import json
from pathlib import Path

from app.iserv.dsa import (
    DieSchulAppClient,
    absence_rules,
    class_for_name,
    deregister_options,
    enabled_absence_types,
    normalize_class,
    parse_period_times,
    parse_pinboards,
    parse_students,
)

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://school.example"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

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


def test_class_for_name_matches_regardless_of_word_order():
    students = parse_students(load("dsa_students.json"))
    assert class_for_name(students, "Alex Example") == "2B"
    assert class_for_name(students, "Example Alex") == "2B"
    assert class_for_name(students, "Someone Else") == ""


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
