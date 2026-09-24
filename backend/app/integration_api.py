import logging
import threading
import time
from hmac import compare_digest

from fastapi import Request
from fastapi.responses import JSONResponse

from . import holidays, integration, messages, supervisor
from .calendar_server import RateLimiter

logger = logging.getLogger(__name__)

PREFIX = "/api/integration"
STATUS_PATH = "/api/integration-status"
ROUTE_INFO = PREFIX + "/info"
ROUTE_STATE = PREFIX + "/state"
ROUTE_EVENTS = PREFIX + "/events"
ROUTE_SCHOOL = PREFIX + "/school"
ROUTE_CHANGES = PREFIX + "/changes"
ROUTES = (ROUTE_INFO, ROUTE_STATE, ROUTE_EVENTS, ROUTE_SCHOOL, ROUTE_CHANGES)
INTEGRATION_PORT = 8099
BEARER = "bearer"
INGRESS_HEADER = "x-ingress-path"
FAILED_ATTEMPT_LIMIT = 10
FAILED_ATTEMPT_WINDOW_SECONDS = 60
PORT_STATE_TTL_SECONDS = 60

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

ERROR_UNAUTHORIZED = "unauthorized"
ERROR_FORBIDDEN = "forbidden"
ERROR_RATE_LIMITED = "rate_limited"
ERROR_UNKNOWN_CHILD = "unknown_child"
ERROR_UNKNOWN_SCHOOL = "unknown_school"
ERROR_BAD_KIND = "bad_kind"
ERROR_BAD_RANGE = "bad_range"
ERROR_BAD_PURPOSE = "bad_purpose"


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
        return {
            "connected": integration.is_connected(self.last_request, now),
            "last_request": integration.berlin_iso(self.last_request) if self.last_request else None,
            "token": self.token,
            "port": INTEGRATION_PORT,
        }


def _client_key(request):
    client = request.client
    return client.host if client and client.host else "unknown"


def _refusal(status, error, key):
    body = {"error": error}
    body.update(messages.payload(key))
    return JSONResponse(status_code=status, content=body)


def _parse_range(start, end, today):
    default_start, default_end = integration.default_event_range(today)
    first = holidays.parse_day(start) if start else default_start
    last = holidays.parse_day(end) if end else default_end
    if first is None or last is None or last < first:
        return None
    if (last - first).days > integration.MAX_EVENT_RANGE_DAYS:
        return None
    return first, last


def register_integration_routes(app, service, store, holiday_calendar, access, warm=None):
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
        return None

    @app.get(ROUTE_INFO)
    def info(request: Request):
        refusal = denied(request)
        if refusal is not None:
            return refusal
        return integration.build_info(service, store, access.now(), access.feed_port_open())

    @app.get(ROUTE_STATE)
    def state(request: Request, child: str = ""):
        refusal = denied(request)
        if refusal is not None:
            return refusal
        if not integration.known_child(store.load_config(), child):
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
        elif not integration.known_child(store.load_config(), child):
            return _refusal(404, ERROR_UNKNOWN_CHILD, UNKNOWN_CHILD_KEY)
        now = access.now()
        window = _parse_range(start, end, holidays.berlin_today(integration._moment(now)))
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
