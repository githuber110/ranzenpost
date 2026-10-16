import logging

from fastapi import Body

from .failure import failure_cause
from .upstream import read_endpoint, write_endpoint

logger = logging.getLogger(__name__)


def _logged(label, call):
    def run():
        try:
            return call()
        except Exception as error:
            logger.warning("conference route %s failed: %s", label, failure_cause(error))
            raise

    return run


def register_routes(app, service):
    @app.get("/api/conferences")
    def conferences(tab: str = "current"):
        return read_endpoint(lambda: service.conferences("archive" if tab == "archive" else "current"))

    @app.get("/api/conferences/page")
    def conference_page(page: str, connection: str = ""):
        return read_endpoint(lambda: service.conference_page(connection, page))

    def _submit(body):
        return service.submit_conference_form(
            body.get("connection_id", ""),
            body.get("page", ""),
            body.get("form"),
            body.get("check", ""),
            body.get("submit", 0),
            body.get("values") if isinstance(body.get("values"), dict) else {},
            body.get("request_id", ""),
            body.get("confirmed") is True,
        )

    @app.post("/api/conferences/submit")
    def conference_submit(body: dict = Body(...)):
        return write_endpoint(_logged("submit", lambda: _submit(body)), fallback="submit_failed")
