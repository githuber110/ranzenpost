import logging

import pytest
import requests

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
            '<table><tbody><tr id="client-twofactor-row-00000000-0000-4000-8000-000000000001"><td>Handy</td></tr></tbody></table>'
            '<form id="deleteTwoFactorForm">'
            '<input type="hidden" name="delete[_token]" value="csrf-x">'
            "</form>"
        )
        self.delete_result = True
        self.delete_error = None
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
        if self.delete_error is not None:
            raise self.delete_error
        return self.delete_result


def make(tmp_path, uuid="00000000-0000-4000-8000-000000000001", delete_result=True, list_page=None):
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
    service, store, client = make(tmp_path, uuid="00000000-0000-4000-8000-000000000001", delete_result=True)
    result = service.disconnect()
    assert result["attempted"] is True
    assert result["removed"] is True
    assert result["message"] == "2FA-Token in IServ entfernt."
    uuid, code, csrf = client.deleted_args
    assert uuid == "00000000-0000-4000-8000-000000000001"
    assert csrf == "csrf-x"
    assert len(code) == 6 and code.isdigit()


def token_list(*names):
    rows = "".join(
        f'<tr id="client-twofactor-row-00000000-0000-4000-8000-00000000000{index}"><td>{name}</td></tr>' for index, name in enumerate(names, 1)
    )
    return (
        f"<table><tbody>{rows}</tbody></table>"
        '<form id="deleteTwoFactorForm"><input type="hidden" name="delete[_token]" value="csrf-x"></form>'
    )


def test_disconnect_without_a_stored_uuid_and_no_app_token_listed_deletes_nothing(tmp_path):
    service, store, client = make(tmp_path, uuid=None, list_page=token_list("Handy"))
    result = service.disconnect()
    assert result["removed"] is True
    assert result["disconnected"] is True
    assert result["message_key"] == "api.disconnect.noToken"
    assert client.deleted_args is None
    assert store.load_secrets() == {}


def test_disconnect_without_a_stored_uuid_lets_the_user_choose_instead_of_guessing(tmp_path):
    service, store, client = make(tmp_path, uuid=None, list_page=token_list("Handy", "ISERV-Connector"))
    result = service.disconnect()
    assert result["disconnected"] is False
    assert result["message_key"] == "api.disconnect.choose"
    assert [token["id"] for token in result["tokens"]] == ["00000000-0000-4000-8000-000000000002"]
    assert result["retryable"] is False
    assert client.deleted_args is None
    assert store.load_secrets()["totp_secret"]


def test_several_tokens_with_the_app_name_are_all_offered_and_none_is_removed(tmp_path):
    service, store, client = make(
        tmp_path, uuid=None, list_page=token_list("ISERV-Connector", "ISERV-Connector")
    )
    result = service.disconnect()
    assert result["disconnected"] is False
    assert [token["id"] for token in result["tokens"]] == ["00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002"]
    assert result["retryable"] is False
    assert client.deleted_args is None


def test_the_chosen_token_is_removed_and_only_when_iserv_still_lists_it(tmp_path):
    service, store, client = make(tmp_path, uuid=None, list_page=token_list("ISERV-Connector", "ISERV-Connector"))
    stale = service.disconnect(token_id="00000000-0000-4000-8000-000000000009")
    assert stale["disconnected"] is False
    assert client.deleted_args is None
    chosen = service.disconnect(token_id="00000000-0000-4000-8000-000000000002")
    assert client.deleted_args[0] == "00000000-0000-4000-8000-000000000002"
    assert chosen["removed"] is True
    assert chosen["disconnected"] is True


def test_an_unreadable_token_list_never_claims_there_is_no_token(tmp_path):
    unreadable = (
        "<table><tbody><tr><td>ISERV-Connector</td></tr></tbody></table>"
        '<form id="deleteTwoFactorForm"><input type="hidden" name="delete[_token]" value="csrf-x"></form>'
    )
    service, store, client = make(tmp_path, uuid=None, list_page=unreadable)
    result = service.disconnect()
    assert result["removed"] is False
    assert result["disconnected"] is False
    assert result["message_key"] == "api.disconnect.unreadable"
    assert result["retryable"] is True
    assert store.load_secrets()["totp_secret"]


def test_a_failed_removal_can_be_tried_again(tmp_path):
    service, store, client = make(tmp_path, uuid="00000000-0000-4000-8000-000000000001", delete_result=False)
    assert service.disconnect()["retryable"] is True


def test_disconnect_without_a_token_secret_never_contacts_iserv(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example", {"username": "u", "password": "p"})
    client = DisconnectClient("https://school.example")
    service = connection_service(store, connection_id, lambda url: client)
    result = service.disconnect()
    assert result["attempted"] is False
    assert result["disconnected"] is True
    assert client.deleted_args is None
    assert client.authed is False


def test_disconnect_reports_failure_when_iserv_still_lists_the_token(tmp_path):
    service, store, client = make(tmp_path, uuid="00000000-0000-4000-8000-000000000001", delete_result=False)
    result = service.disconnect()
    assert result["attempted"] is True
    assert result["removed"] is False
    assert result["message_key"] == "api.disconnect.failed"
    assert result["disconnected"] is False


def test_disconnect_reports_failure_when_the_csrf_token_is_missing(tmp_path):
    service, store, client = make(tmp_path, uuid="00000000-0000-4000-8000-000000000001", list_page="<html></html>")
    result = service.disconnect()
    assert result["attempted"] is True
    assert result["removed"] is False
    assert client.deleted_args is None


def test_disconnect_always_does_local_cleanup_on_success(tmp_path):
    service, store, client = make(tmp_path, uuid="00000000-0000-4000-8000-000000000001", delete_result=True)
    service.disconnect()
    assert store.load_seen() == {}
    assert store.load_absence_history() == {}
    assert store.load_letters_search_cache() == {}


def test_a_failed_token_removal_keeps_the_connection_so_the_app_can_try_again(tmp_path):
    service, store, client = make(tmp_path, uuid="00000000-0000-4000-8000-000000000001", delete_result=False)
    first = service.disconnect()
    assert first["disconnected"] is False
    assert store.load_seen() == {"pinboard": [1, 2, 3]}
    assert store.load_secrets()["twofactor_uuid"] == "00000000-0000-4000-8000-000000000001"
    client.delete_result = True
    again = service.disconnect()
    assert again["removed"] is True
    assert again["disconnected"] is True
    assert store.load_seen() == {}
    assert store.load_secrets() == {}


def test_disconnecting_anyway_clears_the_app_and_says_the_token_stays(tmp_path):
    service, store, client = make(tmp_path, uuid="00000000-0000-4000-8000-000000000001", delete_result=False)
    result = service.disconnect(force=True)
    assert client.deleted_args is not None
    assert result["removed"] is False
    assert result["disconnected"] is True
    assert result["message_key"] == "api.disconnect.forced"
    assert store.load_seen() == {}
    assert store.load_absence_history() == {}
    assert store.load_letters_search_cache() == {}
    assert store.load_secrets() == {}


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
    service, store, client = make(tmp_path, uuid="00000000-0000-4000-8000-000000000001", delete_result=True)
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


PLANTED_HOST = "planted-school.example"


def test_disconnect_network_failure_logs_the_cause_without_the_host(tmp_path, caplog):
    service, store, client = make(tmp_path, uuid="00000000-0000-4000-8000-000000000001")

    def broken():
        raise requests.ConnectionError(
            f"HTTPSConnectionPool(host='{PLANTED_HOST}', port=443): Max retries exceeded with url: /iserv/account/twofactor"
        )

    client.get_twofactor_list_page = broken
    with caplog.at_level(logging.WARNING, logger="app.service"):
        result = service.disconnect()
    assert result["attempted"] is True
    assert result["removed"] is False
    assert "removing the two-factor token could not be confirmed: ConnectionError at" in caplog.text
    assert PLANTED_HOST not in caplog.text
    assert caplog.records[0].exc_info is None


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


def test_a_school_whose_token_stays_is_still_listed_until_it_is_disconnected_anyway(tmp_path):
    store = Store(tmp_path / "data")
    secrets = {"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP", "twofactor_uuid": "00000000-0000-4000-8000-000000000001"}
    connection_id = add_school(store, "https://school.example", secrets)
    client = DisconnectClient("https://school.example")
    client.delete_result = False
    service = IServService(store, client_factory=lambda url: client)
    assert service.disconnect(connection_id)["disconnected"] is False
    assert [entry["id"] for entry in store.connections()] == [connection_id]
    assert service.known_connection(connection_id).id == connection_id
    assert service.disconnect(connection_id, force=True)["disconnected"] is True
    assert store.connections() == []


def test_a_stored_token_iserv_no_longer_lists_counts_as_removed_without_a_second_delete(tmp_path):
    service, store, client = make(tmp_path, list_page=token_list("Handy").replace("00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-00000000000a"))
    result = service.disconnect()
    assert result["removed"] is True
    assert result["disconnected"] is True
    assert result["message_key"] == "api.disconnect.removed"
    assert client.deleted_args is None


@pytest.mark.parametrize(
    "page",
    [
        '<h1>Bitte Passwort erneut eingeben</h1><form id="deleteTwoFactorForm"><input type="hidden" name="delete[_token]" value="csrf-x"></form>'
        "<table><tbody><tr></tr></tbody></table>",
        '<form id="deleteTwoFactorForm"><input type="hidden" name="delete[_token]" value="csrf-x"></form>'
        "<table><tbody><tr><td></td></tr></tbody></table>",
    ],
)
def test_a_stored_token_on_an_unrecognised_list_is_neither_deleted_nor_called_removed(tmp_path, page):
    service, store, client = make(tmp_path, list_page=page)
    result = service.disconnect()
    assert result["removed"] is False
    assert result["disconnected"] is False
    assert result["message_key"] == "api.disconnect.unreadable"
    assert client.deleted_args is None


def test_an_unrecognised_list_after_the_delete_is_unclear_and_keeps_the_connection(tmp_path):
    from app.iserv.errors import DataError

    service, store, client = make(tmp_path)
    client.delete_error = DataError("not recognised", message_key="api.disconnect.unclear")
    result = service.disconnect()
    assert client.deleted_args is not None
    assert result["removed"] is False
    assert result["disconnected"] is False
    assert result["retryable"] is True
    assert result["message_key"] == "api.disconnect.unclear"
    assert store.load_secrets()["totp_secret"]
