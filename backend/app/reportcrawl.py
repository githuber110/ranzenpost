import re
import time
from collections import namedtuple
from urllib.parse import parse_qsl, urljoin, urlsplit

from bs4 import BeautifulSoup

from . import modules, valueshape
from .iserv.client import REDIRECT_NONE, REDIRECT_OTHER_HOST
from .module_catalogue import slug_of
from .pageshape import body_kind, code_text, response_skeleton, status_of
from .pathpattern import path_only, placeholders
from .scriptscan import SCRIPT_ROOT, endpoint_rows, inline_endpoints, script_endpoints, script_label, script_line, script_sources
from .valueshape import table_cell
from .vocabulary import known_word

MAX_PAGES_PER_MODULE = 5
MAX_PAGES_PER_REPORT = 40
MAX_APIS_PER_MODULE = 5
MAX_MODULE_LINES = 400
REPORT_SECONDS = 60
REQUEST_SECONDS = 5
MIN_REQUEST_SECONDS = 0.5
STOP_PAGES = "pages"
STOP_TIME = "time"
ID_MARKS = ("<n>", "<uuid>", "<hex>", "<date>")
WORD = re.compile(r"[^\W\d_]+")
READ_ROUTES = frozenset(
    """
    index list lists overview archive archived parent parents attendee attendees page pages tab tabs home start
    current today week month day history all
    """.split()
)
PROVIDER_ROUTES = READ_ROUTES | frozenset(
    "dashboard overview projects project transactions transaction details detail statements statement invoices invoice".split()
)
API_ROUTES = frozenset("api items entries events data count counts meta list lists index".split())
PAGE_WORDS = frozenset({"page", "pages"})
QUERY_KEYS = frozenset({"page", "sort", "order", "dir", "direction", "tab", "limit", "year", "month", "week", "day"})
BLOCKED_ATTRIBUTES = ("data-method", "data-confirm", "onclick", "data-action", "formaction")
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
MAX_CHAIN_HOPS = 5
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


def _is_id(part):
    return part.isdigit() or placeholders(part) in ID_MARKS


def path_allowed(path, prefix, routes=READ_ROUTES, ids=True):
    if not path.startswith(prefix):
        return False
    previous = ""
    for part in path[len(prefix):].split("/"):
        if not part:
            continue
        lowered = part.casefold()
        if part.isdigit() and previous in PAGE_WORDS:
            previous = lowered
            continue
        if _is_id(part):
            if not ids:
                return False
        elif lowered not in routes:
            return False
        previous = lowered
    return True


def query_allowed(query, routes=READ_ROUTES):
    for key, value in parse_qsl(query, keep_blank_values=True):
        if key.casefold() not in QUERY_KEYS:
            return False
        if value and not value.isdigit() and value.casefold() not in routes and value.casefold() not in ("asc", "desc"):
            return False
    return True


def text_allowed(text):
    return all(known_word(word) for word in WORD.findall(str(text or "")))


def api_allowed(path, prefix):
    return path_allowed(path, prefix, READ_ROUTES | API_ROUTES, ids=False)


def has_id(path):
    previous = ""
    for part in path.split("/"):
        if part and _is_id(part) and not (part.isdigit() and previous in PAGE_WORDS):
            return True
        previous = part.casefold()
    return False


def _query_keys(query):
    return tuple(sorted({key for key, _value in parse_qsl(query, keep_blank_values=True)}))


def crawl_links(html, page_url, prefix, limit, routes=READ_ROUTES):
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
        if not target.path.startswith(prefix):
            skip(SKIP_OTHER)
            continue
        if any(anchor.has_attr(name) for name in BLOCKED_ATTRIBUTES):
            skip(SKIP_ATTRIBUTE)
            continue
        if has_id(target.path):
            skip(SKIP_DETAIL)
            continue
        if not path_allowed(target.path, prefix, routes, ids=False):
            skip(SKIP_PATH)
            continue
        if not query_allowed(target.query, routes):
            skip(SKIP_QUERY)
            continue
        if not text_allowed(text):
            skip(SKIP_TEXT)
            continue
        key = (placeholders(target.path), _query_keys(target.query))
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


def _read_script(client, path, cache):
    if path in cache:
        return cache[path]
    reader = getattr(client, "fetch_capped", None)
    budget = budget_of(client)
    if not callable(reader):
        outcome = ("not read", None)
    elif budget.expired():
        outcome = ("not read, time budget reached", None)
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


def script_facts(client, response, cache, root=SCRIPT_ROOT, link_shape=None):
    sources = script_sources(getattr(response, "text", "") or "", str(getattr(response, "url", "") or ""), root)
    if not sources:
        return [], {}
    lines = ["##### Script endpoints"]
    facts = []
    found = {}
    for path in sources[:MAX_SCRIPTS_PER_MODULE]:
        state, body = _read_script(client, path, cache)
        facts.append("%s (%s)" % (script_line(path, link_shape), _script_fact(state, body)))
        if body is not None and int(getattr(body, "status_code", 0) or 0) == 200:
            for key, keys in script_endpoints(body.text, script_label(path)).items():
                found.setdefault(key, set()).update(keys)
    lines.append("- Scripts: " + " | ".join(facts))
    if len(sources) > MAX_SCRIPTS_PER_MODULE:
        lines.append("- Scripts skipped: %d beyond the limit of %d" % (len(sources) - MAX_SCRIPTS_PER_MODULE, MAX_SCRIPTS_PER_MODULE))
    if not found:
        lines.append("- Endpoints: none")
        return lines, found
    lines.extend(endpoint_rows(found, link_shape))
    return lines, found


def module_link_structure(client, row, nav_paths, cache):
    lines = ["#### %s (%s)" % (row["slug"], row["name"])]
    real = (nav_paths or {}).get(row.get("segment") or row["slug"])
    path = real or row["page"]
    label = menu_shape(path) + ("" if real else " (guessed, not in the menu)")
    answer, problem = read_unfollowed(client, path)
    if answer is None:
        lines.append("- Page: %s -> %s" % (label, problem))
        return lines
    lines.append(page_answer_line(label, answer))
    if status_of(answer) == 200:
        lines.extend(response_skeleton(answer))
        if body_kind(answer) == "html":
            lines.extend(script_section(client, answer, cache))
            lines.extend(module_crawl(client, answer, module_prefix(path), menu_shape, cache, SCRIPT_ROOT))
    elif redirect_of(answer) == REDIRECT_OTHER_HOST and callable(getattr(client, "continue_chain", None)):
        lines.extend(external_chain_lines(client, answer))
    return capped_module(lines)


def module_prefix(path):
    segment = _menu_segment(path)
    return MENU_LINK_PREFIX + segment + "/" if segment else MENU_LINK_PREFIX


def capped_module(lines):
    limit = MAX_MODULE_LINES
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


def _api_targets(endpoints, prefix):
    targets = []
    for method, pattern, _label in sorted(endpoints):
        if method != "GET" or "<" in pattern or "?" in pattern or not api_allowed(pattern, prefix):
            continue
        if pattern not in targets:
            targets.append(pattern)
    return targets[:MAX_APIS_PER_MODULE]


def module_crawl(client, landing, prefix, link_shape, cache, root, routes=READ_ROUTES, apis=True):
    budget = budget_of(client)
    links, skipped = crawl_links(
        getattr(landing, "text", "") or "", str(getattr(landing, "url", "") or ""), prefix, MAX_PAGES_PER_MODULE, routes,
    )
    lines = ["- Crawl: %d linked pages, skipped %s" % (len(links), skipped_text(skipped))]
    entries, endpoints = _write_entries(landing, script_facts(client, landing, cache, root, link_shape)[1], link_shape)
    for link in links:
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
            script_lines, scripts_found = script_facts(client, answer, cache, root, link_shape)
            lines.extend(script_lines)
            found, seen = _write_entries(answer, scripts_found, link_shape)
            entries.extend(entry for entry in found if entry not in entries)
            endpoints |= seen
    for pattern in _api_targets(endpoints, prefix) if apis else ():
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


def external_chain_lines(client, answer):
    try:
        budget = budget_of(client)
        chain = client.continue_chain(answer, MAX_CHAIN_HOPS, MAX_PROBE_BYTES, budget.timeout(PROBE_TIMEOUT), expired=budget.expired)
    except Exception as error:
        return ["- Redirect chain: error (%s)" % type(error).__name__]
    lines = ["- Redirect chain: " + " -> ".join("%d %s" % (hop.status, hop.where) for hop in chain.hops)]
    landing = chain.landing
    if landing is None:
        lines.append("- Landing page: not read, %s" % chain.stop)
        return lines
    lines.append("- Landing page: " + _answer_facts(landing))
    if status_of(landing) == 200:
        lines.extend(response_skeleton(landing, valueshape.link_shape))
        if body_kind(landing) == "html" and chain.reader is not None:
            chain.reader.budget = budget_of(client)
            cache = {}
            lines.extend(script_section(chain.reader, landing, cache, "/", valueshape.link_shape))
            lines.extend(module_crawl(chain.reader, landing, "/", valueshape.link_shape, cache, "/", PROVIDER_ROUTES, apis=False))
    return lines


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


def read_unfollowed(client, path):
    reader = getattr(client, "fetch_unfollowed", None)
    if not callable(reader):
        return None, "not read, no redirect-free request"
    try:
        budget = budget_of(client)
        answer = reader(path, MAX_PROBE_BYTES, budget.timeout(PROBE_TIMEOUT), expired=budget.expired)
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
    lines = ["### Unsupported or unknown modules", UNSUPPORTED_TABLE_HEAD, UNSUPPORTED_TABLE_RULE]
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
