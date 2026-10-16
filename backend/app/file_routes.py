import json
import logging

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from . import messages
from .file_service import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    MEGABYTE,
    UPLOAD_FILE_TOO_LARGE_KEY,
    UPLOAD_TOO_LARGE_KEY,
    UPLOAD_TOO_MANY_KEY,
)
from .uploads import LIMIT_COUNT, LIMIT_FILE, UploadLimitError, declared_too_large, read_uploads
from .upstream import file_response, read_endpoint, write_endpoint

logger = logging.getLogger(__name__)
INVALID_KEY = "api.files.invalid"


def upload_limit(limit):
    if limit == LIMIT_COUNT:
        return messages.result(False, UPLOAD_TOO_MANY_KEY, {"max": MAX_FILES})
    if limit == LIMIT_FILE:
        return messages.result(False, UPLOAD_FILE_TOO_LARGE_KEY, {"max": MAX_FILE_BYTES // MEGABYTE})
    return messages.result(False, UPLOAD_TOO_LARGE_KEY, {"max": MAX_TOTAL_BYTES // MEGABYTE})


def invalid_request():
    return JSONResponse(status_code=400, content=messages.result(False, INVALID_KEY))


async def multipart_body(request, max_file, max_total, max_count):
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        body = await request.json()
        return (body if isinstance(body, dict) else None), []
    if declared_too_large(request, max_total):
        raise UploadLimitError(None)
    form = await request.form(max_files=max_count + 1, max_fields=40)
    try:
        raw = form.get("data")
        if not isinstance(raw, str):
            return None, []
        body = json.loads(raw or "{}")
        files = await read_uploads(form, max_file, max_total, max_count)
    finally:
        await form.close()
    return (body if isinstance(body, dict) else None), files


def register_routes(app, service):
    @app.get("/api/account-modules")
    def account_modules():
        return read_endpoint(service.account_modules)

    @app.get("/api/files")
    def file_listing(connection: str = "", path: str = ""):
        return read_endpoint(lambda: service.file_listing(connection, path))

    @app.get("/api/files/search")
    def file_search(connection: str = "", path: str = "", q: str = ""):
        return read_endpoint(lambda: service.file_search(connection, path, q))

    @app.get("/api/files/file")
    def school_file(connection: str = "", path: str = ""):
        return file_response(lambda: service.school_file(connection, path), "school file")

    @app.post("/api/files/upload")
    async def file_upload(request: Request):
        try:
            body, files = await multipart_body(request, MAX_FILE_BYTES, MAX_TOTAL_BYTES, MAX_FILES)
        except UploadLimitError as error:
            logger.info("file upload refused: %s limit", error.limit or "request")
            return upload_limit(error.limit)
        except ValueError:
            return invalid_request()
        if body is None:
            return invalid_request()
        return await run_in_threadpool(
            write_endpoint,
            lambda: service.file_upload(body.get("connection_id", ""), str(body.get("path") or ""), files, body.get("confirmed") is True),
            "upload_failed",
        )
