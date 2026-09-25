from fastapi.responses import PlainTextResponse
from requests import RequestException

from . import messages
from .iserv.errors import DataError, LoginError, TwoFactorError
from .service import NotConfiguredError

NOT_CONFIGURED = "not_configured"
AUTH_FAILED = "auth_failed"
NETWORK = "network"
UPSTREAM_ERROR_CODES = (NOT_CONFIGURED, AUTH_FAILED, NETWORK)
UPSTREAM_ERROR_MESSAGE_KEYS = {
    NOT_CONFIGURED: "api.notConfigured",
    AUTH_FAILED: "api.authFailed",
    NETWORK: "api.network",
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


def _upstream_code(error):
    if isinstance(error, NotConfiguredError):
        return NOT_CONFIGURED
    if isinstance(error, (LoginError, TwoFactorError)):
        return AUTH_FAILED
    return NETWORK


def read_endpoint(call):
    try:
        return call()
    except (NotConfiguredError, LoginError, TwoFactorError, DataError, RequestException) as error:
        return upstream_error(_upstream_code(error), error)


def write_endpoint(call, fallback=None):
    try:
        return call()
    except (NotConfiguredError, LoginError, TwoFactorError, DataError, RequestException) as error:
        return upstream_write_error(_upstream_code(error), error)
    except Exception:
        if fallback is None:
            raise
        return {"ok": False, "error": fallback}


BINARY_UPSTREAM_RESPONSES = {
    NOT_CONFIGURED: ("not configured", 503),
    AUTH_FAILED: ("auth failed", 503),
    NETWORK: ("upstream unavailable", 502),
}


def binary_upstream_response(error):
    body, status = BINARY_UPSTREAM_RESPONSES[_upstream_code(error)]
    return PlainTextResponse(body, status_code=status)
