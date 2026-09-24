from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import aiohttp

from .const import MODULES, REQUEST_TIMEOUT

ROUTE_INFO = "/api/integration/info"
ROUTE_STATE = "/api/integration/state"
ROUTE_EVENTS = "/api/integration/events"
ROUTE_SCHOOL = "/api/integration/school"
ROUTE_CHANGES = "/api/integration/changes"
AUTH_STATUSES = (401, 403)
KEY_SEPARATOR = ":"
KEY_SCHOOLS = "schools"


class RanzenpostError(Exception):
    pass


class AuthError(RanzenpostError):
    pass


class ConnectionError(RanzenpostError):
    pass


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def school_of_key(key: str) -> str:
    school, separator, _ = str(key or "").partition(KEY_SEPARATOR)
    return school if separator else ""


@dataclass(frozen=True)
class Child:
    key: str
    name: str
    class_name: str
    school_id: str

    @property
    def first_name(self) -> str:
        parts = self.name.split()
        return parts[0] if parts else self.raw_id

    @property
    def raw_id(self) -> str:
        _, separator, rest = self.key.partition(KEY_SEPARATOR)
        return rest if separator else self.key

    @classmethod
    def from_json(cls, data: dict[str, Any], school_id: str = "") -> Child:
        key = str(data["key"])
        return cls(
            key=key,
            name=str(data.get("name") or ""),
            class_name=str(data.get("class_name") or ""),
            school_id=school_id or school_of_key(key),
        )


@dataclass(frozen=True)
class Modules:
    available: frozenset[str]
    disabled: frozenset[str] = frozenset()

    @classmethod
    def from_json(cls, data: Any, disabled: Any = None) -> Modules:
        flags = data if isinstance(data, dict) else {}
        switched_off = disabled if isinstance(disabled, dict) else {}
        off = frozenset(name for name in MODULES if switched_off.get(name) is True)
        return cls(frozenset(name for name in MODULES if flags.get(name, True) is not False and name not in off), off)

    def has(self, name: str) -> bool:
        return name in self.available

    def as_dict(self) -> dict[str, bool]:
        return {name: name in self.available for name in MODULES}


@dataclass(frozen=True)
class SchoolInfo:
    id: str
    name: str
    url_host: str
    modules: Modules
    status: str
    children: tuple[Child, ...]
    last_poll: datetime | None = None
    last_success: datetime | None = None
    status_reason: str = ""
    own_entries: bool = False

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SchoolInfo:
        school_id = str(data.get("id") or "")
        return cls(
            id=school_id,
            name=str(data.get("name") or ""),
            url_host=str(data.get("url_host") or ""),
            modules=Modules.from_json(data.get("modules"), data.get("disabled")),
            status=str(data.get("status") or ""),
            children=tuple(Child.from_json(item, school_id) for item in data.get("children") or []),
            last_poll=parse_datetime(data.get("last_poll")),
            last_success=parse_datetime(data.get("last_success")),
            status_reason=str(data.get("status_reason") or ""),
            own_entries=data.get("own_entries") is True,
        )

    @property
    def label(self) -> str:
        return self.name or self.url_host or self.id


@dataclass(frozen=True)
class Info:
    version: str
    schools: tuple[SchoolInfo, ...]
    language: str
    timezone: str
    feed_port_open: bool
    last_poll: datetime | None
    legacy: bool = False
    ingress_path: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Info:
        return cls(
            version=str(data.get("version") or ""),
            schools=tuple(SchoolInfo.from_json(item) for item in data.get("schools") or []),
            language=str(data.get("language") or ""),
            timezone=str(data.get("timezone") or ""),
            feed_port_open=bool(data.get("feed_port_open")),
            last_poll=parse_datetime(data.get("last_poll")),
            legacy=KEY_SCHOOLS not in data,
            ingress_path=str(data.get("ingress_path") or ""),
        )

    @property
    def children(self) -> tuple[Child, ...]:
        return tuple(child for school in self.schools for child in school.children)

    def school(self, school_id: str) -> SchoolInfo | None:
        return next((school for school in self.schools if school.id == school_id), None)

    def school_of(self, child: Child) -> SchoolInfo | None:
        return self.school(child.school_id)

    def modules_of(self, child: Child) -> Modules:
        school = self.school_of(child)
        return school.modules if school else Modules(frozenset(MODULES))

    @property
    def many_schools(self) -> bool:
        return len(self.schools) > 1


def _text_map(data: Any) -> dict[str, str]:
    return {str(key): str(value or "") for key, value in data.items()} if isinstance(data, dict) else {}


def _isoformat(value: date | datetime | None) -> str | None:
    return value.isoformat() if value else None


@dataclass(frozen=True)
class Lesson:
    subject: str
    subject_code: str
    teacher: str
    room: str
    start: datetime
    end: datetime
    substitution: bool
    cancelled: bool
    note: str
    date: date | None = None
    weekday: str = ""
    period: int = 0
    kind: str = ""
    before: dict[str, str] = field(default_factory=dict)
    after: dict[str, str] = field(default_factory=dict)
    minutes_until: int = 0
    minutes_left: int = 0

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Lesson:
        return cls(
            subject=str(data.get("subject") or ""),
            subject_code=str(data.get("subject_code") or ""),
            teacher=str(data.get("teacher") or ""),
            room=str(data.get("room") or ""),
            start=parse_datetime(data["start"]),
            end=parse_datetime(data["end"]),
            substitution=bool(data.get("substitution")),
            cancelled=bool(data.get("cancelled")),
            note=str(data.get("note") or ""),
            date=parse_date(data.get("date")),
            weekday=str(data.get("weekday") or ""),
            period=int(data.get("period") or 0),
            kind=str(data.get("kind") or ""),
            before=_text_map(data.get("before")),
            after=_text_map(data.get("after")),
            minutes_until=int(data.get("minutes_until") or 0),
            minutes_left=int(data.get("minutes_left") or 0),
        )

    def as_attributes(self) -> dict[str, Any]:
        return {
            "date": _isoformat(self.date),
            "weekday": self.weekday,
            "period": self.period,
            "subject": self.subject,
            "subject_code": self.subject_code,
            "teacher": self.teacher,
            "room": self.room,
            "start": _isoformat(self.start),
            "end": _isoformat(self.end),
            "substitution": self.substitution,
            "cancelled": self.cancelled,
            "kind": self.kind,
            "before": dict(self.before),
            "after": dict(self.after),
            "note": self.note,
            "minutes_until": self.minutes_until,
            "minutes_left": self.minutes_left,
        }


@dataclass(frozen=True)
class Notice:
    title: str
    sender: str
    date: date | None
    child: str

    @classmethod
    def from_json(cls, data: Any) -> Notice:
        if not isinstance(data, dict):
            return cls(title=str(data or ""), sender="", date=None, child="")
        return cls(
            title=str(data.get("title") or ""),
            sender=str(data.get("sender") or ""),
            date=parse_date(data.get("date")),
            child=str(data.get("child") or ""),
        )

    def as_attributes(self) -> dict[str, Any]:
        return {"title": self.title, "sender": self.sender, "date": _isoformat(self.date), "child": self.child}


@dataclass(frozen=True)
class Notices:
    count: int
    items: tuple[Notice, ...]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Notices:
        return cls(
            count=int(data.get("count") or 0),
            items=tuple(Notice.from_json(item) for item in data.get("items") or []),
        )

    def as_attributes(self) -> list[dict[str, Any]]:
        return [item.as_attributes() for item in self.items]


@dataclass(frozen=True)
class SchoolDay:
    date: date | None
    weekday: str
    days_until: int
    start: datetime | None
    end: datetime | None
    lessons: int
    first_lesson: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SchoolDay:
        return cls(
            date=parse_date(data.get("date")),
            weekday=str(data.get("weekday") or ""),
            days_until=int(data.get("days_until") or 0),
            start=parse_datetime(data.get("start")),
            end=parse_datetime(data.get("end")),
            lessons=int(data.get("lessons") or 0),
            first_lesson=str(data.get("first_lesson") or ""),
        )

    def as_attributes(self) -> dict[str, Any]:
        return {
            "date": _isoformat(self.date),
            "weekday": self.weekday,
            "days_until": self.days_until,
            "end": _isoformat(self.end),
            "lessons": self.lessons,
            "first_lesson": self.first_lesson,
        }


@dataclass(frozen=True)
class Exam:
    date: date | None
    weekday: str
    days_until: int
    period: int
    subject: str
    subject_code: str
    name: str
    start: datetime | None
    end: datetime | None
    teacher: str
    room: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Exam:
        return cls(
            date=parse_date(data.get("date")),
            weekday=str(data.get("weekday") or ""),
            days_until=int(data.get("days_until") or 0),
            period=int(data.get("period") or 0),
            subject=str(data.get("subject") or ""),
            subject_code=str(data.get("subject_code") or ""),
            name=str(data.get("name") or ""),
            start=parse_datetime(data.get("start")),
            end=parse_datetime(data.get("end")),
            teacher=str(data.get("teacher") or ""),
            room=str(data.get("room") or ""),
        )

    def as_attributes(self) -> dict[str, Any]:
        return {
            "date": _isoformat(self.date),
            "weekday": self.weekday,
            "days_until": self.days_until,
            "period": self.period,
            "subject": self.subject,
            "subject_code": self.subject_code,
            "name": self.name,
            "start": _isoformat(self.start),
            "end": _isoformat(self.end),
            "teacher": self.teacher,
            "room": self.room,
        }


@dataclass(frozen=True)
class Absence:
    kind: str
    summary: str
    start: date | None
    end: date | None
    status: str
    days_until: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Absence:
        return cls(
            kind=str(data.get("kind") or ""),
            summary=str(data.get("summary") or ""),
            start=parse_date(data.get("start")),
            end=parse_date(data.get("end")),
            status=str(data.get("status") or ""),
            days_until=int(data.get("days_until") or 0),
        )

    def as_attributes(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "status": self.status,
            "days_until": self.days_until,
        }


@dataclass(frozen=True)
class State:
    now_lesson: Lesson | None
    next_lesson: Lesson | None
    school_end_today: datetime | None
    next_school_day: SchoolDay | None
    changes_today: tuple[Lesson, ...]
    unread_letters: Notices
    unread_posts: Notices
    open_absences: tuple[Absence, ...]
    next_absence: Absence | None
    next_exam: Exam | None
    exams_upcoming: tuple[Exam, ...]
    exam_days: int
    school_day_today: bool
    timetable_changed_today: bool
    timetable_last_updated: datetime | None
    timetable_last_updated_source: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> State:
        absences = data.get("open_absences") or {}
        exams = data.get("exams_upcoming") or {}
        return cls(
            now_lesson=Lesson.from_json(data["now_lesson"]) if data.get("now_lesson") else None,
            next_lesson=Lesson.from_json(data["next_lesson"]) if data.get("next_lesson") else None,
            school_end_today=parse_datetime(data.get("school_end_today")),
            next_school_day=SchoolDay.from_json(data["next_school_day"]) if data.get("next_school_day") else None,
            changes_today=tuple(Lesson.from_json(item) for item in data.get("changes_today") or []),
            unread_letters=Notices.from_json(data.get("unread_letters") or {}),
            unread_posts=Notices.from_json(data.get("unread_posts") or {}),
            open_absences=tuple(Absence.from_json(item) for item in absences.get("items") or []),
            next_absence=Absence.from_json(data["next_absence"]) if data.get("next_absence") else None,
            next_exam=Exam.from_json(data["next_exam"]) if data.get("next_exam") else None,
            exams_upcoming=tuple(Exam.from_json(item) for item in exams.get("items") or []),
            exam_days=int(exams.get("days") or 0),
            school_day_today=bool(data.get("school_day_today")),
            timetable_changed_today=bool(data.get("timetable_changed_today")),
            timetable_last_updated=parse_datetime(data.get("timetable_last_updated")),
            timetable_last_updated_source=str(data.get("timetable_last_updated_source") or ""),
        )


@dataclass(frozen=True)
class Event:
    uid: str
    summary: str
    description: str
    location: str
    start: date | datetime
    end: date | datetime
    all_day: bool
    cancelled: bool
    color: str
    subject_code: str = ""
    subject: str = ""
    name: str = ""
    kind: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Event:
        all_day = bool(data.get("all_day"))
        parser = parse_date if all_day else parse_datetime
        return cls(
            uid=str(data["uid"]),
            summary=str(data.get("summary") or ""),
            description=str(data.get("description") or ""),
            location=str(data.get("location") or ""),
            start=parser(data["start"]),
            end=parser(data["end"]),
            all_day=all_day,
            cancelled=bool(data.get("cancelled")),
            color=str(data.get("color") or ""),
            subject_code=str(data.get("subject_code") or ""),
            subject=str(data.get("subject") or ""),
            name=str(data.get("name") or ""),
            kind=str(data.get("kind") or ""),
        )


@dataclass(frozen=True)
class Holiday:
    name: str
    start: date
    end: date
    days_until: int = 0


@dataclass(frozen=True)
class Conference:
    date: date
    title: str
    details: tuple[str, ...] = ()
    days_until: int = 0


@dataclass(frozen=True)
class School:
    next_holiday: Holiday | None
    next_conference: Conference | None
    region: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> School:
        holiday = data.get("next_holiday")
        conference = data.get("next_conference")
        return cls(
            next_holiday=(
                Holiday(
                    name=str(holiday.get("name") or ""),
                    start=parse_date(holiday["start"]),
                    end=parse_date(holiday["end"]),
                    days_until=int(holiday.get("days_until") or 0),
                )
                if holiday
                else None
            ),
            next_conference=(
                Conference(
                    date=parse_date(conference["date"]),
                    title=str(conference.get("title") or ""),
                    details=tuple(str(item) for item in conference.get("details") or []),
                    days_until=int(conference.get("days_until") or 0),
                )
                if conference
                else None
            ),
            region=str(data.get("region") or ""),
        )


@dataclass(frozen=True)
class Change:
    child_key: str
    school_id: str
    at: datetime | None
    kind: str
    summary: str
    date: date | None
    period: int
    new: bool

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Change:
        child_key = str(data.get("child_key") or "")
        return cls(
            child_key=child_key,
            school_id=str(data.get("school_id") or school_of_key(child_key)),
            at=parse_datetime(data.get("at")),
            kind=str(data.get("kind") or ""),
            summary=str(data.get("summary") or ""),
            date=parse_date(data.get("date")),
            period=int(data.get("period") or 0),
            new=bool(data.get("new")),
        )

    @property
    def key(self) -> tuple[str, str, str, str, str, int]:
        return (
            self.child_key,
            self.at.isoformat() if self.at else "",
            self.kind,
            self.summary,
            self.date.isoformat() if self.date else "",
            self.period,
        )


@dataclass
class RanzenpostApi:
    session: aiohttp.ClientSession
    host: str
    port: int
    token: str
    timeout: float = REQUEST_TIMEOUT
    base_url: str = field(init=False)

    def __post_init__(self) -> None:
        self.base_url = f"http://{self.host}:{int(self.port)}"

    async def _get(self, route: str, params: dict[str, str] | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with asyncio.timeout(self.timeout):
                response = await self.session.get(self.base_url + route, params=params, headers=headers)
                if response.status in AUTH_STATUSES:
                    raise AuthError(f"{route} answered {response.status}")
                if response.status != 200:
                    raise ConnectionError(f"{route} answered {response.status}")
                return await response.json()
        except (aiohttp.ClientError, TimeoutError, OSError, ValueError) as err:
            raise ConnectionError(f"{route} could not be read: {err}") from err

    async def info(self) -> Info:
        return Info.from_json(await self._get(ROUTE_INFO))

    async def state(self, child_key: str) -> State:
        return State.from_json(await self._get(ROUTE_STATE, {"child": child_key}))

    async def events(
        self, child_key: str, kind: str, start: date, end: date, school_id: str = "", purpose: str = ""
    ) -> list[Event]:
        params = {"child": child_key, "kind": kind, "start": start.isoformat(), "end": end.isoformat()}
        if school_id:
            params["school"] = school_id
        if purpose:
            params["purpose"] = purpose
        return [Event.from_json(item) for item in await self._get(ROUTE_EVENTS, params)]

    async def school(self, school_id: str) -> School:
        return School.from_json(await self._get(ROUTE_SCHOOL, {"id": school_id}))

    async def changes(self) -> list[Change]:
        return [Change.from_json(item) for item in await self._get(ROUTE_CHANGES)]
