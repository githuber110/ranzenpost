import copy
import hashlib
import json
import logging
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import courses, feed, holidays, integration, marks, messages, modules
from .failure import error_kind
from .iserv.dsa import student_for_name
from .iserv.messenger import STAGE_NO_CREDENTIALS, MessengerStageError
from .iserv.errors import (
    LOGIN_SESSION_KEY,
    LOGIN_TWOFACTOR_KEY,
    REASON_BAD_CREDENTIALS,
    REASON_CODE_STEP_FAILED,
    REASON_DEFAULT_PASSWORD,
    REASON_LOCKED,
    REASON_SESSION_NOT_OPENED,
    REASON_TWOFACTOR_SETUP,
    REASON_UNKNOWN_ACCOUNT,
    DataError,
    LoginError,
    OutageError,
    TwoFactorError,
    code_step_failed,
    login_reason,
    session_never_opened,
)
from .logfile import timeline
from .namebook import current as current_namebook
from .not_configured import ConnectionChangedError
from .service import LETTERS_CHILD_PREFIX, child_list_state
from .store import (
    CHILDREN_REFUSED,
    child_key as make_child_key,
    connection_known,
    directory_key,
    edit,
    edit_config,
    rebase,
    split_child_key,
)
from .subscriptions import COMPONENT_ABSENCES, child_first_name

logger = logging.getLogger(__name__)

ABSENCE_FIELDS = (
    "id",
    "kind",
    "target",
    "label_key",
    "target_key",
    "status",
    "from_date",
    "till_date",
    "from_period",
    "till_period",
    "subject",
    "comment",
)

BAD_CREDENTIALS_KEY = "notify.auth.badCredentials"
AUTH_NOTIFY_KEYS = {
    REASON_BAD_CREDENTIALS: BAD_CREDENTIALS_KEY,
    REASON_UNKNOWN_ACCOUNT: "api.login.unknownAccount",
    REASON_DEFAULT_PASSWORD: "api.login.defaultPassword",
    REASON_TWOFACTOR_SETUP: "api.login.twofactorSetup",
    REASON_LOCKED: "api.login.locked",
}
CODE_REPAIR_KEY = LOGIN_TWOFACTOR_KEY
LETTERS_KEY = "notify.letters.new"
PINBOARD_KEY = "notify.pinboard.new"
CONFERENCES_KEY = "notify.conferences.new"
TIMETABLE_KEY = "notify.timetable.changes"
TIMETABLE_MOVED_KEY = "notify.timetable.changesMoved"
TIMETABLE_CLEARED_KEY = "notify.timetable.cleared"
TIMETABLE_PLAN_KEY = "notify.timetable.plan"
TIMETABLE_COURSES_KEY = "notify.timetable.courses"
PUSH_VIEW_KEY = "push_view"
COURSE_HINT_KEY = "course_hint_sent"
PARALLEL_PENDING = "parallel_pending"
MESSENGER_KEY = "notify.messenger.unread"
SCHOOL_TAG_KEY = "notify.school.tag"
PLAN_ORIGIN_FIELDS = ("date", "period", "subject_code", "teacher_code", "room")
PLAN_FIELDS_KEY = "plan_fields"
PLAN_FIELD_HASH_LENGTH = 12
COURSE_SIGNATURE = "course_signature"
SOURCE_STATE_KEY = "timetable_source"
CHANGES_FORMAT_KEY = "changes_format"
DEFAULT_SOURCE = "school-app"
AUTH_NOTIFIED_FLAG = "auth_incident_sent"
AUTH_NOTIFIED_REASON = "auth_incident_reason"
LEGACY_AUTH_FLAG = "auth_incident"
OWNED_CONFIG_KEYS = ("poll_state", AUTH_NOTIFIED_FLAG, AUTH_NOTIFIED_REASON, LEGACY_AUTH_FLAG)
OUTAGE_SINCE_KEY = "notify.outage.since"
OUTAGE_BACK_KEY = "notify.outage.back"
OUTAGE_PUSH_AFTER_SECONDS = 12 * 60 * 60
SNAPSHOT_FIELD_DEPTH = 4
_SCHOOL_LOCKS = {}
_SCHOOL_LOCKS_GUARD = threading.Lock()
DEFAULT_POLL_INTERVAL = 1800
SESSION_FAILURE_KIND = f"TwoFactorError/{LOGIN_SESSION_KEY}"
SESSION_HELD_KIND = "held after a session that never opened"
CODE_FAILURE_KIND = f"TwoFactorError/{LOGIN_TWOFACTOR_KEY}"
CODE_HELD_KIND = "code refused since the last sign-in"
SUMMARY_KEYS = {"letters": "letters", "pinboard": "posts", "conferences": "conferences"}


def plan_fields(lessons):
    fields = {}
    for field in PLAN_ORIGIN_FIELDS:
        fields[field] = sorted(
            hashlib.sha256(
                json.dumps([field, item.get(field)], ensure_ascii=False).encode("utf-8")
            ).hexdigest()[:PLAN_FIELD_HASH_LENGTH]
            for item in lessons
        )
    return fields


def plan_field_differences(previous, current):
    if not isinstance(previous, dict):
        return None
    found = []
    for field in PLAN_ORIGIN_FIELDS:
        before = Counter(previous.get(field) or [])
        after = Counter(current.get(field) or [])
        count = max(sum((before - after).values()), sum((after - before).values()))
        if count:
            found.append((field, count))
    return found


def describe_plan_differences(found):
    if found is None:
        return "no field detail stored yet"
    if not found:
        return "no plan field differs"
    return ", ".join(f"{field} differs in {count} lessons" for field, count in found)


def moved_in(changes):
    return any(isinstance(item, dict) and item.get("moved") for item in changes or [])


def push_view_of(timetable):
    info = timetable.get("courses") or {}
    if info.get("chosen") or not info.get("parallel"):
        return timetable, False
    parallel = courses.parallel_keys(timetable.get("lessons") or [])
    return courses.apply(timetable, {"chosen": [], "known": sorted(parallel)}), True


def school_lock(store, connection_id):
    directory = getattr(store, "dir", None)
    key = (directory_key(directory) if directory else str(id(store)), str(connection_id or ""))
    with _SCHOOL_LOCKS_GUARD:
        return _SCHOOL_LOCKS.setdefault(key, threading.Lock())


def save_owned_config(store, config):
    def change(fresh):
        for key in OWNED_CONFIG_KEYS:
            if key in config:
                fresh[key] = config[key]
            else:
                fresh.pop(key, None)

    edit_config(store, change)


class Poller:
    def __init__(
        self,
        service,
        notifier=None,
        store=None,
        notifiers=None,
        registry=None,
        holiday_calendar=None,
        clock=None,
        poll_interval=DEFAULT_POLL_INTERVAL,
    ):
        self.service = service
        self.poll_interval = int(poll_interval or DEFAULT_POLL_INTERVAL)
        self.notifier = notifier
        self.notifiers = dict(notifiers or {})
        given = store if store is not None else getattr(service, "store", None)
        self._given_store = given
        self.store = getattr(given, "base", given)
        self.registry = registry
        self.holiday_calendar = holiday_calendar
        self.clock = clock or time.time

    def _scoped_store(self, connection):
        if getattr(self._given_store, "base", None) is not None:
            return self._given_store
        connection_id = str(getattr(connection, "id", "") or "")
        scoped = getattr(self.store, "connection_store", None)
        if connection_id and callable(scoped):
            return scoped(connection_id)
        return self.store

    def _targets(self):
        listed = getattr(self.service, "connections", None)
        if callable(listed):
            return [(connection, connection.store) for connection in listed()]
        return [(self.service, self._scoped_store(self.service))]

    def _notify(self, event, name, message, trigger):
        target = self.notifiers.get(event)
        if target is None and event == "timetable":
            target = self.notifier
        if target is None:
            return False
        logger.info("push %s %s", event, trigger)
        return target(name, message)

    def _subscribed_children(self, component):
        if self.registry is None or self.store is None:
            return set()
        reader = getattr(self.registry, "children_with_component", None)
        if not callable(reader):
            return set()
        try:
            return {key for key in reader(component) if key}
        except Exception:
            return set()

    def _marked_children(self):
        if self.store is None:
            return set()
        reader = getattr(self.store, "load_marks", None)
        if not callable(reader):
            return set()
        try:
            return {
                entry.get("child_key")
                for entry in marks.entries_of(reader())
                if entry.get("child_key")
            }
        except Exception:
            return set()

    def _feed_children(self):
        if self.registry is None or self.store is None:
            return set()
        try:
            timetable = {key for key in self.registry.children_with_timetable() if key}
        except Exception:
            return set()
        return timetable | self._marked_children()

    def _absence_children(self):
        return self._subscribed_children(COMPONENT_ABSENCES)

    def _collect_feed_weeks(self, connection, child_id, current):
        weeks = [current]
        for offset in range(1, feed.WEEKS_AHEAD + 1):
            try:
                weeks.append(connection.timetable(child_id, week_offset=offset))
            except OutageError:
                raise
            except Exception as error:
                logger.warning(
                    "poll school#%s timetable child#%s week %d failed: %s, keeping the earlier weeks",
                    getattr(connection, "id", ""), child_id, offset, error_kind(error),
                )
                break
        return weeks

    def _store_feed_weeks(self, snapshot, child_key, weeks, now):
        children = snapshot.setdefault("children", {})
        entry = children.setdefault(child_key, {})
        stored = entry.get("weeks")
        stored = dict(stored) if isinstance(stored, dict) else {}
        for data in weeks:
            key = str((data or {}).get("start_date") or "")
            if not key:
                continue
            stored[key] = {
                "start_date": key,
                "end_date": (data or {}).get("end_date", ""),
                "lessons": (data or {}).get("lessons") or [],
                "fetched_at": now,
            }
        entry["weeks"] = self._prune_weeks(stored)
        entry["last_success"] = now
        return snapshot

    def _connection_for_key(self, child_key):
        connection_id, child_id = split_child_key(child_key)
        for connection, store in self._targets():
            if getattr(connection, "id", "") == connection_id:
                return connection, store, child_id
        return None, None, ""

    def refresh_child(self, child_key):
        if self.store is None or not child_key:
            return False
        connection, store, child_id = self._connection_for_key(child_key)
        if connection is None or str(child_id).startswith(LETTERS_CHILD_PREFIX):
            return False
        if not modules.registry_of(connection)["modules"][modules.TIMETABLE]:
            return False
        connection_id = str(getattr(connection, "id", "") or "")
        with school_lock(self.store, connection_id):
            try:
                current = connection.timetable(child_id)
            except Exception:
                return False
            try:
                weeks = self._collect_feed_weeks(connection, child_id, current)
            except OutageError:
                weeks = [current]
            now = int(self.clock())

            def change(snapshot):
                if connection_known(self.store, connection_id):
                    self._store_feed_weeks(snapshot, child_key, weeks, now)

            edit(self.store, self.store.load_calendar_snapshot, self.store.save_calendar_snapshot, change)
        self._warm_holidays(store)
        return True

    def _commit_snapshot(self, baseline, snapshot, connection_id=""):
        def change(fresh):
            merged = rebase(fresh, baseline, snapshot, SNAPSHOT_FIELD_DEPTH)
            children = merged.get("children")
            if connection_id and isinstance(children, dict) and not connection_known(self.store, connection_id):
                merged["children"] = {
                    key: value for key, value in children.items() if split_child_key(key)[0] != connection_id
                }
            fresh.clear()
            fresh.update(merged)

        edit(self.store, self.store.load_calendar_snapshot, self.store.save_calendar_snapshot, change)

    def _today(self):
        return holidays.berlin_today(
            datetime.fromtimestamp(self.clock(), timezone.utc).replace(tzinfo=None)
        )

    def _prune_weeks(self, stored):
        window = feed.lesson_window(self._today())
        first = window[0] - timedelta(days=7)
        kept = {}
        for key, value in stored.items():
            day = holidays.parse_day(key)
            if day is None or day < first or day > window[1]:
                continue
            kept[key] = value
        return kept

    def _warm_holidays(self, store):
        if self.holiday_calendar is None:
            return
        today = self._today()
        window = feed.lesson_window(today)
        config = store.load_config() if store is not None else None
        try:
            self.holiday_calendar.range_info(
                window[0], today + timedelta(days=feed.HOLIDAY_DAYS_AHEAD), config
            )
        except Exception:
            pass

    def _registry(self, connection):
        refresh = getattr(connection, "refresh_modules", None)
        if not callable(refresh):
            return modules.registry_of(connection)
        try:
            return modules.normalize(refresh())
        except (LoginError, OutageError):
            raise
        except Exception as error:
            if session_never_opened(error) or code_step_failed(error):
                raise
            return modules.registry_of(connection)

    def _can_clear_snapshot(self):
        return self.store is not None and callable(getattr(self.store, "load_calendar_snapshot", None))

    @staticmethod
    def _clear_missing(snapshot, flags, connection_id):
        cleared = False
        for key, holder in (snapshot.get("children") or {}).items():
            if not isinstance(holder, dict) or split_child_key(key)[0] != connection_id:
                continue
            if not flags[modules.TIMETABLE] and holder.get("weeks"):
                holder["weeks"] = {}
                cleared = True
            if not flags[modules.ABSENCES] and holder.get("absences"):
                holder["absences"] = []
                cleared = True
        return cleared

    def _school_tag(self, connection, many):
        if not many:
            return ""
        namer = getattr(connection, "display_name", None)
        if not callable(namer):
            return ""
        try:
            return str(namer() or "")
        except Exception:
            return ""

    def _tagged(self, language, school, message):
        if not school:
            return message
        return messages.text_in(language, SCHOOL_TAG_KEY, {"school": school, "message": message})

    def poll_once(self, connection_id=None):
        started = time.monotonic()
        now_epoch = int(self.clock())
        targets = self._targets()
        many = len(targets) > 1
        wanted = str(connection_id or "")
        if wanted:
            targets = [(connection, store) for connection, store in targets if str(getattr(connection, "id", "") or "") == wanted]
        timeline.info("poll start: %d schools (%s)", len(targets), "school#" + wanted if wanted else "all")
        self._learn_names()
        integration_active = integration.is_active(self.store, now_epoch)
        events = []
        changes = []
        errors = []
        details = []
        for connection, store in targets:
            with school_lock(self.store, getattr(connection, "id", "")):
                if self.store is not None and not connection_known(self.store, getattr(connection, "id", "")):
                    logger.info("poll school#%s skipped: removed", getattr(connection, "id", ""))
                    continue
                try:
                    if self._outage_backoff_active(connection, now_epoch) and not self._retry_now(connection, wanted):
                        outcome = self._skipped_connection(connection)
                        logger.info("poll school#%s skipped: outage backoff", getattr(connection, "id", ""))
                    else:
                        outcome = self._poll_connection(connection, store, now_epoch, integration_active, many)
                except ConnectionChangedError:
                    logger.warning("poll school#%s skipped: changed", getattr(connection, "id", ""))
                    continue
                except OutageError as error:
                    outcome = self._outage_error(connection, store, now_epoch, error)
                except Exception as error:
                    outcome = self._failed_connection(connection, now_epoch, error)
            events.extend(outcome["events"])
            changes.extend(outcome["changes"])
            if outcome["error"]:
                errors.append(outcome["error"])
                details.extend(self._error_details(outcome))
        integration.record_poll(self.store, now_epoch, not errors, errors[0] if errors else "", changes=changes)
        elapsed = int((time.monotonic() - started) * 1000)
        named = f" ({', '.join(details)})" if details else ""
        timeline.info(
            "poll end after %dms: %d schools, %d errors%s, %d changes",
            elapsed, len(targets), len(errors), named, len(changes),
        )
        return events

    @staticmethod
    def _error_details(outcome):
        found = []
        for entry in outcome.get("events") or []:
            if not isinstance(entry, dict) or not (entry.get("error") or entry.get("connection_id") and entry.get("skipped")):
                continue
            area = entry.get("module") or ("timetable" if entry.get("child_key") else "school")
            found.append(f"{area}: {entry.get('kind') or entry.get('error')}")
        return found or [f"school: {outcome['error']}"]

    def _learn_names(self):
        book = current_namebook()
        if book is None or self.store is None:
            return
        try:
            book.learn_store(self.store)
        except Exception:
            logger.debug("the name book could not read the store", exc_info=True)

    def _outage_backoff_active(self, connection, now_epoch):
        connection_id = str(getattr(connection, "id", "") or "")
        return integration.outage_backoff_active(self.store, connection_id, now_epoch)

    def _retry_now(self, connection, wanted):
        connection_id = str(getattr(connection, "id", "") or "")
        if not wanted or integration.outage_rate_limited(self.store, connection_id):
            return False
        integration.lift_outage_backoff(self.store, connection_id)
        return True

    def _skipped_connection(self, connection):
        connection_id = str(getattr(connection, "id", "") or "")
        return {
            "events": [{"connection_id": connection_id, "skipped": integration.ERROR_OUTAGE, "kind": "outage backoff"}],
            "changes": [],
            "error": integration.ERROR_OUTAGE,
        }

    def _outage_error(self, connection, store, now_epoch, error):
        connection_id = str(getattr(connection, "id", "") or "")
        config = store.load_config() if store is not None else {}
        return self._outage_connection(connection, connection_id, now_epoch, config.get("language"), error)

    def _outage_connection(self, connection, connection_id, now_epoch, language, error):
        entered = not integration.school_state(self.store, connection_id).get(integration.OUTAGE_SINCE)
        retry_after = getattr(error, "retry_after", None)
        slot = integration.note_outage(self.store, connection_id, now_epoch, error.reason, self.poll_interval, retry_after)
        if entered:
            logger.info("school %s is unreachable (%s), polling backs off until it answers", connection_id, error.reason)
        logger.warning("poll school#%s outage: %s", connection_id, error_kind(error))
        since = int(slot.get(integration.OUTAGE_SINCE) or now_epoch)
        if not slot.get(integration.OUTAGE_NOTIFIED) and now_epoch - since >= OUTAGE_PUSH_AFTER_SECONDS:
            variables = {"school": self._school_tag(connection, True), "since": integration.berlin_stamp(since)}
            trigger = f"school#{connection_id}: unreachable for {(now_epoch - since) // 3600} hours"
            if self._notify("outage", "", messages.text_in(language, OUTAGE_SINCE_KEY, variables), trigger):
                integration.mark_outage_notified(self.store, connection_id)
        integration.record_school_poll(self.store, connection_id, now_epoch, False, integration.ERROR_OUTAGE)
        return {
            "events": [{"connection_id": connection_id, "error": integration.ERROR_OUTAGE, "reason": error.reason, "kind": error_kind(error)}],
            "changes": [],
            "error": integration.ERROR_OUTAGE,
        }

    def _leave_outage(self, connection, connection_id, now_epoch, language):
        previous = integration.end_outage(self.store, connection_id)
        if previous is None:
            return
        minutes = max(0, now_epoch - int(previous.get(integration.OUTAGE_SINCE) or now_epoch)) // 60
        logger.info("school %s is reachable again after %d minutes", connection_id, minutes)
        if previous.get(integration.OUTAGE_NOTIFIED):
            variables = {"school": self._school_tag(connection, True)}
            self._notify(
                "outage",
                "",
                messages.text_in(language, OUTAGE_BACK_KEY, variables),
                f"school#{connection_id}: reachable again after {minutes} minutes",
            )

    def _session_not_opened(self, connection, connection_id, now_epoch, language, kind, events=(), changes=()):
        logger.warning("poll school#%s sign-in opened no session: %s", connection_id, kind)
        return self._quiet_sign_in_problem(
            connection, connection_id, now_epoch, language, REASON_SESSION_NOT_OPENED, events, changes
        )

    def _code_refused(self, connection, connection_id, now_epoch, language, kind, school, events=(), changes=()):
        logger.warning("poll school#%s sign-in code refused: %s", connection_id, kind)
        self._announce_code_repair(connection, connection_id, language, school)
        return self._quiet_sign_in_problem(
            connection, connection_id, now_epoch, language, REASON_CODE_STEP_FAILED, events, changes
        )

    def _announce_code_repair(self, connection, connection_id, language, school):
        needed = getattr(connection, "code_refusal_needs_setup", None)
        announced = getattr(connection, "code_repair_announced", None)
        note = getattr(connection, "note_code_repair_announced", None)
        if not all(callable(step) for step in (needed, announced, note)) or not needed() or announced():
            return
        text = messages.text_in(language, CODE_REPAIR_KEY)
        trigger = f"school#{connection_id}: sign-in code refused again after its holds"
        if self._notify("auth", "", self._tagged(language, school, text), trigger):
            note()

    def _quiet_sign_in_problem(self, connection, connection_id, now_epoch, language, reason, events=(), changes=()):
        self._leave_outage(connection, connection_id, now_epoch, language)
        integration.record_school_poll(
            self.store, connection_id, now_epoch, False, integration.ERROR_AUTH, auth_reason=reason
        )
        return {
            "events": list(events) + [{"connection_id": connection_id, "error": reason}],
            "changes": list(changes),
            "error": integration.ERROR_AUTH,
        }

    def _failed_connection(self, connection, now_epoch, error):
        connection_id = str(getattr(connection, "id", "") or "")
        logger.warning("the poll of school %s stopped with %s", connection_id, error_kind(error))
        integration.record_school_poll(self.store, connection_id, now_epoch, False, integration.ERROR_NETWORK)
        return {
            "events": [{"connection_id": connection_id, "error": "network", "kind": error_kind(error)}],
            "changes": [],
            "error": integration.ERROR_NETWORK,
        }

    @staticmethod
    def _children_for_poll(connection, connection_id):
        try:
            return connection.children(), None
        except DataError as error:
            stored = getattr(connection, "stored_children", None)
            kept = stored() if callable(stored) else []
            state = child_list_state(error)
            if state == CHILDREN_REFUSED:
                logger.info(
                    "poll school#%s child list refused for this account, polling on with %d stored child(ren)",
                    connection_id,
                    len(kept),
                )
                return kept, {"connection_id": connection_id, "module": "children", "state": state}
            logger.warning("poll school#%s child list unreadable, using the stored one: %s", connection_id, error_kind(error))
            return kept, {"module": "children", "error": str(error), "kind": error_kind(error)}

    def _poll_connection(self, connection, store, now_epoch, integration_active, many):
        connection_id = str(getattr(connection, "id", "") or "")
        config = store.load_config() if store is not None else {}
        language = config.get("language")
        poll_state = dict(config.get("poll_state") or {})
        school = self._school_tag(connection, many)
        feed_children = self._feed_children()
        absence_children = self._absence_children()
        events = []
        changes = []
        summary = {}
        try:
            flags = self._registry(connection)["modules"]
            needs_children = flags[modules.TIMETABLE] or flags[modules.ABSENCES]
            children, child_event = self._children_for_poll(connection, connection_id) if needs_children else ([], None)
        except OutageError as error:
            return self._outage_connection(connection, connection_id, now_epoch, language, error)
        except LoginError as error:
            reason = login_reason(error)
            logger.warning("poll school#%s sign-in failed: %s", connection_id, error_kind(error))
            self._leave_outage(connection, connection_id, now_epoch, language)
            config.pop(LEGACY_AUTH_FLAG, None)
            announced = config.get(AUTH_NOTIFIED_REASON) or REASON_BAD_CREDENTIALS
            if not config.get(AUTH_NOTIFIED_FLAG) or announced != reason:
                text = messages.text_in(language, AUTH_NOTIFY_KEYS.get(reason, BAD_CREDENTIALS_KEY))
                if self._notify("auth", "", self._tagged(language, school, text), f"school#{connection_id}: sign-in {reason}"):
                    config[AUTH_NOTIFIED_FLAG] = True
                    config[AUTH_NOTIFIED_REASON] = reason
            if store is not None:
                save_owned_config(store, config)
            integration.record_school_poll(
                self.store, connection_id, now_epoch, False, integration.ERROR_AUTH, auth_reason=reason
            )
            return {
                "events": [{"connection_id": connection_id, "error": reason}],
                "changes": [],
                "error": integration.ERROR_AUTH,
            }
        except TwoFactorError as error:
            if session_never_opened(error):
                return self._session_not_opened(connection, connection_id, now_epoch, language, error_kind(error))
            if code_step_failed(error):
                return self._code_refused(connection, connection_id, now_epoch, language, error_kind(error), school)
            raise
        self._leave_outage(connection, connection_id, now_epoch, language)
        config.pop(LEGACY_AUTH_FLAG, None)
        config.pop(AUTH_NOTIFIED_FLAG, None)
        config.pop(AUTH_NOTIFIED_REASON, None)
        if child_event is not None:
            events.append(child_event)
        try:
            keyed = []
            for child in children:
                child_id = str(child.get("child_id") or "")
                keyed.append((make_child_key(connection_id, child_id), child_id, child))
            if integration_active:
                known = {key for key, child_id, _ in keyed if child_id}
                feed_children = set(feed_children) | known
                absence_children = set(absence_children) | known
            cleanup = self._can_clear_snapshot() and not (flags[modules.TIMETABLE] and flags[modules.ABSENCES])
            snapshot = (
                self.store.load_calendar_snapshot()
                if ((feed_children or absence_children) and self.store is not None) or cleanup
                else {}
            )
            baseline = copy.deepcopy(snapshot)
            snapshot_dirty = self._clear_missing(snapshot, flags, connection_id) if cleanup else False
            for key, child_id, child in keyed if flags[modules.TIMETABLE] else []:
                name = child_first_name(child.get("name")) or child.get("name")
                try:
                    timetable = connection.timetable(child_id)
                except OutageError:
                    raise
                except Exception as error:
                    logger.warning(
                        "poll school#%s timetable child#%s failed: %s", connection_id, child_id, error_kind(error)
                    )
                    events.append({"child_key": key, "error": str(error), "kind": error_kind(error)})
                    continue
                push_view, courses_pending = push_view_of(timetable)
                lessons = push_view.get("lessons") or []
                week_changes = push_view.get("changes") or []
                last_updated = timetable.get("last_updated")
                week_anchor = str(timetable.get("start_date") or "")
                changes_count = len(week_changes)
                has_changes = changes_count > 0
                signature = self._signature(lessons, week_changes)
                changes_signature = self._changes_signature(week_changes)
                plan_signature = self._plan_signature(lessons)
                current_plan_fields = plan_fields(lessons)
                previous = poll_state.get(key)
                course_signature = str((timetable.get("courses") or {}).get("signature") or "")
                view_kind = PARALLEL_PENDING if courses_pending else ""
                source = str(timetable.get("source") or DEFAULT_SOURCE)
                changes_format = str(timetable.get(CHANGES_FORMAT_KEY) or "")
                rebased = previous is not None and (
                    str(previous.get(COURSE_SIGNATURE) or "") != course_signature
                    or str(previous.get(PUSH_VIEW_KEY) or "") != view_kind
                    or str(previous.get(SOURCE_STATE_KEY) or DEFAULT_SOURCE) != source
                    or str(previous.get(CHANGES_FORMAT_KEY) or "") != changes_format
                )
                previous_signature = previous.get("signature") if previous else None
                previous_changes_signature = previous.get("changes_signature") if previous else None
                previous_plan_signature = previous.get("plan_signature") if previous else None
                previous_anchor = previous.get("week_anchor") if previous else None
                regular_plan_signature = previous.get("regular_plan_signature") if previous else None
                fresh_changes, change_keys = integration.detect_changes(
                    language,
                    key,
                    lessons,
                    previous.get(integration.CHANGE_KEYS) if previous and not rebased else None,
                    now_epoch,
                )
                changes.extend(fresh_changes)
                same_week = previous is None or previous_anchor == week_anchor
                signature_changed = signature != previous_signature
                changes_changed = same_week and not rebased and changes_signature != previous_changes_signature
                plan_changed = same_week and not rebased and plan_signature != previous_plan_signature
                plan_trigger = f"plan school#{connection_id} child#{child_id}: " + describe_plan_differences(
                    plan_field_differences(previous.get(PLAN_FIELDS_KEY) if previous else None, current_plan_fields)
                )
                if changes_changed and changes_count > 0:
                    self._notify(
                        "timetable",
                        name,
                        self._tagged(language, school, self._message(language, name, changes_count, moved_in(week_changes))),
                        f"changes school#{connection_id} child#{child_id}: {changes_count} changes, changed set",
                    )
                elif (
                    changes_changed
                    and changes_count == 0
                    and previous_changes_signature is not None
                ):
                    plan_left_regular = (
                        regular_plan_signature is not None
                        and plan_signature != regular_plan_signature
                    )
                    self._notify(
                        "timetable",
                        name,
                        self._tagged(
                            language,
                            school,
                            messages.text_in(
                                language,
                                TIMETABLE_PLAN_KEY if plan_left_regular else TIMETABLE_CLEARED_KEY,
                                {"name": name},
                            ),
                        ),
                        plan_trigger + ", changes withdrawn"
                        if plan_left_regular
                        else f"cleared school#{connection_id} child#{child_id}: 0 changes, withdrawn",
                    )
                elif plan_changed and previous_plan_signature is not None:
                    self._notify(
                        "timetable",
                        name,
                        self._tagged(language, school, messages.text_in(language, TIMETABLE_PLAN_KEY, {"name": name})),
                        plan_trigger,
                    )
                hint_sent = bool(previous and previous.get(COURSE_HINT_KEY))
                if courses_pending and not hint_sent:
                    hint_sent = self._notify(
                        "timetable",
                        name,
                        self._tagged(language, school, messages.text_in(language, TIMETABLE_COURSES_KEY, {"name": name})),
                        f"courses school#{connection_id} child#{child_id}: parallel courses not chosen yet",
                    )
                if changes_count == 0:
                    next_regular_plan_signature = plan_signature
                elif rebased:
                    next_regular_plan_signature = None
                elif same_week:
                    next_regular_plan_signature = regular_plan_signature
                else:
                    next_regular_plan_signature = None
                poll_state[key] = {
                    "last_updated": last_updated,
                    "changes_count": changes_count,
                    "signature": signature,
                    "changes_signature": changes_signature,
                    "plan_signature": plan_signature,
                    PLAN_FIELDS_KEY: current_plan_fields,
                    "week_anchor": week_anchor,
                    "regular_plan_signature": next_regular_plan_signature,
                    COURSE_SIGNATURE: course_signature,
                    PUSH_VIEW_KEY: view_kind,
                    COURSE_HINT_KEY: bool(hint_sent),
                    SOURCE_STATE_KEY: source,
                    CHANGES_FORMAT_KEY: changes_format,
                    integration.CHANGE_KEYS: change_keys,
                }
                if key in feed_children:
                    self._store_feed_weeks(
                        snapshot,
                        key,
                        self._collect_feed_weeks(connection, child_id, timetable),
                        int(self.clock()),
                    )
                    snapshot_dirty = True
                events.append({
                    "child_key": key,
                    "changed": signature_changed,
                    "has_changes": has_changes,
                })
            events.extend(self._poll_modules(connection, poll_state, language, flags, summary, school, connection_id))
            messenger_event = (
                self._poll_messenger(connection, poll_state, language, school, connection_id)
                if flags[modules.MESSENGER]
                else None
            )
            if messenger_event is not None:
                events.append(messenger_event)
            if flags[modules.ABSENCES] and self._poll_absences(connection, connection_id, snapshot, absence_children, children):
                snapshot_dirty = True
            if snapshot_dirty and self.store is not None:
                self._commit_snapshot(baseline, snapshot, connection_id)
                self._warm_holidays(store)
        finally:
            if store is not None:
                config["poll_state"] = poll_state
                save_owned_config(store, config)
        failed = any(isinstance(entry, dict) and entry.get("error") for entry in events)
        held = getattr(connection, "session_not_opened_held", None)
        if failed and callable(held) and held():
            session_failed = any(
                isinstance(entry, dict) and entry.get("kind") == SESSION_FAILURE_KIND for entry in events
            )
            kind = SESSION_FAILURE_KIND if session_failed else SESSION_HELD_KIND
            return self._session_not_opened(connection, connection_id, now_epoch, language, kind, events, changes)
        refused = getattr(connection, "code_refused_since_sign_in", None)
        if failed and callable(refused) and refused():
            code_failed = any(isinstance(entry, dict) and entry.get("kind") == CODE_FAILURE_KIND for entry in events)
            kind = CODE_FAILURE_KIND if code_failed else CODE_HELD_KIND
            return self._code_refused(connection, connection_id, now_epoch, language, kind, school, events, changes)
        error = integration.ERROR_NETWORK if failed else ""
        integration.record_school_poll(
            self.store,
            connection_id,
            now_epoch,
            not failed,
            error,
            letters=summary.get("letters"),
            posts=summary.get("posts"),
            conferences=summary.get("conferences"),
            school_name=self._school_name(connection, connection_id, store),
        )
        return {"events": events, "changes": changes, "error": error}

    def _school_name(self, connection, connection_id, store):
        if self.store is None or integration.has_school_name(self.store, connection_id):
            return None
        reader = getattr(connection, "me", None)
        if not callable(reader):
            return None
        try:
            profile = reader() or {}
        except Exception:
            return None
        name = str(profile.get("school_name") or "") if isinstance(profile, dict) else ""
        if name and store is not None and callable(getattr(store, "save_config", None)):

            def change(config):
                if not config.get("school_name"):
                    config["school_name"] = name

            edit_config(store, change)
        return name or None

    def _poll_modules(self, connection, poll_state, language=None, flags=None, summary=None, school="", connection_id=""):
        events = []
        summary = summary if summary is not None else {}
        for event, state_key, collect, key, method in (
            ("letters", "letter_keys", self._letter_keys, LETTERS_KEY, "letters"),
            ("pinboard", "pinboard_ids", self._pinboard_ids, PINBOARD_KEY, "pinboard"),
            ("conferences", "conference_keys", self._conference_keys, CONFERENCES_KEY, "conferences"),
        ):
            if flags is not None and not flags.get(event, True):
                summary[SUMMARY_KEYS[event]] = []
                continue
            if not callable(getattr(connection, method, None)):
                continue
            try:
                current = collect(connection, summary)
            except OutageError:
                raise
            except Exception as error:
                logger.warning("poll school#%s %s failed: %s", connection_id, event, error_kind(error))
                events.append({"module": event, "error": str(error), "kind": error_kind(error)})
                continue
            known = poll_state.get(state_key)
            poll_state[state_key] = sorted(current)
            if known is None:
                events.append({"module": event, "initialized": len(current)})
                continue
            fresh = current - set(known)
            if fresh:
                self._notify(
                    event,
                    "",
                    self._tagged(language, school, messages.text_count(language, key, len(fresh))),
                    f"school#{connection_id}: {len(fresh)} new",
                )
            events.append({"module": event, "new": len(fresh)})
        return events

    def _messenger_push_ready(self):
        return any(name.startswith(f"{MESSENGER_KEY}.") for name in messages.BASE_MESSAGES)

    def _poll_messenger(self, connection, poll_state, language=None, school="", connection_id=""):
        pulse = getattr(connection, "messenger_unread_pulse", None)
        if not callable(pulse):
            return None
        try:
            count = pulse()
        except OutageError:
            raise
        except MessengerStageError as error:
            if error.stage == STAGE_NO_CREDENTIALS:
                logger.info("poll school#%s messenger skipped: %s", connection_id, error.stage)
                return {"module": "messenger", "skipped": True}
            logger.warning("poll school#%s messenger failed: %s", connection_id, error_kind(error))
            return {"module": "messenger", "error": str(error), "kind": error_kind(error)}
        except Exception as error:
            logger.warning("poll school#%s messenger failed: %s", connection_id, error_kind(error))
            return {"module": "messenger", "error": str(error), "kind": error_kind(error)}
        if count is None:
            return {"module": "messenger", "skipped": True}
        previous = poll_state.get("messenger_unread")
        poll_state["messenger_unread"] = count
        if previous is not None and count > previous and self._messenger_push_ready():
            self._notify(
                "messenger",
                "",
                self._tagged(language, school, messages.text_count(language, MESSENGER_KEY, count)),
                f"school#{connection_id}: {count - previous} new, {count} unread",
            )
        return {"module": "messenger", "unread": count}

    def _poll_absences(self, connection, connection_id, snapshot=None, wanted=(), children=()):
        observe = getattr(connection, "absences_overview", None)
        if not callable(observe):
            return False
        try:
            overview = observe()
        except OutageError:
            raise
        except Exception as error:
            logger.warning("poll school#%s absences failed: %s", connection_id, error_kind(error))
            return False
        if not wanted or not isinstance(overview, dict):
            return False
        return self._store_absences(connection_id, snapshot, wanted, children, overview)

    def _store_absences(self, connection_id, snapshot, wanted, children, overview):
        owners = self._student_owners(connection_id, children, overview)
        collected = {key: [] for key in wanted if split_child_key(key)[0] == connection_id}
        if not collected:
            return False
        for entry in overview.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            key = owners.get(entry.get("student_id"))
            if key not in collected:
                continue
            collected[key].append({name: entry.get(name) for name in ABSENCE_FIELDS})
        stamp = int(self.clock())
        holders = snapshot.setdefault("children", {})
        for key, entries in collected.items():
            holder = holders.setdefault(key, {})
            holder["absences"] = entries
            holder["absences_fetched_at"] = stamp
        return True

    def _student_owners(self, connection_id, children, overview):
        owners = {}
        named = []
        for child in children or []:
            if not isinstance(child, dict):
                continue
            child_id = child.get("child_id")
            if not child_id:
                continue
            key = make_child_key(connection_id, child_id)
            student_id = child.get("student_id")
            if student_id is not None:
                owners[student_id] = key
            named.append({"name": child.get("name"), "key": key})
        for student in overview.get("children") or []:
            if not isinstance(student, dict):
                continue
            student_id = student.get("id")
            if student_id is None or student_id in owners:
                continue
            match = student_for_name(named, student.get("name"))
            if match is not None:
                owners[student_id] = match["key"]
        return owners

    def _letter_keys(self, connection, summary):
        data = connection.letters("current") or {}
        summary["letters"] = integration.unread_notices(data.get("letters"))
        return {
            f"{item.get('letter_id')}:{item.get('recipient_id')}"
            for item in data.get("letters") or []
        }

    def _pinboard_ids(self, connection, summary):
        data = connection.pinboard() or {}
        summary["posts"] = integration.unread_notices(data.get("feed"))
        return {str(item.get("id")) for item in data.get("feed") or []}

    def _conference_keys(self, connection, summary):
        data = connection.conferences() or {}
        summary["conferences"] = integration.conference_rows(data)
        if data.get("empty"):
            return set()
        return {
            json.dumps(item.get("cells") or [], sort_keys=True, ensure_ascii=False)
            for item in data.get("items") or []
        }

    @staticmethod
    def _signature(lessons, changes):
        serialized_lessons = sorted(
            json.dumps(item, sort_keys=True, ensure_ascii=False) for item in lessons
        )
        serialized_changes = sorted(
            json.dumps(item, sort_keys=True, ensure_ascii=False) for item in changes
        )
        blob = json.dumps(
            {"lessons": serialized_lessons, "changes": serialized_changes},
            ensure_ascii=False,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    @staticmethod
    def _plan_signature(lessons):
        serialized = sorted(
            json.dumps(
                {field: item.get(field) for field in PLAN_ORIGIN_FIELDS},
                sort_keys=True,
                ensure_ascii=False,
            )
            for item in lessons
        )
        return hashlib.sha256(json.dumps(serialized, ensure_ascii=False).encode("utf-8")).hexdigest()

    @staticmethod
    def _changes_signature(changes):
        serialized = sorted(
            json.dumps(item, sort_keys=True, ensure_ascii=False) for item in changes
        )
        return hashlib.sha256(json.dumps(serialized, ensure_ascii=False).encode("utf-8")).hexdigest()

    @staticmethod
    def _message(language, name, count, moved=False):
        return messages.text_count(language, TIMETABLE_MOVED_KEY if moved else TIMETABLE_KEY, count, {"name": name})
