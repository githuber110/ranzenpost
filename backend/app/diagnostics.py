import io
import json
import logging
import platform
import re
import threading
import time
import zipfile

from . import feed, integration, logfile, modules, namebook, supervisor, valueshape
from .iserv.children import (
    child_select_present,
    parse_children,
    time_table_absence,
    time_table_recognised,
    time_table_session_lost,
)
from .iserv.timetable import data_params, with_time_table_changes
from .module_catalogue import edition_of, official_name
from .pageshape import body_kind, json_of, response_skeleton, shape_block, status_of, visible_text
from .pathpattern import MATRIX_ROOM, ROOM_MARK
from .reportcrawl import (
    CrawlBudget,
    capped_module,
    linked_rows,
    menu_lines,
    menu_paths_by_segment,
    menu_shape,
    module_crawl,
    module_link_structure,
    module_prefix,
    script_section,
    start_page_links,
    unsupported_module_lines,
)
from .reportfacts import children_lines, iserv_version_lines, letters_summary_lines, listed_children, school_app_query_lines
from .requestlog import messenger_sync_lines, slow_request_lines
from .scriptscan import SCRIPT_ROOT
from .store import host_of
from .timetable_source import SCHOOL_APP_SOURCE, SOURCE_KEY, matching_option
from .valueshape import table_cell

logger = logging.getLogger(__name__)

SCHOOL_TIMEZONE = "Europe/Berlin"
TITLE = "# Ranzenpost report"
STATUS_SUPPORTED = "supported"
STATUS_MISSING = "missing"
STATUS_UNKNOWN = "unknown"
STATUS_ERROR = "error"
STATUS_NOT_PROBED = "not probed"
STATUS_ASSUMED = "assumed, never checked"
STATUS_UNSUPPORTED = "present, not supported"
VERDICT_STATUS = {modules.AVAILABLE: STATUS_SUPPORTED, modules.MISSING: STATUS_MISSING, modules.UNKNOWN: STATUS_UNKNOWN}
LEGACY_TIMETABLE = modules.LEGACY_TIMETABLE
KNOWN_ROWS = (
    (modules.TIMETABLE, "timetable", "/iserv/time-table/"),
    (modules.TIMETABLE, LEGACY_TIMETABLE, modules.LEGACY_TIMETABLE_PATH),
    (modules.TIMETABLE, "dsa-timetable", "/iserv/dsa-timetable/"),
    (modules.LETTERS, "parentletter", modules.PROBES[modules.LETTERS][0]),
    (modules.PINBOARD, "dsa-pinboard", "/iserv/dsa-pinboard/"),
    (modules.ABSENCES, "absence", "/iserv/dsa-absences/"),
    (modules.CONFERENCES, "parentconference", modules.PROBES[modules.CONFERENCES][0]),
    (modules.MESSENGER, "messenger", modules.PROBES[modules.MESSENGER][0]),
)
CATALOGUE_SLUGS = {LEGACY_TIMETABLE: "timetable"}
TIME_TABLE_SLUG = "timetable"
TIME_TABLE_DATA = "/iserv/time-table/data"
DATA_PATHS = {
    TIME_TABLE_SLUG: TIME_TABLE_DATA,
    LEGACY_TIMETABLE: "/iserv/timetable/data",
}
JSON_PROBES = {
    "dsa-timetable": modules.TIMETABLE,
    "dsa-pinboard": modules.PINBOARD,
    "absence": modules.ABSENCES,
}
TABLE_HEAD = "| Module | Slug | Edition | Status | Probe | HTTP | Content type | Length | Final path |"
TABLE_RULE = "|---|---|---|---|---|---|---|---|---|"
MAX_UNKNOWN_STRUCTURE_ROWS = 10
MIN_WORD = 3
MIN_SCHOOL_WORD = 4
MIN_SECRET = 4
EMAIL = re.compile(r"[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,10}")
BEARER = re.compile(r"(?i)\bBearer\s+\S{1,4096}")
ASSIGNED_SECRET = re.compile(
    r"(?i)\b(PHPSESSID|IServSession|REMEMBERME|[A-Za-z_]{0,64}(?:token|secret|password|passwd|session|cookie|totp)[A-Za-z_]{0,64})=([^;\s&\"']{1,4096})"
)
URL_HOST = re.compile(r"(?i)\bhttps?://[^\s/\"'<>]{1,2048}")
HOST_SUFFIXES = ("de", "com", "net", "org", "eu", "schule", "school", "example", "local", "io", "info", "edu", "at", "ch")
BARE_HOST = re.compile(r"(?i)\b(?:[a-z0-9-]{1,63}\.){1,10}(?:" + "|".join(HOST_SUFFIXES) + r")\b")
MODULE_NAME = re.compile(r"[^a-z0-9_-]")
MIN_PHONE = 6
REPORT_LOG_TAIL = 200
BUNDLE_NAME = "ranzenpost-report.zip"
REPORT_FILE = "report.md"
LOG_FILE = "log.txt"
REPORT_CACHE_SECONDS = 600
WORD_FIELDS = ("children", "schools", "teachers", "users", "hosts", "secrets", "phones")


class RedactionWords:
    def __init__(self, children=(), schools=(), teachers=(), users=(), hosts=(), secrets=(), phones=()):
        self.children = _clean_words(children)
        self.schools = _clean_words(schools)
        self.teachers = _clean_words(teachers)
        self.users = _clean_words(users)
        self.hosts = _clean_words(hosts)
        self.secrets = [word for word in _clean_words(secrets) if len(word) >= MIN_SECRET]
        self.phones = [word for word in _clean_words(phones) if len(word) >= MIN_PHONE]

    def extend(self, other):
        for field in WORD_FIELDS:
            merged = getattr(self, field) + [word for word in getattr(other, field) if word not in getattr(self, field)]
            setattr(self, field, merged)
        return self


def _clean_words(values):
    cleaned = []
    for value in values or ():
        text = " ".join(str(value or "").split())
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _name_parts(names, minimum, split=True):
    parts = []
    for name in names:
        candidates = [name] + ([part for part in re.split(r"[\s,;/()]+", name) if part] if split else [])
        for candidate in candidates:
            candidate = candidate.strip(".-_")
            if len(candidate) >= minimum and candidate not in parts:
                parts.append(candidate)
    return sorted(parts, key=len, reverse=True)


def _alternation(words, bounded):
    ordered = sorted({word for word in words if word}, key=lambda word: (-len(word), word))
    if not ordered:
        return None
    body = "|".join(re.escape(word) for word in ordered)
    if bounded:
        body = r"(?<![\w])(?:" + body + r")(?![\w])"
    return re.compile(body, re.IGNORECASE)


def _substrings(words, minimum):
    return [word for word in words if len(word) >= minimum]


class Redactor:
    def __init__(self, words=None):
        words = words or RedactionWords()
        self.secrets = _alternation(_substrings(words.secrets, MIN_SECRET), False)
        self.phones = _alternation(_substrings(words.phones, MIN_PHONE), False)
        self.hosts = _alternation(_substrings(words.hosts, MIN_WORD), False)
        self.children = _alternation(_name_parts(words.children, MIN_WORD), True)
        self.teachers = _alternation(_name_parts(words.teachers, MIN_WORD), True)
        self.schools = _alternation(_name_parts(words.schools, MIN_SCHOOL_WORD, split=False), True)
        self.users = _alternation(_name_parts(words.users, MIN_WORD, split=False), True)

    def __call__(self, text):
        line = MATRIX_ROOM.sub(ROOM_MARK, str(text or ""))
        line = _swap(self.secrets, "<secret>", line)
        line = _swap(self.phones, "<phone>", line)
        line = EMAIL.sub("<email>", line)
        line = BEARER.sub("Bearer <secret>", line)
        line = ASSIGNED_SECRET.sub(lambda match: match.group(1) + "=<secret>", line)
        line = _swap(self.hosts, "<host>", line)
        line = URL_HOST.sub(lambda match: match.group(0).split("://", 1)[0] + "://<host>", line)
        line = BARE_HOST.sub("<host>", line)
        line = _swap(self.children, "<child>", line)
        line = _swap(self.teachers, "<teacher>", line)
        line = _swap(self.schools, "<school>", line)
        return _swap(self.users, "<user>", line)


def _swap(pattern, marker, text):
    return pattern.sub(marker, text) if pattern is not None else text


def redact(text, words):
    return Redactor(words)(text)


GENERIC = Redactor()


def scrub_line(line):
    return namebook.scrub(GENERIC(line))


def learn_words(book, words):
    if book is None:
        return
    book.learn(words.children + words.teachers + words.schools + words.users, [], words.hosts)


def _secret_values(secrets):
    values = []
    for key, value in (secrets or {}).items():
        if key == "username" or not isinstance(value, str):
            continue
        if value.strip():
            values.append(value.strip())
    return values


def redaction_words_of(connection, me=None):
    config = _config_of(connection)
    secrets = _secrets_of(connection)
    children = [child.get("name") for child in config.get("children") or [] if isinstance(child, dict)]
    teachers = []
    for entry in (config.get("teachers") or {}).values():
        if isinstance(entry, dict):
            teachers.extend([entry.get("label"), entry.get("surname")])
    schools = [config.get("school_name"), config.get("label"), config.get("short_name")]
    users = [secrets.get("username")]
    hosts = [host_of(config.get("school_url"))]
    phones = [entry.get("number") for entry in config.get("phones") or [] if isinstance(entry, dict)]
    words = RedactionWords(children, schools, teachers, users, hosts, _secret_values(secrets), phones)
    if isinstance(me, dict):
        words.extend(RedactionWords(
            children=[],
            schools=[me.get("school_name"), me.get("school_address")],
            teachers=[],
            users=[me.get("forename"), me.get("surname"), me.get("displayname"), me.get("username"), me.get("email")],
            hosts=[],
            secrets=[],
            phones=[me.get("phone"), me.get("mobile")],
        ))
    return words


def _config_of(connection):
    store = getattr(connection, "store", None)
    try:
        config = store.load_config() if store is not None else {}
    except Exception:
        config = {}
    return config if isinstance(config, dict) else {}


def _secrets_of(connection):
    store = getattr(connection, "store", None)
    try:
        secrets = store.load_secrets() if store is not None else {}
    except Exception:
        secrets = {}
    return secrets if isinstance(secrets, dict) else {}


def _yes_no(value):
    if value is None:
        return "unknown"
    return "yes" if value else "no"


def _stamp(epoch):
    local = feed.berlin_moment(epoch)
    offset = feed.berlin_offset(local)
    return local.isoformat(timespec="seconds") + "+%02d:00" % offset


def _module_row(name, slug, edition, status, probe):
    probe = probe or {}
    return "| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        table_cell(name),
        table_cell(slug),
        table_cell(edition),
        table_cell(status),
        table_cell(probe.get("verdict") or "-"),
        table_cell(probe.get("status") or "-"),
        table_cell(probe.get("content_type") or "-"),
        table_cell(probe.get("length") if probe else "-"),
        table_cell(valueshape.link_shape(probe.get("final_path")) if probe.get("final_path") else "-"),
    )


def _legacy_listed(registry):
    return any(entry.get("segment") == modules.LEGACY_TIMETABLE_SEGMENT for entry in registry["unsupported"])


def _legacy_pair(registry):
    record = registry["probes"].get(modules.LEGACY_TIMETABLE)
    if not record:
        return (STATUS_UNSUPPORTED if _legacy_listed(registry) else STATUS_NOT_PROBED), None
    verdict = record.get("verdict")
    if verdict == modules.AVAILABLE or _legacy_listed(registry):
        return STATUS_UNSUPPORTED, record
    return VERDICT_STATUS.get(verdict, STATUS_UNKNOWN), record


def _timetable_pair(registry, slug):
    if slug == LEGACY_TIMETABLE:
        return _legacy_pair(registry)
    record = registry["probes"].get(modules.TIMETABLE) or {}
    matched = record and (record.get("path", "").startswith(modules.DSA_API) == (slug == "dsa-timetable"))
    if matched:
        return VERDICT_STATUS.get(record.get("verdict"), STATUS_UNKNOWN), record
    verdict = record.get("verdict") if record else ""
    if verdict == modules.AVAILABLE:
        return STATUS_NOT_PROBED, None
    if verdict:
        return VERDICT_STATUS.get(verdict, STATUS_UNKNOWN), None
    return STATUS_SUPPORTED if registry["modules"][modules.TIMETABLE] else STATUS_MISSING, None


def module_rows(registry):
    rows = []
    for name, slug, page in KNOWN_ROWS:
        if name == modules.TIMETABLE:
            status, probe = _timetable_pair(registry, slug)
        else:
            probe = registry["probes"].get(name)
            status = STATUS_SUPPORTED if registry["modules"][name] else STATUS_MISSING
            if probe and probe.get("verdict") == modules.UNKNOWN and probe.get("status") == 0:
                status = STATUS_ERROR
        if not registry["checked_at"]:
            status = STATUS_ASSUMED
        catalogue_slug = CATALOGUE_SLUGS.get(slug, slug)
        rows.append({
            "name": official_name(catalogue_slug) or slug,
            "slug": slug,
            "edition": edition_of(catalogue_slug),
            "status": status,
            "probe": probe,
            "page": page,
            "json": JSON_PROBES.get(slug),
            "data": DATA_PATHS.get(slug),
        })
    for entry in registry["unsupported"]:
        if entry.get("segment") == modules.LEGACY_TIMETABLE_SEGMENT:
            continue
        slug = entry.get("slug") or entry.get("segment")
        rows.append({
            "name": entry.get("name") or official_name(slug) or visible_text(entry.get("label") or slug),
            "slug": slug,
            "segment": entry.get("segment"),
            "edition": edition_of(slug),
            "status": STATUS_UNSUPPORTED,
            "probe": None,
            "page": "/iserv/%s/" % entry.get("segment"),
            "json": None,
            "guessed_page": True,
        })
    for entry in registry["unknown"]:
        rows.append({
            "name": visible_text(entry.get("label") or entry.get("segment")),
            "slug": entry.get("segment"),
            "segment": entry.get("segment"),
            "edition": "",
            "status": STATUS_UNKNOWN,
            "probe": None,
            "page": "/iserv/%s/" % entry.get("segment"),
            "json": None,
            "guessed_page": True,
        })
    return rows


def _answer_line(path, response):
    facts = modules.probe_record(path, response, "")
    shown = valueshape.link_shape(facts["path"])
    final = valueshape.link_shape(facts["final_path"]) if facts["final_path"] else ""
    return "- Page: %s -> %s %s %sB" % (
        shown,
        facts["status"],
        facts["content_type"] or "-",
        facts["length"],
    ) + (" (final %s)" % final if final and final != shown else "")


def _data_params(child_id, today):
    return data_params(child_id, today) if child_id else None


def structure_targets(row, today, child_id=""):
    targets = [(row["page"], None)]
    if row["json"]:
        targets.extend(modules.probes_of(row["json"], today)[:1])
    if row.get("data") and row["slug"] != TIME_TABLE_SLUG:
        targets.append((row["data"], _data_params(child_id, today)))
    return targets


def _probe(client, path, params, cache, lines):
    try:
        response = client.fetch(path, params)
    except Exception as error:
        lines.append("- Page: %s -> error (%s)" % (valueshape.link_shape(path), type(error).__name__))
        return None
    if response is None:
        lines.append("- Page: %s -> no answer" % valueshape.link_shape(path))
        return None
    lines.append(_answer_line(path, response))
    if status_of(response) == 200:
        lines.extend(response_skeleton(response))
        if cache is not None and body_kind(response) == "html":
            lines.extend(script_section(client, response, cache))
    return response


def _time_table_child(options, children, listed):
    for child in listed_children(children):
        option = matching_option(options, str(child.get("child_id")), child.get("name"), listed)
        if option is not None:
            return option.child_id
    return None


def time_table_data_lines(client, page, today, children, listed=None):
    if page is None:
        return ["- Data: not read, the page did not answer"]
    lost = time_table_session_lost(page)
    if lost:
        return ["- Data: not read, the session has expired (%s)" % lost]
    absent = time_table_absence(page)
    if absent:
        return ["- Data: not read, the module is absent for this account (%s)" % absent]
    if status_of(page) != 200:
        return ["- Data: not read, the page answered %d" % status_of(page)]
    html = getattr(page, "text", "") or ""
    if not time_table_recognised(html):
        return ["- Data: not read, the page is no time-table page"]
    listed = len(listed_children(children)) if listed is None else listed
    lines = []
    if child_select_present(html):
        options = parse_children(html)
        lines.append("- Child select: present, options %d, listed children %d" % (len(options), listed))
        chosen = _time_table_child(options, children, listed)
        if chosen is None:
            lines.append("- Data: not read, no listed child matches the child select")
            return lines
        lines.append("- Data query: week filter with childId")
    else:
        lines.append("- Child select: none")
        if listed != 1:
            lines.append("- Data: not read, no child select and %d listed children" % listed)
            return lines
        chosen = ""
        lines.append("- Data query: week filter without childId")
    response = _probe(client, TIME_TABLE_DATA, data_params(chosen, today), None, lines)
    lines.extend(_change_record_lines(response))
    return lines


def _change_record_lines(response):
    if response is None or status_of(response) != 200:
        return []
    try:
        payload = json_of(response)
    except (ValueError, TypeError):
        return []
    if not isinstance(payload, dict):
        return []
    raw = payload.get("plain-changes")
    if not isinstance(raw, list) or not raw:
        return []
    _changed, applied = with_time_table_changes(payload)
    lines = ["- Time-table changes: raw %d, applied %d" % (len(raw), len(applied)), "- Time-table change record shape:"]
    lines.extend(shape_block(raw))
    return lines


def page_structure(client, row, today, cache=None, child_id="", children=(), listed=None, nav_paths=None):
    cache = {} if cache is None else cache
    if row.get("guessed_page"):
        return module_link_structure(client, row, nav_paths, cache)
    lines = ["#### %s (%s)" % (row["slug"], row["name"])]
    answers = {}
    for path, params in structure_targets(row, today, child_id):
        answers[path] = _probe(client, path, params, cache, lines)
    if row["slug"] == TIME_TABLE_SLUG and row.get("data"):
        lines.extend(time_table_data_lines(client, answers.get(row["page"]), today, children, listed))
    landing = answers.get(row["page"])
    if landing is not None and status_of(landing) == 200 and body_kind(landing) == "html" and callable(getattr(client, "fetch_unfollowed", None)):
        lines.extend(module_crawl(client, landing, module_prefix(row["page"]), menu_shape, cache, SCRIPT_ROOT))
    return capped_module(lines)


def _listed_count(connection, children):
    reader = getattr(connection, "listed_child_count", None)
    if callable(reader):
        try:
            count = int(reader() or 0)
        except Exception:
            logger.debug("diagnostics could not count the listed children", exc_info=True)
            count = 0
        if count > 0:
            return count
    return len(listed_children(children))


def module_filter(value):
    return MODULE_NAME.sub("", str(value or "").strip().lower())[:40]


def _session_of(connection):
    opener = getattr(connection, "signed_in_session", None) or getattr(connection, "iserv_session", None)
    if not callable(opener):
        return None, "unavailable"
    try:
        client = opener()
    except Exception as error:
        logger.info("diagnostics could not open a session for school#%s: %s", getattr(connection, "id", ""), type(error).__name__)
        return None, "error (%s)" % type(error).__name__
    return (client, "ok") if client is not None else (None, "not signed in")


def _me_of(connection):
    reader = getattr(connection, "me_if_signed_in", None) or getattr(connection, "me", None)
    if not callable(reader):
        return None
    try:
        data = reader()
    except Exception:
        logger.debug("diagnostics could not read the account facts", exc_info=True)
        return None
    return data if isinstance(data, dict) else None


def _own_child_id(config):
    for child in config.get("children") or []:
        if isinstance(child, dict) and str(child.get("child_id") or "").strip():
            return str(child.get("child_id")).strip()
    return ""


def _stored_registry(connection):
    store = getattr(connection, "store", None)
    reader = getattr(store, "load_modules", None)
    if not callable(reader):
        return {}
    try:
        stored = reader()
    except Exception:
        return {}
    return stored if isinstance(stored, dict) else {}


def history_lines(connection):
    entries = modules.history_of(_stored_registry(connection))
    lines = ["### Registry history", "- Entries: %d" % len(entries)]
    for entry in entries:
        lines.append("- %s IServ %s: %s" % (_stamp(entry["at"]) if entry["at"] else "-", entry["iserv_version"] or "unknown", entry["summary"]))
    return lines


def _registry_without_network(connection):
    reader = getattr(connection, "stored_modules", None)
    if callable(reader):
        try:
            return modules.normalize(reader())
        except Exception:
            return modules.default_registry()
    return modules.registry_of(connection)


def _params_key(params):
    return json.dumps(params, sort_keys=True, default=str) if params else ""


class ReportFetcher:
    def __init__(self, client, budget=None):
        self.client = client
        self.answers = {}
        self.budget = budget if budget is not None else CrawlBudget()
        if callable(getattr(client, "fetch_capped", None)):
            self.fetch_capped = self._fetch_capped
        if callable(getattr(client, "fetch_unfollowed", None)):
            self.fetch_unfollowed = self._fetch_unfollowed
        if callable(getattr(client, "continue_chain", None)):
            self.continue_chain = self._continue_chain

    def _once(self, key, call):
        if key not in self.answers:
            try:
                self.budget.check()
                self.answers[key] = (call(), None)
            except Exception as error:
                self.answers[key] = (None, error)
        answer, error = self.answers[key]
        if error is not None:
            raise error
        return answer

    def fetch(self, path, params=None):
        return self._once(("page", path, _params_key(params)), lambda: self.client.fetch(path, params))

    def _fetch_capped(self, path, limit, timeout, expired=None):
        return self._once(("capped", path, limit), lambda: self.client.fetch_capped(path, limit, timeout, expired=expired))

    def _fetch_unfollowed(self, path, limit, timeout, expired=None):
        return self._once(("unfollowed", path, limit), lambda: self.client.fetch_unfollowed(path, limit, timeout, expired=expired))

    def _continue_chain(self, answer, max_hops, limit, timeout, expired=None):
        return self._once(("chain", str(answer.url), limit), lambda: self.client.continue_chain(answer, max_hops, limit, timeout, expired=expired))


def school_section(index, connection, structure, today, module="", budget=None):
    registry = _registry_without_network(connection)
    config = _config_of(connection)
    secrets = _secrets_of(connection)
    me = _me_of(connection)
    words = redaction_words_of(connection, me)
    stored_secret = bool(secrets.get("totp_secret"))
    server_2fa = (me or {}).get("has_2nd_factor_active") if me else None
    has_2fa = stored_secret or bool(server_2fa)
    guardian = (me or {}).get("is_guardian") if me else None
    lines = ["## School %d" % index]
    lines.append("- Children: %d" % len([child for child in config.get("children") or [] if isinstance(child, dict)]))
    lines.append("- Account: 2fa=%s guardian=%s" % (_yes_no(has_2fa), _yes_no(guardian)))
    lines.append("- Two-factor: has_2fa=%s, totp stored=%s, IServ says=%s" % (_yes_no(has_2fa), _yes_no(stored_secret), _yes_no(server_2fa)))
    lines.append("- IServ version: %s" % (registry["iserv_version"] or "unknown"))
    lines.append("- Modules checked: %s" % (_stamp(registry["checked_at"]) if registry["checked_at"] else "never"))
    client, session_state = _session_of(connection) if structure else (None, "not opened")
    lines.append("- Session: %s" % session_state)
    lines.append("- Timetable source: %s" % (config.get(SOURCE_KEY) or SCHOOL_APP_SOURCE))
    lines.append("### Modules")
    lines.append(TABLE_HEAD)
    lines.append(TABLE_RULE)
    rows = module_rows(registry)
    for row in rows:
        lines.append(_module_row(row["name"], row["slug"], row["edition"], row["status"], row["probe"]))
    lines.extend(history_lines(connection))
    fetcher = ReportFetcher(client, budget) if structure and callable(getattr(client, "fetch", None)) else None
    lines.extend(children_lines(fetcher, config))
    if structure:
        lines.extend(school_app_query_lines(fetcher, config, today))
        lines.extend(letters_summary_lines(fetcher))
        start = start_page_links(fetcher) if fetcher is not None else None
        nav_paths = menu_paths_by_segment(start[0]) if start is not None else {}
        lines.extend(menu_lines(start, linked_rows(rows, nav_paths)))
        lines.extend(iserv_version_lines(fetcher))
        lines.extend(unsupported_module_lines(fetcher, rows, nav_paths))
        lines.append("### Page structure")
        if fetcher is None:
            lines.append("- Not read: no session")
        else:
            base = list(rows) if not module else [row for row in rows if row["slug"] == module]
            if module and not base:
                lines.append("- Not read: no module named %s" % module)
            always = [row for row in rows if row["status"] == STATUS_UNKNOWN and row not in base]
            chosen = base + always[:MAX_UNKNOWN_STRUCTURE_ROWS]
            cache = {}
            child_id = _own_child_id(config)
            listed = _listed_count(connection, config.get("children")) if any(row["slug"] == TIME_TABLE_SLUG for row in chosen) else None
            for row in chosen:
                lines.extend(page_structure(fetcher, row, today, cache, child_id, config.get("children"), listed, nav_paths))
    return lines, words


def _versions(versions):
    given = versions or {}
    app = given.get("app") if "app" in given else integration.addon_version()
    home_assistant = given.get("home_assistant") if "home_assistant" in given else supervisor.core_version()
    return str(app or "unknown"), str(home_assistant or "unknown")


def _log_lines(log_lines):
    return list(log_lines) if log_lines is not None else logfile.lines()


def log_section(log, in_bundle=False):
    summary = logfile.summarize(log)
    tail = log[-REPORT_LOG_TAIL:]
    lines = ["## Log", logfile.covered_line(summary), "- Lines: %d" % len(log)]
    lines.append("- Add-on starts: %d, version changes: %d" % (len(summary["starts"]), len(summary["changes"])))
    if in_bundle or len(tail) < len(log):
        lines.append("- Full log: %s in %s" % (LOG_FILE, BUNDLE_NAME))
    lines.append("- Shown below: the last %d lines" % len(tail))
    lines.append("```")
    lines.extend(tail)
    lines.append("```")
    return lines


def _book(book):
    return book if book is not None else namebook.current()


def _learn_store(book, service):
    store = getattr(service, "store", None)
    if book is None or store is None:
        return
    try:
        book.learn_store(store)
    except Exception:
        logger.debug("the name book could not read the store", exc_info=True)


def report_parts(service, structure=True, log_lines=None, clock=time.time, versions=None, module="", in_bundle=False, book=None):
    book = _book(book)
    _learn_store(book, service)
    module = module_filter(module)
    now = clock()
    today = feed.berlin_moment(now).date()
    connections = list(service.connections())
    config = service.store.load_config() if hasattr(service, "store") else {}
    app_version, home_assistant = _versions(versions)
    iserv_versions = [_registry_without_network(connection)["iserv_version"] for connection in connections]
    iserv_version = next((version for version in iserv_versions if version), "") or "unknown"
    lines = [TITLE, "", "## Versions"]
    lines.append("- Generated: %s" % _stamp(now))
    lines.append("- Ranzenpost: %s" % app_version)
    lines.append("- Home Assistant: %s" % home_assistant)
    lines.append("- IServ: %s" % iserv_version)
    lines.append("- Language: %s" % (config.get("language") or "system"))
    lines.append("- Timezone: %s" % SCHOOL_TIMEZONE)
    lines.append("- Python: %s" % platform.python_version())
    lines.append("- Structure included: %s" % ("yes" if structure else "no"))
    if module:
        lines.append("- Structure module: %s" % module)
    lines.append("")
    lines.append("## Schools")
    lines.append("- Schools: %d" % len(connections))
    words = RedactionWords()
    budget = CrawlBudget()
    for index, connection in enumerate(connections, 1):
        lines.append("")
        section, school_words = school_section(index, connection, structure, today, module, budget)
        lines.extend(section)
        words.extend(school_words)
    log = _log_lines(log_lines)
    lines.append("")
    lines.extend(slow_request_lines(log))
    lines.append("")
    lines.extend(messenger_sync_lines(log))
    lines.append("")
    lines.extend(log_section(log, in_bundle))
    learn_words(book, words)
    text = Redactor(words)("\n".join(lines))
    if book is not None:
        text = book.mask(text)
    return text + "\n", words, log


def build_report(service, structure=True, log_lines=None, clock=time.time, versions=None, module="", book=None):
    report, _words, _log = report_parts(service, structure, log_lines, clock, versions, module, book=book)
    return report


def log_text(log, words, book=None):
    book = _book(book)
    head = logfile.header(logfile.summarize(log))
    body = Redactor(words)("\n".join(log))
    if book is not None:
        body = book.mask(body)
    return "\n".join(head) + "\n\n" + body + ("\n" if body else "")


def bundle_bytes(report, log, words, clock=time.time, book=None):
    moment = feed.berlin_moment(clock())
    stamp = (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in ((REPORT_FILE, report), (LOG_FILE, log_text(log, words, book))):
            info = zipfile.ZipInfo(name, stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, text.encode("utf-8"))
    return buffer.getvalue()


def build_bundle(service, structure=True, log_lines=None, clock=time.time, versions=None, module="", book=None):
    report, words, log = report_parts(service, structure, log_lines, clock, versions, module, in_bundle=True, book=book)
    return bundle_bytes(report, log, words, clock, book)


def report_segments(service):
    segments = []
    for connection in service.connections():
        registry = _registry_without_network(connection)
        for entry in registry["unsupported"] + registry["unknown"]:
            if entry["segment"] not in segments:
                segments.append(entry["segment"])
    return segments


def report_facts(service, versions=None):
    app_version, home_assistant = _versions(versions)
    iserv_versions = [_registry_without_network(connection)["iserv_version"] for connection in service.connections()]
    iserv_version = next((version for version in iserv_versions if version), "") or "unknown"
    return {"app": app_version, "home_assistant": home_assistant, "iserv": iserv_version}


class ReportCache:
    def __init__(self, clock=time.time, max_age=REPORT_CACHE_SECONDS):
        self.clock = clock
        self.max_age = max_age
        self.entry = None
        self.lock = threading.Lock()

    def build(self, service, structure=True, module=""):
        report, words, _log = report_parts(service, structure=structure, clock=self.clock, module=module, in_bundle=True)
        with self.lock:
            self.entry = (self.clock(), bool(structure), module_filter(module), report, words)
        return report

    def _fresh(self, structure, module):
        entry = self.entry
        if entry is None or entry[1:3] != (bool(structure), module_filter(module)):
            return None
        return entry if self.clock() - entry[0] <= self.max_age else None

    def bundle(self, service, structure=True, module=""):
        entry = self._fresh(structure, module)
        if entry is None:
            self.build(service, structure, module)
            entry = self.entry
        return bundle_bytes(entry[3], _log_lines(None), entry[4], self.clock)
