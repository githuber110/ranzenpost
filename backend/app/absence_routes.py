import json
import logging
import unicodedata
from urllib.parse import quote

import requests
from fastapi import Body, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse, Response

from . import messages
from .absence_service import SickNoteNotFoundError
from .iserv.errors import LoginError, TwoFactorError
from .iserv.sick_note_pdf import UnsupportedTextError
from .failure import failure_cause
from .service import NotConfiguredError, SchoolRequiredError
from .upstream import binary_upstream_response, read_endpoint, write_endpoint

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 40 * 1024 * 1024


class AttachmentTooLargeError(Exception):
    pass


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

    @app.post("/api/absences")
    async def report_absence(request: Request):
        content_type = request.headers.get("content-type", "")
        attachments = None
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            body = json.loads(form.get("data") or "{}")
            attachments = []
            total_bytes = 0
            try:
                for upload in form.getlist("files"):
                    content = await upload.read()
                    if len(content) > MAX_ATTACHMENT_BYTES:
                        raise AttachmentTooLargeError()
                    total_bytes += len(content)
                    if total_bytes > MAX_TOTAL_ATTACHMENT_BYTES:
                        raise AttachmentTooLargeError()
                    attachments.append(
                        {
                            "filename": upload.filename,
                            "content": content,
                            "content_type": upload.content_type,
                        }
                    )
            except AttachmentTooLargeError:
                logger.info("absence report refused: attachment too large")
                return messages.result(False, "api.absence.error.attachmentTooLarge")
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
        headers = {}
        disposition = upstream.headers.get("content-disposition")
        if disposition:
            headers["Content-Disposition"] = disposition
        return Response(
            content=upstream.content,
            media_type=upstream.headers.get("content-type", "application/octet-stream"),
            headers=headers,
        )

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
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": _inline_disposition(filename)},
        )
