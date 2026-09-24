import hashlib
import logging
import threading
import time

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import feed, holidays
from .subscriptions import token_log_prefix

logger = logging.getLogger(__name__)

USER_AGENT_LOG_LENGTH = 120
ACCEPT_LOG_LENGTH = 120
RATE_LOG_INTERVAL_SECONDS = 60.0

CACHE_CONTROL = "private, no-cache"
CALENDAR_MEDIA_TYPE = "text/calendar"
MEDIA_TYPE = f"{CALENDAR_MEDIA_TYPE}; charset=utf-8"
NOT_FOUND_BODY = "not found"
RATE_LIMIT_BODY = "too many requests"
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 300
ETAG_LENGTH = 32
SUBSCRIBE_QUERY = "subscribe"
WEBCAL_SCHEME = "webcal"
BROWSER_MEDIA_TYPE = "text/html"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class RateLimitLog:
    def __init__(self, clock=None, interval=RATE_LOG_INTERVAL_SECONDS):
        self.clock = clock or time.monotonic
        self.interval = interval
        self._lock = threading.Lock()
        self._window_start = None
        self._suppressed = 0

    def admit(self):
        now = self.clock()
        with self._lock:
            if self._window_start is not None and now - self._window_start < self.interval:
                self._suppressed += 1
                return False, 0
            suppressed = self._suppressed
            self._suppressed = 0
            self._window_start = now
            return True, suppressed


class RateLimiter:
    def __init__(self, limit=RATE_LIMIT_REQUESTS, window=RATE_LIMIT_WINDOW_SECONDS, clock=None):
        self.limit = limit
        self.window = window
        self.clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._hits = {}

    def _recent(self, key, now):
        recent = [stamp for stamp in self._hits.get(key, ()) if now - stamp < self.window]
        self._hits[key] = recent
        return recent

    def allow(self, key):
        now = self.clock()
        with self._lock:
            recent = self._recent(key, now)
            if len(recent) >= self.limit:
                return False
            recent.append(now)
            return True

    def blocked(self, key):
        with self._lock:
            return len(self._recent(key, self.clock())) >= self.limit


def _etag(body):
    return '"' + hashlib.sha256(body.encode("utf-8")).hexdigest()[:ETAG_LENGTH] + '"'


def _client_key(request):
    client = request.client
    return client.host if client and client.host else "unknown"


def _accept_weight(accept, media_type):
    best = (0.0, -1)
    for offer in accept.split(","):
        parts = [part.strip() for part in offer.split(";")]
        offered = parts[0].lower()
        quality = 1.0
        for parameter in parts[1:]:
            name, _, value = parameter.partition("=")
            if name.strip().lower() == "q":
                try:
                    quality = float(value.strip())
                except ValueError:
                    quality = 1.0
        if offered == media_type:
            rank = 2
        elif offered == media_type.split("/")[0] + "/*":
            rank = 1
        elif offered == "*/*":
            rank = 0
        else:
            continue
        best = max(best, (quality, rank))
    return best


def _wants_hand_off(request):
    if not request.query_params.get(SUBSCRIBE_QUERY):
        return False
    accept = request.headers.get("accept", "")
    return _accept_weight(accept, BROWSER_MEDIA_TYPE) > _accept_weight(accept, CALENDAR_MEDIA_TYPE)


def _log_access(request, token, status_code, kind):
    accept = request.headers.get("accept", "")[:ACCEPT_LOG_LENGTH]
    user_agent = request.headers.get("user-agent", "")[:USER_AGENT_LOG_LENGTH]
    logger.info(
        "calendar feed access status=%s kind=%s accept=%s user_agent=%s token=%s",
        status_code,
        kind,
        accept,
        user_agent,
        token_log_prefix(token),
    )


def _log_rate_limited(throttle, request, token):
    shown, suppressed = throttle.admit()
    if not shown:
        return
    if suppressed:
        logger.info("calendar feed rate limit refused %s more request(s) in the last minute", suppressed)
    _log_access(request, token, 429, "rate_limited")


def _note_fetch(registry, subscription):
    recorder = getattr(registry, "note_fetch", None)
    if not callable(recorder):
        return
    try:
        recorder(subscription.get("id", ""))
    except Exception:
        logger.warning("the fetch time of a calendar feed could not be stored", exc_info=True)


def create_calendar_app(store, registry, holiday_calendar=None, builder=None, limiter=None, rate_log=None):
    app = FastAPI(title="Ranzenpost Calendar", docs_url=None, redoc_url=None, openapi_url=None)
    holiday_source = holiday_calendar or holidays.HolidayCalendar(store)
    build = builder or feed.build_feed
    guard = limiter or RateLimiter()
    throttle = rate_log or RateLimitLog()

    @app.exception_handler(StarletteHTTPException)
    async def not_found(request: Request, exception: StarletteHTTPException):
        return PlainTextResponse(NOT_FOUND_BODY, status_code=404, headers=dict(SECURITY_HEADERS))

    @app.get("/calendar/{token}.ics")
    def calendar_feed(token: str, request: Request):
        if not guard.allow(_client_key(request)):
            _log_rate_limited(throttle, request, token)
            return PlainTextResponse(
                RATE_LIMIT_BODY, status_code=429, headers=dict(SECURITY_HEADERS)
            )
        subscription = registry.find_by_token(token)
        if subscription is None:
            _log_access(request, token, 404, "rejected")
            return PlainTextResponse(
                NOT_FOUND_BODY, status_code=404, headers=dict(SECURITY_HEADERS)
            )
        if _wants_hand_off(request):
            headers = dict(SECURITY_HEADERS)
            headers["Location"] = str(request.url.replace(scheme=WEBCAL_SCHEME, query=""))
            headers["Cache-Control"] = "no-store"
            _log_access(request, token, 302, "subscribe")
            return Response(status_code=302, headers=headers)
        _note_fetch(registry, subscription)
        body = build(subscription, store, holiday_source)
        tag = _etag(body)
        headers = dict(SECURITY_HEADERS)
        headers["Cache-Control"] = CACHE_CONTROL
        headers["ETag"] = tag
        if request.headers.get("if-none-match") == tag:
            _log_access(request, token, 304, "feed")
            return Response(status_code=304, headers=headers)
        _log_access(request, token, 200, "feed")
        return Response(content=body, media_type=MEDIA_TYPE, headers=headers)

    return app
