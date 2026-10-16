import logging

from fastapi.responses import PlainTextResponse, Response
from requests import RequestException

from . import messages
from .iserv.errors import DataError, LoginError, TwoFactorError
from .failure import failure_cause
from .service import SCHOOL_REQUIRED_KEY, NotConfiguredError, SchoolRequiredError

logger = logging.getLogger(__name__)

NOT_CONFIGURED = "not_configured"
AUTH_FAILED = "auth_failed"
NETWORK = "network"
SCHOOL_REQUIRED = "school_required"
UPSTREAM_ERROR_MESSAGE_KEYS = {
    NOT_CONFIGURED: "api.notConfigured",
    AUTH_FAILED: "api.authFailed",
    NETWORK: "api.network",
    SCHOOL_REQUIRED: SCHOOL_REQUIRED_KEY,
}


def upstream_error(code, error=None):
    body = {"error": code}
    body.update(messages.payload(getattr(error, "message_key", "") or UPSTREAM_ERROR_MESSAGE_KEYS[code]))
    detail = getattr(error, "detail", None)
    if isinstance(detail, dict) and detail:
        body["diagnosis"] = detail
    return body


def upstream_write_error(code, error=None):
    body = messages.result(
        False,
        getattr(error, "message_key", "") or UPSTREAM_ERROR_MESSAGE_KEYS[code],
        error=code,
    )
    detail = getattr(error, "detail", None)
    if isinstance(detail, dict) and detail:
        body["diagnosis"] = detail
    return body


def upstream_code(error):
    if isinstance(error, SchoolRequiredError):
        return SCHOOL_REQUIRED
    if isinstance(error, NotConfiguredError):
        return NOT_CONFIGURED
    if isinstance(error, (LoginError, TwoFactorError)):
        return AUTH_FAILED
    return NETWORK


def read_endpoint(call):
    try:
        return call()
    except (NotConfiguredError, LoginError, TwoFactorError, DataError, RequestException) as error:
        return upstream_error(upstream_code(error), error)


def write_endpoint(call, fallback=None):
    try:
        return call()
    except (NotConfiguredError, LoginError, TwoFactorError, DataError, RequestException) as error:
        return upstream_write_error(upstream_code(error), error)
    except Exception:
        if fallback is None:
            raise
        return {"ok": False, "error": fallback}


BINARY_UPSTREAM_RESPONSES = {
    NOT_CONFIGURED: ("not configured", 503),
    AUTH_FAILED: ("auth failed", 503),
    NETWORK: ("upstream unavailable", 502),
    SCHOOL_REQUIRED: ("school required", 400),
}


def binary_upstream_response(error):
    body, status = BINARY_UPSTREAM_RESPONSES[upstream_code(error)]
    return PlainTextResponse(body, status_code=status)


PREVIEW_TYPES = frozenset({
    "application/pdf", "image/avif", "image/bmp", "image/gif", "image/heic", "image/heif", "image/jpeg",
    "image/png", "image/webp",
})
FALLBACK_TYPE = "application/octet-stream"
FILE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "sandbox; default-src 'none'",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def safe_media_type(value):
    base = str(value or "").split(";", 1)[0].strip().lower()
    return base if base in PREVIEW_TYPES else FALLBACK_TYPE


def served_disposition(value, media_type):
    raw = str(value or "").strip()
    if media_type in PREVIEW_TYPES:
        return raw
    _, _, rest = raw.partition(";")
    rest = rest.strip()
    return f"attachment; {rest}" if rest else "attachment"


def file_answer(content, content_type, disposition=None):
    media_type = safe_media_type(content_type)
    headers = dict(FILE_HEADERS)
    shown = served_disposition(disposition, media_type)
    if shown:
        headers["Content-Disposition"] = shown
    return Response(content=content, media_type=media_type, headers=headers)


def upstream_file(upstream):
    headers = getattr(upstream, "headers", None) or {}
    return file_answer(upstream.content, headers.get("content-type"), headers.get("content-disposition"))


def file_response(load, what):
    try:
        upstream = load()
    except (NotConfiguredError, LoginError, TwoFactorError, RequestException) as error:
        logger.warning("%s could not be fetched: %s", what, failure_cause(error))
        return binary_upstream_response(error)
    except Exception as error:
        logger.warning("%s was refused before the request: %s", what, failure_cause(error))
        return PlainTextResponse("invalid file", status_code=400)
    return upstream_file(upstream)
