import hashlib
import logging
import threading
from collections import OrderedDict

from .iserv.conferences import module_path
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

    def _answer(self, path, prefix, allowed):
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
        prefix = PAGE_MODULES[slug]["prefix"]
        response = self._answer(self._path(slug, token), prefix, lambda path: page_allowed(slug, path))
        url = str(getattr(response, "url", "") or "")
        text = getattr(response, "text", "") or ""
        if not self._html(response, text, url):
            raise DataError("the module page is not a readable page", message_key=UNREADABLE_KEY)
        model = read_module_page(text, url, slug)
        content = [block for block in model["blocks"] if block["kind"] != "heading"]
        if model["deferred"] or not (content or model["hidden_forms"]):
            raise DataError("the module page shows nothing the app can read", message_key=UNREADABLE_KEY)
        landed = module_path(url, url, prefix, True) or PAGE_MODULES[slug]["path"]
        return self._public(slug, landed, model)

    def _html(self, response, text, url):
        kind = str((getattr(response, "headers", None) or {}).get("Content-Type") or "").lower()
        if "html" not in kind or getattr(response, "truncated", False):
            return False
        return find_login_form(parse_forms(text, url)) is None

    def _todo(self):
        response = self._answer(TODO_PATH, TODO_PREFIX, lambda path: path == TODO_PATH)
        tasks = read_todo(getattr(response, "text", "") or "")
        return {"module": TASK_LIST, "page": "", "title": "", "notices": [], "hidden_forms": 0, "blocks": [dict(tasks, kind="tasks")]}

    def _public_link(self, slug, link):
        return {"label": link["label"], "page": self._token(slug, link["path"])}

    def _public(self, slug, path, model):
        blocks = []
        for block in model["blocks"]:
            if block["kind"] == "links":
                blocks.append({"kind": "links", "links": [self._public_link(slug, link) for link in block["links"]]})
            elif block["kind"] == "table":
                rows = [{"cells": row["cells"], "links": [self._public_link(slug, link) for link in row["links"]]} for row in block["rows"]]
                blocks.append(dict(block, rows=rows))
            else:
                blocks.append(dict(block))
        return {
            "module": slug,
            "page": self._token(slug, path),
            "title": model["title"],
            "blocks": blocks,
            "notices": list(model["notices"]),
            "hidden_forms": model["hidden_forms"],
        }
