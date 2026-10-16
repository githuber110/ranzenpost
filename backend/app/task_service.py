import html
import logging
import re
import threading
import time
from collections import Counter
from urllib.parse import urlparse

from requests import RequestException

from . import messages, school_lists
from .failure import error_kind
from .iserv.client import server_failure
from .iserv.errors import DataError
from .iserv.exercise_detail import (
    DESCRIPTION,
    FEEDBACK,
    FILES,
    SOLUTION,
    SUBMISSION,
    form_errors,
    parse_task_detail,
    shape_of,
)
from .iserv.exercises import DETAIL_PATH
from .iserv import forms as login_forms
from .iserv.pages import path_of, squeezed
from .pathpattern import path_pattern
from .requestlog import url_host
from .store import connection_known, edit

logger = logging.getLogger(__name__)

DETAILS_FIELD = "task_details"
SHAPES_FIELD = "task_detail_shapes"
DETAIL_KEEP = 60
FILE_KINDS = ("files", "images", SUBMISSION, FEEDBACK, SOLUTION)
SECTION_KINDS = (SUBMISSION, FEEDBACK, SOLUTION)
ACTIONS = ("upload", "text", "confirm", "undo", "delete")
WRITE_OK_STATUSES = (200, 201, 204, 302, 303)
TEXT_MAX_LENGTH = 50000
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_FILES = 20
MEGABYTE = 1024 * 1024
UPLOAD_TIMEOUT = 300
POST_TIMEOUT = 60
SPACE = re.compile(r"\s+")

TASK_UNKNOWN_KEY = "api.tasks.unknown"
TASK_NO_DETAIL_KEY = "api.tasks.noDetail"
ACT_DONE_KEY = "api.tasks.act.done"
ACT_UNCERTAIN_KEY = "api.tasks.act.uncertain"
ACT_REJECTED_KEY = "api.tasks.act.rejected"
ACT_UNAVAILABLE_KEY = "api.tasks.act.unavailable"
ACT_UNCONFIRMED_KEY = "api.tasks.act.unconfirmed"
ACT_BUSY_KEY = "api.tasks.act.busy"
ACT_INVALID_KEY = "api.tasks.act.invalid"
ACT_EMPTY_KEY = "api.tasks.act.empty"
ACT_ONE_FILE_KEY = "api.tasks.act.oneFile"
ACT_TOO_LARGE_KEY = "api.tasks.act.tooLarge"
ACT_FILE_TOO_LARGE_KEY = "api.tasks.act.fileTooLarge"
ACT_TOO_MANY_KEY = "api.tasks.act.tooMany"
ACT_TOO_LONG_KEY = "api.tasks.act.tooLong"

OUTCOME_DONE = "done"
OUTCOME_UNCERTAIN = "uncertain"
OUTCOME_REJECTED = "rejected"
OUTCOME_UNAVAILABLE = "unavailable"


def _links(entries, school_url):
    return school_lists.public_links(entries, school_url)


def _section(payload, school_url):
    return {
        "text": list(payload["text"]),
        "facts": list(payload["facts"]),
        "files": _links(payload["files"] + payload["images"], school_url),
        "links": _links(payload["links"], school_url),
    }


def _fold(text):
    return SPACE.sub(" ", str(text or "")).strip().casefold()


def _actions(parsed, submission_files):
    actions = {}
    deletions = []
    labels = [_fold(entry["label"]) for entry in submission_files]
    for form in parsed["forms"]:
        if not form["writable"]:
            continue
        operations = form["operations"]
        if "upload" in operations and "upload" not in actions:
            actions["upload"] = {"form": form["id"], "multiple": bool(form.get("multiple")), "accept": form.get("accept") or ""}
        if "text" in operations and "text" not in actions:
            actions["text"] = {"form": form["id"], "text": list(form.get("text") or []), "max_length": int(form.get("max_length") or 0)}
        for kind in ("confirm", "undo"):
            if kind in operations and kind not in actions:
                actions[kind] = {"form": form["id"]}
        if "delete" in operations:
            for index, target in enumerate(form.get("targets") or []):
                label = _fold(target["label"])
                deletions.append({
                    "form": form["id"],
                    "target": index,
                    "label": target["label"],
                    "value": target["value"],
                    "file": labels.index(label) if label and label in labels else -1,
                })
    if deletions:
        actions["delete"] = deletions
    return actions


def _unrecognised(parsed):
    return sum(1 for form in parsed["forms"] if form["method"] == "post" and form["writable"] and not form["operations"])


def public_detail(parsed, school_url, now):
    sections = parsed["sections"]
    description = sections[DESCRIPTION]
    attachments = sections[FILES]
    submission = _section(sections[SUBMISSION], school_url)
    detail = {
        "text": list(parsed["text"]),
        "facts": list(parsed["facts"]),
        "start": parsed["start"],
        "start_text": parsed["start_text"],
        "due": parsed["due"],
        "due_text": parsed["due_text"],
        "tags": list(parsed["tags"]),
        "state_text": parsed["state_text"],
        "files": _links(description["files"] + attachments["files"], school_url),
        "images": _links(description["images"] + attachments["images"], school_url),
        "links": _links(description["links"] + attachments["links"], school_url),
        SUBMISSION: submission,
        FEEDBACK: _section(sections[FEEDBACK], school_url),
        SOLUTION: _section(sections[SOLUTION], school_url),
        "actions": _actions(parsed, submission["files"]),
        "unrecognised": _unrecognised(parsed),
        "read_at": int(now),
    }
    return detail


def task_file_path(detail, kind, index):
    if kind not in FILE_KINDS or not isinstance(detail, dict):
        return ""
    if kind in ("files", "images"):
        return school_lists.listed_file_path(detail.get(kind), index)
    section = detail.get(kind)
    return school_lists.listed_file_path(section.get("files") if isinstance(section, dict) else None, index)


def stored_details(store, connection_id):
    holder = store.load_calendar_snapshot().get(DETAILS_FIELD)
    mine = holder.get(connection_id) if isinstance(holder, dict) else None
    return mine if isinstance(mine, dict) else {}


def stored_shape(store, connection_id):
    holder = store.load_calendar_snapshot().get(SHAPES_FIELD)
    mine = holder.get(connection_id) if isinstance(holder, dict) else None
    return mine if isinstance(mine, dict) else None


def remember_detail(store, connection_id, task_id, detail, shape):
    def change(snapshot):
        if not connection_known(store, connection_id):
            return
        holder = snapshot.get(DETAILS_FIELD)
        if not isinstance(holder, dict):
            holder = {}
            snapshot[DETAILS_FIELD] = holder
        mine = holder.get(connection_id)
        mine = dict(mine) if isinstance(mine, dict) else {}
        mine[str(task_id)] = detail
        if len(mine) > DETAIL_KEEP:
            newest = sorted(mine, key=lambda key: int((mine[key] or {}).get("read_at") or 0) if isinstance(mine[key], dict) else 0, reverse=True)
            mine = {key: mine[key] for key in newest[:DETAIL_KEEP]}
        holder[connection_id] = mine
        if shape is not None:
            shapes = snapshot.get(SHAPES_FIELD)
            if not isinstance(shapes, dict):
                shapes = {}
                snapshot[SHAPES_FIELD] = shapes
            shapes[connection_id] = shape

    edit(store, store.load_calendar_snapshot, store.save_calendar_snapshot, change)


def with_details(entries, store):
    known = {}
    result = []
    for item in entries:
        connection_id = str(item.get("connection_id") or "")
        if connection_id not in known:
            known[connection_id] = stored_details(store, connection_id)
        detail = known[connection_id].get(str(item.get("id")))
        result.append(dict(item, detail=detail) if isinstance(detail, dict) else item)
    return result


def _browser_headers(page_url):
    page = str(page_url or "")
    parts = urlparse(page)
    headers = {"Referer": page} if page else {}
    if parts.scheme and parts.netloc:
        headers["Origin"] = f"{parts.scheme}://{parts.netloc}"
    return headers


def text_value(text, editor):
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not editor:
        return "\r\n".join(lines)
    return "".join("<p>%s</p>" % (html.escape(line) if line.strip() else "&nbsp;") for line in lines)


def build_payload(form, operation, text=None, target=None):
    pairs = []
    for field in form["fields"]:
        kind = field["type"]
        name = field["name"]
        if kind == "file":
            continue
        if kind in ("checkbox", "radio"):
            if operation == "delete" and kind == "checkbox":
                continue
            if field.get("checked"):
                pairs.append((name, field["value"]))
            continue
        if kind == "textarea" and operation == "text" and name == form.get("text_field"):
            pairs.append((name, text_value(text, form.get("editor"))))
            continue
        pairs.append((name, field["value"]))
    if operation == "delete" and target and target.get("name"):
        pairs.append((target["name"], target["value"]))
    submit = form["operations"].get(operation)
    if submit:
        pairs.append((submit["name"], submit["value"]))
    return pairs


def _clean_name(name):
    text = str(name or "").replace("\\", "/").split("/")[-1]
    text = "".join(char for char in text if char.isprintable()).strip()
    return text[:200] or "file"


def _own_files(detail):
    return [_fold(entry.get("label")) for entry in (detail.get(SUBMISSION) or {}).get("files") or []]


def _same_file(name, label):
    wanted = _fold(name)
    if label == wanted:
        return True
    stem, dot, suffix = wanted.rpartition(".")
    return bool(dot and stem) and label.startswith(stem) and label.endswith("." + suffix)


def _uploaded(before, after, names):
    remaining = Counter(_own_files(before))
    fresh = []
    for label in _own_files(after):
        if remaining[label] > 0:
            remaining[label] -= 1
        else:
            fresh.append(label)
    for name in names:
        match = next((label for label in fresh if _same_file(name, label)), None)
        if match is None:
            return False
        fresh.remove(match)
    return bool(names)


def _shown_text(detail):
    offered = (detail.get("actions") or {}).get("text")
    lines = offered.get("text") if isinstance(offered, dict) else (detail.get(SUBMISSION) or {}).get("text")
    return _fold(" ".join(lines or []))


def _marked(before, after, gone, shown):
    actions = after.get("actions") or {}
    if gone in actions:
        return False
    return shown in actions or _fold(after.get("state_text")) != _fold(before.get("state_text"))


def _verified(operation, before, after, text=None, names=(), target=None):
    if operation == "upload":
        return _uploaded(before, after, names)
    if operation == "text":
        wanted = _fold(text)
        return bool(wanted) and _shown_text(after) == wanted and _shown_text(before) != wanted
    if operation == "confirm":
        return _marked(before, after, "confirm", "undo")
    if operation == "undo":
        return _marked(before, after, "undo", "confirm")
    if operation == "delete":
        label = _fold((target or {}).get("label"))
        value = str((target or {}).get("value") or "")
        remaining = (after.get("actions") or {}).get("delete") or []
        still_listed = any(_fold(entry.get("label")) == label and str(entry.get("value") or "") == value for entry in remaining)
        return bool(label) and label in _own_files(before) and label not in _own_files(after) and not still_listed
    return False


def _matching_target(form, wanted):
    if not isinstance(wanted, dict):
        return None
    label = _fold(wanted.get("label"))
    value = str(wanted.get("value") or "")
    if not label:
        return None
    for target in form.get("targets") or []:
        if _fold(target.get("label")) == label and str(target.get("value") or "") == value:
            return target
    return None


class TaskService:
    def __init__(self, connection):
        self.connection = connection
        self._lock = threading.Lock()
        self._busy = set()

    @property
    def store(self):
        return self.connection.store

    def _school_url(self):
        return self.store.load_config().get("school_url", "")

    def _now(self):
        return int(getattr(self.connection, "clock", time.time)())

    def listed_task(self, task_id):
        stored = school_lists.stored_list(self.store, self.connection.id, school_lists.TASKS_FIELD)
        for item in (stored or {}).get(school_lists.TASKS_FIELD) or []:
            if isinstance(item, dict) and str(item.get("id")) == str(task_id):
                return item
        raise DataError("the task is not listed", message_key=TASK_UNKNOWN_KEY)

    def _task_path(self, task):
        path = path_of(task.get("path") or "").rstrip("/")
        if not DETAIL_PATH.match(path):
            raise DataError("the task has no detail page", message_key=TASK_NO_DETAIL_KEY)
        return path

    def _read(self, task, client=None):
        path = self._task_path(task)
        client = client or self.connection._session()
        response = school_lists.module_answer(client, path, lambda final: final.rstrip("/") == path)
        parsed = parse_task_detail(
            getattr(response, "text", "") or "",
            path,
            str(getattr(response, "url", "") or ""),
            url_host(self._school_url()),
            task.get("title") or "",
        )
        return client, response, parsed

    def _publish(self, task, parsed):
        detail = public_detail(parsed, self._school_url(), self._now())
        remember_detail(self.store, self.connection.id, task.get("id"), detail, dict(shape_of(parsed), read_at=detail["read_at"]))
        return detail

    def detail(self, task_id):
        task = self.listed_task(task_id)
        _client, _response, parsed = self._read(task)
        logger.info("task detail read: %d forms, %d offered actions", len(parsed["forms"]), sum(1 for form in parsed["forms"] if form["operations"]))
        return self._publish(task, parsed)

    def cached_detail(self, task_id):
        detail = stored_details(self.store, self.connection.id).get(str(task_id))
        return detail if isinstance(detail, dict) else None

    def file(self, task_id, kind, index):
        self.listed_task(task_id)
        path = task_file_path(self.cached_detail(task_id), kind, index)
        if not path:
            raise DataError("unknown task file")
        return school_lists.read_school_file(self.connection._session(), path, self._school_url())

    def act(self, task_id, action, form_id, target=None, text=None, files=None, confirmed=False):
        if confirmed is not True:
            return messages.result(False, ACT_UNCONFIRMED_KEY)
        if action not in ACTIONS or not isinstance(form_id, str) or not form_id:
            return messages.result(False, ACT_INVALID_KEY)
        refusal = self._input_refusal(action, text, files or [])
        if refusal is not None:
            return refusal
        task = self.listed_task(task_id)
        key = str(task_id)
        with self._lock:
            if key in self._busy:
                return messages.result(False, ACT_BUSY_KEY)
            self._busy.add(key)
        try:
            return self._act(task, action, form_id, target, text, files or [])
        finally:
            with self._lock:
                self._busy.discard(key)

    @staticmethod
    def _input_refusal(action, text, files):
        if action == "text":
            if not isinstance(text, str) or not text.strip():
                return messages.result(False, ACT_EMPTY_KEY)
            if len(text) > TEXT_MAX_LENGTH:
                return messages.result(False, ACT_TOO_LONG_KEY, {"max": TEXT_MAX_LENGTH})
        if action == "upload":
            if not files:
                return messages.result(False, ACT_EMPTY_KEY)
            if len(files) > MAX_FILES:
                return messages.result(False, ACT_TOO_MANY_KEY, {"max": MAX_FILES})
            sizes = [len(upload.get("content") or b"") for upload in files]
            if max(sizes) > MAX_FILE_BYTES:
                return messages.result(False, ACT_FILE_TOO_LARGE_KEY, {"max": MAX_FILE_BYTES // MEGABYTE})
            if sum(sizes) > MAX_TOTAL_BYTES:
                return messages.result(False, ACT_TOO_LARGE_KEY, {"max": MAX_TOTAL_BYTES // MEGABYTE})
        return None

    def _act(self, task, action, form_id, target, text, files):
        client, response, parsed = self._read(task)
        before = self._publish(task, parsed)
        form = next((entry for entry in parsed["forms"] if entry["id"] == form_id and entry["writable"]), None)
        if form is None or action not in form["operations"]:
            logger.info("task %s refused before sending: the form is no longer offered", action)
            return messages.result(False, ACT_UNAVAILABLE_KEY, outcome=OUTCOME_UNAVAILABLE, detail=before)
        chosen = None
        if action == "delete":
            chosen = _matching_target(form, target)
            if chosen is None:
                logger.info("task delete refused before sending: the chosen file is no longer offered")
                return messages.result(False, ACT_UNAVAILABLE_KEY, outcome=OUTCOME_UNAVAILABLE, detail=before)
        if action == "upload" and len(files) > 1 and not form.get("multiple"):
            return messages.result(False, ACT_ONE_FILE_KEY, detail=before)
        if action == "text" and form.get("max_length") and len(text) > form["max_length"]:
            return messages.result(False, ACT_TOO_LONG_KEY, {"max": form["max_length"]}, detail=before)
        payload = build_payload(form, action, text=text, target=chosen)
        parts = None
        if action == "upload":
            parts = [
                (form["file_field"], (_clean_name(upload.get("filename")), upload.get("content") or b"", upload.get("content_type") or "application/octet-stream"))
                for upload in files
            ]
        headers = _browser_headers(getattr(response, "url", "") or "")
        try:
            sent = client.post_form(form["action"], payload, files=parts, headers=headers, timeout=UPLOAD_TIMEOUT if parts else POST_TIMEOUT)
        except RequestException as error:
            logger.warning("task %s outcome unknown: the request to the school failed (%s)", action, error_kind(error))
            return self._settle(task, action, OUTCOME_UNCERTAIN, before, text, files, chosen)
        try:
            rejected = self._rejection(action, sent)
        except Exception as error:
            logger.warning("task %s answer could not be read: %s", action, error_kind(error))
            rejected = None
        if rejected is not None:
            return self._settle(task, action, OUTCOME_REJECTED, before, text, files, chosen, rejected)
        return self._settle(task, action, None, before, text, files, chosen)

    def _rejection(self, action, sent):
        status = int(getattr(sent, "status_code", 0) or 0)
        redirected = bool(getattr(sent, "history", None) or [])
        answer = getattr(sent, "text", "") or ""
        url = str(getattr(sent, "url", "") or "")
        if server_failure(sent) is not None:
            logger.warning("task %s outcome unknown: the school answered with status %d", action, status)
            return None
        if not redirected and 400 <= status < 500:
            logger.warning("task %s refused by the school with status %d", action, status)
            return form_errors(answer)
        if status in WRITE_OK_STATUSES and login_forms.find_login_form(login_forms.parse_forms(answer, url or "https://school.invalid/")) is not None:
            logger.warning("task %s refused: the school asked for the sign-in", action)
            return []
        errors = form_errors(answer) if status in WRITE_OK_STATUSES and not redirected else []
        if errors:
            logger.warning("task %s refused by the school form at %s", action, path_pattern(url))
            return errors
        return None

    def _settle(self, task, action, outcome, before, text, files, chosen, errors=None):
        try:
            return self._settled(task, action, outcome, before, text, files, chosen, errors)
        except Exception as error:
            logger.warning("task %s outcome unknown: the result could not be checked (%s)", action, error_kind(error))
            return messages.result(False, ACT_UNCERTAIN_KEY, outcome=OUTCOME_UNCERTAIN, detail=before)

    def _settled(self, task, action, outcome, before, text, files, chosen, errors):
        try:
            _client, _response, parsed = self._read(task)
            after = self._publish(task, parsed)
        except Exception as error:
            logger.warning("task %s could not be read again: %s", action, error_kind(error))
            after = None
        names = [_clean_name(upload.get("filename")) for upload in files]
        changed = after is not None and _verified(action, before, after, text, names, chosen)
        if outcome == OUTCOME_REJECTED and not changed:
            return messages.result(
                False,
                ACT_REJECTED_KEY,
                outcome=OUTCOME_REJECTED,
                errors=[squeezed(item, 200) for item in errors or []],
                detail=after or before,
            )
        if outcome is None and changed:
            logger.info("task %s done and seen on the task page", action)
            self._note_done_state(task, action)
            return messages.result(True, ACT_DONE_KEY, outcome=OUTCOME_DONE, detail=after)
        logger.warning("task %s outcome unknown: the task page does not confirm the change", action)
        return messages.result(False, ACT_UNCERTAIN_KEY, outcome=OUTCOME_UNCERTAIN, detail=after or before)

    def _note_done_state(self, task, action):
        if action not in ("confirm", "undo"):
            return
        done = action == "confirm"
        connection_id = self.connection.id
        task_id = str(task.get("id"))

        def change(snapshot):
            holder = snapshot.get(school_lists.TASKS_FIELD)
            listed = holder.get(connection_id) if isinstance(holder, dict) else None
            entries = listed.get(school_lists.TASKS_FIELD) if isinstance(listed, dict) else None
            for item in entries if isinstance(entries, list) else []:
                if isinstance(item, dict) and str(item.get("id")) == task_id:
                    item["done"] = done

        edit(self.store, self.store.load_calendar_snapshot, self.store.save_calendar_snapshot, change)
