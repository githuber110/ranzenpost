import logging
import re
import time
from datetime import date, datetime, timedelta
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

from . import messages
from .iserv.absences import (
    DEREGISTER_TARGETS,
    ERROR_BODY,
    ERROR_DATE,
    ERROR_DAYCARE_KIND,
    ERROR_DEREGISTER_TARGET,
    ERROR_PICKUP_TIME,
    ERROR_RANGE,
    ERROR_REPEAT,
    ERROR_STUDENT,
    ERROR_SICK_LOCKED,
    ERROR_SUBJECT,
    KIND_DAYCARE,
    KIND_DEREGISTER,
    KIND_LEAVE,
    KIND_SICK,
    SICK_LOCKED_KEY,
    LEAVE_PATH,
    REQUESTS_PATH,
    TARGET_AFTERNOON_CARE,
    build_request,
    delete_path,
    merge_absence_history,
    normalize_sick_note,
    normalize_user_request,
    prune_absence_history,
    record_absence_history,
    sick_day_options,
)
from .iserv.client import IServClient
from .iserv.conferences import parse_conferences
from .iserv.html import plain_text
from .iserv.dsa import (
    DieSchulAppClient,
    absence_rules,
    deregister_options,
    enabled_absence_types,
    student_for_name,
)
from .iserv.sick_note_pdf import (
    render_sick_note_pdf,
    sick_note_pdf_filename,
    sick_note_title,
)
from .iserv.client import PASSWORD_UNVERIFIED
from .iserv.errors import DataError, LoginError, PasswordError, TwoFactorError
from .iserv.letters import (
    RESTORE_ACTION,
    build_archive_payload,
    build_batch_confirm_payload,
    build_confirmation_payload,
    build_hide_payload,
    parse_archive_form,
    parse_batch_confirm,
    parse_confirmation,
    parse_hide_confirm,
    parse_letter_detail,
    parse_letter_list,
)
from .iserv.timetable import lesson_key
from .iserv.totp import generate_code
from .iserv.twofactor import parse_delete_token
from .mapping import merge_discovered_codes, to_display
from .messenger import MessengerService

LETTERS_INDEX_PATH = "/iserv/parentletter/parent/index"
LETTERS_ARCHIVE_PATH = "/iserv/parentletter/parent/archive"
LETTERS_SHOW_PATH = "/iserv/parentletter/parent/show/{letter}/{recipient}"
LETTERS_ATTACHMENT_PATH = "/iserv/parentletter/attachment/{attachment}"
CONFERENCES_PATH = "/iserv/parentconference/attendee/"
NAV_BADGES_PATH = "/iserv/app/navigation/badges"
DSA_API_PATH = "/iserv/dieschulapp/api/1.0"
DSA_FILE_PATH = DSA_API_PATH + "/files/{filename}"
PINBOARD_ATTACHMENT_URL = "api/pinboard/attachment/{filename}"
ABSENCE_ATTACHMENT_URL = "api/absences/attachment/{filename}"
LESSON_SLOTS_PATH = "timetable-slots/"
LESSON_SLOTS_PARAMS = {"filterBy": "type:is(lesson)"}
LEAVE_MIN_DAYS_KEY = "requestToSchools_studentAbsence_minDays"
ABSENCE_ERROR_KEYS = {
    ERROR_SUBJECT: "api.absence.error.subject",
    ERROR_BODY: "api.absence.error.requestBody",
    ERROR_DEREGISTER_TARGET: "api.absence.error.deregisterTarget",
    ERROR_DAYCARE_KIND: "api.absence.error.daycareKind",
    ERROR_REPEAT: "api.absence.error.repeat",
    ERROR_STUDENT: "api.absence.error.student",
    ERROR_DATE: "api.absence.error.date",
    ERROR_PICKUP_TIME: "api.absence.error.pickupTime",
    ERROR_RANGE: "api.absence.error.range",
    ERROR_SICK_LOCKED: "api.absence.lockedSick",
}
DEREGISTER_LIST_PATHS = {
    target: f"{REQUESTS_PATH}not-attend/{target}/" for target in DEREGISTER_TARGETS
}
DAYCARE_LIST_PATH = f"{REQUESTS_PATH}not-attend/{TARGET_AFTERNOON_CARE}/"
ABSENCE_ERROR_FALLBACK_KEY = "api.absence.error.unknownKind"
ABSENCE_SENT_KEYS = {
    KIND_SICK: "api.absence.sent.sick",
    KIND_LEAVE: "api.absence.sent.leave",
    KIND_DEREGISTER: "api.absence.sent.deregister",
    KIND_DAYCARE: "api.absence.sent.daycare",
}
LETTER_CONFIRM_OK_KEY = "api.letters.confirm.ok"
LETTER_CONFIRM_DONE_KEY = "api.letters.confirm.alreadyDone"
LETTER_CONFIRM_GONE_KEY = "api.letters.confirm.gone"
LETTER_CONFIRM_UNSUPPORTED_KEY = "api.letters.confirm.unsupported"
LETTER_CONFIRM_UPSTREAM_KEY = "api.letters.confirm.upstream"
LETTER_CONFIRM_REJECTED_KEY = "api.letters.confirm.rejected"
SAFE_ID = re.compile(r"^[0-9a-fA-F-]{8,64}$")
SAFE_FILENAME = re.compile(r"^[^\x00-\x1f/\\]{1,120}$")


def _absence_failure(response, status_key="api.absence.upstream.statusSubmit"):
    status = getattr(response, "status_code", None)
    if status is None:
        return messages.result(False, "api.absence.upstream.unreachable")
    if status in (400, 422):
        detail = _absence_detail(response)
        if detail:
            return {"ok": False, "message": detail}
        return messages.result(False, "api.absence.upstream.rejected")
    if status in (401, 403):
        return messages.result(False, "api.absence.upstream.forbidden")
    if status == 404:
        return messages.result(False, "api.absence.upstream.gone")
    return messages.result(False, status_key, {"status": status})


def _absence_detail(response):
    try:
        data = response.json()
    except Exception:
        return ""
    if isinstance(data, dict):
        for key in ("message", "detail", "error"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _folder_order(title):
    text = (title or "").strip().lower()
    for umlaut, plain in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
        text = text.replace(umlaut, plain)
    return text


def _folder_sort_key(last_post_id, title):
    if last_post_id is None:
        return (1, _folder_order(title))
    return (0, -last_post_id)


def _published_sort_key(value):
    text = (value or "").strip()
    parts = text.split(" ")[0].split(".")
    if len(parts) == 3:
        try:
            day, month, year = (int(part) for part in parts)
            time_part = text.split(" ")[1] if " " in text else "00:00"
            hour, _, minute = time_part.partition(":")
            return (1, year, month, day, int(hour or 0), int(minute or 0))
        except ValueError:
            pass
    return (0, 0, 0, 0, 0, 0)


def _clean_id(value):
    value = (value or "").strip()
    if not SAFE_ID.match(value):
        raise DataError("invalid identifier")
    return value


def _clean_filename(value):
    value = (value or "").strip()
    if ".." in value or "/" in value or not SAFE_FILENAME.match(value):
        raise DataError("invalid filename")
    return value


def _attachment_file(attachment):
    candidate = (getattr(attachment, "file", "") or attachment.filename or "").strip()
    if ".." in candidate or not SAFE_FILENAME.match(candidate):
        return ""
    return candidate


def _absence_attachment_url(file_name):
    file_name = (file_name or "").strip()
    if ".." in file_name or not SAFE_FILENAME.match(file_name):
        return ""
    return ABSENCE_ATTACHMENT_URL.format(filename=file_name)


def _attachment_dict(attachment):
    file_name = _attachment_file(attachment)
    return {
        "id": attachment.id,
        "filename": attachment.filename,
        "extension": attachment.extension,
        "mimetype": attachment.mimetype,
        "size": attachment.size,
        "file": file_name,
        "url": PINBOARD_ATTACHMENT_URL.format(filename=file_name) if file_name else "",
        "created_at": attachment.created_at,
        "updated_at": attachment.updated_at,
        "image_width": attachment.image_width,
        "image_height": attachment.image_height,
    }


def _min_days(settings):
    value = (settings or {}).get(LEAVE_MIN_DAYS_KEY)
    if isinstance(value, bool) or value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


MAX_WEEK_OFFSET = 8


def _week_offset(value):
    try:
        offset = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(-MAX_WEEK_OFFSET, min(MAX_WEEK_OFFSET, offset))


def _as_int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


class NotConfiguredError(Exception):
    pass


class SickNoteNotFoundError(Exception):
    pass


TOTP_PERIOD = 30
DISCONNECT_NO_UUID_KEY = "api.disconnect.noUuid"
DISCONNECT_REMOVED_KEY = "api.disconnect.removed"
DISCONNECT_FAILED_KEY = "api.disconnect.failed"


def _disconnect_result(attempted, removed, key):
    body = {"attempted": attempted, "removed": removed}
    body.update(messages.payload(key))
    return body


def _next_totp_code(secret, used=None, sleeper=time.sleep, clock=time.time):
    code = generate_code(secret)
    if used is not None and used.get("code") == code:
        now = clock()
        sleeper(max(0.0, TOTP_PERIOD - (now % TOTP_PERIOD)) + 1)
        code = generate_code(secret)
    if used is not None:
        used["code"] = code
    return code


def _code_provider(secrets, used=None, sleeper=time.sleep, clock=time.time):
    def provide():
        secret = secrets.get("totp_secret")
        if not secret:
            raise TwoFactorError("account requires a two-factor code but none is stored")
        return _next_totp_code(secret, used, sleeper, clock)

    return provide


class IServService:
    def __init__(self, store, client_factory=None):
        self.store = store
        self.client_factory = client_factory or (lambda url: IServClient(url))
        self._client = None
        self._last_code = {}
        self._messenger_service = None

    def is_configured(self):
        config = self.store.load_config()
        secrets = self.store.load_secrets()
        return bool(config.get("school_url")) and bool(secrets.get("username"))

    def _login(self):
        config = self.store.load_config()
        secrets = self.store.load_secrets()
        if not config.get("school_url") or not secrets.get("username"):
            raise NotConfiguredError("school url or credentials missing")
        client = self.client_factory(config["school_url"])
        client.login(
            secrets["username"],
            secrets["password"],
            _code_provider(secrets, self._last_code),
        )
        self._client = client
        return client

    def _session(self):
        if self._client is None or not self._client.is_authenticated():
            return self._login()
        return self._client

    def iserv_session(self):
        return self._session()

    def _messenger(self):
        if self._messenger_service is None:
            self._messenger_service = MessengerService(self)
        return self._messenger_service

    def messenger_rooms(self):
        return self._messenger().rooms()

    def messenger_room_messages(self, room_id, before=None):
        return self._messenger().room_messages(room_id, before)

    def messenger_send(self, room_id, text):
        return self._messenger().send_message(room_id, text)

    def messenger_media(self, server_name, media_id):
        return self._messenger().media(server_name, media_id)

    def messenger_unread_pulse(self):
        return self._messenger().unread_pulse()

    def check_connection(self):
        if not self.is_configured():
            return "not_configured"
        if self._client is not None and self._client.is_authenticated():
            return "ok"
        try:
            self._login()
        except (LoginError, TwoFactorError):
            self._client = None
            return "auth_failed"
        except requests.RequestException:
            self._client = None
            return "network"
        except NotConfiguredError:
            return "not_configured"
        return "ok"

    def change_password(self, current, new):
        try:
            self._session().change_password(current, new)
        except PasswordError as error:
            if str(error) == PASSWORD_UNVERIFIED:
                self._store_password(new)
                return "unverified"
            raise
        self._store_password(new)
        return True

    def repair_password(self, password):
        config = self.store.load_config()
        secrets = self.store.load_secrets()
        url = config.get("school_url", "")
        username = secrets.get("username", "")
        if not url or not username:
            raise NotConfiguredError("school url or credentials missing")
        client = self.client_factory(url)
        client.username = username
        accepted = client.accepts_password(password)
        if accepted is False:
            return messages.result(False, "api.repair.rejected")
        if accepted is None:
            return messages.result(False, "api.repair.unreachable")
        self._store_password(password)
        return messages.result(True, "api.repair.ok")

    def _store_password(self, password):
        secrets = self.store.load_secrets()
        secrets["password"] = password
        self.store.save_secrets(secrets)
        self._client = None

    def disconnect(self):
        secrets = self.store.load_secrets()
        uuid = secrets.get("twofactor_uuid")
        if not uuid:
            iserv_result = _disconnect_result(False, False, DISCONNECT_NO_UUID_KEY)
        else:
            iserv_result = self._remove_iserv_token(secrets, uuid)
        self._clear_local_data()
        return iserv_result

    def _remove_iserv_token(self, secrets, uuid):
        secret = secrets.get("totp_secret")
        if not secret:
            return _disconnect_result(True, False, DISCONNECT_FAILED_KEY)
        try:
            client = self._session()
            list_page = client.get_twofactor_list_page()
            csrf_token = parse_delete_token(list_page.text)
            if not csrf_token:
                return _disconnect_result(True, False, DISCONNECT_FAILED_KEY)
            code = _next_totp_code(secret, self._last_code)
            removed = client.delete_totp_token(uuid, code, csrf_token)
        except (NotConfiguredError, LoginError, TwoFactorError, requests.RequestException):
            return _disconnect_result(True, False, DISCONNECT_FAILED_KEY)
        return _disconnect_result(True, removed, DISCONNECT_REMOVED_KEY if removed else DISCONNECT_FAILED_KEY)

    def _clear_local_data(self):
        self.store.save_seen({})
        self.store.save_absence_history({})
        self.store.save_letters_search_cache({})
        self.store.save_letters_confirmations({})
        self.store.reset_config()
        self.store.delete_secrets()
        self._client = None

    def children(self):
        native = self._session().get_children()
        try:
            students = self._dsa().students()
        except Exception:
            logger.debug("dsa students lookup failed", exc_info=True)
            students = []
        result = []
        for child in native:
            student = student_for_name(students, child.name)
            result.append({
                "child_id": child.child_id,
                "name": child.name,
                "class_name": student.get("class_name", "") if student else "",
                "student_id": student.get("id") if student else None,
                "class_full": student.get("class_full", "") if student else "",
                "class_code": student.get("class_code", "") if student else "",
            })
        return result

    def _dsa(self):
        client = self._session()
        return DieSchulAppClient(client.base_url, client.session)

    def school_profile(self):
        return self._dsa().school()

    def pinboard(self):
        boards = self._dsa().pinboards()
        seen_state = self.store.load_seen()
        seen = set(seen_state.get("pinboard", []))
        if not seen_state.get("pinboard_initialised"):
            for board in boards:
                for column in board.columns:
                    for tile in column.tiles:
                        seen.add(tile.id)
            seen_state["pinboard"] = sorted(seen)
            seen_state["pinboard_initialised"] = True
            self.store.save_seen(seen_state)
        folders = []
        feed = []
        for board in boards:
            unread_count = 0
            columns = []
            last_post_id = None
            for column in board.columns:
                tiles = []
                for tile in column.tiles:
                    is_unread = tile.id not in seen
                    if is_unread:
                        unread_count += 1
                    if tile.id is not None and (last_post_id is None or tile.id > last_post_id):
                        last_post_id = tile.id
                    entry = {
                        "id": tile.id,
                        "title": tile.title,
                        "text": tile.text,
                        "color": tile.color,
                        "owner": tile.owner,
                        "folder_id": board.id,
                        "folder_title": board.title,
                        "column_title": column.title,
                        "unread": is_unread,
                        "attachments": [_attachment_dict(a) for a in tile.attachments],
                    }
                    tiles.append(entry)
                    feed.append(entry)
                columns.append({"id": column.id, "title": column.title, "tiles": tiles})
            folders.append(
                {
                    "id": board.id,
                    "title": board.title,
                    "unread": unread_count,
                    "last_post_id": last_post_id,
                    "columns": columns,
                    "attachments": [_attachment_dict(a) for a in board.attachments],
                    "author": board.author,
                    "students_can_create_tiles": board.students_can_create_tiles,
                }
            )
        folders.sort(key=lambda entry: _folder_sort_key(entry.get("last_post_id"), entry.get("title")))
        feed.sort(key=lambda entry: entry["id"] or 0, reverse=True)
        return {"folders": folders, "feed": feed}

    def pinboard_attachment(self, filename):
        filename = _clean_filename(filename)
        return self._session().fetch(DSA_FILE_PATH.format(filename=quote(filename, safe="")))

    def absence_attachment(self, filename):
        return self.pinboard_attachment(filename)

    def mark_pinboard_seen(self, tile_ids=None, mark_all=False, unseen=False):
        seen = self.store.load_seen()
        current = set(seen.get("pinboard", []))
        if mark_all:
            for board in self._dsa().pinboards():
                for column in board.columns:
                    for tile in column.tiles:
                        current.add(tile.id)
        elif unseen:
            for tile_id in tile_ids or []:
                current.discard(tile_id)
        else:
            for tile_id in tile_ids or []:
                current.add(tile_id)
        seen["pinboard"] = sorted(current)
        self.store.save_seen(seen)
        return {"seen": len(current)}

    def _letter_key(self, entry):
        return f"{entry.get('letter_id')}:{entry.get('recipient_id')}"

    def letters(self, tab="current"):
        client = self._session()
        path = LETTERS_ARCHIVE_PATH if tab == "archive" else LETTERS_INDEX_PATH
        response = client.fetch(path)
        entries = parse_letter_list(response.text, response.url)
        entries.sort(key=lambda item: _published_sort_key(item.get("published")), reverse=True)
        search_cache = self.store.load_letters_search_cache()
        records = self.store.load_letters_confirmations()
        for entry in entries:
            key = self._letter_key(entry)
            entry["unread"] = bool(entry.get("unread")) and tab != "archive"
            cached = search_cache.get(key) or {}
            entry["body_text"] = cached.get("body_text", "")
            entry["attachments"] = cached.get("attachments", [])
            entry["confirmation"] = self._confirmation_state(
                cached.get("confirmation"), records.get(key)
            )
        return {"letters": entries}

    def _confirmation_state(self, parsed, record):
        record = record if isinstance(record, dict) else None
        parsed = parsed if isinstance(parsed, dict) else None
        if parsed is None and record is None:
            return None
        kind = (parsed or {}).get("type") or (record or {}).get("type") or ""
        done = record is not None
        return {
            "type": kind,
            "open": bool(parsed) and not done,
            "done": done,
            "sendable": bool((parsed or {}).get("sendable")),
            "confirmed_at": (record or {}).get("confirmed_at", ""),
        }

    def _cached_confirmation(self, parsed):
        if not parsed:
            return None
        return {"type": parsed.get("type", ""), "sendable": bool(parsed.get("sendable"))}

    def _confirmation_cache_entry(self, public):
        if not public or not public.get("open"):
            return None
        return {"type": public.get("type", ""), "sendable": bool(public.get("sendable"))}

    def _store_confirmation_cache(self, key, parsed):
        cache = self.store.load_letters_search_cache()
        entry = cache.get(key)
        if not isinstance(entry, dict):
            return
        state = self._cached_confirmation(parsed)
        if entry.get("confirmation") == state:
            return
        entry["confirmation"] = state
        cache[key] = entry
        self.store.save_letters_search_cache(cache)

    def _needs_confirmation_refresh(self, entry):
        if not isinstance(entry, dict):
            return True
        if "confirmation" not in entry:
            return True
        return bool(entry.get("confirmation"))

    def enrich_letters_search(self, tab="current"):
        entries = self.letters(tab)["letters"]
        cache = self.store.load_letters_search_cache()
        records = self.store.load_letters_confirmations()
        indexed = 0
        for entry in entries:
            key = self._letter_key(entry)
            cached = cache.get(key)
            known = key in cache
            if known and key in records:
                continue
            if known and not self._needs_confirmation_refresh(cached):
                continue
            detail = self.letter_detail(entry.get("letter_id"), entry.get("recipient_id"))
            cache[key] = {
                "body_text": cached.get("body_text", "") if known else plain_text(detail.get("body_html", "")),
                "attachments": cached.get("attachments", []) if known else detail.get("attachments", []),
                "confirmation": self._confirmation_cache_entry(detail.get("confirmation")),
            }
            indexed += 1
        if indexed:
            self.store.save_letters_search_cache(cache)
        return indexed

    def pending_confirmation_keys(self, tab="current"):
        entries = self.letters(tab)["letters"]
        return {
            self._letter_key(entry)
            for entry in entries
            if (entry.get("confirmation") or {}).get("open")
        }

    def mark_letters_read(self, keys=None, mark_all=False):
        targets = list(keys or [])
        if mark_all:
            targets = [
                self._letter_key(entry)
                for entry in self.letters("current")["letters"]
                if entry.get("unread")
            ]
        opened = 0
        for key in targets:
            letter_id, _, recipient_id = str(key).partition(":")
            if self._open_letter(letter_id, recipient_id):
                opened += 1
        return {"read": opened}

    def _open_letter(self, letter_id, recipient_id):
        letter_id = _clean_id(letter_id)
        recipient_id = _clean_id(recipient_id)
        if not letter_id or not recipient_id:
            return False
        response = self._session().fetch(
            LETTERS_SHOW_PATH.format(letter=letter_id, recipient=recipient_id)
        )
        return getattr(response, "status_code", 0) == 200

    def _fetch_letter_page(self, letter_id, recipient_id):
        client = self._session()
        response = client.fetch(LETTERS_SHOW_PATH.format(letter=letter_id, recipient=recipient_id))
        return client, response

    def letter_detail(self, letter_id, recipient_id):
        letter_id = _clean_id(letter_id)
        recipient_id = _clean_id(recipient_id)
        _, response = self._fetch_letter_page(letter_id, recipient_id)
        detail = parse_letter_detail(response.text, response.url)
        parsed = parse_confirmation(response.text, response.url)
        key = f"{letter_id}:{recipient_id}"
        self._store_confirmation_cache(key, parsed)
        record = self.store.load_letters_confirmations().get(key)
        attachments = [
            {"filename": item.get("filename") or "", "url": f"api/letters/attachment/{item.get('attachment_id')}"}
            for item in detail.get("attachments", [])
            if item.get("attachment_id")
        ]
        return {
            "title": detail.get("title", ""),
            "body_html": detail.get("body_html", ""),
            "attachments": attachments,
            "archive_url_present": bool(detail.get("archive_url")),
            "confirmation": self._confirmation_state(self._cached_confirmation(parsed), record),
        }

    def confirm_letter(self, letter_id, recipient_id, text=None):
        letter_id = _clean_id(letter_id)
        recipient_id = _clean_id(recipient_id)
        key = f"{letter_id}:{recipient_id}"
        records = self.store.load_letters_confirmations()
        if key in records:
            return messages.result(False, LETTER_CONFIRM_DONE_KEY)
        client, response = self._fetch_letter_page(letter_id, recipient_id)
        parsed = parse_confirmation(response.text, response.url)
        if parsed is None:
            self._store_confirmation_cache(key, None)
            return messages.result(False, LETTER_CONFIRM_GONE_KEY)
        if not parsed.get("sendable"):
            return messages.result(False, LETTER_CONFIRM_UNSUPPORTED_KEY)
        payload = build_confirmation_payload(parsed, text)
        sent = client.post_absolute(parsed["action"], data=payload)
        status = getattr(sent, "status_code", 0)
        if status not in (200, 201, 204, 302):
            return messages.result(False, LETTER_CONFIRM_UPSTREAM_KEY, {"status": status})
        _, verify = self._fetch_letter_page(letter_id, recipient_id)
        if parse_confirmation(verify.text, verify.url) is not None:
            return messages.result(False, LETTER_CONFIRM_REJECTED_KEY)
        stamp = datetime.now().replace(microsecond=0).isoformat()
        records[key] = {"type": parsed.get("type", ""), "confirmed_at": stamp}
        self.store.save_letters_confirmations(records)
        self._store_confirmation_cache(key, None)
        return messages.result(True, LETTER_CONFIRM_OK_KEY, confirmed_at=stamp)

    def archive_letter(self, letter_id, recipient_id):
        letter_id = _clean_id(letter_id)
        recipient_id = _clean_id(recipient_id)
        client = self._session()
        response = client.fetch(LETTERS_SHOW_PATH.format(letter=letter_id, recipient=recipient_id))
        detail = parse_letter_detail(response.text, response.url)
        archive_url = detail.get("archive_url")
        if not archive_url:
            raise DataError("archive action not available")
        confirm_page = client.fetch(archive_url)
        form = parse_hide_confirm(confirm_page.text, confirm_page.url)
        if form is None:
            raise DataError("archive confirmation form not found")
        client.post_absolute(form.action, data=build_hide_payload(form))
        return True

    def restore_letter(self, letter_id, recipient_id):
        letter_id = _clean_id(letter_id)
        recipient_id = _clean_id(recipient_id)
        client = self._session()
        response = client.fetch(LETTERS_ARCHIVE_PATH)
        form = parse_archive_form(response.text, response.url, RESTORE_ACTION)
        if form is None:
            raise DataError("restore action not available")
        payload = build_archive_payload(form, [f"{letter_id}-{recipient_id}"], RESTORE_ACTION)
        staged = client.post_absolute(form["action"], data=payload)
        confirm = parse_batch_confirm(staged.text, staged.url)
        if confirm is None:
            raise DataError("restore confirmation form not found")
        client.post_absolute(confirm.action, data=build_batch_confirm_payload(confirm, RESTORE_ACTION))
        return True

    def letter_attachment(self, attachment_id):
        attachment_id = _clean_id(attachment_id)
        client = self._session()
        return client.fetch(LETTERS_ATTACHMENT_PATH.format(attachment=attachment_id))

    def me(self):
        data = self._dsa()._get("users/me") or {}
        if not isinstance(data, dict):
            return {}
        school = data.get("school")
        school = school if isinstance(school, dict) else {}
        address = ", ".join(
            part
            for part in (school.get("street"), school.get("zip"), school.get("town"), school.get("country"))
            if part
        )
        return {
            "forename": str(data.get("forename") or "").strip(),
            "displayname": str(data.get("displayname") or "").strip(),
            "id": data.get("id"),
            "surname": str(data.get("surname") or "").strip(),
            "username": str(data.get("username") or "").strip(),
            "email": str(data.get("email") or "").strip(),
            "external_id": data.get("externalId"),
            "is_active": data.get("isActive"),
            "is_activated": data.get("isActivated"),
            "needs_re_registration": data.get("needsReRegistration"),
            "in_preparation": data.get("inPreparation"),
            "is_web_user": data.get("isWebUser"),
            "is_guardian": data.get("isGuardian"),
            "is_main_teacher": data.get("isMainTeacher"),
            "roles": data.get("roles") or [],
            "is_notified_by_email": data.get("isNotifiedByEmail"),
            "is_receiver_of_serial_print": data.get("isReceiverOfSerialPrint"),
            "is_newsletter_receiver": data.get("isNewsletterReceiver"),
            "has_active_devices": data.get("hasActiveDevices"),
            "has_2nd_factor_active": data.get("has2ndFactorActive"),
            "has_restricted_access_pin": data.get("hasRestrictedAccessPin"),
            "created_at": data.get("createdAt"),
            "updated_at": data.get("updatedAt"),
            "school_name": str(school.get("name") or "").strip(),
            "school_address": address,
        }

    def conferences(self):
        client = self._session()
        try:
            response = client.fetch_or_raise(CONFERENCES_PATH)
        except DataError:
            return {"error": "unavailable", "items": []}
        return parse_conferences(response.text, response.url)

    def iserv_badges(self):
        response = self._session().fetch(NAV_BADGES_PATH)
        if getattr(response, "status_code", 0) != 200:
            return {}
        try:
            payload = response.json()
        except ValueError:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): value for key, value in payload.items() if isinstance(value, int)}

    def timetable_available(self):
        try:
            settings = self._dsa().school_settings()
        except Exception:
            logger.debug("timetable availability lookup failed", exc_info=True)
            return True
        return bool(settings.get("timetable_availableForGuardiansAndStudents", True))

    def absences_overview(self):
        dsa = self._dsa()
        settings = dsa.school_settings()
        config = self.store.load_config()
        periods = dsa.lesson_slots()
        targets = deregister_options(settings)
        return {
            "children": dsa.sick_note_children(),
            "types": enabled_absence_types(settings),
            "deregister_options": targets,
            "periods": periods,
            "period_labels": self._period_labels(dsa, periods, config.get("language")),
            "rules": absence_rules(settings),
            "day_options": sick_day_options(),
            "leave_min_days": _min_days(settings),
            "entries": self._absence_entries(dsa, targets, settings),
            "phones": config.get("phones", []),
        }

    def _absence_entries(self, dsa, targets, settings):
        entries = [
            normalize_sick_note(item)
            for item in dsa.sick_notes(since=(date.today() - timedelta(days=30)).isoformat())
        ]
        if settings.get("requestToSchools_studentAbsence_isActive"):
            entries.extend(
                normalize_user_request(item, KIND_LEAVE)
                for item in dsa.user_requests(LEAVE_PATH)
            )
        for target in targets:
            entries.extend(
                normalize_user_request(item, KIND_DEREGISTER, target)
                for item in dsa.user_requests(DEREGISTER_LIST_PATHS[target])
            )
        if settings.get("requestToSchools_notAttend_afternoonCare_isActive"):
            entries.extend(
                normalize_user_request(item, KIND_DAYCARE, TARGET_AFTERNOON_CARE)
                for item in dsa.user_requests(DAYCARE_LIST_PATH)
            )
        for entry in entries:
            for attachment in entry.get("attachments") or []:
                attachment["url"] = _absence_attachment_url(attachment.get("file"))
        self._update_absence_history(entries)
        merged = merge_absence_history(entries, self.store.load_absence_history())
        merged.sort(key=lambda entry: entry.get("from_date") or "", reverse=True)
        return merged

    def _update_absence_history(self, entries):
        history = record_absence_history(self.store.load_absence_history(), entries)
        history = prune_absence_history(history)
        self.store.save_absence_history(history)

    def _period_labels(self, dsa, periods, language=None):
        starts = self._slot_times(dsa, "period_times")
        ends = self._slot_end_times(dsa)
        labels = []
        for slot in periods or []:
            number = slot.get("number")
            name = slot.get("name") or messages.text_in(
                language, "common.period.label", {"number": number}
            )
            start = starts.get(str(number))
            end = ends.get(str(number))
            label = f"{name} {start} - {end}" if start and end else name
            labels.append({"number": number, "label": label})
        return labels

    def _slot_times(self, dsa, method):
        try:
            return getattr(dsa, method)() or {}
        except Exception:
            logger.debug("dsa slot times lookup failed", exc_info=True)
            return {}

    def _slot_end_times(self, dsa):
        reader = getattr(dsa, "_get", None)
        if reader is None:
            return {}
        try:
            slots = reader(LESSON_SLOTS_PATH, dict(LESSON_SLOTS_PARAMS))
        except Exception:
            logger.debug("dsa lesson slots lookup failed", exc_info=True)
            return {}
        ends = {}
        for slot in slots or []:
            number = slot.get("number")
            end = slot.get("endTime")
            if number is not None and end:
                ends[str(number)] = end
        return ends

    def report_absence(self, payload, attachments=None):
        kind = payload.get("type")
        dsa = self._dsa()
        periods = dsa.lesson_slots() if kind == KIND_SICK else None
        try:
            request = build_request(
                kind, payload.get("student_id"), payload, periods=periods, attachments=attachments
            )
        except ValueError as error:
            return messages.result(False, ABSENCE_ERROR_KEYS.get(str(error), ABSENCE_ERROR_FALLBACK_KEY))
        response = dsa.send_request(request)
        if response is not None and response.status_code in (200, 201, 204):
            return messages.result(True, ABSENCE_SENT_KEYS.get(kind, "api.absence.sent.generic"))
        return _absence_failure(response)

    def delete_absence(self, payload):
        kind = payload.get("type")
        if kind == KIND_SICK:
            return messages.result(False, SICK_LOCKED_KEY)

        try:
            path = delete_path(kind, payload.get("id"), payload.get("target"))
        except ValueError as error:
            return messages.result(False, ABSENCE_ERROR_KEYS.get(str(error), ABSENCE_ERROR_FALLBACK_KEY))
        response = self._dsa().delete_entry(path)
        if response is not None and response.status_code in (200, 202, 204):
            return messages.result(True, "api.absence.withdrawn")
        return _absence_failure(response, "api.absence.upstream.statusWithdraw")

    def sick_note_pdf(self, sick_note_id):
        try:
            wanted_id = int(str(sick_note_id).strip())
        except (TypeError, ValueError):
            raise SickNoteNotFoundError("invalid sick note id")
        dsa = self._dsa()
        note = next(
            (
                normalize_sick_note(item)
                for item in dsa.sick_notes()
                if _as_int(item.get("id")) == wanted_id
            ),
            None,
        )
        if note is None:
            raise SickNoteNotFoundError("sick note not found")
        children = dsa.sick_note_children()
        child = next(
            (c for c in children if _as_int(c.get("id")) == note.get("student_id")), None
        )
        if child is None:
            raise SickNoteNotFoundError("sick note not found")
        settings = dsa.school_settings()
        title = sick_note_title(settings)
        name = child.get("name") or ""
        class_code = (note.get("technical") or {}).get("class_code") or ""
        pdf_bytes = render_sick_note_pdf(
            title,
            name,
            class_code,
            note.get("from_date"),
            note.get("till_date"),
            note.get("from_period"),
            note.get("till_period"),
        )
        return pdf_bytes, sick_note_pdf_filename(title, name)

    def _school_period_times(self):
        try:
            return self._dsa().period_times() or {}
        except Exception:
            logger.debug("dsa period times lookup failed", exc_info=True)
            return {}

    def _merge_period_times(self, config, discovered):
        times = dict(config.get("period_times", {}))
        changed = False
        for number, start in (discovered or {}).items():
            if start and not times.get(str(number)):
                times[str(number)] = start
                changed = True
        if not changed:
            return config
        merged = dict(config)
        merged["period_times"] = times
        return merged

    def timetable(self, child_id, reference=None, week_offset=0):
        offset = _week_offset(week_offset)
        target = (reference or date.today()) + timedelta(days=7 * offset)
        week = self._session().get_timetable(child_id, target)
        config = self.store.load_config()
        merged = merge_discovered_codes(config, week.combined + week.plain)
        school_times = self._school_period_times()
        merged = self._merge_period_times(merged, school_times)
        if merged != config:
            self.store.save_config(merged)
            config = merged
        lesson_changes = getattr(week, "lesson_changes", None) or {}
        cancelled = getattr(week, "cancelled", None) or []
        lessons = [
            to_display(lesson, config, lesson_changes.get(lesson_key(lesson.date, lesson.period, lesson.subject)))
            for lesson in week.combined
        ]
        for lesson in cancelled:
            change = dict(lesson_changes.get(lesson_key(lesson.date, lesson.period, lesson.subject)) or {})
            change["kind"] = "cancelled"
            lessons.append(to_display(lesson, config, change))
        return {
            "last_updated": week.last_updated,
            "start_date": week.start_date,
            "end_date": week.end_date,
            "lessons": lessons,
            "changes": week.changes,
            "period_times": config.get("period_times", {}),
            "school_period_times": school_times,
            "change_count": sum(1 for entry in lessons if entry["change_kind"]),
            "week_offset": offset,
        }
