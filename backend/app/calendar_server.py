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
MEDIA_TYPE = "text/calendar; charset=utf-8"
NOT_FOUND_BODY = "not found"
RATE_LIMIT_BODY = "too many requests"
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 300
ETAG_LENGTH = 32
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
        body = build(subscription, store, holiday_source)
        tag = _etag(body)
        headers = dict(SECURITY_HEADERS)
        headers["Cache-Control"] = CACHE_CONTROL
        headers["ETag"] = tag
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type=MEDIA_TYPE, headers=headers)

    return app
