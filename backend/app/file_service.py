import hashlib
import logging
import threading
import time
from collections import Counter

from requests import RequestException

from . import messages, school_lists
from .failure import error_kind
from .iserv import files as iserv_files
from .iserv.client import server_failure
from .iserv.errors import DataError, OutageError
from .iserv.forms import browser_headers, find_login_form, parse_forms
from .iserv.settings_forms import page_errors

logger = logging.getLogger(__name__)

ROOTS = {"own": iserv_files.OWN_PATH, "groups": iserv_files.GROUPS_PATH}
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_FILES = 20
MEGABYTE = 1024 * 1024
UPLOAD_TIMEOUT = 300
SEARCH_TIMEOUT = 60
QUERY_LIMIT = 120
KNOWN_LIMIT = 5000
RECENT_SECONDS = 600
WRITE_OK_STATUSES = (200, 201, 204, 302, 303)

UNKNOWN_FOLDER_KEY = "api.files.unknownFolder"
UNKNOWN_FILE_KEY = "api.files.unknownFile"
SHAPE_KEY = "api.files.shape"
SEARCH_EMPTY_KEY = "api.files.searchEmpty"
NO_SEARCH_KEY = "api.files.noSearch"
UPLOAD_DONE_KEY = "api.files.upload.done"
UPLOAD_UNCERTAIN_KEY = "api.files.upload.uncertain"
UPLOAD_REJECTED_KEY = "api.files.upload.rejected"
UPLOAD_UNAVAILABLE_KEY = "api.files.upload.unavailable"
UPLOAD_UNCONFIRMED_KEY = "api.files.upload.unconfirmed"
UPLOAD_BUSY_KEY = "api.files.upload.busy"
UPLOAD_EMPTY_KEY = "api.files.upload.empty"
UPLOAD_ONE_FILE_KEY = "api.files.upload.oneFile"
UPLOAD_TOO_MANY_KEY = "api.files.upload.tooMany"
UPLOAD_FILE_TOO_LARGE_KEY = "api.files.upload.fileTooLarge"
UPLOAD_TOO_LARGE_KEY = "api.files.upload.tooLarge"
UPLOAD_RECENT_KEY = "api.files.upload.recent"

NOT_OFFERED_KEY = "api.account.notOffered"

OUTCOME_DONE = "done"
OUTCOME_UNCERTAIN = "uncertain"
OUTCOME_REJECTED = "rejected"
OUTCOME_UNAVAILABLE = "unavailable"


class AccountModuleNotOffered(DataError):
    def __init__(self):
        super().__init__("the school offers this module not to this account", message_key=NOT_OFFERED_KEY)


def clean_name(name):
    text = str(name or "").replace("\\", "/").split("/")[-1]
    text = "".join(char for char in text if char.isprintable()).strip()
    return text[:200] or "file"


def fold(text):
    return " ".join(str(text or "").casefold().split())


def uploaded(before, after, names):
    remaining = Counter(fold(entry["name"]) for entry in before if entry["kind"] == iserv_files.KIND_FILE)
    fresh = []
    for entry in after:
        if entry["kind"] != iserv_files.KIND_FILE:
            continue
        label = fold(entry["name"])
        if remaining[label] > 0:
            remaining[label] -= 1
        else:
            fresh.append(label)
    for name in names:
        match = next((label for label in fresh if label == fold(name)), None)
        if match is None:
            return False
        fresh.remove(match)
    return bool(names)


def root_of(path):
    return "own" if iserv_files.own_path(path) else "groups"


def fingerprint(head, values, files):
    digest = hashlib.sha256(str(head).encode("utf-8"))
    for name, value in sorted((str(key), str(item)) for key, item in (values or {}).items()):
        digest.update(("\0%s=%s" % (name, value)).encode("utf-8"))
    for upload in files:
        digest.update(("\0%s\0" % clean_name(upload.get("filename"))).encode("utf-8"))
        digest.update(hashlib.sha256(upload.get("content") or b"").digest())
    return digest.hexdigest()


class RecentRuns:
    def __init__(self, clock):
        self.clock = clock
        self._lock = threading.Lock()
        self._runs = {}

    def unclear(self, key):
        with self._lock:
            stamp = self._runs.get(key)
            return stamp is not None and self.clock() - stamp < RECENT_SECONDS

    def note(self, key, result):
        with self._lock:
            now = self.clock()
            self._runs = {name: stamp for name, stamp in self._runs.items() if now - stamp < RECENT_SECONDS}
            if isinstance(result, dict) and result.get("outcome") == OUTCOME_UNCERTAIN:
                self._runs[key] = now


def masked(path, read):
    try:
        return read()
    except (DataError, OutageError) as error:
        shape = {key: value for key, value in (error.detail or {}).items() if key not in ("path", "final_path")}
        error.detail = dict(shape, area=root_of(path))
        error.args = ("file page in the %s area not read" % root_of(path),)
        raise


def input_refusal(files):
    if not files:
        return messages.result(False, UPLOAD_EMPTY_KEY)
    if len(files) > MAX_FILES:
        return messages.result(False, UPLOAD_TOO_MANY_KEY, {"max": MAX_FILES})
    sizes = [len(upload.get("content") or b"") for upload in files]
    if max(sizes) > MAX_FILE_BYTES:
        return messages.result(False, UPLOAD_FILE_TOO_LARGE_KEY, {"max": MAX_FILE_BYTES // MEGABYTE})
    if sum(sizes) > MAX_TOTAL_BYTES:
        return messages.result(False, UPLOAD_TOO_LARGE_KEY, {"max": MAX_TOTAL_BYTES // MEGABYTE})
    return None


class FileService:
    def __init__(self, connection, clock=None):
        self.connection = connection
        self.clock = clock or time.time
        self._lock = threading.Lock()
        self._known = {}
        self._busy = set()
        self._recent = RecentRuns(lambda: self.clock())

    def _school_url(self):
        return self.connection.store.load_config().get("school_url", "")

    def _client(self):
        return self.connection.iserv_session()

    def _remember(self, entries):
        with self._lock:
            for entry in entries:
                self._known[entry["path"]] = entry["kind"]
            if len(self._known) > KNOWN_LIMIT:
                for path in list(self._known)[: len(self._known) - KNOWN_LIMIT]:
                    self._known.pop(path, None)

    def _folder_path(self, path):
        wanted = str(path or "").strip() or iserv_files.OWN_PATH
        if wanted in ROOTS:
            return ROOTS[wanted]
        wanted = wanted.rstrip("/")
        if wanted in ROOTS.values():
            return wanted
        with self._lock:
            kind = self._known.get(wanted)
        if kind == iserv_files.KIND_FOLDER and iserv_files.listing_path(wanted):
            return wanted
        raise DataError("unknown folder", message_key=UNKNOWN_FOLDER_KEY, detail={"area": root_of(wanted)})

    def _read(self, path, client=None):
        client = client or self._client()
        response = masked(path, lambda: school_lists.module_answer(client, path, iserv_files.within_files))
        parsed = iserv_files.parse_listing(getattr(response, "text", "") or "", str(getattr(response, "url", "") or "") or self._school_url() + path)
        if not parsed["framed"]:
            logger.info("school#%s file list in the %s area carries no file table", self.connection.id, root_of(path))
            raise DataError("file list unreadable", message_key=SHAPE_KEY, detail={"area": root_of(path)})
        self._remember(parsed["entries"])
        return client, response, parsed

    def _public(self, path, parsed, query=""):
        return {
            "path": path,
            "root": root_of(path),
            "entries": parsed["entries"],
            "crumbs": parsed["crumbs"],
            "location": parsed["location"],
            "query": query,
            "can_search": parsed["search"] is not None,
            "can_upload": parsed["upload"] is not None,
            "upload_multiple": bool(parsed["upload"] and parsed["upload"]["multiple"]),
            "upload_accept": parsed["upload"]["accept"] if parsed["upload"] else "",
        }

    def listing(self, path=""):
        folder = self._folder_path(path)
        _client, _response, parsed = self._read(folder)
        logger.info("school#%s file list read: %d entries", self.connection.id, len(parsed["entries"]))
        return self._public(folder, parsed)

    def search(self, path, query):
        folder = self._folder_path(path)
        text = " ".join(str(query or "").split())[:QUERY_LIMIT]
        if not text:
            raise DataError("empty file search", message_key=SEARCH_EMPTY_KEY)
        client, response, parsed = self._read(folder)
        form = parsed["search"]
        if form is None:
            raise DataError("no file search offered", message_key=NO_SEARCH_KEY)
        pairs = [(name, value) for name, value in form["hidden"] if name != form["field"]]
        pairs.append((form["field"], text))
        if form["submit"] is not None:
            pairs.append(form["submit"])
        headers = browser_headers(getattr(response, "url", "") or "")
        answer = client.post_form(form["action"], pairs, headers=headers, timeout=SEARCH_TIMEOUT)
        failure = server_failure(answer)
        if failure is not None:
            raise failure
        status = int(getattr(answer, "status_code", 0) or 0)
        found = iserv_files.parse_listing(getattr(answer, "text", "") or "", str(getattr(answer, "url", "") or form["action"]))
        if status != 200 or not found["framed"]:
            logger.info("school#%s file search answered %d without a file table", self.connection.id, status)
            raise DataError("file search unreadable", message_key=SHAPE_KEY, detail={"area": "search"})
        self._remember(found["entries"])
        logger.info("school#%s file search read: %d entries", self.connection.id, len(found["entries"]))
        return dict(self._public(folder, dict(found, upload=parsed["upload"], search=form)), query=text)

    def download(self, path):
        wanted = str(path or "").strip()
        with self._lock:
            kind = self._known.get(wanted)
        if kind != iserv_files.KIND_FILE:
            raise DataError("unknown file", message_key=UNKNOWN_FILE_KEY, detail={"area": root_of(wanted)})
        return masked(wanted, lambda: school_lists.read_school_file(self._client(), wanted, self._school_url()))

    def upload(self, path, files, confirmed=False):
        if confirmed is not True:
            return messages.result(False, UPLOAD_UNCONFIRMED_KEY)
        refusal = input_refusal(files or [])
        if refusal is not None:
            return refusal
        folder = self._folder_path(path)
        key = fingerprint(folder, {}, files)
        if self._recent.unclear(key):
            logger.info("school#%s file upload refused: the same files went out a moment ago without a clear answer", self.connection.id)
            return messages.result(False, UPLOAD_RECENT_KEY, outcome=OUTCOME_UNCERTAIN)
        with self._lock:
            if folder in self._busy:
                return messages.result(False, UPLOAD_BUSY_KEY)
            self._busy.add(folder)
        try:
            result = self._upload(folder, files)
            self._recent.note(key, result)
            return result
        finally:
            with self._lock:
                self._busy.discard(folder)

    def _upload(self, folder, files):
        client, response, parsed = self._read(folder)
        before = self._public(folder, parsed)
        form = parsed["upload"]
        if form is None:
            logger.info("school#%s file upload refused before sending: no upload form", self.connection.id)
            return messages.result(False, UPLOAD_UNAVAILABLE_KEY, outcome=OUTCOME_UNAVAILABLE, listing=before)
        if len(files) > 1 and not form["multiple"]:
            return messages.result(False, UPLOAD_ONE_FILE_KEY, listing=before)
        pairs = list(form["hidden"])
        if form["submit"] is not None:
            pairs.append(form["submit"])
        parts = [
            (form["file_field"], (clean_name(upload.get("filename")), upload.get("content") or b"", upload.get("content_type") or "application/octet-stream"))
            for upload in files
        ]
        headers = browser_headers(getattr(response, "url", "") or "")
        try:
            sent = client.post_form(form["action"], pairs, files=parts, headers=headers, timeout=UPLOAD_TIMEOUT)
        except RequestException as error:
            logger.warning("school#%s file upload outcome unknown: the request to the school failed (%s)", self.connection.id, error_kind(error))
            return self._settle(folder, None, before, files, [])
        errors = self._rejection(sent)
        return self._settle(folder, OUTCOME_REJECTED if errors is not None else None, before, files, errors or [])

    def _rejection(self, sent):
        status = int(getattr(sent, "status_code", 0) or 0)
        redirected = bool(getattr(sent, "history", None) or [])
        answer = getattr(sent, "text", "") or ""
        url = str(getattr(sent, "url", "") or "")
        if server_failure(sent) is not None:
            logger.warning("school#%s file upload outcome unknown: the school answered with status %d", self.connection.id, status)
            return None
        if not redirected and 400 <= status < 500:
            logger.warning("school#%s file upload refused by the school with status %d", self.connection.id, status)
            return page_errors(answer)
        if status in WRITE_OK_STATUSES and find_login_form(parse_forms(answer, url or "https://school.invalid/")) is not None:
            logger.warning("school#%s file upload refused: the school asked for the sign-in", self.connection.id)
            return []
        return None

    def _settle(self, folder, outcome, before, files, errors):
        try:
            _client, _response, parsed = self._read(folder)
            after = self._public(folder, parsed)
        except Exception as error:
            logger.warning("school#%s file list could not be read again after the upload: %s", self.connection.id, error_kind(error))
            after = None
        names = [clean_name(upload.get("filename")) for upload in files]
        changed = after is not None and uploaded(before["entries"], after["entries"], names)
        if changed:
            logger.info("school#%s file upload done and seen in the file list", self.connection.id)
            return messages.result(True, UPLOAD_DONE_KEY, outcome=OUTCOME_DONE, listing=after)
        if outcome == OUTCOME_REJECTED:
            return messages.result(False, UPLOAD_REJECTED_KEY, outcome=OUTCOME_REJECTED, errors=[str(item)[:200] for item in errors], listing=after or before)
        logger.warning("school#%s file upload outcome unknown: the file list does not show the files", self.connection.id)
        return messages.result(False, UPLOAD_UNCERTAIN_KEY, outcome=OUTCOME_UNCERTAIN, listing=after or before)
