import json
import logging

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from . import messages
from .task_service import (
    ACT_FILE_TOO_LARGE_KEY,
    ACT_INVALID_KEY,
    ACT_TOO_LARGE_KEY,
    ACT_TOO_MANY_KEY,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
)
from .upstream import file_response, read_endpoint, write_endpoint
from .uploads import LIMIT_COUNT, LIMIT_FILE, UploadLimitError, declared_too_large, read_uploads

logger = logging.getLogger(__name__)
MEGABYTE = 1024 * 1024


def limit_result(limit):
    if limit == LIMIT_COUNT:
        return messages.result(False, ACT_TOO_MANY_KEY, {"max": MAX_FILES})
    if limit == LIMIT_FILE:
        return messages.result(False, ACT_FILE_TOO_LARGE_KEY, {"max": MAX_FILE_BYTES // MEGABYTE})
    return messages.result(False, ACT_TOO_LARGE_KEY, {"max": MAX_TOTAL_BYTES // MEGABYTE})


def _invalid():
    return JSONResponse(status_code=400, content=messages.result(False, ACT_INVALID_KEY))


def _target(body):
    index = body.get("target")
    if not isinstance(index, int) or isinstance(index, bool):
        return None
    label = body.get("target_label")
    value = body.get("target_value")
    return {"index": index, "label": label if isinstance(label, str) else "", "value": value if isinstance(value, str) else ""}


def _act(service, body, files):
    return service.task_act(
        body.get("connection_id", ""),
        str(body.get("task_id") or ""),
        body.get("action"),
        body.get("form"),
        _target(body),
        body.get("text") if isinstance(body.get("text"), str) else None,
        files,
        body.get("confirmed") is True,
    )


def register_routes(app, service):
    @app.get("/api/tasks/detail")
    def task_detail(connection: str = "", task: str = ""):
        return read_endpoint(lambda: service.task_detail(connection, task))

    @app.get("/api/tasks/file")
    def task_file(connection: str = "", task: str = "", kind: str = "", index: int = -1):
        return file_response(lambda: service.task_file(connection, task, kind, index), "task file")

    @app.post("/api/tasks/act")
    async def task_act(request: Request):
        files = []
        if request.headers.get("content-type", "").startswith("multipart/form-data"):
            if declared_too_large(request, MAX_TOTAL_BYTES):
                logger.info("task upload refused: the request is larger than the limit")
                return limit_result(None)
            form = await request.form(max_files=MAX_FILES + 1, max_fields=20)
            try:
                raw = form.get("data")
                if not isinstance(raw, str):
                    return _invalid()
                body = json.loads(raw or "{}")
                files = await read_uploads(form, MAX_FILE_BYTES, MAX_TOTAL_BYTES, MAX_FILES)
            except UploadLimitError as error:
                logger.info("task upload refused: %s limit", error.limit)
                return limit_result(error.limit)
            except ValueError:
                return _invalid()
            finally:
                await form.close()
        else:
            try:
                body = await request.json()
            except ValueError:
                return _invalid()
        if not isinstance(body, dict):
            return _invalid()
        return await run_in_threadpool(write_endpoint, lambda: _act(service, body, files), "act_failed")
