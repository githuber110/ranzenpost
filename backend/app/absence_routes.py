import json
import logging
import unicodedata
from urllib.parse import quote

import requests
from fastapi import Body, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, PlainTextResponse

from . import messages
from .absence_service import SickNoteNotFoundError
from .iserv.errors import DataError, LoginError, TwoFactorError
from .iserv.sick_note_pdf import UnsupportedTextError
from .failure import failure_cause
from .service import NotConfiguredError, SchoolRequiredError
from .upstream import binary_upstream_response, file_answer, read_endpoint, upstream_file, write_endpoint
from .uploads import UploadLimitError, declared_too_large, read_uploads

logger = logging.getLogger(__name__)

OLDER_MESSAGE_PREFIX = "api.absence.older."

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 40 * 1024 * 1024


def _ascii_fallback_filename(filename):
    folded = unicodedata.normalize("NFKD", filename)
    kept = []
    for char in folded:
        if unicodedata.combining(char):
            continue
        if 32 <= ord(char) < 127 and char not in '"\\':
            kept.append(char)
    return " ".join("".join(kept).split())


def _inline_disposition(filename):
    filename = unicodedata.normalize("NFC", str(filename or ""))
    filename = "".join(char for char in filename if unicodedata.category(char)[0] != "C")
    encoded = quote(filename, safe="")
    return f'inline; filename="{_ascii_fallback_filename(filename)}"; filename*=UTF-8\'\'{encoded}'


def register_routes(app, service):
    @app.get("/api/absences")
    def absences(connection: str = ""):
        return read_endpoint(lambda: service.absences_overview(connection or None))

    @app.get("/api/absences/older-form")
    def older_absence_form(connection: str = ""):
        return read_endpoint(lambda: service.older_absence_form(connection or None))

    @app.get("/api/absences/older-detail")
    def older_absence_detail(id: str = "", connection: str = ""):
        return read_endpoint(lambda: service.older_absence_detail(connection or None, id))

    @app.get("/api/absences/older-attachment")
    def older_absence_attachment(id: str = "", key: str = "", connection: str = ""):
        try:
            upstream = service.older_absence_attachment(connection or None, id, key)
        except (SchoolRequiredError, NotConfiguredError, LoginError, TwoFactorError, DataError, requests.RequestException) as error:
            logger.warning("older absence attachment could not be fetched: %s", failure_cause(error))
            return binary_upstream_response(error)
        return upstream_file(upstream)

    @app.post("/api/absences/older-attachment/delete")
    def delete_older_attachment(body: dict = Body(...)):
        return write_endpoint(lambda: service.delete_older_attachment(body.get("connection_id") or None, body.get("id"), body.get("key")))

    @app.get("/api/absences/older-export")
    def older_absence_export(connection: str = ""):
        try:
            content, filename = service.older_absence_export(connection or None)
        except (SchoolRequiredError, NotConfiguredError, LoginError, TwoFactorError, DataError, requests.RequestException) as error:
            logger.warning("older absence export could not be fetched: %s", failure_cause(error))
            key = getattr(error, "message_key", "") or ""
            if key.startswith(OLDER_MESSAGE_PREFIX):
                return JSONResponse(messages.payload(key), status_code=422)
            return binary_upstream_response(error)
        return file_answer(content, "text/csv; charset=utf-8", 'attachment; filename="%s"' % filename)

    @app.post("/api/absences/older-attachment")
    async def attach_older_absence(request: Request):
        form = await request.form()
        body = json.loads(form.get("data") or "{}")
        try:
            uploads = await read_uploads(form, MAX_ATTACHMENT_BYTES, MAX_ATTACHMENT_BYTES, max_count=1)
        except UploadLimitError:
            logger.info("older absence attachment refused: too large or too many")
            return messages.result(False, "api.absence.error.attachmentTooLarge")
        if len(uploads) != 1:
            return messages.result(False, "api.absence.older.attachUnsupported")
        upload = uploads[0]
        connection_id = body.get("connection_id") or None
        return await run_in_threadpool(
            write_endpoint, lambda: service.attach_older_absence(connection_id, body.get("id"), upload)
        )

    @app.post("/api/absences")
    async def report_absence(request: Request):
        content_type = request.headers.get("content-type", "")
        attachments = None
        if content_type.startswith("multipart/form-data"):
            if declared_too_large(request, MAX_TOTAL_ATTACHMENT_BYTES):
                logger.info("absence report refused: attachment too large")
                return messages.result(False, "api.absence.error.attachmentTooLarge")
            form = await request.form()
            try:
                body = json.loads(form.get("data") or "{}")
                attachments = await read_uploads(form, MAX_ATTACHMENT_BYTES, MAX_TOTAL_ATTACHMENT_BYTES)
            except UploadLimitError:
                logger.info("absence report refused: attachment too large")
                return messages.result(False, "api.absence.error.attachmentTooLarge")
            finally:
                await form.close()
        else:
            body = await request.json()
        connection_id = body.get("connection_id") or None
        return await run_in_threadpool(
            write_endpoint, lambda: service.report_absence(connection_id, body, attachments=attachments)
        )

    @app.post("/api/absences/delete")
    def delete_absence(body: dict = Body(...)):
        return write_endpoint(lambda: service.delete_absence(body.get("connection_id") or None, body))

    @app.get("/api/absences/attachment/{filename}")
    def absence_attachment(filename: str, connection: str = ""):
        try:
            upstream = service.absence_attachment(connection, filename)
        except (NotConfiguredError, LoginError, TwoFactorError, requests.RequestException) as error:
            logger.warning("absence attachment could not be fetched: %s", failure_cause(error))
            return binary_upstream_response(error)
        except Exception as error:
            logger.warning("absence attachment was refused before the request: %s", failure_cause(error))
            return PlainTextResponse("invalid attachment", status_code=400)
        return upstream_file(upstream)

    @app.get("/api/absences/sick-note-pdf")
    def sick_note_pdf(id: str = "", connection: str = ""):
        try:
            pdf_bytes, filename = service.sick_note_pdf(connection or None, id)
        except SickNoteNotFoundError:
            logger.info("sick note pdf not found")
            return PlainTextResponse("not found", status_code=404)
        except UnsupportedTextError:
            logger.warning("sick note pdf refused: unsupported text")
            return PlainTextResponse("unsupported text", status_code=422)
        except SchoolRequiredError as error:
            logger.info("sick note pdf refused: no school named")
            return binary_upstream_response(error)
        except (NotConfiguredError, LoginError, TwoFactorError, requests.RequestException) as error:
            logger.warning("sick note pdf could not be fetched: %s", failure_cause(error))
            return binary_upstream_response(error)
        return file_answer(pdf_bytes, "application/pdf", _inline_disposition(filename))
