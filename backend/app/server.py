import json
import os
import unicodedata
from pathlib import Path
from urllib.parse import quote

import requests
from fastapi import Body, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import holidays, marks, messages, schoolregion, subscriptions
from .calendar_listener import DEFAULT_PORT as CALENDAR_PORT
from .iserv.errors import LoginError, PasswordError, TwoFactorError
from .iserv.sick_note_pdf import UnsupportedTextError
from .service import NotConfiguredError, SickNoteNotFoundError
from .store import DEFAULT_CONFIG

CONFIG_ALLOWED_KEYS = set(DEFAULT_CONFIG) | {"poll_state"}

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 40 * 1024 * 1024


class AttachmentTooLargeError(Exception):
    pass


def _sanitize_phones(phones):
    if not isinstance(phones, list):
        return None
    cleaned = []
    for entry in phones:
        label = str(entry.get("label", "")).strip() if isinstance(entry, dict) else ""
        number = str(entry.get("number", "")).strip() if isinstance(entry, dict) else ""
        if not label and not number:
            continue
        if not label or not number:
            return None
        cleaned.append(entry)
    return cleaned


CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "frame-src 'none'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)
NOTIFY_TEST_MESSAGE_KEY = "notify.test.message"
NOTIFY_TEST_TITLE_KEY = "notify.test.title"
DEFAULT_LANGUAGE = "system"
MAX_WEEK = 8

NOT_CONFIGURED = "not_configured"
AUTH_FAILED = "auth_failed"
NETWORK = "network"
UPSTREAM_ERROR_CODES = (NOT_CONFIGURED, AUTH_FAILED, NETWORK)
UPSTREAM_ERROR_MESSAGE_KEYS = {
    NOT_CONFIGURED: "api.notConfigured",
    AUTH_FAILED: "api.authFailed",
    NETWORK: "api.network",
}


def upstream_error(code):
    body = {"error": code}
    body.update(messages.payload(UPSTREAM_ERROR_MESSAGE_KEYS[code]))
    return body


def upstream_write_error(code):
    return messages.result(False, UPSTREAM_ERROR_MESSAGE_KEYS[code], error=code)


def _upstream_code(error):
    if isinstance(error, NotConfiguredError):
        return NOT_CONFIGURED
    if isinstance(error, (LoginError, TwoFactorError)):
        return AUTH_FAILED
    return NETWORK


def read_endpoint(call):
    try:
        return call()
    except (NotConfiguredError, LoginError, TwoFactorError, requests.RequestException) as error:
        return upstream_error(_upstream_code(error))


def write_endpoint(call, fallback=None):
    try:
        return call()
    except (NotConfiguredError, LoginError, TwoFactorError, requests.RequestException) as error:
        return upstream_write_error(_upstream_code(error))
    except Exception:
        if fallback is None:
            raise
        return {"ok": False, "error": fallback}


BINARY_UPSTREAM_RESPONSES = {
    NOT_CONFIGURED: ("not configured", 503),
    AUTH_FAILED: ("auth failed", 503),
    NETWORK: ("upstream unavailable", 502),
}


def _binary_upstream_response(error):
    body, status = BINARY_UPSTREAM_RESPONSES[_upstream_code(error)]
    return PlainTextResponse(body, status_code=status)


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


def _clamp_week(value):
    try:
        week = int(value)
    except (TypeError, ValueError):
        return 0
    return max(-MAX_WEEK, min(MAX_WEEK, week))


PLACEHOLDER_HTML = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ranzenpost (IServ)</title></head>
<body style="font-family:system-ui;margin:0;display:grid;place-items:center;height:100vh;background:#f3f4f8;color:#14161c">
<div style="text-align:center;max-width:340px;padding:24px">
<h1 style="font-size:20px">Ranzenpost</h1>
<p style="color:#6b7280">Der Dienst läuft.</p>
</div></body></html>"""


def create_app(
    service,
    wizard=None,
    frontend_dir=None,
    holiday_calendar=None,
    registry=None,
    region_suggester=None,
    mark_registry=None,
):
    app = FastAPI(title="Ranzenpost")
    holiday_source = holiday_calendar or holidays.HolidayCalendar(service.store)
    region_source = region_suggester or schoolregion.RegionSuggester(service)
    subscription_registry = registry or subscriptions.SubscriptionRegistry(service.store)
    marks_registry = mark_registry or marks.MarkRegistry(service.store)

    @app.middleware("http")
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "configured": service.is_configured(),
            "connection": service.check_connection(),
            "username": service.store.load_secrets().get("username", ""),
            "language": service.store.load_config().get("language") or DEFAULT_LANGUAGE,
        }

    if wizard is not None:
        @app.get("/api/wizard")
        def wizard_status():
            return wizard.status()

        @app.post("/api/wizard/url")
        def wizard_url(body: dict = Body(...)):
            return wizard.set_url(body.get("url", ""))

        @app.post("/api/wizard/login")
        def wizard_login(body: dict = Body(...)):
            return wizard.set_login(body.get("username", ""), body.get("password", ""))

        @app.post("/api/wizard/connect")
        def wizard_connect(body: dict = Body(...)):
            return wizard.connect(body.get("code", ""))

        @app.post("/api/wizard/child")
        def wizard_child(body: dict = Body(...)):
            return wizard.select_child(
                body.get("child_id", ""),
                body.get("name", ""),
                body.get("class_name", ""),
            )

        @app.post("/api/wizard/skip-child")
        def wizard_skip_child():
            return wizard.skip_child()

        @app.post("/api/wizard/back")
        def wizard_back():
            return wizard.back()

        @app.post("/api/wizard/reset")
        def wizard_reset():
            return wizard.reset()

    @app.get("/api/timetable-availability")
    def timetable_availability():
        return {"available": service.timetable_available()}

    @app.get("/api/config")
    def get_config():
        return service.store.load_config()

    @app.post("/api/config")
    def set_config(config: dict = Body(...)):
        unknown_keys = sorted(key for key in config if key not in CONFIG_ALLOWED_KEYS)
        if unknown_keys:
            body = {"error": "unknown_keys", "keys": unknown_keys}
            body.update(messages.payload("api.config.unknownKeys", {"keys": ", ".join(unknown_keys)}))
            return JSONResponse(status_code=400, content=body)
        if "phones" in config:
            cleaned_phones = _sanitize_phones(config["phones"])
            if cleaned_phones is None:
                return JSONResponse(status_code=400, content={"error": "invalid_phones"})
            config = dict(config)
            config["phones"] = cleaned_phones
        current = service.store.load_config()
        for key, value in config.items():
            current[key] = value
        service.store.save_config(current)
        return {"saved": True}

    @app.post("/api/password")
    def change_password(body: dict = Body(...)):
        current = body.get("current", "")
        new = body.get("new", "")
        if not current or not new:
            return messages.result(False, "api.password.missing", error="missing")
        if len(new) < 8:
            return messages.result(False, "api.password.tooShort", error="too_short")
        try:
            outcome = service.change_password(current, new)
        except NotConfiguredError:
            return messages.result(False, "api.notConfigured", error="not_configured")
        except PasswordError:
            return messages.result(False, "api.password.rejected", error="rejected")
        except (LoginError, TwoFactorError):
            return messages.result(False, "api.password.authFailed", error="auth_failed")
        except requests.RequestException:
            return messages.result(False, "api.network", error="network")
        if outcome == "unverified":
            return messages.result(True, "api.password.unverified")
        return messages.result(True, "api.password.changed")

    @app.post("/api/password/repair")
    def repair_password(body: dict = Body(...)):
        password = body.get("password", "")
        if not password:
            return messages.result(False, "api.repair.missing")
        return write_endpoint(lambda: service.repair_password(password))

    @app.post("/api/account/disconnect")
    def disconnect_account():
        result = service.disconnect()
        if wizard is not None:
            wizard.reset()
        return result

    @app.get("/api/notify-services")
    def notify_services():
        from .haservices import list_notify_services

        return list_notify_services()

    @app.get("/api/me")
    def me():
        return read_endpoint(service.me)

    @app.get("/api/children")
    def children():
        return read_endpoint(service.children)

    @app.get("/api/timetable")
    def timetable(child_id: str, week: int = 0):
        return read_endpoint(lambda: service.timetable(child_id, week_offset=_clamp_week(week)))

    @app.get("/api/holidays/regions")
    def holiday_regions():
        return {"regions": holidays.region_options()}

    @app.get("/api/holidays/region-suggestion")
    def holiday_region_suggestion():
        return region_source.suggest()

    @app.get("/api/holidays")
    def holiday_range(week: int = 0, start: str = "", end: str = ""):
        first = holidays.parse_day(start)
        last = holidays.parse_day(end)
        if first is None or last is None:
            first, last = holidays.week_range(_clamp_week(week))
        if last < first:
            first, last = last, first
        if (last - first).days > holidays.MAX_SPAN_DAYS:
            return JSONResponse(
                status_code=400, content=messages.payload("api.holidays.error.range")
            )
        return holiday_source.range_info(first, last)

    @app.get("/api/pinboard")
    def pinboard():
        return read_endpoint(service.pinboard)

    @app.post("/api/pinboard/seen")
    def pinboard_seen(body: dict = Body(...)):
        return write_endpoint(
            lambda: service.mark_pinboard_seen(
                body.get("tile_ids"), body.get("all", False), body.get("unseen", False)
            )
        )

    @app.get("/api/pinboard/attachment/{filename}")
    def pinboard_attachment(filename: str):
        try:
            upstream = service.pinboard_attachment(filename)
        except (NotConfiguredError, LoginError, TwoFactorError, requests.RequestException) as error:
            return _binary_upstream_response(error)
        except Exception:
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

    @app.get("/api/letters")
    def letters(tab: str = "current"):
        return read_endpoint(lambda: service.letters(tab))

    @app.post("/api/letters/seen")
    def letters_seen(body: dict = Body(...)):
        return write_endpoint(
            lambda: service.mark_letters_read(body.get("keys"), body.get("all", False))
        )

    @app.get("/api/letters/detail")
    def letter_detail(letter_id: str, recipient_id: str):
        return read_endpoint(lambda: service.letter_detail(letter_id, recipient_id))

    def _archive_letter(body):
        service.archive_letter(body.get("letter_id", ""), body.get("recipient_id", ""))
        return {"ok": True}

    def _restore_letter(body):
        service.restore_letter(body.get("letter_id", ""), body.get("recipient_id", ""))
        return {"ok": True}

    @app.post("/api/letters/archive")
    def letters_archive(body: dict = Body(...)):
        return write_endpoint(lambda: _archive_letter(body), fallback="archive_failed")

    @app.post("/api/letters/restore")
    def letters_restore(body: dict = Body(...)):
        return write_endpoint(lambda: _restore_letter(body), fallback="restore_failed")

    def _confirm_letter(body):
        text = body.get("text")
        return service.confirm_letter(
            body.get("letter_id", ""),
            body.get("recipient_id", ""),
            text if isinstance(text, str) else None,
        )

    @app.post("/api/letters/confirm")
    def letters_confirm(body: dict = Body(...)):
        return write_endpoint(lambda: _confirm_letter(body), fallback="confirm_failed")

    @app.get("/api/letters/attachment/{attachment_id}")
    def letters_attachment(attachment_id: str):
        try:
            upstream = service.letter_attachment(attachment_id)
        except (NotConfiguredError, LoginError, TwoFactorError, requests.RequestException) as error:
            return _binary_upstream_response(error)
        except Exception:
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

    @app.get("/api/conferences")
    def conferences():
        return read_endpoint(service.conferences)

    @app.get("/api/absences")
    def absences():
        return read_endpoint(service.absences_overview)

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
                return messages.result(False, "api.absence.error.attachmentTooLarge")
        else:
            body = await request.json()
        return write_endpoint(lambda: service.report_absence(body, attachments=attachments))

    @app.post("/api/absences/delete")
    def delete_absence(body: dict = Body(...)):
        return write_endpoint(lambda: service.delete_absence(body))

    @app.get("/api/absences/attachment/{filename}")
    def absence_attachment(filename: str):
        try:
            upstream = service.absence_attachment(filename)
        except (NotConfiguredError, LoginError, TwoFactorError, requests.RequestException) as error:
            return _binary_upstream_response(error)
        except Exception:
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
    def sick_note_pdf(id: str = ""):
        try:
            pdf_bytes, filename = service.sick_note_pdf(id)
        except SickNoteNotFoundError:
            return PlainTextResponse("not found", status_code=404)
        except UnsupportedTextError:
            return PlainTextResponse("unsupported text", status_code=422)
        except (NotConfiguredError, LoginError, TwoFactorError, requests.RequestException) as error:
            return _binary_upstream_response(error)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": _inline_disposition(filename)},
        )

    @app.post("/api/notify-test")
    def notify_test(body: dict = Body(...)):
        from .hanotify import notify

        try:
            language = messages.normalize_language(body.get("language"))
            sent = notify(
                messages.text_in(language, NOTIFY_TEST_MESSAGE_KEY),
                service=body.get("service") or None,
                title=messages.text_in(language, NOTIFY_TEST_TITLE_KEY),
            )
        except Exception:
            sent = False
        if not sent:
            return messages.result(False, "api.notify.failed")
        return messages.result(True, "api.notify.sent")

    def _subscription_error(error):
        return JSONResponse(status_code=400, content=messages.result(False, error.message_key))

    @app.get("/api/calendar/subscriptions")
    def calendar_subscriptions():
        config = service.store.load_config()
        return {
            "subscriptions": subscription_registry.list(),
            "components": list(subscriptions.COMPONENTS),
            "holiday_region": config.get("holiday_region") or "",
            "path_template": "/calendar/{token}.ics",
            "port": int(os.environ.get("ISERV_CALENDAR_PORT", str(CALENDAR_PORT))),
        }

    @app.post("/api/calendar/subscriptions")
    def create_calendar_subscription(body: dict = Body(...)):
        try:
            return subscription_registry.create(
                body.get("child_id", ""),
                body.get("components"),
                body.get("label", ""),
                body.get("color", ""),
            )
        except subscriptions.SubscriptionError as error:
            return _subscription_error(error)

    @app.post("/api/calendar/subscriptions/{subscription_id}")
    def update_calendar_subscription(subscription_id: str, body: dict = Body(...)):
        try:
            return subscription_registry.update(
                subscription_id,
                components=body.get("components"),
                label=body.get("label"),
                color=body.get("color"),
            )
        except subscriptions.SubscriptionError as error:
            return _subscription_error(error)

    @app.post("/api/calendar/subscriptions/{subscription_id}/rotate")
    def rotate_calendar_subscription(subscription_id: str):
        try:
            return subscription_registry.rotate(subscription_id)
        except subscriptions.SubscriptionError as error:
            return _subscription_error(error)

    @app.delete("/api/calendar/subscriptions/{subscription_id}")
    def revoke_calendar_subscription(subscription_id: str):
        try:
            return subscription_registry.revoke(subscription_id)
        except subscriptions.SubscriptionError as error:
            return _subscription_error(error)

    def _mark_error(error):
        return JSONResponse(status_code=400, content=messages.result(False, error.message_key))

    @app.get("/api/marks")
    def list_marks(child_id: str = ""):
        return marks_registry.list(child_id)

    @app.post("/api/marks")
    def create_mark(body: dict = Body(...)):
        try:
            return marks_registry.create(
                body.get("child_id", ""),
                body.get("date", ""),
                body.get("period"),
                body.get("subject_code", ""),
                body.get("name", ""),
            )
        except marks.MarkError as error:
            return _mark_error(error)

    @app.post("/api/marks/{mark_id}")
    def update_mark(mark_id: str, body: dict = Body(...)):
        try:
            return marks_registry.update(
                mark_id,
                date_value=body.get("date"),
                period=body.get("period"),
                subject_code=body.get("subject_code"),
                name=body.get("name"),
            )
        except marks.MarkError as error:
            return _mark_error(error)

    @app.delete("/api/marks/{mark_id}")
    def delete_mark(mark_id: str):
        try:
            return marks_registry.delete(mark_id)
        except marks.MarkError as error:
            return _mark_error(error)

    if frontend_dir and Path(frontend_dir).is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    else:
        @app.get("/", response_class=HTMLResponse)
        def index():
            return PLACEHOLDER_HTML

    return app
