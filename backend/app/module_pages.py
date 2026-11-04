import hashlib
import logging
import re
import threading
from collections import OrderedDict

from .iserv.conferences import module_path, public_blocks
from .iserv.errors import DataError, ModulePageRefusedError
from .iserv.forms import find_login_form, parse_forms
from .iserv.module_pages import PAGE_MODULES, TASK_LIST, TODO_PATH, TODO_PREFIX, page_allowed, read_module_page, read_todo, within
from .iserv.pages import path_of
from .school_lists import LOGIN_MARKERS, checked_answer

logger = logging.getLogger(__name__)

UNKNOWN_KEY = "api.conferences.page.unknown"
UNREADABLE_KEY = "api.modulePages.unreadable"
REFUSED_KEY = "api.modulePages.refused"
TOKEN_LIMIT = 2000
MAX_PAGE_BYTES = 4 * 1024 * 1024
READ_SECONDS = 30
MAX_HOPS = 3
PAGE_LINK = re.compile(r"[?&]page=\d+")


def _filled(row):
    return [str(cell).strip() for cell in row["cells"] if str(cell or "").strip()]


def _placeholder(table, row):
    return len(table.get("headers") or []) > 1 and len(_filled(row)) == 1 and not row["links"]


def _row_title(row):
    filled = _filled(row)
    return next((cell for cell in filled if any(char.isalpha() for char in cell)), filled[0] if filled else "")


def _paged(model):
    links = []
    for block in model["blocks"]:
        links.extend(block.get("links") or [])
        for row in block.get("rows") or []:
            links.extend(row["links"])
    return any(PAGE_LINK.search(link["path"]) for link in links)


class ModulePages:
    def __init__(self, connection):
        self.connection = connection
        self._lock = threading.Lock()
        self._pages = OrderedDict()

    def forget(self):
        with self._lock:
            self._pages = OrderedDict()

    def _token(self, slug, path):
        seed = "%s|%s|%s" % (self.connection.id, slug, path)
        token = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
        with self._lock:
            self._pages.pop(token, None)
            self._pages[token] = (slug, path)
            while len(self._pages) > TOKEN_LIMIT:
                self._pages.popitem(last=False)
        return token

    def _path(self, slug, token):
        if not token:
            return PAGE_MODULES[slug]["path"]
        with self._lock:
            known = self._pages.get(str(token))
        if known is None or known[0] != slug or not page_allowed(slug, known[1]):
            logger.warning("module page refused: it was not seen in a page of this module")
            raise DataError("the module page is not known", message_key=UNKNOWN_KEY)
        return known[1]

    def _fetch(self, path, prefix, allowed):
        client = self.connection._session()
        current = path
        renewed = False
        try:
            for _hop in range(MAX_HOPS):
                response = client.fetch_unfollowed(current, MAX_PAGE_BYTES, READ_SECONDS)
                target = str(getattr(response, "next_url", "") or "")
                if not target:
                    return checked_answer(response, current, within(prefix))
                if not renewed and path_of(target).startswith(LOGIN_MARKERS):
                    renewed = True
                    self.connection._forget_session(client)
                    client = self.connection._session()
                    continue
                current = module_path(target, str(getattr(response, "url", "") or ""), prefix, True)
                if current is None or not allowed(current):
                    raise DataError("the module page led away from what the app reads", message_key=UNREADABLE_KEY)
        except ModulePageRefusedError as error:
            raise DataError(str(error), message_key=REFUSED_KEY) from error
        raise DataError("the module page redirected too often", message_key=UNREADABLE_KEY)

    def read(self, slug, token=""):
        if slug == TASK_LIST:
            return self._todo()
        return self._public(slug, self._model(slug, token))

    def _model(self, slug, token=""):
        prefix = PAGE_MODULES[slug]["prefix"]
        response = self._fetch(self._path(slug, token), prefix, lambda path: page_allowed(slug, path))
        url = str(getattr(response, "url", "") or "")
        text = getattr(response, "text", "") or ""
        if not self._is_readable_html(response, text, url):
            raise DataError("the module page is not a readable page", message_key=UNREADABLE_KEY)
        model = read_module_page(text, url, slug)
        content = [block for block in model["blocks"] if block["kind"] != "heading"]
        if model["deferred"] or not (content or model["hidden_forms"]):
            raise DataError("the module page shows nothing the app can read", message_key=UNREADABLE_KEY)
        return model

    def notices(self, slug):
        try:
            return self._todo_notices() if slug == TASK_LIST else self._table_notices(slug)
        except DataError as error:
            if error.message_key == REFUSED_KEY:
                return None
            raise

    def _todo_notices(self):
        open_tasks = self._todo()["blocks"][0]["open"]
        titled = ((task["summary"] or task["description"], task["date"]) for task in open_tasks)
        items = [{"title": title, "date": due} for title, due in titled if title]
        return {"items": items, "count": len(open_tasks)}

    def _table_notices(self, slug):
        model = self._model(slug)
        tables = [block for block in model["blocks"] if block["kind"] == "table"]
        if len(tables) != 1 or _paged(model):
            return None
        rows = [row for row in tables[0]["rows"] if not _placeholder(tables[0], row)]
        titles = (_row_title(row) for row in rows)
        return {"items": [{"title": title} for title in titles if title], "count": len(rows)}

    def _is_readable_html(self, response, text, url):
        kind = str((getattr(response, "headers", None) or {}).get("Content-Type") or "").lower()
        if "html" not in kind or getattr(response, "truncated", False):
            return False
        return find_login_form(parse_forms(text, url)) is None

    def _todo(self):
        response = self._fetch(TODO_PATH, TODO_PREFIX, lambda path: path == TODO_PATH)
        tasks = read_todo(getattr(response, "text", "") or "")
        return {"title": "", "hidden_forms": 0, "blocks": [dict(tasks, kind="tasks")]}

    def _public_link(self, slug, link):
        return {"label": link["label"], "page": self._token(slug, link["path"])}

    def _public(self, slug, model):
        return {
            "title": model["title"],
            "blocks": public_blocks(model["blocks"], lambda link: self._public_link(slug, link)),
            "hidden_forms": model["hidden_forms"],
        }
