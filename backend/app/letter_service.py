import logging
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from urllib.parse import urlparse

from requests import RequestException

from . import messages
from .attachments import LETTERS_ATTACHMENT_URL
from .failure import failure_cause
from .iserv.errors import DataError
from .iserv.forms import browser_headers as _browser_headers
from .iserv.forms import find_login_form, parse_forms
from .iserv.html import plain_text
from .iserv.letters import (
    REPLY_ABSENT,
    REPLY_PRESENT,
    REPLY_UNKNOWN,
    RESTORE_ACTION,
    build_archive_payload,
    build_batch_confirm_payload,
    build_confirmation_payload,
    build_choice_payload,
    build_reply_payload,
    choice_recorded,
    confirmation_evidence,
    confirmation_shape,
    answer_form_shape,
    answer_text,
    answered_page_shape,
    confirmation_closed,
    find_answer_edit,
    parse_answer_form,
    picked_options,
    public_choice,
    reply_problem,
    build_hide_payload,
    parse_archive_form,
    parse_batch_confirm,
    page_notices,
    parse_confirmation,
    parse_hide_confirm,
    parse_letter_detail,
    parse_letter_list,
    parse_reply_form,
    reply_form_errors,
    reply_count,
    reply_warnings,
)
from .school_lists import read_school_file
from .sorting import published_sort_key
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
LETTER_CONFIRM_UNCERTAIN_KEY = "api.letters.confirm.uncertain"
LETTER_CONFIRM_CHANGED_KEY = "api.letters.confirm.changed"
LETTER_CONFIRM_NO_CHOICE_KEY = "api.letters.confirm.noChoice"
LETTER_CONFIRM_ANSWERED_KEY = "api.letters.confirm.answered"
LETTER_EDIT_UNAVAILABLE_KEY = "api.letters.edit.unavailable"
LETTER_EDIT_OK_KEY = "api.letters.edit.ok"
ANSWERED_TYPE = "answered"
LETTER_EDIT_UNCHANGED_KEY = "api.letters.edit.unchanged"
LETTER_REPLY_OK_KEY = "api.letters.reply.ok"
LETTER_REPLY_ALREADY_SENT_KEY = "api.letters.reply.alreadySent"
LETTER_REPLY_BUSY_KEY = "api.letters.reply.busy"
LETTER_REPLY_UNCONFIRMED_KEY = "api.letters.reply.unconfirmed"
LETTER_REPLY_EMPTY_KEY = "api.letters.reply.empty"
LETTER_REPLY_INVALID_KEY = "api.letters.reply.invalid"
LETTER_REPLY_UNAVAILABLE_KEY = "api.letters.reply.unavailable"
LETTER_REPLY_UPSTREAM_KEY = "api.letters.reply.upstream"
LETTER_REPLY_REJECTED_KEY = "api.letters.reply.rejected"
LETTER_REPLY_UNCERTAIN_KEY = "api.letters.reply.uncertain"
REPLY_SENT = "sent"
REPLY_UNCERTAIN = "uncertain"
REPLY_KEEP_DAYS = 30
REPLY_KEEP_COUNT = 200
REPLY_LOGGED_LIMIT = 256
REPLY_REQUEST_ID = re.compile(r"^[0-9A-Za-z-]{16,64}$")
LETTER_OPEN_READ = "read"
LETTER_OPEN_BLOCKED = "blocked"
LETTER_OPEN_FAILED = "failed"
LETTER_ARCHIVE_FAILED_KEY = "api.letters.archiveFailed"
LETTER_RESTORE_FAILED_KEY = "api.letters.restoreFailed"
LETTER_UNKNOWN_KEY = "api.letters.unknown"
TAB_CURRENT = "current"
TAB_ARCHIVE = "archive"
LETTER_TABS = (TAB_CURRENT, TAB_ARCHIVE)
ATTACHMENTS_SEEN_LIMIT = 2000
LIST_REREAD_SECONDS = 30
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


def _reply_age_ok(record, cutoff):
    try:
        return datetime.fromisoformat(str(record.get("at") or "")) >= cutoff
    except ValueError:
        return False


def _prune_replies(slot):
    cutoff = datetime.now() - timedelta(days=REPLY_KEEP_DAYS)
    for request_id in list(slot):
        record = slot[request_id]
        if not isinstance(record, dict) or not _reply_age_ok(record, cutoff):
            slot.pop(request_id)
    order = {request_id: index for index, request_id in enumerate(slot)}
    newest = sorted(
        slot, key=lambda request_id: (str(slot[request_id].get("at") or ""), order[request_id]), reverse=True
    )
    for request_id in newest[REPLY_KEEP_COUNT:]:
        slot.pop(request_id)


def _plain(text):
    return " ".join(str(text or "").split())


def _clean_id(value):
    value = (value or "").strip()
    if not SAFE_ID.match(value):
        raise DataError("invalid identifier")
    return value


class LetterService:
    def __init__(self, connection):
        self.connection = connection
        self._confirming = set()
        self._confirming_lock = threading.Lock()
        self._replying = set()
        self._reply_logged = OrderedDict()
        self._listed = {}
        self._listed_lock = threading.Lock()
        self._attachments_seen = OrderedDict()
        self._read_at = {}
        self._read_serial = 0
        self._applied = {}
        self._rereading = {tab: threading.Lock() for tab in LETTER_TABS}
        self.clock = time.monotonic

    def _letter_key(self, entry):
        return f"{entry.get('letter_id')}:{entry.get('recipient_id')}"

    def letters(self, tab="current"):
        tab = TAB_ARCHIVE if tab == TAB_ARCHIVE else TAB_CURRENT
        client = self.connection._session()
        path = LETTERS_ARCHIVE_PATH if tab == TAB_ARCHIVE else LETTERS_INDEX_PATH
        started = self._start_read()
        response = client.fetch_or_raise(path)
        entries = parse_letter_list(response.text, response.url)
        self._remember_listed(tab, entries, started)
        entries.sort(key=lambda item: published_sort_key(item.get("published")), reverse=True)
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

    def _start_read(self):
        with self._listed_lock:
            self._read_serial += 1
            return self._read_serial, self.clock()

    def _remember_listed(self, tab, entries, started):
        serial, stamp = started
        keys = frozenset(self._letter_key(entry) for entry in entries)
        with self._listed_lock:
            if serial <= self._applied.get(tab, 0):
                return
            self._applied[tab] = serial
            self._listed[tab] = keys
            self._read_at[tab] = stamp

    def _read_stamp(self, tab):
        with self._listed_lock:
            return self._read_at.get(tab)

    def _reread(self, tab):
        seen = self._read_stamp(tab)
        with self._rereading[tab]:
            stamp = self._read_stamp(tab)
            if stamp != seen:
                return
            if stamp is not None and self.clock() - stamp < LIST_REREAD_SECONDS:
                return
            self.letters(tab)

    def _listed_keys(self, keys, tabs):
        with self._listed_lock:
            return {key for key in keys if any(key in self._listed.get(tab, ()) for tab in tabs)}

    def _authorised_keys(self, keys, tabs, need_all=True):
        keys = set(keys)
        found = self._listed_keys(keys, tabs)
        for tab in tabs:
            if found == keys or (found and not need_all):
                break
            self._reread(tab)
            found = self._listed_keys(keys, tabs)
        return found

    def _authorised(self, key, tabs):
        return key in self._authorised_keys({key}, tabs)

    def forget_listed(self):
        with self._listed_lock:
            self._listed = {}
            self._read_at = {}
            self._applied = {tab: self._read_serial for tab in LETTER_TABS}
            self._attachments_seen = OrderedDict()

    def _remember_attachments(self, key, attachment_ids):
        with self._listed_lock:
            for attachment_id in attachment_ids:
                letters = self._attachments_seen.pop(attachment_id, frozenset())
                self._attachments_seen[attachment_id] = letters | {key}
            while len(self._attachments_seen) > ATTACHMENTS_SEEN_LIMIT:
                self._attachments_seen.popitem(last=False)

    def _attachment_letters(self, attachment_id):
        with self._listed_lock:
            letters = set(self._attachments_seen.get(attachment_id, ()))
        url = LETTERS_ATTACHMENT_URL.format(attachment=attachment_id, connection=self.connection.id)
        for key, entry in self.connection.store.load_letters_search_cache().items():
            files = entry.get("attachments") if isinstance(entry, dict) else None
            if any(isinstance(item, dict) and item.get("url") == url for item in files or []):
                letters.add(key)
        return letters

    def _attachment_seen(self, attachment_id):
        letters = self._attachment_letters(attachment_id)
        return bool(letters) and bool(self._authorised_keys(letters, LETTER_TABS, need_all=False))

    def _moved(self, key, source, target):
        with self._listed_lock:
            self._applied[source] = self._read_serial
            self._applied[target] = self._read_serial
            self._listed[source] = self._listed.get(source, frozenset()) - {key}
            self._listed[target] = self._listed.get(target, frozenset()) | {key}

    def _refuse_unknown(self, key, tabs):
        if self._authorised(key, tabs):
            return False
        logger.warning("letter action refused: the letter is not in the letter list of this school")
        return True

    def _confirmation_state(self, parsed, record):
        record = record if isinstance(record, dict) else None
        parsed = parsed if isinstance(parsed, dict) else None
        if parsed is None and record is None:
            return None
        kind = (parsed or {}).get("type") or (record or {}).get("type") or ""
        done = record is not None
        state = {
            "type": kind,
            "open": bool(parsed) and not done,
            "done": done,
            "sendable": bool((parsed or {}).get("sendable")),
            "can_reply": bool(
                (parsed or {}).get("can_reply") or (parsed or {}).get("editor") or (parsed or {}).get("text_field")
            ),
            "confirmed_at": (record or {}).get("confirmed_at", ""),
        }
        answer = [str(item) for item in (record or {}).get("answer") or [] if isinstance(item, str)]
        if answer:
            state["answer"] = answer
        return state

    def _cached_confirmation(self, parsed, shape=""):
        if not parsed:
            return None
        cached = {
            "type": parsed.get("type", ""),
            "sendable": bool(parsed.get("sendable")),
            "can_reply": bool(parsed.get("editor") or parsed.get("text_field")),
        }
        if shape:
            cached["shape"] = shape
        return cached

    def _store_confirmation_cache(self, key, parsed, shape=""):
        state = self._cached_confirmation(parsed, shape)

        def change(cache):
            entry = cache.get(key)
            cache[key] = dict(entry if isinstance(entry, dict) else {}, confirmation=state)

        edit_slot(self.connection.store, "letters_search_cache", change)

    def _store_search_entry(self, key, body_html, attachments, parsed, shape=""):
        entry = {
            "body_text": plain_text(body_html),
            "attachments": attachments,
            "confirmation": self._cached_confirmation(parsed, shape),
        }
        def change(cache):
            previous = cache.get(key)
            if isinstance(previous, dict) and previous.get("answer_shape"):
                entry["answer_shape"] = previous["answer_shape"]
            cache[key] = entry

        edit_slot(self.connection.store, "letters_search_cache", change)

    def mark_letters_read(self, keys=None, mark_all=False):
        targets = [str(key) for key in keys or []]
        if mark_all:
            targets = [
                self._letter_key(entry)
                for entry in self.letters("current")["letters"]
                if entry.get("unread")
            ]
        allowed = self._authorised_keys(targets, (TAB_CURRENT,)) if targets else set()
        opened = 0
        blocked = 0
        failed = 0
        for key in targets:
            if key not in allowed:
                logger.warning("a letter was not marked read: it is not in the letter list of this school")
                failed += 1
                continue
            letter_id, _, recipient_id = str(key).partition(":")
            try:
                outcome = self._open_letter(letter_id, recipient_id)
            except DataError as error:
                logger.warning("a letter could not be opened while marking it read: %s", failure_cause(error))
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
        response = self.connection._session().fetch(
            LETTERS_SHOW_PATH.format(letter=letter_id, recipient=recipient_id)
        )
        if getattr(response, "status_code", 0) != 200:
            return LETTER_OPEN_FAILED
        parsed = parse_confirmation(response.text, response.url)
        shape = confirmation_shape(response.text, response.url) if parsed is not None else ""
        self._store_confirmation_cache(f"{letter_id}:{recipient_id}", parsed, shape)
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
        if self._refuse_unknown(f"{letter_id}:{recipient_id}", LETTER_TABS):
            raise DataError("the letter is not listed", message_key=LETTER_UNKNOWN_KEY)
        return self._letter_detail(letter_id, recipient_id)

    def _letter_detail(self, letter_id, recipient_id):
        _, response = self._fetch_letter_page(letter_id, recipient_id)
        detail = parse_letter_detail(response.text, response.url)
        parsed = parse_confirmation(response.text, response.url)
        key = f"{letter_id}:{recipient_id}"
        record = self.connection.store.load_letters_confirmations().get(key)
        attachments = [
            {
                "filename": item.get("filename") or "",
                "url": LETTERS_ATTACHMENT_URL.format(attachment=item.get("attachment_id"), connection=self.connection.id),
            }
            for item in detail.get("attachments", [])
            if item.get("attachment_id")
        ]
        self._remember_attachments(
            key, [str(item.get("attachment_id")) for item in detail.get("attachments", []) if item.get("attachment_id")]
        )
        shape = confirmation_shape(response.text, response.url) if parsed is not None else ""
        self._store_search_entry(key, detail.get("body_html", ""), attachments, parsed, shape)
        reply = None
        if parsed is None:
            reply = self._reply_offer(key, response)
        confirmation = self._confirmation_state(self._cached_confirmation(parsed), record)
        if confirmation is not None and confirmation["open"] and parsed.get("choice"):
            confirmation["choice"] = public_choice(parsed["choice"])
        editable = parsed is None and find_answer_edit(response.text, response.url, letter_id, recipient_id)
        if parsed is None and record is not None and not editable:
            self._store_answer_shape(key, answered_page_shape(response.text, response.url))
        closed = confirmation_closed(response.text) if parsed is None else ""
        if confirmation is None and closed:
            confirmation = {
                "type": closed,
                "open": False,
                "done": True,
                "sendable": False,
                "can_reply": False,
                "confirmed_at": "",
            }
        if editable:
            confirmation = confirmation or {
                "type": ANSWERED_TYPE,
                "open": False,
                "done": True,
                "sendable": False,
                "can_reply": False,
                "confirmed_at": "",
            }
            confirmation["editable"] = True
        return {
            "title": detail.get("title", ""),
            "body_html": detail.get("body_html", ""),
            "attachments": attachments,
            "archive_url_present": bool(detail.get("archive_url")),
            "confirmation": confirmation,
            "confirmation_evidence": confirmation_evidence(response.text) if parsed is not None else None,
            "reply": reply,
        }

    def _reply_offer(self, key, response):
        found = parse_reply_form(response.text, response.url)
        if found["state"] == REPLY_PRESENT:
            return {"available": True}
        with self._confirming_lock:
            if key in self._reply_logged:
                return None
            self._reply_logged[key] = True
            while len(self._reply_logged) > REPLY_LOGGED_LIMIT:
                self._reply_logged.popitem(last=False)
        outline = found["outline"]
        level = logging.WARNING if found["state"] == REPLY_UNKNOWN else logging.INFO
        logger.log(
            level,
            "letter reply form %s: candidates=%d editors=%d textareas=%d submits=%d marked=%d hints=%d",
            found["state"],
            outline["candidates"],
            outline["editors"],
            outline["textareas"],
            outline["submits"],
            outline["marked"],
            outline["hints"],
        )
        return None

    def reply_to_letter(self, letter_id, recipient_id, text, request_id, confirmed=False):
        letter_id = _clean_id(letter_id)
        recipient_id = _clean_id(recipient_id)
        if confirmed is not True:
            return messages.result(False, LETTER_REPLY_UNCONFIRMED_KEY)
        text = text.strip() if isinstance(text, str) else ""
        if not text:
            return messages.result(False, LETTER_REPLY_EMPTY_KEY)
        request_id = request_id if isinstance(request_id, str) else ""
        if not REPLY_REQUEST_ID.match(request_id):
            return messages.result(False, LETTER_REPLY_INVALID_KEY)
        key = f"{letter_id}:{recipient_id}"
        known = self._reply_answer(self.connection.store.load_letters_replies().get(request_id), key)
        if known is not None:
            return known
        with self._confirming_lock:
            if key in self._replying:
                return messages.result(False, LETTER_REPLY_BUSY_KEY)
            self._replying.add(key)
        try:
            if self._refuse_unknown(key, LETTER_TABS):
                return messages.result(False, LETTER_UNKNOWN_KEY)
            return self._reply_to_letter(key, letter_id, recipient_id, text, request_id)
        finally:
            with self._confirming_lock:
                self._replying.discard(key)

    @staticmethod
    def _reply_answer(record, key):
        if not isinstance(record, dict):
            return None
        if record.get("letter") != key:
            return messages.result(False, LETTER_REPLY_INVALID_KEY)
        if record.get("state") == REPLY_SENT:
            return messages.result(True, LETTER_REPLY_ALREADY_SENT_KEY)
        return messages.result(False, LETTER_REPLY_UNCERTAIN_KEY)

    def _claim_reply(self, request_id, key):
        found = {}

        def change(slot):
            record = slot.get(request_id)
            if isinstance(record, dict):
                found["record"] = record
                return
            slot[request_id] = self._reply_record(key, REPLY_UNCERTAIN)
            _prune_replies(slot)

        edit_slot(self.connection.store, "letters_replies", change)
        return self._reply_answer(found.get("record"), key)

    def _settle_reply(self, request_id, key, outcome):
        def change(slot):
            slot.pop(request_id, None)
            if outcome is not None:
                slot[request_id] = self._reply_record(key, outcome)
            _prune_replies(slot)

        edit_slot(self.connection.store, "letters_replies", change)

    @staticmethod
    def _reply_record(key, state):
        return {"letter": key, "state": state, "at": datetime.now().replace(microsecond=0).isoformat()}

    def _reply_to_letter(self, key, letter_id, recipient_id, text, request_id):
        client, response = self._fetch_letter_page(letter_id, recipient_id)
        found = parse_reply_form(response.text, response.url)
        if found["state"] != REPLY_PRESENT:
            logger.warning("letter reply refused before sending: the reply form is %s", found["state"])
            return messages.result(False, LETTER_REPLY_UNAVAILABLE_KEY)
        form = found["form"]
        payload = build_reply_payload(form, text)
        claimed = self._claim_reply(request_id, key)
        if claimed is not None:
            return claimed
        try:
            sent = client.post_absolute(form["action"], data=payload, headers=_browser_headers(response.url))
        except RequestException:
            logger.warning("letter reply outcome unknown: the request to the school failed")
            return messages.result(False, LETTER_REPLY_UNCERTAIN_KEY)
        except Exception:
            self._settle_reply(request_id, key, None)
            raise
        try:
            shown = reply_count(response.text, text)
            outcome, result = self._reply_outcome(sent, lambda: self._reply_read_back(letter_id, recipient_id, text, shown))
            self._settle_reply(request_id, key, outcome)
        except Exception:
            logger.warning("letter reply outcome unknown: the answer of the school could not be read")
            return messages.result(False, LETTER_REPLY_UNCERTAIN_KEY)
        return result

    def _reply_read_back(self, letter_id, recipient_id, text, shown):
        try:
            _, page = self._fetch_letter_page(letter_id, recipient_id)
        except (RequestException, DataError) as error:
            logger.warning("letter reply outcome unknown: the letter was not readable again: %s", failure_cause(error))
            return False
        html = getattr(page, "text", "") or ""
        if find_login_form(parse_forms(html, str(getattr(page, "url", "") or ""))) is not None:
            logger.warning("letter reply outcome unknown: the letter read again is the sign-in page")
            return False
        return reply_count(html, text) > shown

    def _reply_outcome(self, sent, read_back):
        status = int(getattr(sent, "status_code", 0) or 0)
        redirected = bool(getattr(sent, "history", None) or [])
        answer = getattr(sent, "text", "") or ""
        url = str(getattr(sent, "url", "") or "")
        diagnosis = self._reply_diagnosis(sent)
        if not redirected and 400 <= status < 500:
            logger.warning("letter reply refused by the school with status %d", status)
            return None, messages.result(False, LETTER_REPLY_UPSTREAM_KEY, {"status": status}, diagnosis=diagnosis)
        if status not in WRITE_OK_STATUSES:
            logger.warning("letter reply outcome unknown: the school answered with status %d", status)
            return REPLY_UNCERTAIN, messages.result(False, LETTER_REPLY_UNCERTAIN_KEY, diagnosis=diagnosis)
        signed_out = find_login_form(parse_forms(answer, url)) is not None
        errors = reply_form_errors(answer) > 0
        if signed_out or (errors and not redirected):
            logger.warning("letter reply refused by the school form")
            return None, messages.result(False, LETTER_REPLY_REJECTED_KEY, diagnosis=diagnosis)
        shown_again = not redirected and parse_reply_form(answer, url)["state"] != REPLY_ABSENT
        if errors or shown_again:
            logger.warning("letter reply outcome unknown: the school showed the page again")
            return REPLY_UNCERTAIN, messages.result(False, LETTER_REPLY_UNCERTAIN_KEY, diagnosis=diagnosis)
        if reply_warnings(answer):
            logger.warning("letter reply outcome unknown: the school answered with a warning")
            return REPLY_UNCERTAIN, messages.result(False, LETTER_REPLY_UNCERTAIN_KEY, diagnosis=diagnosis)
        if not read_back():
            logger.warning("letter reply outcome unknown: the letter read again does not show the reply")
            return REPLY_UNCERTAIN, messages.result(False, LETTER_REPLY_UNCERTAIN_KEY, diagnosis=diagnosis)
        logger.info("letter reply sent and read back")
        return REPLY_SENT, messages.result(True, LETTER_REPLY_OK_KEY)

    @staticmethod
    def _reply_diagnosis(sent):
        return {
            "post_status": getattr(sent, "status_code", 0),
            "post_path": urlparse(str(getattr(sent, "url", "") or "")).path,
            "post_redirects": len(getattr(sent, "history", None) or []),
            "response_notices": page_notices(getattr(sent, "text", "") or ""),
        }

    def answer_form(self, letter_id, recipient_id):
        letter_id = _clean_id(letter_id)
        recipient_id = _clean_id(recipient_id)
        key = f"{letter_id}:{recipient_id}"
        if self._refuse_unknown(key, LETTER_TABS):
            raise DataError("the letter is not listed", message_key=LETTER_UNKNOWN_KEY)
        _, page, parsed = self._answer_page(key, letter_id, recipient_id)
        if page is None:
            return messages.result(False, LETTER_EDIT_UNAVAILABLE_KEY)
        if parsed is None or not parsed.get("sendable"):
            return messages.result(False, LETTER_CONFIRM_UNSUPPORTED_KEY)
        return {
            "ok": True,
            "choice": public_choice(parsed.get("choice")),
            "can_reply": bool(parsed.get("editor") or parsed.get("text_field")),
            "text": answer_text(parsed),
        }

    def _answer_page(self, key, letter_id, recipient_id):
        client, response = self._fetch_letter_page(letter_id, recipient_id)
        edit_url = find_answer_edit(response.text, response.url, letter_id, recipient_id)
        if not edit_url:
            logger.warning("letter answer cannot be changed: the letter offers no edit link")
            return client, None, None
        page = client.fetch_or_raise(edit_url)
        parsed = parse_answer_form(page.text, page.url, letter_id, recipient_id)
        if parsed is None or not parsed.get("sendable"):
            shape = answer_form_shape(page.text, page.url, letter_id, recipient_id)
            logger.warning("letter answer cannot be changed: the edit form is not recognised")
            self._store_answer_shape(key, shape)
        return client, page, parsed

    def _store_answer_shape(self, key, shape):
        def change(cache):
            entry = cache.get(key)
            cache[key] = dict(entry if isinstance(entry, dict) else {}, answer_shape=shape)

        edit_slot(self.connection.store, "letters_search_cache", change)

    def edit_answer(self, letter_id, recipient_id, text=None, choices=None):
        letter_id = _clean_id(letter_id)
        recipient_id = _clean_id(recipient_id)
        key = f"{letter_id}:{recipient_id}"
        with self._confirming_lock:
            if key in self._confirming:
                return messages.result(False, LETTER_CONFIRM_BUSY_KEY)
            self._confirming.add(key)
        try:
            if self._refuse_unknown(key, LETTER_TABS):
                return messages.result(False, LETTER_UNKNOWN_KEY)
            return self._edit_answer(key, letter_id, recipient_id, text, choices)
        finally:
            with self._confirming_lock:
                self._confirming.discard(key)

    def _edit_answer(self, key, letter_id, recipient_id, text, choices):
        client, page, parsed = self._answer_page(key, letter_id, recipient_id)
        if page is None:
            return messages.result(False, LETTER_EDIT_UNAVAILABLE_KEY)
        if parsed is None or not parsed.get("sendable"):
            return messages.result(False, LETTER_CONFIRM_UNSUPPORTED_KEY)
        has_text = bool(parsed.get("editor") or parsed.get("text_field"))
        if text and not has_text:
            return messages.result(False, LETTER_CONFIRM_NO_MESSAGE_FIELD_KEY)
        prepared, refusal = self._confirm_payload(parsed, text, choices)
        if refusal is not None:
            return refusal
        payload, picked = prepared
        if not self._edit_changes(parsed, picked, text if has_text else None):
            logger.info("letter answer change refused before sending: it changes nothing")
            return messages.result(False, LETTER_EDIT_UNCHANGED_KEY)
        try:
            sent = client.post_absolute(parsed["action"], data=payload, headers=_browser_headers(page.url))
        except RequestException:
            logger.warning("letter answer change outcome unknown: the request failed, reading the answer again")
            sent = None
        status = getattr(sent, "status_code", 0) if sent is not None else 0
        if sent is not None and status not in WRITE_OK_STATUSES:
            logger.warning("letter answer change refused by the school with status %d", status)
            return messages.result(
                False, LETTER_CONFIRM_UPSTREAM_KEY, {"status": status}, diagnosis=self._confirm_diagnosis(sent, None)
            )
        return self._edit_read_back(key, letter_id, recipient_id, parsed, picked, text, sent)

    def _edit_read_back(self, key, letter_id, recipient_id, parsed, picked, text, sent):
        try:
            _, page, after = self._answer_page(key, letter_id, recipient_id)
        except (RequestException, DataError) as error:
            logger.warning("letter answer change outcome unknown: the answer was not readable: %s", failure_cause(error))
            return messages.result(False, LETTER_CONFIRM_UNCERTAIN_KEY)
        if page is None or after is None:
            return messages.result(False, LETTER_CONFIRM_UNCERTAIN_KEY, diagnosis=self._confirm_diagnosis(sent, None))
        checks = [sent is not None and not reply_problem(getattr(sent, "text", ""), str(getattr(sent, "url", "") or ""))]
        if picked and not choice_recorded(parsed, picked):
            checks.append(choice_recorded(after, picked))
        if text is not None and _plain(text) != _plain(answer_text(parsed)):
            checks.append(bool(after.get("editor") or after.get("text_field")) and _plain(answer_text(after)) == _plain(text))
        if len(checks) < 2 or not all(checks):
            logger.warning("letter answer change not confirmed by the school")
            return messages.result(False, LETTER_CONFIRM_UNCERTAIN_KEY, diagnosis=self._confirm_diagnosis(sent, page))
        stamp = datetime.now().replace(microsecond=0).isoformat()
        previous = self.connection.store.load_letters_confirmations().get(key)
        record = dict(previous if isinstance(previous, dict) else {"type": ANSWERED_TYPE}, confirmed_at=stamp)
        answer = [option["label"] for option in picked or []]
        if answer:
            record["answer"] = answer
        edit_slot(self.connection.store, "letters_confirmations", lambda current: current.update({key: record}))
        logger.info("letter answer changed and read back")
        return messages.result(True, LETTER_EDIT_OK_KEY, confirmed_at=stamp, answer=answer)

    def confirm_letter(self, letter_id, recipient_id, text=None, choices=None):
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
            if self._refuse_unknown(key, LETTER_TABS):
                return messages.result(False, LETTER_UNKNOWN_KEY)
            return self._confirm_letter(letter_id, recipient_id, key, text, choices)
        finally:
            with self._confirming_lock:
                self._confirming.discard(key)

    def _confirm_payload(self, parsed, text, choices):
        choice = parsed.get("choice")
        if not choice:
            if choices:
                logger.warning("letter answer refused before sending: the letter no longer offers a choice")
                return None, messages.result(False, LETTER_CONFIRM_CHANGED_KEY)
            return (build_confirmation_payload(parsed, text), None), None
        if not choices:
            return None, messages.result(False, LETTER_CONFIRM_NO_CHOICE_KEY)
        picked = picked_options(choice, choices)
        if picked is None:
            logger.warning("letter answer refused before sending: the choice no longer matches the form")
            return None, messages.result(False, LETTER_CONFIRM_CHANGED_KEY)
        return (build_choice_payload(parsed, picked, text), picked), None

    def _confirm_letter(self, letter_id, recipient_id, key, text, choices):
        client, response = self._fetch_letter_page(letter_id, recipient_id)
        parsed = parse_confirmation(response.text, response.url)
        if parsed is None:
            self._store_confirmation_cache(key, None)
            return messages.result(False, LETTER_CONFIRM_GONE_KEY)
        if not parsed.get("sendable"):
            logger.warning("letter confirmation refused before sending: the form is not recognised")
            return messages.result(False, LETTER_CONFIRM_UNSUPPORTED_KEY)
        if text and not (parsed.get("editor") or parsed.get("text_field")):
            return messages.result(False, LETTER_CONFIRM_NO_MESSAGE_FIELD_KEY)
        prepared, refusal = self._confirm_payload(parsed, text, choices)
        if refusal is not None:
            return refusal
        payload, picked = prepared
        sent = None
        try:
            sent = client.post_absolute(parsed["action"], data=payload, headers=_browser_headers(response.url))
        except RequestException:
            logger.warning("letter confirmation outcome unknown: the request failed, reading the letter again")
        status = getattr(sent, "status_code", 0) if sent is not None else 0
        if sent is not None and status not in WRITE_OK_STATUSES:
            logger.warning("letter confirmation refused by the school with status %d", status)
            return messages.result(
                False,
                LETTER_CONFIRM_UPSTREAM_KEY,
                {"status": status},
                diagnosis=self._confirm_diagnosis(sent, None),
            )
        return self._confirm_read_back(key, letter_id, recipient_id, parsed, picked, text, sent)

    def _confirm_read_back(self, key, letter_id, recipient_id, parsed, picked, text, sent):
        try:
            _, verify = self._fetch_letter_page(letter_id, recipient_id)
            after = parse_confirmation(verify.text, verify.url)
        except (RequestException, DataError) as error:
            logger.warning("letter confirmation outcome unknown: the letter was not readable: %s", failure_cause(error))
            return messages.result(False, LETTER_CONFIRM_UNCERTAIN_KEY, diagnosis=self._confirm_diagnosis(sent, None))
        problem = sent is not None and reply_problem(getattr(sent, "text", ""), str(getattr(sent, "url", "") or ""))
        shown = bool(picked) and choice_recorded(after, picked)
        proven = after is None or (shown and not choice_recorded(parsed, picked))
        if problem or not proven:
            diagnosis = self._confirm_diagnosis(sent, verify)
            if after is not None:
                self._store_confirmation_cache(key, after, confirmation_shape(verify.text, verify.url))
            if self._confirm_refused(parsed, after, picked, text, shown):
                logger.warning("letter confirmation not taken over: the letter still asks for it")
                return messages.result(False, LETTER_CONFIRM_REJECTED_KEY, diagnosis=diagnosis)
            logger.warning("letter confirmation outcome unknown: the answer of the school does not prove it")
            return messages.result(False, LETTER_CONFIRM_UNCERTAIN_KEY, diagnosis=diagnosis)
        stamp = datetime.now().replace(microsecond=0).isoformat()
        record = {"type": parsed.get("type", ""), "confirmed_at": stamp}
        answer = [option["label"] for option in picked or []]
        if answer:
            record["answer"] = answer
        edit_slot(self.connection.store, "letters_confirmations", lambda current: current.update({key: record}))
        self._store_confirmation_cache(key, None)
        logger.info("letter confirmation sent and read back")
        if answer:
            return messages.result(True, LETTER_CONFIRM_ANSWERED_KEY, confirmed_at=stamp, answer=answer)
        return messages.result(True, LETTER_CONFIRM_OK_KEY, confirmed_at=stamp)

    def _confirm_refused(self, parsed, after, picked, text, shown):
        if after is None or shown or text:
            return False
        choice = parsed.get("choice")
        if not choice:
            return True
        return choice["mode"] != "submit" and self._same_choice(choice, after.get("choice"))

    @staticmethod
    def _edit_changes(parsed, picked, text):
        if picked and not choice_recorded(parsed, picked):
            return True
        return text is not None and _plain(text) != _plain(answer_text(parsed))

    @staticmethod
    def _same_choice(before, after):
        if not after:
            return False
        return [option["id"] for option in before["options"]] == [option["id"] for option in after["options"]]

    @staticmethod
    def _confirm_diagnosis(sent, verify):
        diagnosis = {
            "post_status": getattr(sent, "status_code", 0) if sent is not None else 0,
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
        key = f"{letter_id}:{recipient_id}"
        if self._refuse_unknown(key, (TAB_CURRENT,)):
            raise DataError("the letter is not listed", message_key=LETTER_UNKNOWN_KEY)
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
        self._require_signed_in(
            _require_write(client.post_absolute(form.action, data=build_hide_payload(form)), LETTER_ARCHIVE_FAILED_KEY),
            LETTER_ARCHIVE_FAILED_KEY,
        )
        self._require_listed(client, key, LETTERS_INDEX_PATH, False, LETTER_ARCHIVE_FAILED_KEY)
        self._moved(key, TAB_CURRENT, TAB_ARCHIVE)
        return True

    @staticmethod
    def _require_signed_in(response, message_key):
        html = getattr(response, "text", "") or ""
        if find_login_form(parse_forms(html, str(getattr(response, "url", "") or ""))) is not None:
            logger.warning("letter move outcome unknown: the school answered with the sign-in page")
            raise DataError("the school asked to sign in again", message_key=message_key, detail={"state": "signed_out"})
        return response

    def _require_listed(self, client, key, path, wanted, message_key):
        try:
            response = client.fetch_or_raise(path)
        except (RequestException, DataError) as error:
            logger.warning("letter move outcome unknown: the list was not readable again: %s", failure_cause(error))
            raise DataError("the letter list was not readable again", message_key=message_key, detail={"state": "uncertain"}) from error
        self._require_signed_in(response, message_key)
        listed = {self._letter_key(entry) for entry in parse_letter_list(response.text, response.url)}
        if (key in listed) != wanted:
            logger.warning("letter move not confirmed: the list read again does not show the change")
            raise DataError("the letter list does not show the change", message_key=message_key, detail={"state": "uncertain"})

    def restore_letter(self, letter_id, recipient_id):
        letter_id = _clean_id(letter_id)
        recipient_id = _clean_id(recipient_id)
        key = f"{letter_id}:{recipient_id}"
        if self._refuse_unknown(key, (TAB_ARCHIVE,)):
            raise DataError("the letter is not listed", message_key=LETTER_UNKNOWN_KEY)
        client = self.connection._session()
        response = client.fetch_or_raise(LETTERS_ARCHIVE_PATH)
        form = parse_archive_form(response.text, response.url, RESTORE_ACTION)
        if form is None:
            raise DataError("restore action not available", message_key=LETTER_RESTORE_FAILED_KEY)
        payload = build_archive_payload(form, [f"{letter_id}-{recipient_id}"], RESTORE_ACTION)
        staged = _require_write(
            client.post_absolute(form["action"], data=payload), LETTER_RESTORE_FAILED_KEY
        )
        confirm = parse_batch_confirm(self._require_signed_in(staged, LETTER_RESTORE_FAILED_KEY).text, staged.url)
        if confirm is None:
            raise DataError("restore confirmation form not found", message_key=LETTER_RESTORE_FAILED_KEY)
        self._require_signed_in(
            _require_write(
                client.post_absolute(confirm.action, data=build_batch_confirm_payload(confirm, RESTORE_ACTION)),
                LETTER_RESTORE_FAILED_KEY,
            ),
            LETTER_RESTORE_FAILED_KEY,
        )
        self._require_listed(client, key, LETTERS_INDEX_PATH, True, LETTER_RESTORE_FAILED_KEY)
        self._moved(key, TAB_ARCHIVE, TAB_CURRENT)
        return True

    def letter_attachment(self, attachment_id):
        attachment_id = _clean_id(attachment_id)
        if not self._attachment_seen(attachment_id):
            logger.warning("letter attachment refused: it was not seen in a letter of this school")
            raise DataError("the attachment is not listed", message_key=LETTER_UNKNOWN_KEY)
        client = self.connection._session()
        return read_school_file(client, LETTERS_ATTACHMENT_PATH.format(attachment=attachment_id), self.connection._school_url())
