import re
import time
from datetime import date

from bs4 import BeautifulSoup

from .iserv.dsa import API_ROOT, CURRENT_TIMETABLE_PATH
from .iserv.dsa_timetable import query_date
from .iserv.messenger import (
    XHR_CREDENTIALS,
    XHR_UNREACHABLE,
    BootstrapNotFoundError,
    authenticate_over_xhr,
    continuation_target,
    credentials_withheld,
    parse_bootstrap,
)
from .iserv.pages import path_of
from .pathpattern import path_pattern
from .module_catalogue import (
    CATALOGUE,
    CURRENT,
    NEW,
    OBSOLETE,
    SEGMENT_SLUGS,
    edition_of,
    english_label,
    official_name,
    slug_of,
)

TIMETABLE = "timetable"
LETTERS = "letters"
PINBOARD = "pinboard"
ABSENCES = "absences"
CONFERENCES = "conferences"
MESSENGER = "messenger"
MODULES = (TIMETABLE, LETTERS, PINBOARD, ABSENCES, CONFERENCES, MESSENGER)

AVAILABLE = "available"
MISSING = "missing"
UNKNOWN = "unknown"

ISERV_ROOT = "/iserv"
SEGMENTS = {
    "time-table": (TIMETABLE,),
    "parentletter": (LETTERS,),
    "parentconference": (CONFERENCES,),
    "messenger": (MESSENGER,),
    "dieschulapp": (PINBOARD, ABSENCES),
    "dsa-timetable": (TIMETABLE,),
    "dsa-pinboard": (PINBOARD,),
    "dsa-absences": (ABSENCES,),
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
    ABSENCES: (DSA_API + "/sickNotes/userSelection/", None),
    CONFERENCES: ("/iserv/parentconference/attendee/", None),
    MESSENGER: ("/iserv/messenger/", None),
}
MISSING_STATUSES = (403, 404)
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
PROBE_KEYS = MODULES + (LEGACY_TIMETABLE,)
HISTORY_LIMIT = 30


def default_registry():
    return {
        "modules": {name: True for name in MODULES},
        "unsupported": [],
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
    return {
        "segment": segment,
        "slug": slug,
        "label": _clean_label((entry or {}).get("label"), segment),
        "name": official_name(slug) or str((entry or {}).get("name") or ""),
    }


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
    base["modules"] = {name: bool(flags.get(name, True)) for name in MODULES}
    base["unsupported"] = [
        _unsupported_entry(entry)
        for entry in registry.get("unsupported") or []
        if isinstance(entry, dict) and str(entry.get("segment") or "").strip()
    ]
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


def _messenger_served(response, fetch):
    if continuation_target(response):
        return UNKNOWN
    html = getattr(response, "text", "") or ""
    try:
        parse_bootstrap(html)
        return AVAILABLE
    except BootstrapNotFoundError:
        pass
    if credentials_withheld(html):
        return AVAILABLE
    verdict = authenticate_over_xhr(lambda path: fetch(path, None), html).verdict
    if verdict == XHR_CREDENTIALS:
        return AVAILABLE
    if verdict == XHR_UNREACHABLE:
        return UNKNOWN
    return MISSING


PAGE_CHECKS = {MESSENGER: _messenger_served}


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


def _probe_all(fetch, today, school_app_timetable=True):
    outcomes = {}
    records = {}
    pages = []
    for name in MODULES:
        outcome = MISSING
        for path, params in probes_of(name, today, school_app_timetable):
            response = _probe(fetch, path, params)
            if response is not None and not path.startswith(DSA_API):
                pages.append(response)
            verdict = classify(response, path)
            if verdict == AVAILABLE and name in PAGE_CHECKS:
                verdict = PAGE_CHECKS[name](response, fetch)
            if name not in records or OUTCOME_RANK[verdict] >= OUTCOME_RANK[outcome]:
                records[name] = probe_record(path, response, verdict)
            if OUTCOME_RANK[verdict] > OUTCOME_RANK[outcome]:
                outcome = verdict
            if outcome == AVAILABLE:
                break
        outcomes[name] = outcome
    if pages and all(_landed_on_login(response) for response in pages):
        return {name: UNKNOWN for name in MODULES}, records
    if outcomes[TIMETABLE] != AVAILABLE:
        response = _probe(fetch, LEGACY_TIMETABLE_PATH, None)
        records[LEGACY_TIMETABLE] = probe_record(LEGACY_TIMETABLE_PATH, response, classify(response, LEGACY_TIMETABLE_PATH))
    return outcomes, records


def legacy_timetable_served(probes, outcomes):
    record = probes.get(LEGACY_TIMETABLE) or {}
    return record.get("verdict") == AVAILABLE and outcomes.get(TIMETABLE) != AVAILABLE


def with_legacy_timetable(unsupported):
    if any(entry.get("segment") == LEGACY_TIMETABLE_SEGMENT for entry in unsupported):
        return unsupported
    slug = slug_of(LEGACY_TIMETABLE_SEGMENT)
    entry = _unsupported_entry({"segment": LEGACY_TIMETABLE_SEGMENT, "label": official_name(slug)})
    return list(unsupported) + [entry]


def _linked_modules(links):
    linked = set()
    for entry in links:
        linked.update(SEGMENTS.get(entry["segment"], ()))
    return linked


def detect(html, fetch, previous, clock=time.time, login_html="", school_app_timetable=True):
    earlier = normalize(previous) if previous else None
    links = harvest_links(html)
    outcomes, probes = _probe_all(fetch, date.fromtimestamp(clock()), school_app_timetable)
    linked = _linked_modules(links)
    flags = {}
    for name in MODULES:
        outcome = outcomes[name]
        if outcome == AVAILABLE:
            flags[name] = True
        elif outcome == MISSING:
            flags[name] = False
        elif earlier is not None and earlier["checked_at"]:
            flags[name] = earlier["modules"][name]
        elif links:
            flags[name] = name in linked
        else:
            flags[name] = True
    unsupported, unknown = split_links(links)
    if not links and earlier is not None:
        unsupported = earlier["unsupported"]
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
        tuple(entry["segment"] for entry in normalized["unknown"]),
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
    parts = [
        "modules available: " + (", ".join(available) or "none"),
        "missing: " + (", ".join(missing) or "none"),
        f"not supported: {len(unsupported)}" + (f" ({', '.join(unsupported)})" if unsupported else ""),
        f"unknown: {len(segments)}" + (f" ({', '.join(segments)})" if segments else ""),
    ]
    return "; ".join(parts)


def school_app_timetable_served(registry):
    record = normalize(registry)["probes"].get(TIMETABLE) or {}
    return record.get("verdict") == AVAILABLE and record.get("path", "").startswith(DSA_API)


def available(registry, name):
    return normalize(registry)["modules"].get(name, True)


def any_available(registry):
    return any(normalize(registry)["modules"].values())
