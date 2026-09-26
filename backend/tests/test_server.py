import json
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app import blocks, hanotify, messages, server
from app.absence_service import SickNoteNotFoundError
from app.iserv.errors import DataError, PasswordError
from app.iserv.sick_note_pdf import UnsupportedTextError
from app.server import create_app
from app.store import Store
from tests.support import add_school

SCHOOL = "a1b2c3d4"
CHILD_KEY = f"{SCHOOL}:uuid-1"


class FakeConnection:
    def __init__(self, service):
        self.id = SCHOOL
        self.store = service.store.connection_store(SCHOOL)
        self.service = service

    def display_name(self):
        return "School One"

    def child_key(self, child_id):
        return f"{SCHOOL}:{child_id}"

    def modules(self):
        return self.service.modules()

    def check_connection(self):
        return self.service.connection


class FakeService:
    def __init__(self, store, connection="ok"):
        self.store = store
        self.connection = connection
        if store.connection(SCHOOL) is None:
            add_school(store, connection_id=SCHOOL, children=[{"child_id": "uuid-1", "name": "Mia"}])
        self._connection = FakeConnection(self)

    def is_configured(self):
        return True

    def check_connection(self):
        return self.connection

    def connections(self, include_pending=False):
        return [self._connection]

    def known_connection(self, connection_id):
        if connection_id != SCHOOL:
            raise DataError("unknown connection", message_key="api.connection.unknown")
        return self._connection

    def pick_school(self, connection_id=None):
        return self.known_connection(connection_id) if connection_id else self._connection

    def health_overview(self):
        rows = self.summaries(with_status=True)
        for row in rows:
            row["stale"] = False
        return self.connection, rows

    def summaries(self, with_status=False):
        row = {
            "id": SCHOOL,
            "name": "School One",
            "school_name": "School One",
            "label": "",
            "school_url": "https://school-one.example",
            "host": "school-one.example",
            "setup_complete": True,
            "username": "u",
            "children": [{"child_id": "uuid-1", "name": "Mia", "key": CHILD_KEY, "connection_id": SCHOOL}],
        }
        if with_status:
            row["status"] = self.connection
        return [row]

    def modules_of(self, connection_id):
        return self.modules()

    def change_password(self, connection_id, current, new):
        if current == "wrong":
            raise PasswordError("bad current password")
        return True

    def children(self, connection_id=None):
        return [{"child_id": "uuid-1", "name": "Mia", "key": CHILD_KEY, "connection_id": SCHOOL, "school": "School One"}]

    def timetable_available(self):
        return getattr(self, "timetable_available_value", True)

    def timetable(self, child_key, week_offset=0):
        lessons = [
            {
                "date": "31.08.2026", "day_of_week": 1, "period": 1, "start_time": "08:00",
                "subject_code": "D", "subject_label": "Deutsch", "color": "#111111",
                "teacher_code": "BEH", "teacher_label": "Fr. Behrend", "is_class_teacher": True,
                "room": "R1", "change_kind": "", "changed_fields": [],
                "previous": {"subject": "", "teacher": "", "room": ""},
            },
            {
                "date": "31.08.2026", "day_of_week": 1, "period": 3, "start_time": "09:45",
                "subject_code": "SP", "subject_label": "Sport", "color": "#16a34a",
                "teacher_code": "OTT", "teacher_label": "Hr. Otte", "is_class_teacher": False,
                "room": "GYM", "change_kind": "cancelled", "changed_fields": [],
                "previous": {"subject": "", "teacher": "", "room": ""},
            },
        ]
        return {
            "last_updated": "22.07.2026 12:25",
            "start_date": "31.08.2026",
            "end_date": "06.09.2026",
            "lessons": lessons,
            "changes": [],
            "period_times": {"1": "08:00", "3": "09:45"},
            "change_count": 1,
            "week_offset": week_offset,
        }

    def pinboard(self):
        return {"folders": [{"id": 1, "title": "Board A", "unread": 1, "columns": []}], "feed": []}

    def mark_pinboard_seen(self, keys=None, mark_all=False, unseen=False):
        return {"seen": 3}

    def pinboard_attachment(self, connection_id, filename):
        if "." not in filename:
            raise DataError("invalid filename")

        class Upstream:
            content = b"%PDF"
            headers = {"content-type": "application/pdf", "content-disposition": "attachment; filename=info.pdf"}

        return Upstream()

    def absence_attachment(self, connection_id, filename):
        return self.pinboard_attachment(connection_id, filename)

    def sick_note_pdf(self, connection_id, sick_note_id):
        if str(sick_note_id) == "7":
            raise UnsupportedTextError(["أ", "م"])
        if str(sick_note_id) == "8":
            return b"%PDF-fake", "Schriftliche Bestätigung [Софія Şahin] [02.09.2026].pdf"
        if str(sick_note_id) != "42":
            raise SickNoteNotFoundError("sick note not found")
        return b"%PDF-fake", "Schriftliche Bestätigung der Krankmeldung [Mia] [02.09.2026].pdf"

    def letters(self, tab="current"):
        return {"letters": [{"letter_id": "l1", "recipient_id": "r1", "title": "Letter", "unread": tab == "current"}]}

    def mark_letters_read(self, keys=None, mark_all=False):
        return {"read": len(keys or []) or 7}

    def letter_detail(self, connection_id, letter_id, recipient_id):
        return {"title": "Letter", "body_html": "<p>x</p>", "attachments": [], "archive_url_present": True}

    def archive_letter(self, connection_id, letter_id, recipient_id):
        return True

    def confirm_letter(self, connection_id, letter_id, recipient_id, text=None):
        self.confirm_args = (connection_id, letter_id, recipient_id, text)
        return {"ok": True, "message_key": "api.letters.confirm.ok", "confirmed_at": "2026-09-03T14:05:00"}

    def reply_to_letter(self, connection_id, letter_id, recipient_id, text, request_id, confirmed=False):
        self.reply_args = (connection_id, letter_id, recipient_id, text, request_id, confirmed)
        return {"ok": True, "message_key": "api.letters.reply.ok"}

    def letter_attachment(self, connection_id, attachment_id):
        class Upstream:
            content = b"%PDF"
            headers = {"content-type": "application/pdf", "content-disposition": "attachment; filename=x.pdf"}

        return Upstream()

    def conferences(self):
        return {"empty": True, "items": []}

    def absences_overview(self, connection_id=None):
        return {
            "children": [],
            "types": ["krankmeldung"],
            "deregister_options": [],
            "periods": [{"number": 1, "name": "1. Stunde"}],
            "period_labels": [{"number": 1, "label": "1. Stunde 08:00 - 08:45"}],
            "leave_min_days": 3,
            "notes": [],
            "phones": [],
        }

    def report_absence(self, connection_id, payload, attachments=None):
        if payload.get("type") == "beurlaubungsantrag" and not payload.get("subject"):
            return {"ok": False, "message": "Bitte einen Betreff für den Antrag angeben."}
        self.absence_payload = payload
        self.absence_attachments = attachments
        return {"ok": True, "message": "Meldung eingereicht."}


def client(tmp_path):
    store = Store(tmp_path / "data")
    return TestClient(create_app(FakeService(store))), store


def test_timetable_availability_endpoint(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/timetable-availability").json() == {"available": True}


def test_health(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["connection"] == "ok"


def test_password_change_success(tmp_path):
    api, _ = client(tmp_path)
    response = api.post("/api/password", json={"current": "old-pass", "new": "new-pass-123"})
    assert response.json() == {
        "ok": True,
        "message_key": "api.password.changed",
        "message": "Passwort geändert.",
    }


def test_password_change_rejected(tmp_path):
    api, _ = client(tmp_path)
    response = api.post("/api/password", json={"current": "wrong", "new": "new-pass-123"})
    body = response.json()
    assert body["ok"] is False
    assert body["error"] == "rejected"


def test_password_change_too_short(tmp_path):
    api, _ = client(tmp_path)
    response = api.post("/api/password", json={"current": "old-pass", "new": "short"})
    assert response.json()["error"] == "too_short"


def test_notify_services_endpoint(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/notify-services").json() == {"supervisor": False, "services": []}


def test_config_roundtrip(tmp_path):
    api, _ = client(tmp_path)
    api.post("/api/config", json={"language": "en", "notify_services": ["notify.phone"]})
    body = api.get("/api/config").json()
    assert body["language"] == "en"
    assert body["notify_services"] == ["notify.phone"]
    assert body["connections"][0]["id"] == SCHOOL


def test_config_post_rejects_unknown_keys_with_400(tmp_path):
    api, _ = client(tmp_path)
    response = api.post("/api/config", json={"language": "en", "admin": True, "__proto__": "x"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "unknown_keys"
    assert body["keys"] == ["__proto__", "admin"]


def test_config_post_rejects_per_school_keys_so_they_cannot_land_globally(tmp_path):
    api, _ = client(tmp_path)
    response = api.post("/api/config", json={"school_url": "https://x", "subjects": {}, "connections": []})
    assert response.status_code == 400
    assert response.json()["keys"] == ["connections", "school_url", "subjects"]


def test_config_post_rejecting_unknown_keys_does_not_persist_anything(tmp_path):
    api, _ = client(tmp_path)
    api.post("/api/config", json={"language": "en", "admin": True})
    body = api.get("/api/config").json()
    assert body["language"] == "system"


def test_connection_config_roundtrip(tmp_path):
    api, _ = client(tmp_path)
    view = api.get(f"/api/connections/{SCHOOL}").json()
    assert view["id"] == SCHOOL
    assert view["school_url"] == "https://school-one.example"
    assert view["username"] == "u"
    assert view["children"][0]["key"] == CHILD_KEY
    assert "modules" in view
    response = api.post(f"/api/connections/{SCHOOL}", json={"label": "  Short  name ", "holiday_region": "DE-NI"})
    assert response.status_code == 200
    view = api.get(f"/api/connections/{SCHOOL}").json()
    assert view["label"] == "Short name"
    assert view["holiday_region"] == "DE-NI"


def test_connection_config_rejects_unknown_keys_and_unknown_schools(tmp_path):
    api, _ = client(tmp_path)
    response = api.post(f"/api/connections/{SCHOOL}", json={"school_url": "https://x"})
    assert response.status_code == 400
    assert response.json()["keys"] == ["school_url"]
    assert api.post("/api/connections/deadbeef", json={"label": "x"}).status_code == 404
    assert api.get("/api/connections/deadbeef").json()["error"] == "network"


def test_connection_config_drops_fully_empty_phone_row(tmp_path):
    api, _ = client(tmp_path)
    response = api.post(
        f"/api/connections/{SCHOOL}",
        json={"phones": [{"label": "Oma", "number": "123"}, {"label": "", "number": ""}]},
    )
    assert response.status_code == 200
    body = api.get(f"/api/connections/{SCHOOL}").json()
    assert body["phones"] == [{"label": "Oma", "number": "123"}]


def test_connection_config_rejects_half_filled_phone_row(tmp_path):
    api, _ = client(tmp_path)
    response = api.post(f"/api/connections/{SCHOOL}", json={"phones": [{"label": "Oma", "number": ""}]})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_phones"
    body = api.get(f"/api/connections/{SCHOOL}").json()
    assert body["phones"] == []


def test_connection_config_accepts_subject_color_mapping(tmp_path):
    api, _ = client(tmp_path)
    response = api.post(
        f"/api/connections/{SCHOOL}", json={"subjects": {"D": {"label": "Deutsch", "color": "#ff0000"}}}
    )
    assert response.status_code == 200
    body = api.get(f"/api/connections/{SCHOOL}").json()
    assert body["subjects"]["D"]["color"] == "#ff0000"


def test_the_connection_list_names_every_school(tmp_path):
    api, store = client(tmp_path)
    listed = api.get("/api/connections").json()["connections"]
    assert [row["id"] for row in listed] == [SCHOOL]
    assert listed[0]["name"] == "School One"


def color_api(tmp_path, codes):
    from app.iserv.models import Child, Lesson, TimetableWeek
    from app.service import IServService

    class ColorFakeClient:
        def __init__(self, url):
            self.url = url

        def login(self, username, password, code_provider):
            return self

        def is_authenticated(self):
            return True

        def get_children(self):
            return [Child("uuid-1", "Mia")]

        def get_timetable(self, child_id, reference=None):
            lessons = [
                Lesson("31.08.2026", 1, index + 1, code, "BEH", "R1", "1a")
                for index, code in enumerate(codes)
            ]
            return TimetableWeek("31.08.2026", "06.09.2026", "22.07.2026 12:25", lessons, lessons, [])

    store = Store(tmp_path / "data")
    add_school(store, "https://school.example", connection_id=SCHOOL)
    service = IServService(store, client_factory=lambda url: ColorFakeClient(url))
    return TestClient(create_app(service)), store


def test_picked_subject_color_survives_the_full_config_round_trip_into_the_timetable(tmp_path):
    api, _ = color_api(tmp_path, ["D"])

    api.get("/api/timetable", params={"child": CHILD_KEY})

    picked = api.post(
        f"/api/connections/{SCHOOL}",
        json={"subjects": {"D": {"label": "Deutsch", "color": "#123456", "color_source": "user"}}},
    )
    assert picked.status_code == 200

    config_after_save = api.get(f"/api/connections/{SCHOOL}").json()
    assert config_after_save["subjects"]["D"]["color"] == "#123456"

    timetable_after_save = api.get("/api/timetable", params={"child": CHILD_KEY}).json()
    lesson = timetable_after_save["lessons"][0]
    assert lesson["subject_code"] == "D"
    assert lesson["color"] == "#123456"
    assert lesson["subject_label"] == "Deutsch"


def test_picked_subject_color_survives_even_when_another_subject_has_it(tmp_path):
    codes = ["BIO", "CH", "D", "E", "EK", "GE", "KU", "MA", "MU", "PH", "RE", "SP"]
    api, _ = color_api(tmp_path, codes)

    api.get("/api/timetable", params={"child": CHILD_KEY})
    discovered = api.get(f"/api/connections/{SCHOOL}").json()["subjects"]
    taken = discovered["BIO"]["color"]
    assert taken

    subjects = {code: dict(entry) for code, entry in discovered.items()}
    subjects["SP"] = dict(subjects["SP"], color=taken, color_source="user")
    assert api.post(f"/api/connections/{SCHOOL}", json={"subjects": subjects}).status_code == 200

    api.get("/api/timetable", params={"child": CHILD_KEY})

    config_after_reload = api.get(f"/api/connections/{SCHOOL}").json()
    assert config_after_reload["subjects"]["SP"]["color"] == taken
    assert config_after_reload["subjects"]["SP"]["color_source"] == "user"
    assert config_after_reload["subjects"]["BIO"]["color"]

    lessons = api.get("/api/timetable", params={"child": CHILD_KEY}).json()["lessons"]
    by_code = {entry["subject_code"]: entry["color"] for entry in lessons}
    assert by_code["SP"] == taken

    twinned = {code: dict(entry) for code, entry in config_after_reload["subjects"].items()}
    twinned["MU"] = dict(twinned["MU"], color=taken, color_source="user")
    assert api.post(f"/api/connections/{SCHOOL}", json={"subjects": twinned}).status_code == 200

    api.get("/api/timetable", params={"child": CHILD_KEY})
    twins = api.get(f"/api/connections/{SCHOOL}").json()["subjects"]
    assert twins["SP"]["color"] == taken
    assert twins["MU"]["color"] == taken


def test_reloading_the_timetable_does_not_rewrite_an_untouched_config(tmp_path):
    codes = ["BIO", "CH", "D", "E", "EK", "GE", "KU", "MA", "MU", "PH", "RE", "SP"]
    api, store = color_api(tmp_path, codes)

    api.get("/api/timetable", params={"child": CHILD_KEY})
    before = store.config_path.read_bytes()

    api.get("/api/timetable", params={"child": CHILD_KEY})
    api.get("/api/timetable", params={"child": CHILD_KEY})

    assert store.config_path.read_bytes() == before


def test_newly_discovered_subjects_still_get_a_colour_of_their_own(tmp_path):
    codes = ["BIO", "CH", "D", "E", "EK", "GE", "KU", "MA", "MU", "PH", "RE", "SP"]
    api, _ = color_api(tmp_path, codes)

    api.get("/api/timetable", params={"child": CHILD_KEY})
    subjects = api.get(f"/api/connections/{SCHOOL}").json()["subjects"]

    assert sorted(subjects) == sorted(codes)
    colors = [entry["color"] for entry in subjects.values()]
    assert all(colors)
    assert len(set(colors)) == len(codes)
    assert all(entry["color_source"] == "auto" for entry in subjects.values())


def test_children_and_timetable(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/children").json()[0]["name"] == "Mia"
    assert api.get("/api/timetable", params={"child": CHILD_KEY}).json()["last_updated"] == "22.07.2026 12:25"


def test_timetable_week_parameter_defaults_to_zero(tmp_path):
    api, _ = client(tmp_path)
    body = api.get("/api/timetable", params={"child": CHILD_KEY}).json()
    assert body["week_offset"] == 0
    assert body["change_count"] == 1


def test_timetable_week_parameter_is_passed_through(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/timetable", params={"child": CHILD_KEY, "week": 2}).json()["week_offset"] == 2
    assert api.get("/api/timetable", params={"child": CHILD_KEY, "week": -3}).json()["week_offset"] == -3


def test_timetable_week_parameter_is_clamped(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/timetable", params={"child": CHILD_KEY, "week": 99}).json()["week_offset"] == 8
    assert api.get("/api/timetable", params={"child": CHILD_KEY, "week": -99}).json()["week_offset"] == -8


def test_timetable_week_parameter_rejects_non_numbers(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/timetable", params={"child": CHILD_KEY, "week": "zwei"}).status_code == 422


def test_timetable_lessons_carry_change_information(tmp_path):
    api, _ = client(tmp_path)
    lessons = api.get("/api/timetable", params={"child": CHILD_KEY}).json()["lessons"]
    assert [item["change_kind"] for item in lessons] == ["", "cancelled"]
    assert lessons[0]["previous"] == {"subject": "", "teacher": "", "room": ""}


def test_pinboard_endpoint(tmp_path):
    api, _ = client(tmp_path)
    body = api.get("/api/pinboard").json()
    assert body["folders"][0]["title"] == "Board A"


def test_pinboard_seen_endpoint(tmp_path):
    api, _ = client(tmp_path)
    assert api.post("/api/pinboard/seen", json={"keys": [f"{SCHOOL}:1", f"{SCHOOL}:2"]}).json() == {"seen": 3}


def test_letters_endpoints(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/letters").json()["letters"][0]["title"] == "Letter"
    assert api.get("/api/letters", params={"tab": "archive"}).json()["letters"][0]["unread"] is False
    assert api.post("/api/letters/seen", json={"keys": [f"{SCHOOL}:l1:r1"]}).json() == {"read": 1}
    detail = api.get(
        "/api/letters/detail", params={"letter_id": "l1", "recipient_id": "r1", "connection": SCHOOL}
    ).json()
    assert detail["archive_url_present"] is True
    archived = api.post(
        "/api/letters/archive", json={"connection_id": SCHOOL, "letter_id": "l1", "recipient_id": "r1"}
    )
    assert archived.json() == {"ok": True}


def test_letters_confirm_endpoint_passes_the_ids_and_the_optional_message(tmp_path):
    service = FakeService(Store(tmp_path / "data"))
    api = TestClient(create_app(service))
    base = {"connection_id": SCHOOL, "letter_id": "l1", "recipient_id": "r1"}
    answer = api.post("/api/letters/confirm", json=base).json()
    assert answer["ok"] is True
    assert answer["message_key"] == "api.letters.confirm.ok"
    assert answer["confirmed_at"] == "2026-09-03T14:05:00"
    assert service.confirm_args == (SCHOOL, "l1", "r1", None)
    api.post("/api/letters/confirm", json=dict(base, text="danke"))
    assert service.confirm_args == (SCHOOL, "l1", "r1", "danke")
    api.post("/api/letters/confirm", json=dict(base, text=5))
    assert service.confirm_args == (SCHOOL, "l1", "r1", None)


def test_letters_reply_endpoint_trims_the_text_and_passes_only_a_literal_confirmation(tmp_path):
    from app import letter_routes

    service = FakeService(Store(tmp_path / "data"))
    api = TestClient(create_app(service))
    base = {"connection_id": SCHOOL, "letter_id": "l1", "recipient_id": "r1", "request_id": "a" * 32}
    answer = api.post("/api/letters/reply", json=dict(base, text="  Danke  ", confirmed=True)).json()
    assert answer["ok"] is True
    assert service.reply_args == (SCHOOL, "l1", "r1", "Danke", "a" * 32, True)
    api.post("/api/letters/reply", json=dict(base, text="Danke", confirmed="true"))
    assert service.reply_args[5] is False
    api.post("/api/letters/reply", json=dict(base, text=5))
    assert service.reply_args[3:] == ("", "a" * 32, False)
    service.reply_args = None
    refused = api.post(
        "/api/letters/reply",
        json=dict(base, text="x" * (letter_routes.LETTER_REPLY_MAX_LENGTH + 1), confirmed=True),
    ).json()
    assert refused["ok"] is False
    assert refused["message_key"] == "api.letters.reply.tooLong"
    assert refused["message_vars"] == {"max": letter_routes.LETTER_REPLY_MAX_LENGTH}
    assert service.reply_args is None


def test_letters_attachment_proxies_content(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/api/letters/attachment/abc123")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content == b"%PDF"


def test_an_unknown_letter_attachment_answers_with_the_short_note(tmp_path, monkeypatch):
    api, _ = client(tmp_path)

    def refused(self, connection_id, attachment_id):
        raise DataError("the attachment is not listed", message_key="api.letters.unknown")

    monkeypatch.setattr(FakeService, "letter_attachment", refused)
    response = api.get("/api/letters/attachment/abc123")
    assert response.status_code == 404
    assert response.json()["message_key"] == "api.letters.unknown"


def test_pinboard_attachment_proxies_content(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/api/pinboard/attachment/abcdef01-42.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"] == "attachment; filename=info.pdf"
    assert response.content == b"%PDF"


def test_pinboard_attachment_rejects_invalid_filename(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/pinboard/attachment/no-extension").status_code == 400


def test_pinboard_attachment_with_umlauts_and_spaces_proxies_content_and_headers_unchanged(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/api/pinboard/attachment/" + quote("Bücher Eigenanteil Klasse 1_Neu.pdf"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"] == "attachment; filename=info.pdf"
    assert response.content == b"%PDF"


def test_absence_attachment_proxies_content(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/api/absences/attachment/abcdef01-42.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"] == "attachment; filename=info.pdf"
    assert response.content == b"%PDF"


def test_absence_attachment_rejects_invalid_filename(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/absences/attachment/no-extension").status_code == 400


def test_sick_note_pdf_serves_owned_note_inline(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/api/absences/sick-note-pdf", params={"id": "42"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.content == b"%PDF-fake"


def test_sick_note_pdf_rejects_id_that_does_not_belong_to_the_user(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/api/absences/sick-note-pdf", params={"id": "999"})
    assert response.status_code == 404


def test_sick_note_pdf_refuses_instead_of_serving_a_broken_document(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/api/absences/sick-note-pdf", params={"id": "7"})
    assert response.status_code == 422
    assert not response.content.startswith(b"%PDF")


def test_sick_note_pdf_disposition_carries_foreign_names_utf8_encoded(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/api/absences/sick-note-pdf", params={"id": "8"})
    disposition = response.headers["content-disposition"]
    filename = "Schriftliche Bestätigung [Софія Şahin] [02.09.2026].pdf"
    assert disposition.endswith("filename*=UTF-8''" + quote(filename, safe=""))
    assert "?" not in disposition
    assert chr(13) not in disposition and chr(10) not in disposition
    ascii_part = disposition.split('filename="', 1)[1].split('"', 1)[0]
    assert ascii_part.isascii()
    assert "Schriftliche Bestatigung" in ascii_part


def test_notify_test_success(tmp_path, monkeypatch):
    captured = {}

    def fake_notify(message, service=None, title="Ranzenpost"):
        captured["args"] = (message, service)
        captured["title"] = title
        return True

    monkeypatch.setattr(hanotify, "notify", fake_notify)
    api, _ = client(tmp_path)
    response = api.post("/api/notify-test", json={"service": "notify.mobile_app_test"})
    assert response.json() == {
        "ok": True,
        "message_key": "api.notify.sent",
        "message": "Testbenachrichtigung gesendet.",
    }
    assert captured["args"] == (
        messages.text_in("de", "notify.test.message"),
        "notify.mobile_app_test",
    )
    assert captured["title"] == messages.text_in("de", "notify.test.title")


def test_notify_test_uses_the_requested_language_for_the_push_text(tmp_path, monkeypatch):
    captured = {}

    def fake_notify(message, service=None, title="Ranzenpost"):
        captured["message"] = message
        captured["title"] = title
        return True

    monkeypatch.setattr(hanotify, "notify", fake_notify)
    api, _ = client(tmp_path)
    api.post("/api/notify-test", json={"service": "notify.mobile_app_test", "language": "uk"})

    assert captured["message"] == messages.text_in("uk", "notify.test.message")
    assert captured["title"] == messages.text_in("uk", "notify.test.title")
    assert captured["message"] != messages.text_in("de", "notify.test.message")


def test_notify_test_falls_back_to_the_base_language_for_an_unknown_tag(tmp_path, monkeypatch):
    captured = {}

    def fake_notify(message, service=None, title="Ranzenpost"):
        captured["message"] = message
        return True

    monkeypatch.setattr(hanotify, "notify", fake_notify)
    api, _ = client(tmp_path)
    api.post("/api/notify-test", json={"service": "notify.mobile_app_test", "language": "../../etc"})

    assert captured["message"] == messages.text_in("de", "notify.test.message")


def test_notify_test_carries_no_hardcoded_user_facing_text():
    source = Path(server.__file__).read_text(encoding="utf-8")
    assert "Testbenachrichtigung von" not in source
    assert messages.text_in("de", "notify.test.message") not in source


def test_notify_test_reports_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(hanotify, "notify", lambda *args, **kwargs: False)
    api, _ = client(tmp_path)
    body = api.post("/api/notify-test", json={"service": "notify.unknown"}).json()
    assert body == {
        "ok": False,
        "message_key": "api.notify.failed",
        "message": "Senden fehlgeschlagen. Prüfe den Dienst-Namen.",
    }


def test_notify_test_survives_exceptions(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("supervisor unreachable")

    monkeypatch.setattr(hanotify, "notify", boom)
    api, _ = client(tmp_path)
    assert api.post("/api/notify-test", json={"service": ""}).json()["ok"] is False


def test_conferences_endpoint(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/conferences").json()["empty"] is True


def test_absences_endpoints(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/absences").json()["types"] == ["krankmeldung"]
    assert api.post("/api/absences", json={"type": "krankmeldung"}).json()["ok"] is True


def test_absences_overview_exposes_period_labels_and_min_days(tmp_path):
    api, _ = client(tmp_path)
    body = api.get("/api/absences").json()
    assert body["period_labels"] == [{"number": 1, "label": "1. Stunde 08:00 - 08:45"}]
    assert body["leave_min_days"] == 3


def test_absences_post_forwards_real_fields(tmp_path):
    api, _ = client(tmp_path)
    payload = {
        "type": "abmeldung_ganztagsbetreuung",
        "student_id": 7,
        "daycare_kind": "early_end",
        "date": "2026-09-05",
        "repeat": "weekly",
        "reason": "Sport",
    }
    assert api.post("/api/absences", json=payload).json()["ok"] is True


def test_absences_post_accepts_multipart_leave_request_with_attachments(tmp_path):
    service = FakeService(Store(tmp_path / "data"))
    api = TestClient(create_app(service))
    payload = {
        "type": "beurlaubungsantrag",
        "student_id": 7,
        "subject": "Test",
        "body": "Text",
        "from_date": "2026-09-30",
    }
    response = api.post(
        "/api/absences",
        data={"data": json.dumps(payload)},
        files=[("files", ("beleg.pdf", b"%PDF-1", "application/pdf"))],
    )
    assert response.json()["ok"] is True
    assert service.absence_payload["subject"] == "Test"
    assert service.absence_attachments == [
        {"filename": "beleg.pdf", "content": b"%PDF-1", "content_type": "application/pdf"}
    ]


def test_absences_post_rejects_a_single_attachment_over_the_per_file_limit(tmp_path):
    service = FakeService(Store(tmp_path / "data"))
    api = TestClient(create_app(service))
    payload = {"type": "beurlaubungsantrag", "student_id": 7, "subject": "Test", "body": "Text"}
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    response = api.post(
        "/api/absences",
        data={"data": json.dumps(payload)},
        files=[("files", ("big.pdf", oversized, "application/pdf"))],
    )
    body = response.json()
    assert body["ok"] is False
    assert body["message_key"] == "api.absence.error.attachmentTooLarge"
    assert not hasattr(service, "absence_attachments")


def test_absences_post_rejects_attachments_over_the_total_limit(tmp_path):
    service = FakeService(Store(tmp_path / "data"))
    api = TestClient(create_app(service))
    payload = {"type": "beurlaubungsantrag", "student_id": 7, "subject": "Test", "body": "Text"}
    chunk = b"x" * (9 * 1024 * 1024)
    response = api.post(
        "/api/absences",
        data={"data": json.dumps(payload)},
        files=[
            ("files", (f"f{index}.pdf", chunk, "application/pdf"))
            for index in range(5)
        ],
    )
    body = response.json()
    assert body["ok"] is False
    assert body["message_key"] == "api.absence.error.attachmentTooLarge"
    assert not hasattr(service, "absence_attachments")


def test_absences_post_returns_field_specific_error(tmp_path):
    api, _ = client(tmp_path)
    response = api.post("/api/absences", json={"type": "beurlaubungsantrag", "subject": "", "body": "Text"})
    assert response.json() == {"ok": False, "message": "Bitte einen Betreff für den Antrag angeben."}


def test_index_serves_html(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/")
    assert response.status_code == 200
    assert "Ranzenpost" in response.text


class FakeWizard:
    def __init__(self):
        self.child_args = None

    def status(self):
        return {"step": "url"}

    def set_url(self, url):
        return {"step": "login", "school_url": url}

    def set_login(self, username, password):
        return {"step": "connect"}

    def connect(self, code):
        return {"step": "child", "code": code}

    def select_child(self, child_id, name="", class_name=""):
        self.child_args = (child_id, name, class_name)
        return {"step": "done"}

    def skip_child(self):
        self.skip_child_called = True
        return {"step": "done"}

    def back(self):
        return {"step": "login"}

    def reset(self, connection_id=None):
        return {"step": "url"}


def test_wizard_endpoints(tmp_path):
    store = Store(tmp_path / "data")
    fake = FakeWizard()
    api = TestClient(create_app(FakeService(store), wizard=fake))
    assert api.get("/api/wizard").json()["step"] == "url"
    assert api.post("/api/wizard/url", json={"url": "x"}).json()["step"] == "login"
    assert api.post("/api/wizard/login", json={"username": "u", "password": "p"}).json()["step"] == "connect"
    assert api.post("/api/wizard/connect", json={"code": "123456"}).json()["step"] == "child"
    assert api.post("/api/wizard/child", json={"child_id": "c", "name": "Bella", "class_name": "2b"}).json()["step"] == "done"
    assert fake.child_args == ("c", "Bella", "2b")
    assert api.post("/api/wizard/skip-child").json()["step"] == "done"
    assert fake.skip_child_called is True
    assert api.post("/api/wizard/back").json()["step"] == "login"
    assert api.post("/api/wizard/reset").json()["step"] == "url"



def test_frontend_is_never_cached(tmp_path):
    api, _ = client(tmp_path)
    for path in ("/", "/api/health"):
        response = api.get(path)
        assert "no-store" in response.headers.get("cache-control", "")


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@pytest.mark.parametrize("path", ["/app.js", "/lib/globals.js", "/lib/i18n.js"])
def test_a_frontend_script_is_served_as_javascript_and_never_cached(tmp_path, path):
    store = Store(tmp_path / "data")
    api = TestClient(create_app(FakeService(store), frontend_dir=str(FRONTEND_DIR)))
    response = api.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0].strip() == "text/javascript"
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_csp_has_no_external_font_hosts(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/api/health")
    csp = response.headers.get("content-security-policy", "")
    assert "fonts.googleapis.com" not in csp
    assert "fonts.gstatic.com" not in csp


def test_csp_header_exact_value(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/api/health")
    assert response.headers.get("content-security-policy") == (
        "default-src 'self'; "
        "img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; "
        "script-src 'self'; "
        "connect-src 'self'; "
        "frame-src blob:; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "form-action 'none'"
    )


def test_index_html_has_no_google_fonts_link():
    index_html = (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis" not in index_html


def test_health_and_the_registry_route_carry_the_module_registry(tmp_path):
    api, store = client(tmp_path)
    health = api.get("/api/health").json()
    assert health["modules"]["modules"] == {
        "timetable": True,
        "letters": True,
        "pinboard": True,
        "absences": True,
        "conferences": True,
        "messenger": True,
    }
    assert health["modules"]["unknown"] == []
    assert api.get("/api/modules").json() == health["modules"]
    assert "version" in health


def test_the_timetable_availability_route_is_an_alias_of_the_registry(tmp_path):
    api, store = client(tmp_path)
    stored = {
        "modules": {"timetable": False, "letters": True, "pinboard": True, "absences": True, "conferences": True, "messenger": True},
        "unknown": [{"segment": "mail", "label": "E-Mail"}],
        "checked_at": 10,
        "iserv_version": "3.9",
    }
    api.app.state.service_modules = stored
    FakeService.modules = lambda self: stored
    try:
        assert api.get("/api/timetable-availability").json() == {"available": False}
        assert api.get("/api/health").json()["modules"]["unknown"] == [{"segment": "mail", "label": "E-Mail"}]
    finally:
        del FakeService.modules


def test_connection_short_name_is_saved_trimmed_and_capped_and_defaults_to_the_host(tmp_path):
    api, _ = client(tmp_path)
    view = api.get(f"/api/connections/{SCHOOL}").json()
    assert view["short_name"] == ""
    response = api.post(f"/api/connections/{SCHOOL}", json={"short_name": "  Gym   Süd  "})
    assert response.status_code == 200
    assert api.get(f"/api/connections/{SCHOOL}").json()["short_name"] == "Gym Süd"
    api.post(f"/api/connections/{SCHOOL}", json={"short_name": "x" * 80})
    assert len(api.get(f"/api/connections/{SCHOOL}").json()["short_name"]) == 30
    api.post(f"/api/connections/{SCHOOL}", json={"short_name": ""})
    assert api.get(f"/api/connections/{SCHOOL}").json()["short_name"] == ""


def test_config_serves_layout_defaults_for_a_fresh_store(tmp_path):
    api, _ = client(tmp_path)
    body = api.get("/api/config").json()
    assert body["overview_blocks"] == blocks.default_overview_blocks()
    assert body["navigation"] == list(blocks.DEFAULT_NAVIGATION)
    assert body["modules_disabled"] == []


def test_config_post_validates_the_layout_keys(tmp_path):
    api, _ = client(tmp_path)
    response = api.post(
        "/api/config",
        json={
            "overview_blocks": [{"key": "chat", "size": "compact"}, {"key": "today"}, {"key": "bogus"}],
            "navigation": ["messenger", "bogus"],
            "modules_disabled": ["messenger", "bogus"],
        },
    )
    assert response.status_code == 200
    body = api.get("/api/config").json()
    assert body["overview_blocks"] == [{"key": "today", "size": "normal"}]
    assert body["navigation"] == ["messenger", "timetable", "absence", "post", "conferences"]
    assert body["modules_disabled"] == ["messenger"]


def test_an_empty_overview_list_is_kept_as_empty(tmp_path):
    api, _ = client(tmp_path)
    api.post("/api/config", json={"overview_blocks": []})
    assert api.get("/api/config").json()["overview_blocks"] == []


def test_a_saved_layout_from_before_the_new_default_is_kept_as_is(tmp_path):
    api, _ = client(tmp_path)
    old_full_layout = [{"key": block["key"], "size": block["size"]} for block in blocks.BLOCKS]
    api.post("/api/config", json={"overview_blocks": old_full_layout})
    saved = api.get("/api/config").json()["overview_blocks"]
    assert saved == old_full_layout
    assert len(saved) == len(blocks.BLOCK_KEYS) > len(blocks.DEFAULT_OVERVIEW_KEYS)


def test_a_letter_message_is_trimmed_and_a_too_long_one_is_refused(tmp_path):
    from app import letter_routes

    service = FakeService(Store(tmp_path / "data"))
    sent = []
    service.confirm_letter = lambda connection_id, letter_id, recipient_id, text=None: sent.append(text) or {"ok": True}
    api = TestClient(create_app(service))
    identity = {"letter_id": "1", "recipient_id": "2"}
    api.post("/api/letters/confirm", json=dict(identity, text="  Danke  "))
    api.post("/api/letters/confirm", json=dict(identity, text="   "))
    refused = api.post("/api/letters/confirm", json=dict(identity, text="x" * (letter_routes.LETTER_REPLY_MAX_LENGTH + 1))).json()
    assert sent == ["Danke", None]
    assert refused["message_key"] == "api.letters.confirm.tooLong"
