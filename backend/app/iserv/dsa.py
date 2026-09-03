import re
from dataclasses import dataclass, field

from .absences import ATTACHMENT_FIELD_NAME, BODY_JSON, form_fields
from .html import clean_html

API_ROOT = "/iserv/dieschulapp/api/1.0"
PINBOARD_FIELDS = (
    "id,title,staticFiles,studentsAndGuardiansCanCreateTiles,author,"
    "columns,columns.tiles"
)
PINBOARD_PARAMS = {"fields": PINBOARD_FIELDS}

@dataclass(frozen=True)
class Attachment:
    id: int
    filename: str
    extension: str
    mimetype: str
    size: int
    file: str = ""
    created_at: object = None
    updated_at: object = None
    image_width: object = None
    image_height: object = None


@dataclass
class Tile:
    id: int
    title: str
    text: str
    color: str
    owner: str
    attachments: list = field(default_factory=list)


@dataclass
class PinboardColumn:
    id: int
    title: str
    tiles: list = field(default_factory=list)


@dataclass
class Pinboard:
    id: int
    title: str
    columns: list = field(default_factory=list)
    attachments: list = field(default_factory=list)
    author: str = ""
    students_can_create_tiles: bool = False


def normalize_class(value):
    if isinstance(value, dict):
        value = value.get("externalId") or value.get("name") or ""
    token = re.split(r"[.\s]+", str(value).strip())
    token = token[-1] if token else ""
    token = token.upper()
    token = re.sub(r"^0+(?=\d)", "", token)
    return token


def _name_words(name):
    return frozenset(part for part in re.split(r"[\s,]+", (name or "").lower()) if part)


def parse_students(payload):
    students = []
    for entry in payload or []:
        raw_main_course = entry.get("mainCourse") or {}
        main_course = raw_main_course if isinstance(raw_main_course, dict) else {}
        students.append(
            {
                "id": entry.get("id"),
                "name": entry.get("displayname") or f"{entry.get('forename', '')} {entry.get('surname', '')}".strip(),
                "class_name": normalize_class(raw_main_course),
                "class_full": main_course.get("name") or "",
                "class_code": main_course.get("externalId") or "",
            }
        )
    return students


def class_for_name(students, name):
    student = student_for_name(students, name)
    return student.get("class_name", "") if student else ""


def student_for_name(students, name):
    target = _name_words(name)
    if not target:
        return None
    for student in students or []:
        if _name_words(student.get("name")) == target:
            return student
    return None


def parse_school(payload):
    entry = payload[0] if isinstance(payload, list) and payload else payload
    if not isinstance(entry, dict) or not entry:
        return {}
    return {
        "id": entry.get("id"),
        "name": entry.get("name") or "",
        "street": entry.get("street") or "",
        "postal_code": entry.get("zip") or "",
        "town": entry.get("town") or "",
        "country": entry.get("country") or "",
    }


def parse_period_times(slots):
    times = {}
    for slot in slots or []:
        number = slot.get("number")
        start = slot.get("startTime")
        if number is not None and start:
            times[str(number)] = start
    return times


def _parse_attachments(items):
    result = []
    for item in items or []:
        result.append(
            Attachment(
                id=item.get("id"),
                filename=item.get("originalFilename") or item.get("filename") or "",
                extension=item.get("extension") or "",
                mimetype=item.get("mimetype") or "",
                size=item.get("size") or 0,
                file=item.get("filename") or "",
                created_at=item.get("createdAt"),
                updated_at=item.get("updatedAt"),
                image_width=item.get("imageWidth"),
                image_height=item.get("imageHeight"),
            )
        )
    return result


def parse_pinboards(payload):
    boards = []
    for entry in payload or []:
        columns = []
        for column in entry.get("columns") or []:
            tiles = []
            for tile in column.get("tiles") or []:
                owner = tile.get("owner") or {}
                tiles.append(
                    Tile(
                        id=tile.get("id"),
                        title=tile.get("title") or "",
                        text=clean_html(tile.get("text")),
                        color=tile.get("color") or "",
                        owner=owner.get("displayname") or "",
                        attachments=_parse_attachments(tile.get("staticFiles")),
                    )
                )
            columns.append(PinboardColumn(id=column.get("id"), title=column.get("title") or "", tiles=tiles))
        author = entry.get("author")
        author = author if isinstance(author, dict) else {}
        boards.append(
            Pinboard(
                id=entry.get("id"),
                title=entry.get("title") or "",
                columns=columns,
                attachments=_parse_attachments(entry.get("staticFiles")),
                author=author.get("displayname") or "",
                students_can_create_tiles=bool(entry.get("studentsAndGuardiansCanCreateTiles")),
            )
        )
    return boards


def enabled_absence_types(settings):
    settings = settings or {}
    types = ["sick", "leave"]
    if settings.get("requestToSchools_studentAbsence_isActive") is False:
        types.remove("leave")
    deregister = deregister_options(settings)
    if deregister:
        types.append("deregister")
    if settings.get("requestToSchools_notAttend_afternoonCare_isActive"):
        types.append("daycare")
    return types


def deregister_options(settings):
    settings = settings or {}
    options = []
    if settings.get("requestToSchools_notAttend_bus_isActive"):
        options.append("bus")
    if settings.get("requestToSchools_notAttend_kindergarten_isActive"):
        options.append("kindergarten")
    if settings.get("requestToSchools_notAttend_lunch_isActive"):
        options.append("lunch")
    return options


def absence_rules(settings):
    settings = settings or {}
    pickup_times = settings.get("requestToSchools_notAttend_afternoonCare_pickupTimes")
    return {
        "sick_by_lesson": bool(settings.get("sickNotes_guardiansCanReportByLesson")),
        "sick_comment": bool(settings.get("sickNotes_allowTextnoteForGuardiansAndStudents")),
        "sick_cutoff": settings.get("sickNotes_latestTimeToReportASickNoteToday") or "",
        "sick_cutoff_message": settings.get("sickNotes_tooLateMessageForToday") or "",
        "duty_hint": settings.get("sickNotes_dutyToReportTooltip") or "",
        "leave_min_days": _int_setting(settings, "requestToSchools_studentAbsence_minDays"),
        "daycare_min_days": _int_setting(
            settings, "requestToSchools_notAttend_afternoonCare_minDays"
        ),
        "daycare_cutoff": settings.get("dayCare_latestTimeToCancelAttendanceToday") or "",
        "daycare_reason_required": bool(
            settings.get("requestToSchools_notAttend_afternoonCare_noteRequired")
        ),
        "daycare_custom_pickup": bool(
            settings.get("requestToSchools_notAttend_afternoonCare_allowCustomPickupTime")
        ),
        "daycare_pickup_times": list(pickup_times) if isinstance(pickup_times, list) else [],
    }


def _int_setting(settings, key):
    try:
        return int(settings.get(key) or 0)
    except (TypeError, ValueError):
        return 0


class DieSchulAppClient:
    def __init__(self, base_url, session, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.session = session
        self.timeout = timeout

    def _get(self, path, params=None):
        response = self.session.get(f"{self.base_url}{API_ROOT}/{path}", params=params, timeout=self.timeout)
        if response.status_code != 200:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    def students(self):
        return parse_students(self._get("students/"))

    def school(self):
        return parse_school(self._get("schools/"))

    def school_settings(self):
        data = self._get("school-settings/")
        if isinstance(data, list):
            return data[0] if data else {}
        return data or {}

    def services(self):
        return self._get("services/") or []

    def period_times(self):
        return parse_period_times(self._get("timetable-slots/", {"filterBy": "type:is(lesson)"}))

    def lesson_slots(self):
        slots = self._get("timetable-slots/", {"filterBy": "type:is(lesson)"}) or []
        result = []
        for slot in slots:
            number = slot.get("number")
            if number is None:
                continue
            result.append({"number": number, "name": slot.get("name") or ""})
        return result

    def send_request(self, request):
        url = f"{self.base_url}{API_ROOT}/{request.path}"
        if request.body_mode == BODY_JSON:
            return self.session.post(url, json=request.payload, timeout=self.timeout)
        parts = [(name, (None, value)) for name, value in form_fields(request.payload).items()]
        for attachment in request.attachments:
            parts.append(
                (
                    ATTACHMENT_FIELD_NAME,
                    (
                        attachment.get("filename") or "attachment",
                        attachment.get("content") or b"",
                        attachment.get("content_type") or "application/octet-stream",
                    ),
                )
            )
        return self.session.post(
            url,
            files=parts,
            headers=request.headers or None,
            timeout=self.timeout,
        )

    def delete_entry(self, path):
        return self.session.delete(f"{self.base_url}{API_ROOT}/{path}", timeout=self.timeout)

    def pinboards(self):
        return parse_pinboards(self._get("pinboards/", PINBOARD_PARAMS))

    def sick_note_children(self):
        return parse_students(self._get("sickNotes/userSelection/"))

    def sick_notes(self, since=None):
        params = {"filterBy": f"sickTillDateAsString:greaterOrEqualThan({since})"} if since else None
        return self._get("sickNotes/", params) or []

    def user_requests(self, path, student_id=None):
        params = {"filterBy": "initiatingRepeatRequest:is(null)"}
        if student_id:
            params = {"filterBy": [params["filterBy"], f"student.id:is({student_id})"]}
        return self._get(path, params) or []
