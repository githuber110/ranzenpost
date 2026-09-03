import json
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from app import hanotify, messages, server
from app.iserv.errors import DataError, PasswordError
from app.iserv.sick_note_pdf import UnsupportedTextError
from app.server import create_app
from app.service import SickNoteNotFoundError
from app.store import Store


class FakeService:
    def __init__(self, store, connection="ok"):
        self.store = store
        self.connection = connection

    def is_configured(self):
        return True

    def check_connection(self):
        return self.connection

    def change_password(self, current, new):
        if current == "wrong":
            raise PasswordError("bad current password")
        return True

    def children(self):
        return [{"child_id": "uuid-1", "name": "Mia"}]

    def timetable_available(self):
        return getattr(self, "timetable_available_value", True)

    def timetable(self, child_id, week_offset=0):
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

    def mark_pinboard_seen(self, tile_ids=None, mark_all=False, unseen=False):
        return {"seen": 3}

    def pinboard_attachment(self, filename):
        if "." not in filename:
            raise DataError("invalid filename")

        class Upstream:
            content = b"%PDF"
            headers = {"content-type": "application/pdf", "content-disposition": "attachment; filename=info.pdf"}

        return Upstream()

    def absence_attachment(self, filename):
        return self.pinboard_attachment(filename)

    def sick_note_pdf(self, sick_note_id):
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

    def letter_detail(self, letter_id, recipient_id):
        return {"title": "Letter", "body_html": "<p>x</p>", "attachments": [], "archive_url_present": True}

    def archive_letter(self, letter_id, recipient_id):
        return True

    def letter_attachment(self, attachment_id):
        class Upstream:
            content = b"%PDF"
            headers = {"content-type": "application/pdf", "content-disposition": "attachment; filename=x.pdf"}

        return Upstream()

    def conferences(self):
        return {"empty": True, "items": []}

    def absences_overview(self):
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

    def report_absence(self, payload, attachments=None):
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
    api.post("/api/config", json={"school_url": "https://x", "subjects": {}})
    assert api.get("/api/config").json()["school_url"] == "https://x"


def test_config_post_rejects_unknown_keys_with_400(tmp_path):
    api, _ = client(tmp_path)
    response = api.post("/api/config", json={"school_url": "https://x", "admin": True, "__proto__": "x"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "unknown_keys"
    assert body["keys"] == ["__proto__", "admin"]


def test_config_post_rejecting_unknown_keys_does_not_persist_anything(tmp_path):
    api, _ = client(tmp_path)
    api.post("/api/config", json={"school_url": "https://x", "admin": True})
    body = api.get("/api/config").json()
    assert body["school_url"] == ""


def test_config_post_drops_fully_empty_phone_row(tmp_path):
    api, _ = client(tmp_path)
    response = api.post("/api/config", json={"phones": [{"label": "Oma", "number": "123"}, {"label": "", "number": ""}]})
    assert response.status_code == 200
    body = api.get("/api/config").json()
    assert body["phones"] == [{"label": "Oma", "number": "123"}]


def test_config_post_rejects_half_filled_phone_row(tmp_path):
    api, _ = client(tmp_path)
    response = api.post("/api/config", json={"phones": [{"label": "Oma", "number": ""}]})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_phones"
    body = api.get("/api/config").json()
    assert body["phones"] == []


def test_config_post_accepts_subject_color_mapping(tmp_path):
    api, _ = client(tmp_path)
    response = api.post("/api/config", json={"subjects": {"D": {"label": "Deutsch", "color": "#ff0000"}}})
    assert response.status_code == 200
    body = api.get("/api/config").json()
    assert body["subjects"]["D"]["color"] == "#ff0000"


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
    store.save_config({"school_url": "https://school.example"})
    store.save_secrets({"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP"})
    service = IServService(store, client_factory=lambda url: ColorFakeClient(url))
    return TestClient(create_app(service)), store


def test_picked_subject_color_survives_the_full_config_round_trip_into_the_timetable(tmp_path):
    api, _ = color_api(tmp_path, ["D"])

    api.get("/api/timetable", params={"child_id": "uuid-1"})

    picked = api.post(
        "/api/config",
        json={"subjects": {"D": {"label": "Deutsch", "color": "#2486ed", "color_source": "user"}}},
    )
    assert picked.status_code == 200

    config_after_save = api.get("/api/config").json()
    assert config_after_save["subjects"]["D"]["color"] == "#2486ed"

    timetable_after_save = api.get("/api/timetable", params={"child_id": "uuid-1"}).json()
    lesson = timetable_after_save["lessons"][0]
    assert lesson["subject_code"] == "D"
    assert lesson["color"] == "#2486ed"
    assert lesson["subject_label"] == "Deutsch"


def test_picked_subject_color_survives_even_when_another_subject_has_it(tmp_path):
    codes = ["BIO", "CH", "D", "E", "EK", "GE", "KU", "MA", "MU", "PH", "RE", "SP"]
    api, _ = color_api(tmp_path, codes)

    api.get("/api/timetable", params={"child_id": "uuid-1"})
    discovered = api.get("/api/config").json()["subjects"]
    taken = discovered["BIO"]["color"]
    assert taken

    subjects = {code: dict(entry) for code, entry in discovered.items()}
    subjects["SP"] = dict(subjects["SP"], color=taken, color_source="user")
    assert api.post("/api/config", json={"subjects": subjects}).status_code == 200

    api.get("/api/timetable", params={"child_id": "uuid-1"})

    config_after_reload = api.get("/api/config").json()
    assert config_after_reload["subjects"]["SP"]["color"] == taken
    assert config_after_reload["subjects"]["SP"]["color_source"] == "user"
    assert config_after_reload["subjects"]["BIO"]["color"]

    lessons = api.get("/api/timetable", params={"child_id": "uuid-1"}).json()["lessons"]
    by_code = {entry["subject_code"]: entry["color"] for entry in lessons}
    assert by_code["SP"] == taken

    twinned = {code: dict(entry) for code, entry in config_after_reload["subjects"].items()}
    twinned["MU"] = dict(twinned["MU"], color=taken, color_source="user")
    assert api.post("/api/config", json={"subjects": twinned}).status_code == 200

    api.get("/api/timetable", params={"child_id": "uuid-1"})
    twins = api.get("/api/config").json()["subjects"]
    assert twins["SP"]["color"] == taken
    assert twins["MU"]["color"] == taken


def test_reloading_the_timetable_does_not_rewrite_an_untouched_config(tmp_path):
    codes = ["BIO", "CH", "D", "E", "EK", "GE", "KU", "MA", "MU", "PH", "RE", "SP"]
    api, store = color_api(tmp_path, codes)

    api.get("/api/timetable", params={"child_id": "uuid-1"})
    before = store.config_path.read_bytes()

    api.get("/api/timetable", params={"child_id": "uuid-1"})
    api.get("/api/timetable", params={"child_id": "uuid-1"})

    assert store.config_path.read_bytes() == before


def test_newly_discovered_subjects_still_get_a_colour_of_their_own(tmp_path):
    codes = ["BIO", "CH", "D", "E", "EK", "GE", "KU", "MA", "MU", "PH", "RE", "SP"]
    api, _ = color_api(tmp_path, codes)

    api.get("/api/timetable", params={"child_id": "uuid-1"})
    subjects = api.get("/api/config").json()["subjects"]

    assert sorted(subjects) == sorted(codes)
    colors = [entry["color"] for entry in subjects.values()]
    assert all(colors)
    assert len(set(colors)) == len(codes)
    assert all(entry["color_source"] == "auto" for entry in subjects.values())


def test_children_and_timetable(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/children").json()[0]["name"] == "Mia"
    assert api.get("/api/timetable", params={"child_id": "uuid-1"}).json()["last_updated"] == "22.07.2026 12:25"


def test_timetable_week_parameter_defaults_to_zero(tmp_path):
    api, _ = client(tmp_path)
    body = api.get("/api/timetable", params={"child_id": "uuid-1"}).json()
    assert body["week_offset"] == 0
    assert body["change_count"] == 1


def test_timetable_week_parameter_is_passed_through(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/timetable", params={"child_id": "uuid-1", "week": 2}).json()["week_offset"] == 2
    assert api.get("/api/timetable", params={"child_id": "uuid-1", "week": -3}).json()["week_offset"] == -3


def test_timetable_week_parameter_is_clamped(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/timetable", params={"child_id": "uuid-1", "week": 99}).json()["week_offset"] == 8
    assert api.get("/api/timetable", params={"child_id": "uuid-1", "week": -99}).json()["week_offset"] == -8


def test_timetable_week_parameter_rejects_non_numbers(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/timetable", params={"child_id": "uuid-1", "week": "zwei"}).status_code == 422


def test_timetable_lessons_carry_change_information(tmp_path):
    api, _ = client(tmp_path)
    lessons = api.get("/api/timetable", params={"child_id": "uuid-1"}).json()["lessons"]
    assert [item["change_kind"] for item in lessons] == ["", "cancelled"]
    assert lessons[0]["previous"] == {"subject": "", "teacher": "", "room": ""}


def test_pinboard_endpoint(tmp_path):
    api, _ = client(tmp_path)
    body = api.get("/api/pinboard").json()
    assert body["folders"][0]["title"] == "Board A"


def test_pinboard_seen_endpoint(tmp_path):
    api, _ = client(tmp_path)
    assert api.post("/api/pinboard/seen", json={"tile_ids": [1, 2]}).json() == {"seen": 3}


def test_letters_endpoints(tmp_path):
    api, _ = client(tmp_path)
    assert api.get("/api/letters").json()["letters"][0]["title"] == "Letter"
    assert api.get("/api/letters", params={"tab": "archive"}).json()["letters"][0]["unread"] is False
    assert api.post("/api/letters/seen", json={"keys": ["l1:r1"]}).json() == {"read": 1}
    detail = api.get("/api/letters/detail", params={"letter_id": "l1", "recipient_id": "r1"}).json()
    assert detail["archive_url_present"] is True
    assert api.post("/api/letters/archive", json={"letter_id": "l1", "recipient_id": "r1"}).json() == {"ok": True}


def test_letters_attachment_proxies_content(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/api/letters/attachment/abc123")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content == b"%PDF"


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

    def reset(self):
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


def test_csp_has_no_external_font_hosts(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/api/health")
    csp = response.headers.get("content-security-policy", "")
    assert "fonts.googleapis.com" not in csp
    assert "fonts.gstatic.com" not in csp


def test_index_html_has_no_google_fonts_link():
    index_html = (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis" not in index_html
