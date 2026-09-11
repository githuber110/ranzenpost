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

CACHE_CONTROL = "private, max-age=600, must-revalidate"
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


class RateLimiter:
    def __init__(self, limit=RATE_LIMIT_REQUESTS, window=RATE_LIMIT_WINDOW_SECONDS, clock=None):
        self.limit = limit
        self.window = window
        self.clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._hits = {}

    def allow(self, key):
        now = self.clock()
        with self._lock:
            recent = [stamp for stamp in self._hits.get(key, ()) if now - stamp < self.window]
            if len(recent) >= self.limit:
                self._hits[key] = recent
                return False
            recent.append(now)
            self._hits[key] = recent
            return True


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


def _note_fetch(registry, subscription):
    recorder = getattr(registry, "note_fetch", None)
    if not callable(recorder):
        return
    try:
        recorder(subscription.get("id", ""))
    except Exception:
        logger.warning("the fetch time of a calendar feed could not be stored", exc_info=True)


def create_calendar_app(store, registry, holiday_calendar=None, builder=None, limiter=None):
    app = FastAPI(title="Ranzenpost Calendar", docs_url=None, redoc_url=None, openapi_url=None)
    holiday_source = holiday_calendar or holidays.HolidayCalendar(store)
    build = builder or feed.build_feed
    guard = limiter or RateLimiter()

    @app.exception_handler(StarletteHTTPException)
    async def not_found(request: Request, exception: StarletteHTTPException):
        return PlainTextResponse(NOT_FOUND_BODY, status_code=404, headers=dict(SECURITY_HEADERS))

    @app.get("/calendar/{token}.ics")
    def calendar_feed(token: str, request: Request):
        if not guard.allow(_client_key(request)):
            return PlainTextResponse(
                RATE_LIMIT_BODY, status_code=429, headers=dict(SECURITY_HEADERS)
            )
        subscription = registry.find_by_token(token)
        if subscription is None:
            logger.info("calendar feed rejected token prefix %s", token_log_prefix(token))
            return PlainTextResponse(
                NOT_FOUND_BODY, status_code=404, headers=dict(SECURITY_HEADERS)
            )
        if _wants_hand_off(request):
            headers = dict(SECURITY_HEADERS)
            headers["Location"] = str(request.url.replace(scheme=WEBCAL_SCHEME, query=""))
            headers["Cache-Control"] = "no-store"
            return Response(status_code=302, headers=headers)
        _note_fetch(registry, subscription)
        body = build(subscription, store, holiday_source)
        tag = _etag(body)
        headers = dict(SECURITY_HEADERS)
        headers["Cache-Control"] = CACHE_CONTROL
        headers["ETag"] = tag
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type=MEDIA_TYPE, headers=headers)

    return app
