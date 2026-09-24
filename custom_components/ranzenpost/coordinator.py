from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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
    EVENT_CACHE_TTL,
    LOGIN_ISSUE_KEYS,
    LOGIN_NEEDED_ISSUE_KEY,
    MAX_SCAN_INTERVAL,
    MIN_ADDON_VERSION,
    MIN_SCAN_INTERVAL,
    NO_SCHOOL_ISSUE_KEY,
    STATUS_AUTH_FAILED,
    UNKNOWN_VERSION,
)
from .signals import Signal, signals_between
from .version import ADDON_TOO_OLD, INTEGRATION_TOO_OLD, version_mismatch

_LOGGER = logging.getLogger(__name__)

VERSION_ISSUE_KEYS = (ADDON_TOO_OLD, INTEGRATION_TOO_OLD)
ENTRY_ISSUE_KEYS = (*VERSION_ISSUE_KEYS, NO_SCHOOL_ISSUE_KEY)
PLACEHOLDER_ADDON_VERSION = "addon_version"
PLACEHOLDER_INTEGRATION_VERSION = "integration_version"
PLACEHOLDER_REQUIRED_VERSION = "required_version"


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


def _fingerprint(info: Info) -> tuple[tuple[tuple[str, Modules, bool], ...], frozenset[str]]:
    schools = tuple((school.id, school.modules, school.own_entries) for school in info.schools)
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
        self.events = EventCache(self.api)
        self._seen_changes: set[tuple] = set()
        self._entity_fingerprint: tuple | None = None
        self._version_issue: str | None = None

    def _sync_version_issues(self, info: Info) -> None:
        entry_id = self.config_entry.entry_id
        mismatch = version_mismatch(info.version, self.integration_version, info.legacy)
        for key in VERSION_ISSUE_KEYS:
            if key != mismatch:
                ir.async_delete_issue(self.hass, DOMAIN, entry_issue_id(key, entry_id))
        if mismatch is None:
            self._version_issue = None
            return
        addon_version = info.version or UNKNOWN_VERSION
        integration_version = self.integration_version or UNKNOWN_VERSION
        if mismatch != self._version_issue:
            _LOGGER.warning(
                "the Ranzenpost add-on %s and the integration %s do not match (%s), update the older one",
                addon_version,
                integration_version,
                mismatch,
            )
        self._version_issue = mismatch
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            entry_issue_id(mismatch, entry_id),
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR if mismatch == ADDON_TOO_OLD else ir.IssueSeverity.WARNING,
            translation_key=mismatch,
            translation_placeholders={
                PLACEHOLDER_ADDON_VERSION: addon_version,
                PLACEHOLDER_INTEGRATION_VERSION: integration_version,
                PLACEHOLDER_REQUIRED_VERSION: MIN_ADDON_VERSION,
            },
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
        try:
            info = await self.api.info()
            self._sync_version_issues(info)
            self._sync_no_school_issue(info)
            states = {child.key: await self.api.state(child.key) for child in selected_children(info, self.config_entry)}
            schools = {school.id: await self.api.school(school.id) for school in info.schools}
            changes = await self.api.changes()
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except RanzenpostError as err:
            raise UpdateFailed(str(err)) from err
        self._clear_events_when_timetables_changed(states)
        self._reload_when_schools_modules_or_children_changed(info)
        self._sync_login_issues(info)
        new_changes = self._fresh_changes(changes)
        previous = self.data
        signals = signals_between(
            previous.info if previous else None, previous.states if previous else {}, info, states, new_changes
        )
        return RanzenpostData(info, states, schools, changes, new_changes, signals)

    def _sync_login_issues(self, info: Info) -> None:
        entry_id = self.config_entry.entry_id
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

    def _fresh_changes(self, changes: list[Change]) -> list[Change]:
        current = {change.key for change in changes}
        fresh = [change for change in changes if change.new and change.key not in self._seen_changes]
        self._seen_changes = current
        return fresh
