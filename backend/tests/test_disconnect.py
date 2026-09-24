import pytest

from app.service import IServService, NotConfiguredError
from app.store import Store
from tests.support import add_school, connection_service


class FakeResponse:
    def __init__(self, text):
        self.text = text


class DisconnectClient:
    def __init__(self, url):
        self.url = url
        self.authed = False
        self.list_page = (
            '<form id="deleteTwoFactorForm">'
            '<input type="hidden" name="delete[_token]" value="csrf-x">'
            "</form>"
        )
        self.delete_result = True
        self.deleted_args = None

    def login(self, username, password, code_provider):
        assert code_provider()
        self.authed = True
        return self

    def is_authenticated(self):
        return self.authed

    def get_twofactor_list_page(self):
        return FakeResponse(self.list_page)

    def delete_totp_token(self, uuid, code, csrf_token):
        self.deleted_args = (uuid, code, csrf_token)
        return self.delete_result


def make(tmp_path, uuid="uuid-1", delete_result=True, list_page=None):
    store = Store(tmp_path / "data")
    secrets = {"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP"}
    if uuid:
        secrets["twofactor_uuid"] = uuid
    connection_id = add_school(store, "https://school.example", secrets)
    scoped = store.connection_store(connection_id)
    scoped.save_seen({"pinboard": [1, 2, 3]})
    scoped.save_absence_history({"a": {}})
    scoped.save_letters_search_cache({"b": {}})
    client = DisconnectClient("https://school.example")
    client.delete_result = delete_result
    if list_page is not None:
        client.list_page = list_page
    service = connection_service(store, connection_id, lambda url: client)
    return service, scoped, client


def test_disconnect_with_stored_uuid_generates_a_fresh_code_and_deletes_by_uuid(tmp_path):
    service, store, client = make(tmp_path, uuid="uuid-1", delete_result=True)
    result = service.disconnect()
    assert result["attempted"] is True
    assert result["removed"] is True
    assert result["message"] == "2FA-Token in IServ entfernt."
    uuid, code, csrf = client.deleted_args
    assert uuid == "uuid-1"
    assert csrf == "csrf-x"
    assert len(code) == 6 and code.isdigit()


def test_disconnect_without_a_stored_uuid_never_attempts_a_delete(tmp_path):
    service, store, client = make(tmp_path, uuid=None)
    result = service.disconnect()
    assert result["attempted"] is False
    assert result["removed"] is False
    assert "selbst entfernen" in result["message"]
    assert client.deleted_args is None


def test_disconnect_reports_failure_when_iserv_still_lists_the_token(tmp_path):
    service, store, client = make(tmp_path, uuid="uuid-1", delete_result=False)
    result = service.disconnect()
    assert result["attempted"] is True
    assert result["removed"] is False
    assert "nicht entfernt" in result["message"]


def test_disconnect_reports_failure_when_the_csrf_token_is_missing(tmp_path):
    service, store, client = make(tmp_path, uuid="uuid-1", list_page="<html></html>")
    result = service.disconnect()
    assert result["attempted"] is True
    assert result["removed"] is False
    assert client.deleted_args is None


def test_disconnect_always_does_local_cleanup_on_success(tmp_path):
    service, store, client = make(tmp_path, uuid="uuid-1", delete_result=True)
    service.disconnect()
    assert store.load_seen() == {}
    assert store.load_absence_history() == {}
    assert store.load_letters_search_cache() == {}


def test_disconnect_always_does_local_cleanup_on_failure(tmp_path):
    service, store, client = make(tmp_path, uuid="uuid-1", delete_result=False)
    service.disconnect()
    assert store.load_seen() == {}
    assert store.load_absence_history() == {}
    assert store.load_letters_search_cache() == {}


def test_disconnect_always_does_local_cleanup_when_skipped(tmp_path):
    service, store, client = make(tmp_path, uuid=None)
    service.disconnect()
    assert store.load_seen() == {}
    assert store.load_absence_history() == {}
    assert store.load_letters_search_cache() == {}


def test_disconnect_forgets_the_module_registry_and_the_integration_state(tmp_path):
    service, store, client = make(tmp_path, uuid=None)
    store.save_modules({"modules": {"timetable": False}, "checked_at": 1})
    store.save_integration_state({"last_request": 1, "last_poll": {"changes": ["x"]}})

    service.disconnect()

    assert store.load_modules() == {}
    assert store.load_integration_state() == {}


def test_disconnect_clears_config_and_secrets_as_the_ui_promises(tmp_path):
    service, store, client = make(tmp_path, uuid="uuid-1", delete_result=True)
    store.base.update_connection(
        service.id,
        children=[{"child_id": "1", "name": "Mia"}],
        phones=[{"label": "Sekretariat", "number": "0123"}],
    )
    service.disconnect()
    assert store.base.connection(service.id) is None
    assert store.base.connections() == []
    assert store.load_config()["school_url"] == ""
    assert store.load_config()["children"] == []
    assert store.load_config()["phones"] == []
    assert store.load_secrets() == {}
    assert service.is_configured() is False


def test_disconnect_forgets_the_children_the_school_listed(tmp_path):
    service, store, client = make(tmp_path, uuid=None)
    children = service._child_service
    children._remember_children([{"child_id": "500001", "name": "Mia"}])
    children._listed_ids = (service.clock(), {"500001"})
    assert service.authorized_child("500001") == "500001"

    service.disconnect()

    assert service._cached_child("500001") is None
    with pytest.raises(NotConfiguredError):
        service.authorized_child("500001")
