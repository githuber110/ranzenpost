from http import HTTPStatus

import pytest
from homeassistant.core_config import async_process_ha_core_config
from homeassistant.setup import async_setup_component

from custom_components.ranzenpost import online_feed
from custom_components.ranzenpost.api import AuthError, ConnectionError, NotFoundError, OnlineFeed, OutsideAccess
from custom_components.ranzenpost.diagnostics import async_get_config_entry_diagnostics
from custom_components.ranzenpost.online_feed import FetchLimiter, OnlineFeeds

from . import fixture, route, setup_entry

WEBHOOK_ID = "ranzenpost_" + "a" * 32
OTHER_WEBHOOK_ID = "ranzenpost_" + "b" * 32
CLOUD_URL = "https://hooks.nabu.casa/abc"
CALENDAR = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"


class FakeApi:
    def __init__(self, calendar=CALENDAR, error=None, report_error=None):
        self.calendar = calendar
        self.error = error
        self.report_error = report_error
        self.reports = []
        self.outside = []
        self.asked = []

    async def feed(self, feed_id, webhook_id):
        self.asked.append((feed_id, webhook_id))
        if self.error is not None:
            raise self.error
        return self.calendar

    async def report_feeds(self, feeds, outside=None):
        if self.report_error is not None:
            raise self.report_error
        self.outside.append(outside)
        if feeds:
            self.reports.append(feeds)


class FakeCloud:
    def __init__(self, active=True, connected=True):
        self.active = active
        self.connected = connected
        self.created = []
        self.deleted = []

    def async_active_subscription(self, hass):
        return self.active

    def async_is_connected(self, hass):
        return self.connected

    def async_is_logged_in(self, hass):
        return self.active

    async def async_get_or_create_cloudhook(self, hass, webhook_id):
        self.created.append(webhook_id)
        return f"{CLOUD_URL}/{webhook_id[-4:]}"

    async def async_delete_cloudhook(self, hass, webhook_id):
        self.deleted.append(webhook_id)


def feed(webhook_id=WEBHOOK_ID, feed_id="sub1", cloud_url="", external_url="", reported=False):
    return OnlineFeed(
        id=feed_id, webhook_id=webhook_id, cloud_url=cloud_url, external_url=external_url, reported=reported
    )


@pytest.fixture
async def webhooks(hass):
    assert await async_setup_component(hass, "webhook", {})
    assert await async_setup_component(hass, "http", {})


@pytest.fixture
def no_cloud(monkeypatch):
    monkeypatch.setattr(online_feed, "_cloud", lambda hass: None)


@pytest.fixture
def cloud(monkeypatch):
    fake = FakeCloud()
    monkeypatch.setattr(online_feed, "_cloud", lambda hass: fake)
    return fake


async def test_an_online_feed_is_served_from_outside_without_login(hass, webhooks, no_cloud, hass_client_no_auth):
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api)
    await feeds.async_sync((feed(),))
    client = await hass_client_no_auth()

    response = await client.get(f"/api/webhook/{WEBHOOK_ID}")

    assert response.status == HTTPStatus.OK
    assert response.content_type == "text/calendar"
    assert await response.text() == CALENDAR
    assert api.asked == [("sub1", WEBHOOK_ID)]


async def test_post_is_not_allowed_on_a_calendar_address(hass, webhooks, no_cloud, hass_client_no_auth):
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api)
    await feeds.async_sync((feed(),))
    client = await hass_client_no_auth()

    response = await client.post(f"/api/webhook/{WEBHOOK_ID}", data="x")

    assert response.status == HTTPStatus.METHOD_NOT_ALLOWED
    assert api.asked == []


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (NotFoundError("gone"), HTTPStatus.NOT_FOUND),
        (ConnectionError("down"), HTTPStatus.SERVICE_UNAVAILABLE),
        (AuthError("rotated"), HTTPStatus.SERVICE_UNAVAILABLE),
        (RuntimeError("odd"), HTTPStatus.SERVICE_UNAVAILABLE),
    ],
)
async def test_add_on_failures_are_passed_on(hass, webhooks, no_cloud, hass_client_no_auth, error, status):
    feeds = OnlineFeeds(hass, "entry1", FakeApi(error=error))
    await feeds.async_sync((feed(),))
    client = await hass_client_no_auth()

    response = await client.get(f"/api/webhook/{WEBHOOK_ID}")

    assert response.status == status


async def test_too_many_fetches_are_refused(hass, webhooks, no_cloud, hass_client_no_auth):
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api, limiter=FetchLimiter(limit=2, window=60, clock=lambda: 100.0))
    await feeds.async_sync((feed(),))
    client = await hass_client_no_auth()

    statuses = [(await client.get(f"/api/webhook/{WEBHOOK_ID}")).status for _ in range(3)]

    assert statuses == [HTTPStatus.OK, HTTPStatus.OK, HTTPStatus.TOO_MANY_REQUESTS]
    assert len(api.asked) == 2


async def test_a_removed_feed_loses_its_webhook(hass, webhooks, no_cloud, hass_client_no_auth):
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api)
    await feeds.async_sync((feed(), feed(OTHER_WEBHOOK_ID, "sub2")))

    await feeds.async_sync((feed(OTHER_WEBHOOK_ID, "sub2"),))

    assert feeds.registered == {OTHER_WEBHOOK_ID: "sub2"}
    client = await hass_client_no_auth()
    response = await client.get(f"/api/webhook/{WEBHOOK_ID}")
    assert await response.text() == ""
    assert api.asked == []


async def test_unloading_removes_every_webhook(hass, webhooks, no_cloud):
    feeds = OnlineFeeds(hass, "entry1", FakeApi())
    await feeds.async_sync((feed(),))

    await feeds.async_unload()

    assert feeds.registered == {}
    again = OnlineFeeds(hass, "entry1", FakeApi())
    await again.async_sync((feed(),))
    assert again.registered == {WEBHOOK_ID: "sub1"}


async def test_without_any_outside_access_the_add_on_still_hears_it(hass, webhooks, no_cloud):
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api)

    await feeds.async_sync((feed(),))

    assert api.reports == [[{"id": "sub1", "webhook_id": WEBHOOK_ID, "cloud_url": "", "external_url": ""}]]


async def test_an_unchanged_reported_state_is_not_reported_again(hass, webhooks, no_cloud):
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api)

    await feeds.async_sync((feed(reported=True),))

    assert api.reports == []


async def test_an_address_the_add_on_would_drop_is_reported_empty(hass, webhooks, no_cloud):
    await async_process_ha_core_config(hass, {"external_url": "https://home.example.test/" + "x" * 600})
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api)

    await feeds.async_sync((feed(),))
    await feeds.async_sync((feed(reported=True),))

    assert [report[0]["external_url"] for report in api.reports] == [""]


async def test_a_failing_sync_never_raises(hass, webhooks, no_cloud):
    feeds = OnlineFeeds(hass, "entry1", FakeApi(report_error=AuthError("rotated")))

    await feeds.async_sync((feed(),))

    assert feeds.registered == {WEBHOOK_ID: "sub1"}


async def test_a_webhook_held_by_another_entry_is_left_alone(hass, webhooks, no_cloud, hass_client_no_auth):
    first_api = FakeApi()
    second_api = FakeApi()
    first = OnlineFeeds(hass, "entry1", first_api)
    second = OnlineFeeds(hass, "entry2", second_api)
    await first.async_sync((feed(),))

    await second.async_sync((feed(),))
    await second.async_unload()

    assert second.registered == {}
    assert second_api.reports == []
    client = await hass_client_no_auth()
    assert await (await client.get(f"/api/webhook/{WEBHOOK_ID}")).text() == CALENDAR


async def test_a_sync_after_unload_registers_nothing(hass, webhooks, no_cloud):
    feeds = OnlineFeeds(hass, "entry1", FakeApi())
    await feeds.async_unload()

    await feeds.async_sync((feed(),))

    assert feeds.registered == {}


async def test_the_external_address_is_reported(hass, webhooks, no_cloud):
    await async_process_ha_core_config(hass, {"external_url": "https://home.example.test:8123"})
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api)

    await feeds.async_sync((feed(),))

    assert api.reports == [[{
        "id": "sub1",
        "webhook_id": WEBHOOK_ID,
        "cloud_url": "",
        "external_url": f"https://home.example.test:8123/api/webhook/{WEBHOOK_ID}",
    }]]


async def test_a_known_address_is_not_reported_again(hass, webhooks, no_cloud):
    await async_process_ha_core_config(hass, {"external_url": "https://home.example.test"})
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api)

    await feeds.async_sync((feed(external_url=f"https://home.example.test/api/webhook/{WEBHOOK_ID}", reported=True),))

    assert api.reports == []


async def test_home_assistant_cloud_creates_and_reports_the_address(hass, webhooks, cloud, hass_storage):
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api)

    await feeds.async_sync((feed(),))

    assert cloud.created == [WEBHOOK_ID]
    assert api.reports[0][0]["cloud_url"] == f"{CLOUD_URL}/aaaa"
    assert hass_storage[online_feed.storage_key("entry1")]["data"] == {"webhook_ids": [WEBHOOK_ID]}


async def test_without_a_subscription_no_cloud_address_is_made(hass, webhooks, cloud):
    cloud.active = False
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api)

    await feeds.async_sync((feed(cloud_url=f"{CLOUD_URL}/aaaa"),))

    assert cloud.created == []
    assert api.reports[0][0]["cloud_url"] == ""


async def test_a_short_cloud_outage_keeps_the_known_address(hass, webhooks, cloud):
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api)
    await feeds.async_sync((feed(),))
    cloud.connected = False

    await feeds.async_sync((feed(cloud_url=f"{CLOUD_URL}/aaaa", reported=True),))

    assert len(api.reports) == 1


async def test_an_old_cloud_address_is_deleted(hass, webhooks, cloud, hass_storage):
    feeds = OnlineFeeds(hass, "entry1", FakeApi())
    await feeds.async_sync((feed(),))

    await feeds.async_sync((feed(OTHER_WEBHOOK_ID, "sub1"),))

    assert cloud.deleted == [WEBHOOK_ID]
    assert hass_storage[online_feed.storage_key("entry1")]["data"] == {"webhook_ids": [OTHER_WEBHOOK_ID]}


async def test_a_failed_delete_is_tried_again(hass, webhooks, cloud):
    feeds = OnlineFeeds(hass, "entry1", FakeApi())
    await feeds.async_sync((feed(),))
    calls = []

    async def failing(hass, webhook_id):
        calls.append(webhook_id)
        raise RuntimeError("offline")

    cloud.async_delete_cloudhook = failing
    await feeds.async_sync(())
    await feeds.async_sync(())

    assert calls == [WEBHOOK_ID, WEBHOOK_ID]


async def test_old_cloud_addresses_are_deleted_even_when_logged_out(hass, webhooks, cloud):
    feeds = OnlineFeeds(hass, "entry1", FakeApi())
    await feeds.async_sync((feed(),))
    cloud.active = False

    await feeds.async_sync(())

    assert cloud.deleted == [WEBHOOK_ID]


async def test_removing_the_entry_deletes_its_cloud_addresses(hass, webhooks, cloud, hass_storage):
    feeds = OnlineFeeds(hass, "entry1", FakeApi())
    await feeds.async_sync((feed(),))

    await online_feed.async_remove_cloudhooks(hass, "entry1")

    assert cloud.deleted == [WEBHOOK_ID]
    assert online_feed.storage_key("entry1") not in hass_storage


async def test_setup_registers_the_feeds_the_add_on_lists(hass, aioclient_mock, no_cloud, hass_client_no_auth):
    info = fixture("info")
    info["online_feeds"] = [{"id": "sub1", "webhook_id": WEBHOOK_ID, "cloud_url": "", "external_url": ""}]
    aioclient_mock.get(route("feed", id="sub1", webhook=WEBHOOK_ID), json={"calendar": CALENDAR})
    aioclient_mock.post(route("feeds"), json={"stored": 1})
    await setup_entry(hass, aioclient_mock, info=info)
    client = await hass_client_no_auth()

    response = await client.get(f"/api/webhook/{WEBHOOK_ID}")

    assert response.status == HTTPStatus.OK
    assert await response.text() == CALENDAR


async def test_feeds_with_odd_webhook_ids_are_ignored(hass, aioclient_mock, no_cloud):
    info = fixture("info")
    info["online_feeds"] = [
        {"id": "sub1", "webhook_id": "automation_hook", "cloud_url": "", "external_url": ""},
        {"id": "", "webhook_id": WEBHOOK_ID, "cloud_url": "", "external_url": ""},
        "x",
    ]
    entry = await setup_entry(hass, aioclient_mock, info=info)

    assert entry.runtime_data.data.info.online_feeds == ()


async def test_diagnostics_never_carry_an_outside_address(hass, aioclient_mock, no_cloud):
    info = fixture("info")
    info["online_feeds"] = [
        {"id": "sub1", "webhook_id": WEBHOOK_ID, "cloud_url": CLOUD_URL, "external_url": "https://x.test/a", "reported": True}
    ]
    aioclient_mock.post(route("feeds"), json={"stored": 1})
    entry = await setup_entry(hass, aioclient_mock, info=info)

    shown = str(await async_get_config_entry_diagnostics(hass, entry))

    assert WEBHOOK_ID not in shown
    assert CLOUD_URL not in shown
    assert "x.test" not in shown


async def test_losing_the_webhook_after_a_restart_keeps_the_shared_cloud_address(hass, webhooks, cloud):
    before = OnlineFeeds(hass, "entry1", FakeApi())
    await before.async_sync((feed(),))
    await before.async_unload()
    other = OnlineFeeds(hass, "entry2", FakeApi())
    await other.async_sync((feed(),))

    after = OnlineFeeds(hass, "entry1", FakeApi())
    await after.async_sync((feed(),))

    assert cloud.deleted == []
    assert after.registered == {}


async def test_a_held_webhook_is_warned_about_once(hass, webhooks, no_cloud, caplog):
    first = OnlineFeeds(hass, "entry1", FakeApi())
    second = OnlineFeeds(hass, "entry2", FakeApi())
    await first.async_sync((feed(),))

    for _ in range(3):
        await second.async_sync((feed(),))

    assert caplog.text.count("already served by another Ranzenpost entry") == 1


async def test_an_unknown_access_from_outside_is_reported_without_feeds(hass, webhooks, no_cloud):
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api)

    await feeds.async_sync((), OutsideAccess())

    assert api.outside == [{"cloud": False, "external": False}]
    assert api.reports == []


async def test_a_known_access_from_outside_is_not_reported_again(hass, webhooks, no_cloud):
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api)

    await feeds.async_sync((), OutsideAccess(reported=True))

    assert api.outside == []


async def test_a_new_cloud_subscription_is_reported(hass, webhooks, cloud):
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api)

    await feeds.async_sync((), OutsideAccess(reported=True))

    assert api.outside == [{"cloud": True, "external": False}]


async def test_an_external_url_counts_as_access_from_outside(hass, webhooks, no_cloud):
    await async_process_ha_core_config(hass, {"external_url": "https://home.example.test"})
    api = FakeApi()
    feeds = OnlineFeeds(hass, "entry1", api)

    await feeds.async_sync((), OutsideAccess(reported=True))

    assert api.outside == [{"cloud": False, "external": True}]


async def test_setup_reports_the_access_from_outside(hass, aioclient_mock, no_cloud):
    aioclient_mock.post(route("feeds"), json={"stored": 0})
    await setup_entry(hass, aioclient_mock)

    posted = [call for call in aioclient_mock.mock_calls if call[0] == "POST"]
    assert posted and posted[0][2] == {"feeds": [], "outside": {"cloud": False, "external": False}}
