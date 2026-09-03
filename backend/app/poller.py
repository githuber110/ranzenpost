import hashlib
import json
import time
from datetime import datetime, timedelta, timezone

from . import feed, holidays, marks, messages
from .iserv.errors import LoginError
from .subscriptions import COMPONENT_ABSENCES

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
LETTERS_KEY = "notify.letters.new"
LETTERS_CONFIRM_KEY = "notify.letters.newConfirm"
PINBOARD_KEY = "notify.pinboard.new"
CONFERENCES_KEY = "notify.conferences.new"
TIMETABLE_KEY = "notify.timetable.changes"
MESSENGER_KEY = "notify.messenger.unread"


class Poller:
    def __init__(
        self,
        service,
        publisher=None,
        notifier=None,
        store=None,
        notifiers=None,
        registry=None,
        holiday_calendar=None,
        clock=None,
    ):
        self.service = service
        self.publisher = publisher
        self.notifier = notifier
        self.notifiers = dict(notifiers or {})
        self.store = store if store is not None else getattr(service, "store", None)
        self.registry = registry
        self.holiday_calendar = holiday_calendar
        self.clock = clock or time.time

    def _notify(self, event, name, message):
        target = self.notifiers.get(event)
        if target is None and event == "timetable":
            target = self.notifier
        if target is None:
            return False
        return target(name, message)

    def _subscribed_children(self, component):
        if self.registry is None or self.store is None:
            return set()
        reader = getattr(self.registry, "children_with_component", None)
        if not callable(reader):
            return set()
        try:
            return {child_id for child_id in reader(component) if child_id}
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
                entry.get("child_id")
                for entry in marks.entries_of(reader())
                if entry.get("child_id")
            }
        except Exception:
            return set()

    def _feed_children(self):
        if self.registry is None or self.store is None:
            return set()
        try:
            timetable = {
                child_id for child_id in self.registry.children_with_timetable() if child_id
            }
        except Exception:
            return set()
        return timetable | self._marked_children()

    def _absence_children(self):
        return self._subscribed_children(COMPONENT_ABSENCES)

    def _collect_feed_weeks(self, child_id, current):
        weeks = [current]
        for offset in range(1, feed.WEEKS_AHEAD + 1):
            try:
                weeks.append(self.service.timetable(child_id, week_offset=offset))
            except Exception:
                break
        return weeks

    def _store_feed_weeks(self, snapshot, child_id, weeks, now):
        children = snapshot.setdefault("children", {})
        entry = children.setdefault(child_id, {})
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

    def _warm_holidays(self):
        if self.holiday_calendar is None:
            return
        today = self._today()
        window = feed.lesson_window(today)
        try:
            self.holiday_calendar.range_info(
                window[0], today + timedelta(days=feed.HOLIDAY_DAYS_AHEAD)
            )
        except Exception:
            pass

    def poll_once(self):
        config = self.store.load_config() if self.store is not None else {}
        language = config.get("language")
        poll_state = dict(config.get("poll_state") or {})
        feed_children = self._feed_children()
        absence_children = self._absence_children()
        snapshot = (
            self.store.load_calendar_snapshot()
            if (feed_children or absence_children) and self.store is not None
            else {}
        )
        snapshot_dirty = False
        events = []
        try:
            children = self.service.children()
        except LoginError:
            if not config.get("auth_incident"):
                config["auth_incident"] = True
                self._notify("auth", "", messages.text_in(language, BAD_CREDENTIALS_KEY))
            if self.store is not None:
                self.store.save_config(config)
            return [{"error": "bad_credentials"}]
        config.pop("auth_incident", None)
        for child in children:
            child_id = child.get("child_id")
            name = child.get("name")
            try:
                timetable = self.service.timetable(child_id)
            except Exception as error:
                if self.publisher is not None:
                    self.publisher.publish_state(child_id, None, False, error=str(error))
                events.append({"child_id": child_id, "error": str(error)})
                continue
            lessons = timetable.get("lessons") or []
            changes = timetable.get("changes") or []
            last_updated = timetable.get("last_updated")
            changes_count = len(changes)
            has_changes = changes_count > 0
            signature = self._signature(lessons, changes)
            changes_signature = self._changes_signature(changes)
            previous = poll_state.get(child_id)
            previous_signature = previous.get("signature") if previous else None
            previous_changes_signature = previous.get("changes_signature") if previous else None
            signature_changed = signature != previous_signature
            changes_changed = changes_signature != previous_changes_signature
            if signature_changed and self.publisher is not None:
                self.publisher.publish_state(child_id, last_updated, has_changes, error=None)
            if changes_changed and changes_count > 0:
                self._notify("timetable", name, self._message(language, name, changes_count))
            if child_id in feed_children:
                self._store_feed_weeks(
                    snapshot,
                    child_id,
                    self._collect_feed_weeks(child_id, timetable),
                    int(self.clock()),
                )
                snapshot_dirty = True
            poll_state[child_id] = {
                "last_updated": last_updated,
                "changes_count": changes_count,
                "signature": signature,
                "changes_signature": changes_signature,
            }
            events.append({
                "child_id": child_id,
                "changed": signature_changed,
                "has_changes": has_changes,
            })
        self._enrich_letters_search()
        events.extend(self._poll_modules(poll_state, language))
        messenger_event = self._poll_messenger(poll_state, language)
        if messenger_event is not None:
            events.append(messenger_event)
        if self._poll_absences(snapshot, absence_children, children):
            snapshot_dirty = True
        if snapshot_dirty and self.store is not None:
            self.store.save_calendar_snapshot(snapshot)
            self._warm_holidays()
        if self.store is not None:
            config["poll_state"] = poll_state
            self.store.save_config(config)
        return events

    def _poll_modules(self, poll_state, language=None):
        events = []
        for event, state_key, collect, key, method, resolve in (
            ("letters", "letter_keys", self._letter_keys, LETTERS_KEY, "letters", self._letters_key),
            ("pinboard", "pinboard_ids", self._pinboard_ids, PINBOARD_KEY, "pinboard", None),
            ("conferences", "conference_keys", self._conference_keys, CONFERENCES_KEY, "conferences", None),
        ):
            if not callable(getattr(self.service, method, None)):
                continue
            try:
                current = collect()
            except Exception as error:
                events.append({"module": event, "error": str(error)})
                continue
            known = poll_state.get(state_key)
            poll_state[state_key] = sorted(current)
            if known is None:
                events.append({"module": event, "initialized": len(current)})
                continue
            fresh = current - set(known)
            if fresh:
                chosen = (resolve(fresh) if resolve is not None else None) or key
                self._notify(event, "", messages.text_count(language, chosen, len(fresh)))
            events.append({"module": event, "new": len(fresh)})
        return events

    def _messenger_push_ready(self):
        return any(name.startswith(f"{MESSENGER_KEY}.") for name in messages.BASE_MESSAGES)

    def _poll_messenger(self, poll_state, language=None):
        pulse = getattr(self.service, "messenger_unread_pulse", None)
        if not callable(pulse):
            return None
        try:
            count = pulse()
        except Exception as error:
            return {"module": "messenger", "error": str(error)}
        if count is None:
            return {"module": "messenger", "skipped": True}
        previous = poll_state.get("messenger_unread")
        poll_state["messenger_unread"] = count
        if previous is not None and count > previous and self._messenger_push_ready():
            self._notify("messenger", "", messages.text_count(language, MESSENGER_KEY, count))
        return {"module": "messenger", "unread": count}

    def _letters_key(self, fresh):
        reader = getattr(self.service, "pending_confirmation_keys", None)
        if not callable(reader):
            return None
        try:
            pending = reader("current")
        except Exception:
            return None
        return LETTERS_CONFIRM_KEY if fresh & set(pending or ()) else None

    def _poll_absences(self, snapshot=None, wanted=(), children=()):
        observe = getattr(self.service, "absences_overview", None)
        if not callable(observe):
            return False
        try:
            overview = observe()
        except Exception:
            return False
        if not wanted or not isinstance(overview, dict):
            return False
        return self._store_absences(snapshot, wanted, children, overview)

    def _store_absences(self, snapshot, wanted, children, overview):
        owners = self._student_owners(children, overview)
        collected = {child_id: [] for child_id in wanted}
        for entry in overview.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            child_id = owners.get(entry.get("student_id"))
            if child_id not in collected:
                continue
            collected[child_id].append({name: entry.get(name) for name in ABSENCE_FIELDS})
        stamp = int(self.clock())
        holders = snapshot.setdefault("children", {})
        for child_id, entries in collected.items():
            holder = holders.setdefault(child_id, {})
            holder["absences"] = entries
            holder["absences_fetched_at"] = stamp
        return True

    def _student_owners(self, children, overview):
        owners = {}
        by_name = {}
        for child in children or []:
            if not isinstance(child, dict):
                continue
            child_id = child.get("child_id")
            if not child_id:
                continue
            student_id = child.get("student_id")
            if student_id is not None:
                owners[student_id] = child_id
            name = " ".join(str(child.get("name") or "").split()).casefold()
            if name:
                by_name[name] = child_id
        for student in overview.get("children") or []:
            if not isinstance(student, dict):
                continue
            student_id = student.get("id")
            if student_id is None or student_id in owners:
                continue
            name = " ".join(str(student.get("name") or "").split()).casefold()
            if name in by_name:
                owners[student_id] = by_name[name]
        return owners

    def _enrich_letters_search(self):
        enrich = getattr(self.service, "enrich_letters_search", None)
        if not callable(enrich):
            return
        try:
            enrich("current")
        except Exception:
            pass

    def _letter_keys(self):
        data = self.service.letters("current") or {}
        return {
            f"{item.get('letter_id')}:{item.get('recipient_id')}"
            for item in data.get("letters") or []
        }

    def _pinboard_ids(self):
        data = self.service.pinboard() or {}
        return {str(item.get("id")) for item in data.get("feed") or []}

    def _conference_keys(self):
        data = self.service.conferences() or {}
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
    def _changes_signature(changes):
        serialized = sorted(
            json.dumps(item, sort_keys=True, ensure_ascii=False) for item in changes
        )
        return hashlib.sha256(json.dumps(serialized, ensure_ascii=False).encode("utf-8")).hexdigest()

    @staticmethod
    def _message(language, name, count):
        return messages.text_count(language, TIMETABLE_KEY, count, {"name": name})
