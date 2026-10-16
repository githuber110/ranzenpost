import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from . import messages

logger = logging.getLogger(__name__)

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
APP_HEADER = "x-ranzenpost-app"
APP_HEADER_VALUE = "1"
SAFE_SITES = frozenset({"same-origin", "none"})
API_ROOT = "/api/"
CROSS_SITE_KEY = "api.crossSite"
FORBIDDEN = "forbidden"


def from_another_site(method, path, headers, exempt):
    if method.upper() not in WRITE_METHODS or not path.startswith(API_ROOT) or path in exempt:
        return False
    if headers.get(APP_HEADER) == APP_HEADER_VALUE:
        return False
    site = str(headers.get("sec-fetch-site") or "").strip().lower()
    if site:
        return site not in SAFE_SITES
    return bool(headers.get("origin"))


def register_request_guard(app, exempt):
    exempt = frozenset(exempt)

    @app.middleware("http")
    async def same_site_writes(request: Request, call_next):
        path = request.scope.get("path") or ""
        if from_another_site(request.method, path, request.headers, exempt):
            logger.warning("a %s from another site to %s was refused", request.method, path)
            body = {"ok": False, "error": FORBIDDEN}
            body.update(messages.payload(CROSS_SITE_KEY))
            return JSONResponse(status_code=403, content=body)
        return await call_next(request)
