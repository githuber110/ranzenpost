import logging

import requests
from fastapi import Body
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from . import messages
from .iserv.errors import LoginError, TwoFactorError
from .failure import failure_cause
from .letter_service import LETTER_UNKNOWN_KEY
from .service import NotConfiguredError
from .upstream import binary_upstream_response, read_endpoint, write_endpoint

logger = logging.getLogger(__name__)

LETTER_REPLY_MAX_LENGTH = 4000


def _logged(label, call):
    def run():
        try:
            return call()
        except Exception as error:
            logger.warning("letter route %s failed: %s", label, failure_cause(error))
            raise

    return run


def register_routes(app, service):
    @app.get("/api/letters")
    def letters(tab: str = "current"):
        return read_endpoint(lambda: service.letters(tab))

    @app.post("/api/letters/seen")
    def letters_seen(body: dict = Body(...)):
        return write_endpoint(
            lambda: service.mark_letters_read(body.get("keys"), body.get("all", False))
        )

    @app.get("/api/letters/detail")
    def letter_detail(letter_id: str, recipient_id: str, connection: str = ""):
        return read_endpoint(lambda: service.letter_detail(connection, letter_id, recipient_id))

    def _archive_letter(body):
        service.archive_letter(body.get("connection_id", ""), body.get("letter_id", ""), body.get("recipient_id", ""))
        return {"ok": True}

    def _restore_letter(body):
        service.restore_letter(body.get("connection_id", ""), body.get("letter_id", ""), body.get("recipient_id", ""))
        return {"ok": True}

    @app.post("/api/letters/archive")
    def letters_archive(body: dict = Body(...)):
        return write_endpoint(_logged("archive", lambda: _archive_letter(body)), fallback="archive_failed")

    @app.post("/api/letters/restore")
    def letters_restore(body: dict = Body(...)):
        return write_endpoint(_logged("restore", lambda: _restore_letter(body)), fallback="restore_failed")

    def _confirm_letter(body):
        text = body.get("text")
        text = text.strip() if isinstance(text, str) else ""
        if len(text) > LETTER_REPLY_MAX_LENGTH:
            return messages.result(False, "api.letters.confirm.tooLong", {"max": LETTER_REPLY_MAX_LENGTH})
        return service.confirm_letter(
            body.get("connection_id", ""),
            body.get("letter_id", ""),
            body.get("recipient_id", ""),
            text or None,
        )

    @app.post("/api/letters/confirm")
    def letters_confirm(body: dict = Body(...)):
        return write_endpoint(_logged("confirm", lambda: _confirm_letter(body)), fallback="confirm_failed")

    def _reply_to_letter(body):
        text = body.get("text")
        text = text.strip() if isinstance(text, str) else ""
        if len(text) > LETTER_REPLY_MAX_LENGTH:
            return messages.result(False, "api.letters.reply.tooLong", {"max": LETTER_REPLY_MAX_LENGTH})
        return service.reply_to_letter(
            body.get("connection_id", ""),
            body.get("letter_id", ""),
            body.get("recipient_id", ""),
            text,
            body.get("request_id", ""),
            body.get("confirmed") is True,
        )

    @app.post("/api/letters/reply")
    def letters_reply(body: dict = Body(...)):
        return write_endpoint(_logged("reply", lambda: _reply_to_letter(body)), fallback="reply_failed")

    @app.get("/api/letters/attachment/{attachment_id}")
    def letters_attachment(attachment_id: str, connection: str = ""):
        try:
            upstream = service.letter_attachment(connection, attachment_id)
        except (NotConfiguredError, LoginError, TwoFactorError, requests.RequestException) as error:
            logger.warning("letter attachment could not be fetched: %s", failure_cause(error))
            return binary_upstream_response(error)
        except Exception as error:
            if getattr(error, "message_key", "") == LETTER_UNKNOWN_KEY:
                return JSONResponse(status_code=404, content=messages.payload(LETTER_UNKNOWN_KEY))
            logger.warning("letter attachment was refused before the request: %s", failure_cause(error))
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
