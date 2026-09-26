import json
import logging
import threading
from collections import namedtuple

from .child_service import connection_marker
from .iserv.dsa import SCHOOL_APP_EXPIRED_KEY, name_words, parse_period_slots
from .iserv.errors import DataError, OutageError
from .iserv.timetable import TIME_TABLE_SOURCE, TIMETABLE_SHAPE_KEY, display_rows
from .store import edit_config

logger = logging.getLogger(__name__)

SOURCE_KEY = "timetable_source"
SCHOOL_APP_SOURCE = "school-app"
RECHECK_SECONDS = 3600
MATCH_SECONDS = 600
LOGGED_DETAIL_LEFT_OUT = ("refusal",)

Reading = namedtuple("Reading", "week source slots")


class Absent:
    def __init__(self, reason):
        self.reason = reason


def has_lessons(week):
    return bool(display_rows(week))


def _covered(words, others):
    return all(any(other.startswith(word) for other in others) for word in words)


def names_agree(first, second):
    one, two = name_words(first), name_words(second)
    if not one or not two:
        return True
    if len(one) == len(two):
        return _covered(one, two) or _covered(two, one)
    shorter, longer = (one, two) if len(one) < len(two) else (two, one)
    return _covered(shorter, longer)


def fresh_error(error):
    return DataError(str(error), message_key=error.message_key, detail=dict(error.detail))


def matching_option(options, child_id, name, listed_count):
    options = [option for option in options if option.child_id]
    by_id = [option for option in options if option.child_id == str(child_id)]
    if len(by_id) == 1:
        return by_id[0] if names_agree(by_id[0].name, name) else None
    wanted = name_words(name)
    if wanted:
        exact = [option for option in options if name_words(option.name) == wanted]
        if exact:
            return exact[0] if len(exact) == 1 else None
        wider = [option for option in options if wanted < name_words(option.name)]
        if wider:
            return wider[0] if len(wider) == 1 else None
    if len(options) == 1 and listed_count == 1 and names_agree(options[0].name, name):
        return options[0]
    return None


def unmatched_child(page, listed_count):
    return DataError(
        "no child of the time-table page matches the listed child",
        message_key=TIMETABLE_SHAPE_KEY,
        detail={
            "source": TIME_TABLE_SOURCE,
            "child_select": bool(page.select),
            "options": len(page.children),
            "listed_children": listed_count,
        },
    )


def diagnosis_text(error):
    detail = {
        key: value
        for key, value in (getattr(error, "detail", None) or {}).items()
        if key not in LOGGED_DETAIL_LEFT_OUT
    }
    return json.dumps(detail, sort_keys=True, ensure_ascii=True)


def _yes_no(value):
    return "yes" if value else "no"


class TimetableSources:
    def __init__(self, connection):
        self.connection = connection
        self._lock = threading.Lock()
        self._checked_at = None
        self._matches = {}
        self._notes = {}
        self._vacations = None
        self._announced = False

    def reset(self):
        with self._lock:
            self._checked_at = None
            self._matches = {}
            self._notes = {}
            self._vacations = None
            self._announced = False

    def _note(self, key, message, *args, level=logging.INFO):
        now = self.connection.clock()
        with self._lock:
            stamp = self._notes.get((key, args))
            if stamp is not None and now - stamp < RECHECK_SECONDS:
                return
            self._notes[(key, args)] = now
        logger.log(level, "school#%s " + message, self.connection.id, *args)

    def _marker(self):
        return connection_marker(self.connection.store.load_config(), getattr(self.connection, "login_revision", None))

    def remembered(self):
        return self.connection.store.load_config().get(SOURCE_KEY) == TIME_TABLE_SOURCE

    def _store_source(self, value, why, marker):
        stored = []

        def change(config):
            if connection_marker(config) != marker:
                return
            stored.append(True)
            if (config.get(SOURCE_KEY) or "") != value:
                config[SOURCE_KEY] = value

        edit_config(self.connection.store, change)
        if stored:
            logger.info("school#%s timetable source: %s (%s)", self.connection.id, value or SCHOOL_APP_SOURCE, why)
        else:
            logger.info("school#%s timetable source not stored, the connection changed during the read", self.connection.id)

    def _recheck_due(self):
        now = self.connection.clock()
        with self._lock:
            due = self._checked_at is None or self._vacations is None or now - self._checked_at >= RECHECK_SECONDS
            announce = not self._announced
            self._announced = True
        if announce:
            logger.info(
                "school#%s timetable source time-table remembered, the school app is asked again every %d s",
                self.connection.id, RECHECK_SECONDS,
            )
        return due

    def _slots(self):
        try:
            return self.connection._dsa().timetable_slots_or_raise()
        except Exception as error:
            logger.info("school#%s timetable slots unknown: %s", self.connection.id, type(error).__name__)
            return None

    def _school_week(self, target, course_ids):
        school = self.connection._school_timetable(target, course_ids)
        with self._lock:
            self._checked_at = self.connection.clock()
            self._vacations = list(getattr(school, "vacations", None) or [])
        return school

    def _time_table_reading(self, week, slots):
        with self._lock:
            vacations = list(self._vacations or [])
        week.vacations = vacations
        return Reading(week, TIME_TABLE_SOURCE, slots)

    def read(self, child_id, child, target):
        course_ids = (child or {}).get("course_ids")
        if not course_ids:
            page_id = self.connection._child_service.timetable_page_id(child_id)
            return Reading(self.connection._session().get_timetable(page_id, target), TIME_TABLE_SOURCE, None)
        marker = self._marker()
        raw_slots = self._slots()
        slots = parse_period_slots(raw_slots) if raw_slots is not None else None
        remembered = self.remembered()
        if remembered and raw_slots:
            self._store_source("", "the school app lists lesson slots", marker)
            remembered = False
        if remembered and not self._recheck_due():
            week = self._time_table_week(child_id, child, target)
            if week is not None:
                return self._time_table_reading(week, slots)
            self._store_source("", "the time-table module is absent", marker)
            remembered = False
        school = self._school_week(target, course_ids)
        if has_lessons(school):
            if remembered:
                self._store_source("", "the school app lists lessons", marker)
            return Reading(school, SCHOOL_APP_SOURCE, slots)
        week_key = school.start_date
        slot_count = "unknown" if raw_slots is None else len(raw_slots)
        if raw_slots:
            self._note("empty", "school app timetable empty (entries 0, slots %s) for the week of %s, no lessons that week", slot_count, week_key)
            return Reading(school, SCHOOL_APP_SOURCE, slots)
        self._note("fallback", "school app timetable empty (entries 0, slots %s), trying the time-table module", slot_count)
        week = self._time_table_week(child_id, child, target)
        if week is None:
            self._note("absent", "the week of %s has no lessons", week_key)
            if remembered:
                self._store_source("", "the time-table module is absent", marker)
            return Reading(school, SCHOOL_APP_SOURCE, slots)
        if has_lessons(week) and not remembered:
            self._store_source(TIME_TABLE_SOURCE, "the school app lists no lessons and no slots", marker)
            remembered = True
        if not remembered:
            self._note("empty-both", "time-table module lists no lessons either, the week of %s has no lessons", week_key)
            return Reading(school, SCHOOL_APP_SOURCE, slots)
        self._note("chosen", "timetable source time-table chosen for the week of %s", week_key)
        return self._time_table_reading(week, slots)

    def _time_table_week(self, child_id, child, target):
        client = self.connection._session()
        try:
            chosen = self._time_table_id(client, str(child_id), child)
            if chosen is None:
                return None
            week = client.read_time_table_week(chosen, target)
        except OutageError:
            raise
        except DataError as error:
            if error.message_key == SCHOOL_APP_EXPIRED_KEY:
                self.connection._forget_session(client)
            self._note(
                "unreadable",
                "time-table module unreadable (%s): %s",
                error.message_key or type(error).__name__, diagnosis_text(error),
                level=logging.WARNING,
            )
            raise
        answer = getattr(week, "answer", None) or {}
        self._note(
            "data",
            "time-table data answered %s %s, lessons %d for the week of %s",
            answer.get("status", "-"), answer.get("content_type") or "-", len(display_rows(week)), week.start_date,
        )
        return week

    def _cached_match(self, child_id, now):
        with self._lock:
            known = self._matches.get(child_id)
        if known is None or now - known[0] > MATCH_SECONDS:
            return None
        return known

    def _remember_match(self, child_id, now, outcome):
        with self._lock:
            self._matches[child_id] = (now, outcome)

    def _time_table_id(self, client, child_id, child):
        now = self.connection.clock()
        known = self._cached_match(child_id, now)
        if known is not None:
            outcome = known[1]
            if isinstance(outcome, DataError):
                raise fresh_error(outcome)
            return None if isinstance(outcome, Absent) else outcome
        page = client.read_time_table_page()
        if page.absent:
            self._note("module-absent", "time-table module absent for this account (%s)", page.absent)
            self._remember_match(child_id, now, Absent(page.absent))
            return None
        listed = self.connection._child_service.listed_count()
        chosen = None
        if page.select:
            option = matching_option(page.children, child_id, (child or {}).get("name"), listed)
            chosen = option.child_id if option is not None else None
        elif listed == 1:
            chosen = ""
        logger.info(
            "school#%s time-table child select: %s, options %d, listed children %d, matched %s",
            self.connection.id, "present" if page.select else "none", len(page.children), listed, _yes_no(chosen is not None),
        )
        if chosen is None:
            failure = unmatched_child(page, listed)
            self._remember_match(child_id, now, failure)
            raise failure
        self._remember_match(child_id, now, chosen)
        return chosen
