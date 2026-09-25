import logging
from datetime import date, timedelta

from . import messages
from .attachments import absence_attachment_url
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
from .iserv.dsa import absence_rules, deregister_options, enabled_absence_types
from .iserv.errors import OUTAGE_KEY
from .iserv.sick_note_pdf import render_sick_note_pdf, sick_note_pdf_filename, sick_note_title
from .mapping import LESSON_MINUTES as LESSON_LENGTH, configured_time, shift_time
from .store import edit_slot

logger = logging.getLogger(__name__)

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


class SickNoteNotFoundError(Exception):
    pass


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


def _request_list_path(kind, target):
    if kind == KIND_LEAVE:
        return LEAVE_PATH
    if kind == KIND_DAYCARE:
        return DAYCARE_LIST_PATH
    return DEREGISTER_LIST_PATHS.get(target)


class AbsenceService:
    def __init__(self, connection):
        self.connection = connection

    def absence_attachment(self, filename):
        return self.connection.pinboard_attachment(filename)

    def absences_overview(self):
        dsa = self.connection._dsa()
        settings = dsa.school_settings()
        config = self.connection.store.load_config()
        periods = dsa.lesson_slots()
        targets = deregister_options(settings)
        return {
            "children": dsa.sick_note_children(),
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

    def report_absence(self, payload, attachments=None):
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
        dsa = self.connection._dsa()
        listed = {
            as_int(item.get("id"))
            for item in dsa.user_requests_or_raise(_request_list_path(kind, payload.get("target"))) or []
            if isinstance(item, dict)
        }
        if as_int(payload.get("id")) not in listed - {None}:
            return messages.result(False, "api.absence.upstream.gone")
        response = dsa.delete_entry(path)
        if response is not None and response.status_code in (200, 202, 204):
            self._forget_absence(payload.get("id"))
            return messages.result(True, "api.absence.withdrawn")
        return _absence_failure(response, "api.absence.upstream.statusWithdraw")

    def sick_note_pdf(self, sick_note_id):
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
