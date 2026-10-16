import json
import logging

import requests
from fastapi import Body, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse

from . import messages
from .failure import failure_cause
from .iserv import mail, mail_frame
from .iserv.errors import DataError, LoginError, TwoFactorError
from .iserv.mail_compose import ATTACHMENT_LIMIT, TOO_LARGE_KEY
from .service import NotConfiguredError, SchoolRequiredError
from .uploads import LIMIT_TOTAL, UploadLimitError, declared_too_large, read_uploads
from .upstream import binary_upstream_response, read_endpoint, upstream_file, write_endpoint

logger = logging.getLogger(__name__)

MISSING_KEYS = (mail.UNKNOWN_ATTACHMENT_KEY, mail.UNKNOWN_MESSAGE_KEY, mail.UNKNOWN_FOLDER_KEY)
SEARCH_FIELDS = ("status", "query", "scope", "since", "until", "tag")


FRAME_HEADERS = {"X-Content-Type-Options": "nosniff", "Cross-Origin-Resource-Policy": "same-origin", "Referrer-Policy": "no-referrer"}


async def _compose_body(request):
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        return await request.json(), []
    if declared_too_large(request, ATTACHMENT_LIMIT):
        raise UploadLimitError(LIMIT_TOTAL)
    form = await request.form()
    body = json.loads(form.get("data") or "{}")
    files = await read_uploads(form, ATTACHMENT_LIMIT, ATTACHMENT_LIMIT)
    return body, [{"filename": entry["filename"], "content": entry["content"], "mimetype": entry["content_type"]} for entry in files]


def _expect(body):
    return body.get("expect") if isinstance(body.get("expect"), dict) else None


def register_routes(app, service):
    def call(connection, action, *args, **kwargs):
        return service.mail_call(connection or None, action, *args, **kwargs)

    @app.get("/api/mail/folders")
    def mail_folders(connection: str = ""):
        return read_endpoint(lambda: call(connection, "folders"))

    @app.get("/api/mail/messages")
    def mail_messages(request: Request, folder: str = "", connection: str = "", offset: int = 0, order: str = "newest", everywhere: bool = False, limit: int = 0):
        search = {key: request.query_params.get(key) for key in SEARCH_FIELDS if request.query_params.get(key)}
        if everywhere:
            return read_endpoint(lambda: call(connection, "search_everywhere", search, order))
        return read_endpoint(lambda: call(connection, "messages", folder, offset, search, order, limit or None))

    @app.get("/api/mail/message")
    def mail_message(folder: str, uid: str, connection: str = ""):
        return read_endpoint(lambda: call(connection, "message", folder, uid))

    @app.get("/api/mail/source")
    def mail_source(folder: str, uid: str, connection: str = ""):
        return read_endpoint(lambda: call(connection, "source", folder, uid))

    @app.get("/api/mail/compose")
    def mail_compose_start(connection: str = "", folder: str = "", uid: str = "", mode: str = "new"):
        return read_endpoint(lambda: call(connection, "compose_start", folder, uid, mode))

    @app.post("/api/mail/seen")
    def mail_seen(body: dict = Body(...)):
        return write_endpoint(lambda: call(body.get("connection_id") or None, "mark_seen", body.get("folder", ""), body.get("uid", ""), expect=_expect(body)), fallback="seen_failed")

    @app.post("/api/mail/flag")
    def mail_flag(body: dict = Body(...)):
        return write_endpoint(
            lambda: call(body.get("connection_id") or None, "set_flag", body.get("folder", ""), body.get("uids") or [], body.get("flag", ""), body.get("on") is True, expect=_expect(body)),
            fallback="flag_failed",
        )

    @app.post("/api/mail/move")
    def mail_move(body: dict = Body(...)):
        return write_endpoint(lambda: call(body.get("connection_id") or None, "move", body.get("folder", ""), body.get("uids") or [], body.get("target", ""), expect=_expect(body)), fallback="move_failed")

    @app.post("/api/mail/archive")
    def mail_archive(body: dict = Body(...)):
        return write_endpoint(lambda: call(body.get("connection_id") or None, "archive", body.get("folder", ""), body.get("uids") or [], expect=_expect(body)), fallback="archive_failed")

    @app.post("/api/mail/trash")
    def mail_trash(body: dict = Body(...)):
        return write_endpoint(
            lambda: call(body.get("connection_id") or None, "trash", body.get("folder", ""), body.get("uids") or [], body.get("confirmed") is True, expect=_expect(body)),
            fallback="trash_failed",
        )

    @app.post("/api/mail/spam")
    def mail_spam(body: dict = Body(...)):
        return write_endpoint(
            lambda: call(body.get("connection_id") or None, "spam", body.get("folder", ""), body.get("uids") or [], body.get("confirmed") is True, expect=_expect(body)),
            fallback="spam_failed",
        )

    @app.post("/api/mail/folder/create")
    def mail_folder_create(body: dict = Body(...)):
        return write_endpoint(lambda: call(body.get("connection_id") or None, "create_folder", body.get("name", ""), body.get("parent", "")), fallback="folder_failed")

    @app.post("/api/mail/folder/rename")
    def mail_folder_rename(body: dict = Body(...)):
        return write_endpoint(lambda: call(body.get("connection_id") or None, "rename_folder", body.get("folder", ""), body.get("name", "")), fallback="folder_failed")

    @app.post("/api/mail/folder/delete")
    def mail_folder_delete(body: dict = Body(...)):
        return write_endpoint(lambda: call(body.get("connection_id") or None, "delete_folder", body.get("folder", ""), body.get("confirmed") is True), fallback="folder_failed")

    @app.post("/api/mail/draft/delete")
    def mail_draft_delete(body: dict = Body(...)):
        return write_endpoint(
            lambda: call(body.get("connection_id") or None, "delete_draft", body.get("folder", ""), body.get("uid", ""), body.get("confirmed") is True),
            fallback="draft_failed",
        )

    @app.post("/api/mail/receipt")
    def mail_receipt(body: dict = Body(...)):
        return write_endpoint(
            lambda: call(body.get("connection_id") or None, "receipt", body.get("folder", ""), body.get("uid", ""), body.get("send") is True, body.get("confirmed") is True,
                         str(body.get("request_id") or ""), expect=_expect(body)),
            fallback="receipt_failed",
        )

    def web(connection, action, *args, **kwargs):
        return service.mail_web_call(connection or None, action, *args, **kwargs)

    @app.get("/api/mail/account")
    def mail_account(connection: str = ""):
        return read_endpoint(lambda: web(connection, "account"))

    @app.get("/api/mail/recipients")
    def mail_recipients(q: str = "", connection: str = ""):
        return read_endpoint(lambda: web(connection, "recipients", q))

    @app.get("/api/mail/settings")
    def mail_settings(connection: str = ""):
        return read_endpoint(lambda: web(connection, "settings"))

    @app.get("/api/mail/settings/page")
    def mail_settings_page(path: str, connection: str = ""):
        return read_endpoint(lambda: web(connection, "settings_page", path))

    @app.post("/api/mail/settings/page")
    def mail_settings_save(body: dict = Body(...)):
        def save():
            try:
                form = int(body.get("form"))
            except (TypeError, ValueError):
                form = -1
            fields = body.get("fields") if isinstance(body.get("fields"), list) else None
            values = body.get("values") if isinstance(body.get("values"), dict) else {}
            return web(body.get("connection_id") or None, "save_settings", str(body.get("path") or ""), form, values, fields, body.get("confirmed") is True)

        return write_endpoint(save, fallback="settings_failed")

    @app.get("/api/mail/event")
    def mail_event_form(folder: str, uid: str, connection: str = ""):
        return read_endpoint(lambda: web(connection, "event_form", folder, uid))

    @app.post("/api/mail/event")
    def mail_event_save(body: dict = Body(...)):
        def save():
            try:
                form = int(body.get("form"))
            except (TypeError, ValueError):
                form = -1
            fields = body.get("fields") if isinstance(body.get("fields"), list) else None
            values = body.get("values") if isinstance(body.get("values"), dict) else {}
            return web(
                body.get("connection_id") or None, "save_event", str(body.get("path") or ""), form, values, fields, body.get("confirmed") is True,
                request_id=str(body.get("request_id") or ""), check=str(body.get("check") or ""),
            )

        return write_endpoint(save, fallback="event_failed")

    @app.post("/api/mail/draft")
    async def mail_draft(request: Request):
        try:
            body, uploads = await _compose_body(request)
        except UploadLimitError:
            return messages.result(False, TOO_LARGE_KEY)
        return await run_in_threadpool(write_endpoint, lambda: call(body.get("connection_id") or None, "save_draft", body, uploads), "draft_failed")

    @app.post("/api/mail/send")
    async def mail_send(request: Request):
        try:
            body, uploads = await _compose_body(request)
        except UploadLimitError:
            return messages.result(False, TOO_LARGE_KEY)
        return await run_in_threadpool(
            write_endpoint, lambda: call(body.get("connection_id") or None, "send", body, uploads, body.get("confirmed") is True), "send_failed"
        )

    @app.get("/api/mail/attachment")
    def mail_attachment(folder: str, uid: str, part: str, connection: str = ""):
        try:
            found = service.mail_attachment(connection or None, folder, uid, part)
        except (NotConfiguredError, SchoolRequiredError, LoginError, TwoFactorError, requests.RequestException) as error:
            logger.warning("mail attachment could not be fetched: %s", failure_cause(error))
            return binary_upstream_response(error)
        except DataError as error:
            status = 404 if error.message_key in MISSING_KEYS else 502
            return JSONResponse(status_code=status, content=messages.payload(error.message_key or mail.UNREADABLE_KEY))
        return upstream_file(found)

    @app.get("/api/mail/body")
    def mail_body(folder: str, uid: str, connection: str = "", theme: str = "light"):
        try:
            page = service.mail_call(connection or None, "body_page", folder, uid, mail_frame.theme_of(theme))
        except (NotConfiguredError, SchoolRequiredError, LoginError, TwoFactorError, requests.RequestException) as error:
            logger.warning("mail body could not be fetched: %s", failure_cause(error))
            return binary_upstream_response(error)
        except DataError as error:
            status = 404 if error.message_key in MISSING_KEYS else 502
            return JSONResponse(status_code=status, content=messages.payload(error.message_key or mail.UNREADABLE_KEY))
        headers = dict(FRAME_HEADERS, **{"Content-Security-Policy": mail_frame.FRAME_POLICY})
        return HTMLResponse(content=page["html"], headers=headers)
