import logging

from fastapi import Body, Request
from fastapi.concurrency import run_in_threadpool

from . import messages
from .contacts_service import IMPORT_MAX_BYTES, IMPORT_TOO_LARGE_KEY
from .file_routes import invalid_request, multipart_body
from .uploads import UploadLimitError
from .upstream import read_endpoint, write_endpoint

logger = logging.getLogger(__name__)


def register_routes(app, service):
    @app.get("/api/addressbook/search")
    def address_search(connection: str = "", q: str = ""):
        return read_endpoint(lambda: service.address_search(connection, q))

    @app.get("/api/mailinglists")
    def mailing_lists(connection: str = ""):
        return read_endpoint(lambda: service.mailing_lists(connection))

    @app.get("/api/mailinglists/detail")
    def mailing_list_detail(connection: str = "", list_id: str = ""):
        return read_endpoint(lambda: service.mailing_list_detail(connection, list_id))

    @app.post("/api/mailinglists/import")
    async def mailing_list_import(request: Request):
        try:
            body, files = await multipart_body(request, IMPORT_MAX_BYTES, IMPORT_MAX_BYTES, 1)
        except UploadLimitError as error:
            logger.info("mailing list import refused: %s limit", error.limit or "request")
            return messages.result(False, IMPORT_TOO_LARGE_KEY, {"max": IMPORT_MAX_BYTES // 1024})
        except ValueError:
            return invalid_request()
        if body is None:
            return invalid_request()
        values = body.get("values") if isinstance(body.get("values"), dict) else {}
        return await run_in_threadpool(
            write_endpoint,
            lambda: service.mailing_list_import(body.get("connection_id", ""), values, files, body.get("confirmed") is True),
            "import_failed",
        )

    @app.post("/api/mailinglists/delete")
    def mailing_list_delete(body: dict = Body(...)):
        return write_endpoint(
            lambda: service.mailing_list_delete(body.get("connection_id", ""), str(body.get("list_id") or ""), body.get("confirmed") is True),
            fallback="delete_failed",
        )
