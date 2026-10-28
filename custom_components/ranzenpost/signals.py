from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant, callback

from .api import Absence, Change, Info, Notice, Notices, School, SchoolInfo, State
from .const import (
    ATTR_CHILD_KEY,
    ATTR_COUNT,
    ATTR_DATE,
    ATTR_END,
    ATTR_ENTRY_ID,
    ATTR_ID,
    ATTR_LAST_UPDATED,
    ATTR_PERIOD,
    ATTR_PREVIOUS_STATUS,
    ATTR_SCHOOL_ID,
    ATTR_SENDER,
    ATTR_SOURCE,
    ATTR_START,
    ATTR_STATUS,
    ATTR_SUMMARY,
    ATTR_TEXT,
    ATTR_TITLE,
    ATTR_TYPE,
    CHANGE_CANCELLATION,
    CHANGE_SUBSTITUTION,
    EVENT_RANZENPOST,
    STATUS_AUTH_FAILED,
    STATUS_UNREACHABLE,
    TRIGGER_ABSENCE_STATUS_CHANGED,
    TRIGGER_LESSON_CANCELLED,
    TRIGGER_LOGIN_NEEDED,
    TRIGGER_NEW_LETTER,
    TRIGGER_NEW_POST,
    TRIGGER_SCHOOL_NEW_LETTER,
    TRIGGER_SCHOOL_NEW_NEWS,
    TRIGGER_SCHOOL_NEW_FORUM_POST,
    TRIGGER_SCHOOL_NEW_TEXT,
    TRIGGER_SCHOOL_NEW_POST,
    TRIGGER_SCHOOL_NEW_TASK,
    TRIGGER_SCHOOL_REACHABLE,
    TRIGGER_SCHOOL_UNREACHABLE,
    TRIGGER_SUBSTITUTION,
    TRIGGER_TIMETABLE_CHANGED,
)
from .devices import child_key_identifier, device_id_of, school_identifier

ATTR_DEVICE_ID = "device_id"
CHANGE_TRIGGERS = {CHANGE_CANCELLATION: TRIGGER_LESSON_CANCELLED, CHANGE_SUBSTITUTION: TRIGGER_SUBSTITUTION}


@dataclass(frozen=True)
class Signal:
    type: str
    school_id: str
    child_key: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _notice_key(notice: Notice, by_id: bool = True) -> tuple[str, ...]:
    if notice.id and by_id:
        return (notice.id,)
    return (notice.title, notice.sender, _iso(notice.date))


def _notice_data(item: Notice) -> dict[str, Any]:
    data = {ATTR_TITLE: item.title, ATTR_SENDER: item.sender, ATTR_DATE: _iso(item.date)}
    for name in (ATTR_ID, ATTR_TEXT):
        if getattr(item, name):
            data[name] = getattr(item, name)
    return data


def _new_notices(previous: Notices | None, current: Notices | None) -> list[dict[str, Any]]:
    if previous is None or current is None:
        return []
    if current.fresh is not None:
        floor = max((item.seen for item in previous.fresh or ()), default=0)
        return [_notice_data(item) for item in sorted(current.fresh, key=lambda item: item.seen) if item.seen > floor]
    if current.ids is not None and previous.ids is not None:
        known_ids = set(previous.ids)
        listed = {item.id: item for item in current.items if item.id}
        return [_notice_data(listed[item]) if item in listed else {ATTR_ID: item} for item in current.ids if item not in known_ids]
    by_id = all(item.id for item in (*previous.items, *current.items))
    known = {_notice_key(item, by_id) for item in previous.items}
    fresh = [item for item in current.items if _notice_key(item, by_id) not in known]
    if fresh:
        return [_notice_data(item) for item in fresh]
    if current.count > previous.count:
        return [{ATTR_COUNT: current.count}]
    return []


def _absence_key(absence: Absence) -> tuple[str, str, str | None, str | None]:
    return (absence.kind, absence.summary, _iso(absence.start), _iso(absence.end))


def _change_data(change: Change) -> dict[str, Any]:
    return {ATTR_SUMMARY: change.summary, ATTR_DATE: _iso(change.date), ATTR_PERIOD: change.period}


def change_signals(child_key: str, school_id: str, new_changes: list[Change]) -> list[Signal]:
    return [
        Signal(CHANGE_TRIGGERS[change.kind], school_id, child_key, _change_data(change))
        for change in new_changes
        if change.child_key == child_key and change.kind in CHANGE_TRIGGERS
    ]


def child_signals(
    child_key: str, school_id: str, previous: State, current: State, new_changes: list[Change]
) -> list[Signal]:
    signals: list[Signal] = []
    if current.timetable_last_updated != previous.timetable_last_updated:
        data = {ATTR_LAST_UPDATED: _iso(current.timetable_last_updated), ATTR_SOURCE: current.timetable_last_updated_source}
        signals.append(Signal(TRIGGER_TIMETABLE_CHANGED, school_id, child_key, data))
    signals.extend(change_signals(child_key, school_id, new_changes))
    for data in _new_notices(previous.unread_letters, current.unread_letters):
        signals.append(Signal(TRIGGER_NEW_LETTER, school_id, child_key, data))
    for data in _new_notices(previous.unread_posts, current.unread_posts):
        signals.append(Signal(TRIGGER_NEW_POST, school_id, child_key, data))
    before = {_absence_key(absence): absence.status for absence in previous.open_absences}
    for absence in current.open_absences:
        status_before = before.get(_absence_key(absence))
        if status_before is not None and status_before != absence.status:
            data = {
                ATTR_SUMMARY: absence.summary,
                ATTR_START: _iso(absence.start),
                ATTR_END: _iso(absence.end),
                ATTR_STATUS: absence.status,
                ATTR_PREVIOUS_STATUS: status_before,
            }
            signals.append(Signal(TRIGGER_ABSENCE_STATUS_CHANGED, school_id, child_key, data))
    return signals


def school_signals(previous: SchoolInfo, current: SchoolInfo) -> list[Signal]:
    signals: list[Signal] = []
    data = {ATTR_STATUS: current.status}
    if current.status == STATUS_UNREACHABLE and previous.status != STATUS_UNREACHABLE:
        signals.append(Signal(TRIGGER_SCHOOL_UNREACHABLE, current.id, "", data))
    if previous.status == STATUS_UNREACHABLE and current.status != STATUS_UNREACHABLE:
        signals.append(Signal(TRIGGER_SCHOOL_REACHABLE, current.id, "", data))
    if current.status == STATUS_AUTH_FAILED and previous.status != STATUS_AUTH_FAILED:
        signals.append(Signal(TRIGGER_LOGIN_NEEDED, current.id, "", data))
    return signals


def school_notice_signals(school_id: str, previous: School, current: School) -> list[Signal]:
    signals: list[Signal] = []
    for trigger, before, now in (
        (TRIGGER_SCHOOL_NEW_LETTER, previous.unread_letters, current.unread_letters),
        (TRIGGER_SCHOOL_NEW_POST, previous.unread_posts, current.unread_posts),
        (TRIGGER_SCHOOL_NEW_TASK, previous.open_tasks, current.open_tasks),
        (TRIGGER_SCHOOL_NEW_NEWS, previous.news, current.news),
        (TRIGGER_SCHOOL_NEW_FORUM_POST, previous.unread_forum_posts, current.unread_forum_posts),
        (TRIGGER_SCHOOL_NEW_TEXT, previous.texts, current.texts),
    ):
        signals.extend(Signal(trigger, school_id, "", data) for data in _new_notices(before, now))
    return signals


def signals_between(
    previous_info: Info | None,
    previous_states: dict[str, State],
    info: Info,
    states: dict[str, State],
    new_changes: list[Change],
    previous_schools: dict[str, School] | None = None,
    schools: dict[str, School] | None = None,
) -> list[Signal]:
    if previous_info is None:
        return [
            signal
            for child in info.children
            if child.key in states
            for signal in change_signals(child.key, child.school_id, new_changes)
        ]
    signals: list[Signal] = []
    for school in info.schools:
        before = previous_info.school(school.id)
        if before is not None:
            signals.extend(school_signals(before, school))
        known = (previous_schools or {}).get(school.id)
        current = (schools or {}).get(school.id)
        if known is not None and current is not None:
            signals.extend(school_notice_signals(school.id, known, current))
    for child in info.children:
        before = previous_states.get(child.key)
        current = states.get(child.key)
        if before is not None and current is not None:
            signals.extend(child_signals(child.key, child.school_id, before, current, new_changes))
        elif current is not None:
            signals.extend(change_signals(child.key, child.school_id, new_changes))
    return signals


@callback
def async_fire_signals(hass: HomeAssistant, entry_id: str, signals: list[Signal]) -> None:
    for signal in signals:
        if signal.child_key:
            identifier = child_key_identifier(entry_id, signal.child_key)
        else:
            identifier = school_identifier(entry_id, signal.school_id)
        device_id = device_id_of(hass, entry_id, identifier)
        if device_id is None:
            continue
        hass.bus.async_fire(
            EVENT_RANZENPOST,
            {
                ATTR_DEVICE_ID: device_id,
                ATTR_TYPE: signal.type,
                ATTR_ENTRY_ID: entry_id,
                ATTR_SCHOOL_ID: signal.school_id,
                ATTR_CHILD_KEY: signal.child_key,
                **signal.data,
            },
        )
