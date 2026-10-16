import logging
import threading
import time
import uuid
from collections import Counter
from datetime import date, timedelta
from urllib.parse import urlencode

from requests import ConnectTimeout, RequestException

from . import messages, modules
from .attachments import absence_attachment_url
from .failure import failure_cause
from .identifiers import UNKNOWN_CHILD_KEY, as_int
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
    LEAVE_PATH,
    REQUESTS_PATH,
    SICK_LOCKED_KEY,
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
from .iserv.dsa import LESSON_FILTER, absence_rules, deregister_options, enabled_absence_types, name_words
from .iserv.errors import OUTAGE_KEY, REASON_DNS, REASON_REFUSED, DataError, transport_reason
from .iserv.older_absence_form import export_path
from .iserv.older_absences import OlderAbsenceShapeError, filter_query, merged_rows, parse_older_absences
from .iserv.sick_note_pdf import render_sick_note_pdf, sick_note_pdf_filename, sick_note_title
from .mapping import LESSON_MINUTES as LESSON_LENGTH, configured_time, shift_time
from .older_absence_actions import LOCKED_KEY as OLDER_LOCKED_KEY, OlderAbsenceActions
from .store import edit_slot

logger = logging.getLogger(__name__)

LESSON_SLOTS_PATH = "timetable-slots/"
LESSON_SLOTS_PARAMS = {"filterBy": LESSON_FILTER}
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
OLDER_SOURCE = "older_page"
OLDER_KIND = "absence"
OLDER_LABEL_KEY = "absence.entry.kind.absence"
SEND_UNCLEAR_KEY = "api.absence.sendUnclear"
WITHDRAW_UNCLEAR_KEY = "api.absence.withdrawUnclear"
WITHDRAW_STILL_LISTED_KEY = "api.absence.older.withdrawUncertain"
ALREADY_SENT_KEY = "api.absence.older.alreadySent"
SEND_MEMORY_SECONDS = 10 * 60
NOT_SENT_REASONS = (REASON_DNS, REASON_REFUSED)
REQUEST_ID_LIMIT = 64
SENT_STATUSES = (200, 201, 204)
SEND_SENDING = "sending"
SEND_SENT = "sent"
SEND_UNCLEAR = "unclear"
ABSENCE_SENT_KEYS = {
    KIND_SICK: "api.absence.sent.sick",
    KIND_LEAVE: "api.absence.sent.leave",
    KIND_DEREGISTER: "api.absence.sent.deregister",
    KIND_DAYCARE: "api.absence.sent.daycare",
}


class SickNoteNotFoundError(Exception):
    pass


def older_identifier(row, child_id):
    if row.entry_id:
        return row.entry_id
    identifier = "%s:%s:%s" % (child_id, row.from_date, row.till_date)
    if row.from_time or row.till_time:
        identifier += ":%s-%s" % (row.from_time, row.till_time)
    return identifier


def older_entry(row, child_id, identifier=None):
    identifier = identifier or older_identifier(row, child_id)
    return {
        "id": "older:%s" % identifier,
        "kind": OLDER_KIND,
        "source": OLDER_SOURCE,
        "target": "",
        "label": messages.text(OLDER_LABEL_KEY),
        "label_key": OLDER_LABEL_KEY,
        "target_key": "",
        "from_date": row.from_date,
        "till_date": row.till_date,
        "from_time": row.from_time,
        "till_time": row.till_time,
        "from_period": None,
        "till_period": None,
        "subject": "",
        "comment": row.reason,
        "student_id": child_id,
        "status": row.status,
        "deletable": bool(row.delete_path),
        "detail": bool(row.detail_path),
        "locked_reason": "" if row.delete_path else messages.text(OLDER_LOCKED_KEY),
        "locked_reason_key": "" if row.delete_path else OLDER_LOCKED_KEY,
        "attachments": [],
        "technical": {
            "id": row.entry_id,
            "created_at": row.created,
            "class_code": row.class_text,
        },
    }


def attach_older_rows(rows, children):
    known = [(str(child.get("child_id") or ""), name_words(child.get("name"))) for child in children or []]
    entries = []
    withheld = 0
    used = Counter()
    for row in rows:
        words = name_words(row.name)
        matches = [child_id for child_id, child_words in known if child_id and words and child_words == words]
        if len(matches) != 1:
            withheld += 1
            continue
        identifier = older_identifier(row, matches[0])
        used[identifier] += 1
        if used[identifier] > 1:
            identifier = "%s:%d" % (identifier, used[identifier])
        entries.append(older_entry(row, matches[0], identifier))
    return entries, withheld


def _absence_failure(response, status_key="api.absence.upstream.statusSubmit"):
    status = getattr(response, "status_code", None)
    if status is None:
        return messages.result(False, "api.absence.upstream.unreachable")
    if status in (400, 422):
        detail = _absence_detail(response)
        if detail:
            return {"ok": False, "message": detail}
        return messages.result(False, "api.absence.upstream.rejected")
    if status == 401:
        return messages.result(False, status_key, {"status": status})
    if status == 403:
        return messages.result(False, "api.absence.upstream.forbidden")
    if status == 404:
        return messages.result(False, "api.absence.upstream.gone")
    if status == 429:
        return messages.result(False, OUTAGE_KEY)
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


def _min_days(settings):
    value = (settings or {}).get(LEAVE_MIN_DAYS_KEY)
    if isinstance(value, bool) or value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _request_id(value):
    text = str(value or "").strip()
    if not text or len(text) > REQUEST_ID_LIMIT or not text.replace("-", "").isalnum():
        return ""
    return text


def _send_target(kind, payload):
    if kind == KIND_DAYCARE:
        return TARGET_AFTERNOON_CARE
    if kind == KIND_DEREGISTER:
        return str(payload.get("deregister_from") or "")
    return ""


def _entry_key(kind, target, entry):
    return (kind, target, entry.get("student_id"), entry.get("from_date"), entry.get("till_date"))


def _send_key(kind, target, request):
    if kind == KIND_SICK:
        return _entry_key(kind, target, normalize_sick_note(request.payload))
    return _entry_key(kind, target, normalize_user_request(request.payload, kind, target))


def _request_list_path(kind, target):
    if kind == KIND_LEAVE:
        return LEAVE_PATH
    if kind == KIND_DAYCARE:
        return DAYCARE_LIST_PATH
    return DEREGISTER_LIST_PATHS.get(target)


class AbsenceService:
    def __init__(self, connection):
        self.connection = connection
        self.older_actions = OlderAbsenceActions(self)
        self._sends = {}
        self._sends_lock = threading.Lock()

    def absence_attachment(self, filename):
        return self.connection.pinboard_attachment(filename)

    def older_source(self):
        return modules.older_absences(modules.registry_of(self.connection))

    def _known_children(self):
        stored = [child for child in self.connection.stored_children() if child.get("name")]
        if stored:
            return stored
        return [child for child in self.connection.children() or [] if isinstance(child, dict) and child.get("name")]

    def _older_filtered(self, client, html, listed):
        pairs = filter_query(html, modules.OLDER_ABSENCE_PATH, date.today())
        if not pairs:
            return listed
        try:
            response = client.fetch_or_raise(modules.OLDER_ABSENCE_PATH + "?" + urlencode(pairs))
            filtered = parse_older_absences(getattr(response, "text", "") or "")
        except (DataError, OlderAbsenceShapeError) as error:
            logger.info("school#%s older absence page: the filtered list was not read, using the default list: %s", self.connection.id, type(error).__name__)
            return listed
        return merged_rows(filtered, listed)

    def older_list(self, client):
        response = client.fetch_or_raise(modules.OLDER_ABSENCE_PATH)
        html = getattr(response, "text", "") or ""
        try:
            listed = parse_older_absences(html)
        except OlderAbsenceShapeError as error:
            raise DataError("older absence page unreadable: %s" % error) from error
        return self._older_filtered(client, html, listed), response

    def owned_rows(self, rows):
        return attach_older_rows(rows, self._known_children())[0]

    def older_overview(self):
        client = self.connection._session()
        listed, page = self.older_list(client)
        children = self._known_children() if listed.rows else []
        entries, withheld = attach_older_rows(listed.rows, children)
        withheld += listed.unreadable
        if withheld:
            logger.info("school#%s older absence page: %d entries not matched to a profile", self.connection.id, withheld)
        entries.extend(self.older_actions.pending_entries(entries, older_entry))
        entries.sort(key=lambda entry: entry.get("from_date") or "", reverse=True)
        config = self.connection.store.load_config()
        return {
            "source": OLDER_SOURCE,
            "export": bool(export_path(getattr(page, "text", "") or "", str(getattr(page, "url", "") or ""))),
            "children": [
                {"id": str(child.get("child_id")), "name": child.get("name") or ""}
                for child in (children or self.connection.stored_children())
                if child.get("child_id")
            ],
            "types": [],
            "deregister_options": [],
            "periods": [],
            "period_labels": [],
            "rules": {},
            "day_options": {"from": [], "till": []},
            "leave_min_days": 0,
            "entries": entries,
            "withheld": withheld,
            "phones": config.get("phones", []),
        }

    def absences_overview(self):
        if self.older_source():
            return self.older_overview()
        dsa = self.connection._dsa()
        settings = dsa.school_settings_or_raise()
        children = dsa.sick_note_children_or_raise()
        config = self.connection.store.load_config()
        periods = dsa.lesson_slots()
        targets = deregister_options(settings)
        return {
            "children": children,
            "types": enabled_absence_types(settings),
            "deregister_options": targets,
            "periods": periods,
            "period_labels": self._period_labels(dsa, periods, config.get("language"), config),
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
                attachment["url"] = absence_attachment_url(attachment.get("file"), self.connection.id)
        self._update_absence_history(entries)
        merged = merge_absence_history(entries, self.connection.store.load_absence_history())
        merged.sort(key=lambda entry: entry.get("from_date") or "", reverse=True)
        return merged

    def _forget_absence(self, entry_id):
        edit_slot(self.connection.store, "absence_history", lambda history: history.pop(str(entry_id), None))

    def _update_absence_history(self, entries):
        def change(history):
            updated = prune_absence_history(record_absence_history(dict(history), entries))
            history.clear()
            history.update(updated)

        edit_slot(self.connection.store, "absence_history", change)

    def _period_labels(self, dsa, periods, language=None, config=None):
        starts = self._slot_times(dsa, "period_times")
        ends = self._slot_end_times(dsa)
        labels = []
        for slot in periods or []:
            number = slot.get("number")
            name = slot.get("name") or messages.text_in(
                language, "common.period.label", {"number": number}
            )
            chosen = configured_time(config, number)
            if chosen:
                start = chosen
                end = ends.get(str(number)) if chosen == starts.get(str(number)) else shift_time(chosen, LESSON_LENGTH)
            else:
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

    def older_absence_form(self):
        if not self.older_source():
            return messages.result(False, ABSENCE_ERROR_FALLBACK_KEY)
        return self.older_actions.form()

    def older_absence_detail(self, entry_id):
        if not self.older_source():
            return messages.result(False, ABSENCE_ERROR_FALLBACK_KEY)
        return self.older_actions.detail(entry_id)

    def older_absence_attachment(self, entry_id, key):
        if not self.older_source():
            raise DataError("the older absence page is not the absences source")
        return self.older_actions.attachment(entry_id, key)

    def delete_older_attachment(self, entry_id, key):
        if not self.older_source():
            return messages.result(False, ABSENCE_ERROR_FALLBACK_KEY)
        return self.older_actions.delete_attachment(entry_id, key)

    def older_absence_export(self):
        if not self.older_source():
            raise DataError("the older absence page is not the absences source")
        return self.older_actions.export()

    def attach_older_absence(self, entry_id, upload):
        if not self.older_source():
            return messages.result(False, ABSENCE_ERROR_FALLBACK_KEY)
        return self.older_actions.attach(entry_id, upload)

    def report_absence(self, payload, attachments=None):
        if self.older_source():
            return self.older_actions.report(payload, attachments)
        kind = payload.get("type")
        dsa = self.connection._dsa()
        periods = dsa.lesson_slots() if kind == KIND_SICK else None
        try:
            request = build_request(
                kind, payload.get("student_id"), payload, periods=periods, attachments=attachments
            )
        except ValueError as error:
            return messages.result(False, ABSENCE_ERROR_KEYS.get(str(error), ABSENCE_ERROR_FALLBACK_KEY))
        offered = {str(child.get("id")) for child in dsa.sick_note_children_or_raise() or [] if isinstance(child, dict)}
        if str(payload.get("student_id")) not in offered:
            return messages.result(False, UNKNOWN_CHILD_KEY)
        return self._send_absence(dsa, request, kind, payload)

    def _send_absence(self, dsa, request, kind, payload):
        key = _send_key(kind, _send_target(kind, payload), request)
        request_id = _request_id(payload.get("request_id")) or uuid.uuid4().hex
        again = payload.get("send_again") is True
        record = None
        with self._sends_lock:
            self._forget_old_sends()
            earlier = self._sends.get(request_id)
            twin = earlier is None and any(entry["key"] == key for entry in self._sends.values())
            if earlier is None and (again or not twin):
                record = {"key": key, "at": time.monotonic(), "state": SEND_SENDING, "before": None}
                self._sends[request_id] = record
        if earlier is not None:
            return self._settle_earlier(dsa, earlier)
        if record is None:
            logger.info("school#%s absence report held back: the same kind, profile and days were sent a moment ago", self.connection.id)
            return messages.result(False, ALREADY_SENT_KEY, already_sent=True)
        record["before"] = self._listed_count(dsa, key)
        if record["before"] and not again:
            self._drop_send(request_id)
            logger.info("school#%s absence report held back: the school already lists the same kind, profile and days", self.connection.id)
            return messages.result(False, ALREADY_SENT_KEY, already_sent=True)
        try:
            response = dsa.send_request(request)
        except RequestException as error:
            if isinstance(error, ConnectTimeout) or transport_reason(error) in NOT_SENT_REASONS:
                self._drop_send(request_id)
                raise
            logger.warning("school#%s absence report outcome unknown: %s", self.connection.id, failure_cause(error))
            return self._verify_send(dsa, record)
        status = getattr(response, "status_code", None)
        if status in SENT_STATUSES:
            return self._sent_result(record)
        if isinstance(status, int) and status >= 500:
            logger.warning("school#%s absence report answered %s, checking the list", self.connection.id, status)
            return self._verify_send(dsa, record)
        self._drop_send(request_id)
        return _absence_failure(response)

    def _forget_old_sends(self):
        cutoff = time.monotonic() - SEND_MEMORY_SECONDS
        for request_id in [key for key, entry in self._sends.items() if entry["at"] < cutoff]:
            self._sends.pop(request_id, None)

    def _drop_send(self, request_id):
        with self._sends_lock:
            self._sends.pop(request_id, None)

    def _sent_result(self, record):
        record["state"] = SEND_SENT
        return messages.result(True, ABSENCE_SENT_KEYS.get(record["key"][0], "api.absence.sent.generic"))

    def _verify_send(self, dsa, record):
        before = record["before"]
        after = self._listed_count(dsa, record["key"])
        if before is not None and after is not None and after > before:
            return self._sent_result(record)
        logger.warning("school#%s absence report not found in the list after an unclear answer", self.connection.id)
        record["state"] = SEND_UNCLEAR
        return messages.result(False, SEND_UNCLEAR_KEY, uncertain=True)

    def _settle_earlier(self, dsa, record):
        if record["state"] == SEND_SENT:
            return self._sent_result(record)
        if record["state"] == SEND_UNCLEAR:
            return self._verify_send(dsa, record)
        return messages.result(False, SEND_UNCLEAR_KEY, uncertain=True)

    def _listed_count(self, dsa, key):
        kind, target, _student, from_date, _till = key
        try:
            if kind == KIND_SICK:
                listed = dsa.sick_notes_or_raise(since=from_date) or []
                rows = [normalize_sick_note(item) for item in listed if isinstance(item, dict)]
            else:
                listed = dsa.user_requests_or_raise(_request_list_path(kind, target)) or []
                rows = [normalize_user_request(item, kind, target) for item in listed if isinstance(item, dict)]
        except (DataError, RequestException) as error:
            logger.info("school#%s absence list not read around a report: %s", self.connection.id, failure_cause(error))
            return None
        return sum(1 for row in rows if _entry_key(kind, target, row) == key)

    def delete_absence(self, payload):
        if self.older_source():
            return self.older_actions.withdraw(payload.get("id"))
        kind = payload.get("type")
        if kind == KIND_SICK:
            return messages.result(False, SICK_LOCKED_KEY)

        try:
            path = delete_path(kind, payload.get("id"), payload.get("target"))
        except ValueError as error:
            return messages.result(False, ABSENCE_ERROR_KEYS.get(str(error), ABSENCE_ERROR_FALLBACK_KEY))
        dsa = self.connection._dsa()
        list_path = _request_list_path(kind, payload.get("target"))
        if as_int(payload.get("id")) not in self._listed_ids(dsa, list_path):
            return messages.result(False, "api.absence.upstream.gone")
        try:
            response = dsa.delete_entry(path)
        except RequestException as error:
            if isinstance(error, ConnectTimeout) or transport_reason(error) in NOT_SENT_REASONS:
                raise
            logger.warning("school#%s absence withdrawal outcome unknown: %s", self.connection.id, failure_cause(error))
            return self._settle_withdrawal(dsa, list_path, payload.get("id"))
        status = getattr(response, "status_code", None)
        if status in (200, 202, 204):
            self._forget_absence(payload.get("id"))
            return messages.result(True, "api.absence.withdrawn")
        if isinstance(status, int) and status >= 500:
            logger.warning("school#%s absence withdrawal answered %s, checking the list", self.connection.id, status)
            return self._settle_withdrawal(dsa, list_path, payload.get("id"))
        return _absence_failure(response, "api.absence.upstream.statusWithdraw")

    def _listed_ids(self, dsa, list_path):
        return {
            as_int(item.get("id"))
            for item in dsa.user_requests_or_raise(list_path) or []
            if isinstance(item, dict)
        } - {None}

    def _settle_withdrawal(self, dsa, list_path, entry_id):
        try:
            listed = self._listed_ids(dsa, list_path)
        except (DataError, RequestException) as error:
            logger.warning("school#%s absence list not read after an unclear withdrawal: %s", self.connection.id, failure_cause(error))
            return messages.result(False, WITHDRAW_UNCLEAR_KEY, uncertain=True)
        if as_int(entry_id) in listed:
            logger.warning("school#%s absence withdrawal unclear and the entry is still listed", self.connection.id)
            return messages.result(False, WITHDRAW_STILL_LISTED_KEY)
        self._forget_absence(entry_id)
        return messages.result(True, "api.absence.withdrawn")

    def sick_note_pdf(self, sick_note_id):
        if self.older_source():
            raise SickNoteNotFoundError("the older absence page has no sick note document")
        try:
            wanted_id = int(str(sick_note_id).strip())
        except (TypeError, ValueError):
            raise SickNoteNotFoundError("invalid sick note id")
        dsa = self.connection._dsa()
        note = next(
            (
                normalize_sick_note(item)
                for item in dsa.sick_notes()
                if as_int(item.get("id")) == wanted_id
            ),
            None,
        )
        if note is None:
            raise SickNoteNotFoundError("sick note not found")
        children = dsa.sick_note_children()
        child = next(
            (c for c in children if as_int(c.get("id")) == note.get("student_id")), None
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
