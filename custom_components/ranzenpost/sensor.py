from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .api import Exam, Holiday, Info, Lesson, Notices, School, SchoolInfo, State
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
    ATTR_FORUMS,
    ATTR_TEXTS,
    ATTR_NEWS,
    ATTR_POSTS,
    ATTR_PROFILES,
    ATTR_SCHOOL_DAY,
    ATTR_SOURCE,
    ATTR_START,
    ATTR_TASKS,
    ATTR_TITLE,
    ATTR_VERSION,
    ATTR_INTEGRATION_VERSION,
    CONNECTION_STATES,
    FIELD_CHANGES_TODAY,
    FIELD_NEXT_LESSON,
    FIELD_NEXT_SCHOOL_DAY,
    FIELD_NOW_LESSON,
    FIELD_SCHOOL_END_TODAY,
    KEY_CHANGES_TODAY,
    KEY_CONNECTION,
    KEY_CURRENT_LESSON,
    KEY_EXAMS_UPCOMING,
    KEY_NEXT_CONFERENCE,
    KEY_NEXT_ABSENCE,
    KEY_NEXT_EXAM,
    KEY_NEXT_FREE_DAY,
    KEY_NEXT_HOLIDAY,
    KEY_NEXT_LESSON,
    KEY_NEXT_SCHOOL_DAY,
    KEY_NEWS,
    KEY_TEXTS,
    KEY_UNREAD_FORUM_POSTS,
    KEY_OPEN_ABSENCES,
    KEY_OPEN_TASKS,
    KEY_SCHOOL_END_TODAY,
    KEY_TIMETABLE_LAST_UPDATED,
    KEY_UNREAD_LETTERS,
    KEY_UNREAD_MAIL,
    KEY_UNREAD_POSTS,
    MODULE_ABSENCES,
    MODULE_CONFERENCES,
    MODULE_LETTERS,
    MODULE_FORUMS,
    MODULE_TEXTS,
    MODULE_NEWS,
    MODULE_PINBOARD,
    MODULE_TASKS,
    MODULE_TIMETABLE,
    STATE_NONE,
)
from .coordinator import RanzenpostConfigEntry, RanzenpostCoordinator, selected_children
from .entity import RanzenpostChildEntity, RanzenpostSchoolEntity

PARALLEL_UPDATES = 0


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




def _school_day_attributes(state: State) -> dict[str, Any]:
    return state.next_school_day.as_attributes() if state.next_school_day else {}


def _holiday_attributes(holiday: Holiday | None) -> dict[str, Any]:
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


def _notice_count(notices: Notices | None) -> int | None:
    return notices.count if notices is not None else None


def _notice_attributes(name: str, notices: Notices | None) -> dict[str, Any]:
    return {name: notices.as_attributes()} if notices is not None else {}


def _connection_attributes(listed: SchoolInfo, info: Info) -> dict[str, Any]:
    return {
        ATTR_LAST_POLL: listed.last_poll.isoformat() if listed.last_poll else None,
        ATTR_LAST_SUCCESS: listed.last_success.isoformat() if listed.last_success else None,
        ATTR_VERSION: info.version,
        ATTR_INTEGRATION_VERSION: info.integration_version,
        ATTR_MODULES: listed.modules.as_dict(),
        ATTR_MODULES_DISABLED: sorted(listed.modules.disabled),
        ATTR_FEED_PORT_OPEN: info.feed_port_open,
        ATTR_INGRESS_PATH: info.ingress_path,
        ATTR_PROFILES: len(listed.children),
    }


@dataclass(frozen=True, kw_only=True)
class ChildSensorDescription(SensorEntityDescription):
    value_fn: Callable[[State], Any]
    attributes_fn: Callable[[State], dict[str, Any]] = lambda state: {}
    module: str | None = None
    field: str | None = None
    follows_clock: bool = False


@dataclass(frozen=True, kw_only=True)
class SchoolSensorDescription(SensorEntityDescription):
    value_fn: Callable[[School, SchoolInfo, Info], Any]
    attributes_fn: Callable[[School, SchoolInfo, Info], dict[str, Any]] = lambda school, listed, info: {}
    module: str | None = None
    mail: bool = False
    field: str | None = None


CHILD_SENSORS: tuple[ChildSensorDescription, ...] = (
    ChildSensorDescription(
        key=KEY_CURRENT_LESSON,
        value_fn=lambda state: _lesson_value(state.lesson_at(dt_util.now())),
        attributes_fn=lambda state: _lesson_attributes(state.lesson_at(dt_util.now())),
        module=MODULE_TIMETABLE,
        field=FIELD_NOW_LESSON,
        follows_clock=True,
    ),
    ChildSensorDescription(
        key=KEY_NEXT_LESSON,
        value_fn=lambda state: _lesson_value(state.lesson_after(dt_util.now())),
        attributes_fn=lambda state: _lesson_attributes(state.lesson_after(dt_util.now())),
        module=MODULE_TIMETABLE,
        field=FIELD_NEXT_LESSON,
        follows_clock=True,
    ),
    ChildSensorDescription(
        key=KEY_SCHOOL_END_TODAY,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda state: state.school_end_today,
        attributes_fn=lambda state: {ATTR_SCHOOL_DAY: state.school_day_today},
        module=MODULE_TIMETABLE,
        field=FIELD_SCHOOL_END_TODAY,
    ),
    ChildSensorDescription(
        key=KEY_NEXT_SCHOOL_DAY,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda state: state.next_school_day.start if state.next_school_day else None,
        attributes_fn=_school_day_attributes,
        module=MODULE_TIMETABLE,
        field=FIELD_NEXT_SCHOOL_DAY,
    ),
    ChildSensorDescription(
        key=KEY_CHANGES_TODAY,
        value_fn=lambda state: len(state.changes_today),
        attributes_fn=lambda state: {ATTR_CHANGES: [_lesson_attributes(lesson) for lesson in state.changes_today]},
        module=MODULE_TIMETABLE,
        field=FIELD_CHANGES_TODAY,
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
        value_fn=lambda state: _notice_count(state.unread_letters),
        attributes_fn=lambda state: _notice_attributes(ATTR_LETTERS, state.unread_letters),
        module=MODULE_LETTERS,
    ),
    ChildSensorDescription(
        key=KEY_UNREAD_POSTS,
        value_fn=lambda state: _notice_count(state.unread_posts),
        attributes_fn=lambda state: _notice_attributes(ATTR_POSTS, state.unread_posts),
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
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda state: state.next_absence.start if state.next_absence else None,
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
        attributes_fn=lambda school, listed, info: _holiday_attributes(school.next_holiday),
        field=KEY_NEXT_HOLIDAY,
    ),
    SchoolSensorDescription(
        key=KEY_NEXT_FREE_DAY,
        value_fn=lambda school, listed, info: school.next_free_day.name if school.next_free_day else STATE_NONE,
        attributes_fn=lambda school, listed, info: _holiday_attributes(school.next_free_day),
        field=KEY_NEXT_FREE_DAY,
    ),
    SchoolSensorDescription(
        key=KEY_NEXT_CONFERENCE,
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda school, listed, info: school.next_conference.date if school.next_conference else None,
        attributes_fn=lambda school, listed, info: _conference_attributes(school),
        module=MODULE_CONFERENCES,
    ),
    SchoolSensorDescription(
        key=KEY_UNREAD_LETTERS,
        value_fn=lambda school, listed, info: _notice_count(school.unread_letters),
        attributes_fn=lambda school, listed, info: _notice_attributes(ATTR_LETTERS, school.unread_letters),
        module=MODULE_LETTERS,
    ),
    SchoolSensorDescription(
        key=KEY_UNREAD_POSTS,
        value_fn=lambda school, listed, info: _notice_count(school.unread_posts),
        attributes_fn=lambda school, listed, info: _notice_attributes(ATTR_POSTS, school.unread_posts),
        module=MODULE_PINBOARD,
    ),
    SchoolSensorDescription(
        key=KEY_OPEN_TASKS,
        value_fn=lambda school, listed, info: _notice_count(school.open_tasks),
        attributes_fn=lambda school, listed, info: _notice_attributes(ATTR_TASKS, school.open_tasks),
        module=MODULE_TASKS,
    ),
    SchoolSensorDescription(
        key=KEY_NEWS,
        value_fn=lambda school, listed, info: _notice_count(school.news),
        attributes_fn=lambda school, listed, info: _notice_attributes(ATTR_NEWS, school.news),
        module=MODULE_NEWS,
    ),
    SchoolSensorDescription(
        key=KEY_UNREAD_FORUM_POSTS,
        value_fn=lambda school, listed, info: _notice_count(school.unread_forum_posts),
        attributes_fn=lambda school, listed, info: _notice_attributes(ATTR_FORUMS, school.unread_forum_posts),
        module=MODULE_FORUMS,
    ),
    SchoolSensorDescription(
        key=KEY_TEXTS,
        value_fn=lambda school, listed, info: _notice_count(school.texts),
        attributes_fn=lambda school, listed, info: _notice_attributes(ATTR_TEXTS, school.texts),
        module=MODULE_TEXTS,
    ),
    SchoolSensorDescription(
        key=KEY_UNREAD_MAIL,
        value_fn=lambda school, listed, info: school.unread_mail,
        mail=True,
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
            if (description.module is None or school.modules.has(description.module))
            and (not description.mail or school.mail)
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
        self._clock_unsub: CALLBACK_TYPE | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._cancel_clock)
        self._follow_clock()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._follow_clock()
        super()._handle_coordinator_update()

    @callback
    def _cancel_clock(self) -> None:
        if self._clock_unsub is not None:
            self._clock_unsub()
            self._clock_unsub = None

    @callback
    def _follow_clock(self) -> None:
        self._cancel_clock()
        state = self.state_of_child
        if not self.entity_description.follows_clock or state is None:
            return
        moment = state.next_boundary(dt_util.now())
        if moment is not None:
            self._clock_unsub = async_track_point_in_utc_time(self.hass, self._clock_reached, dt_util.as_utc(moment))

    @callback
    def _clock_reached(self, _now: datetime) -> None:
        self._clock_unsub = None
        self._follow_clock()
        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        state = self.state_of_child
        if state is None or not state.knows(self.entity_description.field):
            return None
        return self.entity_description.value_fn(state)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.state_of_child
        if state is None or not state.knows(self.entity_description.field):
            return {}
        return self.entity_description.attributes_fn(state)


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
        school = self.coordinator.data.school(self.school_id)
        if listed is None or not school.knows(self.entity_description.field):
            return None
        return self.entity_description.value_fn(school, listed, self.info)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        listed = self.school_info
        school = self.coordinator.data.school(self.school_id)
        if listed is None or not school.knows(self.entity_description.field):
            return {}
        return self.entity_description.attributes_fn(school, listed, self.info)
