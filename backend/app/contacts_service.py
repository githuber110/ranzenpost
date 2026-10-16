import logging
import threading
import time

from requests import RequestException

from . import messages, school_lists
from .failure import error_kind
from .file_service import RecentRuns, clean_name, fingerprint, fold
from .iserv import addressbook, mailinglists
from .iserv.client import server_failure
from .iserv.errors import DataError
from .iserv.forms import browser_headers, find_login_form, parse_forms
from .iserv.pages import path_of
from .iserv.settings_forms import page_errors
from .pathpattern import path_pattern

logger = logging.getLogger(__name__)

QUERY_MIN = 2
QUERY_LIMIT = 80
PEOPLE_LIMIT = 50
BOOKS_SECONDS = 600
IMPORT_MAX_BYTES = 2 * 1024 * 1024
TEXT_LIMIT = 200
POST_TIMEOUT = 60
WRITE_OK_STATUSES = (200, 201, 204, 302, 303)

SHAPE_KEY = "api.contacts.shape"
UNKNOWN_LIST_KEY = "api.lists.unknown"
UNCONFIRMED_KEY = "api.lists.unconfirmed"
BUSY_KEY = "api.lists.busy"
IMPORT_DONE_KEY = "api.lists.import.done"
IMPORT_UNCERTAIN_KEY = "api.lists.import.uncertain"
IMPORT_REJECTED_KEY = "api.lists.import.rejected"
IMPORT_UNAVAILABLE_KEY = "api.lists.import.unavailable"
IMPORT_EMPTY_KEY = "api.lists.import.empty"
IMPORT_TOO_LARGE_KEY = "api.lists.import.tooLarge"
IMPORT_MISSING_KEY = "api.lists.import.missing"
IMPORT_RECENT_KEY = "api.lists.import.recent"
DELETE_DONE_KEY = "api.lists.delete.done"
DELETE_UNCERTAIN_KEY = "api.lists.delete.uncertain"
DELETE_REJECTED_KEY = "api.lists.delete.rejected"
DELETE_UNAVAILABLE_KEY = "api.lists.delete.unavailable"
DELETE_OTHERS_KEY = "api.lists.delete.othersGone"

OUTCOME_DONE = "done"
OUTCOME_UNCERTAIN = "uncertain"
OUTCOME_REJECTED = "rejected"
OUTCOME_UNAVAILABLE = "unavailable"


def public_list(entry):
    return {"id": entry["id"], "title": entry["title"], "extra": entry["extra"], "has_detail": bool(entry["path"]), "deletable": entry["box"] is not None}


def import_fields(importer):
    if importer is None:
        return []
    return [{"name": field["name"], "label": field["label"], "required": field["required"], "maxlength": field["maxlength"]} for field in importer["texts"]]


def _stem(name):
    text = clean_name(name)
    stem, dot, _suffix = text.rpartition(".")
    return stem if dot and stem else text


class ContactsService:
    def __init__(self, connection, clock=None):
        self.connection = connection
        self.clock = clock or time.time
        self._lock = threading.Lock()
        self._books = (0.0, None)
        self._lists = {}
        self._busy = False
        self._recent = RecentRuns(lambda: self.clock())

    def _client(self):
        return self.connection.iserv_session()

    def _school_url(self):
        return self.connection.store.load_config().get("school_url", "")

    def _url(self, response, path):
        return str(getattr(response, "url", "") or "") or self._school_url() + path

    def books(self, client=None):
        stamp, cached = self._books
        if cached is not None and self.clock() - stamp < BOOKS_SECONDS:
            return cached
        client = client or self._client()
        try:
            response = school_lists.module_answer(client, addressbook.ROOT, addressbook.within_addressbook)
            final = path_of(self._url(response, addressbook.ROOT))
            listed = addressbook.book_links(getattr(response, "text", "") or "", final)
        except DataError as error:
            logger.info("school#%s address book start page not read, the shared book is tried: %s", self.connection.id, error_kind(error))
            response, final, listed = None, "", []
        if not any(entry["path"] == addressbook.PUBLIC_PATH for entry in listed):
            listed.append({"path": addressbook.PUBLIC_PATH, "label": ""})
        found = []
        for book in listed:
            try:
                page = response if book["path"] == final.rstrip("/") else school_lists.module_answer(client, book["path"], addressbook.within_addressbook)
            except DataError as error:
                logger.info("school#%s address book %s not read: %s", self.connection.id, path_pattern(book["path"]), error_kind(error))
                continue
            target = addressbook.searchable(getattr(page, "text", "") or "", self._url(page, book["path"]))
            if target:
                found.append(dict(book, target=target))
        self._books = (self.clock(), found)
        logger.info("school#%s address books found: %d of %d searchable", self.connection.id, len(found), len(listed))
        return found

    def search(self, query):
        text = " ".join(str(query or "").split())[:QUERY_LIMIT]
        if len(text) < QUERY_MIN:
            return {"people": [], "query": text}
        client = self._client()
        people = []
        seen = set()
        read = 0
        for book in self.books(client):
            answer = school_lists.module_answer(_Params(client, {addressbook.SEARCH_FIELD: text}), book["target"], addressbook.within_addressbook)
            found = addressbook.parse_people(getattr(answer, "text", "") or "")
            if found is None:
                logger.info("school#%s address book %s carries no table", self.connection.id, path_pattern(book["target"]))
                continue
            read += 1
            for person in found:
                key = (person["address"] or person["name"]).casefold()
                if key in seen:
                    continue
                seen.add(key)
                people.append(dict(person, book=book["label"]))
        if not read:
            raise DataError("address book unreadable", message_key=SHAPE_KEY)
        logger.info("school#%s address search read: %d people from %d books", self.connection.id, len(people), read)
        return {"people": people[:PEOPLE_LIMIT], "query": text}

    def recipients(self, query):
        found = self.search(query)["people"]
        return [{"name": person["name"], "address": person["address"], "group": False} for person in found if person["address"]]

    def _overview(self, client=None):
        client = client or self._client()
        response = school_lists.module_answer(client, mailinglists.LIST_PATH, mailinglists.within_lists)
        parsed = mailinglists.parse_overview(getattr(response, "text", "") or "", self._url(response, mailinglists.LIST_PATH))
        if not parsed["framed"] and parsed["importer"] is None:
            logger.info("school#%s mailing list page carries no list table", self.connection.id)
            raise DataError("mailing lists unreadable", message_key=SHAPE_KEY)
        with self._lock:
            self._lists = {entry["id"]: entry for entry in parsed["lists"]}
        return client, response, parsed

    def _public_overview(self, parsed):
        return {
            "lists": [public_list(entry) for entry in parsed["lists"]],
            "labels": parsed["labels"],
            "can_import": parsed["importer"] is not None,
            "import_fields": import_fields(parsed["importer"]),
            "import_accept": parsed["importer"]["accept"] if parsed["importer"] else "",
            "can_delete": parsed["remover"] is not None and any(entry["box"] is not None for entry in parsed["lists"]),
        }

    def lists(self):
        _client, _response, parsed = self._overview()
        logger.info("school#%s mailing lists read: %d", self.connection.id, len(parsed["lists"]))
        return self._public_overview(parsed)

    def _known(self, list_id):
        with self._lock:
            entry = self._lists.get(str(list_id or ""))
        if entry is None:
            raise DataError("unknown mailing list", message_key=UNKNOWN_LIST_KEY)
        return entry

    def list_detail(self, list_id):
        entry = self._known(list_id)
        if not entry["path"]:
            return {"id": entry["id"], "title": entry["title"], "addresses": [], "read": False}
        response = school_lists.module_answer(self._client(), entry["path"], mailinglists.within_lists)
        parsed = mailinglists.parse_detail(getattr(response, "text", "") or "")
        logger.info("school#%s mailing list detail read: %d addresses", self.connection.id, len(parsed["addresses"]))
        return {"id": entry["id"], "title": entry["title"], "addresses": parsed["addresses"], "read": True}

    def _claim(self):
        with self._lock:
            if self._busy:
                return False
            self._busy = True
            return True

    def _release(self):
        with self._lock:
            self._busy = False

    def import_list(self, values, files, confirmed=False):
        if confirmed is not True:
            return messages.result(False, UNCONFIRMED_KEY)
        if len(files or []) != 1 or not (files[0].get("content") or b""):
            return messages.result(False, IMPORT_EMPTY_KEY)
        if len(files[0]["content"]) > IMPORT_MAX_BYTES:
            return messages.result(False, IMPORT_TOO_LARGE_KEY, {"max": IMPORT_MAX_BYTES // 1024})
        values = values if isinstance(values, dict) else {}
        key = fingerprint("import", values, files[:1])
        if self._recent.unclear(key):
            logger.info("school#%s mailing list import refused: the same file went out a moment ago without a clear answer", self.connection.id)
            return messages.result(False, IMPORT_RECENT_KEY, outcome=OUTCOME_UNCERTAIN)
        if not self._claim():
            return messages.result(False, BUSY_KEY)
        try:
            result = self._import(values, files[0])
            self._recent.note(key, result)
            return result
        finally:
            self._release()

    def _import(self, values, upload):
        client, response, parsed = self._overview()
        before = self._public_overview(parsed)
        form = parsed["importer"]
        if form is None:
            logger.info("school#%s mailing list import refused before sending: no import form", self.connection.id)
            return messages.result(False, IMPORT_UNAVAILABLE_KEY, outcome=OUTCOME_UNAVAILABLE, overview=before)
        pairs = list(form["hidden"])
        typed = []
        for field in form["texts"]:
            value = " ".join(str(values.get(field["name"]) or "").split())[:TEXT_LIMIT]
            if field["required"] and not value:
                return messages.result(False, IMPORT_MISSING_KEY, {"field": field["label"] or field["name"]}, overview=before)
            pairs.append((field["name"], value))
            if value:
                typed.append(value)
        if form["submit"] is not None:
            pairs.append(form["submit"])
        name = clean_name(upload.get("filename"))
        parts = [(form["file_field"], (name, upload["content"], upload.get("content_type") or "text/plain"))]
        known = {entry["id"] for entry in parsed["lists"]}
        try:
            sent = client.post_form(form["action"], pairs, files=parts, headers=browser_headers(getattr(response, "url", "") or ""), timeout=POST_TIMEOUT)
        except RequestException as error:
            logger.warning("school#%s mailing list import outcome unknown: the request failed (%s)", self.connection.id, error_kind(error))
            return self._settle_import(known, None, [], before, typed + [_stem(name), name])
        errors = self._rejection("import", sent)
        return self._settle_import(known, OUTCOME_REJECTED if errors is not None else None, errors or [], before, typed + [_stem(name), name])

    def _settle_import(self, known, outcome, errors, before, names):
        try:
            _client, _response, parsed = self._overview()
            after = self._public_overview(parsed)
        except Exception as error:
            logger.warning("school#%s mailing lists could not be read again after the import: %s", self.connection.id, error_kind(error))
            parsed, after = None, None
        fresh = [entry for entry in (parsed or {}).get("lists", []) if entry["id"] not in known]
        wanted = {fold(name) for name in names if name}
        if any(fold(entry["title"]) in wanted for entry in fresh):
            logger.info("school#%s mailing list import done and seen in the overview", self.connection.id)
            return messages.result(True, IMPORT_DONE_KEY, outcome=OUTCOME_DONE, overview=after)
        if outcome == OUTCOME_REJECTED:
            return messages.result(False, IMPORT_REJECTED_KEY, outcome=OUTCOME_REJECTED, errors=[str(item)[:200] for item in errors], overview=after or before)
        logger.warning("school#%s mailing list import outcome unknown: %d new lists without the expected title", self.connection.id, len(fresh))
        return messages.result(False, IMPORT_UNCERTAIN_KEY, outcome=OUTCOME_UNCERTAIN, overview=after or before)

    def delete_list(self, list_id, confirmed=False):
        if confirmed is not True:
            return messages.result(False, UNCONFIRMED_KEY)
        if not self._claim():
            return messages.result(False, BUSY_KEY)
        try:
            return self._delete(str(list_id or ""))
        finally:
            self._release()

    def _delete(self, list_id):
        self._known(list_id)
        client, response, parsed = self._overview()
        before = self._public_overview(parsed)
        entry = next((item for item in parsed["lists"] if item["id"] == list_id), None)
        remover = parsed["remover"]
        if entry is None or entry["box"] is None or remover is None:
            logger.info("school#%s mailing list delete refused before sending: the list or its form is no longer offered", self.connection.id)
            return messages.result(False, DELETE_UNAVAILABLE_KEY, outcome=OUTCOME_UNAVAILABLE, overview=before)
        pairs = list(remover["hidden"]) + [tuple(entry["box"]), remover["button"]]
        try:
            sent = client.post_form(remover["action"], pairs, headers=browser_headers(getattr(response, "url", "") or ""), timeout=POST_TIMEOUT)
            errors = self._rejection("delete", sent)
            answered = int(getattr(sent, "status_code", 0) or 0) == 200 and not (getattr(sent, "history", None) or [])
            if errors is None and answered:
                follow = mailinglists.follow_up_form(
                    getattr(sent, "text", "") or "",
                    str(getattr(sent, "url", "") or remover["action"]),
                    entry["box"][1],
                    remover["action"],
                    [item["box"][1] for item in parsed["lists"] if item["box"] is not None],
                )
                if follow is not None:
                    logger.info("school#%s mailing list delete asked for a confirmation, the confirmation form is sent", self.connection.id)
                    sent = client.post_form(follow["action"], follow["pairs"], headers=browser_headers(str(getattr(sent, "url", "") or "")), timeout=POST_TIMEOUT)
                    errors = self._rejection("delete", sent)
        except RequestException as error:
            logger.warning("school#%s mailing list delete outcome unknown: the request failed (%s)", self.connection.id, error_kind(error))
            errors = None
        return self._settle_delete(entry, OUTCOME_REJECTED if errors is not None else None, errors or [], before, {item["id"] for item in parsed["lists"]})

    def _settle_delete(self, entry, outcome, errors, before, listed):
        try:
            _client, _response, parsed = self._overview()
            after = self._public_overview(parsed)
        except Exception as error:
            logger.warning("school#%s mailing lists could not be read again after the delete: %s", self.connection.id, error_kind(error))
            parsed, after = None, None
        remaining = {item["id"] for item in parsed["lists"]} if parsed is not None else None
        if remaining is not None and entry["id"] not in remaining and listed - {entry["id"]} - remaining:
            logger.warning("school#%s mailing list delete: %d other lists are gone as well", self.connection.id, len(listed - {entry["id"]} - remaining))
            return messages.result(False, DELETE_OTHERS_KEY, outcome=OUTCOME_UNCERTAIN, overview=after)
        if remaining is not None and entry["id"] not in remaining:
            logger.info("school#%s mailing list delete done and seen in the overview", self.connection.id)
            return messages.result(True, DELETE_DONE_KEY, outcome=OUTCOME_DONE, overview=after)
        if outcome == OUTCOME_REJECTED:
            return messages.result(False, DELETE_REJECTED_KEY, outcome=OUTCOME_REJECTED, errors=[str(item)[:200] for item in errors], overview=after or before)
        logger.warning("school#%s mailing list delete outcome unknown: the list is still listed", self.connection.id)
        return messages.result(False, DELETE_UNCERTAIN_KEY, outcome=OUTCOME_UNCERTAIN, overview=after or before)

    def _rejection(self, action, sent):
        status = int(getattr(sent, "status_code", 0) or 0)
        redirected = bool(getattr(sent, "history", None) or [])
        answer = getattr(sent, "text", "") or ""
        url = str(getattr(sent, "url", "") or "")
        if server_failure(sent) is not None:
            logger.warning("school#%s mailing list %s outcome unknown: the school answered with status %d", self.connection.id, action, status)
            return None
        if not redirected and 400 <= status < 500:
            logger.warning("school#%s mailing list %s refused by the school with status %d", self.connection.id, action, status)
            return page_errors(answer)
        if status in WRITE_OK_STATUSES and find_login_form(parse_forms(answer, url or "https://school.invalid/")) is not None:
            logger.warning("school#%s mailing list %s refused: the school asked for the sign-in", self.connection.id, action)
            return []
        return None


class _Params:
    def __init__(self, client, params):
        self.client = client
        self.params = params

    def fetch(self, path, params=None):
        return self.client.fetch(path, dict(params or {}, **self.params))
