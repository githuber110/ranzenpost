from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from homeassistant.components.calendar import DOMAIN as CALENDAR_DOMAIN
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import Child, Event, RanzenpostError, SchoolInfo
from .const import (
    ATTR_END,
    ATTR_KIND,
    ATTR_NAME,
    ATTR_START,
    ATTR_SUBJECT,
    ATTR_SUBJECT_CODE,
    ATTR_SUMMARY,
    CALENDAR_MODULES,
    CHILD_CALENDAR_KINDS,
    KIND_HOLIDAYS,
    OPT_IN_CALENDAR_KINDS,
    UPCOMING_WINDOW_DAYS,
)
from .coordinator import RanzenpostConfigEntry, RanzenpostCoordinator, selected_children
from .entity import RanzenpostChildEntity, RanzenpostSchoolEntity

_LOGGER = logging.getLogger(__name__)
SCHOOL_CHILD_ID = ""


async def async_setup_entry(
    hass: HomeAssistant, entry: RanzenpostConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    info = coordinator.data.info
    entities: list[CalendarEntity] = [RanzenpostSchoolCalendar(coordinator, school) for school in info.schools]
    for child in selected_children(info, entry):
        modules = info.modules_of(child)
        school = info.school_of(child)
        kinds = CHILD_CALENDAR_KINDS + (OPT_IN_CALENDAR_KINDS if school is not None and school.own_entries else ())
        entities.extend(
            RanzenpostChildCalendar(coordinator, child, kind)
            for kind in kinds
            if modules.has(CALENDAR_MODULES[kind])
        )
    async_add_entities(entities)


@dataclass
class RanzenpostCalendarEvent(CalendarEvent):
    color: str = ""
    cancelled: bool = False
    subject_code: str = ""
    subject: str = ""
    name: str = ""
    kind: str = ""


def to_calendar_event(event: Event) -> RanzenpostCalendarEvent:
    return RanzenpostCalendarEvent(
        start=event.start,
        end=event.end,
        summary=event.summary,
        description=event.description or None,
        location=event.location or None,
        uid=event.uid,
        color=event.color,
        cancelled=event.cancelled,
        subject_code=event.subject_code,
        subject=event.subject,
        name=event.name,
        kind=event.kind,
    )


def upcoming_attributes(event: Event | None) -> dict[str, object]:
    if event is None:
        return {}
    return {
        ATTR_SUMMARY: event.summary,
        ATTR_START: event.start.isoformat(),
        ATTR_END: event.end.isoformat(),
        ATTR_SUBJECT: event.subject,
        ATTR_SUBJECT_CODE: event.subject_code,
        ATTR_NAME: event.name,
        ATTR_KIND: event.kind,
    }


def _moment(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return dt_util.as_utc(value)
    return dt_util.as_utc(dt_util.start_of_local_day(value))


def _overlaps(event: Event, start: datetime, end: datetime) -> bool:
    return _moment(event.start) < end and _moment(event.end) > start


def _is_active(event: Event, now: datetime) -> bool:
    return _moment(event.start) <= now < _moment(event.end)


def _upcoming_event(events: list[Event], now: datetime) -> Event | None:
    candidates = [event for event in events if not event.cancelled]
    for event in candidates:
        if _is_active(event, now):
            return event
    future = [event for event in candidates if _moment(event.start) > now]
    return min(future, key=lambda event: _moment(event.start), default=None)


class RanzenpostCalendarMixin(CalendarEntity):
    coordinator: RanzenpostCoordinator
    child_key: str
    school_query: str
    kind: str

    def _init_calendar(self) -> None:
        self._upcoming: list[Event] = []

    @property
    def event(self) -> CalendarEvent | None:
        upcoming = _upcoming_event(self._upcoming, dt_util.utcnow())
        return to_calendar_event(upcoming) if upcoming else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return upcoming_attributes(_upcoming_event(self._upcoming, dt_util.utcnow()))

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        first = dt_util.as_local(start_date).date()
        last = dt_util.as_local(end_date).date()
        events = await self.coordinator.events.events(self.child_key, self.kind, first, last, self.school_query)
        return [
            to_calendar_event(event)
            for event in events
            if _overlaps(event, dt_util.as_utc(start_date), dt_util.as_utc(end_date))
        ]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.hass.async_create_task(self._async_refresh_upcoming())

    @callback
    def _handle_coordinator_update(self) -> None:
        super()._handle_coordinator_update()
        self.hass.async_create_task(self._async_refresh_upcoming())

    async def _async_refresh_upcoming(self) -> None:
        today = dt_util.now().date()
        try:
            self._upcoming = await self.coordinator.events.events(
                self.child_key, self.kind, today, today + timedelta(days=UPCOMING_WINDOW_DAYS), self.school_query
            )
        except RanzenpostError as err:
            _LOGGER.debug("the upcoming events for %s could not be refreshed: %s", self.entity_id, err)
        self.async_write_ha_state()


class RanzenpostChildCalendar(RanzenpostCalendarMixin, RanzenpostChildEntity):
    def __init__(self, coordinator: RanzenpostCoordinator, child: Child, kind: str) -> None:
        super().__init__(coordinator, CALENDAR_DOMAIN, child, kind)
        self.child_key = child.key
        self.school_query = ""
        self.kind = kind
        self._init_calendar()


class RanzenpostSchoolCalendar(RanzenpostCalendarMixin, RanzenpostSchoolEntity):
    def __init__(self, coordinator: RanzenpostCoordinator, school: SchoolInfo) -> None:
        super().__init__(coordinator, CALENDAR_DOMAIN, school, KIND_HOLIDAYS)
        self.child_key = SCHOOL_CHILD_ID
        self.school_query = school.id
        self.kind = KIND_HOLIDAYS
        self._init_calendar()
