from app.service import IServService
from app.store import Store


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
    store.save_config({"school_url": "https://school.example"})
    secrets = {"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP"}
    if uuid:
        secrets["twofactor_uuid"] = uuid
    store.save_secrets(secrets)
    store.save_seen({"pinboard": [1, 2, 3]})
    store.save_absence_history({"a": {}})
    store.save_letters_search_cache({"b": {}})
    client = DisconnectClient("https://school.example")
    client.delete_result = delete_result
    if list_page is not None:
        client.list_page = list_page
    service = IServService(store, client_factory=lambda url: client)
    return service, store, client


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


def test_disconnect_clears_config_and_secrets_as_the_ui_promises(tmp_path):
    service, store, client = make(tmp_path, uuid="uuid-1", delete_result=True)
    store.save_config(
        {
            "school_url": "https://school.example",
            "children": [{"child_id": "1", "name": "Mia"}],
            "phones": [{"label": "Sekretariat", "number": "0123"}],
        }
    )
    service.disconnect()
    assert store.load_config()["school_url"] == ""
    assert store.load_config()["children"] == []
    assert store.load_config()["phones"] == []
    assert store.load_secrets() == {}
    assert service.is_configured() is False
