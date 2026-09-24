import pytest

from app import integration, modules
from app.iserv.models import Child
from app.not_configured import ConnectionChangedError
from app.poller import Poller
from app.service import IServService, NotConfiguredError
from app.store import LOGIN_REVISION_KEY
from tests.support import single_school
from tests.test_child_list_states import rerun, wizard_with_child
from tests.test_connections import FakeClient, two_schools

LISTED = [{"child_id": "uuid-1", "name": "Bella", "class_name": "2b"}]


class ListingClient:
    during_fetch = None

    def __init__(self, url):
        self.url = url
        self.base_url = url
        self.session = None
        self.authed = False

    def login(self, username, password, code_provider):
        self.authed = True
        return self

    def is_authenticated(self):
        return self.authed

    def get_children(self):
        if self.during_fetch is not None:
            self.during_fetch()
        return [Child("uuid-1", "Bella")]


def listing_school(tmp_path):
    clients = []

    def factory(url):
        client = ListingClient(url)
        clients.append(client)
        return client

    service, scoped, connection_id = single_school(tmp_path / "data", client_factory=factory)
    return service, scoped, clients


def refused(call):
    try:
        call()
    except NotConfiguredError:
        return True
    return False


def listed_after(action):
    def fetch():
        action()
        return [dict(child) for child in LISTED]

    return fetch


def test_a_disconnect_during_the_timetable_list_leaves_no_child_behind(tmp_path):
    service, scoped, _ = listing_school(tmp_path)
    ListingClient.during_fetch = service.disconnect
    try:
        outcome = refused(service.children)
    finally:
        ListingClient.during_fetch = None
    assert scoped.base.connections() == []
    assert service.stored_children() == []
    assert outcome is True


def test_a_disconnect_during_the_school_account_list_keeps_no_cache(tmp_path):
    service, scoped, _ = listing_school(tmp_path)
    old = service._child_service
    old._children_from_school_account = listed_after(service.disconnect)
    outcome = refused(service.children)
    assert old._children_cache[1] == {}
    assert old._listed_ids[1] == set()
    assert service._cached_child("uuid-1") is None
    assert service.stored_children() == []
    assert outcome is True


def test_a_replaced_child_list_does_not_fill_its_cache_afterwards(tmp_path):
    service, _, _ = listing_school(tmp_path)
    old = service._child_service
    service._clear_local_data()
    old._remember_children(LISTED)
    assert old._children_cache[1] == {}


def test_a_login_switch_during_the_child_list_drops_the_old_children(tmp_path):
    wizard, flat = wizard_with_child(tmp_path)
    connection_id = flat.load_config()["connection_id"]
    before = IServService(flat.base).connection(connection_id)
    before._child_service._children_from_school_account = listed_after(
        lambda: rerun(wizard, "someone.else", "school-one.example")
    )
    outcome = refused(before.children)
    assert flat.load_config()["children"] == []
    assert outcome is True


def test_an_unchanged_connection_still_learns_the_listed_children(tmp_path):
    service, _, _ = listing_school(tmp_path)
    service._child_service._children_from_school_account = listed_after(lambda: None)
    assert [child["child_id"] for child in service.children()] == ["uuid-1"]
    assert [child["child_id"] for child in service.stored_children()] == ["uuid-1"]
    assert service._cached_child("uuid-1")["name"] == "Bella"


def wizard_school(tmp_path):
    wizard, flat = wizard_with_child(tmp_path)
    connection_id = flat.load_config()["connection_id"]
    service = IServService(flat.base, client_factory=ListingClient)
    return wizard, flat, service, connection_id


def switch_to_another_account(wizard):
    return lambda: rerun(wizard, "someone.else", "school-one.example")


def test_a_connection_built_before_an_account_switch_never_reads_the_list(tmp_path):
    wizard, flat, service, connection_id = wizard_school(tmp_path)
    before = service.connection(connection_id)
    rerun(wizard, "someone.else", "school-one.example")
    before._child_service._children_from_school_account = lambda: pytest.fail("the old session must not list children")
    with pytest.raises(ConnectionChangedError):
        before.children()
    with pytest.raises(NotConfiguredError):
        before.authorized_child("uuid-1")
    assert flat.load_config()["children"] == []


def test_an_account_switch_during_the_timetable_list_drops_the_old_children(tmp_path):
    wizard, flat, service, connection_id = wizard_school(tmp_path)
    before = service.connection(connection_id)
    ListingClient.during_fetch = staticmethod(switch_to_another_account(wizard))
    try:
        outcome = refused(before.children)
    finally:
        ListingClient.during_fetch = None
    assert flat.load_config()["children"] == []
    assert outcome is True


def test_an_account_switch_during_the_fallback_list_drops_the_old_children(tmp_path):
    wizard, flat, service, connection_id = wizard_school(tmp_path)
    before = service.connection(connection_id)
    before.module_available = lambda module: module != modules.TIMETABLE
    before._child_service._fallback_children = listed_after(switch_to_another_account(wizard))
    outcome = refused(before.children)
    assert flat.load_config()["children"] == []
    assert outcome is True


@pytest.mark.parametrize("school", [True, False], ids=["one-school", "all-schools"])
def test_signing_in_again_with_the_same_account_during_the_list_still_answers(tmp_path, school):
    wizard, flat, service, connection_id = wizard_school(tmp_path)
    before = service.connection(connection_id)
    calls = []

    def fetch():
        calls.append(1)
        if len(calls) == 1:
            rerun(wizard, "parent", "school-one.example")
        return [dict(child) for child in LISTED]

    ListingClient.during_fetch = None
    before._child_service._children_from_school_account = fetch
    original = IServService.connection

    def fresh(self, wanted, entry=None):
        made = original(self, wanted, entry)
        if made is not before:
            made._child_service._children_from_school_account = fetch
        return made

    IServService.connection = fresh
    try:
        listed = service.children(connection_id if school else None)
    finally:
        IServService.connection = original
    assert [child["child_id"] for child in listed] == ["uuid-1"]
    assert len(calls) == 2
    assert [child["child_id"] for child in flat.load_config()["children"]] == ["uuid-1"]


def test_a_disconnect_during_the_list_of_one_school_answers_not_configured(tmp_path):
    service, store, one, _, _ = two_schools(tmp_path)
    connection = service.connection(one)
    connection._child_service._children_from_school_account = listed_after(lambda: service.disconnect(one))
    with pytest.raises(NotConfiguredError):
        service.children(one)
    assert store.connection(one) is None


def bump_revision(store, connection_id):
    entry = store.connection(connection_id)
    store.update_connection(connection_id, login_revision=int(entry.get(LOGIN_REVISION_KEY) or 0) + 1)


@pytest.mark.parametrize("change", ["disconnect", "switch"])
def test_the_poller_skips_a_school_that_changed_during_its_child_list(tmp_path, change, caplog):
    holder = {}

    class ChangingClient(FakeClient):
        def get_children(self):
            if change == "disconnect":
                holder["service"].disconnect(holder["one"])
            else:
                bump_revision(holder["store"], holder["one"])
            return super().get_children()

    service, store, one, two, _ = two_schools(
        tmp_path, {"https://school-one.example": lambda url: ChangingClient(url, children=[("c1", "Alice Example")])}
    )
    holder.update(service=service, store=store, one=one)
    for name in (one, two):
        store.connection_store(name).save_modules(
            {"modules": {name: name == modules.TIMETABLE for name in modules.MODULES}, "checked_at": 1}
        )
    with caplog.at_level("WARNING", logger="app.poller"):
        events = Poller(service, notifier=lambda name, message: True).poll_once()
    assert [record.getMessage() for record in caplog.records if "skipped: changed" in record.getMessage()] == [f"poll school#{one} skipped: changed"]
    assert not [entry for entry in events if entry.get("connection_id") == one]
    assert integration.school_state(store, one) == {}
    assert integration.school_state(store, two)["last_poll_ok"] is True
    assert store.load_integration_state()["last_poll_ok"] is True
    if change == "switch":
        assert store.connection(one)["children"] == []


def test_a_sign_in_bumps_the_revision_once_after_the_new_credentials(tmp_path):
    wizard, flat = wizard_with_child(tmp_path)
    connection_id = flat.load_config()["connection_id"]
    base = flat.base
    seen = []
    original = base.update_connection

    def recording(wanted, **fields):
        if LOGIN_REVISION_KEY in fields:
            seen.append((base.load_secrets(wanted).get("username"), dict(fields)))
        return original(wanted, **fields)

    base.update_connection = recording
    rerun(wizard, "someone.else", "school-one.example")
    assert len(seen) == 1
    username, fields = seen[0]
    assert username == "someone.else"
    assert fields["children"] == []
    assert fields["course_filters"] == {}
    assert base.connection(connection_id)["children"] == []


def test_an_old_list_landing_while_the_new_login_is_stored_is_forgotten_with_the_bump(tmp_path):
    wizard, flat, service, connection_id = wizard_school(tmp_path)
    before = service.connection(connection_id)
    before._child_service._children_from_school_account = listed_after(lambda: None)
    base = flat.base
    original = base.save_secrets
    landed = []

    def storing(wanted, secrets):
        if secrets.get("username") == "someone.else" and not landed:
            landed.append([child["child_id"] for child in before.children()])
        return original(wanted, secrets)

    base.save_secrets = storing
    rerun(wizard, "someone.else", "school-one.example")
    base.save_secrets = original
    assert landed == [["uuid-1"]]
    assert flat.load_config()["children"] == []
