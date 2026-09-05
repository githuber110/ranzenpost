import pytest
from fastapi.testclient import TestClient

from app.iserv.children import (
    CHILD_PAGE_MESSAGE_KEY,
    child_select_present,
    page_diagnosis,
    parse_children,
)
from app.iserv.errors import DataError
from app.server import create_app

SELECT_PAGE = (
    "<html><body><form>"
    '<select id="timetable-filter-child-select">'
    '<option value="c1">Kim</option>'
    '<option value="c2">Alex</option>'
    "</select></form></body></html>"
)
EMPTY_SELECT_PAGE = (
    '<html><body><select id="timetable-filter-child-select"></select></body></html>'
)
LOGIN_PAGE = (
    '<html><body><form><input name="_username"><input name="_password">'
    '<select id="language"></select></form></body></html>'
)


class FakePage:
    def __init__(self, status_code=200, text="", url="", headers=None):
        self.status_code = status_code
        self.text = text
        self.url = url
        self.headers = headers or {}


class FakeSession:
    def __init__(self, page):
        self.page = page
        self.headers = {}

    def get(self, url, **kwargs):
        return self.page


def _client(page):
    from app.iserv.client import IServClient

    return IServClient("https://school.example", session=FakeSession(page))


def test_a_page_that_carries_the_child_select_is_read_as_before():
    assert child_select_present(SELECT_PAGE)
    children = _client(FakePage(200, SELECT_PAGE)).get_children()
    assert [child.child_id for child in children] == ["c1", "c2"]


def test_an_account_without_a_child_is_an_empty_list_not_a_failure():
    assert child_select_present(EMPTY_SELECT_PAGE)
    assert _client(FakePage(200, EMPTY_SELECT_PAGE)).get_children() == []


def test_a_page_without_the_child_select_is_a_failure_instead_of_an_empty_list():
    with pytest.raises(DataError) as caught:
        _client(FakePage(200, LOGIN_PAGE, url="https://school.example/iserv/auth/login")).get_children()
    assert caught.value.message_key == CHILD_PAGE_MESSAGE_KEY
    assert caught.value.detail["child_select"] is False
    assert caught.value.detail["login_form"] is True
    assert caught.value.detail["final_path"] == "/iserv/auth/login"


@pytest.mark.parametrize("status", [302, 403, 500, 503])
def test_a_page_the_server_refused_is_never_read_as_an_empty_family(status):
    with pytest.raises(DataError) as caught:
        _client(FakePage(status, SELECT_PAGE)).get_children()
    assert caught.value.detail["status"] == status


def test_the_diagnosis_describes_the_page_without_repeating_its_content():
    secret = "Kim Mustermann"
    page = FakePage(
        200,
        f"<html><body><p>{secret}</p><select id='other'></select></body></html>",
        url="https://school.example/iserv/time-table/?child=1",
        headers={"content-type": "text/html; charset=utf-8"},
    )
    shape = page_diagnosis(page)
    assert shape["content_type"] == "text/html"
    assert shape["final_path"] == "/iserv/time-table/"
    assert shape["select_elements"] == 1
    assert shape["child_select"] is False
    assert secret not in str(shape)


class FailingService:
    def __init__(self):
        self.store = None

    def is_configured(self):
        return True

    def check_connection(self):
        return "ok"

    def children(self):
        raise DataError(
            "child list page was not readable",
            message_key=CHILD_PAGE_MESSAGE_KEY,
            detail={"status": 200, "child_select": False},
        )


class StubStore:
    def load_secrets(self):
        return {}

    def load_config(self):
        return {}


class StubWizard:
    def status(self):
        return {}


def test_the_route_answers_with_the_reason_instead_of_an_empty_list():
    service = FailingService()
    service.store = StubStore()
    api = TestClient(create_app(service, wizard=StubWizard()))
    payload = api.get("/api/children").json()
    assert payload["error"] == "network"
    assert payload["message_key"] == CHILD_PAGE_MESSAGE_KEY
    assert payload["diagnosis"]["child_select"] is False
    assert payload != []


def test_the_parser_itself_is_unchanged_for_a_normal_page():
    assert [child.name for child in parse_children(SELECT_PAGE)] == ["Kim", "Alex"]
