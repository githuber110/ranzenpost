import re

import pytest
from fastapi.testclient import TestClient

from app import subscriptions
from app.integration_api import IntegrationAccess
from app.server import create_app
from app.subscriptions import SubscriptionRegistry
from tests.test_calendar_feed import FakeHolidayCalendar
from tests.test_integration_api import CHILD_ID, INGRESS, PREFIX, Clock, FakeService, _auth, _store

WEBHOOK = re.compile(r"^ranzenpost_[0-9a-f]{32}$")
CLOUD_URL = "https://hooks.nabu.casa/abc123"
EXTERNAL_URL = "https://home.example.test:8123/api/webhook/x"


@pytest.fixture(autouse=True)
def _no_supervisor(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.setenv("ISERV_ADDON_VERSION", "2609.02.00")


def _registry(tmp_path):
    store = _store(tmp_path)
    return store, SubscriptionRegistry(store, clock=Clock())


def _created(registry):
    return registry.create(CHILD_ID, ["timetable"])


def _online(registry):
    entry = _created(registry)
    return registry.update(entry["id"], online=True)


def _webhook_of(registry, subscription_id):
    return next(feed["webhook_id"] for feed in registry.online_feeds() if feed["id"] == subscription_id)


def _report(registry, view, cloud_url=CLOUD_URL, external_url=""):
    webhook_id = _webhook_of(registry, view["id"])
    return registry.record_online_reports(
        [{"id": view["id"], "webhook_id": webhook_id, "cloud_url": cloud_url, "external_url": external_url}]
    )


def test_a_new_subscription_is_not_reachable_from_outside(tmp_path):
    _, registry = _registry(tmp_path)

    view = _created(registry)

    assert (view["online"], view["online_state"], view["online_url"]) == (False, "off", "")
    assert registry.online_feeds() == []
    assert registry.find_online(view["id"], "ranzenpost_" + "0" * 32) is None


def test_going_online_waits_for_home_assistant_with_a_fresh_webhook(tmp_path):
    _, registry = _registry(tmp_path)

    view = _online(registry)

    assert (view["online"], view["online_state"], view["online_url"]) == (True, "pending", "")
    feeds = registry.online_feeds()
    assert [(feed["id"], feed["cloud_url"], feed["external_url"]) for feed in feeds] == [(view["id"], "", "")]
    assert WEBHOOK.match(feeds[0]["webhook_id"])
    assert feeds[0]["webhook_id"] not in str(view)


def test_switching_online_twice_keeps_the_webhook(tmp_path):
    _, registry = _registry(tmp_path)
    view = _online(registry)
    first = _webhook_of(registry, view["id"])

    registry.update(view["id"], online=True)

    assert _webhook_of(registry, view["id"]) == first


def test_a_report_makes_the_cloud_address_visible(tmp_path):
    _, registry = _registry(tmp_path)
    view = _online(registry)

    assert _report(registry, view, external_url=EXTERNAL_URL) == ["ready"]

    shown = registry.list()[0]
    assert (shown["online_state"], shown["online_url"]) == ("ready", CLOUD_URL)
    assert registry.online_feeds()[0]["external_url"] == EXTERNAL_URL


def test_the_external_address_is_shown_without_a_cloud_address(tmp_path):
    _, registry = _registry(tmp_path)
    view = _online(registry)

    _report(registry, view, cloud_url="", external_url=EXTERNAL_URL)

    assert registry.list()[0]["online_url"] == EXTERNAL_URL


def test_a_report_without_any_address_says_unreachable(tmp_path):
    _, registry = _registry(tmp_path)
    view = _online(registry)

    assert _report(registry, view, cloud_url="") == ["unreachable"]

    assert (registry.list()[0]["online_state"], registry.list()[0]["online_url"]) == ("unreachable", "")


@pytest.mark.parametrize(
    "address",
    [
        "javascript:alert(1)",
        "ftp://hooks.nabu.casa/x",
        "https://user:secret@hooks.nabu.casa/x",
        "https://hooks.nabu.casa/a b",
        "https:///nohost",
        "https://" + "a" * 600 + ".test/",
        42,
    ],
)
def test_odd_addresses_are_dropped(tmp_path, address):
    _, registry = _registry(tmp_path)
    view = _online(registry)

    assert _report(registry, view, cloud_url=address) == ["unreachable"]
    assert registry.online_feeds()[0]["cloud_url"] == ""


def test_a_report_for_an_old_webhook_is_ignored(tmp_path):
    _, registry = _registry(tmp_path)
    view = _online(registry)
    old = _webhook_of(registry, view["id"])
    registry.rotate(view["id"])

    stored = registry.record_online_reports(
        [{"id": view["id"], "webhook_id": old, "cloud_url": CLOUD_URL, "external_url": ""}]
    )

    assert stored == []
    assert registry.list()[0]["online_state"] == "pending"


def test_a_report_for_a_subscription_that_is_not_online_is_ignored(tmp_path):
    _, registry = _registry(tmp_path)
    view = _created(registry)

    stored = registry.record_online_reports(
        [{"id": view["id"], "webhook_id": "ranzenpost_" + "0" * 32, "cloud_url": CLOUD_URL, "external_url": ""}]
    )

    assert stored == []
    assert registry.list()[0]["online"] is False


def test_renewing_the_link_also_renews_the_outside_address(tmp_path):
    _, registry = _registry(tmp_path)
    view = _online(registry)
    _report(registry, view)
    old = _webhook_of(registry, view["id"])

    renewed = registry.rotate(view["id"])

    assert (renewed["online"], renewed["online_state"], renewed["online_url"]) == (True, "pending", "")
    assert _webhook_of(registry, view["id"]) != old


def test_renewing_an_offline_subscription_stays_offline(tmp_path):
    _, registry = _registry(tmp_path)
    view = _created(registry)

    assert registry.rotate(view["id"])["online"] is False
    assert registry.online_feeds() == []


def test_going_offline_forgets_webhook_and_addresses(tmp_path):
    store, registry = _registry(tmp_path)
    view = _online(registry)
    _report(registry, view)

    offline = registry.update(view["id"], online=False)

    assert (offline["online"], offline["online_state"], offline["online_url"]) == (False, "off", "")
    assert registry.online_feeds() == []
    stored = store.load_calendar_subscriptions()["subscriptions"][0]
    assert not {subscriptions.ONLINE_FIELD, subscriptions.WEBHOOK_FIELD, subscriptions.REPORT_FIELD} & set(stored)


def test_a_deleted_subscription_leaves_no_online_feed(tmp_path):
    _, registry = _registry(tmp_path)
    view = _online(registry)

    registry.revoke(view["id"])

    assert registry.online_feeds() == []


def _app(tmp_path, clock=None):
    clock = clock or Clock()
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store, clock=clock)
    access = IntegrationAccess(store, clock=clock, announce=lambda token: None)
    app = create_app(
        FakeService(store),
        holiday_calendar=FakeHolidayCalendar(),
        registry=registry,
        integration_access=access,
        calendar_warmer=lambda child_id: None,
    )
    return TestClient(app), store, registry


def test_info_lists_the_online_feeds_for_the_integration(tmp_path):
    client, store, registry = _app(tmp_path)
    view = _online(registry)

    body = client.get(PREFIX + "/info", headers=_auth(store)).json()

    assert body["online_feeds"] == [
        {
            "id": view["id"],
            "webhook_id": _webhook_of(registry, view["id"]),
            "cloud_url": "",
            "external_url": "",
            "reported": False,
        }
    ]


def test_the_feed_route_answers_the_calendar_of_an_online_subscription(tmp_path):
    client, store, registry = _app(tmp_path)
    view = _online(registry)

    params = {"id": view["id"], "webhook": _webhook_of(registry, view["id"])}
    response = client.get(PREFIX + "/feed", params=params, headers=_auth(store))

    assert response.status_code == 200
    assert response.json()["calendar"].startswith("BEGIN:VCALENDAR")
    assert registry.list()[0]["last_fetched_at"] > 0


def test_the_feed_route_refuses_a_subscription_that_is_not_online(tmp_path):
    client, store, registry = _app(tmp_path)
    view = _created(registry)

    response = client.get(PREFIX + "/feed", params={"id": view["id"], "webhook": "ranzenpost_" + "0" * 32}, headers=_auth(store))

    assert response.status_code == 404
    assert response.json()["error"] == "unknown_feed"


@pytest.mark.parametrize("webhook", ["", "ranzenpost_" + "0" * 32, "ranzenpost_"])
def test_the_feed_route_needs_the_current_webhook_id(tmp_path, webhook):
    client, store, registry = _app(tmp_path)
    view = _online(registry)

    response = client.get(PREFIX + "/feed", params={"id": view["id"], "webhook": webhook}, headers=_auth(store))

    assert response.status_code == 404


def test_a_renewed_link_ends_the_old_outside_address_at_once(tmp_path):
    client, store, registry = _app(tmp_path)
    view = _online(registry)
    old = _webhook_of(registry, view["id"])
    registry.rotate(view["id"])

    stale = client.get(PREFIX + "/feed", params={"id": view["id"], "webhook": old}, headers=_auth(store))
    fresh = client.get(
        PREFIX + "/feed", params={"id": view["id"], "webhook": _webhook_of(registry, view["id"])}, headers=_auth(store)
    )

    assert (stale.status_code, fresh.status_code) == (404, 200)


def test_the_feed_route_needs_the_integration_token(tmp_path):
    client, _, registry = _app(tmp_path)
    view = _online(registry)

    assert client.get(PREFIX + "/feed", params={"id": view["id"]}).status_code == 401
    wrong = {"Authorization": "Bearer nope"}
    assert client.post(PREFIX + "/feeds", json={"feeds": []}, headers=wrong).status_code == 401


def test_the_feed_routes_refuse_the_ingress_proxy(tmp_path):
    client, store, registry = _app(tmp_path)
    view = _online(registry)
    headers = dict(_auth(store), **INGRESS)

    assert client.get(PREFIX + "/feed", params={"id": view["id"]}, headers=headers).status_code == 403
    assert client.post(PREFIX + "/feeds", json={"feeds": []}, headers=headers).status_code == 403


def test_the_integration_reports_the_addresses(tmp_path):
    client, store, registry = _app(tmp_path)
    view = _online(registry)
    report = {"id": view["id"], "webhook_id": _webhook_of(registry, view["id"]), "cloud_url": CLOUD_URL, "external_url": ""}

    response = client.post(PREFIX + "/feeds", json={"feeds": [report]}, headers=_auth(store))

    assert response.json() == {"stored": 1}
    shown = client.get("/api/calendar/subscriptions").json()["subscriptions"][0]
    assert (shown["online_state"], shown["online_url"]) == ("ready", CLOUD_URL)


@pytest.mark.parametrize("body", [{}, {"feeds": "x"}, {"feeds": [{}] * 101}, []])
def test_a_malformed_report_is_refused(tmp_path, body):
    client, store, _ = _app(tmp_path)

    response = client.post(PREFIX + "/feeds", json=body, headers=_auth(store))

    assert response.status_code == 400
    assert response.json()["error"] == "bad_feeds"


def _reachable(client, store, cloud=True):
    client.post(PREFIX + "/feeds", json={"feeds": [], "outside": {"cloud": cloud, "external": False}}, headers=_auth(store))


def test_the_app_switches_a_subscription_online_and_back(tmp_path):
    client, store, registry = _app(tmp_path)
    _reachable(client, store)
    view = _created(registry)
    path = f"/api/calendar/subscriptions/{view['id']}"

    assert client.post(path, json={"online": True}).json()["online_state"] == "pending"
    assert client.post(path, json={"label": "Plan"}).json()["online"] is True
    assert client.post(path, json={"online": "yes"}).json()["online"] is True
    assert client.post(path, json={"online": False}).json()["online"] is False


def _shown_state(client):
    return client.get("/api/calendar/subscriptions").json()["subscriptions"][0]


def test_without_the_integration_an_online_subscription_says_so(tmp_path):
    client, _, registry = _app(tmp_path)
    _online(registry)

    assert _shown_state(client)["online_state"] == "no_integration"


def test_a_fresh_online_subscription_waits_for_the_integration(tmp_path):
    client, store, registry = _app(tmp_path)
    _online(registry)
    client.get(PREFIX + "/info", headers=_auth(store))

    assert _shown_state(client)["online_state"] == "pending"


def test_an_integration_that_never_reports_is_named(tmp_path):
    clock = Clock()
    client, store, registry = _app(tmp_path, clock=clock)
    _online(registry)
    clock.epoch += 3000
    client.get(PREFIX + "/info", headers=_auth(store))
    assert _shown_state(client)["online_state"] == "pending"

    clock.epoch += subscriptions.STALL_GRACE_SECONDS

    assert _shown_state(client)["online_state"] == "stalled"


def test_other_requests_of_the_integration_do_not_count_as_offered(tmp_path):
    clock = Clock()
    client, store, registry = _app(tmp_path, clock=clock)
    view = _online(registry)
    clock.epoch += subscriptions.STALL_GRACE_SECONDS * 3
    client.get(PREFIX + "/feed", params={"id": view["id"], "webhook": "ranzenpost_" + "0" * 32}, headers=_auth(store))
    clock.epoch += subscriptions.STALL_GRACE_SECONDS * 3

    assert _shown_state(client)["online_state"] == "pending"


def test_a_report_right_after_the_offer_is_ready(tmp_path):
    clock = Clock()
    client, store, registry = _app(tmp_path, clock=clock)
    view = _online(registry)
    client.get(PREFIX + "/info", headers=_auth(store))
    report = {"id": view["id"], "webhook_id": _webhook_of(registry, view["id"]), "cloud_url": CLOUD_URL, "external_url": ""}
    client.post(PREFIX + "/feeds", json={"feeds": [report]}, headers=_auth(store))
    clock.epoch += subscriptions.STALL_GRACE_SECONDS * 3

    assert _shown_state(client)["online_state"] == "ready"


def test_a_renewed_link_is_offered_afresh(tmp_path):
    clock = Clock()
    client, store, registry = _app(tmp_path, clock=clock)
    view = _online(registry)
    client.get(PREFIX + "/info", headers=_auth(store))
    clock.epoch += subscriptions.STALL_GRACE_SECONDS * 3
    registry.rotate(view["id"])

    assert _shown_state(client)["online_state"] == "pending"


def test_a_ready_address_is_hidden_once_home_assistant_is_gone(tmp_path):
    clock = Clock()
    client, store, registry = _app(tmp_path, clock=clock)
    view = _online(registry)
    client.get(PREFIX + "/info", headers=_auth(store))
    _report(registry, view)
    assert (_shown_state(client)["online_state"], _shown_state(client)["online_url"]) == ("ready", CLOUD_URL)

    clock.epoch += subscriptions.INTEGRATION_WINDOW_SECONDS + 1

    assert (_shown_state(client)["online_state"], _shown_state(client)["online_url"]) == ("no_integration", "")


def test_an_offline_subscription_stays_off_without_the_integration(tmp_path):
    client, _, registry = _app(tmp_path)
    _created(registry)

    assert _shown_state(client)["online_state"] == "off"


def test_only_feeds_in_the_answer_count_as_offered(tmp_path):
    _, registry = _registry(tmp_path)
    shown = _online(registry)
    later = registry.update(_created(registry)["id"], online=True)

    assert registry.mark_offered([_webhook_of(registry, shown["id"])]) == 1

    views = {view["id"]: view for view in registry.list()}
    assert views[shown["id"]]["offered_at"] > 0
    assert views[later["id"]]["offered_at"] == 0


def test_a_subscription_can_start_on_the_internet(tmp_path):
    _, registry = _registry(tmp_path)

    view = registry.create(CHILD_ID, ["timetable"], online=True)

    assert (view["online"], view["online_state"]) == (True, "pending")
    assert WEBHOOK.match(_webhook_of(registry, view["id"]))


def test_the_app_creates_an_internet_subscription(tmp_path):
    client, store, _ = _app(tmp_path)
    _reachable(client, store)

    created = client.post("/api/calendar/subscriptions", json={"child_key": CHILD_ID, "components": ["timetable"], "online": True}).json()
    plain = client.post("/api/calendar/subscriptions", json={"child_key": CHILD_ID, "components": ["timetable"], "online": "yes"}).json()

    assert (created["online"], plain["online"]) == (True, False)


def _internet(client):
    return client.get("/api/calendar/subscriptions").json()["internet"]


def test_the_internet_choice_needs_the_integration(tmp_path):
    client, _, _ = _app(tmp_path)

    assert _internet(client) == "no_integration"


def test_an_integration_that_never_said_how_it_is_reached_needs_an_update(tmp_path):
    clock = Clock()
    client, store, _ = _app(tmp_path, clock=clock)
    clock.epoch += subscriptions.STALL_GRACE_SECONDS
    client.get(PREFIX + "/info", headers=_auth(store))

    assert _internet(client) == "update_integration"


@pytest.mark.parametrize(
    ("outside", "expected"),
    [
        ({"cloud": True, "external": False}, "ready"),
        ({"cloud": False, "external": True}, "ready"),
        ({"cloud": False, "external": False}, "no_access"),
        ({"cloud": "yes", "external": 1}, "no_access"),
    ],
)
def test_the_reported_access_from_outside_decides_the_internet_choice(tmp_path, outside, expected):
    client, store, _ = _app(tmp_path)

    response = client.post(PREFIX + "/feeds", json={"feeds": [], "outside": outside}, headers=_auth(store))

    assert response.json() == {"stored": 0}
    assert _internet(client) == expected


def test_info_tells_the_integration_what_the_add_on_knows_about_outside_access(tmp_path):
    client, store, _ = _app(tmp_path)

    before = client.get(PREFIX + "/info", headers=_auth(store)).json()["outside_access"]
    client.post(PREFIX + "/feeds", json={"feeds": [], "outside": {"cloud": True, "external": False}}, headers=_auth(store))
    after = client.get(PREFIX + "/info", headers=_auth(store)).json()["outside_access"]

    assert before == {"cloud": False, "external": False, "reported": False}
    assert after == {"cloud": True, "external": False, "reported": True}


def test_a_report_without_outside_keeps_the_known_access(tmp_path):
    client, store, _ = _app(tmp_path)
    client.post(PREFIX + "/feeds", json={"feeds": [], "outside": {"cloud": True, "external": False}}, headers=_auth(store))

    client.post(PREFIX + "/feeds", json={"feeds": []}, headers=_auth(store))

    assert _internet(client) == "ready"


def test_internet_is_refused_without_access_from_outside(tmp_path):
    client, store, registry = _app(tmp_path)
    _reachable(client, store, cloud=False)
    view = _created(registry)

    created = client.post("/api/calendar/subscriptions", json={"child_key": CHILD_ID, "components": ["timetable"], "online": True})
    switched = client.post(f"/api/calendar/subscriptions/{view['id']}", json={"online": True})

    assert (created.status_code, switched.status_code) == (400, 400)
    assert created.json()["message_key"] == "calendar.subscribe.variant.internet.noAccess"
    assert registry.online_feeds() == []


def test_an_internet_calendar_stays_editable_while_access_is_gone(tmp_path):
    client, store, registry = _app(tmp_path)
    _reachable(client, store)
    view = client.post("/api/calendar/subscriptions", json={"child_key": CHILD_ID, "components": ["timetable"], "online": True}).json()
    _reachable(client, store, cloud=False)

    edited = client.post(f"/api/calendar/subscriptions/{view['id']}", json={"label": "Plan", "online": True})

    assert edited.status_code == 200
    assert (edited.json()["label"], edited.json()["online"]) == ("Plan", True)


def test_right_after_a_restart_the_access_is_being_checked(tmp_path):
    clock = Clock()
    client, store, _ = _app(tmp_path, clock=clock)
    client.get(PREFIX + "/state", params={"child": CHILD_ID}, headers=_auth(store))

    assert _internet(client) == "checking"

    clock.epoch += subscriptions.STALL_GRACE_SECONDS
    client.get(PREFIX + "/state", params={"child": CHILD_ID}, headers=_auth(store))

    assert _internet(client) == "update_integration"
