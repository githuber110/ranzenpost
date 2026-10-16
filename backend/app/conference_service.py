import hashlib
import logging
import re
import threading
import time
from collections import OrderedDict
from urllib.parse import urlencode, urljoin

from requests import RequestException

from . import messages
from .failure import failure_cause
from .iserv.conferences import (
    ARCHIVE_PATH,
    LIST_PATH,
    booking_key,
    change_matches,
    first_time,
    form_signature,
    is_profile_field,
    is_profile_name,
    module_path,
    page_problems,
    page_successes,
    parse_conference_page,
    parse_conferences,
    write_link,
)
from .iserv.dsa import name_words
from .iserv.errors import DataError
from .iserv.forms import browser_headers, find_login_form, parse_forms
from .iserv.pages import path_of, status_of
from .store import edit_config

logger = logging.getLogger(__name__)

TAB_CURRENT = "current"
TAB_ARCHIVE = "archive"
CONFERENCE_UNKNOWN_KEY = "api.conferences.page.unknown"
CONFERENCE_GONE_KEY = "api.conferences.page.gone"
SUBMIT_OK_KEY = "api.conferences.submit.ok"
SUBMIT_OPENED_KEY = "api.conferences.submit.opened"
SUBMIT_ALREADY_KEY = "api.conferences.submit.alreadySent"
SUBMIT_BUSY_KEY = "api.conferences.submit.busy"
SUBMIT_UNCONFIRMED_KEY = "api.conferences.submit.unconfirmed"
SUBMIT_INVALID_REQUEST_KEY = "api.conferences.submit.invalidRequest"
SUBMIT_STALE_KEY = "api.conferences.submit.stale"
SUBMIT_REQUIRED_KEY = "api.conferences.submit.required"
SUBMIT_CHOICE_KEY = "api.conferences.submit.choice"
SUBMIT_UNSUPPORTED_KEY = "api.conferences.submit.unsupported"
SUBMIT_INVALID_KEY = "api.conferences.submit.invalid"
SUBMIT_REJECTED_KEY = "api.conferences.submit.rejected"
SUBMIT_SIGNED_OUT_KEY = "api.conferences.submit.signedOut"
SUBMIT_UNCERTAIN_KEY = "api.conferences.submit.uncertain"
SUBMIT_NO_PROFILE_KEY = "api.conferences.submit.noProfile"
OWN_CHANGE_KEY = "conference_own_change"
OWN_CANCELLATIONS_KEY = "conference_own_cancellations"
OWN_CANCELLATIONS_SECONDS = 14 * 24 * 60 * 60
OWN_CANCELLATIONS_LIMIT = 50
STATE_DONE = "done"
STATE_OPENED = "opened"
STATE_INVALID = "invalid"
STATE_REJECTED = "rejected"
STATE_UNCERTAIN = "uncertain"
STATE_REFUSED = "refused"
STATE_PENDING = "pending"
WRITE_OK_STATUSES = (200, 201, 204, 302, 303)
VALIDATION_STATUSES = (400, 422)
REQUEST_ID = re.compile(r"^[0-9A-Za-z-]{16,64}$")
TOKEN = re.compile(r"^[0-9a-f]{24}$")
TOKEN_LIMIT = 4000
REQUEST_LIMIT = 200
TEXT_LIMIT = 4000
CHECK_LENGTH = 16
SUBMIT_KEY_LENGTH = 12
SUBMIT_KEY = re.compile(r"^[0-9a-f]{12}$")


def form_check(form):
    return hashlib.sha256(form_signature(form).encode("utf-8")).hexdigest()[:CHECK_LENGTH]


def submit_key(submit):
    seed = "".join([submit.get("name") or "", submit.get("value") or "", submit.get("label") or ""])
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:SUBMIT_KEY_LENGTH]


def _default_choice(options):
    for option in options:
        if option["selected"] and not option["disabled"]:
            return option["value"]
    return None


def _enabled(options):
    return [option["value"] for option in options if not option["disabled"]]


def build_payload(form, values, submit):
    values = values if isinstance(values, dict) else {}
    pairs = []
    missing = []
    refused = []
    for field in form["fields"]:
        kind = field["kind"]
        name = field["name"]
        if kind == "hidden":
            pairs.append((name, field["value"]))
            continue
        if field.get("disabled"):
            continue
        given = values.get(field["key"])
        label = field.get("label") or name
        if kind == "radio":
            chosen = given if isinstance(given, str) else _default_choice(field["options"])
            if not chosen:
                if field["required"]:
                    missing.append(label)
                continue
            if chosen not in _enabled(field["options"]):
                refused.append(label)
                continue
            pairs.append((name, chosen))
        elif kind == "select":
            chosen = _select_choice(field, given)
            allowed = _enabled(field["options"])
            if any(value not in allowed for value in chosen):
                refused.append(label)
                continue
            if field["required"] and not any(value for value in chosen):
                missing.append(label)
                continue
            pairs.extend((name, value) for value in chosen)
        elif kind == "checkbox":
            on = bool(given) if isinstance(given, bool) else field["checked"]
            if on:
                pairs.append((name, field["value"]))
            elif field["required"]:
                missing.append(label)
        else:
            text = given if isinstance(given, str) and not field.get("readonly") else field.get("value") or ""
            limit = field.get("maxlength") or TEXT_LIMIT
            text = text[:limit]
            if field["required"] and not text.strip():
                missing.append(label)
                continue
            pairs.append((name, text))
    if submit.get("name"):
        pairs.append((submit["name"], submit.get("value") or ""))
    return pairs, missing, refused


def _select_choice(field, given):
    options = field["options"]
    if field.get("multiple"):
        if isinstance(given, list):
            return [str(value) for value in given if isinstance(value, str)]
        return [option["value"] for option in options if option["selected"] and not option["disabled"]]
    if isinstance(given, str):
        return [given]
    chosen = _default_choice(options)
    if chosen is not None:
        return [chosen]
    allowed = _enabled(options)
    return allowed[:1]


class ConferenceService:
    def __init__(self, connection, clock=time.time):
        self.connection = connection
        self.clock = clock
        self._lock = threading.Lock()
        self._pages = OrderedDict()
        self._busy = set()
        self._requests = OrderedDict()

    def forget(self):
        with self._lock:
            self._pages = OrderedDict()
            self._requests = OrderedDict()

    def token(self, path):
        seed = "%s|%s" % (self.connection.id, path)
        token = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
        with self._lock:
            self._pages.pop(token, None)
            self._pages[token] = path
            while len(self._pages) > TOKEN_LIMIT:
                self._pages.popitem(last=False)
        return token

    def _known(self, token):
        with self._lock:
            return self._pages.get(token)

    def _path(self, token):
        token = str(token or "")
        if not TOKEN.match(token):
            raise DataError("invalid conference page", message_key=CONFERENCE_UNKNOWN_KEY)
        path = self._known(token)
        if path is None:
            for tab in (TAB_CURRENT, TAB_ARCHIVE):
                self.conferences(tab)
                path = self._known(token)
                if path is not None:
                    break
        if path is None:
            logger.warning("conference page refused: it was not seen in a conference page of this school")
            raise DataError("the conference page is not listed", message_key=CONFERENCE_UNKNOWN_KEY)
        return path

    def conferences(self, tab=TAB_CURRENT):
        path = ARCHIVE_PATH if tab == TAB_ARCHIVE else LIST_PATH
        client = self.connection._session()
        try:
            response = client.fetch_or_raise(path)
        except DataError:
            return {"error": "unavailable", "items": []}
        parsed = parse_conferences(response.text, response.url)
        items = []
        for item in parsed.get("items") or []:
            paths = item.get("paths") or []
            items.append({
                "cells": item.get("cells") or [],
                "headers": item.get("headers") or [],
                "page": self.token(paths[0]) if paths else "",
            })
        result = {key: value for key, value in parsed.items() if key != "items"}
        result["items"] = items
        return result

    def page(self, token):
        path = self._path(token)
        if write_link(path):
            logger.warning("conference page refused: its address names a change, it is never opened without a confirmation")
            raise DataError("the conference page names a change", message_key=CONFERENCE_UNKNOWN_KEY)
        client = self.connection._session()
        response = client.fetch_or_raise(path)
        return self._public_page(path, response.text, response.url)

    @staticmethod
    def _landing_path(url):
        landed = module_path(str(url or ""), str(url or ""))
        if landed is None:
            raise DataError("the conference page moved out of the module", message_key=CONFERENCE_GONE_KEY)
        return landed

    def _public_page(self, path, html, url, model=None):
        landed = self._landing_path(url) if url else path
        model = model if model is not None else parse_conference_page(html, url)
        return self._publish(landed, model)

    def _known_profiles(self):
        reader = getattr(self.connection, "stored_children", None)
        try:
            listed = reader() if callable(reader) else []
        except Exception:
            listed = []
        known = []
        for child in listed or []:
            words = name_words(child.get("name")) if isinstance(child, dict) else frozenset()
            if words and child.get("child_id"):
                known.append((str(child["child_id"]), words))
        return known

    @staticmethod
    def _names_profile(field, known):
        if field["kind"] not in ("select", "radio"):
            return False
        full = [words for _child_id, words in known if len(words) > 1]
        return any(name_words(option["label"]) in full for option in field["options"])

    def _authorise(self, model):
        known = self._known_profiles()
        known_ids = {child_id for child_id, _words in known}
        for form in model["forms"]:
            for field in form["fields"]:
                if field["kind"] == "hidden" and is_profile_name(field["name"]) and str(field.get("value") or "").strip():
                    if str(field["value"]).strip() not in known_ids:
                        form["profiles_missing"] = True
                        logger.info("conference form: a profile id of the school page matches no known profile of this account")
                    continue
                if not (is_profile_field(field) or self._names_profile(field, known)):
                    continue
                kept = []
                withheld = 0
                matched = 0
                for option in field["options"]:
                    if not str(option["value"]).strip():
                        kept.append(option)
                        continue
                    words = name_words(option["label"])
                    owners = {child_id for child_id, child_words in known if words and (words <= child_words or child_words <= words)}
                    if len(owners) == 1:
                        kept.append(option)
                        matched += 1
                    else:
                        withheld += 1
                field["options"] = kept
                field["profile"] = True
                field["withheld"] = withheld
                field["profiles_missing"] = matched == 0
                if withheld:
                    logger.info("conference form: %d choices withheld, they match no known profile of this account", withheld)
        return model

    @staticmethod
    def _profile_missing(form):
        return bool(form.get("profiles_missing")) or any(field.get("profiles_missing") for field in form["fields"])

    def _publish(self, path, model):
        model = self._authorise(model)
        blocks = []
        for block in model["blocks"]:
            kind = block["kind"]
            if kind == "links":
                blocks.append({"kind": kind, "links": [self._public_link(link) for link in block["links"]]})
            elif kind == "table":
                rows = [
                    {"cells": row["cells"], "links": [self._public_link(link) for link in row["links"]], "forms": row["forms"]}
                    for row in block["rows"]
                ]
                blocks.append(dict(block, rows=rows))
            else:
                blocks.append(dict(block))
        return {
            "page": self.token(path),
            "title": model["title"],
            "blocks": blocks,
            "forms": [self._public_form(form) for form in model["forms"]],
            "notices": list(model["notices"]),
        }

    def _public_link(self, link):
        return {"label": link["label"], "page": self.token(link["path"])}

    @staticmethod
    def _public_form(form):
        fields = []
        for field in form["fields"]:
            if field["kind"] == "hidden":
                continue
            fields.append(dict(field))
        return {
            "id": form["index"],
            "check": form_check(form),
            "method": form["method"],
            "title": form["title"],
            "fields": fields,
            "submits": [
                {"id": submit_key(submit), "label": submit["label"], "destructive": bool(submit["destructive"])}
                for submit in form["submits"]
            ],
            "errors": list(form["errors"]),
            "row": list(form.get("row") or []),
            "profiles_missing": bool(form.get("profiles_missing")),
            "unsupported": bool(form["unsupported"]),
            "destructive": bool(form["destructive"]),
            "writes": bool(form.get("writes")),
        }

    def submit(self, token, form_id, check, submit_id, values, request_id="", confirmed=False):
        request_id = request_id if isinstance(request_id, str) else ""
        reserved = False
        if request_id and REQUEST_ID.match(request_id):
            with self._lock:
                record = self._requests.get(request_id)
                if record is None:
                    self._requests[request_id] = {"page": token, "state": STATE_PENDING}
                    reserved = True
            if record is not None:
                return self._request_answer(record, token)
        try:
            return self._submit(token, form_id, check, submit_id, values, request_id, confirmed)
        finally:
            if reserved:
                with self._lock:
                    record = self._requests.get(request_id)
                    if record is not None and record["state"] == STATE_PENDING:
                        self._requests.pop(request_id, None)

    def _submit(self, token, form_id, check, submit_id, values, request_id, confirmed):
        path = self._path(token)
        client = self.connection._session()
        response = client.fetch_or_raise(path)
        model = self._authorise(parse_conference_page(response.text, response.url))
        form = self._chosen_form(model, form_id, check)
        if form is None:
            logger.info("conference form refused before sending: the form changed on the school page")
            return messages.result(False, SUBMIT_STALE_KEY, state=STATE_REFUSED, page=self._public_page(path, response.text, response.url, model))
        if form["unsupported"]:
            return messages.result(False, SUBMIT_UNSUPPORTED_KEY, state=STATE_REFUSED)
        if self._profile_missing(form):
            logger.info("conference form refused before sending: no choice matches a known profile of this account")
            return messages.result(False, SUBMIT_NO_PROFILE_KEY, state=STATE_REFUSED)
        submit = self._chosen_submit(form, submit_id)
        if submit is None:
            return messages.result(False, SUBMIT_INVALID_REQUEST_KEY, state=STATE_REFUSED)
        pairs, missing, refused = build_payload(form, values, submit)
        if refused:
            logger.info("conference form refused before sending: %d choices are not offered", len(refused))
            return messages.result(
                False, SUBMIT_CHOICE_KEY, {"fields": ", ".join(refused)}, state=STATE_REFUSED,
                page=self._public_page(path, response.text, response.url, model),
            )
        if missing:
            return messages.result(False, SUBMIT_REQUIRED_KEY, {"fields": ", ".join(missing)}, state=STATE_INVALID, missing=missing)
        if form["method"] == "get" and not form.get("writes"):
            return self._open(client, path, form, pairs, response.url)
        if confirmed is not True:
            return messages.result(False, SUBMIT_UNCONFIRMED_KEY, state=STATE_REFUSED)
        if not REQUEST_ID.match(request_id):
            return messages.result(False, SUBMIT_INVALID_REQUEST_KEY, state=STATE_REFUSED)
        with self._lock:
            if token in self._busy:
                return messages.result(False, SUBMIT_BUSY_KEY, state=STATE_REFUSED)
            self._busy.add(token)
        try:
            return self._send(client, path, token, request_id, form, pairs, response, model)
        finally:
            with self._lock:
                self._busy.discard(token)

    @staticmethod
    def _chosen_form(model, form_id, check):
        try:
            index = int(form_id)
        except (TypeError, ValueError):
            return None
        forms = model["forms"]
        if index < 0 or index >= len(forms):
            return None
        form = forms[index]
        return form if form_check(form) == str(check or "") else None

    @staticmethod
    def _chosen_submit(form, submit_id):
        submits = form["submits"]
        if isinstance(submit_id, str) and SUBMIT_KEY.match(submit_id):
            return next((submit for submit in submits if submit_key(submit) == submit_id), None)
        if len(submits) == 1 and submit_id in (0, "0", None, ""):
            return submits[0]
        return None

    def _open(self, client, path, form, pairs, page_url):
        target = urljoin(page_url, form["action"].split("?", 1)[0])
        query = urlencode([(name, value) for name, value in pairs])
        opened = module_path(target + ("?" + query if query else ""), page_url)
        if opened is None:
            return messages.result(False, SUBMIT_INVALID_REQUEST_KEY, state=STATE_REFUSED)
        response = client.fetch_or_raise(opened)
        return messages.result(True, SUBMIT_OPENED_KEY, state=STATE_OPENED, page=self._public_page(opened, response.text, response.url))

    @staticmethod
    def _request_answer(record, token):
        if record["page"] != token:
            return messages.result(False, SUBMIT_INVALID_REQUEST_KEY, state=STATE_REFUSED)
        if record["state"] == STATE_DONE:
            return messages.result(True, SUBMIT_ALREADY_KEY, state=STATE_DONE)
        if record["state"] == STATE_UNCERTAIN:
            return messages.result(False, SUBMIT_UNCERTAIN_KEY, state=STATE_UNCERTAIN)
        return messages.result(False, SUBMIT_BUSY_KEY, state=STATE_REFUSED)

    def _record(self, request_id, token, state):
        with self._lock:
            self._requests.pop(request_id, None)
            self._requests[request_id] = {"page": token, "state": state}
            while len(self._requests) > REQUEST_LIMIT:
                self._requests.popitem(last=False)

    def _note_own_change(self, form):
        store = getattr(self.connection, "store", None)
        if store is None or not callable(getattr(store, "load_config", None)):
            return
        stamp = int(self.clock())
        row = list(form.get("row") or [])
        key = booking_key(row) if row and first_time(row) else ""

        def change(config):
            if not key:
                config[OWN_CHANGE_KEY] = stamp
                return
            kept = [
                entry for entry in config.get(OWN_CANCELLATIONS_KEY) or []
                if isinstance(entry, dict) and stamp - int(entry.get("at") or 0) < OWN_CANCELLATIONS_SECONDS
            ]
            config[OWN_CANCELLATIONS_KEY] = (kept + [{"key": key, "at": stamp}])[-OWN_CANCELLATIONS_LIMIT:]

        try:
            edit_config(store, change)
        except Exception as error:
            logger.warning("conference own change could not be noted: %s", failure_cause(error))

    @staticmethod
    def _sender(client, form, pairs, page_url):
        target = urljoin(page_url, form["action"])
        if form["method"] != "get":
            return target, lambda: client.post_absolute(target, data=pairs, headers=browser_headers(page_url))
        query = urlencode(pairs)
        opened = module_path(target.split("?", 1)[0] + ("?" + query if query else ""), page_url)
        if opened is None:
            return target, None

        def send():
            forget = getattr(client, "forget_kept", None)
            if callable(forget):
                forget()
            live = getattr(client, "fetch_live", None)
            return (live if callable(live) else client.fetch)(opened)

        return target, send

    def _send(self, client, path, token, request_id, form, pairs, response, model):
        known_problems = set(page_problems(model))
        target, send = self._sender(client, form, pairs, response.url)
        if send is None:
            return messages.result(False, SUBMIT_INVALID_REQUEST_KEY, state=STATE_REFUSED)
        self._record(request_id, token, STATE_PENDING)
        self._note_own_change(form)
        try:
            sent = send()
        except RequestException as error:
            logger.warning("conference form outcome unknown: the request to the school failed: %s", failure_cause(error))
            self._record(request_id, token, STATE_UNCERTAIN)
            return self._answer(False, SUBMIT_UNCERTAIN_KEY, STATE_UNCERTAIN, path, client, {"post_status": 0, "post_redirects": 0})
        status = status_of(sent)
        redirected = bool(getattr(sent, "history", None) or [])
        answer_html = getattr(sent, "text", "") or ""
        answer_url = str(getattr(sent, "url", "") or target)
        answer = parse_conference_page(answer_html, answer_url)
        diagnosis = {
            "post_status": status,
            "post_path": path_of(answer_url),
            "post_redirects": len(getattr(sent, "history", None) or []),
            "response_notices": [notice["text"] for notice in answer["notices"]][:5],
        }
        if find_login_form(parse_forms(answer_html, answer_url)) is not None:
            logger.warning("conference form outcome unknown: the school asked to sign in again")
            self._record(request_id, token, STATE_UNCERTAIN)
            return self._answer(False, SUBMIT_SIGNED_OUT_KEY, STATE_UNCERTAIN, path, client, diagnosis)
        errors = [text for text in page_problems(answer) if text not in known_problems]
        successes = page_successes(answer)
        if errors and successes:
            logger.warning("conference form outcome unknown: the school named %d problems next to a success", len(errors))
            self._record(request_id, token, STATE_UNCERTAIN)
            return self._answer(False, SUBMIT_UNCERTAIN_KEY, STATE_UNCERTAIN, path, client, diagnosis)
        if errors and (status in WRITE_OK_STATUSES or status in VALIDATION_STATUSES):
            logger.info("conference form not accepted: the school named %d problems", len(errors))
            self._forget_request(request_id)
            shown = (module_path(answer_url, answer_url) or path) if redirected else path
            return messages.result(
                False, SUBMIT_INVALID_KEY, state=STATE_INVALID, errors=errors, diagnosis=diagnosis,
                page=self._publish(shown, answer),
            )
        if not redirected and 400 <= status < 500:
            logger.warning("conference form refused by the school with status %d", status)
            self._forget_request(request_id)
            return self._answer(False, SUBMIT_REJECTED_KEY, STATE_REJECTED, path, client, diagnosis, {"status": status})
        if status not in WRITE_OK_STATUSES:
            logger.warning("conference form outcome unknown: the school answered with status %d", status)
            self._record(request_id, token, STATE_UNCERTAIN)
            return self._answer(False, SUBMIT_UNCERTAIN_KEY, STATE_UNCERTAIN, path, client, diagnosis)
        reread = self._reread(client, path)
        matched = reread is not None and change_matches(form, pairs, model, reread[1])
        if successes or matched:
            logger.info("conference form sent and confirmed by %s", "a school notice" if successes else "the page read again")
            self._record(request_id, token, STATE_DONE)
            page = self._publish(reread[0], reread[1]) if reread is not None else None
            return messages.result(True, SUBMIT_OK_KEY, state=STATE_DONE, notices=successes, page=page, diagnosis=diagnosis)
        opened = self._opened_instead(form, reread, answer, answer_url, path)
        if opened is not None:
            logger.info("conference link opened a page with its own form, nothing changed on the page read again")
            self._forget_request(request_id)
            return messages.result(True, SUBMIT_OPENED_KEY, state=STATE_OPENED, page=self._publish(opened, answer), diagnosis=diagnosis)
        logger.warning("conference form outcome unknown: the page read again shows no change that matches the sent form")
        self._record(request_id, token, STATE_UNCERTAIN)
        page = self._publish(reread[0], reread[1]) if reread is not None else None
        return messages.result(False, SUBMIT_UNCERTAIN_KEY, state=STATE_UNCERTAIN, page=page, diagnosis=diagnosis)

    @staticmethod
    def _opened_instead(form, reread, answer, answer_url, path):
        if form["method"] != "get" or reread is None:
            return None
        landed = module_path(answer_url, answer_url)
        if landed is None or landed.split("?", 1)[0] == path.split("?", 1)[0]:
            return None
        if not any(other["method"] == "post" for other in answer["forms"]):
            return None
        return landed

    def _forget_request(self, request_id):
        with self._lock:
            self._requests.pop(request_id, None)

    def _reread(self, client, path):
        try:
            response = client.fetch(path)
        except Exception as error:
            logger.warning("conference page could not be read again: %s", failure_cause(error))
            return None
        if status_of(response) != 200:
            logger.warning("conference page could not be read again: status %d", status_of(response))
            return None
        landed = module_path(str(getattr(response, "url", "") or ""), str(getattr(response, "url", "") or ""))
        if landed is None:
            return None
        return path, parse_conference_page(response.text, response.url)

    def _answer(self, ok, key, state, path, client, diagnosis, variables=None):
        reread = self._reread(client, path)
        extra = {"state": state, "diagnosis": diagnosis}
        if reread is not None:
            extra["page"] = self._publish(reread[0], reread[1])
        return messages.result(ok, key, variables, **extra)
