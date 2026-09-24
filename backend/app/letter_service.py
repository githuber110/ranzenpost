import logging
import re
import threading
from datetime import datetime
from urllib.parse import urlparse

from . import messages
from .attachments import LETTERS_ATTACHMENT_URL
from .iserv.errors import DataError
from .iserv.html import plain_text
from .iserv.letters import (
    RESTORE_ACTION,
    build_archive_payload,
    build_batch_confirm_payload,
    build_confirmation_payload,
    confirmation_evidence,
    build_hide_payload,
    parse_archive_form,
    parse_batch_confirm,
    page_notices,
    parse_confirmation,
    parse_hide_confirm,
    parse_letter_detail,
    parse_letter_list,
)
from .sorting import _published_sort_key
from .store import edit_slot

logger = logging.getLogger(__name__)

LETTERS_INDEX_PATH = "/iserv/parentletter/parent/index"
LETTERS_ARCHIVE_PATH = "/iserv/parentletter/parent/archive"
LETTERS_SHOW_PATH = "/iserv/parentletter/parent/show/{letter}/{recipient}"
LETTERS_ATTACHMENT_PATH = "/iserv/parentletter/attachment/{attachment}"
LETTER_CONFIRM_OK_KEY = "api.letters.confirm.ok"
LETTER_CONFIRM_DONE_KEY = "api.letters.confirm.alreadyDone"
LETTER_CONFIRM_GONE_KEY = "api.letters.confirm.gone"
LETTER_CONFIRM_BUSY_KEY = "api.letters.confirm.busy"
LETTER_CONFIRM_NO_MESSAGE_FIELD_KEY = "api.letters.confirm.noMessageField"
LETTER_CONFIRM_UNSUPPORTED_KEY = "api.letters.confirm.unsupported"
LETTER_CONFIRM_UPSTREAM_KEY = "api.letters.confirm.upstream"
LETTER_CONFIRM_REJECTED_KEY = "api.letters.confirm.rejected"
LETTER_OPEN_READ = "read"
LETTER_OPEN_BLOCKED = "blocked"
LETTER_OPEN_FAILED = "failed"
LETTER_ARCHIVE_FAILED_KEY = "api.letters.archiveFailed"
LETTER_RESTORE_FAILED_KEY = "api.letters.restoreFailed"
WRITE_OK_STATUSES = (200, 201, 204, 302, 303)
SAFE_ID = re.compile(r"^[0-9a-fA-F-]{8,64}$")


def _require_write(response, message_key):
    status = int(getattr(response, "status_code", 0) or 0)
    if status not in WRITE_OK_STATUSES:
        raise DataError(
            "the school server refused the change",
            message_key=message_key,
            detail={"status": status},
        )
    return response


def _clean_id(value):
    value = (value or "").strip()
    if not SAFE_ID.match(value):
        raise DataError("invalid identifier")
    return value


def _browser_headers(page_url):
    page = str(page_url or "")
    parts = urlparse(page)
    headers = {"Referer": page} if page else {}
    if parts.scheme and parts.netloc:
        headers["Origin"] = f"{parts.scheme}://{parts.netloc}"
    return headers


class LetterService:
    def __init__(self, connection):
        self.connection = connection
        self._confirming = set()
        self._confirming_lock = threading.Lock()

    def _letter_key(self, entry):
        return f"{entry.get('letter_id')}:{entry.get('recipient_id')}"

    def letters(self, tab="current"):
        client = self.connection._session()
        path = LETTERS_ARCHIVE_PATH if tab == "archive" else LETTERS_INDEX_PATH
        response = client.fetch_or_raise(path)
        entries = parse_letter_list(response.text, response.url)
        entries.sort(key=lambda item: _published_sort_key(item.get("published")), reverse=True)
        search_cache = self.connection.store.load_letters_search_cache()
        records = self.connection.store.load_letters_confirmations()
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
            "can_reply": bool(
                (parsed or {}).get("can_reply") or (parsed or {}).get("editor") or (parsed or {}).get("text_field")
            ),
            "confirmed_at": (record or {}).get("confirmed_at", ""),
        }

    def _cached_confirmation(self, parsed):
        if not parsed:
            return None
        return {
            "type": parsed.get("type", ""),
            "sendable": bool(parsed.get("sendable")),
            "can_reply": bool(parsed.get("editor") or parsed.get("text_field")),
        }

    def _confirmation_cache_entry(self, public):
        if not public or not public.get("open"):
            return None
        return {
            "type": public.get("type", ""),
            "sendable": bool(public.get("sendable")),
            "can_reply": bool(public.get("can_reply")),
        }

    def _store_confirmation_cache(self, key, parsed):
        state = self._cached_confirmation(parsed)

        def change(cache):
            entry = cache.get(key)
            if isinstance(entry, dict):
                cache[key] = dict(entry, confirmation=state)

        edit_slot(self.connection.store, "letters_search_cache", change)

    def _needs_confirmation_refresh(self, entry):
        if not isinstance(entry, dict):
            return True
        if "confirmation" not in entry:
            return True
        return bool(entry.get("confirmation"))

    def enrich_letters_search(self, tab="current"):
        entries = self.letters(tab)["letters"]
        cache = self.connection.store.load_letters_search_cache()
        cached_before = dict(cache)
        records = self.connection.store.load_letters_confirmations()
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
            fresh = {key: value for key, value in cache.items() if value is not cached_before.get(key)}

            def change(current):
                confirmed = self.connection.store.load_letters_confirmations()
                for key, value in fresh.items():
                    if key in confirmed and key in current:
                        continue
                    current[key] = value

            edit_slot(self.connection.store, "letters_search_cache", change)
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
        blocked = 0
        failed = 0
        for key in targets:
            letter_id, _, recipient_id = str(key).partition(":")
            try:
                outcome = self._open_letter(letter_id, recipient_id)
            except DataError:
                logger.warning("a letter could not be opened while marking it read", exc_info=True)
                outcome = LETTER_OPEN_FAILED
            if outcome == LETTER_OPEN_READ:
                opened += 1
            elif outcome == LETTER_OPEN_BLOCKED:
                blocked += 1
            else:
                failed += 1
        return {"read": opened, "blocked": blocked, "failed": failed}

    def _open_letter(self, letter_id, recipient_id):
        letter_id = _clean_id(letter_id)
        recipient_id = _clean_id(recipient_id)
        if not letter_id or not recipient_id:
            return LETTER_OPEN_FAILED
        response = self.connection._session().fetch(
            LETTERS_SHOW_PATH.format(letter=letter_id, recipient=recipient_id)
        )
        if getattr(response, "status_code", 0) != 200:
            return LETTER_OPEN_FAILED
        parsed = parse_confirmation(response.text, response.url)
        self._store_confirmation_cache(f"{letter_id}:{recipient_id}", parsed)
        if parsed is not None:
            return LETTER_OPEN_BLOCKED
        return LETTER_OPEN_READ

    def _fetch_letter_page(self, letter_id, recipient_id):
        client = self.connection._session()
        response = client.fetch_or_raise(LETTERS_SHOW_PATH.format(letter=letter_id, recipient=recipient_id))
        return client, response

    def letter_detail(self, letter_id, recipient_id):
        letter_id = _clean_id(letter_id)
        recipient_id = _clean_id(recipient_id)
        _, response = self._fetch_letter_page(letter_id, recipient_id)
        detail = parse_letter_detail(response.text, response.url)
        parsed = parse_confirmation(response.text, response.url)
        key = f"{letter_id}:{recipient_id}"
        self._store_confirmation_cache(key, parsed)
        record = self.connection.store.load_letters_confirmations().get(key)
        attachments = [
            {
                "filename": item.get("filename") or "",
                "url": LETTERS_ATTACHMENT_URL.format(attachment=item.get("attachment_id"), connection=self.connection.id),
            }
            for item in detail.get("attachments", [])
            if item.get("attachment_id")
        ]
        return {
            "title": detail.get("title", ""),
            "body_html": detail.get("body_html", ""),
            "attachments": attachments,
            "archive_url_present": bool(detail.get("archive_url")),
            "confirmation": self._confirmation_state(self._cached_confirmation(parsed), record),
            "confirmation_evidence": confirmation_evidence(response.text) if parsed is not None else None,
        }

    def confirm_letter(self, letter_id, recipient_id, text=None):
        letter_id = _clean_id(letter_id)
        recipient_id = _clean_id(recipient_id)
        key = f"{letter_id}:{recipient_id}"
        records = self.connection.store.load_letters_confirmations()
        if key in records:
            return messages.result(False, LETTER_CONFIRM_DONE_KEY)
        with self._confirming_lock:
            if key in self._confirming:
                return messages.result(False, LETTER_CONFIRM_BUSY_KEY)
            self._confirming.add(key)
        try:
            return self._confirm_letter(letter_id, recipient_id, key, text)
        finally:
            with self._confirming_lock:
                self._confirming.discard(key)

    def _confirm_letter(self, letter_id, recipient_id, key, text):
        client, response = self._fetch_letter_page(letter_id, recipient_id)
        parsed = parse_confirmation(response.text, response.url)
        if parsed is None:
            self._store_confirmation_cache(key, None)
            return messages.result(False, LETTER_CONFIRM_GONE_KEY)
        if not parsed.get("sendable"):
            return messages.result(False, LETTER_CONFIRM_UNSUPPORTED_KEY)
        if text and not (parsed.get("editor") or parsed.get("text_field")):
            return messages.result(False, LETTER_CONFIRM_NO_MESSAGE_FIELD_KEY)
        payload = build_confirmation_payload(parsed, text)
        sent = client.post_absolute(parsed["action"], data=payload, headers=_browser_headers(response.url))
        status = getattr(sent, "status_code", 0)
        if status not in (200, 201, 204, 302):
            return messages.result(
                False,
                LETTER_CONFIRM_UPSTREAM_KEY,
                {"status": status},
                diagnosis=self._confirm_diagnosis(sent, None),
            )
        _, verify = self._fetch_letter_page(letter_id, recipient_id)
        if parse_confirmation(verify.text, verify.url) is not None:
            return messages.result(
                False, LETTER_CONFIRM_REJECTED_KEY, diagnosis=self._confirm_diagnosis(sent, verify)
            )
        stamp = datetime.now().replace(microsecond=0).isoformat()
        record = {"type": parsed.get("type", ""), "confirmed_at": stamp}
        edit_slot(self.connection.store, "letters_confirmations", lambda current: current.update({key: record}))
        self._store_confirmation_cache(key, None)
        return messages.result(True, LETTER_CONFIRM_OK_KEY, confirmed_at=stamp)

    @staticmethod
    def _confirm_diagnosis(sent, verify):
        diagnosis = {
            "post_status": getattr(sent, "status_code", 0),
            "post_path": urlparse(str(getattr(sent, "url", "") or "")).path,
            "post_redirects": len(getattr(sent, "history", None) or []),
            "response_notices": page_notices(getattr(sent, "text", "") or ""),
        }
        if verify is not None:
            after = confirmation_evidence(verify.text) or {}
            diagnosis["after_marks"] = after.get("confirmation_marks", [])
            diagnosis["after_disabled"] = bool(after.get("confirmation_disabled"))
            diagnosis["after_button"] = after.get("confirmation_button", "")
        return diagnosis

    def archive_letter(self, letter_id, recipient_id):
        letter_id = _clean_id(letter_id)
        recipient_id = _clean_id(recipient_id)
        client = self.connection._session()
        response = client.fetch_or_raise(LETTERS_SHOW_PATH.format(letter=letter_id, recipient=recipient_id))
        detail = parse_letter_detail(response.text, response.url)
        archive_url = detail.get("archive_url")
        if not archive_url:
            raise DataError("archive action not available", message_key=LETTER_ARCHIVE_FAILED_KEY)
        confirm_page = client.fetch_or_raise(archive_url)
        form = parse_hide_confirm(confirm_page.text, confirm_page.url)
        if form is None:
            raise DataError("archive confirmation form not found", message_key=LETTER_ARCHIVE_FAILED_KEY)
        _require_write(
            client.post_absolute(form.action, data=build_hide_payload(form)),
            LETTER_ARCHIVE_FAILED_KEY,
        )
        return True

    def restore_letter(self, letter_id, recipient_id):
        letter_id = _clean_id(letter_id)
        recipient_id = _clean_id(recipient_id)
        client = self.connection._session()
        response = client.fetch_or_raise(LETTERS_ARCHIVE_PATH)
        form = parse_archive_form(response.text, response.url, RESTORE_ACTION)
        if form is None:
            raise DataError("restore action not available", message_key=LETTER_RESTORE_FAILED_KEY)
        payload = build_archive_payload(form, [f"{letter_id}-{recipient_id}"], RESTORE_ACTION)
        staged = _require_write(
            client.post_absolute(form["action"], data=payload), LETTER_RESTORE_FAILED_KEY
        )
        confirm = parse_batch_confirm(staged.text, staged.url)
        if confirm is None:
            raise DataError("restore confirmation form not found", message_key=LETTER_RESTORE_FAILED_KEY)
        _require_write(
            client.post_absolute(confirm.action, data=build_batch_confirm_payload(confirm, RESTORE_ACTION)),
            LETTER_RESTORE_FAILED_KEY,
        )
        return True

    def letter_attachment(self, attachment_id):
        attachment_id = _clean_id(attachment_id)
        client = self.connection._session()
        return client.fetch(LETTERS_ATTACHMENT_PATH.format(attachment=attachment_id))
