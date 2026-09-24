from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import Absence, Exam, Info, Lesson, School, SchoolInfo, State
from .const import (
    ATTR_ABSENCES,
    ATTR_CHANGES,
    ATTR_DATE,
    ATTR_DAYS,
    ATTR_DAYS_UNTIL,
    ATTR_DETAILS,
    ATTR_END,
    ATTR_EXAMS,
    ATTR_FEED_PORT_OPEN,
    ATTR_INGRESS_PATH,
    ATTR_LAST_POLL,
    ATTR_LAST_SUCCESS,
    ATTR_LETTERS,
    ATTR_MINUTES_LEFT,
    ATTR_MINUTES_UNTIL,
    ATTR_MODULES,
    ATTR_MODULES_DISABLED,
    ATTR_POSTS,
    ATTR_SCHOOL_DAY,
    ATTR_SOURCE,
    ATTR_START,
    ATTR_TITLE,
    ATTR_VERSION,
    CONNECTION_STATES,
    KEY_CHANGES_TODAY,
    KEY_CONNECTION,
    KEY_CURRENT_LESSON,
    KEY_EXAMS_UPCOMING,
    KEY_NEXT_CONFERENCE,
    KEY_NEXT_ABSENCE,
    KEY_NEXT_EXAM,
    KEY_NEXT_HOLIDAY,
    KEY_NEXT_LESSON,
    KEY_NEXT_SCHOOL_DAY,
    KEY_OPEN_ABSENCES,
    KEY_SCHOOL_END_TODAY,
    KEY_TIMETABLE_LAST_UPDATED,
    KEY_UNREAD_LETTERS,
    KEY_UNREAD_POSTS,
    MODULE_ABSENCES,
    MODULE_CONFERENCES,
    MODULE_LETTERS,
    MODULE_PINBOARD,
    MODULE_TIMETABLE,
    STATE_NONE,
)
from .coordinator import RanzenpostConfigEntry, RanzenpostCoordinator, selected_children
from .entity import RanzenpostChildEntity, RanzenpostSchoolEntity


def _minutes_from_now(moment: datetime | None) -> int:
    if moment is None:
        return 0
    return max(0, int((moment - dt_util.now()).total_seconds() // 60))


def _lesson_value(lesson: Lesson | None) -> str:
    return lesson.subject if lesson and lesson.subject else STATE_NONE


def _lesson_attributes(lesson: Lesson | None) -> dict[str, Any]:
    if lesson is None:
        return {}
    attributes = lesson.as_attributes()
    attributes[ATTR_MINUTES_UNTIL] = _minutes_from_now(lesson.start)
    attributes[ATTR_MINUTES_LEFT] = _minutes_from_now(lesson.end)
    return attributes


def _exam_value(exam: Exam | None) -> str:
    return exam.subject if exam and exam.subject else STATE_NONE


def _absence_value(absence: Absence | None) -> str:
    return absence.start.isoformat() if absence and absence.start else STATE_NONE


def _school_day_attributes(state: State) -> dict[str, Any]:
    return state.next_school_day.as_attributes() if state.next_school_day else {}


def _conference_moment(school: School, info: Info) -> datetime | None:
    if school.next_conference is None:
        return None
    zone = dt_util.get_time_zone(info.timezone) or dt_util.DEFAULT_TIME_ZONE
    return datetime.combine(school.next_conference.date, datetime.min.time(), tzinfo=zone)


def _holiday_attributes(school: School) -> dict[str, Any]:
    holiday = school.next_holiday
    if holiday is None:
        return {}
    return {ATTR_START: holiday.start.isoformat(), ATTR_END: holiday.end.isoformat(), ATTR_DAYS_UNTIL: holiday.days_until}


def _conference_attributes(school: School) -> dict[str, Any]:
    conference = school.next_conference
    if conference is None:
        return {}
    return {
        ATTR_DATE: conference.date.isoformat(),
        ATTR_TITLE: conference.title,
        ATTR_DETAILS: list(conference.details),
        ATTR_DAYS_UNTIL: conference.days_until,
    }


def _connection_attributes(listed: SchoolInfo, info: Info) -> dict[str, Any]:
    return {
        ATTR_LAST_POLL: listed.last_poll.isoformat() if listed.last_poll else None,
        ATTR_LAST_SUCCESS: listed.last_success.isoformat() if listed.last_success else None,
        ATTR_VERSION: info.version,
        ATTR_MODULES: listed.modules.as_dict(),
        ATTR_MODULES_DISABLED: sorted(listed.modules.disabled),
        ATTR_FEED_PORT_OPEN: info.feed_port_open,
        ATTR_INGRESS_PATH: info.ingress_path,
    }


@dataclass(frozen=True, kw_only=True)
class ChildSensorDescription(SensorEntityDescription):
    value_fn: Callable[[State], Any]
    attributes_fn: Callable[[State], dict[str, Any]] = lambda state: {}
    module: str | None = None


@dataclass(frozen=True, kw_only=True)
class SchoolSensorDescription(SensorEntityDescription):
    value_fn: Callable[[School, SchoolInfo, Info], Any]
    attributes_fn: Callable[[School, SchoolInfo, Info], dict[str, Any]] = lambda school, listed, info: {}
    module: str | None = None


CHILD_SENSORS: tuple[ChildSensorDescription, ...] = (
    ChildSensorDescription(
        key=KEY_CURRENT_LESSON,
        value_fn=lambda state: _lesson_value(state.now_lesson),
        attributes_fn=lambda state: _lesson_attributes(state.now_lesson),
        module=MODULE_TIMETABLE,
    ),
    ChildSensorDescription(
        key=KEY_NEXT_LESSON,
        value_fn=lambda state: _lesson_value(state.next_lesson),
        attributes_fn=lambda state: _lesson_attributes(state.next_lesson),
        module=MODULE_TIMETABLE,
    ),
    ChildSensorDescription(
        key=KEY_SCHOOL_END_TODAY,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda state: state.school_end_today,
        attributes_fn=lambda state: {ATTR_SCHOOL_DAY: state.school_day_today},
        module=MODULE_TIMETABLE,
    ),
    ChildSensorDescription(
        key=KEY_NEXT_SCHOOL_DAY,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda state: state.next_school_day.start if state.next_school_day else None,
        attributes_fn=_school_day_attributes,
        module=MODULE_TIMETABLE,
    ),
    ChildSensorDescription(
        key=KEY_CHANGES_TODAY,
        value_fn=lambda state: len(state.changes_today),
        attributes_fn=lambda state: {ATTR_CHANGES: [_lesson_attributes(lesson) for lesson in state.changes_today]},
        module=MODULE_TIMETABLE,
    ),
    ChildSensorDescription(
        key=KEY_NEXT_EXAM,
        value_fn=lambda state: _exam_value(state.next_exam),
        attributes_fn=lambda state: state.next_exam.as_attributes() if state.next_exam else {},
        module=MODULE_TIMETABLE,
    ),
    ChildSensorDescription(
        key=KEY_EXAMS_UPCOMING,
        value_fn=lambda state: len(state.exams_upcoming),
        attributes_fn=lambda state: {
            ATTR_EXAMS: [exam.as_attributes() for exam in state.exams_upcoming],
            ATTR_DAYS: state.exam_days,
        },
        module=MODULE_TIMETABLE,
    ),
    ChildSensorDescription(
        key=KEY_UNREAD_LETTERS,
        value_fn=lambda state: state.unread_letters.count,
        attributes_fn=lambda state: {ATTR_LETTERS: state.unread_letters.as_attributes()},
        module=MODULE_LETTERS,
    ),
    ChildSensorDescription(
        key=KEY_UNREAD_POSTS,
        value_fn=lambda state: state.unread_posts.count,
        attributes_fn=lambda state: {ATTR_POSTS: state.unread_posts.as_attributes()},
        module=MODULE_PINBOARD,
    ),
    ChildSensorDescription(
        key=KEY_OPEN_ABSENCES,
        value_fn=lambda state: len(state.open_absences),
        attributes_fn=lambda state: {ATTR_ABSENCES: [absence.as_attributes() for absence in state.open_absences]},
        module=MODULE_ABSENCES,
    ),
    ChildSensorDescription(
        key=KEY_NEXT_ABSENCE,
        value_fn=lambda state: _absence_value(state.next_absence),
        attributes_fn=lambda state: state.next_absence.as_attributes() if state.next_absence else {},
        module=MODULE_ABSENCES,
    ),
    ChildSensorDescription(
        key=KEY_TIMETABLE_LAST_UPDATED,
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.timetable_last_updated,
        attributes_fn=lambda state: {ATTR_SOURCE: state.timetable_last_updated_source},
        module=MODULE_TIMETABLE,
    ),
)

SCHOOL_SENSORS: tuple[SchoolSensorDescription, ...] = (
    SchoolSensorDescription(
        key=KEY_NEXT_HOLIDAY,
        value_fn=lambda school, listed, info: school.next_holiday.name if school.next_holiday else STATE_NONE,
        attributes_fn=lambda school, listed, info: _holiday_attributes(school),
    ),
    SchoolSensorDescription(
        key=KEY_NEXT_CONFERENCE,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda school, listed, info: _conference_moment(school, info),
        attributes_fn=lambda school, listed, info: _conference_attributes(school),
        module=MODULE_CONFERENCES,
    ),
    SchoolSensorDescription(
        key=KEY_CONNECTION,
        device_class=SensorDeviceClass.ENUM,
        options=list(CONNECTION_STATES),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda school, listed, info: listed.status if listed.status in CONNECTION_STATES else None,
        attributes_fn=lambda school, listed, info: _connection_attributes(listed, info),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: RanzenpostConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    info = coordinator.data.info
    entities: list[SensorEntity] = []
    for school in info.schools:
        entities.extend(
            RanzenpostSchoolSensor(coordinator, school, description)
            for description in SCHOOL_SENSORS
            if description.module is None or school.modules.has(description.module)
        )
    for child in selected_children(info, entry):
        modules = info.modules_of(child)
        entities.extend(
            RanzenpostChildSensor(coordinator, child, description)
            for description in CHILD_SENSORS
            if description.module is None or modules.has(description.module)
        )
    async_add_entities(entities)


class RanzenpostChildSensor(RanzenpostChildEntity, SensorEntity):
    entity_description: ChildSensorDescription

    def __init__(self, coordinator: RanzenpostCoordinator, child, description: ChildSensorDescription) -> None:
        super().__init__(coordinator, SENSOR_DOMAIN, child, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        state = self.state_of_child
        return self.entity_description.value_fn(state) if state else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.state_of_child
        return self.entity_description.attributes_fn(state) if state else {}


class RanzenpostSchoolSensor(RanzenpostSchoolEntity, SensorEntity):
    entity_description: SchoolSensorDescription

    def __init__(
        self, coordinator: RanzenpostCoordinator, school: SchoolInfo, description: SchoolSensorDescription
    ) -> None:
        super().__init__(coordinator, SENSOR_DOMAIN, school, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        listed = self.school_info
        if listed is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data.school(self.school_id), listed, self.info)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        listed = self.school_info
        if listed is None:
            return {}
        return self.entity_description.attributes_fn(self.coordinator.data.school(self.school_id), listed, self.info)
