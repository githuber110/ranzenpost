import logging
import threading
import time

from requests import RequestException

from . import account_lists, messages, school_lists
from .failure import error_kind
from .iserv.client import server_failure
from .iserv.forms import browser_headers, find_login_form, parse_forms
from .iserv.forums import FORUMS_PATH, READ_PATH, is_forum_page, total_unread
from .iserv.pages import path_of

logger = logging.getLogger(__name__)

READ_DONE_KEY = "api.forums.read.done"
READ_UNCERTAIN_KEY = "api.forums.read.uncertain"
READ_REJECTED_KEY = "api.forums.read.rejected"
READ_UNAVAILABLE_KEY = "api.forums.read.unavailable"
READ_UNCONFIRMED_KEY = "api.forums.read.unconfirmed"
READ_BUSY_KEY = "api.forums.read.busy"
OUTCOME_DONE = "done"
OUTCOME_UNCERTAIN = "uncertain"
OUTCOME_REJECTED = "rejected"
OUTCOME_UNAVAILABLE = "unavailable"
POST_TIMEOUT = 60
SKIPPED_CONTROLS = frozenset({"submit", "button", "checkbox", "radio", "file", "reset", "image"})


def read_form(html, page_url):
    for form in parse_forms(html or "", page_url or "https://school.invalid" + FORUMS_PATH):
        if form.method == "post" and path_of(form.action).rstrip("/") == READ_PATH:
            return form
    return None


def read_payload(form):
    pairs = [(name, value) for name, value in form.fields.items() if form.control_types.get(name) not in SKIPPED_CONTROLS]
    for name, value in form.submits.items():
        pairs.append((name, value))
        break
    return pairs


def all_read(forums):
    return bool(forums) and all(forum.get("unread") == 0 for forum in forums) and total_unread(forums) == 0


class ForumService:
    def __init__(self, connection):
        self.connection = connection
        self._lock = threading.Lock()
        self._busy = False

    def _now(self):
        return int(getattr(self.connection, "clock", time.time)())

    def mark_all_read(self, confirmed=False):
        if confirmed is not True:
            return messages.result(False, READ_UNCONFIRMED_KEY)
        with self._lock:
            if self._busy:
                return messages.result(False, READ_BUSY_KEY)
            self._busy = True
        try:
            return self._mark_all_read()
        finally:
            with self._lock:
                self._busy = False

    def _mark_all_read(self):
        client = self.connection._session()
        page = school_lists.module_answer(client, FORUMS_PATH, is_forum_page)
        page_url = str(getattr(page, "url", "") or "")
        form = read_form(getattr(page, "text", "") or "", page_url)
        if form is None:
            logger.info("forum mark read refused before sending: the form is not offered")
            return messages.result(False, READ_UNAVAILABLE_KEY, outcome=OUTCOME_UNAVAILABLE)
        try:
            sent = client.post_form(form.action, read_payload(form), headers=browser_headers(page_url), timeout=POST_TIMEOUT)
        except RequestException as error:
            logger.warning("forum mark read outcome unknown: the request to the school failed (%s)", error_kind(error))
            return self._settle(None)
        refused = self._refused(sent)
        if refused:
            return messages.result(False, READ_REJECTED_KEY, outcome=OUTCOME_REJECTED)
        return self._settle(sent)

    def _refused(self, sent):
        status = int(getattr(sent, "status_code", 0) or 0)
        redirected = bool(getattr(sent, "history", None) or [])
        if server_failure(sent) is not None:
            logger.warning("forum mark read outcome unknown: the school answered with status %d", status)
            return False
        if not redirected and 400 <= status < 500:
            logger.warning("forum mark read refused by the school with status %d", status)
            return True
        answer = getattr(sent, "text", "") or ""
        url = str(getattr(sent, "url", "") or "") or "https://school.invalid/"
        if find_login_form(parse_forms(answer, url)) is not None:
            logger.warning("forum mark read refused: the school asked for the sign-in")
            return True
        return False

    def _settle(self, sent):
        try:
            listed = account_lists.read_forums(self.connection._session())
        except Exception as error:
            logger.warning("forum list could not be read again after mark read: %s", error_kind(error))
            return messages.result(False, READ_UNCERTAIN_KEY, outcome=OUTCOME_UNCERTAIN)
        forums = listed[account_lists.FORUMS_FIELD]
        school_lists.store_list(
            self.connection.store,
            self.connection.id,
            account_lists.FORUMS_FIELD,
            forums,
            self._now(),
            account_lists.list_extra_of(listed),
        )
        if sent is not None and all_read(forums):
            logger.info("forum mark read done and seen on the forum overview")
            return messages.result(True, READ_DONE_KEY, outcome=OUTCOME_DONE)
        logger.warning("forum mark read outcome unknown: the forum overview still shows unread posts")
        return messages.result(False, READ_UNCERTAIN_KEY, outcome=OUTCOME_UNCERTAIN)
