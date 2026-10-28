from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AuthError, Change, Child, Event, Info, Modules, RanzenpostApi, RanzenpostError, School, State
from .const import (
    CONF_CHILDREN,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ERROR_APP_TOKEN_REJECTED,
    ERROR_APP_UNREACHABLE,
    EVENT_CACHE_TTL,
    ISSUE_ENTRY,
    LOGIN_ISSUE_KEYS,
    LOGIN_NEEDED_ISSUE_KEY,
    MAX_SCAN_INTERVAL,
    MIN_ADDON_VERSION,
    MIN_SCAN_INTERVAL,
    NO_SCHOOL_ISSUE_KEY,
    STATUS_AUTH_FAILED,
    UNKNOWN_VERSION,
)
from .panels import PANELS_KEY, app_panel_path
from .signals import Signal, signals_between
from .version import (
    ADDON_TOO_OLD,
    APP_UPDATE_NEEDED,
    INTEGRATION_TOO_OLD,
    RESTART_REQUIRED,
    mismatch_is_severe,
    newer_version,
    restart_pending,
    version_mismatch,
)

_LOGGER = logging.getLogger(__name__)

VERSION_ISSUE_KEYS = (ADDON_TOO_OLD, APP_UPDATE_NEEDED, INTEGRATION_TOO_OLD)
ENTRY_ISSUE_KEYS = (*VERSION_ISSUE_KEYS, NO_SCHOOL_ISSUE_KEY)
PLACEHOLDER_ADDON_VERSION = "addon_version"
PLACEHOLDER_INTEGRATION_VERSION = "integration_version"
PLACEHOLDER_REQUIRED_VERSION = "required_version"
PLACEHOLDER_LOADED_VERSION = "loaded_version"
PLACEHOLDER_INSTALLED_VERSION = "installed_version"
MANIFEST_FILE = Path(__file__).parent / "manifest.json"
NOTICE_FIELDS = ("unread_letters", "unread_posts", "open_tasks", "news", "unread_forum_posts", "texts")
SCOPE_CHILD = "child"
SCOPE_SCHOOL = "school"
CHANGES_STORE_VERSION = 1
CHANGES_SEEN = "seen"

type ManifestStamp = tuple[int, str]


def read_installed_version(path: Path, known: ManifestStamp | None) -> ManifestStamp | None:
    try:
        stamp = path.stat().st_mtime_ns
        if known is not None and known[0] == stamp:
            return known
        return (stamp, str(json.loads(path.read_text(encoding="utf-8")).get("version") or ""))
    except (OSError, ValueError, AttributeError):
        return known


def login_issue_id(entry_id: str, school_id: str) -> str:
    return f"{LOGIN_NEEDED_ISSUE_KEY}:{entry_id}:{school_id}"


def entry_issue_id(key: str, entry_id: str) -> str:
    return f"{key}:{entry_id}"

type RanzenpostConfigEntry = ConfigEntry[RanzenpostCoordinator]


@dataclass
class RanzenpostData:
    info: Info
    states: dict[str, State]
    schools: dict[str, School]
    changes: list[Change]
    new_changes: list[Change] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)

    @property
    def children(self) -> tuple[Child, ...]:
        return tuple(child for child in self.info.children if child.key in self.states)

    def school(self, school_id: str) -> School:
        return self.schools.get(school_id) or School(None, None, "")


def with_known_notices(item, scope: tuple[str, str], memory: dict) -> object:
    known = {
        name: memory[(scope, name)]
        for name in NOTICE_FIELDS
        if hasattr(item, name) and getattr(item, name) is None and (scope, name) in memory
    }
    return replace(item, **known) if known else item


def remember_notices(item, scope: tuple[str, str], memory: dict) -> None:
    for name in NOTICE_FIELDS:
        value = getattr(item, name, None)
        if value is not None:
            memory[(scope, name)] = value


def changes_store(hass: HomeAssistant, entry_id: str) -> Store:
    return Store(hass, CHANGES_STORE_VERSION, f"{DOMAIN}.{entry_id}.changes")


async def async_remove_changes_store(hass: HomeAssistant, entry_id: str) -> None:
    await changes_store(hass, entry_id).async_remove()


def scan_interval_of(entry: ConfigEntry) -> timedelta:
    seconds = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    return timedelta(seconds=min(max(seconds, MIN_SCAN_INTERVAL), MAX_SCAN_INTERVAL))


def child_option_keys(info: Info, chosen: list[str]) -> list[str]:
    keys = {child.key for child in info.children}
    by_raw_id = {child.raw_id: child.key for child in info.children}
    return [item if item in keys else by_raw_id.get(item, item) for item in chosen]


def selected_children(info: Info, entry: ConfigEntry) -> tuple[Child, ...]:
    chosen = [str(item) for item in entry.options.get(CONF_CHILDREN) or []]
    if not chosen:
        return info.children
    wanted = set(child_option_keys(info, chosen))
    return tuple(child for child in info.children if child.key in wanted)


def api_for_entry(hass: HomeAssistant, entry: ConfigEntry) -> RanzenpostApi:
    return RanzenpostApi(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_TOKEN],
    )


class EventCache:
    def __init__(self, api: RanzenpostApi, ttl: timedelta = EVENT_CACHE_TTL) -> None:
        self._api = api
        self._ttl = ttl
        self._entries: dict[tuple[str, str, str, date, date, str], tuple[float, list[Event]]] = {}

    async def events(
        self, child_key: str, kind: str, start: date, end: date, school_id: str = "", purpose: str = ""
    ) -> list[Event]:
        key = (child_key, school_id, kind, start, end, purpose)
        now = dt_util.utcnow().timestamp()
        cached = self._entries.get(key)
        if cached is not None and now - cached[0] < self._ttl.total_seconds():
            return cached[1]
        events = await self._api.events(child_key, kind, start, end, school_id, purpose)
        ttl = self._ttl.total_seconds()
        self._entries = {other: hit for other, hit in self._entries.items() if now - hit[0] < ttl}
        self._entries[key] = (now, events)
        return events

    def clear(self) -> None:
        self._entries.clear()


def _fingerprint(info: Info) -> tuple[tuple[tuple[str, Modules, bool, bool], ...], frozenset[str]]:
    schools = tuple((school.id, school.modules, school.own_entries, school.mail) for school in info.schools)
    return (schools, frozenset(child.key for child in info.children))


class RanzenpostCoordinator(DataUpdateCoordinator[RanzenpostData]):
    config_entry: RanzenpostConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: RanzenpostConfigEntry,
        api: RanzenpostApi | None = None,
        integration_version: str = "",
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=scan_interval_of(entry),
        )
        self.api = api or api_for_entry(hass, entry)
        self.integration_version = integration_version
        self.api.integration_version = integration_version
        self.installed_version = ""
        self._manifest: ManifestStamp | None = None
        self._manifest_check: asyncio.Task | None = None
        self.events = EventCache(self.api)
        self._changes_store = changes_store(hass, entry.entry_id)
        self._seen_changes: set[str] | None = None
        self._notices: dict = {}
        self._known_modules: dict[str, Modules] = {}
        self.time_zone = dt_util.get_default_time_zone()
        self._time_zone_name: str | None = None
        self._entity_fingerprint: tuple | None = None
        self._version_issue: str | None = None

    async def _async_setup(self) -> None:
        stored = await self._changes_store.async_load()
        seen = stored.get(CHANGES_SEEN) if isinstance(stored, dict) else None
        self._seen_changes = {str(item) for item in seen} if isinstance(seen, list) else None
        if not self._started:
            self.config_entry.async_on_unload(async_at_started(self.hass, self._async_announce_held_changes))

    @property
    def _started(self) -> bool:
        return self.hass.state is CoreState.running

    async def _async_announce_held_changes(self, _hass: HomeAssistant) -> None:
        await self.async_request_refresh()

    def schedule_manifest_check(self) -> None:
        if self._manifest_check is not None and not self._manifest_check.done():
            return
        self._manifest_check = self.config_entry.async_create_background_task(
            self.hass, self._async_check_manifest(), f"{DOMAIN} manifest check"
        )

    async def _async_check_manifest(self) -> None:
        self._manifest = await self.hass.async_add_executor_job(read_installed_version, MANIFEST_FILE, self._manifest)
        installed = self._manifest[1] if self._manifest else ""
        changed = installed != self.installed_version
        self.installed_version = installed
        self.api.installed_version = installed if self.restart_pending else ""
        self._sync_restart_issue()
        if changed and self.data is not None:
            self._sync_version_issues(self.data.info)

    @property
    def restart_pending(self) -> bool:
        return restart_pending(self.integration_version, self.installed_version)

    @property
    def target_version(self) -> str:
        return newer_version(self.integration_version, self.installed_version)

    def _sync_restart_issue(self) -> None:
        if not self.restart_pending:
            ir.async_delete_issue(self.hass, DOMAIN, RESTART_REQUIRED)
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            RESTART_REQUIRED,
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=RESTART_REQUIRED,
            translation_placeholders={
                PLACEHOLDER_LOADED_VERSION: self.integration_version,
                PLACEHOLDER_INSTALLED_VERSION: self.installed_version,
            },
        )

    def _sync_version_issues(self, info: Info) -> None:
        entry_id = self.config_entry.entry_id
        target = self.target_version
        mismatch = version_mismatch(info.version, target, info.legacy)
        for key in VERSION_ISSUE_KEYS:
            if key != mismatch:
                ir.async_delete_issue(self.hass, DOMAIN, entry_issue_id(key, entry_id))
        if mismatch is None:
            self._version_issue = None
            return
        addon_version = info.version or UNKNOWN_VERSION
        integration_version = target or UNKNOWN_VERSION
        if mismatch != self._version_issue:
            _LOGGER.warning(
                "the Ranzenpost app %s and the integration %s do not match (%s), update the older one",
                addon_version,
                integration_version,
                mismatch,
            )
        self._version_issue = mismatch
        severe = mismatch_is_severe(mismatch, info.version, target)
        issue_id = entry_issue_id(mismatch, entry_id)
        placeholders = {
            PLACEHOLDER_ADDON_VERSION: addon_version,
            PLACEHOLDER_INTEGRATION_VERSION: integration_version,
            PLACEHOLDER_REQUIRED_VERSION: MIN_ADDON_VERSION,
        }
        known = ir.async_get(self.hass).async_get_issue(DOMAIN, issue_id)
        if known is not None and known.translation_placeholders is not None and known.translation_placeholders != placeholders:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=True,
            is_persistent=True,
            data={ISSUE_ENTRY: entry_id},
            severity=ir.IssueSeverity.ERROR if severe else ir.IssueSeverity.WARNING,
            translation_key=mismatch,
            translation_placeholders=placeholders,
        )

    def _sync_no_school_issue(self, info: Info) -> None:
        issue_id = entry_issue_id(NO_SCHOOL_ISSUE_KEY, self.config_entry.entry_id)
        if info.legacy or info.schools:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=NO_SCHOOL_ISSUE_KEY,
            learn_more_url=info.ingress_path or None,
        )

    async def _async_update_data(self) -> RanzenpostData:
        self.schedule_manifest_check()
        try:
            info = await self.api.info()
            info = replace(
                info,
                ingress_path=app_panel_path(self.hass.data.get(PANELS_KEY), info.ingress_path),
                integration_version=self.integration_version,
            )
            info = self._with_known_modules(info)
            await self._async_follow_time_zone(info.timezone)
            self._sync_version_issues(info)
            self._sync_no_school_issue(info)
            states = {child.key: await self.api.state(child.key) for child in selected_children(info, self.config_entry)}
            schools = {school.id: await self.api.school(school.id) for school in info.schools}
            changes = await self.api.changes()
        except AuthError as err:
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key=ERROR_APP_TOKEN_REJECTED) from err
        except RanzenpostError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key=ERROR_APP_UNREACHABLE,
                translation_placeholders={"error": str(err)},
            ) from err
        self._clear_events_when_timetables_changed(states)
        self._reload_when_schools_modules_or_children_changed(info)
        self._sync_login_issues(info)
        new_changes, seen = self._fresh_changes(changes)
        previous = self.data
        signals = signals_between(
            previous.info if previous else None,
            {
                key: with_known_notices(state, (SCOPE_CHILD, key), self._notices)
                for key, state in (previous.states if previous else {}).items()
            },
            info,
            states,
            new_changes,
            {
                key: with_known_notices(school, (SCOPE_SCHOOL, key), self._notices)
                for key, school in (previous.schools if previous else {}).items()
            },
            schools,
        )
        for key, state in states.items():
            remember_notices(state, (SCOPE_CHILD, key), self._notices)
        for key, school in schools.items():
            remember_notices(school, (SCOPE_SCHOOL, key), self._notices)
        data = RanzenpostData(info, states, schools, changes, new_changes, signals)
        await self._async_note_seen_changes(seen)
        return data

    async def _async_follow_time_zone(self, name: str) -> None:
        if name == self._time_zone_name:
            return
        self._time_zone_name = name
        zone = await dt_util.async_get_time_zone(name) if name else None
        self.time_zone = zone or dt_util.get_default_time_zone()

    def _with_known_modules(self, info: Info) -> Info:
        schools = []
        for school in info.schools:
            if school.modules_known:
                self._known_modules[school.id] = school.modules
            elif school.id in self._known_modules:
                _LOGGER.info("the modules of school %s could not be read, the last known ones stay", school.id)
                school = replace(school, modules=self._known_modules[school.id], modules_known=True)
            schools.append(school)
        return replace(info, schools=tuple(schools))

    def _sync_login_issues(self, info: Info) -> None:
        entry_id = self.config_entry.entry_id
        prefix = login_issue_id(entry_id, "")
        listed = {school.id for school in info.schools}
        for domain, issue_id in list(ir.async_get(self.hass).issues):
            if domain == DOMAIN and issue_id.startswith(prefix) and issue_id[len(prefix):] not in listed:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        for school in info.schools:
            issue_id = login_issue_id(entry_id, school.id)
            if school.status == STATUS_AUTH_FAILED:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key=LOGIN_ISSUE_KEYS.get(school.status_reason, LOGIN_NEEDED_ISSUE_KEY),
                    translation_placeholders={"school": school.label},
                )
            else:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    def _clear_events_when_timetables_changed(self, states: dict[str, State]) -> None:
        previous = self.data.states if self.data else {}
        stamps = {key: state.timetable_last_updated for key, state in states.items()}
        known = {key: state.timetable_last_updated for key, state in previous.items()}
        if any(stamp != known.get(key) for key, stamp in stamps.items()):
            self.events.clear()

    def _reload_when_schools_modules_or_children_changed(self, info: Info) -> None:
        fingerprint = _fingerprint(info)
        if self._entity_fingerprint is None:
            self._entity_fingerprint = fingerprint
            return
        if fingerprint == self._entity_fingerprint:
            return
        before_schools, before_children = self._entity_fingerprint
        if tuple(school[0] for school in before_schools) != tuple(school[0] for school in fingerprint[0]):
            reason = "the set of schools changed (%d listed)" % len(info.schools)
        elif tuple(school[:2] for school in before_schools) != tuple(school[:2] for school in fingerprint[0]):
            reason = "the IServ modules of a school changed"
        elif before_schools != fingerprint[0]:
            reason = "the own entries setting of a school changed"
        else:
            reason = "the children of the schools changed (%d listed)" % len(info.children)
        _LOGGER.info("%s, reloading the Ranzenpost entities", reason)
        self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)

    def _fresh_changes(self, changes: list[Change]) -> tuple[list[Change], set[str] | None]:
        current = {change.id for change in changes}
        known = self._seen_changes
        if known is None:
            return [], current
        fresh = [change for change in changes if change.id not in known]
        if fresh and not self._started:
            _LOGGER.info("%d timetable changes wait until Home Assistant has started", len(fresh))
            return [], known & current
        return fresh, current

    async def _async_note_seen_changes(self, seen: set[str] | None) -> None:
        if seen is None or seen == self._seen_changes:
            return
        self._seen_changes = seen
        await self._changes_store.async_save({CHANGES_SEEN: sorted(seen)})
