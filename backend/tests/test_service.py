from datetime import date, timedelta
from urllib.parse import quote

import pytest
import requests

from app.iserv.errors import DataError, TwoFactorError
from app.iserv.models import Child, Lesson, TimetableWeek
from app.iserv.timetable import detect_changes
from app.service import IServService, NotConfiguredError, SickNoteNotFoundError
from app.store import Store


class FakeClient:
    def __init__(self, url):
        self.url = url
        self.authed = False
        self.password_args = None

    def login(self, username, password, code_provider):
        assert code_provider()
        self.authed = True
        return self

    def is_authenticated(self):
        return self.authed

    def change_password(self, current, new):
        self.password_args = (current, new)
        return True

    def get_children(self):
        return [Child("uuid-1", "Mia")]

    def get_timetable(self, child_id, reference=None):
        lessons = [Lesson("31.08.2026", 1, 1, "D", "BEH", "R1", "1a")]
        return TimetableWeek("31.08.2026", "06.09.2026", "22.07.2026 12:25", lessons, lessons, [])


def make(tmp_path, configured=True):
    store = Store(tmp_path / "data")
    if configured:
        store.save_config({"school_url": "https://school.example"})
        store.save_secrets({"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP"})
    return IServService(store, client_factory=lambda url: FakeClient(url)), store


def test_children(tmp_path):
    service, _ = make(tmp_path)
    assert service.children() == [{
        "child_id": "uuid-1",
        "name": "Mia",
        "class_name": "",
        "student_id": None,
        "class_full": "",
        "class_code": "",
    }]


def test_children_enriched_with_class_and_student_id(tmp_path):
    service, _ = make(tmp_path)
    service._dsa = lambda: type("D", (), {"students": lambda self=None: [
        {"id": 99, "name": "Mia", "class_name": "2b", "class_full": "Klasse 02B", "class_code": "klasse.02b"}
    ]})()
    assert service.children() == [{
        "child_id": "uuid-1",
        "name": "Mia",
        "class_name": "2b",
        "student_id": 99,
        "class_full": "Klasse 02B",
        "class_code": "klasse.02b",
    }]


def test_timetable_autofills_new_codes(tmp_path):
    service, store = make(tmp_path)
    result = service.timetable("uuid-1")
    assert result["last_updated"] == "22.07.2026 12:25"
    assert result["lessons"][0]["subject_code"] == "D"
    saved = store.load_config()
    assert "D" in saved["subjects"]
    assert "BEH" in saved["teachers"]


def test_not_configured_raises(tmp_path):
    service, _ = make(tmp_path, configured=False)
    with pytest.raises(NotConfiguredError):
        service.children()


def test_check_connection_ok(tmp_path):
    service, _ = make(tmp_path)
    assert service.check_connection() == "ok"


def test_check_connection_not_configured(tmp_path):
    service, _ = make(tmp_path, configured=False)
    assert service.check_connection() == "not_configured"


def test_check_connection_auth_failed(tmp_path):
    store = Store(tmp_path / "data")
    store.save_config({"school_url": "https://school.example"})
    store.save_secrets({"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP"})

    def factory(url):
        client = FakeClient(url)

        def boom(*args, **kwargs):
            raise TwoFactorError("token gone")

        client.login = boom
        return client

    service = IServService(store, client_factory=factory)
    assert service.check_connection() == "auth_failed"


def test_check_connection_network(tmp_path):
    store = Store(tmp_path / "data")
    store.save_config({"school_url": "https://school.example"})
    store.save_secrets({"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP"})

    def factory(url):
        client = FakeClient(url)

        def boom(*args, **kwargs):
            raise requests.ConnectionError("down")

        client.login = boom
        return client

    service = IServService(store, client_factory=factory)
    assert service.check_connection() == "network"


def test_change_password_updates_stored_password(tmp_path):
    captured = {}

    def factory(url):
        client = FakeClient(url)
        original = client.change_password

        def record(current, new):
            captured["args"] = (current, new)
            return original(current, new)

        client.change_password = record
        return client

    service, store = make(tmp_path)
    service.client_factory = factory
    service.change_password("old-pass", "new-pass-123")
    assert captured["args"] == ("old-pass", "new-pass-123")
    assert store.load_secrets()["password"] == "new-pass-123"


from app.iserv.dsa import Attachment, Pinboard, PinboardColumn, Tile


class FakeDsa:
    def __init__(self, boards):
        self._boards = boards

    def pinboards(self):
        return self._boards


def _board():
    return Pinboard(
        id=1,
        title="Board A",
        columns=[
            PinboardColumn(id=10, title="Termine", tiles=[
                Tile(id=100, title="T1", text="hello world", color="", owner="X", attachments=[]),
                Tile(id=101, title="T2", text="second", color="", owner="X",
                     attachments=[Attachment(5, "f.pdf", "pdf", "application/pdf", 10)]),
            ])
        ],
        attachments=[],
    )


def test_pinboard_feed_is_newest_first_and_starts_fully_seen(tmp_path):
    service, store = make(tmp_path)
    service._dsa = lambda: FakeDsa([_board()])
    result = service.pinboard()
    assert [t["id"] for t in result["feed"]] == [101, 100]
    assert result["folders"][0]["unread"] == 0
    assert store.load_seen()["pinboard_initialised"] is True
    assert result["feed"][0]["folder_title"] == "Board A"
    assert result["feed"][0]["attachments"][0]["extension"] == "pdf"


def test_pinboard_marking_a_tile_unseen_makes_it_unread_again(tmp_path):
    service, store = make(tmp_path)
    service._dsa = lambda: FakeDsa([_board()])
    service.pinboard()
    service.mark_pinboard_seen(tile_ids=[101], unseen=True)
    result = service.pinboard()
    assert result["folders"][0]["unread"] == 1
    assert next(t for t in result["feed"] if t["id"] == 101)["unread"] is True


def test_pinboard_mark_all_seen(tmp_path):
    service, store = make(tmp_path)
    service._dsa = lambda: FakeDsa([_board()])
    service.mark_pinboard_seen(mark_all=True)
    result = service.pinboard()
    assert result["folders"][0]["unread"] == 0


def test_letters_unread_annotation_and_seen_toggle(tmp_path):
    from pathlib import Path as _Path

    fixture = (_Path(__file__).parent / "fixtures" / "letters_index.html").read_text(encoding="utf-8")

    class LetterClient(FakeClient):
        def fetch(self, path, params=None):
            class R:
                pass

            r = R()
            r.text = fixture
            r.url = "https://school.example" + path
            return r

    service, store = make(tmp_path)
    service.client_factory = lambda url: LetterClient(url)
    data = service.letters("current")
    assert data["letters"]
    unread = [entry for entry in data["letters"] if entry["unread"]]
    assert len(unread) == 1, "IServ marks exactly one row in the fixture"
    assert unread[0]["title"] == "Informationen zum Wandertag"


def test_enrich_letters_search_indexes_body_and_attachments(tmp_path):
    from pathlib import Path as _Path

    list_fixture = (_Path(__file__).parent / "fixtures" / "letters_index.html").read_text(encoding="utf-8")
    detail_fixture = (_Path(__file__).parent / "fixtures" / "letter_detail.html").read_text(encoding="utf-8")

    class LetterClient(FakeClient):
        def fetch(self, path, params=None):
            class R:
                status_code = 200
                url = "https://school.example" + path
                text = detail_fixture if "/parent/show/" in path else list_fixture

            return R()

    service, store = make(tmp_path)
    service.client_factory = lambda url: LetterClient(url)

    before = service.letters("current")["letters"]
    assert all(entry["body_text"] == "" and entry["attachments"] == [] for entry in before)

    indexed = service.enrich_letters_search("current")
    assert indexed == len(before)

    after = service.letters("current")["letters"]
    enriched = next(entry for entry in after if entry["title"] == "Einladung zum Schulfest")
    assert "Schulfest" in enriched["body_text"]
    assert {a["filename"] for a in enriched["attachments"]} == {"einladung.pdf", "anmeldung.docx"}

    again = service.enrich_letters_search("current")
    assert again == 0


from app.iserv.errors import DataError


class FileClient(FakeClient):
    def __init__(self, url):
        super().__init__(url)
        self.paths = []

    def fetch(self, path, params=None):
        self.paths.append(path)

        class Upstream:
            content = b"%PDF"
            headers = {"content-type": "application/pdf"}

        return Upstream()


class FakeResponse:
    def __init__(self, payload, status_code=200, invalid=False):
        self._payload = payload
        self.status_code = status_code
        self._invalid = invalid

    def json(self):
        if self._invalid:
            raise ValueError("response was not json")
        return self._payload


class ResponseClient(FakeClient):
    def __init__(self, url, response=None, error=None):
        super().__init__(url)
        self.response = response
        self.error = error
        self.paths = []

    def fetch(self, path, params=None):
        self.paths.append(path)
        if self.error is not None:
            raise self.error
        return self.response


class FakeAdvancedDsa:
    def __init__(self, settings=None, services=None, period_times=None):
        self._settings = settings or {}
        self._services = services or []
        self._period_times = period_times or {}

    def school_settings(self):
        return self._settings

    def services(self):
        return self._services

    def period_times(self):
        return self._period_times


class FakeMeDsa:
    def __init__(self, payload):
        self._payload = payload

    def _get(self, path, params=None):
        return self._payload if path == "users/me" else None


def test_timetable_available_reads_school_setting(tmp_path):
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeAdvancedDsa(settings={"timetable_availableForGuardiansAndStudents": False})
    assert service.timetable_available() is False


def test_timetable_available_defaults_true_when_setting_missing(tmp_path):
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeAdvancedDsa(settings={})
    assert service.timetable_available() is True


def test_timetable_available_defaults_true_on_error(tmp_path):
    service, _ = make(tmp_path)

    def boom():
        raise RuntimeError("iserv unreachable")

    service._dsa = boom
    assert service.timetable_available() is True


def test_me_passes_through_profile_and_school_fields(tmp_path):
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeMeDsa({
        "id": 16000001,
        "forename": "Alex",
        "surname": "Example",
        "displayname": "Example Alex",
        "username": "alex.example",
        "email": "alex.example@example.invalid",
        "externalId": None,
        "isActive": True,
        "isActivated": True,
        "needsReRegistration": False,
        "inPreparation": False,
        "isWebUser": True,
        "isGuardian": True,
        "isMainTeacher": False,
        "roles": ["guardian"],
        "isNotifiedByEmail": False,
        "isReceiverOfSerialPrint": False,
        "isNewsletterReceiver": None,
        "hasActiveDevices": False,
        "has2ndFactorActive": False,
        "hasRestrictedAccessPin": False,
        "createdAt": 1700000000,
        "updatedAt": 1700003600,
        "school": {
            "id": 5000001,
            "name": "example-school.example",
            "colorPrimary": "#00447c",
            "street": "",
            "zip": "",
            "town": "",
            "country": "",
        },
    })
    result = service.me()
    assert result["id"] == 16000001
    assert result["surname"] == "Example"
    assert result["username"] == "alex.example"
    assert result["email"] == "alex.example@example.invalid"
    assert result["roles"] == ["guardian"]
    assert result["has_2nd_factor_active"] is False
    assert result["created_at"] == 1700000000
    assert result["updated_at"] == 1700003600
    assert result["school_name"] == "example-school.example"
    assert result["school_address"] == ""
    assert "colorPrimary" not in result
    assert "school" not in result


def test_me_builds_school_address_when_filled(tmp_path):
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeMeDsa({
        "school": {"name": "Schule", "street": "Beispielweg 1", "zip": "12345", "town": "Beispielstadt", "country": "DE"},
    })
    result = service.me()
    assert result["school_address"] == "Beispielweg 1, 12345, Beispielstadt, DE"


class BrokenDsa:
    def school_settings(self):
        raise RuntimeError("school settings unavailable")

    def services(self):
        raise RuntimeError("services unavailable")

    def period_times(self):
        raise RuntimeError("period times unavailable")


def with_client(tmp_path, client):
    service, store = make(tmp_path)
    service.client_factory = lambda url: client
    return service, store


def test_pinboard_attachment_fetches_dsa_file_endpoint(tmp_path):
    client = FileClient("https://school.example")
    service, _ = with_client(tmp_path, client)
    response = service.pinboard_attachment("0123456789abcdef0123456789abcdef-42.pdf")
    assert client.paths == ["/iserv/dieschulapp/api/1.0/files/0123456789abcdef0123456789abcdef-42.pdf"]
    assert response.content == b"%PDF"


def test_pinboard_attachment_url_quotes_the_filename_segment(tmp_path):
    client = FileClient("https://school.example")
    service, _ = with_client(tmp_path, client)
    service.pinboard_attachment("a b#c.pdf")
    assert client.paths == ["/iserv/dieschulapp/api/1.0/files/a%20b%23c.pdf"]


@pytest.mark.parametrize(
    "filename",
    [
        "",
        "..",
        "../secrets.json",
        "a/b.pdf",
        "sub/../x.pdf",
        "../../etc/passwd",
        "..\\..\\secrets",
        "a\x00b.pdf",
        "x" * 121,
    ],
)
def test_pinboard_attachment_rejects_unsafe_filenames(tmp_path, filename):
    client = FileClient("https://school.example")
    service, _ = with_client(tmp_path, client)
    with pytest.raises(DataError):
        service.pinboard_attachment(filename)
    assert client.paths == []


@pytest.mark.parametrize(
    "filename",
    [
        "Bücher Eigenanteil Klasse 1_Neu.pdf",
        "infobrief_krätze_eltern.pdf",
        "Elternabend Einladung.pdf",
        "Präsentation Herbstfest.pptx",
        "Klassenfoto.png",
        "Ausflug Foto.jpg",
        "Anmeldeformular Ganztag.docx",
    ],
)
def test_pinboard_attachment_accepts_realistic_filenames_with_spaces_and_umlauts(tmp_path, filename):
    client = FileClient("https://school.example")
    service, _ = with_client(tmp_path, client)
    response = service.pinboard_attachment(filename)
    assert client.paths == [f"/iserv/dieschulapp/api/1.0/files/{quote(filename, safe='')}"]
    assert response.content == b"%PDF"


def test_pinboard_attachments_carry_download_url(tmp_path):
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeDsa([_board()])
    attachment = service.pinboard()["feed"][0]["attachments"][0]
    assert attachment["file"] == "f.pdf"
    assert attachment["url"] == "api/pinboard/attachment/f.pdf"
    assert attachment["filename"] == "f.pdf"


def test_pinboard_folder_carries_author_and_create_permission(tmp_path):
    board = _board()
    board.author = "Teacher One"
    board.students_can_create_tiles = True
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeDsa([board])
    folder = service.pinboard()["folders"][0]
    assert folder["author"] == "Teacher One"
    assert folder["students_can_create_tiles"] is True


def test_pinboard_attachment_dict_carries_timestamps_and_image_size(tmp_path):
    board = _board()
    board.columns[0].tiles[1].attachments = [
        Attachment(6, "bild.png", "png", "image/png", 10, created_at=1700000000, updated_at=1700003600, image_width=640, image_height=480)
    ]
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeDsa([board])
    attachment = service.pinboard()["feed"][0]["attachments"][0]
    assert attachment["created_at"] == 1700000000
    assert attachment["updated_at"] == 1700003600
    assert attachment["image_width"] == 640
    assert attachment["image_height"] == 480


def test_pinboard_board_level_attachments_are_returned_in_folder(tmp_path):
    board = _board()
    board.attachments = [Attachment(9, "einladung.pdf", "pdf", "application/pdf", 20)]
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeDsa([board])
    folder = service.pinboard()["folders"][0]
    assert folder["attachments"][0]["filename"] == "einladung.pdf"
    assert folder["attachments"][0]["url"] == "api/pinboard/attachment/einladung.pdf"


def test_pinboard_board_without_attachments_returns_empty_list(tmp_path):
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeDsa([_board()])
    folder = service.pinboard()["folders"][0]
    assert folder["attachments"] == []


def test_pinboard_attachment_url_is_empty_for_unsafe_names(tmp_path):
    board = _board()
    board.columns[0].tiles[1].attachments = [
        Attachment(6, "../secrets/Elternabend.pdf", "pdf", "application/pdf", 10)
    ]
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeDsa([board])
    attachment = service.pinboard()["feed"][0]["attachments"][0]
    assert attachment["file"] == ""
    assert attachment["url"] == ""


def test_pinboard_attachment_url_carries_spaces_and_umlauts(tmp_path):
    board = _board()
    board.columns[0].tiles[1].attachments = [
        Attachment(6, "Einladung Elternabend äöü.pdf", "pdf", "application/pdf", 10)
    ]
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeDsa([board])
    attachment = service.pinboard()["feed"][0]["attachments"][0]
    assert attachment["file"] == "Einladung Elternabend äöü.pdf"
    assert attachment["url"] == "api/pinboard/attachment/Einladung Elternabend äöü.pdf"


def test_timetable_fills_period_times_automatically(tmp_path):
    service, store = make(tmp_path)
    service._dsa = lambda: FakeAdvancedDsa(period_times={"1": "08:00", "2": "08:50"})
    result = service.timetable("uuid-1")
    assert result["period_times"] == {"1": "08:00", "2": "08:50"}
    assert store.load_config()["period_times"] == {"1": "08:00", "2": "08:50"}
    assert result["lessons"][0]["start_time"] == "08:00"


def test_timetable_never_overwrites_manual_period_times(tmp_path):
    service, store = make(tmp_path)
    config = store.load_config()
    config["period_times"] = {"1": "07:55"}
    store.save_config(config)
    service._dsa = lambda: FakeAdvancedDsa(period_times={"1": "08:00", "2": "08:50"})
    result = service.timetable("uuid-1")
    assert result["period_times"] == {"1": "07:55", "2": "08:50"}
    assert store.load_config()["period_times"]["1"] == "07:55"


def test_timetable_survives_period_time_errors(tmp_path):
    service, _ = make(tmp_path)
    service._dsa = lambda: BrokenDsa()
    result = service.timetable("uuid-1")
    assert result["period_times"] == {}
    assert result["lessons"][0]["start_time"] == ""


class ChangeClient(FakeClient):
    def __init__(self, url):
        super().__init__(url)
        self.reference = None

    def get_timetable(self, child_id, reference=None):
        self.reference = reference
        combined = [
            Lesson("31.08.2026", 1, 1, "D", "BEH", "R1", "1a"),
            Lesson("31.08.2026", 1, 2, "M", "ERN", "R2", "1a"),
        ]
        plain = [
            Lesson("31.08.2026", 1, 1, "D", "BEH", "R1", "1a"),
            Lesson("31.08.2026", 1, 2, "M", "KRA", "R1", "1a"),
            Lesson("31.08.2026", 1, 3, "SP", "OTT", "GYM", "1a"),
        ]
        week = TimetableWeek("31.08.2026", "06.09.2026", "22.07.2026 12:25", combined, plain, [])
        week.lesson_changes, week.cancelled = detect_changes(combined, plain, [])
        return week


def make_with_changes(tmp_path):
    store = Store(tmp_path / "data")
    store.save_config({"school_url": "https://school.example"})
    store.save_secrets({"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP"})
    clients = []

    def factory(url):
        client = ChangeClient(url)
        clients.append(client)
        return client

    return IServService(store, client_factory=factory), clients


def test_timetable_marks_substitutions(tmp_path):
    service, _ = make_with_changes(tmp_path)
    result = service.timetable("uuid-1")
    changed = next(item for item in result["lessons"] if item["period"] == 2)
    assert changed["change_kind"] == "changed"
    assert changed["changed_fields"] == ["teacher", "room"]
    assert changed["previous"]["teacher"] == "KRA"
    assert changed["previous"]["room"] == "R1"


def test_timetable_appends_cancelled_lessons(tmp_path):
    service, _ = make_with_changes(tmp_path)
    result = service.timetable("uuid-1")
    assert len(result["lessons"]) == 3
    cancelled = [item for item in result["lessons"] if item["change_kind"] == "cancelled"]
    assert len(cancelled) == 1
    assert cancelled[0]["period"] == 3
    assert cancelled[0]["subject_code"] == "SP"
    assert cancelled[0]["room"] == "GYM"


def test_timetable_regular_lesson_stays_unmarked(tmp_path):
    service, _ = make_with_changes(tmp_path)
    result = service.timetable("uuid-1")
    regular = next(item for item in result["lessons"] if item["period"] == 1)
    assert regular["change_kind"] == ""
    assert regular["changed_fields"] == []
    assert regular["previous"] == {"subject": "", "teacher": "", "room": ""}


def test_timetable_reports_change_count(tmp_path):
    service, _ = make_with_changes(tmp_path)
    assert service.timetable("uuid-1")["change_count"] == 2


def test_timetable_without_change_data_stays_compatible(tmp_path):
    service, _ = make(tmp_path)
    result = service.timetable("uuid-1")
    assert result["change_count"] == 0
    assert result["lessons"][0]["change_kind"] == ""
    assert result["week_offset"] == 0


def test_timetable_week_offset_shifts_the_reference(tmp_path):
    service, clients = make_with_changes(tmp_path)
    result = service.timetable("uuid-1", reference=date(2026, 9, 2), week_offset=1)
    assert clients[0].reference == date(2026, 9, 9)
    assert result["week_offset"] == 1


def test_timetable_week_offset_can_go_backwards(tmp_path):
    service, clients = make_with_changes(tmp_path)
    service.timetable("uuid-1", reference=date(2026, 9, 2), week_offset=-2)
    assert clients[0].reference == date(2026, 8, 19)


def test_timetable_week_offset_defaults_to_current_week(tmp_path):
    service, clients = make_with_changes(tmp_path)
    service.timetable("uuid-1", reference=date(2026, 9, 2))
    assert clients[0].reference == date(2026, 9, 2)


def test_timetable_week_offset_is_clamped(tmp_path):
    service, clients = make_with_changes(tmp_path)
    high = service.timetable("uuid-1", reference=date(2026, 9, 2), week_offset=99)
    assert clients[0].reference == date(2026, 9, 2) + timedelta(days=56)
    assert high["week_offset"] == 8
    low = service.timetable("uuid-1", reference=date(2026, 9, 2), week_offset=-99)
    assert clients[0].reference == date(2026, 9, 2) - timedelta(days=56)
    assert low["week_offset"] == -8


class SharedSlotClient(FakeClient):
    combined_subjects = ("M", "TEAM")

    def get_timetable(self, child_id, reference=None):
        plain = [
            Lesson("01.09.2026", 2, 4, "M", "ERN", "R1", "1a"),
            Lesson("01.09.2026", 2, 4, "TEAM", "BEH", "R2", "1a"),
        ]
        combined = [lesson for lesson in plain if lesson.subject in self.combined_subjects]
        week = TimetableWeek("31.08.2026", "06.09.2026", "22.07.2026 12:25", combined, plain, [])
        week.lesson_changes, week.cancelled = detect_changes(combined, plain, [])
        return week


class PartialCancelClient(SharedSlotClient):
    combined_subjects = ("M",)


def make_with_client(tmp_path, client_class):
    store = Store(tmp_path / "data")
    store.save_config({"school_url": "https://school.example"})
    store.save_secrets({"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP"})
    return IServService(store, client_factory=lambda url: client_class(url))


def test_timetable_keeps_both_lessons_of_a_shared_slot(tmp_path):
    service = make_with_client(tmp_path, SharedSlotClient)
    result = service.timetable("uuid-1")
    shared = [item for item in result["lessons"] if item["period"] == 4]
    assert sorted(item["subject_code"] for item in shared) == ["M", "TEAM"]
    assert all(item["change_kind"] == "" for item in shared)
    assert result["change_count"] == 0


def test_timetable_partial_cancellation_marks_only_the_missing_subject(tmp_path):
    service = make_with_client(tmp_path, PartialCancelClient)
    result = service.timetable("uuid-1")
    shared = [item for item in result["lessons"] if item["period"] == 4]
    assert len(shared) == 2
    running = next(item for item in shared if item["subject_code"] == "M")
    dropped = next(item for item in shared if item["subject_code"] == "TEAM")
    assert running["change_kind"] == ""
    assert running["changed_fields"] == []
    assert dropped["change_kind"] == "cancelled"
    assert dropped["room"] == "R2"
    assert result["change_count"] == 1


def test_timetable_week_offset_ignores_broken_values(tmp_path):
    service, clients = make_with_changes(tmp_path)
    result = service.timetable("uuid-1", reference=date(2026, 9, 2), week_offset="zwei")
    assert clients[0].reference == date(2026, 9, 2)
    assert result["week_offset"] == 0


class FakeAbsenceDsa:
    def __init__(self, settings=None, slots=None, notes=None, status=201, raw_slots=None):
        self._settings = settings if settings is not None else {
            "requestToSchools_studentAbsence_isActive": True,
            "requestToSchools_notAttend_bus_isActive": True,
            "requestToSchools_notAttend_afternoonCare_isActive": True,
            "requestToSchools_studentAbsence_minDays": 3,
        }
        self._slots = slots if slots is not None else [
            {"number": 1, "name": "1. Stunde"},
            {"number": 2, "name": "2. Stunde"},
        ]
        self._raw_slots = raw_slots if raw_slots is not None else [
            {"number": 1, "name": "1. Stunde", "startTime": "08:00", "endTime": "08:45"},
            {"number": 2, "name": "2. Stunde", "startTime": "08:45", "endTime": "09:30"},
        ]
        self._notes = notes or []
        self._requests = {}
        self.status = status
        self.sent = None
        self.deleted = None

    def school_settings(self):
        return self._settings

    def sick_notes(self, since=None):
        return self._notes

    def sick_note_children(self):
        return [{"id": 7, "name": "Mia", "class_name": "2b"}]

    def lesson_slots(self):
        return self._slots

    def period_times(self):
        return {str(slot["number"]): slot["startTime"] for slot in self._raw_slots if slot.get("startTime")}

    def user_requests(self, path, student_id=None):
        return self._requests.get(path, [])

    def send_request(self, request):
        self.sent = request
        return type("R", (), {"status_code": self.status, "json": lambda self: {}})()

    def delete_entry(self, path):
        self.deleted = path
        return type("R", (), {"status_code": self.status, "json": lambda self: {}})()

    def _get(self, path, params=None):
        assert path == "timetable-slots/"
        assert params == {"filterBy": "type:is(lesson)"}
        return self._raw_slots


class RawlessAbsenceDsa(FakeAbsenceDsa):
    _get = None


class BrokenSlotsAbsenceDsa(FakeAbsenceDsa):
    def _get(self, path, params=None):
        raise RuntimeError("slots unavailable")


def with_absences(tmp_path, dsa):
    service, store = make(tmp_path)
    service._dsa = lambda: dsa
    return service, store


def test_absences_overview_exposes_leave_min_days(tmp_path):
    service, _ = with_absences(tmp_path, FakeAbsenceDsa())
    assert service.absences_overview()["leave_min_days"] == 3


def test_absences_overview_entry_attachments_carry_download_url(tmp_path):
    from app.iserv.absences import LEAVE_PATH

    dsa = FakeAbsenceDsa()
    dsa._requests[LEAVE_PATH] = [
        {
            "id": 1,
            "staticFiles": [
                {
                    "id": 5,
                    "originalFilename": "attest.pdf",
                    "extension": "pdf",
                    "mimetype": "application/pdf",
                    "size": 1234,
                    "filename": "0123456789abcdef0123456789abcdef-5.pdf",
                }
            ],
        }
    ]
    service, _ = with_absences(tmp_path, dsa)
    entries = service.absences_overview()["entries"]
    leave_entry = next(entry for entry in entries if entry["kind"] == "leave")
    assert leave_entry["attachments"] == [
        {
            "id": 5,
            "filename": "attest.pdf",
            "extension": "pdf",
            "mimetype": "application/pdf",
            "size": 1234,
            "file": "0123456789abcdef0123456789abcdef-5.pdf",
            "url": "api/absences/attachment/0123456789abcdef0123456789abcdef-5.pdf",
        }
    ]


def test_absences_overview_entry_attachments_reject_unsafe_filename(tmp_path):
    from app.iserv.absences import LEAVE_PATH

    dsa = FakeAbsenceDsa()
    dsa._requests[LEAVE_PATH] = [
        {"id": 1, "staticFiles": [{"id": 5, "filename": "../../etc/passwd"}]}
    ]
    service, _ = with_absences(tmp_path, dsa)
    entries = service.absences_overview()["entries"]
    leave_entry = next(entry for entry in entries if entry["kind"] == "leave")
    assert leave_entry["attachments"][0]["url"] == ""


def test_absences_overview_leave_min_days_is_zero_when_absent(tmp_path):
    service, _ = with_absences(tmp_path, FakeAbsenceDsa(settings={"requestToSchools_notAttend_bus_isActive": True}))
    assert service.absences_overview()["leave_min_days"] == 0


def test_absences_overview_leave_min_days_accepts_numeric_string(tmp_path):
    dsa = FakeAbsenceDsa(settings={"requestToSchools_studentAbsence_minDays": "5"})
    service, _ = with_absences(tmp_path, dsa)
    assert service.absences_overview()["leave_min_days"] == 5


def test_absences_overview_leave_min_days_survives_garbage(tmp_path):
    dsa = FakeAbsenceDsa(settings={"requestToSchools_studentAbsence_minDays": "drei"})
    service, _ = with_absences(tmp_path, dsa)
    assert service.absences_overview()["leave_min_days"] == 0


def test_absences_overview_builds_period_labels_with_times(tmp_path):
    service, _ = with_absences(tmp_path, FakeAbsenceDsa())
    assert service.absences_overview()["period_labels"] == [
        {"number": 1, "label": "1. Stunde 08:00 - 08:45"},
        {"number": 2, "label": "2. Stunde 08:45 - 09:30"},
    ]


def test_absences_overview_period_labels_without_end_times(tmp_path):
    dsa = FakeAbsenceDsa(
        slots=[{"number": 1, "name": "1. Stunde"}],
        raw_slots=[{"number": 1, "name": "1. Stunde", "startTime": "08:00"}],
    )
    service, _ = with_absences(tmp_path, dsa)
    assert service.absences_overview()["period_labels"] == [{"number": 1, "label": "1. Stunde"}]


def test_absences_overview_period_labels_survive_broken_raw_slots(tmp_path):
    service, _ = with_absences(tmp_path, BrokenSlotsAbsenceDsa())
    assert service.absences_overview()["period_labels"] == [
        {"number": 1, "label": "1. Stunde"},
        {"number": 2, "label": "2. Stunde"},
    ]


def test_absences_overview_period_labels_without_raw_reader(tmp_path):
    service, _ = with_absences(tmp_path, RawlessAbsenceDsa())
    assert service.absences_overview()["period_labels"] == [
        {"number": 1, "label": "1. Stunde"},
        {"number": 2, "label": "2. Stunde"},
    ]


def test_absences_overview_period_labels_fall_back_to_numbered_name(tmp_path):
    dsa = FakeAbsenceDsa(
        slots=[{"number": 3, "name": ""}],
        raw_slots=[{"number": 3, "startTime": "10:00", "endTime": "10:45"}],
    )
    service, _ = with_absences(tmp_path, dsa)
    assert service.absences_overview()["period_labels"] == [{"number": 3, "label": "3. Stunde 10:00 - 10:45"}]


def test_absences_overview_entries_carry_german_labels(tmp_path):
    dsa = FakeAbsenceDsa(notes=[{"id": 1, "sickFromDateAsString": "2026-09-05"}])
    dsa._requests["user-requests-to-school/not-attend/afternoon-care/"] = [
        {"id": 4, "absentDate": "2026-09-05T22:00:00+00:00", "accepted": None}
    ]
    service, _ = with_absences(tmp_path, dsa)
    labels = [entry["label"] for entry in service.absences_overview()["entries"]]
    assert "Krankmeldung" in labels
    assert "Abmeldung Ganztagsbetreuung Ganztagsbetreuung" in labels


def test_absences_overview_sorts_entries_newest_first(tmp_path):
    dsa = FakeAbsenceDsa(
        notes=[
            {"id": 1, "sickFromDateAsString": "2026-09-01"},
            {"id": 2, "sickFromDateAsString": "2026-09-07"},
        ]
    )
    service, _ = with_absences(tmp_path, dsa)
    entries = service.absences_overview()["entries"]
    assert [entry["id"] for entry in entries] == [2, 1]


def test_absences_overview_exposes_school_rules(tmp_path):
    dsa = FakeAbsenceDsa(
        settings={
            "requestToSchools_notAttend_afternoonCare_isActive": True,
            "requestToSchools_notAttend_afternoonCare_pickupTimes": ["15:00"],
            "requestToSchools_notAttend_afternoonCare_allowCustomPickupTime": False,
            "dayCare_latestTimeToCancelAttendanceToday": "11:00",
            "sickNotes_guardiansCanReportByLesson": True,
            "sickNotes_allowTextnoteForGuardiansAndStudents": True,
        }
    )
    service, _ = with_absences(tmp_path, dsa)
    rules = service.absences_overview()["rules"]
    assert rules["daycare_pickup_times"] == ["15:00"]
    assert rules["daycare_custom_pickup"] is False
    assert rules["daycare_cutoff"] == "11:00"
    assert rules["sick_by_lesson"] is True
    assert rules["sick_comment"] is True


def test_absences_overview_offers_only_today_and_tomorrow_as_start(tmp_path):
    service, _ = with_absences(tmp_path, FakeAbsenceDsa())
    options = service.absences_overview()["day_options"]
    assert [item["label"] for item in options["from"]] == ["Heute", "Morgen"]


def test_absences_overview_keeps_periods_and_types(tmp_path):
    service, _ = with_absences(tmp_path, FakeAbsenceDsa())
    overview = service.absences_overview()
    assert overview["periods"] == [{"number": 1, "name": "1. Stunde"}, {"number": 2, "name": "2. Stunde"}]
    assert overview["deregister_options"] == ["bus"]
    assert "daycare" in overview["types"]


def test_absences_overview_writes_observed_entries_into_history_cache(tmp_path):
    today = date.today().isoformat()
    dsa = FakeAbsenceDsa(notes=[{"id": 7040001, "sickFromDateAsString": today, "sickTillDateAsString": today}])
    service, store = with_absences(tmp_path, dsa)
    service.absences_overview()
    history = store.load_absence_history()
    assert "7040001" in history
    assert history["7040001"]["kind"] == "sick"


def test_poller_observation_path_also_writes_into_history_cache(tmp_path):
    today = date.today().isoformat()
    dsa = FakeAbsenceDsa(notes=[{"id": 7040002, "sickFromDateAsString": today, "sickTillDateAsString": today}])
    service, store = with_absences(tmp_path, dsa)

    from app.poller import Poller

    Poller(service, store=store)._poll_absences()

    assert "7040002" in store.load_absence_history()


def test_absences_overview_shows_history_entry_no_longer_in_live_data(tmp_path):
    vanished_till = (date.today() - timedelta(days=5)).isoformat()
    dsa = FakeAbsenceDsa(notes=[{"id": 9001, "sickFromDateAsString": vanished_till, "sickTillDateAsString": vanished_till}])
    service, store = with_absences(tmp_path, dsa)
    service.absences_overview()

    dsa._notes = []
    entries = service.absences_overview()["entries"]

    vanished = next(entry for entry in entries if entry["id"] == 9001)
    assert vanished["from_history"] is True
    assert vanished["deletable"] is False
    assert "IServ" in vanished["locked_reason"]


def test_absences_overview_prunes_history_entries_older_than_30_days(tmp_path):
    old_till = (date.today() - timedelta(days=40)).isoformat()
    dsa = FakeAbsenceDsa(notes=[{"id": 9002, "sickFromDateAsString": old_till, "sickTillDateAsString": old_till}])
    service, store = with_absences(tmp_path, dsa)
    service.absences_overview()

    dsa._notes = []
    entries = service.absences_overview()["entries"]

    assert all(entry["id"] != 9002 for entry in entries)
    assert "9002" not in store.load_absence_history()


def test_absences_overview_does_not_duplicate_an_entry_still_present_live(tmp_path):
    today = date.today().isoformat()
    note = {"id": 9003, "sickFromDateAsString": today, "sickTillDateAsString": today}
    dsa = FakeAbsenceDsa(notes=[note])
    service, store = with_absences(tmp_path, dsa)
    service.absences_overview()
    entries = service.absences_overview()["entries"]

    matches = [entry for entry in entries if entry["id"] == 9003]
    assert len(matches) == 1
    assert "from_history" not in matches[0]


def test_report_absence_sends_resolved_sick_note(tmp_path):
    dsa = FakeAbsenceDsa()
    service, _ = with_absences(tmp_path, dsa)
    result = service.report_absence(
        {
            "type": "sick",
            "student_id": 7,
            "day_from": "today",
            "day_till": "today",
            "from_period": "1",
            "till_period": "6",
            "duty_to_report": True,
            "comment": "Fieber",
        }
    )
    assert result["ok"] is True
    assert dsa.sent.path == "sickNotes/"
    assert dsa.sent.body_mode == "json"
    assert dsa.sent.payload == {
        "sickUser": 7,
        "sickFromDate": date.today().isoformat(),
        "sickTillDate": date.today().isoformat(),
        "isDutyToReport": True,
        "note": "Fieber",
        "sickFromLessonNumber": 1,
        "sickTillLessonNumber": 6,
    }


def test_report_absence_sends_ganztaegig_sick_note_with_dynamic_last_period(tmp_path):
    dsa = FakeAbsenceDsa(slots=[
        {"number": 1, "name": "1. Stunde"},
        {"number": 2, "name": "2. Stunde"},
        {"number": 3, "name": "3. Stunde"},
    ])
    service, _ = with_absences(tmp_path, dsa)
    result = service.report_absence(
        {
            "type": "sick",
            "student_id": 7,
            "day_from": "today",
            "day_till": "today",
        }
    )
    assert result["ok"] is True
    assert dsa.sent.payload["sickFromLessonNumber"] == 1
    assert dsa.sent.payload["sickTillLessonNumber"] == 3


def test_report_absence_sends_daycare_payload(tmp_path):
    dsa = FakeAbsenceDsa()
    service, _ = with_absences(tmp_path, dsa)
    service.report_absence(
        {
            "type": "daycare",
            "student_id": 7,
            "daycare_kind": "early_end",
            "date": "2026-09-05",
            "repeat": "weekly",
            "reason": "Sport",
            "pickup_time": "15:00",
        }
    )
    assert dsa.sent.path == "user-requests-to-school/not-attend/afternoon-care/"
    assert dsa.sent.body_mode == "form"
    assert dsa.sent.headers == {"X-Do-Not-Set-Default-Content-Type": "true"}
    assert dsa.sent.payload["type"] == "not-attend-afternoon-care"
    assert dsa.sent.payload["absentDate"] == "2026-09-04T22:00:00.000Z"
    assert dsa.sent.payload["repeatWeekly"] is True
    assert dsa.sent.payload["note"] == "Sport"
    assert dsa.sent.payload["pickupTime"] == "15:00"


def test_report_absence_names_the_missing_subject(tmp_path):
    dsa = FakeAbsenceDsa()
    service, _ = with_absences(tmp_path, dsa)
    result = service.report_absence(
        {"type": "leave", "student_id": 7, "from_date": "2026-09-10", "subject": "", "body": "Text"}
    )
    assert result == {
        "ok": False,
        "message_key": "api.absence.error.subject",
        "message": "Bitte einen Betreff für den Antrag angeben.",
    }
    assert dsa.sent is None


def test_report_absence_names_the_missing_body(tmp_path):
    service, _ = with_absences(tmp_path, FakeAbsenceDsa())
    result = service.report_absence(
        {"type": "leave", "student_id": 7, "from_date": "2026-09-10", "subject": "Arzt", "body": "  "}
    )
    assert result["message"] == "Bitte den Antragstext ausfüllen."


def test_report_absence_names_the_invalid_deregister_target(tmp_path):
    service, _ = with_absences(tmp_path, FakeAbsenceDsa())
    result = service.report_absence({"type": "deregister", "student_id": 7, "date": "2026-09-04"})
    assert result["message"] == "Bitte auswählen, wovon abgemeldet werden soll (Bus, Kindergarten oder Mittagessen)."


def test_report_absence_names_the_invalid_daycare_kind(tmp_path):
    service, _ = with_absences(tmp_path, FakeAbsenceDsa())
    result = service.report_absence(
        {"type": "daycare", "student_id": 7, "date": "2026-09-05", "repeat": "once"}
    )
    assert result["message"] == "Bitte die Art der Abmeldung wählen (abmelden oder vorzeitiges Ende)."


def test_report_absence_names_the_invalid_repeat(tmp_path):
    service, _ = with_absences(tmp_path, FakeAbsenceDsa())
    result = service.report_absence(
        {
            "type": "daycare",
            "student_id": 7,
            "daycare_kind": "deregister",
            "date": "2026-09-05",
            "repeat": "monatlich",
        }
    )
    assert result["message"] == "Bitte die Wiederholung wählen (einmalig oder wöchentlich)."


def test_report_absence_rejects_unknown_kind(tmp_path):
    service, _ = with_absences(tmp_path, FakeAbsenceDsa())
    result = service.report_absence({"type": "ferienantrag", "student_id": 7})
    assert result == {
        "ok": False,
        "message_key": "api.absence.error.unknownKind",
        "message": "Unbekannter Abwesenheits-Typ.",
    }


def test_report_absence_explains_a_rejected_payload(tmp_path):
    service, _ = with_absences(tmp_path, FakeAbsenceDsa(status=422))
    result = service.report_absence(
        {"type": "deregister", "student_id": 7, "deregister_from": "bus", "date": "2026-09-04"}
    )
    assert result["ok"] is False
    assert "abgelehnt" in result["message"]


def test_report_absence_reports_unexpected_status_with_number(tmp_path):
    service, _ = with_absences(tmp_path, FakeAbsenceDsa(status=500))
    result = service.report_absence(
        {"type": "deregister", "student_id": 7, "deregister_from": "bus", "date": "2026-09-04"}
    )
    assert "500" in result["message"]


def test_delete_absence_never_touches_a_sick_note(tmp_path):
    dsa = FakeAbsenceDsa(status=204)
    service, _ = with_absences(tmp_path, dsa)
    result = service.delete_absence({"type": "sick", "id": 42})
    assert result["ok"] is False
    assert "Sekretariat" in result["message"]
    assert dsa.deleted is None, "IServ refuses it anyway - do not even try"


def test_delete_absence_hits_the_item_route(tmp_path):
    dsa = FakeAbsenceDsa(status=204)
    service, _ = with_absences(tmp_path, dsa)
    result = service.delete_absence({"type": "leave", "id": 42})
    assert result["ok"] is True
    assert dsa.deleted == "user-requests-to-school/student-absences/42"


def test_delete_absence_explains_a_refusal(tmp_path):
    dsa = FakeAbsenceDsa(status=403)
    service, _ = with_absences(tmp_path, dsa)
    result = service.delete_absence({"type": "leave", "id": 42})
    assert result["ok"] is False
    assert "Eltern-Konten" in result["message"]


def test_delete_absence_needs_the_deregister_target(tmp_path):
    dsa = FakeAbsenceDsa(status=204)
    service, _ = with_absences(tmp_path, dsa)
    result = service.delete_absence({"type": "deregister", "id": 42})
    assert result["ok"] is False
    assert dsa.deleted is None


def test_delete_absence_uses_the_deregister_target(tmp_path):
    dsa = FakeAbsenceDsa(status=204)
    service, _ = with_absences(tmp_path, dsa)
    service.delete_absence({"type": "deregister", "id": 42, "target": "kindergarten"})
    assert dsa.deleted == "user-requests-to-school/not-attend/kindergarten/42"


def test_iserv_badges_reads_native_unread_counts(tmp_path):
    class BadgeClient(FakeClient):
        def fetch(self, path, params=None):
            class R:
                status_code = 200

                @staticmethod
                def json():
                    return {"parentletter": 1, "other": "nope"}

            return R()

    service, _ = make(tmp_path)
    service.client_factory = lambda url: BadgeClient(url)
    assert service.iserv_badges() == {"parentletter": 1}


def test_iserv_badges_tolerates_bad_responses(tmp_path):
    class BrokenClient(FakeClient):
        def fetch(self, path, params=None):
            class R:
                status_code = 500

                @staticmethod
                def json():
                    raise ValueError("no json")

            return R()

    service, _ = make(tmp_path)
    service.client_factory = lambda url: BrokenClient(url)
    assert service.iserv_badges() == {}


def test_check_connection_reuses_a_live_session_instead_of_logging_in_again(tmp_path):
    logins = []

    def factory(url):
        client = FakeClient(url)
        original = client.login

        def counted(username, password, provider):
            logins.append(provider())
            return original(username, password, provider)

        client.login = counted
        return client

    service, _ = make(tmp_path)
    service.client_factory = factory
    assert service.check_connection() == "ok"
    assert service.check_connection() == "ok"
    assert service.check_connection() == "ok"
    assert len(logins) == 1


def test_code_provider_never_sends_the_same_code_twice(tmp_path):
    from app.service import _code_provider

    slept = []
    ticks = iter([0.0, 5.0, 40.0, 40.0])
    secrets = {"totp_secret": "JBSWY3DPEHPK3PXP"}
    used = {}
    provide = _code_provider(secrets, used, sleeper=slept.append, clock=lambda: next(ticks))
    first = provide()
    used["code"] = first
    second = provide()
    assert slept, "expected a wait for the next time window"
    assert second != first or slept


def _seen_service(tmp_path, letters_html=None):
    store = Store(tmp_path / "data")
    store.save_config({"school_url": "https://school.example"})
    store.save_secrets({"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP"})
    return store


def test_letters_read_state_comes_from_iserv_not_from_a_local_baseline(tmp_path):
    from pathlib import Path as _P

    pages = {"first": (_P(__file__).parent / "fixtures" / "letters_index.html").read_text(encoding="utf-8")}
    opened = []

    class LetterClient(FakeClient):
        def fetch(self, path, params=None):
            opened.append(path)

            class R:
                status_code = 200
                text = pages["first"]
                url = "https://school.example" + path

            return R()

    service, store = make(tmp_path)
    service.client_factory = lambda url: LetterClient(url)
    first = service.letters("current")
    assert sum(1 for entry in first["letters"] if entry["unread"]) == 1
    assert "letters_initialised" not in store.load_seen()
    assert not store.load_seen().get("letters")


def test_marking_a_letter_read_opens_it_in_iserv(tmp_path):
    from pathlib import Path as _P

    fixture = (_P(__file__).parent / "fixtures" / "letters_index.html").read_text(encoding="utf-8")
    opened = []

    class LetterClient(FakeClient):
        def fetch(self, path, params=None):
            opened.append(path)

            class R:
                status_code = 200
                text = fixture
                url = "https://school.example" + path

            return R()

    service, _ = make(tmp_path)
    service.client_factory = lambda url: LetterClient(url)
    result = service.mark_letters_read(["10000000-0000-4000-8000-000000000002:20000000-0000-4000-8000-000000000002"])
    assert result == {"read": 1}
    assert any("/parent/show/" in path for path in opened)


def test_marking_a_letter_read_never_hides_it_if_iserv_keeps_reporting_unread(tmp_path):
    from pathlib import Path as _P

    fixture = (_P(__file__).parent / "fixtures" / "letters_index.html").read_text(encoding="utf-8")

    class StubbornLetterClient(FakeClient):
        def fetch(self, path, params=None):
            class R:
                status_code = 200
                text = fixture
                url = "https://school.example" + path

            return R()

    service, store = make(tmp_path)
    service.client_factory = lambda url: StubbornLetterClient(url)
    key = "10000000-0000-4000-8000-000000000002:20000000-0000-4000-8000-000000000002"

    before = service.letters("current")["letters"]
    target_before = next(entry for entry in before if service._letter_key(entry) == key)
    assert target_before["unread"] is True
    assert "technical" not in target_before

    assert service.mark_letters_read([key]) == {"read": 1}
    assert not (store.dir / "letters_read_override.json").exists()

    after = service.letters("current")["letters"]
    target_after = next(entry for entry in after if service._letter_key(entry) == key)
    assert target_after["unread"] is True


def test_letters_have_no_local_unread_override_mechanism(tmp_path):
    import inspect

    service, store = make(tmp_path)
    assert not hasattr(store, "load_letters_read_override")
    assert not hasattr(store, "save_letters_read_override")
    assert not hasattr(store, "load_letters_unread_override")
    assert not hasattr(store, "save_letters_unread_override")
    assert "unseen" not in inspect.signature(service.mark_letters_read).parameters


def test_stray_letter_override_files_are_cleaned_up_on_store_startup(tmp_path):
    from app.store import Store

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    stray_read = data_dir / "letters_read_override.json"
    stray_unread = data_dir / "letters_unread_override.json"
    stray_read.write_text('{"keys": ["a:b"]}', encoding="utf-8")
    stray_unread.write_text('{"keys": ["c:d"]}', encoding="utf-8")

    Store(data_dir)

    assert not stray_read.exists()
    assert not stray_unread.exists()


def test_store_startup_is_safe_when_no_stray_override_files_exist(tmp_path):
    from app.store import Store

    Store(tmp_path / "data")


def test_marking_all_read_only_opens_the_unread_ones(tmp_path):
    from pathlib import Path as _P

    fixture = (_P(__file__).parent / "fixtures" / "letters_index.html").read_text(encoding="utf-8")
    opened = []

    class LetterClient(FakeClient):
        def fetch(self, path, params=None):
            opened.append(path)

            class R:
                status_code = 200
                text = fixture
                url = "https://school.example" + path

            return R()

    service, _ = make(tmp_path)
    service.client_factory = lambda url: LetterClient(url)
    assert service.mark_letters_read(mark_all=True) == {"read": 1}
    assert sum(1 for path in opened if "/parent/show/" in path) == 1


def test_archive_tab_never_reports_unread(tmp_path):
    from pathlib import Path as _P

    fixture = (_P(__file__).parent / "fixtures" / "letters_index.html").read_text(encoding="utf-8")

    class LetterClient(FakeClient):
        def fetch(self, path, params=None):
            class R:
                status_code = 200
                text = fixture
                url = "https://school.example" + path

            return R()

    service, _ = make(tmp_path)
    service.client_factory = lambda url: LetterClient(url)
    assert all(not entry["unread"] for entry in service.letters("archive")["letters"])


def test_letters_come_back_newest_first(tmp_path):
    from app.service import _published_sort_key

    values = ["01.09.2026 08:00", "31.08.2026 15:15", "kaputt", "01.09.2026 09:30"]
    ordered = sorted(values, key=_published_sort_key, reverse=True)
    assert ordered[0] == "01.09.2026 09:30"
    assert ordered[1] == "01.09.2026 08:00"
    assert ordered[-1] == "kaputt"


def test_pinboard_folders_sort_by_highest_post_id_not_by_updated_timestamp(tmp_path):
    zebra = Pinboard(
        id=1,
        title="Zebra Board",
        columns=[PinboardColumn(id=10, title="Termine", tiles=[Tile(500, "T", "x", "", "X", [])])],
    )
    alpha = Pinboard(
        id=2,
        title="Alpha Board",
        columns=[PinboardColumn(id=11, title="Termine", tiles=[Tile(50, "T", "x", "", "X", [])])],
    )
    empty_zeta = Pinboard(id=3, title="Zeta Empty", columns=[])
    empty_aaa = Pinboard(id=4, title="Aaa Empty", columns=[])
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeDsa([zebra, alpha, empty_zeta, empty_aaa])
    result = service.pinboard()
    assert [f["title"] for f in result["folders"]] == ["Zebra Board", "Alpha Board", "Aaa Empty", "Zeta Empty"]


def test_letter_detail_leaves_attachment_filename_empty_instead_of_inventing_one(tmp_path, monkeypatch):
    import app.service as service_module

    class FetchClient:
        def fetch(self, path):
            return type("Response", (), {"text": "", "url": ""})()

    monkeypatch.setattr(
        service_module,
        "parse_letter_detail",
        lambda text, url: {
            "title": "T",
            "body_html": "",
            "attachments": [{"attachment_id": 5}],
            "archive_url": None,
        },
    )
    service, _ = make(tmp_path)
    service._session = lambda: FetchClient()
    detail = service.letter_detail("11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222")
    assert detail["attachments"] == [{"filename": "", "url": "api/letters/attachment/5"}]


def test_conferences_reports_unavailable_instead_of_raising_when_the_fetch_fails(tmp_path):
    class FailingClient:
        def fetch_or_raise(self, path):
            raise DataError("boom")

    service, _ = make(tmp_path)
    service._session = lambda: FailingClient()
    assert service.conferences() == {"error": "unavailable", "items": []}


class FakeSickNoteDsa:
    def __init__(self, notes, children, settings=None):
        self._notes = notes
        self._children = children
        self._settings = settings or {}

    def sick_notes(self, since=None):
        return self._notes

    def sick_note_children(self):
        return self._children

    def school_settings(self):
        return self._settings


def _sick_note_raw(note_id, student_id):
    return {
        "id": note_id,
        "sickFromDateAsString": "2026-09-01",
        "sickTillDateAsString": "2026-09-01",
        "sickFromLessonNumber": 1,
        "sickTillLessonNumber": 3,
        "sickUser": {"id": student_id, "mainCourse": {"externalId": "5A"}},
    }


def test_sick_note_pdf_returns_bytes_and_filename_for_own_child(tmp_path):
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeSickNoteDsa(
        notes=[_sick_note_raw(42, 5)],
        children=[{"id": 5, "name": "Mia Müller"}],
    )
    pdf_bytes, filename = service.sick_note_pdf("42")
    assert pdf_bytes.startswith(b"%PDF")
    assert filename == "Schriftliche Bestätigung der Krankmeldung [Mia Müller] [" + date.today().strftime("%d.%m.%Y") + "].pdf"


def test_sick_note_pdf_rejects_id_not_present_in_own_sick_notes(tmp_path):
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeSickNoteDsa(
        notes=[_sick_note_raw(42, 5)],
        children=[{"id": 5, "name": "Mia Müller"}],
    )
    with pytest.raises(SickNoteNotFoundError):
        service.sick_note_pdf("999")


def test_sick_note_pdf_rejects_note_whose_student_is_not_an_own_child(tmp_path):
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeSickNoteDsa(
        notes=[_sick_note_raw(42, 999)],
        children=[{"id": 5, "name": "Mia Müller"}],
    )
    with pytest.raises(SickNoteNotFoundError):
        service.sick_note_pdf("42")


def test_sick_note_pdf_uses_school_replace_term_in_title(tmp_path):
    service, _ = make(tmp_path)
    service._dsa = lambda: FakeSickNoteDsa(
        notes=[_sick_note_raw(42, 5)],
        children=[{"id": 5, "name": "Mia Müller"}],
        settings={"sickNotes_replaceTerm": "Fehlzeitenmeldung"},
    )
    _, filename = service.sick_note_pdf("42")
    assert filename.startswith("Schriftliche Bestätigung der Fehlzeitenmeldung [Mia Müller]")


def test_folder_order_sorts_alphabetically_and_folds_umlauts():
    from app.service import _folder_order

    titles = ["Zebra", "Äpfel", "betreuung", "10 - Schulkonferenz", "Ostern"]
    assert sorted(titles, key=_folder_order) == [
        "10 - Schulkonferenz",
        "Äpfel",
        "betreuung",
        "Ostern",
        "Zebra",
    ]


CONFIRM_LETTER = "10000000-0000-4000-8000-000000000001"
CONFIRM_RECIPIENT = "20000000-0000-4000-8000-000000000001"


def _fixture_text(name):
    from pathlib import Path as _Path

    return (_Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


class ConfirmClient(FakeClient):
    def __init__(self, url, pages, post_status=200):
        super().__init__(url)
        self.pages = list(pages)
        self.post_status = post_status
        self.posts = []
        self.stage = 0
        self.list_html = _fixture_text("letters_index.html")

    def fetch(self, path, params=None):
        class R:
            pass

        response = R()
        response.status_code = 200
        response.url = "https://school.example" + path
        if "/parent/show/" in path:
            response.text = self.pages[min(self.stage, len(self.pages) - 1)]
        else:
            response.text = self.list_html
        return response

    def post_absolute(self, url, data, timeout=30):
        class R:
            pass

        self.posts.append((url, dict(data)))
        self.stage += 1
        response = R()
        response.status_code = self.post_status
        response.url = url
        response.text = ""
        return response


def _confirm_service(tmp_path, pages, post_status=200):
    service, store = make(tmp_path)
    client = ConfirmClient("https://school.example", pages, post_status)
    service.client_factory = lambda url: client
    return service, store, client


def test_letter_detail_carries_the_open_read_receipt(tmp_path):
    service, _, _ = _confirm_service(tmp_path, [_fixture_text("letter_confirm_seen.html")])
    detail = service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    assert detail["confirmation"] == {
        "type": "seen",
        "open": True,
        "done": False,
        "sendable": True,
        "confirmed_at": "",
    }


def test_letter_detail_has_no_confirmation_when_iserv_asks_for_none(tmp_path):
    service, _, _ = _confirm_service(tmp_path, [_fixture_text("letter_detail.html")])
    assert service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)["confirmation"] is None


def test_confirm_letter_sends_the_receipt_and_records_it(tmp_path):
    service, store, client = _confirm_service(
        tmp_path,
        [_fixture_text("letter_confirm_seen.html"), _fixture_text("letter_confirm_done.html")],
    )
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    assert result["ok"] is True
    assert result["message_key"] == "api.letters.confirm.ok"
    assert len(client.posts) == 1
    url, payload = client.posts[0]
    assert url.endswith(f"/parent/show/{CONFIRM_LETTER}/{CONFIRM_RECIPIENT}")
    assert payload == {"form[_token]": "fixture-token-0001", "form[submit]": ""}
    record = store.load_letters_confirmations()[f"{CONFIRM_LETTER}:{CONFIRM_RECIPIENT}"]
    assert record["type"] == "seen"
    assert record["confirmed_at"] == result["confirmed_at"]


def test_confirm_letter_refuses_a_second_send(tmp_path):
    service, _, client = _confirm_service(
        tmp_path,
        [_fixture_text("letter_confirm_seen.html"), _fixture_text("letter_confirm_done.html")],
    )
    assert service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)["ok"] is True
    again = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    assert again["ok"] is False
    assert again["message_key"] == "api.letters.confirm.alreadyDone"
    assert len(client.posts) == 1


def test_confirm_letter_reports_a_missing_form(tmp_path):
    service, store, client = _confirm_service(tmp_path, [_fixture_text("letter_confirm_done.html")])
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.confirm.gone"
    assert client.posts == []
    assert store.load_letters_confirmations() == {}


def test_confirm_letter_refuses_accept_decline(tmp_path):
    service, store, client = _confirm_service(tmp_path, [_fixture_text("letter_confirm_choice.html")])
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.confirm.unsupported"
    assert client.posts == []
    assert store.load_letters_confirmations() == {}


def test_confirm_letter_never_records_a_silent_failure(tmp_path):
    seen = _fixture_text("letter_confirm_seen.html")
    service, store, client = _confirm_service(tmp_path, [seen, seen])
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.confirm.rejected"
    assert len(client.posts) == 1
    assert store.load_letters_confirmations() == {}


def test_confirm_letter_reports_an_upstream_status(tmp_path):
    seen = _fixture_text("letter_confirm_seen.html")
    service, store, client = _confirm_service(tmp_path, [seen, seen], post_status=500)
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.confirm.upstream"
    assert result["message_vars"] == {"status": 500}
    assert store.load_letters_confirmations() == {}


def test_letters_list_carries_the_open_confirmation_after_enrichment(tmp_path):
    service, _, _ = _confirm_service(tmp_path, [_fixture_text("letter_confirm_seen.html")])
    assert all(entry["confirmation"] is None for entry in service.letters("current")["letters"])
    service.enrich_letters_search("current")
    entries = service.letters("current")["letters"]
    assert all(entry["confirmation"]["open"] for entry in entries)
    assert service.pending_confirmation_keys("current") == {
        service._letter_key(entry) for entry in entries
    }


def test_enrich_keeps_refreshing_an_open_confirmation_but_stops_once_it_is_done(tmp_path):
    service, store, client = _confirm_service(
        tmp_path,
        [_fixture_text("letter_confirm_seen.html"), _fixture_text("letter_confirm_done.html")],
    )
    first = service.enrich_letters_search("current")
    assert first == 3
    assert service.enrich_letters_search("current") == 3
    assert service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)["ok"] is True
    assert store.load_letters_confirmations()
    remaining = service.enrich_letters_search("current")
    assert remaining == 2
    done = next(
        entry
        for entry in service.letters("current")["letters"]
        if service._letter_key(entry) == f"{CONFIRM_LETTER}:{CONFIRM_RECIPIENT}"
    )
    assert done["confirmation"]["done"] is True
    assert done["confirmation"]["open"] is False
    assert done["confirmation"]["confirmed_at"]


def test_letters_without_a_confirmation_are_not_refetched(tmp_path):
    service, _, _ = _confirm_service(tmp_path, [_fixture_text("letter_detail.html")])
    assert service.enrich_letters_search("current") == 3
    assert service.enrich_letters_search("current") == 0
