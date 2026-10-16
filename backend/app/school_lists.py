import logging
from urllib.parse import urlsplit

from . import modules
from .failure import error_kind
from .iserv.client import server_failure
from .iserv.errors import DataError, ModulePageRefusedError, OutageError
from .iserv.forms import find_login_form, parse_forms
from .iserv.exercises import (
    EXERCISE_PATH,
    PAGE_LIMIT,
    PAST_EXERCISE_PATH,
    ExerciseShapeError,
    is_exercise_page,
    note_once,
    parse_exercises,
    unique_id,
)
from .iserv.news import ITEM_PATH, NEWS_PATH, SECTIONS as NEWS_SECTIONS, is_news_page, parse_news, section_links
from .iserv.news_detail import parse_news_detail
from .iserv.pages import path_of
from .pathpattern import path_pattern
from .requestlog import url_host
from .store import connection_known, edit

logger = logging.getLogger(__name__)

REFUSED_STATUSES = (401, 403, 404)
LOGIN_MARKERS = modules.LOGIN_MARKERS
TASKS_FIELD = "tasks"
NEWS_FIELD = "news"
FAR_DAY = "9999-12-31"
CARRY_FIELD = "carry"
FILE_KINDS = ("files", "images")
FILE_ROOT = "/iserv/"
SECTIONS_FIELD = "sections"
FILE_LIMIT = 100 * 1024 * 1024
SIGN_IN_SNIFF = 256 * 1024
PART_CURRENT = "current"
PART_PAST = "past"


def module_answer(client, path, within, params=None):
    response = client.fetch(path, params) if params else client.fetch(path)
    status = int(getattr(response, "status_code", 0) or 0)
    if status in REFUSED_STATUSES:
        raise ModulePageRefusedError("%s refused: %d" % (path_pattern(path), status))
    failure = server_failure(response)
    if failure is not None:
        raise failure
    if status != 200:
        raise DataError("%s answered %d" % (path_pattern(path), status), detail={"path": path_pattern(path)})
    final = path_of(getattr(response, "url", "") or "")
    if any(final.startswith(marker) for marker in LOGIN_MARKERS):
        raise DataError("%s led to the sign-in" % path_pattern(path), detail={"path": path_pattern(path)})
    if not within(final):
        raise DataError("%s led to another page" % path_pattern(path), detail={"path": path_pattern(path)})
    return response


def _ids(parsed, field):
    return {str(item.get("id")) for item in parsed[field]}


def _pages(client, path, parse, within, field, kind):
    first = parse(module_answer(client, path, within).text)
    return _following(client, path, first, parse, within, field, kind)


def _following(client, path, first, parse, within, field, kind):
    parsed = [first]
    queue = list(first["pages"])
    seen = {path}
    known = _ids(first, field)
    partial = False
    while queue:
        target = queue.pop(0)
        if target in seen:
            continue
        if len(seen) >= PAGE_LIMIT:
            note_once(kind, path, "page limit %d reached" % PAGE_LIMIT)
            break
        seen.add(target)
        try:
            following = parse(module_answer(client, target, within).text)
        except (DataError, OutageError, ExerciseShapeError) as error:
            logger.info("%s list page %s unreadable, the earlier list is kept: %s", kind, path_pattern(target), error_kind(error))
            partial = True
            break
        fresh = _ids(following, field) - known
        if not fresh:
            break
        known |= fresh
        parsed.append(following)
        queue.extend(following["pages"])
    return parsed, partial


def _exercise_list(client, path, past):
    try:
        return _pages(client, path, lambda html: parse_exercises(html, path, past), is_exercise_page, TASKS_FIELD, "exercise")
    except ExerciseShapeError as error:
        raise DataError(str(error), detail={"path": path_pattern(path)}) from error


def task_order(task):
    return (bool(task.get("past")), task.get("done") is True, task.get("due") or FAR_DAY, task.get("title") or "")


def read_tasks(client):
    current, partial = _exercise_list(client, EXERCISE_PATH, False)
    carry = [PART_CURRENT] if partial else []
    try:
        past, past_partial = _exercise_list(client, PAST_EXERCISE_PATH, True)
    except (DataError, OutageError) as error:
        note_once("exercise", PAST_EXERCISE_PATH, "unreadable, earlier past tasks kept: %s" % error_kind(error))
        past, past_partial = [], True
    if past_partial:
        carry.append(PART_PAST)
    tasks = []
    seen = set()
    for parsed in current + past:
        for task in parsed["tasks"]:
            task_id = unique_id(task, seen)
            if task_id is None:
                continue
            seen.add(task_id)
            tasks.append(dict(task, id=task_id))
    tasks.sort(key=task_order)
    return {TASKS_FIELD: tasks, CARRY_FIELD: carry}


def _unique_items(pages, section=None):
    items = []
    seen = set()
    for parsed in pages:
        for item in parsed["items"]:
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            items.append(dict(item, section=section) if section else dict(item))
    return items


def same_entry(left, right):
    return all(left.get(name) == right.get(name) for name in ("title", "date", "path", "summary"))


def read_news_section(client, path, section):
    if section not in NEWS_SECTIONS or not is_news_page(path) or path.rstrip("/") == NEWS_PATH:
        raise DataError("not a news section", detail={"path": path_pattern(path)})
    pages, _partial = _pages(client, path, lambda html: parse_news(html, path), is_news_page, "items", "news")
    return _unique_items(pages, section)


def read_news(client):
    response = module_answer(client, NEWS_PATH, is_news_page)
    first = parse_news(response.text, NEWS_PATH)
    if not first["items"]:
        if not first["framed"]:
            note_once("news", NEWS_PATH, "no item links and no news list")
            raise DataError("news page shows no news list", detail={"path": NEWS_PATH})
        note_once("news", NEWS_PATH, "no item links")
    pages, partial = _following(client, NEWS_PATH, first, lambda html: parse_news(html, NEWS_PATH), is_news_page, "items", "news")
    sections = {section: path for section, path in section_links(response.text).items() if path.rstrip("/") != NEWS_PATH}
    return {NEWS_FIELD: _unique_items(pages), CARRY_FIELD: [PART_CURRENT] if partial else [], SECTIONS_FIELD: sections}


def public_link(entry, school_url):
    parts = urlsplit(entry["href"])
    link = {"label": entry["label"]}
    if entry.get("meta"):
        link["meta"] = entry["meta"]
    if parts.netloc and url_host(entry["href"]) != url_host(school_url):
        return dict(link, url=entry["href"])
    if not parts.path.startswith("/"):
        return None
    return dict(link, path=parts.path + ("?" + parts.query if parts.query else ""))


def public_links(entries, school_url):
    return [link for link in (public_link(entry, school_url) for entry in entries) if link]


def listed_file_path(listed, index):
    if not isinstance(listed, list) or isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(listed):
        return ""
    entry = listed[index]
    path = str(entry.get("path") or "") if isinstance(entry, dict) else ""
    return path if path.startswith(FILE_ROOT) and ".." not in path and "\\" not in path else ""


def news_file_path(entries, item_id, kind, index):
    if kind not in FILE_KINDS:
        return ""
    for item in entries or []:
        if not isinstance(item, dict) or str(item.get("id")) != str(item_id):
            continue
        detail = item.get("detail")
        return listed_file_path(detail.get(kind) if isinstance(detail, dict) else None, index)
    return ""


def read_school_file(client, path, school_url):
    response = client.fetch_file(path, FILE_LIMIT)
    failure = server_failure(response)
    if failure is not None:
        raise failure
    status = int(getattr(response, "status_code", 0) or 0)
    final = str(getattr(response, "url", "") or "")
    if status != 200 or any(path_of(final).startswith(marker) for marker in LOGIN_MARKERS):
        raise DataError("school file not served: %d" % status, detail={"path": path_pattern(path)})
    if url_host(final) != url_host(school_url):
        raise DataError("school file came from another host", detail={"path": path_pattern(path)})
    if getattr(response, "truncated", False):
        raise DataError("school file too large", detail={"path": path_pattern(path)})
    if sign_in_page(response):
        raise DataError("school file answered with the sign-in page", detail={"path": path_pattern(path)})
    return response


def sign_in_page(response):
    headers = getattr(response, "headers", None) or {}
    kind = str(headers.get("content-type") or headers.get("Content-Type") or "").lower()
    if "html" not in kind:
        return False
    text = bytes(getattr(response, "content", b"") or b"")[:SIGN_IN_SNIFF].decode("utf-8", "replace")
    return find_login_form(parse_forms(text, str(getattr(response, "url", "") or ""))) is not None


def read_news_detail(client, school_url, path, title=""):
    item_path = path_of(path).rstrip("/")
    if not ITEM_PATH.match(item_path):
        raise DataError("not a news item path", detail={"path": path_pattern(path)})
    response = module_answer(client, item_path, lambda final: final.rstrip("/") == item_path)
    parsed = parse_news_detail(getattr(response, "text", "") or "", item_path, title)
    detail = {"text": parsed["lines"]}
    for name in ("images", "files", "links"):
        detail[name] = public_links(parsed[name], school_url)
    return detail


def entry_part(item):
    if item.get("past"):
        return PART_PAST
    return str(item.get("section") or "") or PART_CURRENT


def carried(listed, field, stored):
    entries = [item for item in listed.get(field) or [] if isinstance(item, dict)]
    parts = listed.get(CARRY_FIELD) or []
    if not parts or not isinstance(stored, list):
        return entries
    present = {str(item.get("id")) for item in entries}
    kept = [
        item
        for item in stored
        if isinstance(item, dict) and entry_part(item) in parts and str(item.get("id")) not in present
    ]
    return entries + kept


def store_list(store, connection_id, field, entries, now, extra=None):
    entry = dict(extra or {}, **{field: entries, "last_success": int(now)})

    def change(snapshot):
        if not connection_known(store, connection_id):
            return
        holder = snapshot.get(field)
        if not isinstance(holder, dict):
            holder = {}
            snapshot[field] = holder
        holder[connection_id] = entry

    edit(store, store.load_calendar_snapshot, store.save_calendar_snapshot, change)
    return entry


def list_extra(listed):
    sections = listed.get(SECTIONS_FIELD)
    return {SECTIONS_FIELD: dict(sections)} if isinstance(sections, dict) else None


def stored_list(store, connection_id, field):
    holder = store.load_calendar_snapshot().get(field)
    entry = holder.get(connection_id) if isinstance(holder, dict) else None
    return entry if isinstance(entry, dict) and isinstance(entry.get(field), list) else None


def news_order(items):
    return sorted(items, key=lambda item: item.get("date") or "", reverse=True)
