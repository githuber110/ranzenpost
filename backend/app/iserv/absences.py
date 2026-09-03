import json
from datetime import date, datetime, time, timedelta, timezone

from .. import messages
from .html import clean_html

KIND_SICK = "sick"
KIND_LEAVE = "leave"
KIND_DEREGISTER = "deregister"
KIND_DAYCARE = "daycare"
KINDS = (KIND_SICK, KIND_LEAVE, KIND_DEREGISTER, KIND_DAYCARE)

KIND_LABELS = {
    KIND_SICK: messages.text("absence.entry.kind.sick"),
    KIND_LEAVE: messages.text("absence.entry.kind.leave"),
    KIND_DEREGISTER: messages.text("absence.entry.kind.deregister"),
    KIND_DAYCARE: messages.text("absence.entry.kind.daycare"),
}

SICK_NOTES_PATH = "sickNotes/"
REQUESTS_PATH = "user-requests-to-school/"

DAY_TODAY = "today"
DAY_TOMORROW = "tomorrow"

TARGET_BUS = "bus"
TARGET_LUNCH = "lunch"
TARGET_KINDERGARTEN = "kindergarten"
TARGET_AFTERNOON_CARE = "afternoon-care"
DEREGISTER_TARGETS = (TARGET_BUS, TARGET_KINDERGARTEN, TARGET_LUNCH)

TARGET_LABELS = {
    TARGET_BUS: messages.text("absence.target.bus"),
    TARGET_LUNCH: messages.text("absence.target.lunch"),
    TARGET_KINDERGARTEN: messages.text("absence.target.kindergarten"),
    TARGET_AFTERNOON_CARE: messages.text("absence.target.afternoonCare"),
}

REQUEST_TYPES = {
    TARGET_BUS: "not-attend-bus",
    TARGET_LUNCH: "not-attend-lunch",
    TARGET_KINDERGARTEN: "not-attend-kindergarten",
    TARGET_AFTERNOON_CARE: "not-attend-afternoon-care",
}
LEAVE_TYPE = "student-absence"
LEAVE_PATH = REQUESTS_PATH + "student-absences/"

DAYCARE_DEREGISTER = "deregister"
DAYCARE_EARLY_END = "early_end"
DAYCARE_KINDS = (DAYCARE_DEREGISTER, DAYCARE_EARLY_END)

REPEAT_ONCE = "once"
REPEAT_WEEKLY = "weekly"
REPEATS = (REPEAT_ONCE, REPEAT_WEEKLY)

BODY_JSON = "json"
BODY_FORM = "form"
NO_DEFAULT_CONTENT_TYPE = {"X-Do-Not-Set-Default-Content-Type": "true"}

ATTACHMENT_FIELD_NAME = "file[]"

WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
DAY_OPTION_KEYS = {0: "absence.day.today", 1: "absence.day.tomorrow"}

ERROR_UNKNOWN_KIND = "unknown absence kind"
ERROR_STUDENT = "missing student"
ERROR_IDENTIFIER = "missing identifier"
ERROR_SUBJECT = "missing subject"
ERROR_BODY = "missing body"
ERROR_DEREGISTER_TARGET = "invalid deregister target"
ERROR_DAYCARE_KIND = "unknown daycare kind"
ERROR_REPEAT = "unknown repeat"
ERROR_DATE = "missing date"
ERROR_PICKUP_TIME = "missing pickup time"
ERROR_RANGE = "till before from"
ERROR_SICK_LOCKED = "sick note cannot be withdrawn"

SICK_LOCKED_KEY = "api.absence.lockedSick"
SICK_LOCKED = messages.text(SICK_LOCKED_KEY)

HISTORY_MAX_AGE_DAYS = 30

HISTORY_LOCKED_KEY = "api.absence.lockedHistory"
HISTORY_LOCKED = messages.text(HISTORY_LOCKED_KEY)

KIND_LABEL_KEYS = {
    KIND_SICK: "absence.entry.kind.sick",
    KIND_LEAVE: "absence.entry.kind.leave",
    KIND_DEREGISTER: "absence.entry.kind.deregister",
    KIND_DAYCARE: "absence.entry.kind.daycare",
}

TARGET_LABEL_KEYS = {
    TARGET_BUS: "absence.target.bus",
    TARGET_LUNCH: "absence.target.lunch",
    TARGET_KINDERGARTEN: "absence.target.kindergarten",
    TARGET_AFTERNOON_CARE: "absence.target.afternoonCare",
}

class Request:
    def __init__(self, path, body_mode, payload, headers=None, attachments=None):
        self.path = path
        self.body_mode = body_mode
        self.payload = payload
        self.headers = dict(headers or {})
        self.attachments = list(attachments or [])

    def __eq__(self, other):
        return (
            isinstance(other, Request)
            and self.path == other.path
            and self.body_mode == other.body_mode
            and self.payload == other.payload
            and self.headers == other.headers
            and self.attachments == other.attachments
        )

    def __repr__(self):
        return f"Request({self.path!r}, {self.body_mode!r}, {self.payload!r})"


def resolve_day(value, today=None):
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    today = today or date.today()
    key = text.lower()
    if key == DAY_TODAY:
        return today.isoformat()
    if key == DAY_TOMORROW:
        return (today + timedelta(days=1)).isoformat()
    return text


def sick_day_options(today=None):
    today = today or date.today()
    starts = [_day_option(today, 0), _day_option(today, 1)]
    ends = [_day_option(today, offset) for offset in range(0, 6)]
    return {"from": starts, "till": ends}


def _day_option(today, offset):
    day = today + timedelta(days=offset)
    key = DAY_OPTION_KEYS.get(offset, "")
    label = messages.text(key) if key else f"{WEEKDAYS[day.weekday()]}, {day.strftime('%d.%m.')}"
    return {"value": day.isoformat(), "label": label, "label_key": key}


def build_request(kind, student_id, data, today=None, periods=None, attachments=None):
    if kind not in KINDS:
        raise ValueError(f"{ERROR_UNKNOWN_KIND}: {kind}")
    student = _as_int(student_id)
    if student is None:
        raise ValueError(ERROR_STUDENT)
    data = data or {}
    if kind == KIND_SICK:
        return _sick_request(student, data, today, periods)
    if kind == KIND_LEAVE:
        return _leave_request(student, data, today, attachments)
    if kind == KIND_DEREGISTER:
        return _deregister_request(student, data, today)
    return _daycare_request(student, data, today)


def delete_path(kind, entry_id, target=None):
    if kind not in KINDS:
        raise ValueError(f"{ERROR_UNKNOWN_KIND}: {kind}")
    identifier = _as_int(entry_id)
    if identifier is None:
        raise ValueError(ERROR_IDENTIFIER)
    if kind == KIND_SICK:
        raise ValueError(ERROR_SICK_LOCKED)
    if kind == KIND_LEAVE:
        return f"{LEAVE_PATH}{identifier}"
    if kind == KIND_DAYCARE:
        return f"{REQUESTS_PATH}not-attend/{TARGET_AFTERNOON_CARE}/{identifier}"
    if target not in DEREGISTER_TARGETS:
        raise ValueError(ERROR_DEREGISTER_TARGET)
    return f"{REQUESTS_PATH}not-attend/{target}/{identifier}"


def normalize_sick_note(raw):
    raw = raw or {}
    sick_user = raw.get("sickUser")
    sick_user = sick_user if isinstance(sick_user, dict) else {}
    reporter = raw.get("reporter") or {}
    return {
        "id": raw.get("id"),
        "kind": KIND_SICK,
        "target": "",
        "label": KIND_LABELS[KIND_SICK],
        "label_key": KIND_LABEL_KEYS[KIND_SICK],
        "target_key": "",
        "from_date": _date_part(_first(raw, "sickFromDateAsString", "sickFromDate")),
        "till_date": _date_part(_first(raw, "sickTillDateAsString", "sickTillDate")),
        "from_period": raw.get("sickFromLessonNumber"),
        "till_period": raw.get("sickTillLessonNumber"),
        "comment": _first(raw, "note", "textnote"),
        "duty_to_report": bool(raw.get("isDutyToReport")),
        "student_id": _as_int(_first(raw, "sickUser", "student")),
        "status": "",
        "deletable": False,
        "locked_reason": SICK_LOCKED,
        "locked_reason_key": SICK_LOCKED_KEY,
        "technical": {
            "id": raw.get("id"),
            "created_at": raw.get("createdAt"),
            "reporter": str(reporter.get("displayname") or "").strip(),
            "duty_to_report": bool(raw.get("isDutyToReport")),
            "class_code": (sick_user.get("mainCourse") or {}).get("externalId") or "",
            "has_written_confirmation": bool(raw.get("hasWrittenConfirmation")),
            "needs_official_confirmation": bool(raw.get("needsOfficialConfirmation")),
            "has_official_confirmation": bool(raw.get("hasOfficialConfirmation")),
            "counted_in_statistics": bool(raw.get("isCountedAsAnAbsenceInStatistics")),
        },
    }


def _parse_request_attachments(items):
    result = []
    for item in items or []:
        result.append(
            {
                "id": item.get("id"),
                "filename": item.get("originalFilename") or item.get("filename") or "",
                "extension": item.get("extension") or "",
                "mimetype": item.get("mimetype") or "",
                "size": item.get("size") or 0,
                "file": item.get("filename") or "",
            }
        )
    return result


def normalize_user_request(raw, kind, target=""):
    raw = raw or {}
    accepted = raw.get("accepted")
    label = KIND_LABELS.get(kind, "")
    if target:
        label = f"{label} {TARGET_LABELS.get(target, target)}".strip()
    author = raw.get("author")
    author = author if isinstance(author, dict) else {}
    response_author = raw.get("responseAuthor")
    response_author = response_author if isinstance(response_author, dict) else {}
    return {
        "id": raw.get("id"),
        "kind": kind,
        "target": target,
        "label": label,
        "label_key": KIND_LABEL_KEYS.get(kind, ""),
        "target_key": TARGET_LABEL_KEYS.get(target, "") if target else "",
        "created_at": _date_part(_first(raw, "createdAt")),
        "from_date": _date_part(_first(raw, "absentDate", "absentFrom")),
        "till_date": _date_part(_first(raw, "absentUntil", "absentDate")),
        "subject": _first(raw, "topic"),
        "body": clean_html(_first(raw, "requestDescriptionHtml")),
        "comment": _first(raw, "note"),
        "pickup_time": _first(raw, "pickupTime"),
        "weekly": bool(raw.get("repeatWeekly")),
        "repeat_until": _date_part(_first(raw, "repeatWeeklyUntil")),
        "answer": clean_html(_first(raw, "responseDescriptionHtml")),
        "student_id": _as_int(raw.get("student")),
        "status": "open" if accepted is None else ("accepted" if accepted else "rejected"),
        "deletable": True,
        "locked_reason": "",
        "locked_reason_key": "",
        "attachments": _parse_request_attachments(raw.get("staticFiles")),
        "technical": {
            "id": raw.get("id"),
            "created_at": raw.get("createdAt"),
            "updated_at": raw.get("updatedAt"),
            "author": str(author.get("displayname") or "").strip(),
            "response_author": str(response_author.get("displayname") or "").strip(),
        },
    }


def seed_absence_history(history, entry):
    history = dict(history or {})
    entry_id = entry.get("id")
    if entry_id is None:
        return history
    history.setdefault(str(entry_id), dict(entry))
    return history


def record_absence_history(history, entries, seen_at=None):
    seen_at = seen_at or datetime.now(timezone.utc).isoformat()
    history = dict(history or {})
    for entry in entries or []:
        entry_id = entry.get("id")
        if entry_id is None:
            continue
        record = dict(entry)
        record["seen_at"] = seen_at
        history[str(entry_id)] = record
    return history


def prune_absence_history(history, today=None, max_age_days=HISTORY_MAX_AGE_DAYS):
    today = today or date.today()
    pruned = {}
    for key, record in (history or {}).items():
        age_date = _date_value(record.get("till_date") or record.get("from_date"))
        if age_date is None:
            continue
        if (today - age_date).days <= max_age_days:
            pruned[key] = record
    return pruned


def merge_absence_history(live_entries, history, today=None, max_age_days=HISTORY_MAX_AGE_DAYS):
    today = today or date.today()
    live_ids = {str(entry.get("id")) for entry in live_entries or [] if entry.get("id") is not None}
    merged = list(live_entries or [])
    for key, record in (history or {}).items():
        if key in live_ids:
            continue
        age_date = _date_value(record.get("till_date") or record.get("from_date"))
        if age_date is None or (today - age_date).days > max_age_days:
            continue
        historic = dict(record)
        historic.pop("seen_at", None)
        historic["from_history"] = True
        historic["deletable"] = False
        historic["locked_reason"] = HISTORY_LOCKED
        historic["locked_reason_key"] = HISTORY_LOCKED_KEY
        merged.append(historic)
    return merged


def _sick_request(student, data, today, periods=None):
    from_date = resolve_day(data.get("day_from"), today)
    till_date = resolve_day(data.get("day_till"), today) or from_date
    if not from_date:
        raise ValueError(ERROR_DATE)
    if till_date < from_date:
        raise ValueError(ERROR_RANGE)
    payload = {
        "sickUser": student,
        "sickFromDate": from_date,
        "sickTillDate": till_date,
        "isDutyToReport": bool(data.get("duty_to_report")),
    }
    comment = _text(data.get("comment"))
    if comment:
        payload["note"] = comment
    from_period = _as_int(data.get("from_period"))
    till_period = _as_int(data.get("till_period"))
    if from_period is None and till_period is None:
        last_period = _max_period(periods)
        if last_period is not None:
            from_period = 1
            till_period = last_period
    if from_period is not None:
        payload["sickFromLessonNumber"] = from_period
    if till_period is not None:
        payload["sickTillLessonNumber"] = till_period
    return Request(SICK_NOTES_PATH, BODY_JSON, payload)


def _max_period(periods):
    numbers = [_as_int(slot.get("number")) for slot in periods or [] if isinstance(slot, dict)]
    numbers = [number for number in numbers if number is not None]
    return max(numbers) if numbers else None


def _leave_request(student, data, today, attachments=None):
    subject = _text(data.get("subject"))
    if not subject:
        raise ValueError(ERROR_SUBJECT)
    body = _text(data.get("body"))
    if not body:
        raise ValueError(ERROR_BODY)
    from_date = _date_value(data.get("from_date"), today)
    till_date = _date_value(data.get("till_date"), today) or from_date
    if from_date is None:
        raise ValueError(ERROR_DATE)
    start = _epoch(from_date, _time_value(data.get("from_time"), time(8, 0)))
    end = _epoch(till_date, _time_value(data.get("till_time"), time(14, 0)))
    if end < start:
        raise ValueError(ERROR_RANGE)
    payload = {
        "type": LEAVE_TYPE,
        "student": {"id": student},
        "topic": subject,
        "requestDescriptionHtml": _html(body),
        "absentFrom": start,
        "absentUntil": end,
        "repeatWeekly": bool(data.get("weekly")),
        "repeatWeeklyUntil": _repeat_until(data, today),
    }
    return Request(LEAVE_PATH, BODY_FORM, payload, NO_DEFAULT_CONTENT_TYPE, attachments=attachments)


def _deregister_request(student, data, today):
    target = _text(data.get("deregister_from"))
    if target not in DEREGISTER_TARGETS:
        raise ValueError(ERROR_DEREGISTER_TARGET)
    day = _date_value(data.get("date"), today)
    if day is None:
        raise ValueError(ERROR_DATE)
    payload = {
        "student": {"id": student},
        "type": REQUEST_TYPES[target],
        "topic": "",
        "requestDescriptionHtml": "",
        "absentDate": _iso_utc(day),
        "repeatWeekly": bool(data.get("weekly")),
        "repeatWeeklyUntil": _repeat_until(data, today),
    }
    return Request(
        f"{REQUESTS_PATH}not-attend/{target}/", BODY_FORM, payload, NO_DEFAULT_CONTENT_TYPE
    )


def _daycare_request(student, data, today):
    daycare_kind = _text(data.get("daycare_kind"))
    if daycare_kind not in DAYCARE_KINDS:
        raise ValueError(ERROR_DAYCARE_KIND)
    repeat = _text(data.get("repeat")) or REPEAT_ONCE
    if repeat not in REPEATS:
        raise ValueError(ERROR_REPEAT)
    day = _date_value(data.get("date"), today)
    if day is None:
        raise ValueError(ERROR_DATE)
    pickup = _text(data.get("pickup_time")) or None
    if daycare_kind == DAYCARE_EARLY_END and not pickup:
        raise ValueError(ERROR_PICKUP_TIME)
    if daycare_kind == DAYCARE_DEREGISTER:
        pickup = None
    payload = {
        "student": {"id": student},
        "type": REQUEST_TYPES[TARGET_AFTERNOON_CARE],
        "absentDate": _iso_utc(day),
        "note": _text(data.get("reason")) or None,
        "topic": "",
        "requestDescriptionHtml": "",
        "pickupTime": pickup,
        "repeatWeekly": repeat == REPEAT_WEEKLY,
        "repeatWeeklyUntil": _repeat_until(data, today),
    }
    return Request(
        f"{REQUESTS_PATH}not-attend/{TARGET_AFTERNOON_CARE}/",
        BODY_FORM,
        payload,
        NO_DEFAULT_CONTENT_TYPE,
    )


def form_fields(payload):
    return {"data": json.dumps(payload, separators=(",", ":"), ensure_ascii=False)}


def _repeat_until(data, today):
    value = _date_value(data.get("repeat_until"), today)
    return _iso_utc(value) if value else None


def _html(text):
    cleaned = text.replace("\r\n", "\n").strip()
    parts = [line.strip() for line in cleaned.split("\n") if line.strip()]
    return "".join(f"<p>{_escape(part)}</p>" for part in parts)


def _escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _last_sunday(year, month):
    day = 31
    while True:
        try:
            candidate = date(year, month, day)
        except ValueError:
            day -= 1
            continue
        if candidate.weekday() == 6:
            return candidate
        day -= 1


def berlin_offset(moment):
    year = moment.year
    starts = datetime.combine(_last_sunday(year, 3), time(2, 0))
    ends = datetime.combine(_last_sunday(year, 10), time(3, 0))
    return 2 if starts <= moment < ends else 1


def _iso_utc(day):
    local = datetime.combine(day, time(0, 0))
    return (local - timedelta(hours=berlin_offset(local))).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _epoch(day, moment):
    local = datetime.combine(day, moment)
    stamp = local - timedelta(hours=berlin_offset(local))
    return int(stamp.replace(tzinfo=timezone.utc).timestamp())


def _date_value(value, today=None):
    text = resolve_day(value, today)
    if not text:
        return None
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def _time_value(value, fallback):
    text = _text(value)
    if not text:
        return fallback
    try:
        return time.fromisoformat(text if len(text) > 5 else f"{text}:00")
    except ValueError:
        return fallback


def _berlin_date_from_utc(utc_naive):
    if berlin_offset(utc_naive + timedelta(hours=2)) == 2:
        local = utc_naive + timedelta(hours=2)
    else:
        local = utc_naive + timedelta(hours=1)
    return local.date()


def _date_part(value):
    if value in (None, ""):
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        utc_naive = datetime.fromtimestamp(value, timezone.utc).replace(tzinfo=None)
        return _berlin_date_from_utc(utc_naive).isoformat()
    text = str(value)
    if "T" in text and text.endswith("Z"):
        utc_naive = datetime.fromisoformat(text[:-1])
        return _berlin_date_from_utc(utc_naive).isoformat()
    return text[:10]


def _text(value):
    if value in (None, ""):
        return ""
    return str(value).strip()


def _as_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, dict):
        return _as_int(value.get("id"))
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _first(raw, *keys):
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return ""
