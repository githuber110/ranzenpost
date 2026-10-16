import re
import time
from collections import namedtuple
from types import SimpleNamespace
from datetime import timedelta
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from . import modules, valueshape
from .iserv.badges import BADGES_PATH
from .iserv.client import REDIRECT_NONE, REDIRECT_OTHER_HOST, REDIRECT_SAME_HOST
from .iserv.forms import find_login_form, parse_forms
from .iserv.pages import FORM_PAGE_WORDS, WRITE_WORDS as SHARED_WRITE_WORDS
from .iserv.pages import path_of, status_of
from .iserv.dsa import CHILDREN_FIELDS
from .iserv.school_calendar import (
    CALENDAR_EVENTS_PATH,
    CALENDAR_SOURCES_PATH,
    URL_REFUSED,
    CalendarShapeError,
    events_params,
    feed_request,
    feed_sources,
    poll_window,
    source_events,
    source_kind,
)
from .module_catalogue import slug_of
from .pageshape import body_kind, code_text, json_of, response_skeleton
from .pathpattern import path_only, placeholders
from .reportexplore import (
    APP_API_WORDS,
    alias_prefixes,
    app_bases,
    app_root_line,
    as_prefixes,
    embedded_sources,
    first_foreign_frame,
    frame_line,
    free_part,
    free_shape,
    join_lines,
    never_hit,
    notice_blocks,
    prefix_rest,
    resolved_paths,
    row_text_lines,
    rule_for,
)
from .reportlists import crawl_page_lines
from .scriptscan import SCRIPT_ROOT, endpoint_rows, inline_endpoints, script_endpoints, script_label, script_line, script_sources
from .valueshape import table_cell
from .vocabulary import known_word

MAX_PAGES_PER_MODULE = 5
MAX_PAGES_PER_REPORT = 64
MAX_APIS_PER_MODULE = 5
MAX_MODULE_LINES = 400
REPORT_SECONDS = 60
REQUEST_SECONDS = 5
MIN_REQUEST_SECONDS = 0.5
STOP_PAGES = "pages"
STOP_TIME = "time"
ID_MARKS = ("<n>", "<uuid>", "<hex>", "<date>")
WORD = re.compile(r"[^\W\d_]+")
SHARED_READ_ROUTES = frozenset(
    """
    index list lists overview archive archived parent parents attendee attendees page pages tab tabs home start
    current today week month day history all
    """.split()
)
READ_ROUTES = SHARED_READ_ROUTES | frozenset("request requests".split())
PROVIDER_ROUTES = SHARED_READ_ROUTES | frozenset(
    "dashboard overview projects project transactions transaction details detail statements statement invoices invoice".split()
)
API_ROUTES = frozenset("api items entries events data count counts meta list lists index".split())
PROVIDER_API_ROUTES = API_ROUTES | PROVIDER_ROUTES | frozenset(
    """
    student students child children balance balances payment payments account accounts extra extras
    me user users profile school schools class classes parent parents bank settings
    """.split()
)
VERSION_PART = re.compile(r"^v\d{1,2}$")
FORM_ROUTES = frozenset("add edit new create".split())
API_VERBS = frozenset("start archive archived participate participation redeem request requests".split())
CHAIN_STOP_WORDS = frozenset("join logout logoff signout leave".split())
JSON_HEADERS = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}
MAX_RESOLVED_LINES = 10
MAX_SOURCE_PROBES = 3
FILE_ROUTES = frozenset("file files attachment attachments download downloads export media".split())
STATIC_ROOTS = ("/iserv/img/", "/iserv/static/", "/iserv/assets/", "/iserv/js/")
PAGE_WORDS = frozenset({"page", "pages"})
QUERY_KEYS = frozenset({"page", "sort", "order", "dir", "direction", "tab", "limit", "year", "month", "week", "day"})
BLOCKED_ATTRIBUTES = ("data-method", "data-confirm", "onclick", "data-action", "formaction")
WRITE_WORDS = (SHARED_WRITE_WORDS - FORM_PAGE_WORDS) | frozenset("book booking bookings reservation appointment appointments".split())
SKIP_PATH = "path not allowed"
SKIP_QUERY = "query not allowed"
SKIP_ATTRIBUTE = "script attribute"
SKIP_TEXT = "text not allowed"
SKIP_DETAIL = "detail page"
SKIP_OTHER = "other module"
SKIP_SAME = "same shape"
SKIP_LIMIT = "limit"
SKIP_ORDER = (SKIP_PATH, SKIP_QUERY, SKIP_ATTRIBUTE, SKIP_TEXT, SKIP_DETAIL, SKIP_OTHER, SKIP_SAME, SKIP_LIMIT)
MAX_SCRIPTS_PER_MODULE = 8
MAX_SCRIPT_BYTES = 2 * 1024 * 1024
SCRIPT_TIMEOUT = REQUEST_SECONDS
MAX_PROBE_BYTES = 1024 * 1024
PROBE_TIMEOUT = REQUEST_SECONDS
MAX_CHAIN_HOPS = 10
CrawlScope = namedtuple("CrawlScope", "pages scripts apis routes api_routes external details any_text depth rule", defaults=(False, False, 1, None))
MODULE_SCOPE = CrawlScope(MAX_PAGES_PER_MODULE, MAX_SCRIPTS_PER_MODULE, MAX_APIS_PER_MODULE, READ_ROUTES, (READ_ROUTES | API_ROUTES) - API_VERBS, False)
PROVIDER_SCOPE = CrawlScope(8, 20, 15, PROVIDER_ROUTES, PROVIDER_API_ROUTES, True)
MODULE_ROUTES = {
    "exercise": frozenset({"past", "exercise"}),
    "absence": frozenset({"add", "new", "create"}),
    "parentconference": frozenset(
        """
        conference conferences teacher teachers slot slots timeslot timeslots show view detail details day days
        event events
        """.split()
    ),
}
DETAIL_MODULES = frozenset({"parentconference"})
DEEP_MODULES = frozenset({"parentconference"})
PROVIDER_PAGES = 30
PROVIDER_SECONDS = 45
MAX_PROVIDER_LINES = 1200
MENU_LINK_PREFIX = modules.ISERV_ROOT + "/"
MENU_TABLE_HEAD = "| Path | Probed |"
MENU_TABLE_RULE = "|---|---|"
MAX_MENU_LINKS = 60
MAX_MENU_DEPTH = 3
MENU_CONTAINER = re.compile(r"nav|sidebar|menu", re.IGNORECASE)
MENU_MORE = "<more>"
MENU_SOURCE_NAVIGATION = "navigation"
MENU_SOURCE_PAGE = "whole start page, no navigation found"
UNSUPPORTED_TABLE_HEAD = "| Module | Link | Status | Redirect |"
UNSUPPORTED_TABLE_RULE = "|---|---|---|---|"
CrawlLink = namedtuple("CrawlLink", "target path")
MAX_SAME_HOST_HOPS = 3
SIGN_IN_SEGMENTS = frozenset({"login", "logout", "logoff", "auth", "oauth", "sso", "saml", "signin", "signout"})
CALENDAR_PROBE_DAYS = 30
CALENDAR_SOURCES_HEAD = "##### Calendar sources (app window %s)"
MAX_CALENDAR_SOURCES = 12
QUERY_KEY = re.compile(r"^[a-z][a-z_]{0,19}$")
KNOWN_API_LABEL = "##### Known API GET %s"
ACCOUNT_API_HEAD = "### Account APIs"
UPCOMING_PATH = "/iserv/calendar/api/upcoming"
MAIL_FOLDERS_PATH = "/iserv/mail/api/folder/list"
MAIL_LIST_PATH = "/iserv/mail/api/message/list"
PLAN_RAW_PATH = "/iserv/plan/show/raw"
SCHOOL_ACCOUNT_PATH = modules.DSA_API + "/users/me"


def upcoming_params(_today):
    return {"limit": "5", "includeSubscriptions": "true"}


def school_account_params(_today):
    return {"fields": CHILDREN_FIELDS}


def calendar_window(today):
    return events_params(today, today + timedelta(days=CALENDAR_PROBE_DAYS))


def mail_list_params(_today):
    return {"path": "INBOX", "length": "5", "start": "0", "order[column]": "date", "order[dir]": "desc"}


KNOWN_APIS = {
    "calendar": ((CALENDAR_SOURCES_PATH, None), (UPCOMING_PATH, upcoming_params), (CALENDAR_EVENTS_PATH, calendar_window)),
    "mail": ((MAIL_FOLDERS_PATH, None), (MAIL_LIST_PATH, mail_list_params)),
    "plan": ((PLAN_RAW_PATH, None),),
}
ACCOUNT_APIS = ((BADGES_PATH, None), (SCHOOL_ACCOUNT_PATH, school_account_params))


def _is_id(part):
    return part.isdigit() or placeholders(part) in ID_MARKS


def write_path(path, allowed=frozenset()):
    for part in unquote(path).casefold().split("/"):
        words = {word for word in re.split(r"[^a-z]+", part) if word}
        if words & (WRITE_WORDS - allowed):
            return True
    return False


def _version_part(lowered, external, rule):
    if external and VERSION_PART.match(lowered):
        return True
    return rule is not None and bool(VERSION_PART.match(lowered) or valueshape.VERSION_SEGMENT.match(lowered))


def path_allowed(path, prefix, routes=READ_ROUTES, ids=True, external=False, rule=None):
    rest = prefix_rest(path, prefix)
    if rest is None:
        return False
    previous = ""
    found = 0
    for position, part in enumerate(part for part in rest.split("/") if part):
        lowered = part.casefold()
        if never_hit(rule, part):
            return False
        if part.isdigit() and previous in PAGE_WORDS:
            previous = lowered
            continue
        if free_part(rule, previous, position, part):
            found += 1
        elif _is_id(part):
            if not ids or (external and previous not in routes):
                return False
            found += 1
        elif lowered not in routes and not _version_part(lowered, external, rule):
            return False
        previous = lowered
    return rule is None or rule.max_ids is None or found <= rule.max_ids


def query_allowed(query, routes=READ_ROUTES):
    for key, value in parse_qsl(query, keep_blank_values=True):
        if key.casefold() not in QUERY_KEYS:
            return False
        if value and not value.isdigit() and value.casefold() not in routes and value.casefold() not in ("asc", "desc"):
            return False
    return True


def text_allowed(text):
    return all(known_word(word) for word in WORD.findall(str(text or "")))


def api_allowed(path, prefix, routes=READ_ROUTES | API_ROUTES, external=False, rule=None):
    if rule is not None and write_path(path):
        return False
    return path_allowed(path, prefix, routes, ids=False, external=external, rule=rule)


def _shape_key(path):
    return "/".join("<id>" if part and (part.isdigit() or _is_id(part)) else part for part in path.split("/"))


def has_id(path):
    previous = ""
    for part in path.split("/"):
        if part and _is_id(part) and not (part.isdigit() and previous in PAGE_WORDS):
            return True
        previous = part.casefold()
    return False


def _query_keys(query):
    return tuple(sorted({key for key, _value in parse_qsl(query, keep_blank_values=True)}))


def module_scope(prefix, scope=MODULE_SCOPE):
    if scope.external:
        return scope
    rule = rule_for(prefix)
    if rule is not None:
        return scope._replace(
            routes=scope.routes | rule.routes, api_routes=(scope.api_routes | APP_API_WORDS | (rule.routes - FORM_ROUTES)) - API_VERBS,
            scripts=rule.scripts or scope.scripts, details=rule.details, any_text=True, depth=rule.depth, rule=rule,
        )
    segment = _menu_segment(as_prefixes(prefix)[0])
    extra = MODULE_ROUTES.get(segment)
    if not extra:
        return scope
    return scope._replace(
        routes=scope.routes | extra, details=segment in DETAIL_MODULES, any_text=True, depth=2 if segment in DEEP_MODULES else 1
    )


def crawl_links(html, page_url, prefix, limit, routes=READ_ROUTES, external=False, details=False, any_text=False, rule=None):
    soup = BeautifulSoup(html or "", "html.parser")
    page = urlsplit(page_url or "")
    chosen = []
    seen = set()
    skipped = {}

    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1

    for anchor in soup.find_all("a", href=True):
        target = urlsplit(urljoin(page_url or "", str(anchor.get("href") or "").strip()))
        if target.scheme not in ("http", "https") or target.netloc.lower() != page.netloc.lower():
            continue
        if (target.path, target.query) == (page.path, page.query):
            continue
        text = " ".join(anchor.get_text(" ").split())
        if prefix_rest(target.path, prefix) is None:
            skip(SKIP_OTHER)
            continue
        if any(anchor.has_attr(name) for name in BLOCKED_ATTRIBUTES):
            skip(SKIP_ATTRIBUTE)
            continue
        detail = has_id(target.path)
        if detail and not external and not details:
            skip(SKIP_DETAIL)
            continue
        if write_path(target.path, rule.forms if rule is not None else frozenset()):
            skip(SKIP_PATH)
            continue
        if not path_allowed(target.path, prefix, routes, ids=detail, external=external, rule=rule):
            skip(SKIP_PATH)
            continue
        if not query_allowed(target.query, routes):
            skip(SKIP_QUERY)
            continue
        if not any_text and not text_allowed(text):
            skip(SKIP_TEXT)
            continue
        shaped = free_shape(target.path, prefix, rule) if rule is not None else None
        if shaped is not None and (rule.free_after or rule.first_free):
            key = (_shape_key(shaped), _query_keys(target.query))
        else:
            key = (_shape_key(target.path) if external or details else placeholders(target.path), _query_keys(target.query))
        if key in seen:
            skip(SKIP_SAME)
            continue
        if len(chosen) >= limit:
            skip(SKIP_LIMIT)
            continue
        seen.add(key)
        chosen.append(CrawlLink(target.path + ("?" + target.query if target.query else ""), target.path))
    return chosen, skipped


def skipped_text(skipped):
    parts = ["%s %d" % (reason, skipped[reason]) for reason in SKIP_ORDER if skipped.get(reason)]
    return ", ".join(parts) or "none"


def write_forms(html, shape, name_shape):
    found = []
    for form in BeautifulSoup(html or "", "html.parser").find_all("form"):
        method = str(form.get("method") or "get").strip().lower()
        if method == "get":
            continue
        label = form.get("id") or form.get("name") or ""
        buttons = [str(field.get("name")) for field in form.find_all(("button", "input")) if field.get("name") and _submits(field)]
        name = name_shape(str(label)) if label else "-"
        entry = "%s %s form '%s'" % (method.upper(), shape(form.get("action") or "") or "-", name)
        if buttons:
            entry += " buttons " + ", ".join(sorted({name_shape(button) for button in buttons}))
        if entry not in found:
            found.append(entry)
    return found


def _submits(field):
    kind = str(field.get("type") or ("submit" if field.name == "button" else "text")).lower()
    return kind in ("submit", "image")


def write_scripts(endpoints, shape):
    found = []
    for method, pattern, label in endpoints:
        if method in ("GET", "-"):
            continue
        entry = "%s %s script '%s'" % (method, shape(pattern), label)
        if entry not in found:
            found.append(entry)
    return found


def functions_line(entries):
    if not entries:
        return "- Functions: read-only, no form or script writes found"
    return "- Functions: write candidates: " + "; ".join(entries)


class TimeBudgetReached(Exception):
    pass


class CrawlBudget:
    def __init__(self, pages=MAX_PAGES_PER_REPORT, seconds=REPORT_SECONDS, clock=time.monotonic):
        self.pages = pages
        self.clock = clock
        self.deadline = clock() + seconds
        self.used = 0
        self.stop = ""

    def expired(self):
        return self.clock() >= self.deadline

    def take(self):
        if self.expired():
            self.stop = STOP_TIME
            return False
        if self.pages <= 0:
            self.stop = STOP_PAGES
            return False
        self.pages -= 1
        self.used += 1
        return True

    def timeout(self, limit=REQUEST_SECONDS):
        return max(MIN_REQUEST_SECONDS, min(limit, self.deadline - self.clock()))

    def check(self):
        if self.expired():
            raise TimeBudgetReached("the report time budget is used up")

    def stop_line(self, what):
        if self.stop == STOP_TIME:
            return "- %s stopped after %d pages, time budget reached" % (what, self.used)
        return "- %s stopped: the report page limit is reached" % what


def _read_script(client, path, cache, counted=False):
    if path in cache:
        return cache[path]
    reader = getattr(client, "fetch_capped", None)
    budget = budget_of(client)
    if not callable(reader):
        outcome = ("not read", None)
    elif budget.expired():
        outcome = ("not read, time budget reached", None)
    elif counted and not budget.take():
        outcome = ("not read, request budget reached", None)
    else:
        try:
            outcome = ("ok", reader(path, MAX_SCRIPT_BYTES, budget.timeout(SCRIPT_TIMEOUT), expired=budget.expired))
        except Exception as error:
            outcome = ("error %s" % type(error).__name__, None)
    cache[path] = outcome
    return outcome


def _script_fact(state, body):
    if body is None:
        return state
    status = int(getattr(body, "status_code", 0) or 0)
    if status != 200:
        return "HTTP %d" % status
    if body.truncated:
        return "truncated at %dB" % MAX_SCRIPT_BYTES
    return "%dB" % len(body.text.encode("utf-8"))


def script_section(client, response, cache, root=SCRIPT_ROOT, link_shape=None):
    return script_facts(client, response, cache, root, link_shape)[0]


def own_scripts_first(sources, page_url):
    segment = _menu_segment(path_of(page_url))
    if not segment:
        return list(sources)
    own = [path for path in sources if "/%s/" % segment in path_only(path) or path_only(path).rsplit("/", 1)[-1].startswith(segment)]
    return own + [path for path in sources if path not in own]


def script_facts(client, response, cache, root=SCRIPT_ROOT, link_shape=None, limit=MAX_SCRIPTS_PER_MODULE, counted=False):
    page_url = str(getattr(response, "url", "") or "")
    sources = own_scripts_first(script_sources(getattr(response, "text", "") or "", page_url, root), page_url)
    if not sources:
        return [], {}
    lines = ["##### Script endpoints"]
    facts = []
    found = {}
    for path in sources[:limit]:
        state, body = _read_script(client, path, cache, counted)
        facts.append("%s (%s)" % (script_line(path, link_shape), _script_fact(state, body)))
        if body is not None and int(getattr(body, "status_code", 0) or 0) == 200:
            for key, keys in script_endpoints(body.text, script_label(path)).items():
                found.setdefault(key, set()).update(keys)
    lines.append("- Scripts: " + " | ".join(facts))
    if len(sources) > limit:
        lines.append("- Scripts skipped: %d beyond the limit of %d" % (len(sources) - limit, limit))
    if not found:
        lines.append("- Endpoints: none")
        return lines, found
    lines.extend(endpoint_rows(found, link_shape))
    return lines, found


def module_link_structure(client, row, nav_paths, cache, today):
    lines = ["#### %s (%s)" % (row["slug"], row["name"])]
    real = (nav_paths or {}).get(row.get("segment") or row["slug"])
    path = real or row["page"]
    label = menu_shape(path) + ("" if real else " (guessed, not in the menu)")
    answer, problem = read_unfollowed(client, path)
    if answer is None:
        lines.append("- Page: %s -> %s" % (label, problem))
        lines.extend(known_api_lines(client, row["slug"], today))
        return capped_module(lines)
    lines.append(page_answer_line(label, answer))
    followed = redirect_of(answer) == REDIRECT_SAME_HOST
    if followed:
        answer, hop_lines = follow_same_host(client, answer)
        lines.extend(hop_lines)
        path = path_of(getattr(answer, "url", "")) if answer is not None else path
    if answer is not None and status_of(answer) == 200:
        lines.extend(response_skeleton(answer))
        if body_kind(answer) == "html":
            rule = rule_for(module_prefix(path))
            limit = rule.scripts if rule is not None and rule.scripts else MAX_SCRIPTS_PER_MODULE
            lines.extend(script_facts(client, answer, cache, SCRIPT_ROOT, None, limit)[0])
            lines.extend(module_crawl(client, answer, module_prefix(path), menu_shape, cache, SCRIPT_ROOT))
            if rule is not None and rule.frames:
                lines.extend(frame_chain_lines(client, answer))
    elif answer is not None and redirect_of(answer) == REDIRECT_OTHER_HOST and followed:
        lines.append("- Redirect: to another host after a same-host redirect, not followed")
    elif answer is not None and redirect_of(answer) == REDIRECT_OTHER_HOST and callable(getattr(client, "continue_chain", None)):
        lines.extend(external_chain_lines(client, answer))
        return capped_module(lines, MAX_PROVIDER_LINES)
    lines.extend(known_api_lines(client, row["slug"], today))
    return capped_module(lines)


def sign_in_path(path):
    lowered = unquote(path).casefold()
    if any(marker in lowered for marker in modules.LOGIN_MARKERS):
        return True
    return any(segment in SIGN_IN_SEGMENTS for segment in lowered.split("/"))


def sign_in_page(answer):
    if status_of(answer) != 200 or body_kind(answer) != "html":
        return False
    return find_login_form(parse_forms(getattr(answer, "text", "") or "", str(getattr(answer, "url", "") or ""))) is not None


def follow_same_host(client, answer):
    budget = budget_of(client)
    lines = []
    seen = set()
    current = answer
    while redirect_of(current) == REDIRECT_SAME_HOST:
        target = str(getattr(current, "next_url", "") or "")
        path = path_of(target)
        shape = menu_shape(path)
        if not path.startswith(MENU_LINK_PREFIX) or sign_in_path(path):
            lines.append("- Redirect: stopped before %s, not a module page" % shape)
            return None, lines
        if path in seen or len(seen) >= MAX_SAME_HOST_HOPS:
            lines.append("- Redirect: stopped before %s, too many hops" % shape)
            return None, lines
        if not budget.take():
            lines.append(budget.stop_line("Redirect"))
            return None, lines
        seen.add(path)
        current, problem = read_unfollowed(client, target)
        if current is None:
            lines.append("- Redirect: %s -> %s" % (shape, problem))
            return None, lines
        if sign_in_page(current):
            lines.append("- Redirect: %s landed on the IServ sign-in page" % shape)
            return None, lines
        lines.append("- Redirect: %s -> %s" % (shape, _answer_facts(current)))
    return current, lines


def known_api_lines(client, slug, today, skip=(), answers=None):
    answers = dict(answers or {})
    targets = [target for target in KNOWN_APIS.get(slug) or () if target[0] not in skip]
    lines = api_probe_lines(client, targets, today, answers, retry_json=slug == "mail")
    if slug == "calendar":
        lines.extend(calendar_source_lines(client, answers.get(CALENDAR_SOURCES_PATH), today))
    return lines


def _query_shape(key, value):
    shown = key if QUERY_KEY.match(key) else valueshape.safe_key(key)
    return "%s=%s" % (shown, valueshape.link_shape(value) if value else "")


def calendar_url_shape(url):
    text = str(url or "").strip()
    if not text:
        return "-"
    parts = urlsplit(text)
    shape = valueshape.link_shape(parts.path) if parts.path.startswith("/") else valueshape.SEGMENT_MARK
    if parts.scheme or parts.netloc:
        shape = "<host>" + shape
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    return shape + ("?" + "&".join(_query_shape(key, value) for key, value in pairs) if pairs else "")


def _source_answer(answer, source):
    facts = _answer_facts(answer)
    if status_of(answer) != 200:
        return facts
    try:
        return "%s, %d events" % (facts, len(source_events(json_of(answer), source)))
    except (ValueError, TypeError, CalendarShapeError):
        return facts + ", events unreadable"


def calendar_source_lines(client, answer, today):
    first, last = poll_window(today)
    lines = [CALENDAR_SOURCES_HEAD % ("%s to %s" % (first.isoformat(), last.isoformat()))]
    if answer is None or status_of(answer) != 200:
        lines.append("- Sources: not read")
        return lines
    try:
        sources = feed_sources(json_of(answer))
    except (ValueError, TypeError, CalendarShapeError):
        lines.append("- Sources: unreadable, the app falls back to the combined feed")
        return lines
    budget = budget_of(client)
    for index, source in enumerate(sources[:MAX_CALENDAR_SOURCES], 1):
        line = "- Source %d: type %s, url %s" % (index, source_kind(source["type"]), calendar_url_shape(source["url"]))
        request = feed_request(source["url"], first, last)
        if request is None:
            lines.append(line + ", not read: " + URL_REFUSED)
            continue
        if not budget.take():
            lines.append(budget.stop_line("Calendar source reads"))
            return lines
        path, params = request
        reply, problem = read_unfollowed(client, path + "?" + urlencode(params))
        lines.append(line + " -> " + (problem if reply is None else _source_answer(reply, source)))
    if len(sources) > MAX_CALENDAR_SOURCES:
        lines.append("- Sources not read: %d beyond the limit of %d" % (len(sources) - MAX_CALENDAR_SOURCES, MAX_CALENDAR_SOURCES))
    return lines


def account_api_lines(client, today):
    if client is None:
        return []
    return [ACCOUNT_API_HEAD] + api_probe_lines(client, ACCOUNT_APIS, today)


def api_probe_lines(client, targets, today, answers=None, retry_json=False):
    budget = budget_of(client)
    lines = []
    for path, params in targets:
        if not budget.take():
            lines.append(budget.stop_line("Known API reads"))
            break
        query = params(today) if callable(params) else None
        label = path + (" +query" if query else "")
        lines.append(KNOWN_API_LABEL % label)
        target = path + ("?" + urlencode(query) if query else "")
        answer, problem = read_unfollowed(client, target)
        if answer is None:
            lines.append("- Answer: %s" % problem)
            continue
        if answers is not None:
            answers[path] = answer
        lines.append(page_answer_line(label, answer))
        if status_of(answer) == 200:
            lines.extend(response_skeleton(answer, menu_shape))
        if retry_json and status_of(answer) == 200 and body_kind(answer) == "html":
            lines.extend(json_retry_lines(client, target, label))
    return lines


def json_retry_lines(client, target, label):
    budget = budget_of(client)
    shown = label + " with json headers"
    lines = [KNOWN_API_LABEL % shown]
    if not budget.take():
        return lines + [budget.stop_line("Known API reads")]
    answer, problem = read_unfollowed(client, target, JSON_HEADERS)
    if answer is None:
        return lines + ["- Answer: %s" % problem]
    lines.append(page_answer_line(shown, answer))
    if status_of(answer) == 200:
        lines.extend(response_skeleton(answer, menu_shape) if body_kind(answer) == "json" else ["- Body: %s again" % body_kind(answer)])
    return lines


def module_prefix(path):
    segment = _menu_segment(path)
    return MENU_LINK_PREFIX + segment + "/" if segment else MENU_LINK_PREFIX


def capped_module(lines, limit=MAX_MODULE_LINES):
    if len(lines) <= limit:
        return lines
    return lines[:limit] + ["- Module lines cut at %d" % limit]


def budget_of(client):
    budget = getattr(client, "budget", None)
    return budget if isinstance(budget, CrawlBudget) else CrawlBudget()


def _answer_facts(answer):
    facts = modules.probe_record("", answer, "")
    line = "%s %s %sB" % (facts["status"], facts["content_type"] or "-", facts["length"])
    if redirect_of(answer) != REDIRECT_NONE:
        line += ", redirect to %s" % redirect_of(answer)
    if getattr(answer, "truncated", False):
        line += ", cut at %dB" % MAX_PROBE_BYTES
    return line


def page_answer_line(label, answer):
    return "- Page: %s -> %s" % (label, _answer_facts(answer))


def _write_entries(answer, found, link_shape):
    html = getattr(answer, "text", "") or ""
    endpoints = set(found) | set(inline_endpoints(html))
    entries = write_forms(html, link_shape, lambda name: code_text(placeholders(name)))
    entries.extend(entry for entry in write_scripts(sorted(endpoints), link_shape) if entry not in entries)
    return entries, endpoints


def _api_targets(endpoints, prefix, scope=MODULE_SCOPE, bases=()):
    rule = scope.rule
    resolving = rule is not None and rule.apis
    targets = []
    resolved = []
    for method, pattern, _label in sorted(endpoints):
        if method not in (("GET", "-") if resolving else ("GET",)):
            continue
        candidates = resolved_paths(pattern, bases) if resolving else ([] if "<" in pattern or "?" in pattern else [pattern])
        for candidate in candidates:
            if method == "-" and candidate.rstrip("/").rsplit("/", 1)[-1].casefold() not in APP_API_WORDS:
                continue
            if not api_allowed(candidate, prefix, scope.api_routes, scope.external, rule):
                continue
            if candidate != pattern and (pattern, candidate) not in resolved:
                resolved.append((pattern, candidate))
            if candidate not in targets:
                targets.append(candidate)
    return targets[:scope.apis], resolved


def resolution_lines(bases, from_tag, resolved, link_shape):
    if not resolved:
        return []
    lines = ["- App base: %s (%s)" % (link_shape(bases[0]), "base tag" if from_tag else "module path")]
    for pattern, candidate in resolved[:MAX_RESOLVED_LINES]:
        lines.append("- Resolved endpoint: %s -> %s" % (valueshape.link_shape(pattern), link_shape(candidate)))
    if len(resolved) > MAX_RESOLVED_LINES:
        lines.append("- Resolved endpoints skipped: %d beyond the limit of %d" % (len(resolved) - MAX_RESOLVED_LINES, MAX_RESOLVED_LINES))
    return lines


def rule_page_lines(client, rule, answer, link_shape, prefix, landing=False):
    if rule is None:
        return []
    html = getattr(answer, "text", "") or ""
    url = str(getattr(answer, "url", "") or "")
    lines = []
    root = app_root_line(html) if landing else ""
    if root:
        lines.append(root)
    if rule.join:
        lines.extend(join_lines(html, url, link_shape))
    if rule.rows:
        lines.extend(row_text_lines(html))
    if rule.media:
        shown, own = embedded_sources(html, url, link_shape)
        lines.extend(shown)
        lines.extend(source_type_lines(client, own, link_shape, prefix, rule))
    return lines


def source_readable(path, prefix, rule):
    if path.startswith(STATIC_ROOTS) or prefix_rest(path, prefix) is None or write_path(path) or sign_in_path(path):
        return False
    parts = [unquote(part).casefold() for part in path.split("/") if part]
    if not parts or valueshape.FILE_SEGMENT.match(parts[-1]) or FILE_ROUTES & set(parts):
        return False
    return not any(never_hit(rule, part) for part in path.split("/") if part)


def source_type_lines(client, paths, link_shape, prefix, rule):
    budget = budget_of(client)
    lines = []
    for path in [path for path in paths if source_readable(path, prefix, rule)][:MAX_SOURCE_PROBES]:
        if not budget.take():
            lines.append(budget.stop_line("Source reads"))
            break
        answer, problem = read_unfollowed(client, path)
        lines.append("- Source %s -> %s" % (link_shape(path), problem if answer is None else _answer_facts(answer)))
    return lines


def module_crawl(client, landing, prefix, link_shape, cache, root, scope=MODULE_SCOPE):
    budget = budget_of(client)
    html = getattr(landing, "text", "") or ""
    url = str(getattr(landing, "url", "") or "")
    primary = as_prefixes(prefix)[0]
    prefix = prefix if scope.external else alias_prefixes(primary, html, url)
    scope = module_scope(prefix, scope)
    links, skipped = crawl_links(html, url, prefix, scope.pages, scope.routes, scope.external, scope.details, scope.any_text, scope.rule)
    lines = []
    if len(as_prefixes(prefix)) > 1:
        lines.append("- Crawl prefixes: " + ", ".join(link_shape(candidate) for candidate in as_prefixes(prefix)))
    lines.append("- Crawl: %d linked pages, skipped %s" % (len(links), skipped_text(skipped)))
    lines.extend(rule_page_lines(client, scope.rule, landing, link_shape, prefix, landing=True))
    entries, endpoints = _write_entries(landing, script_facts(client, landing, cache, root, link_shape, scope.scripts, scope.external)[1], link_shape)
    queue = [(link, 1) for link in links]
    shapes = {_shape_key(link.path) for link in links} | {_shape_key(path_of(getattr(landing, "url", "")))}
    crawled = 0
    while queue:
        link, level = queue.pop(0)
        crawled += 1
        if not budget.take():
            lines.append(budget.stop_line("Crawl"))
            break
        label = link_shape(link.path) + (" +query" if "?" in link.target else "")
        lines.append("##### Page %s" % label)
        answer, problem = read_unfollowed(client, link.target)
        if answer is None:
            lines.append("- Page: %s" % problem)
            continue
        lines.append(page_answer_line(label, answer))
        if status_of(answer) != 200:
            continue
        lines.extend(response_skeleton(answer, link_shape))
        if body_kind(answer) == "html":
            lines.extend(crawl_page_lines(primary, answer))
            lines.extend(rule_page_lines(client, scope.rule, answer, link_shape, prefix))
            script_lines, scripts_found = script_facts(client, answer, cache, root, link_shape, scope.scripts, scope.external)
            lines.extend(script_lines)
            found, seen = _write_entries(answer, scripts_found, link_shape)
            entries.extend(entry for entry in found if entry not in entries)
            endpoints |= seen
            if level < scope.depth:
                room = max(0, scope.pages * scope.depth - crawled - len(queue))
                deeper = _deeper_links(answer, prefix, scope, shapes)[:room]
                if deeper:
                    lines.append("- Crawl from this page: %d more linked pages" % len(deeper))
                queue.extend((item, level + 1) for item in deeper)
    bases, from_tag = app_bases(html, url, prefix) if scope.rule is not None else ([], False)
    targets, resolved = _api_targets(endpoints, prefix, scope, bases)
    lines.extend(resolution_lines(bases, from_tag, resolved, link_shape))
    for pattern in targets:
        if not budget.take():
            lines.append(budget.stop_line("API reads"))
            break
        lines.append("##### API GET %s" % link_shape(pattern))
        answer, problem = read_unfollowed(client, pattern)
        if answer is None:
            lines.append("- Answer: %s" % problem)
            continue
        lines.append(page_answer_line(link_shape(pattern), answer))
        if status_of(answer) == 200:
            lines.extend(response_skeleton(answer, link_shape))
    lines.append(functions_line(entries))
    return lines


def _deeper_links(answer, prefix, scope, shapes):
    found, _skipped = crawl_links(
        getattr(answer, "text", "") or "", str(getattr(answer, "url", "") or ""), prefix, scope.pages, scope.routes,
        scope.external, scope.details, scope.any_text, scope.rule,
    )
    chosen = []
    for link in found:
        shape = _shape_key(link.path)
        if shape in shapes:
            continue
        shapes.add(shape)
        chosen.append(link)
    return chosen


def _iserv_sign_in_page(hops, landing):
    if not hops or hops[-1].where != REDIRECT_SAME_HOST or body_kind(landing) != "html":
        return False
    return find_login_form(parse_forms(getattr(landing, "text", "") or "", str(getattr(landing, "url", "") or ""))) is not None


def provider_budget(outer):
    left = outer.deadline + PROVIDER_SECONDS - outer.clock()
    return CrawlBudget(pages=PROVIDER_PAGES, seconds=max(0, min(PROVIDER_SECONDS, left)), clock=outer.clock)


def chain_home_steps(answer):
    segment = _menu_segment(path_of(str(getattr(answer, "url", "") or "")))
    return (MENU_LINK_PREFIX + segment + "/auth",) if segment else ()


def chain_stop_words(answer):
    rule = rule_for(module_prefix(path_of(str(getattr(answer, "url", "") or ""))))
    return WRITE_WORDS | CHAIN_STOP_WORDS | (rule.never if rule is not None else frozenset())


def external_chain_lines(client, answer, label="Redirect chain", framing=False):
    try:
        budget = budget_of(client)
        chain = client.continue_chain(
            answer, MAX_CHAIN_HOPS, MAX_PROBE_BYTES, budget.timeout(PROBE_TIMEOUT), expired=budget.expired, home_steps=chain_home_steps(answer),
            stop_words=chain_stop_words(answer),
        )
    except Exception as error:
        return ["- %s: error (%s)" % (label, type(error).__name__)]
    lines = ["- %s: " % label + " -> ".join("%d %s" % (hop.status, hop.where) for hop in chain.hops)]
    landing = chain.landing
    if landing is None:
        lines.append("- Landing page: not read, %s" % chain.stop)
        return lines
    if _iserv_sign_in_page(chain.hops, landing):
        lines.append("- Landing page: %s, landed on the IServ sign-in page" % _answer_facts(landing))
        return lines
    lines.append("- Landing page: " + _answer_facts(landing))
    if framing:
        lines.append(frame_line(landing))
    if status_of(landing) == 200:
        lines.extend(response_skeleton(landing, valueshape.link_shape))
        if body_kind(landing) == "html" and chain.reader is not None:
            chain.reader.budget = provider_budget(budget)
            cache = {}
            lines.extend(script_facts(chain.reader, landing, cache, "/", valueshape.link_shape, PROVIDER_SCOPE.scripts, True)[0])
            lines.extend(module_crawl(chain.reader, landing, "/", valueshape.link_shape, cache, "/", PROVIDER_SCOPE))
    return lines


def frame_chain_lines(client, answer):
    target = first_foreign_frame(getattr(answer, "text", "") or "", str(getattr(answer, "url", "") or ""))
    if not target:
        return ["- Frame: none to another host"]
    lines = ["- Frame: iframe to another host, path %s" % valueshape.link_shape(target)]
    if not callable(getattr(client, "continue_chain", None)):
        return lines + ["- Frame page: not read, no chain request"]
    start = SimpleNamespace(status_code=200, url=str(getattr(answer, "url", "") or ""), redirect=REDIRECT_OTHER_HOST, next_url=target)
    return lines + external_chain_lines(client, start, "Frame chain", framing=True)


def _navigation_container(node):
    if node.name == "nav" or str(node.get("role") or "").lower() == "navigation":
        return True
    marks = [str(node.get("id") or "")] + [str(name) for name in node.get("class") or []]
    return any(MENU_CONTAINER.search(mark) for mark in marks)


def _own_path(href, page_url):
    href = str(href or "").strip()
    if not href:
        return ""
    page = urlsplit(page_url or "")
    target = urlsplit(urljoin(page_url or "", href))
    if page.netloc:
        if target.netloc.lower() != page.netloc.lower():
            return ""
    elif target.netloc or target.scheme:
        return ""
    return target.path if target.path.startswith(MENU_LINK_PREFIX) else ""


def _link_paths(anchors, page_url):
    paths = []
    for anchor in anchors:
        path = _own_path(anchor.get("href"), page_url)
        if path and path not in paths:
            paths.append(path)
    return paths


def navigation_links(html, page_url=""):
    soup = BeautifulSoup(html or "", "html.parser")
    anchors = []
    for node in soup.find_all(True):
        if _navigation_container(node):
            anchors.extend(anchor for anchor in node.find_all("a", href=True) if anchor not in anchors)
    paths = _link_paths(anchors, page_url)
    if paths:
        return paths, MENU_SOURCE_NAVIGATION
    return _link_paths(soup.find_all("a", href=True), page_url), MENU_SOURCE_PAGE


def _known_module_segment(segment):
    return bool(slug_of(segment)) or segment in modules.SEGMENTS or segment in modules.IGNORED_SEGMENTS


def _menu_head(segment):
    lowered = segment.lower()
    if _known_module_segment(lowered):
        return lowered
    return valueshape.link_shape(segment)


def menu_shape(path):
    path = path_only(path)
    if not path.startswith(MENU_LINK_PREFIX):
        return valueshape.SEGMENT_MARK
    segments = path[len(MENU_LINK_PREFIX):].split("/")
    shown = [modules.ISERV_ROOT, _menu_head(segments[0])]
    shown.extend(valueshape.link_shape(segment) for segment in segments[1:MAX_MENU_DEPTH + 1])
    if len(segments) > MAX_MENU_DEPTH + 1:
        shown.append(MENU_MORE)
    return "/".join(shown)


def _menu_segment(path):
    path = path_only(path)
    if not path.startswith(MENU_LINK_PREFIX):
        return ""
    return path[len(MENU_LINK_PREFIX):].split("/", 1)[0].strip().lower()


def _probed_paths_by_segment(rows):
    probed = {}
    for row in rows:
        segment = _menu_segment(row.get("page") or "")
        if segment:
            probed.setdefault(segment, row["page"])
    return probed


def _start_page(client):
    try:
        response = client.fetch(MENU_LINK_PREFIX)
    except Exception:
        return None, "request failed"
    if response is None:
        return None, "no answer"
    if status_of(response) != 200:
        return None, "page answered %d" % status_of(response)
    return response, ""


def start_notice_lines(client):
    lines = ["### Start page notices"]
    if client is None:
        return lines + ["- Not read: no session"]
    response, problem = _start_page(client)
    if response is None:
        return lines + ["- Not read: %s" % problem]
    return lines + notice_blocks(getattr(response, "text", "") or "", str(getattr(response, "url", "") or ""), menu_shape)


def start_page_links(client):
    response, problem = _start_page(client)
    if response is None:
        return [], "", problem
    paths, source = navigation_links(getattr(response, "text", "") or "", str(getattr(response, "url", "") or ""))
    return paths, source, ""


def menu_lines(start, rows):
    if start is None:
        return ["### Menu", "- Not read: no session"]
    links, source, problem = start
    if problem:
        return ["### Menu", "- Not read: %s" % problem]
    probed_by_segment = _probed_paths_by_segment(rows)
    lines = ["### Menu", "- Source: %s" % source, MENU_TABLE_HEAD, MENU_TABLE_RULE]
    shown = []
    for path in links:
        probed = probed_by_segment.get(_menu_segment(path))
        pattern = menu_shape(path)
        if probed is None:
            outcome = "not probed"
        elif path_only(probed).rstrip("/") == path.rstrip("/"):
            outcome = "match"
        else:
            outcome = "mismatch (probed %s)" % menu_shape(probed)
        line = "| %s | %s |" % (table_cell(pattern), table_cell(outcome))
        if line not in shown:
            shown.append(line)
    lines.extend(shown[:MAX_MENU_LINKS])
    if len(shown) > MAX_MENU_LINKS:
        lines.append("- Links skipped: %d beyond the limit of %d" % (len(shown) - MAX_MENU_LINKS, MAX_MENU_LINKS))
    return lines


def menu_paths_by_segment(links):
    mapping = {}
    for path in links:
        segment = _menu_segment(path)
        if segment and (segment not in mapping or len(path) < len(mapping[segment])):
            mapping[segment] = path
    return mapping


def read_unfollowed(client, path, headers=None):
    reader = getattr(client, "fetch_unfollowed", None)
    if not callable(reader):
        return None, "not read, no redirect-free request"
    try:
        budget = budget_of(client)
        extra = {"headers": headers} if headers else {}
        answer = reader(path, MAX_PROBE_BYTES, budget.timeout(PROBE_TIMEOUT), expired=budget.expired, **extra)
    except Exception as error:
        return None, "error (%s)" % type(error).__name__
    if answer is None:
        return None, "no answer"
    return answer, ""


def redirect_of(answer):
    return str(getattr(answer, "redirect", "") or REDIRECT_NONE)


def linked_rows(rows, nav_paths):
    linked = []
    for row in rows:
        real = nav_paths.get(row.get("segment") or row["slug"]) if row.get("guessed_page") else None
        linked.append(dict(row, page=real) if real else row)
    return linked


def unsupported_module_lines(client, rows, nav_paths):
    targets = [row for row in rows if row.get("guessed_page")]
    if not targets:
        return []
    lines = ["### Unsupported, covered or unknown modules", UNSUPPORTED_TABLE_HEAD, UNSUPPORTED_TABLE_RULE]
    if client is None:
        for row in targets:
            lines.append("| %s | not read | - | - |" % table_cell(row["slug"]))
        return lines
    for row in targets:
        real_path = nav_paths.get(row.get("segment") or row["slug"])
        if not real_path:
            lines.append("| %s | not in menu | - | - |" % table_cell(row["slug"]))
            continue
        answer, problem = read_unfollowed(client, real_path)
        if answer is None:
            lines.append("| %s | %s | %s | - |" % (table_cell(row["slug"]), table_cell(menu_shape(real_path)), table_cell(problem)))
            continue
        lines.append("| %s | %s | %s | %s |" % (
            table_cell(row["slug"]), table_cell(menu_shape(real_path)), table_cell(status_of(answer)), table_cell(redirect_of(answer)),
        ))
    return lines
