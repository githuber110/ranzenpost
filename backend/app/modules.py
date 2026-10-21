import re
import time
from datetime import date

from bs4 import BeautifulSoup

from .iserv.dsa import API_ROOT, CURRENT_TIMETABLE_PATH, SICK_NOTE_SELECTION_PATH
from .iserv.dsa_timetable import query_date
from .iserv.exercises import EXERCISE_PATH, is_exercise_page
from .iserv.forums import FORUMS_PATH, is_forum_page
from .iserv.infodisplay import INFODISPLAY_PATH, is_infodisplay_page
from .iserv.messenger import (
    XHR_CREDENTIALS,
    XHR_UNREACHABLE,
    BootstrapNotFoundError,
    authenticate_over_xhr,
    continuation_target,
    credentials_withheld,
    parse_bootstrap,
)
from .iserv.news import NEWS_PATH, is_news_page
from .iserv.older_absences import older_list_present
from .iserv.pages import path_of
from .iserv.texts import TEXTS_PATH, is_text_page
from .iserv.whiteboards import WHITEBOARDS_PATH, is_whiteboard_page
from .iserv.school_calendar import (
    CALENDAR_EVENTS_PATH,
    CALENDAR_SOURCES_PATH,
    CalendarShapeError,
    feed_request,
    feed_sources,
    parse_events,
    parse_sources,
    poll_window,
    window_params,
)
from .pathpattern import path_pattern
from .validate import normalize_school_url
from .module_catalogue import official_name, slug_of

TIMETABLE = "timetable"
LETTERS = "letters"
PINBOARD = "pinboard"
ABSENCES = "absences"
CONFERENCES = "conferences"
MESSENGER = "messenger"
CALENDAR = "calendar"
TASKS = "tasks"
NEWS = "news"
FORUMS = "forums"
TEXTS = "texts"
INFODISPLAY = "infodisplay"
WHITEBOARDS = "whiteboards"
ACCOUNT_MODULES = (FORUMS, TEXTS, INFODISPLAY, WHITEBOARDS)
MODULES = (TIMETABLE, LETTERS, PINBOARD, ABSENCES, CONFERENCES, MESSENGER, CALENDAR, TASKS, NEWS) + ACCOUNT_MODULES
CONFIRMED_ONLY = frozenset({CALENDAR, TASKS, NEWS}) | frozenset(ACCOUNT_MODULES)

AVAILABLE = "available"
MISSING = "missing"
UNKNOWN = "unknown"

ISERV_ROOT = "/iserv"
SEGMENTS = {
    "time-table": (TIMETABLE,),
    "parentletter": (LETTERS,),
    "parentconference": (CONFERENCES,),
    "messenger": (MESSENGER,),
    "calendar": (CALENDAR,),
    "exercise": (TASKS,),
    "news": (NEWS,),
    "dieschulapp": (PINBOARD, ABSENCES),
    "dsa-timetable": (TIMETABLE,),
    "dsa-pinboard": (PINBOARD,),
    "dsa-absences": (ABSENCES,),
    "forum": (FORUMS,),
    "forums": (FORUMS,),
    "etherpad": (TEXTS,),
    "infodisplay": (INFODISPLAY,),
    "excalidraw": (WHITEBOARDS,),
}
IGNORED_SEGMENTS = frozenset(
    {
        "about",
        "account",
        "admin",
        "app",
        "auth",
        "help",
        "imprint",
        "legal",
        "login",
        "logout",
        "notification",
        "notifications",
        "privacy",
        "profile",
        "search",
        "settings",
        "user",
    }
)
DSA_API = API_ROOT
DSA_TIMETABLE_PATH = DSA_API + "/" + CURRENT_TIMETABLE_PATH
PROBES = {
    TIMETABLE: ("/iserv/time-table/", None),
    LETTERS: ("/iserv/parentletter/parent/index", None),
    PINBOARD: (DSA_API + "/pinboards/", {"fields": "id"}),
    ABSENCES: (DSA_API + "/" + SICK_NOTE_SELECTION_PATH, None),
    CONFERENCES: ("/iserv/parentconference/attendee/", None),
    MESSENGER: ("/iserv/messenger/", None),
    CALENDAR: (CALENDAR_SOURCES_PATH, None),
    TASKS: (EXERCISE_PATH, None),
    NEWS: (NEWS_PATH, None),
    FORUMS: (FORUMS_PATH, None),
    TEXTS: (TEXTS_PATH, None),
    INFODISPLAY: (INFODISPLAY_PATH, None),
    WHITEBOARDS: (WHITEBOARDS_PATH, None),
}
MISSING_STATUSES = (403, 404)
ANSWER_REFUSED_STATUSES = (401, 403, 404)
OUTCOME_RANK = {AVAILABLE: 2, UNKNOWN: 1, MISSING: 0}
LOGIN_MARKERS = ("/iserv/auth/", "/iserv/login", "/idesk/login")
VERSION_NUMBER = r"v?(\d+(?:\.\d+)+)(?!\.?\d)"
VERSION_PATTERNS = (
    re.compile(r"IServ(?:\s+Schulserver)?\s+" + VERSION_NUMBER),
    re.compile(r"\bversion\b[\"']?\s*[:=]?\s*[\"']?" + VERSION_NUMBER, re.IGNORECASE),
)
LABEL_LIMIT = 60


PROBE_FIELDS = ("path", "status", "content_type", "length", "final_path", "verdict")
HISTORY_KEY = "history"
LEGACY_TIMETABLE = "timetable-legacy"
LEGACY_TIMETABLE_SEGMENT = "timetable"
LEGACY_TIMETABLE_PATH = "/iserv/timetable/"
OLDER_ABSENCES = "absences-older"
OLDER_ABSENCE_SEGMENT = "absence"
OLDER_ABSENCE_PATH = "/iserv/absence/"
PROBE_KEYS = MODULES + (LEGACY_TIMETABLE, OLDER_ABSENCES)
COVERED_BY = {"absence_obsolete": ABSENCES}
MAIL = "mail"
FILES = "file"
ADDRESSBOOK = "addressbook"
MAILING_LISTS = "mailinglist"
LISTED_MODULES = (FILES, ADDRESSBOOK, MAILING_LISTS)
READ_BY_APP = frozenset({MAIL}) | frozenset(LISTED_MODULES)
HISTORY_LIMIT = 30


def default_registry():
    return {
        "modules": {name: name not in CONFIRMED_ONLY for name in MODULES},
        "unsupported": [],
        "covered": [],
        "unknown": [],
        "probes": {},
        "checked_at": 0,
        "iserv_version": "",
    }


def _content_type(response):
    headers = getattr(response, "headers", None) or {}
    try:
        raw = headers.get("Content-Type") or headers.get("content-type") or ""
    except AttributeError:
        raw = ""
    return str(raw).split(";", 1)[0].strip().lower()


def _body_length(response):
    content = getattr(response, "content", None)
    if isinstance(content, (bytes, bytearray)):
        return len(content)
    text = getattr(response, "text", "")
    return len(text.encode("utf-8")) if isinstance(text, str) else 0


def probe_record(path, response, verdict):
    if response is None:
        return {"path": path_pattern(path), "status": 0, "content_type": "", "length": 0, "final_path": "", "verdict": verdict}
    return {
        "path": path_pattern(path),
        "status": int(getattr(response, "status_code", 0) or 0),
        "content_type": _content_type(response),
        "length": _body_length(response),
        "final_path": path_pattern(getattr(response, "url", "") or ""),
        "verdict": verdict,
    }


def _clean_probe(entry):
    if not isinstance(entry, dict):
        return None
    status = entry.get("status")
    try:
        status = int(status or 0)
    except (TypeError, ValueError):
        status = 0
    length = entry.get("length")
    try:
        length = int(length or 0)
    except (TypeError, ValueError):
        length = 0
    return {
        "path": str(entry.get("path") or ""),
        "status": status,
        "content_type": str(entry.get("content_type") or ""),
        "length": length,
        "final_path": str(entry.get("final_path") or ""),
        "verdict": str(entry.get("verdict") or ""),
    }


def _clean_label(text, fallback):
    label = " ".join(str(text or "").split())[:LABEL_LIMIT]
    return label or fallback


def _unknown_entry(entry):
    segment = str((entry or {}).get("segment") or "").strip()
    return {"segment": segment, "label": _clean_label((entry or {}).get("label"), segment)}


def is_known_segment(segment):
    return bool(slug_of(segment))


def _unsupported_entry(entry):
    segment = str((entry or {}).get("segment") or "").strip()
    slug = slug_of(segment) or str((entry or {}).get("slug") or "").strip()
    cleaned = {
        "segment": segment,
        "slug": slug,
        "label": _clean_label((entry or {}).get("label"), segment),
        "name": official_name(slug) or str((entry or {}).get("name") or ""),
    }
    return cleaned


def open_page_url(school_url, path):
    try:
        base = normalize_school_url(school_url)
    except ValueError:
        return ""
    return base + path


def lists_module(registry, slug):
    listed = list((registry or {}).get("unsupported") or []) + list((registry or {}).get("covered") or [])
    return any(isinstance(entry, dict) and entry.get("slug") == slug for entry in listed)


def read_by_app(entry):
    return isinstance(entry, dict) and entry.get("slug") in READ_BY_APP


def _covered(entry, flags):
    if read_by_app(entry):
        return True
    covering = COVERED_BY.get(entry.get("slug"))
    return bool(covering) and bool(flags.get(covering))


def split_links(links):
    unsupported = []
    unknown = []
    for entry in links:
        segment = entry["segment"]
        if segment in SEGMENTS or segment in IGNORED_SEGMENTS:
            continue
        if is_known_segment(segment):
            unsupported.append(_unsupported_entry(entry))
        else:
            unknown.append(_unknown_entry(entry))
    return unsupported, unknown


def normalize(registry):
    base = default_registry()
    if not isinstance(registry, dict):
        return base
    flags = registry.get("modules") if isinstance(registry.get("modules"), dict) else {}
    base["modules"] = {name: bool(flags.get(name, name not in CONFIRMED_ONLY)) for name in MODULES}
    present = [
        _unsupported_entry(entry)
        for entry in (registry.get("unsupported") or []) + (registry.get("covered") or [])
        if isinstance(entry, dict) and str(entry.get("segment") or "").strip()
    ]
    base["unsupported"] = [entry for entry in present if not _covered(entry, base["modules"])]
    base["covered"] = [entry for entry in present if _covered(entry, base["modules"])]
    base["unknown"] = [
        _unknown_entry(entry)
        for entry in registry.get("unknown") or []
        if isinstance(entry, dict) and str(entry.get("segment") or "").strip()
    ]
    probes = registry.get("probes") if isinstance(registry.get("probes"), dict) else {}
    for name in PROBE_KEYS:
        cleaned = _clean_probe(probes.get(name))
        if cleaned is not None:
            base["probes"][name] = cleaned
    checked = registry.get("checked_at")
    base["checked_at"] = int(checked) if isinstance(checked, (int, float)) and not isinstance(checked, bool) else 0
    base["iserv_version"] = str(registry.get("iserv_version") or "")
    return base


def registry_of(service):
    reader = getattr(service, "modules", None)
    if not callable(reader):
        return default_registry()
    try:
        return normalize(reader())
    except Exception:
        return default_registry()


def _first_segment(href):
    path = path_of(href)
    if not path.startswith(ISERV_ROOT + "/"):
        return ""
    rest = path[len(ISERV_ROOT) + 1 :]
    return rest.split("/", 1)[0].strip().lower()


def harvest_links(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    seen = {}
    order = []
    for anchor in soup.find_all("a", href=True):
        segment = _first_segment(anchor.get("href"))
        if not segment:
            continue
        label = " ".join(anchor.get_text(" ").split())
        if segment not in seen:
            seen[segment] = label
            order.append(segment)
        elif not seen[segment] and label:
            seen[segment] = label
    return [{"segment": segment, "label": _clean_label(seen[segment], segment)} for segment in order]


def _version_in(text):
    for pattern in VERSION_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return ""


def iserv_version(html):
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    generator = soup.find("meta", attrs={"name": "generator"})
    candidates = [str(generator.get("content") or "")] if generator else []
    footer = soup.find("footer")
    if footer is not None:
        candidates.append(footer.get_text(" "))
    candidates.append(soup.get_text(" "))
    candidates.extend(script.get_text() for script in soup.find_all("script"))
    for text in candidates:
        found = _version_in(text)
        if found:
            return found
    return ""


def _is_login_path(path):
    return any(path.startswith(marker) for marker in LOGIN_MARKERS)


def classify(response, probe_path):
    if response is None:
        return UNKNOWN
    status = int(getattr(response, "status_code", 0) or 0)
    if status in MISSING_STATUSES:
        return MISSING
    final = path_of(getattr(response, "url", "") or "")
    if final and _is_login_path(final):
        return MISSING
    if status != 200:
        return UNKNOWN
    if final.rstrip("/") == ISERV_ROOT and probe_path.rstrip("/") != ISERV_ROOT:
        return MISSING
    return AVAILABLE


def _landed_on_login(response):
    return response is not None and _is_login_path(path_of(getattr(response, "url", "") or ""))


def _messenger_served(response, fetch, today):
    if continuation_target(response):
        return UNKNOWN, 0
    html = getattr(response, "text", "") or ""
    try:
        parse_bootstrap(html)
        return AVAILABLE, 0
    except BootstrapNotFoundError:
        pass
    if credentials_withheld(html):
        return AVAILABLE, 0
    outcome = authenticate_over_xhr(lambda path: fetch(path, None), html)
    if outcome.verdict == XHR_CREDENTIALS:
        return AVAILABLE, 0
    statuses = [status for _path, status in outcome.attempts]
    if outcome.verdict == XHR_UNREACHABLE or any(_inconclusive(status) for status in statuses):
        return UNKNOWN, 0
    return MISSING, _all_refused(statuses)


def _all_refused(statuses):
    if statuses and all(status in ANSWER_REFUSED_STATUSES for status in statuses):
        return statuses[-1]
    return 0


def _inconclusive(status):
    return status != 200 and status not in ANSWER_REFUSED_STATUSES


def _refusal_of(response):
    status = int(getattr(response, "status_code", 0) or 0)
    return status if status in MISSING_STATUSES else 0


def _calendar_feeds(response, today):
    reader = getattr(response, "json", None)
    try:
        sources = feed_sources(reader() if callable(reader) else None)
    except (ValueError, TypeError, CalendarShapeError):
        return None
    requests = [feed_request(source["url"], *poll_window(today)) for source in sources]
    return [request for request in requests if request is not None]


def _school_calendar_served(response, fetch, today):
    if not _json_reads(response, parse_sources):
        return MISSING, 0
    feeds = _calendar_feeds(response, today) or [(CALENDAR_EVENTS_PATH, window_params(today))]
    statuses = []
    for path, params in feeds:
        events = fetch(path, params)
        status = int(getattr(events, "status_code", 0) or 0)
        if status == 200 and _json_reads(events, parse_events):
            return AVAILABLE, 0
        statuses.append(status)
    if any(_inconclusive(status) for status in statuses):
        return UNKNOWN, 0
    return MISSING, _all_refused(statuses)


def _json_reads(response, parse):
    reader = getattr(response, "json", None)
    try:
        parse(reader() if callable(reader) else None)
    except (ValueError, TypeError, CalendarShapeError):
        return False
    return True


def _page_kept(within):
    def check(response, fetch, today):
        return (AVAILABLE if within(getattr(response, "url", "") or "") else MISSING), 0

    return check


PAGE_CHECKS = {
    MESSENGER: _messenger_served,
    CALENDAR: _school_calendar_served,
    TASKS: _page_kept(is_exercise_page),
    NEWS: _page_kept(is_news_page),
    FORUMS: _page_kept(is_forum_page),
    TEXTS: _page_kept(is_text_page),
    INFODISPLAY: _page_kept(is_infodisplay_page),
    WHITEBOARDS: _page_kept(is_whiteboard_page),
}


def _school_app_timetable_probe(today):
    return (DSA_TIMETABLE_PATH, {"date": query_date(today), "week": "true", "substitutions": "false"})


def probes_of(name, today, school_app_timetable=True):
    if name == TIMETABLE:
        return ((_school_app_timetable_probe(today),) if school_app_timetable else ()) + (PROBES[name],)
    return (PROBES[name],)


def _probe(fetch, path, params):
    try:
        return fetch(path, params)
    except OSError:
        return None


def _probe_all(fetch, today, school_app_timetable=True, skip=frozenset(), earlier_probes=None):
    outcomes = {}
    records = {}
    refused = {}
    pages = []
    earlier_probes = earlier_probes or {}
    for name in MODULES:
        outcome = MISSING
        if name in skip:
            outcomes[name] = MISSING
            if name in earlier_probes:
                records[name] = earlier_probes[name]
            continue
        refusals = []
        for path, params in probes_of(name, today, school_app_timetable):
            response = _probe(fetch, path, params)
            if response is not None and not path.startswith(DSA_API):
                pages.append(response)
            verdict = classify(response, path)
            refusal = _refusal_of(response) if verdict == MISSING else 0
            if verdict == AVAILABLE and name in PAGE_CHECKS:
                verdict, refusal = PAGE_CHECKS[name](response, fetch, today)
            refusals.append(refusal)
            if name not in records or OUTCOME_RANK[verdict] >= OUTCOME_RANK[outcome]:
                records[name] = probe_record(path, response, verdict)
            if OUTCOME_RANK[verdict] > OUTCOME_RANK[outcome]:
                outcome = verdict
            if outcome == AVAILABLE:
                break
        outcomes[name] = outcome
        if outcome == MISSING and refusals and all(refusals):
            refused[name] = refusals[-1]
    if pages and all(_landed_on_login(response) for response in pages):
        return {name: MISSING if name in skip else UNKNOWN for name in MODULES}, records, {}
    if outcomes[TIMETABLE] != AVAILABLE and TIMETABLE in skip:
        if LEGACY_TIMETABLE in earlier_probes:
            records[LEGACY_TIMETABLE] = earlier_probes[LEGACY_TIMETABLE]
    elif outcomes[TIMETABLE] != AVAILABLE:
        response = _probe(fetch, LEGACY_TIMETABLE_PATH, None)
        records[LEGACY_TIMETABLE] = probe_record(LEGACY_TIMETABLE_PATH, response, classify(response, LEGACY_TIMETABLE_PATH))
    return outcomes, records, refused


def legacy_timetable_served(probes, outcomes):
    record = probes.get(LEGACY_TIMETABLE) or {}
    return record.get("verdict") == AVAILABLE and outcomes.get(TIMETABLE) != AVAILABLE


def with_legacy_timetable(unsupported):
    if any(entry.get("segment") == LEGACY_TIMETABLE_SEGMENT for entry in unsupported):
        return unsupported
    slug = slug_of(LEGACY_TIMETABLE_SEGMENT)
    entry = _unsupported_entry({"segment": LEGACY_TIMETABLE_SEGMENT, "label": official_name(slug)})
    return list(unsupported) + [entry]


def _older_absence_verdict(response):
    verdict = classify(response, OLDER_ABSENCE_PATH)
    if verdict == AVAILABLE and not older_list_present(getattr(response, "text", "") or ""):
        return MISSING
    return verdict


def _older_absence_linked(links, earlier):
    if any(entry["segment"] == OLDER_ABSENCE_SEGMENT for entry in links):
        return True
    record = (earlier or {}).get("probes", {}).get(OLDER_ABSENCES) or {}
    return not links and record.get("verdict") == AVAILABLE


def _older_absence_probe(fetch, links, earlier, outcome):
    if outcome == MISSING and _older_absence_linked(links, earlier):
        response = _probe(fetch, OLDER_ABSENCE_PATH, None)
        verdict = _older_absence_verdict(response)
        if verdict == UNKNOWN and earlier is not None and earlier["probes"].get(OLDER_ABSENCES):
            return earlier["probes"][OLDER_ABSENCES]
        return probe_record(OLDER_ABSENCE_PATH, response, verdict)
    if outcome == UNKNOWN and earlier is not None:
        return earlier["probes"].get(OLDER_ABSENCES)
    return None


def older_absences_served(probes, outcomes):
    record = probes.get(OLDER_ABSENCES) or {}
    return record.get("verdict") == AVAILABLE and outcomes.get(ABSENCES) != AVAILABLE


def older_absences(registry):
    normalized = normalize(registry)
    school_app = normalized["probes"].get(ABSENCES) or {}
    record = normalized["probes"].get(OLDER_ABSENCES) or {}
    return (
        normalized["modules"][ABSENCES]
        and record.get("verdict") == AVAILABLE
        and school_app.get("verdict") != AVAILABLE
    )


def school_app_absences(registry):
    normalized = normalize(registry)
    return normalized["modules"][ABSENCES] and not older_absences(normalized)


def _linked_modules(links):
    linked = set()
    for entry in links:
        linked.update(SEGMENTS.get(entry["segment"], ()))
    return linked


def _ledger_key(name):
    return ("module", name)


def _linked_key(name):
    return ("module-linked", name)


def _school_app_served_earlier(earlier, name):
    if name == ABSENCES:
        return school_app_absences(earlier)
    return earlier["modules"][name]


def _skipped_modules(earlier, ledger, linked):
    if ledger is None or earlier is None:
        return frozenset()
    return frozenset(
        name
        for name in MODULES
        if not _school_app_served_earlier(earlier, name)
        and ledger.refused(_ledger_key(name))
        and not (name in linked and not ledger.refused(_linked_key(name)))
    )


def _settle_ledger(ledger, skip, outcomes, refused, linked):
    if ledger is None:
        return
    for name in MODULES:
        if name in skip:
            continue
        if outcomes[name] == MISSING and refused.get(name):
            ledger.note(_ledger_key(name), refused[name])
            if name in linked:
                ledger.note(_linked_key(name), 1)
            else:
                ledger.forget(_linked_key(name))
        else:
            ledger.forget(_ledger_key(name))
            ledger.forget(_linked_key(name))


def detect(html, fetch, previous, clock=time.time, login_html="", school_app_timetable=True, ledger=None):
    earlier = normalize(previous) if previous else None
    links = harvest_links(html)
    linked = _linked_modules(links)
    skip = _skipped_modules(earlier, ledger, linked)
    outcomes, probes, refused = _probe_all(
        fetch, date.fromtimestamp(clock()), school_app_timetable, skip, earlier["probes"] if earlier else None
    )
    _settle_ledger(ledger, skip, outcomes, refused, linked)
    flags = {}
    for name in MODULES:
        outcome = outcomes[name]
        if outcome == AVAILABLE:
            flags[name] = True
        elif outcome == MISSING:
            flags[name] = False
        elif earlier is not None and earlier["checked_at"]:
            flags[name] = earlier["modules"][name]
        elif name in CONFIRMED_ONLY:
            flags[name] = False
        elif links:
            flags[name] = name in linked
        else:
            flags[name] = True
    older = _older_absence_probe(fetch, links, earlier, outcomes[ABSENCES])
    if older is not None:
        probes[OLDER_ABSENCES] = older
    if older_absences_served(probes, outcomes):
        flags[ABSENCES] = True
    unsupported, unknown = split_links(links)
    if not links and earlier is not None:
        unsupported = earlier["unsupported"] + earlier["covered"]
        unknown = earlier["unknown"]
    if legacy_timetable_served(probes, outcomes):
        unsupported = with_legacy_timetable(unsupported)
    version = iserv_version(html) or iserv_version(login_html) or (earlier["iserv_version"] if earlier else "")
    return {
        "modules": flags,
        "unsupported": unsupported,
        "unknown": unknown,
        "probes": probes,
        "checked_at": int(clock()),
        "iserv_version": version,
    }


def _signature(registry):
    normalized = normalize(registry)
    return (
        tuple(normalized["modules"][name] for name in MODULES),
        tuple(entry["segment"] for entry in normalized["unsupported"]),
        tuple(entry["segment"] for entry in normalized["covered"]),
        tuple(entry["segment"] for entry in normalized["unknown"]),
        older_absences(normalized),
    )


def changed(previous, current):
    if not isinstance(previous, dict):
        return True
    return _signature(previous) != _signature(current)


def history_of(stored):
    raw = stored.get(HISTORY_KEY) if isinstance(stored, dict) else None
    entries = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        moment = entry.get("at")
        if not isinstance(moment, (int, float)) or isinstance(moment, bool):
            continue
        entries.append({
            "at": int(moment),
            "summary": str(entry.get("summary") or ""),
            "iserv_version": str(entry.get("iserv_version") or ""),
        })
    return entries[-HISTORY_LIMIT:]


def with_history(previous, current):
    history = history_of(previous)
    earlier = normalize(previous) if isinstance(previous, dict) and previous else None
    version_moved = earlier is not None and earlier["iserv_version"] != normalize(current)["iserv_version"]
    if changed(previous if previous else None, current) or version_moved:
        history.append({
            "at": int(current.get("checked_at") or 0),
            "summary": summary(current),
            "iserv_version": str(current.get("iserv_version") or ""),
        })
    stored = dict(current)
    stored[HISTORY_KEY] = history[-HISTORY_LIMIT:]
    return stored


def summary(registry):
    normalized = normalize(registry)
    available = [name for name in MODULES if normalized["modules"][name]]
    missing = [name for name in MODULES if not normalized["modules"][name]]
    unsupported = [entry["slug"] or entry["segment"] for entry in normalized["unsupported"]]
    segments = [entry["segment"] for entry in normalized["unknown"]]
    covered = [entry["slug"] or entry["segment"] for entry in normalized["covered"] if not read_by_app(entry)]
    read = [entry["slug"] or entry["segment"] for entry in normalized["covered"] if read_by_app(entry)]
    parts = [
        "modules available: " + (", ".join(available) or "none"),
        "missing: " + (", ".join(missing) or "none"),
        f"not supported: {len(unsupported)}" + (f" ({', '.join(unsupported)})" if unsupported else ""),
        f"unknown: {len(segments)}" + (f" ({', '.join(segments)})" if segments else ""),
    ]
    if covered:
        parts.append(f"covered by another module: {len(covered)} ({', '.join(covered)})")
    if read:
        parts.append(f"read by the app: {len(read)} ({', '.join(read)})")
    if older_absences(normalized):
        parts.append("absences read from the older page (absence_obsolete)")
    return "; ".join(parts)


def school_app_timetable_served(registry):
    record = normalize(registry)["probes"].get(TIMETABLE) or {}
    return record.get("verdict") == AVAILABLE and record.get("path", "").startswith(DSA_API)


def available(registry, name):
    return normalize(registry)["modules"].get(name, True)
