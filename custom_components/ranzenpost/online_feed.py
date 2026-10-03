from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from http import HTTPStatus
from typing import Any
from urllib.parse import urlsplit

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.storage import Store

from .api import NotFoundError, OnlineFeed, OutsideAccess, RanzenpostApi
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CLOUD_DOMAIN = "cloud"
STORAGE_VERSION = 1
CALENDAR_CONTENT_TYPE = "text/calendar"
CACHE_CONTROL = "private, max-age=300"
FETCH_LIMIT = 20
FETCH_WINDOW_SECONDS = 60.0
RETRY_AFTER_LIMITED = "60"
RETRY_AFTER_UNAVAILABLE = "300"
WEBHOOK_NAME = "Ranzenpost calendar"
MAX_URL_LENGTH = 512
URL_SCHEMES = ("https", "http")


def storage_key(entry_id: str) -> str:
    return f"{DOMAIN}.{entry_id}.cloudhooks"


def _cloud(hass: HomeAssistant) -> Any | None:
    if CLOUD_DOMAIN not in hass.config.components:
        return None
    try:
        from homeassistant.components import cloud
    except ImportError:
        return None
    return cloud


def clean_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > MAX_URL_LENGTH or any(char.isspace() for char in text):
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return ""
    if parts.scheme not in URL_SCHEMES or not parts.hostname or parts.username or parts.password:
        return ""
    return text


def external_base(hass: HomeAssistant) -> str:
    try:
        return get_url(hass, allow_internal=False, allow_cloud=False, prefer_external=True)
    except NoURLAvailableError:
        return ""


def external_url(hass: HomeAssistant, webhook_id: str) -> str:
    base = external_base(hass)
    if not base:
        return ""
    return clean_url(base.rstrip("/") + webhook.async_generate_path(webhook_id))


def outside_access(hass: HomeAssistant) -> dict[str, bool]:
    cloud = _cloud(hass)
    return {
        "cloud": bool(cloud is not None and cloud.async_active_subscription(hass)),
        "external": bool(clean_url(external_base(hass))),
    }


class FetchLimiter:
    def __init__(
        self,
        limit: int = FETCH_LIMIT,
        window: float = FETCH_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window = window
        self.clock = clock
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = self.clock()
        recent = [stamp for stamp in self._hits.get(key, ()) if now - stamp < self.window]
        if len(recent) >= self.limit:
            self._hits[key] = recent
            return False
        recent.append(now)
        self._hits[key] = recent
        return True

    def forget(self, key: str) -> None:
        self._hits.pop(key, None)


class OnlineFeeds:
    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        api: RanzenpostApi,
        limiter: FetchLimiter | None = None,
    ) -> None:
        self.hass = hass
        self.api = api
        self.limiter = limiter or FetchLimiter()
        self._store: Store[dict[str, list[str]]] = Store(hass, STORAGE_VERSION, storage_key(entry_id))
        self._feeds: dict[str, str] = {}
        self._cloudhooks: set[str] | None = None
        self._lock = asyncio.Lock()
        self._closed = False
        self._held: set[str] = set()

    @property
    def registered(self) -> dict[str, str]:
        return dict(self._feeds)

    async def async_sync(self, feeds: tuple[OnlineFeed, ...], known: OutsideAccess | None = None) -> None:
        try:
            async with self._lock:
                if self._closed:
                    return
                await self._sync(feeds, known or OutsideAccess(reported=True))
        except Exception as err:
            _LOGGER.warning("the calendar addresses from outside could not be updated: %s", type(err).__name__)

    async def _sync(self, feeds: tuple[OnlineFeed, ...], known: OutsideAccess) -> None:
        wanted = {feed.webhook_id: feed for feed in feeds}
        for webhook_id in [registered for registered in self._feeds if registered not in wanted]:
            self._unregister(webhook_id)
        self._held &= set(wanted)
        for webhook_id, feed in wanted.items():
            if webhook_id in self._feeds or self._register(webhook_id):
                self._feeds[webhook_id] = feed.id
        await self._drop_cloudhooks(set(wanted))
        reports = []
        for feed in feeds:
            if feed.webhook_id not in self._feeds:
                continue
            cloud_url = clean_url(await self._cloud_url(feed))
            outside_url = external_url(self.hass, feed.webhook_id)
            if feed.reported and (cloud_url, outside_url) == (feed.cloud_url, feed.external_url):
                continue
            reports.append(
                {"id": feed.id, "webhook_id": feed.webhook_id, "cloud_url": cloud_url, "external_url": outside_url}
            )
        current = outside_access(self.hass)
        changed = not known.reported or (current["cloud"], current["external"]) != (known.cloud, known.external)
        if not reports and not changed:
            return
        await self.api.report_feeds(reports, current if changed else None)
        _LOGGER.info(
            "reported %s calendar address(es) from outside to the add-on%s",
            len(reports),
            ", access from outside changed" if changed else "",
        )

    async def async_unload(self) -> None:
        async with self._lock:
            self._closed = True
            for webhook_id in list(self._feeds):
                self._unregister(webhook_id)

    def _register(self, webhook_id: str) -> bool:
        try:
            webhook.async_register(
                self.hass,
                DOMAIN,
                WEBHOOK_NAME,
                webhook_id,
                self._handle,
                local_only=False,
                allowed_methods=("GET",),
            )
        except ValueError:
            if webhook_id not in self._held:
                self._held.add(webhook_id)
                _LOGGER.warning("a calendar address from outside is already served by another Ranzenpost entry")
            return False
        self._held.discard(webhook_id)
        return True

    def _unregister(self, webhook_id: str) -> None:
        self._feeds.pop(webhook_id, None)
        self.limiter.forget(webhook_id)
        webhook.async_unregister(self.hass, webhook_id)

    async def _known_cloudhooks(self) -> set[str]:
        if self._cloudhooks is None:
            stored = await self._store.async_load() or {}
            self._cloudhooks = {str(item) for item in stored.get("webhook_ids") or []}
        return self._cloudhooks

    async def _save_cloudhooks(self) -> None:
        await self._store.async_save({"webhook_ids": sorted(await self._known_cloudhooks())})

    async def _cloud_url(self, feed: OnlineFeed) -> str:
        cloud = _cloud(self.hass)
        if cloud is None or not cloud.async_active_subscription(self.hass):
            return ""
        known = await self._known_cloudhooks()
        if not cloud.async_is_connected(self.hass):
            return feed.cloud_url if feed.webhook_id in known else ""
        try:
            url = await cloud.async_get_or_create_cloudhook(self.hass, feed.webhook_id)
        except Exception as err:
            _LOGGER.warning("Home Assistant Cloud could not create the calendar address: %s", type(err).__name__)
            return feed.cloud_url if feed.webhook_id in known else ""
        if feed.webhook_id not in known:
            known.add(feed.webhook_id)
            await self._save_cloudhooks()
            _LOGGER.info("Home Assistant Cloud created a calendar address")
        return str(url or "")

    async def _drop_cloudhooks(self, wanted: set[str]) -> None:
        known = await self._known_cloudhooks()
        stale = known - wanted
        if not stale:
            return
        cloud = _cloud(self.hass)
        for webhook_id in stale:
            if cloud is not None and not await _delete_cloudhook(cloud, self.hass, webhook_id):
                continue
            known.discard(webhook_id)
        await self._save_cloudhooks()

    async def _handle(self, hass: HomeAssistant, webhook_id: str, request: Any) -> web.Response:
        feed_id = self._feeds.get(webhook_id)
        if feed_id is None:
            return web.Response(status=HTTPStatus.NOT_FOUND)
        if not self.limiter.allow(webhook_id):
            _LOGGER.info("a calendar address from outside was asked too often, refused for a minute")
            return web.Response(status=HTTPStatus.TOO_MANY_REQUESTS, headers={"Retry-After": RETRY_AFTER_LIMITED})
        try:
            calendar = await self.api.feed(feed_id, webhook_id)
        except NotFoundError:
            return web.Response(status=HTTPStatus.NOT_FOUND)
        except Exception as err:
            _LOGGER.warning("a calendar from outside could not be read from the add-on: %s", type(err).__name__)
            return web.Response(
                status=HTTPStatus.SERVICE_UNAVAILABLE, headers={"Retry-After": RETRY_AFTER_UNAVAILABLE}
            )
        return web.Response(text=calendar, content_type=CALENDAR_CONTENT_TYPE, headers={"Cache-Control": CACHE_CONTROL})


async def _delete_cloudhook(cloud: Any, hass: HomeAssistant, webhook_id: str) -> bool:
    try:
        await cloud.async_delete_cloudhook(hass, webhook_id)
    except ValueError:
        return True
    except Exception as err:
        _LOGGER.warning(
            "Home Assistant Cloud could not delete an old calendar address, retrying later: %s", type(err).__name__
        )
        return False
    return True


async def async_remove_cloudhooks(hass: HomeAssistant, entry_id: str) -> None:
    store: Store[dict[str, list[str]]] = Store(hass, STORAGE_VERSION, storage_key(entry_id))
    stored = await store.async_load() or {}
    cloud = _cloud(hass)
    if cloud is not None:
        for webhook_id in stored.get("webhook_ids") or []:
            await _delete_cloudhook(cloud, hass, str(webhook_id))
    await store.async_remove()
