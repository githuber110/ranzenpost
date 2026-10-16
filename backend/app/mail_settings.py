import hashlib
import logging
import re
import threading
import time
from collections import OrderedDict
from datetime import timedelta
from urllib.parse import urlsplit

from requests import RequestException

from . import messages

from .failure import failure_cause
from .iserv import mail_web, settings_forms
from .iserv.client import server_failure
from .iserv.errors import DataError, SchoolCalendarRefusedError
from .iserv.forms import find_login_form, parse_forms
from .iserv.html import plain_text
from .iserv.school_calendar import read_calendar
from .mail_service import MailConfirmRequired
from .modules import ADDRESSBOOK
from .pathpattern import path_pattern

logger = logging.getLogger(__name__)

PAGE_CACHE_SECONDS = 5 * 60
DISCOVERY_SECONDS = 10 * 60
WEB_UNKNOWN_KEY = "api.mail.webUnknown"
SETTINGS_UNKNOWN_KEY = "api.mail.settings.unknown"
SETTINGS_REFUSED_KEY = "api.mail.settings.refused"
LOOKUP_PROBE = "ab"
EVENT_UNKNOWN_KEY = "api.mail.event.unknown"
EVENT_TEXT_LIMIT = 800
EVENT_INVALID_KEY = "api.mail.event.invalidRequest"
EVENT_UNCERTAIN_KEY = "api.mail.event.uncertain"
EVENT_BUSY_KEY = "api.mail.event.busy"
EVENT_SAVED_KEY = "api.mail.event.saved"
EVENT_REJECTED_KEY = "api.mail.event.rejected"
EVENT_ACTION_ROOT = "/iserv/calendar"
EVENT_PENDING = "pending"
EVENT_DONE = "done"
EVENT_UNCERTAIN = "uncertain"
EVENT_REFUSED = "refused"
EVENT_REQUEST_LIMIT = 200
REQUEST_ID = re.compile(r"^[0-9A-Za-z-]{16,64}$")
SECRET_WORDS = ("token", "csrf", "nonce")


def event_check(form):
    hidden = sorted(
        "%s=%s" % (entry["name"], entry["value"])
        for entry in form["hidden"]
        if not any(word in entry["name"].lower() for word in SECRET_WORDS)
    )
    names = sorted("%s:%s" % (field["kind"], field["name"]) for field in form["fields"])
    seed = "\n".join([urlsplit(form["action"]).path, ",".join(names), ",".join(hidden), ",".join(sorted(form["submits"]))])
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


class MailWebUnknown(DataError):
    def __init__(self, note="the mail page carries no readable data", message_key=WEB_UNKNOWN_KEY):
        super().__init__(note, message_key=message_key)


class MailWebService:
    def __init__(self, connection, clock=None):
        self.connection = connection
        self.clock = clock or time.time
        self._lock = threading.Lock()
        self._page = (0.0, None)
        self._discovered = (0.0, None)
        self._lookup_params = {}
        self._events_lock = threading.Lock()
        self._event_requests = OrderedDict()

    def _client(self):
        return self.connection.iserv_session()

    def _mail_page(self):
        stamp, html = self._page
        if html is not None and self.clock() - stamp < PAGE_CACHE_SECONDS:
            return html
        response = self._client().fetch_or_raise(mail_web.MAIL_PAGE)
        html = getattr(response, "text", "") or ""
        self._page = (self.clock(), html)
        return html

    def account(self):
        found = mail_web.account(self._mail_page())
        if found is None:
            raise MailWebUnknown()
        return {"account": found}

    def _address_book(self, query):
        offered = getattr(self.connection, "account_modules", None)
        if not callable(offered) or not offered().get(ADDRESSBOOK):
            return []
        try:
            return self.connection.contacts(ADDRESSBOOK).recipients(query)
        except (DataError, RequestException) as error:
            logger.info("school#%s address book not used for the recipients: %s", self.connection.id, failure_cause(error))
            return []

    def recipients(self, query):
        data = mail_web.php_data(self._mail_page())
        paths = mail_web.lookup_paths(data)
        found = []
        failure = None
        if paths:
            try:
                found, remembered = mail_web.lookup(self._client(), paths, query, self._lookup_params)
                self._lookup_params = remembered or {}
            except DataError as error:
                failure = error
        booked = self._address_book(query)
        if failure is not None and not booked:
            raise failure
        known = {entry["address"].lower() for entry in found}
        found = found + [entry for entry in booked if entry["address"].lower() not in known]
        if not paths and not booked:
            return {"recipients": [], "lookup": False}
        return {"recipients": found[:mail_web.LOOKUP_LIMIT], "lookup": True}

    def _discover(self):
        stamp, pages = self._discovered
        if pages is not None and self.clock() - stamp < DISCOVERY_SECONDS:
            return pages
        client = self._client()
        base = str(getattr(client, "base_url", "") or "")
        found = []
        failed = 0
        for candidate in mail_web.candidate_pages(self._mail_page(), base):
            try:
                response = client.fetch(candidate["path"])
            except DataError:
                failed += 1
                continue
            path = mail_web.settings_page(response, candidate["path"])
            if not path or path in [entry["path"] for entry in found]:
                continue
            html = getattr(response, "text", "") or ""
            forms = settings_forms.describe_forms(html, getattr(response, "url", "") or base + path)
            if not forms:
                continue
            title = settings_forms.page_title(html)
            found.append({"path": path, "kind": mail_web.setting_kind(path, title), "title": title, "forms": len(forms), "guessed": candidate["guessed"]})
        pages = {"pages": found, "failed": failed}
        self._discovered = (self.clock(), pages)
        logger.info("school#%s mail settings pages found: %d (%s)", self.connection.id, len(found), ", ".join(path_pattern(entry["path"]) for entry in found) or "none")
        return pages

    def structure(self):
        html = self._mail_page()
        data = mail_web.php_data(html)
        client = self._client()
        base = str(getattr(client, "base_url", "") or "")
        probes = []
        for candidate in mail_web.candidate_pages(html, base):
            try:
                response = client.fetch(candidate["path"])
            except Exception as error:
                probes.append({"path": candidate["path"], "guessed": candidate["guessed"], "verdict": "error %s" % type(error).__name__})
                continue
            path = mail_web.settings_page(response, candidate["path"])
            if not path:
                probes.append({"path": candidate["path"], "guessed": candidate["guessed"], "verdict": "no settings page (HTTP %s)" % getattr(response, "status_code", "-")})
                continue
            forms = settings_forms.describe_forms(getattr(response, "text", "") or "", getattr(response, "url", "") or base + path)
            probes.append({"path": candidate["path"], "guessed": candidate["guessed"], "verdict": "forms %d" % len(forms), "forms": forms})
        lookups = []
        for path in mail_web.lookup_paths(data):
            answers = []
            for param in mail_web.LOOKUP_PARAMS:
                response = client.fetch(path, {param: LOOKUP_PROBE})
                answers.append((param, response))
                if int(getattr(response, "status_code", 0) or 0) == 200:
                    break
            lookups.append({"path": path, "answers": answers})
        event = {"path": "", "found": False, "forms": [], "routes": []}
        try:
            calendar = client.fetch(mail_web.CALENDAR_PAGE)
            calendar_html = getattr(calendar, "text", "") or ""
            event["found"] = bool(mail_web.create_event_path(calendar_html))
            event["routes"] = mail_web.calendar_routes(calendar_html)
            event["path"] = self._create_path()
            forms, _html = self._forms(event["path"])
            event["forms"] = forms
        except Exception as error:
            event["error"] = type(error).__name__
        return {"account": mail_web.account(html), "probes": probes, "lookups": lookups, "event": event}

    def settings(self):
        with self._lock:
            pages = self._discover()
        return {"pages": pages["pages"], "unknown": not pages["pages"] and pages["failed"] > 0}

    def _known_path(self, path):
        with self._lock:
            pages = self._discover()
        for entry in pages["pages"]:
            if entry["path"] == path:
                return entry
        raise DataError("unknown settings page", message_key=SETTINGS_UNKNOWN_KEY)

    def _forms(self, path):
        response = self._client().fetch_or_raise(path)
        html = getattr(response, "text", "") or ""
        return settings_forms.describe_forms(html, getattr(response, "url", "") or path), html

    def settings_page(self, path):
        entry = self._known_path(path)
        forms, html = self._forms(path)
        return dict(entry, title=entry["title"] or settings_forms.page_title(html), forms=[settings_forms.public_form(form) for form in forms])

    def save_settings(self, path, form_index, values, fields=None, confirmed=False):
        if not confirmed:
            raise MailConfirmRequired()
        entry = self._known_path(path)
        before, errors = self._post_form(path, form_index, values, fields)
        after_forms, _after_html = self._forms(path)
        after = next((form for form in after_forms if form["index"] == form_index), None)
        missing = settings_forms.unconfirmed(before, after, values) if after is not None else list(values)
        labels = [self._label(before, name) for name in missing]
        outcome = "refused" if errors else ("saved" if not missing else "not confirmed")
        logger.info("school#%s mail settings %s %s (%s): %d fields, %d not confirmed", self.connection.id, entry["kind"], path_pattern(path), outcome, len(values), len(missing))
        return {
            "ok": not errors,
            "verified": not errors and not missing,
            "errors": errors,
            "unconfirmed": labels,
            "path": path,
            "form": settings_forms.public_form(after) if after is not None else None,
        }

    def _post_form(self, path, form_index, values, fields):
        before_forms, _html = self._forms(path)
        before = next((form for form in before_forms if form["index"] == form_index), None)
        if before is None:
            raise DataError("form not found", message_key=settings_forms.FORM_CHANGED_KEY)
        if fields is not None and sorted(fields) != sorted(field["name"] for field in before["fields"]):
            raise DataError("form changed", message_key=settings_forms.FORM_CHANGED_KEY)
        if before["method"] != "post":
            raise DataError("form does not post", message_key=SETTINGS_REFUSED_KEY)
        data = settings_forms.payload_for(before, values)
        try:
            answer = self._client().post_absolute(before["action"], data)
        except DataError as error:
            logger.warning("school#%s form %s not sent: %s", self.connection.id, path_pattern(path), failure_cause(error))
            raise
        status = int(getattr(answer, "status_code", 0) or 0)
        if status >= 400:
            logger.warning("school#%s form %s refused with HTTP %d", self.connection.id, path_pattern(path), status)
            raise DataError("form refused: %d" % status, message_key=SETTINGS_REFUSED_KEY)
        return before, settings_forms.page_errors(getattr(answer, "text", "") or "")

    def _create_path(self):
        try:
            response = self._client().fetch(mail_web.CALENDAR_PAGE)
        except DataError:
            return mail_web.CREATE_EVENT_FALLBACK
        found = mail_web.create_event_path(getattr(response, "text", "") or "")
        return found or mail_web.CREATE_EVENT_FALLBACK

    def _event_form(self, path):
        forms, _html = self._forms(path)
        chosen = mail_web.event_form_of(forms)
        if chosen is None:
            raise DataError("no event form", message_key=EVENT_UNKNOWN_KEY)
        return chosen

    def event_form(self, folder, uid):
        detail = self.connection.mail().message(folder, uid)
        path = self._create_path()
        form = self._event_form(path)
        text = detail.get("body_text") or plain_text(detail.get("body_html") or "")
        prefill = {}
        title = mail_web.event_title_field(form)
        if title:
            prefill[title] = detail.get("subject") or ""
        description = mail_web.event_description_field(form)
        if description:
            prefill[description] = text.strip()[:EVENT_TEXT_LIMIT]
        return {"path": path, "form": settings_forms.public_form(form), "check": event_check(form), "prefill": prefill, "subject": detail.get("subject") or ""}

    def save_event(self, path, form_index, values, fields=None, confirmed=False, request_id="", check=""):
        if not confirmed:
            raise MailConfirmRequired()
        request_id = request_id if isinstance(request_id, str) else ""
        if not REQUEST_ID.match(request_id):
            raise DataError("event request id missing", message_key=EVENT_INVALID_KEY)
        with self._events_lock:
            record = self._event_requests.get(request_id)
            if record is None:
                self._event_requests[request_id] = {"state": EVENT_PENDING}
                while len(self._event_requests) > EVENT_REQUEST_LIMIT:
                    self._event_requests.popitem(last=False)
        if record is not None:
            return self._event_answer(record)
        try:
            outcome = self._save_event(path, form_index, values, fields, check)
        except BaseException:
            self._settle_event(request_id, None)
            raise
        self._settle_event(request_id, outcome)
        return outcome

    def _settle_event(self, request_id, outcome):
        with self._events_lock:
            if outcome is None or outcome.get("state") == EVENT_REFUSED:
                self._event_requests.pop(request_id, None)
            else:
                self._event_requests[request_id] = {"state": outcome["state"], "event": outcome.get("event")}

    @staticmethod
    def _event_answer(record):
        if record["state"] == EVENT_DONE:
            return messages.result(True, EVENT_SAVED_KEY, state=EVENT_DONE, verified=True, errors=[], event=record.get("event"))
        if record["state"] == EVENT_UNCERTAIN:
            return messages.result(False, EVENT_UNCERTAIN_KEY, state=EVENT_UNCERTAIN, verified=False, errors=[], event=None)
        return messages.result(False, EVENT_BUSY_KEY, state=EVENT_REFUSED, verified=False, errors=[], event=None)

    def _save_event(self, path, form_index, values, fields, check):
        if path != self._create_path():
            raise DataError("unknown event page", message_key=EVENT_UNKNOWN_KEY)
        forms, _html = self._forms(path)
        before = mail_web.event_form_of(forms)
        if before is None or before["index"] != form_index or not urlsplit(before["action"]).path.startswith(EVENT_ACTION_ROOT):
            logger.info("school#%s calendar entry from mail refused: the chosen form is not the event form", self.connection.id)
            raise DataError("not the event form", message_key=EVENT_UNKNOWN_KEY)
        if fields is not None and sorted(fields) != sorted(field["name"] for field in before["fields"]):
            raise DataError("form changed", message_key=settings_forms.FORM_CHANGED_KEY)
        if not check or check != event_check(before):
            logger.info("school#%s calendar entry from mail refused: the event form changed", self.connection.id)
            raise DataError("form changed", message_key=settings_forms.FORM_CHANGED_KEY)
        data = settings_forms.payload_for(before, values)
        try:
            answer = self._client().post_absolute(before["action"], data)
        except RequestException as error:
            logger.warning("school#%s calendar entry from mail outcome unknown: %s", self.connection.id, failure_cause(error))
            return self._event_uncertain()
        status = int(getattr(answer, "status_code", 0) or 0)
        if status >= 400:
            logger.warning("school#%s calendar entry from mail refused with HTTP %d", self.connection.id, status)
            raise DataError("form refused: %d" % status, message_key=SETTINGS_REFUSED_KEY)
        html = getattr(answer, "text", "") or ""
        if find_login_form(parse_forms(html, str(getattr(answer, "url", "") or ""))) is not None:
            logger.warning("school#%s calendar entry from mail outcome unknown: the school asked to sign in again", self.connection.id)
            return self._event_uncertain()
        errors = settings_forms.page_errors(html)
        if errors:
            logger.info("school#%s calendar entry from mail refused by the form: %d errors", self.connection.id, len(errors))
            return messages.result(False, EVENT_REJECTED_KEY, state=EVENT_REFUSED, verified=False, errors=errors, event=None)
        found = self._find_event(before, values, data)
        logger.info("school#%s calendar entry from mail %s", self.connection.id, "found in the calendar" if found else "not found in the calendar")
        if found is None:
            return self._event_uncertain()
        shown = {"title": found["title"], "start": found["start"], "calendar": found["calendar"]}
        return messages.result(True, EVENT_SAVED_KEY, state=EVENT_DONE, verified=True, errors=[], event=shown)

    @staticmethod
    def _event_uncertain():
        return messages.result(False, EVENT_UNCERTAIN_KEY, state=EVENT_UNCERTAIN, verified=False, errors=[], event=None)

    def _find_event(self, form, values, data):
        title = " ".join(str(values.get(mail_web.event_title_field(form) or "", "")).split())
        day = mail_web.event_day(form, values)
        if not title or day is None:
            return None
        time_text = mail_web.event_time(form, data)
        all_day = mail_web.event_all_day(form, data) or not time_text
        calendar = mail_web.event_calendar(form, data)
        try:
            events = read_calendar(self._client(), day - timedelta(days=1), day + timedelta(days=1), server_failure).events
        except (DataError, SchoolCalendarRefusedError, RequestException) as error:
            logger.info("school#%s calendar entry from mail not read back: %s", self.connection.id, failure_cause(error))
            return None
        for event in events:
            if " ".join(event["title"].split()) != title or str(event["start"])[:10] != day.isoformat():
                continue
            if all_day != bool(event.get("all_day")):
                continue
            if not all_day and str(event["start"])[11:16] != time_text:
                continue
            if calendar and event.get("calendar") and " ".join(event["calendar"].split()) != calendar:
                continue
            return event
        return None

    @staticmethod
    def _label(form, name):
        for field in form["fields"]:
            if field["name"] == name:
                return field["label"] or name
        return name
