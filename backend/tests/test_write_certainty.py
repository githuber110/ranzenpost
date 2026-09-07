import pytest

from app.iserv.dsa import SCHOOL_APP_UNREADABLE_KEY
from app.iserv.errors import DataError
from app.service import (
    LETTER_ARCHIVE_FAILED_KEY,
    LETTER_RESTORE_FAILED_KEY,
    IServService,
)
from app.store import Store

LETTER_ID = "11111111"
RECIPIENT_ID = "22222222"
ARCHIVE_HREF = "/iserv/parentletter/parent/parent_hide/11111111/22222222"
LETTER_PAGE = (
    "<html><body><h1>Elternbrief</h1>"
    '<a href="' + ARCHIVE_HREF + '">Archivieren</a>'
    "<p>Inhalt</p></body></html>"
)
HIDE_CONFIRM = (
    '<html><body><form action="/iserv/parentletter/parent/hide/confirm" method="post">'
    '<input name="hide_confirm[_token]" value="tok">'
    '<button type="submit" name="hide_confirm[submit]" value="1">Ja</button>'
    "</form></body></html>"
)
ARCHIVE_LIST = (
    '<html><body><form action="/iserv/parentletter/parent/archive" method="post">'
    '<input name="iserv_crud_multi_select[_token]" value="tok">'
    '<input type="checkbox" name="iserv_crud_multi_select[multi][]" value="11111111-22222222">'
    '<button type="submit" name="iserv_crud_multi_select[actions][parent-restore-letter]" value="restore">'
    "Wiederherstellen</button>"
    "</form></body></html>"
)
BATCH_CONFIRM = (
    '<html><body><form action="/iserv/parentletter/parent/batch/confirm" method="post">'
    '<input name="iserv_crud_multi_select[_token]" value="tok">'
    '<input type="hidden" name="iserv_crud_multi_select[multi][]" value="11111111-22222222">'
    '<button type="submit" name="iserv_crud_multi_select[actions][parent-restore-letter]" value="restore">'
    "Ja</button>"
    "</form></body></html>"
)


class Answer:
    def __init__(self, status_code=200, text="", url="https://school.example/x"):
        self.status_code = status_code
        self.text = text
        self.url = url
        self.headers = {}


class Client:
    def __init__(self, url, pages=None, post_status=200, fetch_status=200):
        self.base_url = url
        self.session = object()
        self.pages = pages or {}
        self.post_status = post_status
        self.fetch_status = fetch_status
        self.posts = []

    def login(self, username, password, code_provider):
        return self

    def is_authenticated(self):
        return True

    def fetch(self, path, params=None):
        for fragment, page in self.pages.items():
            if fragment in path:
                return page
        return Answer(self.fetch_status, "", "https://school.example" + path)

    def fetch_or_raise(self, path, params=None):
        response = self.fetch(path, params)
        if response.status_code != 200:
            raise DataError("request failed: %s" % response.status_code)
        return response

    def post_absolute(self, url, data=None, timeout=30):
        self.posts.append(url)
        return Answer(self.post_status, "", url)


def make(tmp_path, client):
    store = Store(tmp_path / "data")
    store.save_config({"school_url": "https://school.example"})
    store.save_secrets({"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP"})
    service = IServService(store, client_factory=lambda url: client)
    return service, store


def _archive_client(post_status=200):
    return Client(
        "https://school.example",
        pages={"parent_hide/": Answer(200, HIDE_CONFIRM), "show/": Answer(200, LETTER_PAGE)},
        post_status=post_status,
    )


def _restore_client(post_status=200):
    pages = {"archive": Answer(200, ARCHIVE_LIST)}
    client = Client("https://school.example", pages=pages, post_status=post_status)
    original = client.post_absolute

    def post(url, data=None, timeout=30):
        answer = original(url, data, timeout)
        answer.text = BATCH_CONFIRM
        return answer

    client.post_absolute = post
    return client


def test_archiving_a_letter_still_works_when_the_server_accepts_it(tmp_path):
    service, _ = make(tmp_path, _archive_client())
    assert service.archive_letter(LETTER_ID, RECIPIENT_ID) is True


def test_a_refused_archive_is_reported_instead_of_claimed_as_done(tmp_path):
    service, _ = make(tmp_path, _archive_client(post_status=500))
    with pytest.raises(DataError) as caught:
        service.archive_letter(LETTER_ID, RECIPIENT_ID)
    assert caught.value.message_key == LETTER_ARCHIVE_FAILED_KEY
    assert caught.value.detail["status"] == 500


def test_a_refused_letter_page_never_becomes_a_successful_archive(tmp_path):
    client = Client(
        "https://school.example",
        pages={"parent_hide/": Answer(200, HIDE_CONFIRM), "show/": Answer(403, LETTER_PAGE)},
    )
    service, _ = make(tmp_path, client)
    with pytest.raises(DataError):
        service.archive_letter(LETTER_ID, RECIPIENT_ID)
    assert client.posts == [], "the change was sent even though the page was refused"


def test_a_refused_confirmation_page_never_becomes_a_successful_archive(tmp_path):
    client = Client(
        "https://school.example",
        pages={"parent_hide/": Answer(403, HIDE_CONFIRM), "show/": Answer(200, LETTER_PAGE)},
    )
    service, _ = make(tmp_path, client)
    with pytest.raises(DataError):
        service.archive_letter(LETTER_ID, RECIPIENT_ID)
    assert client.posts == []


def test_restoring_a_letter_still_works_when_the_server_accepts_it(tmp_path):
    service, _ = make(tmp_path, _restore_client())
    assert service.restore_letter(LETTER_ID, RECIPIENT_ID) is True


def test_a_refused_restore_is_reported_instead_of_claimed_as_done(tmp_path):
    service, _ = make(tmp_path, _restore_client(post_status=500))
    with pytest.raises(DataError) as caught:
        service.restore_letter(LETTER_ID, RECIPIENT_ID)
    assert caught.value.message_key == LETTER_RESTORE_FAILED_KEY


def test_a_letter_list_the_server_refused_is_a_failure_not_an_empty_inbox(tmp_path):
    service, _ = make(tmp_path, Client("https://school.example", fetch_status=503))
    with pytest.raises(DataError):
        service.letters()


class SchoolApp:
    def __init__(self, boards=None, unreadable=False):
        self.boards = boards or []
        self.unreadable = unreadable

    def pinboards_or_raise(self):
        if self.unreadable:
            raise DataError("school app did not answer with data", message_key=SCHOOL_APP_UNREADABLE_KEY)
        return list(self.boards)


class RefusingSession:
    def __init__(self, status_code=503, payload=None):
        self.status_code = status_code
        self.payload = payload

    def get(self, url, params=None, timeout=None):
        return _SchoolAnswer(self.status_code, self.payload)


class _SchoolAnswer:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_the_real_school_app_client_refuses_to_turn_a_bad_answer_into_an_empty_list():
    from app.iserv.dsa import DieSchulAppClient

    client = DieSchulAppClient("https://school.example", RefusingSession(503))
    with pytest.raises(DataError) as caught:
        client.pinboards_or_raise()
    assert caught.value.message_key == SCHOOL_APP_UNREADABLE_KEY
    with pytest.raises(DataError):
        client.sick_note_children_or_raise()


def test_the_real_school_app_client_still_returns_a_genuinely_empty_list():
    from app.iserv.dsa import DieSchulAppClient

    client = DieSchulAppClient("https://school.example", RefusingSession(200, []))
    assert client.pinboards_or_raise() == []
    assert client.sick_note_children_or_raise() == []


def test_an_unreadable_pinboard_is_a_failure_not_an_empty_board(tmp_path):
    service, _ = make(tmp_path, Client("https://school.example"))
    service._dsa = lambda: SchoolApp(unreadable=True)
    with pytest.raises(DataError) as caught:
        service.pinboard()
    assert caught.value.message_key == SCHOOL_APP_UNREADABLE_KEY


def test_a_genuinely_empty_pinboard_is_still_just_empty(tmp_path):
    service, _ = make(tmp_path, Client("https://school.example"))
    service._dsa = lambda: SchoolApp(boards=[])
    assert service.pinboard()["feed"] == []


def test_marking_letters_read_counts_the_ones_it_could_not_open(tmp_path):
    service, _ = make(tmp_path, Client("https://school.example", fetch_status=500))
    result = service.mark_letters_read(["11111111:22222222"])
    assert result["failed"] == 1
    assert result["read"] == 0


def test_marks_follow_the_child_to_its_new_id(tmp_path):
    from app.marks import MarkRegistry

    store = Store(tmp_path / "data")
    store.save_marks({"marks": [
        {"id": "m1", "child_id": "uuid-old", "date": "07.09.2026", "period": 1, "subject_code": "D"},
        {"id": "m2", "child_id": "uuid-other", "date": "07.09.2026", "period": 2, "subject_code": "M"},
    ]})
    assert MarkRegistry(store).move_child("uuid-old", "500001") == 1
    stored = store.load_marks()["marks"]
    assert [entry["child_id"] for entry in stored] == ["500001", "uuid-other"]


def test_moving_a_child_nowhere_changes_nothing(tmp_path):
    from app.marks import MarkRegistry

    store = Store(tmp_path / "data")
    store.save_marks({"marks": [{"id": "m1", "child_id": "a"}]})
    registry = MarkRegistry(store)
    assert registry.move_child("", "b") == 0
    assert registry.move_child("a", "a") == 0
    assert store.load_marks()["marks"][0]["child_id"] == "a"
