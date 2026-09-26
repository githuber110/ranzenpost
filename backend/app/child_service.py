import logging
import time

import requests

from . import courses, modules
from .failure import failure_cause
from .identifiers import UNKNOWN_CHILD_KEY
from .iserv.children import CHILD_PAGE_FORBIDDEN_KEY, CHILD_PAGE_MESSAGE_KEY, CHILD_PAGE_SESSION_KEY
from .iserv.dsa import parse_children_from_me, student_for_name
from .iserv.errors import DataError, LoginError, OutageError, TwoFactorError
from .iserv.letters import parse_letter_list
from .letter_service import LETTERS_ARCHIVE_PATH, LETTERS_INDEX_PATH
from .not_configured import ConnectionChangedError, NotConfiguredError
from .store import LOGIN_REVISION_KEY, edit_config

logger = logging.getLogger(__name__)

LETTERS_CHILD_PREFIX = "letters:"
UPSTREAM_SIGN_IN_ERRORS = (LoginError, TwoFactorError)
CHILD_PAGE_KEYS = (CHILD_PAGE_FORBIDDEN_KEY, CHILD_PAGE_MESSAGE_KEY)
SCHOOL_CACHE_SECONDS = 600


def letters_child_id(name):
    slug = "".join(char if char.isalnum() else "-" for char in str(name).strip().casefold())
    return LETTERS_CHILD_PREFIX + "-".join(part for part in slug.split("-") if part)


def _moved_children(config, children):
    current_ids = {child["child_id"] for child in children}
    moves = []
    for entry in config.get("children") or []:
        if not isinstance(entry, dict):
            continue
        child_id = str(entry.get("child_id") or "")
        if child_id in current_ids:
            continue
        match = student_for_name(children, entry.get("name"))
        if match is not None:
            moves.append((child_id, match["child_id"]))
    return moves


def _stored_identities(stored, children):
    stored_ids = {str(entry.get("child_id") or "") for entry in stored}
    listed_ids = {str(child.get("child_id") or "") for child in children}
    candidates = [entry for entry in stored if str(entry.get("child_id") or "") not in listed_ids]
    taken = set()
    result = []
    for child in children:
        child_id = str(child.get("child_id") or "")
        match = student_for_name(candidates, child.get("name"))
        stored_id = str(match.get("child_id") or "") if match is not None else ""
        if not child_id or child_id in stored_ids or not stored_id or stored_id in taken:
            result.append((child, child_id))
            continue
        taken.add(stored_id)
        result.append((dict(child, child_id=stored_id), child_id))
    return result


def unknown_child():
    return DataError("unknown child", message_key=UNKNOWN_CHILD_KEY)


def connection_marker(config, revision=None):
    return (
        str(config.get("school_url") or ""),
        (config.get(LOGIN_REVISION_KEY) or 0) if revision is None else revision,
    )


def _changed_connection():
    return ConnectionChangedError("the connection changed since this child list was asked for")


class ChildService:
    def __init__(self, connection):
        self.connection = connection
        self._children_cache = (0.0, {})
        self._listed_ids = (0.0, set())
        self._page_ids = None
        self._retired = False

    def retire(self):
        self._retired = True
        self._children_cache = (0.0, {})
        self._listed_ids = (0.0, set())
        self._page_ids = None

    def _marker(self):
        config = self.connection.store.load_config()
        marker = connection_marker(config, getattr(self.connection, "login_revision", None))
        if not self._current(config, marker):
            raise _changed_connection()
        return marker

    def _current(self, config, marker):
        return not self._retired and connection_marker(config) == marker

    def stored_children(self):
        return [
            dict(child)
            for child in self.connection.store.load_config().get("children") or []
            if isinstance(child, dict) and child.get("child_id")
        ]

    def authorized_child(self, child_id):
        child_id = str(child_id or "")
        stored = {child["child_id"] for child in self.stored_children()}
        if not stored:
            stored = self._listed_child_ids()
        if not child_id or child_id not in stored:
            raise unknown_child()
        return child_id

    def _listed_child_ids(self):
        stamp, listed = self._listed_ids
        if self.connection.clock() - stamp > SCHOOL_CACHE_SECONDS:
            listed = {str(child.get("child_id") or "") for child in self.children()}
            if not self._retired:
                self._listed_ids = (self.connection.clock(), listed)
        return listed

    def children(self):
        marker = self._marker()
        self.connection._timetable_page_denied = False
        listed = self._children_from_school_account()
        if listed:
            self._remember_page_ids({})
            self._migrate_stored_children(listed, marker)
            return self._keep(listed, marker, remember=True)
        if not self.connection.module_available(modules.TIMETABLE):
            self._remember_page_ids({})
            return self._keep(self._as_stored(self._fallback_children(), "fallback"), marker, remember=True)
        client = self.connection._session()
        try:
            native = client.get_children()
        except DataError as error:
            if error.message_key == CHILD_PAGE_SESSION_KEY:
                self.connection._forget_session(client)
            if error.message_key not in CHILD_PAGE_KEYS:
                raise
            fallback = self._children_from_school_app()
            if not fallback:
                raise
            logger.warning(
                "the timetable page refused the child list, using the school app list instead: %s",
                failure_cause(error),
            )
            self._remember_page_ids({})
            kept = self._keep(self._as_stored(fallback, "school app"), marker)
            self.connection._timetable_page_denied = True
            return kept
        try:
            students = self.connection._dsa().students()
        except Exception:
            logger.debug("dsa students lookup failed", exc_info=True)
            students = []
        result = []
        for child in native:
            student = student_for_name(students, child.name)
            result.append({
                "child_id": child.child_id,
                "name": child.name,
                "class_name": student.get("class_name", "") if student else "",
                "student_id": student.get("id") if student else None,
                "class_full": student.get("class_full", "") if student else "",
                "class_code": student.get("class_code", "") if student else "",
            })
        identities = self._identities(result, "timetable page")
        kept = self._keep([child for child, _ in identities], marker)
        self._remember_page_ids({child["child_id"]: source_id for child, source_id in identities if child["child_id"] != source_id})
        return kept

    def _identities(self, children, source):
        identities = _stored_identities(self.stored_children(), children)
        kept = sum(1 for child, source_id in identities if child["child_id"] != source_id)
        if kept:
            logger.info("school#%s kept %d child(ren) of the %s list under the stored id", self.connection.id, kept, source)
        return identities

    def _as_stored(self, children, source):
        return [child for child, _ in self._identities(children, source)]

    def _remember_page_ids(self, page_ids):
        if not self._retired:
            self._page_ids = page_ids

    def timetable_page_id(self, child_id):
        child_id = str(child_id or "")
        if self._page_ids is None:
            try:
                self.children()
            except Exception as error:
                logger.info("school#%s child list for the timetable page unreadable: %s", self.connection.id, type(error).__name__)
            if self._page_ids is None:
                self._remember_page_ids({})
        return (self._page_ids or {}).get(child_id, child_id)

    def _keep(self, children, marker, remember=False):
        if not self._learn_children(children, marker):
            logger.info("school#%s dropped a child list read before the connection changed", self.connection.id)
            raise _changed_connection()
        if remember:
            self._remember_children(children)
        return children

    def _learn_children(self, children, marker):
        added = []
        current = []

        def change(config):
            current.append(self._current(config, marker))
            if not current[-1]:
                return
            stored = [child for child in config.get("children") or [] if isinstance(child, dict)]
            known = {str(child.get("child_id") or "") for child in stored}
            for child in children:
                child_id = str(child.get("child_id") or "")
                if not child_id or child_id in known:
                    continue
                known.add(child_id)
                entry = {"child_id": child_id}
                if child.get("name"):
                    entry["name"] = child["name"]
                if child.get("class_name"):
                    entry["class_name"] = child["class_name"]
                added.append(entry)
            if added:
                config["children"] = stored + added

        edit_config(self.connection.store, change)
        if added:
            logger.info("school#%s learned %d child(ren) it had not stored yet", self.connection.id, len(added))
        return bool(current) and current[-1]

    def _children_from_school_account(self):
        try:
            payload = self.connection._dsa().me_with_children()
        except Exception:
            logger.debug("school account lookup failed", exc_info=True)
            return []
        return parse_children_from_me(payload)

    def _remember_children(self, children):
        if self._retired:
            return
        self._children_cache = (time.time(), {child["child_id"]: child for child in children})

    def listed_count(self, refresh=False):
        stamp, cached = self._children_cache
        if refresh and (not cached or time.time() - stamp > SCHOOL_CACHE_SECONDS):
            listed = self._children_from_school_account()
            if listed:
                self._remember_children(listed)
                cached = self._children_cache[1]
        return len(cached)

    def course_ids_known(self):
        _, cached = self._children_cache
        return any(child.get("course_ids") for child in cached.values())

    def _cached_child(self, child_id):
        stamp, cached = self._children_cache
        if time.time() - stamp > SCHOOL_CACHE_SECONDS or child_id not in cached:
            listed = self._children_from_school_account()
            if listed:
                self._remember_children(listed)
                cached = self._children_cache[1]
        return cached.get(child_id)

    def _migrate_stored_children(self, children, marker=None):
        marker = self._marker() if marker is None else marker
        config = self.connection.store.load_config()
        if not self._current(config, marker):
            return
        for old_id, new_id in _moved_children(config, children):
            self._move_child_subscriptions(old_id, new_id)

        def change(config):
            if not self._current(config, marker):
                return
            stored = config.get("children") or []
            targets = dict(_moved_children(config, children))
            migrated = []
            seen = {}
            for entry in stored:
                if not isinstance(entry, dict):
                    continue
                child_id = str(entry.get("child_id") or "")
                match = student_for_name(children, entry.get("name")) if child_id in targets else None
                if match is not None:
                    entry = dict(entry, child_id=match["child_id"])
                    if match.get("class_name"):
                        entry["class_name"] = match["class_name"]
                    config.update(courses.moved_filter(config, child_id, match["child_id"]) or {})
                    logger.info("stored child moved to the school account id")
                final_id = str(entry.get("child_id") or "")
                if final_id and final_id in seen:
                    kept = seen[final_id]
                    kept.update({key: value for key, value in entry.items() if value and not kept.get(key)})
                    logger.info("a child stored twice under the same id was merged")
                    continue
                entry = dict(entry)
                seen[final_id] = entry
                migrated.append(entry)
            if migrated != stored:
                config["children"] = migrated

        edit_config(self.connection.store, change)

    def _move_child_subscriptions(self, old_id, new_id):
        from .marks import MarkRegistry
        from .subscriptions import SubscriptionRegistry

        old_key = self.connection.child_key(old_id)
        new_key = self.connection.child_key(new_id)
        try:
            SubscriptionRegistry(self.connection.store).move_child(old_key, new_key)
        except Exception:
            logger.warning("calendar subscriptions could not follow the child", exc_info=True)
        try:
            MarkRegistry(self.connection.store).move_child(old_key, new_key)
        except Exception:
            logger.warning("marks could not follow the child", exc_info=True)

    def _fallback_children(self):
        failures = []
        confirmed = False
        school_app = self.connection.module_available(modules.ABSENCES)
        for module, read, confirms in (
            (modules.ABSENCES, self._school_app_children_or_raise, True),
            (modules.LETTERS, self._letter_children_or_raise, not school_app),
        ):
            if not self.connection.module_available(module):
                continue
            try:
                listed = read()
            except (OutageError, NotConfiguredError, requests.RequestException) + UPSTREAM_SIGN_IN_ERRORS:
                raise
            except Exception as error:
                logger.warning("school#%s child list from %s unreadable: %s", self.connection.id, module, type(error).__name__)
                failures.append(error)
                continue
            if listed:
                return listed
            confirmed = confirmed or confirms
        if failures and not confirmed:
            failure = failures[0]
            if isinstance(failure, DataError):
                raise failure
            raise DataError("child list unreadable", message_key=CHILD_PAGE_MESSAGE_KEY) from failure
        return []

    def _school_app_children_or_raise(self):
        return self._school_app_rows(self.connection._dsa().sick_note_children_or_raise())

    def _children_from_school_app(self):
        try:
            students = self.connection._dsa().sick_note_children()
        except Exception:
            logger.debug("school app child list lookup failed", exc_info=True)
            return []
        return self._school_app_rows(students)

    def _school_app_rows(self, students):
        return [
            {
                "child_id": str(student.get("id")),
                "name": student.get("name", ""),
                "class_name": student.get("class_name", ""),
                "student_id": student.get("id"),
                "class_full": student.get("class_full", ""),
                "class_code": student.get("class_code", ""),
            }
            for student in students
            if student.get("id") is not None and student.get("name")
        ]

    def _letter_children_or_raise(self):
        return self._children_from_letters(strict=True)

    def _children_from_letters(self, strict=False):
        names = []
        read = 0
        for path in (LETTERS_INDEX_PATH, LETTERS_ARCHIVE_PATH):
            try:
                response = self.connection._session().fetch(path)
            except requests.RequestException:
                logger.debug("letter page lookup for the child list failed", exc_info=True)
                continue
            if getattr(response, "status_code", 0) != 200:
                continue
            read += 1
            for letter in parse_letter_list(response.text, response.url):
                name = " ".join(str(letter.get("child") or "").split())
                if name and name not in names:
                    names.append(name)
        if strict and not read:
            raise DataError("letter pages unreadable", message_key=CHILD_PAGE_MESSAGE_KEY)
        return [
            {
                "child_id": letters_child_id(name),
                "name": name,
                "class_name": "",
                "student_id": None,
                "class_full": "",
                "class_code": "",
            }
            for name in names
        ]
