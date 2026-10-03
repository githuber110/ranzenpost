import logging
import os
import threading
import time
from hmac import compare_digest
from typing import Any

from fastapi import Body, Request
from fastapi.responses import JSONResponse

from . import feed, holidays, integration, messages, supervisor, versions
from .calendar_server import RateLimiter
from .subscriptions import ONLINE_READY, known_child, token_log_prefix

logger = logging.getLogger(__name__)

PREFIX = "/api/integration"
STATUS_PATH = "/api/integration-status"
ROUTE_INFO = PREFIX + "/info"
ROUTE_STATE = PREFIX + "/state"
ROUTE_EVENTS = PREFIX + "/events"
ROUTE_SCHOOL = PREFIX + "/school"
ROUTE_CHANGES = PREFIX + "/changes"
ROUTE_FEED = PREFIX + "/feed"
ROUTE_FEEDS = PREFIX + "/feeds"
ROUTES = (ROUTE_INFO, ROUTE_STATE, ROUTE_EVENTS, ROUTE_SCHOOL, ROUTE_CHANGES, ROUTE_FEED, ROUTE_FEEDS)
MAX_FEED_REPORTS = 100
INTEGRATION_PORT = 8099
BEARER = "bearer"
INGRESS_HEADER = "x-ingress-path"
VERSION_HEADER = "x-ranzenpost-integration"
INSTALLED_HEADER = "x-ranzenpost-integration-installed"
FAILED_ATTEMPT_LIMIT = 10
FAILED_ATTEMPT_WINDOW_SECONDS = 60
PORT_STATE_TTL_SECONDS = 60
INGRESS_PROXY_ADDRESS = "172.30.32.2"
INGRESS_ONLY_ENV = "ISERV_INGRESS_ONLY"
SUPERVISOR_TOKEN_ENV = "SUPERVISOR_TOKEN"

UNAUTHORIZED_KEY = "api.integration.unauthorized"
INGRESS_REFUSED_KEY = "api.integration.ingressRefused"
INGRESS_REQUIRED_KEY = "api.integration.ingressRequired"
TOO_MANY_ATTEMPTS_KEY = "api.integration.tooManyAttempts"
UNKNOWN_CHILD_KEY = "api.integration.unknownChild"
UNKNOWN_SCHOOL_KEY = "api.integration.unknownSchool"
BAD_KIND_KEY = "api.integration.badKind"
BAD_RANGE_KEY = "api.integration.badRange"
BAD_PURPOSE_KEY = "api.integration.badPurpose"
TOKEN_ROTATED_KEY = "api.integration.token.rotated"
UNKNOWN_FEED_KEY = "api.integration.unknownFeed"
BAD_FEEDS_KEY = "api.integration.badFeeds"

ERROR_UNAUTHORIZED = "unauthorized"
ERROR_FORBIDDEN = "forbidden"
ERROR_RATE_LIMITED = "rate_limited"
ERROR_UNKNOWN_CHILD = "unknown_child"
ERROR_UNKNOWN_SCHOOL = "unknown_school"
ERROR_BAD_KIND = "bad_kind"
ERROR_BAD_RANGE = "bad_range"
ERROR_BAD_PURPOSE = "bad_purpose"
ERROR_UNKNOWN_FEED = "unknown_feed"
ERROR_BAD_FEEDS = "bad_feeds"


class IntegrationAccess:
    def __init__(self, store, clock=None, announce=None, limiter=None):
        self.store = store
        self.clock = clock or time.time
        self.announce = announce if announce is not None else supervisor.announce_discovery
        self.limiter = limiter or RateLimiter(
            limit=FAILED_ATTEMPT_LIMIT, window=FAILED_ATTEMPT_WINDOW_SECONDS, clock=self.clock
        )
        self._lock = threading.Lock()
        self.token = integration.ensure_token(store)
        self.last_request = integration.last_request(store)
        self.integration_version, self.integration_installed = integration.seen_integration(store)
        self.unversioned = integration.integration_unversioned(store)
        self._warmed = set()
        self._port_state = (0, False)

    def now(self):
        return int(self.clock())

    def accepts(self, header):
        scheme, _, presented = str(header or "").strip().partition(" ")
        candidate = presented.strip() if scheme.lower() == BEARER else ""
        with self._lock:
            expected = self.token
        return compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))

    def note_request(self):
        now = self.now()
        self.last_request = now
        integration.note_request(self.store, now)

    def note_versions(self, version, installed):
        if version is None:
            with self._lock:
                if self.unversioned:
                    return
                self.unversioned = True
            logger.info("the Home Assistant integration sends no version, it predates the version check")
            integration.note_unversioned(self.store)
            return
        version = versions.clean_version(version)
        installed = versions.clean_version(installed)
        if not version:
            return
        with self._lock:
            known = (version, installed) == (self.integration_version, self.integration_installed)
            if known and not self.unversioned:
                return
            previous = "" if self.unversioned else self.integration_version
            self.unversioned = False
            self.integration_version, self.integration_installed = version, installed
        logger.info(
            "the Home Assistant integration reports version %s%s (was %s)",
            version,
            " with %s installed" % installed if installed else "",
            previous or "unknown",
        )
        integration.note_integration(self.store, version, installed)

    def pending_updates(self, app_version):
        if not self.recently_active():
            return []
        return versions.pending_updates(
            app_version, self.integration_version, self.integration_installed, self.unversioned
        )

    def recently_active(self):
        return bool(self.last_request) and 0 <= self.now() - self.last_request <= integration.ACTIVE_WINDOW_SECONDS

    def rotate(self):
        with self._lock:
            self.token = integration.rotate_token(self.store)
            token = self.token
        self._announce(token)
        return token

    def announce_now(self):
        self._announce(self.token)

    def _announce(self, token):
        def run():
            try:
                self.announce(token)
            except Exception:
                logger.warning("the discovery announcement could not be started", exc_info=True)

        if self.announce is supervisor.announce_discovery:
            threading.Thread(target=run, daemon=True).start()
        else:
            run()

    def warm_once(self, child_id, warm):
        if warm is None or child_id in self._warmed:
            return
        self._warmed.add(child_id)
        try:
            warm(child_id)
        except Exception:
            logger.warning("the snapshot warm-up for a child could not be started", exc_info=True)

    def feed_port_open(self):
        now = self.now()
        stamp, value = self._port_state
        if now - stamp < PORT_STATE_TTL_SECONDS:
            return value
        value = bool(supervisor.feed_port_open())
        self._port_state = (now, value)
        return value

    def status(self):
        now = self.now()
        app_version = integration.addon_version()
        return {
            "connected": integration.is_connected(self.last_request, now),
            "last_request": integration.berlin_iso(self.last_request) if self.last_request else None,
            "token": self.token,
            "port": INTEGRATION_PORT,
            "app_version": app_version,
            "integration_version": "" if self.unversioned else self.integration_version,
            "integration_installed": "" if self.unversioned else self.integration_installed,
            "updates": self.pending_updates(app_version),
        }


def _client_key(request):
    client = request.client
    return client.host if client and client.host else "unknown"


def _refusal(status, error, key):
    body = {"error": error}
    body.update(messages.payload(key))
    return JSONResponse(status_code=status, content=body)


def ingress_only_from_env():
    setting = os.environ.get(INGRESS_ONLY_ENV, "").strip()
    if setting in ("0", "1"):
        return setting == "1"
    return bool(os.environ.get(SUPERVISOR_TOKEN_ENV))


def register_ingress_guard(app, active):
    if not active:
        return

    @app.middleware("http")
    async def ingress_only(request: Request, call_next):
        if request.scope.get("path") not in ROUTES and _client_key(request) != INGRESS_PROXY_ADDRESS:
            return _refusal(403, ERROR_FORBIDDEN, INGRESS_REQUIRED_KEY)
        return await call_next(request)


def _parse_range(start, end, today):
    default_start, default_end = integration.default_event_range(today)
    first = holidays.parse_day(start) if start else default_start
    last = holidays.parse_day(end) if end else default_end
    if first is None or last is None or last < first:
        return None
    if (last - first).days > integration.MAX_EVENT_RANGE_DAYS:
        return None
    return first, last


def register_integration_routes(app, service, store, holiday_calendar, access, warm=None, registry=None):
    def _known_school(school_id):
        entry = store.connection(school_id) if school_id else None
        return entry is not None and bool(entry.get("setup_complete"))

    def denied(request):
        if request.headers.get(INGRESS_HEADER):
            return _refusal(403, ERROR_FORBIDDEN, INGRESS_REFUSED_KEY)
        source = _client_key(request)
        if access.limiter.blocked(source):
            return _refusal(429, ERROR_RATE_LIMITED, TOO_MANY_ATTEMPTS_KEY)
        if not access.accepts(request.headers.get("authorization")):
            access.limiter.allow(source)
            return _refusal(401, ERROR_UNAUTHORIZED, UNAUTHORIZED_KEY)
        access.note_request()
        access.note_versions(request.headers.get(VERSION_HEADER), request.headers.get(INSTALLED_HEADER))
        return None

    @app.get(ROUTE_INFO)
    def info(request: Request):
        refusal = denied(request)
        if refusal is not None:
            return refusal
        if registry is None:
            return integration.build_info(service, store, access.now(), access.feed_port_open())
        feeds = registry.online_feeds()
        unreported = [feed["webhook_id"] for feed in feeds if not feed["reported"]]
        if unreported:
            registry.mark_offered(unreported)
        return integration.build_info(
            service, store, access.now(), access.feed_port_open(),
            online_feeds=feeds, outside_access=registry.outside_access,
        )

    @app.get(ROUTE_STATE)
    def state(request: Request, child: str = ""):
        refusal = denied(request)
        if refusal is not None:
            return refusal
        if not known_child(store.load_config(), child):
            return _refusal(404, ERROR_UNKNOWN_CHILD, UNKNOWN_CHILD_KEY)
        if not integration.has_snapshot(store, child):
            access.warm_once(child, warm)
        return integration.build_state(store, holiday_calendar, child, access.now())

    @app.get(ROUTE_EVENTS)
    def events(
        request: Request,
        child: str = "",
        kind: str = "",
        start: str = "",
        end: str = "",
        school: str = "",
        purpose: str = integration.PURPOSE_CALENDAR,
    ):
        refusal = denied(request)
        if refusal is not None:
            return refusal
        if kind not in integration.EVENT_COMPONENTS:
            return _refusal(400, ERROR_BAD_KIND, BAD_KIND_KEY)
        if purpose not in integration.PURPOSES:
            return _refusal(400, ERROR_BAD_PURPOSE, BAD_PURPOSE_KEY)
        if kind == integration.KIND_HOLIDAYS:
            child = ""
            if not _known_school(school):
                return _refusal(404, ERROR_UNKNOWN_SCHOOL, UNKNOWN_SCHOOL_KEY)
        elif not known_child(store.load_config(), child):
            return _refusal(404, ERROR_UNKNOWN_CHILD, UNKNOWN_CHILD_KEY)
        now = access.now()
        window = _parse_range(start, end, holidays.berlin_today(integration.utc_moment(now)))
        if window is None:
            return _refusal(400, ERROR_BAD_RANGE, BAD_RANGE_KEY)
        if child and not integration.has_snapshot(store, child):
            access.warm_once(child, warm)
        return integration.build_events(
            store, holiday_calendar, child, kind, window[0], window[1], now, school_id=school, purpose=purpose
        )

    @app.get(ROUTE_SCHOOL)
    def school(request: Request, id: str = ""):
        refusal = denied(request)
        if refusal is not None:
            return refusal
        if not _known_school(id):
            return _refusal(404, ERROR_UNKNOWN_SCHOOL, UNKNOWN_SCHOOL_KEY)
        return integration.build_school(store, holiday_calendar, access.now(), id)

    @app.get(ROUTE_CHANGES)
    def changes(request: Request):
        refusal = denied(request)
        if refusal is not None:
            return refusal
        return integration.build_changes(store)

    @app.get(ROUTE_FEED)
    def online_feed(request: Request, id: str = "", webhook: str = ""):
        refusal = denied(request)
        if refusal is not None:
            return refusal
        subscription = registry.find_online(id, webhook) if registry is not None else None
        if subscription is None:
            logger.info("Home Assistant asked for a calendar feed that is not online")
            return _refusal(404, ERROR_UNKNOWN_FEED, UNKNOWN_FEED_KEY)
        registry.note_fetch(subscription.get("id", ""))
        logger.info(
            "calendar feed access through Home Assistant token=%s",
            token_log_prefix(subscription.get("token", "")),
        )
        return {"calendar": feed.build_feed(subscription, store, holiday_calendar)}

    @app.post(ROUTE_FEEDS)
    def online_feed_reports(request: Request, body: Any = Body(default=None)):
        refusal = denied(request)
        if refusal is not None:
            return refusal
        reports = body.get("feeds") if isinstance(body, dict) else None
        if registry is None or not isinstance(reports, list) or len(reports) > MAX_FEED_REPORTS:
            return _refusal(400, ERROR_BAD_FEEDS, BAD_FEEDS_KEY)
        outside = registry.record_outside_access(body.get("outside"))
        if outside is not None:
            logger.info(
                "Home Assistant reports access from outside: cloud %s, external %s",
                "yes" if outside["cloud"] else "no",
                "yes" if outside["external"] else "no",
            )
        states = registry.record_online_reports(reports)
        ready = states.count(ONLINE_READY)
        logger.info(
            "Home Assistant reported online calendar addresses: %s ready, %s without access from outside",
            ready,
            len(states) - ready,
        )
        return {"stored": len(states)}


def register_status_routes(app, access):
    def denied(request):
        if not request.headers.get(INGRESS_HEADER):
            return _refusal(403, ERROR_FORBIDDEN, INGRESS_REQUIRED_KEY)
        return None

    @app.get(STATUS_PATH)
    def integration_status(request: Request):
        refusal = denied(request)
        if refusal is not None:
            return refusal
        return access.status()

    @app.post(STATUS_PATH + "/rotate")
    def rotate_integration_token(request: Request):
        refusal = denied(request)
        if refusal is not None:
            return refusal
        token = access.rotate()
        return messages.result(True, TOKEN_ROTATED_KEY, token=token)
