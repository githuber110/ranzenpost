import csv
import io
import logging
import threading
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from requests import RequestException

from . import messages
from .identifiers import UNKNOWN_CHILD_KEY
from .iserv.dsa import name_words
from .iserv.errors import DataError
from .iserv.older_absence_form import (
    ERROR_CHOICE,
    ERROR_DATE,
    ERROR_PROFILE,
    ERROR_RANGE,
    ERROR_REQUIRED,
    ERROR_TEXT,
    ERROR_TIME,
    OlderFormError,
    answer_errors,
    attachment_entries,
    attachment_key,
    change_log,
    delete_target,
    export_path,
    create_path,
    form_pairs,
    form_schema,
    form_values,
    offered_profiles,
    parse_confirm_form,
    parse_create_form,
    structure_text,
    upload_form,
    upload_link,
)
from .iserv.older_absences import DELETE_SEGMENTS as DELETE_WORDS
from .iserv.older_absences import LIST_PATH, ROLE_NAME, OlderAbsenceRow, header_role
from .iserv.forms import browser_headers
from .pageshape import code_text
from .pathpattern import placeholders
from .school_lists import read_school_file
from .store import edit_slot

logger = logging.getLogger(__name__)

PENDING_SLOT = "older_absence_pending"
PENDING_DAYS = 7
PENDING_STATUS = "unconfirmed"
NO_FORM_KEY = "api.absence.older.noForm"
UNSUPPORTED_KEY = "api.absence.older.unsupported"
NO_PROFILE_KEY = "api.absence.older.noProfile"
BUSY_KEY = "api.absence.older.busy"
REJECTED_KEY = "api.absence.older.rejected"
SENT_KEY = "api.absence.older.sent"
UNCERTAIN_KEY = "api.absence.older.uncertain"
PENDING_KEY = "api.absence.older.pending"
LOCKED_KEY = "api.absence.older.locked"
WITHDRAW_UNCERTAIN_KEY = "api.absence.older.withdrawUncertain"
ATTACH_UNSUPPORTED_KEY = "api.absence.older.attachUnsupported"
ATTACHED_KEY = "api.absence.older.attached"
ATTACH_UNCERTAIN_KEY = "api.absence.older.attachUncertain"
ATTACH_STATUS_KEY = "api.absence.older.attachStatus"
ATTACHMENT_REMOVED_KEY = "api.absence.older.attachmentRemoved"
ATTACHMENT_KEPT_KEY = "api.absence.older.attachmentKept"
ATTACHMENT_LOCKED_KEY = "api.absence.older.attachmentLocked"
EXPORT_KEY = "api.absence.older.exportUnreadable"
EXPORT_EMPTY_KEY = "api.absence.older.exportEmpty"
ALREADY_SENT_KEY = "api.absence.older.alreadySent"
FILES_NOT_TAKEN_KEY = "api.absence.older.filesNotTaken"
EXPORT_NAME = "absences.csv"
GONE_KEY = "api.absence.upstream.gone"
WITHDRAWN_KEY = "api.absence.withdrawn"
SUBMIT_STATUS_KEY = "api.absence.upstream.statusSubmit"
WITHDRAW_STATUS_KEY = "api.absence.upstream.statusWithdraw"
FORM_ERROR_KEYS = {
    ERROR_PROFILE: "api.absence.error.student",
    ERROR_DATE: "api.absence.error.date",
    ERROR_RANGE: "api.absence.error.range",
    ERROR_TIME: "api.absence.older.error.time",
    ERROR_REQUIRED: "api.absence.older.error.required",
    ERROR_CHOICE: "api.absence.older.error.choice",
    ERROR_TEXT: "api.absence.older.error.text",
}
RECENT_MINUTES = 10
ENTRY_PREFIX = "older:"
ID_LIMIT = 64


def _shape(name):
    return code_text(placeholders(name))


def _status(answer):
    return int(getattr(answer, "status_code", 0) or 0)


def _refused(answer):
    return answer is not None and 400 <= _status(answer) < 500 and not getattr(answer, "history", None)


def _own_action(form, page_url):
    action = urlsplit(form.action)
    page = urlsplit(str(page_url or ""))
    return action.netloc.lower() == page.netloc.lower() and action.path.startswith(LIST_PATH)


def _same_child_rows(rows, child, sent):
    wanted = name_words(child.get("name"))
    return sum(
        1 for row in rows
        if wanted and name_words(row.name) == wanted
        and row.from_date == sent["from_date"] and row.till_date == sent["till_date"]
    )


def _confirm_for(form, row):
    path = urlsplit(form.action).path
    parts = {part.casefold() for part in path.split("/") if part}
    return path == row.delete_path or (row.entry_id in parts and bool(parts & DELETE_WORDS))


def _sent_before(record, cutoff):
    try:
        return datetime.fromisoformat(str(record.get("sent_at") or "")) < cutoff
    except ValueError:
        return True


class OlderAbsenceActions:
    def __init__(self, absences):
        self.absences = absences
        self.connection = absences.connection
        self._busy = threading.Lock()

    def _create_form(self, client, page, children):
        path = create_path(getattr(page, "text", "") or "", str(getattr(page, "url", "") or ""))
        if not path:
            raise DataError("older absence create page not linked", message_key=NO_FORM_KEY)
        answer = client.fetch_or_raise(path)
        form = parse_create_form(getattr(answer, "text", "") or "", str(getattr(answer, "url", "") or ""), children)
        if form is None or not _own_action(form, getattr(answer, "url", "")):
            raise DataError("older absence create form not readable", message_key=NO_FORM_KEY)
        logger.info("school#%s older absence form: %s", self.connection.id, structure_text(form, _shape))
        return form, str(getattr(answer, "url", "") or "")

    def form(self):
        client = self.connection._session()
        _listed, page = self.absences.older_list(client)
        children = self.absences._known_children()
        form, _url = self._create_form(client, page, children)
        if form.unsupported:
            logger.info("school#%s older absence form: %d required fields cannot be filled", self.connection.id, len(form.unsupported))
            return messages.result(False, UNSUPPORTED_KEY)
        schema = form_schema(form, children)
        if not schema["profiles"]:
            logger.info("school#%s older absence form: no profile option matches, options %d", self.connection.id, form.profile_options)
            return messages.result(False, NO_PROFILE_KEY)
        return {"ok": True, "form": schema}

    def report(self, payload, attachments=None):
        if not self._busy.acquire(blocking=False):
            return messages.result(False, BUSY_KEY)
        try:
            return self._report(payload, attachments or [])
        finally:
            self._busy.release()

    def _recently_sent(self, child_id, sent):
        cutoff = datetime.now() - timedelta(minutes=RECENT_MINUTES)
        wanted = (child_id, sent["from_date"], sent["till_date"])
        for record in self.connection.store.load_older_absence_pending().values():
            if isinstance(record, dict) and (record.get("student_id"), record.get("from_date"), record.get("till_date")) == wanted:
                if not _sent_before(record, cutoff):
                    return True
        return False

    def _files(self, form, attachments):
        if not attachments:
            if form.files is not None and form.files.required:
                raise OlderFormError(ERROR_REQUIRED, "files")
            return None
        if form.files is None or (len(attachments) > 1 and not form.files.multiple):
            return False
        return [(form.files.name, (item["filename"], item["content"], item.get("content_type") or "application/octet-stream")) for item in attachments]

    def _report(self, payload, attachments):
        client = self.connection._session()
        listed, page = self.absences.older_list(client)
        children = self.absences._known_children()
        form, form_url = self._create_form(client, page, children)
        if form.unsupported:
            return messages.result(False, UNSUPPORTED_KEY)
        child_id = str(payload.get("student_id") or "")
        offered = offered_profiles(form, children)
        if child_id not in offered:
            return messages.result(False, UNKNOWN_CHILD_KEY)
        try:
            values, sent = form_values(form, payload, child_id, offered)
            files = self._files(form, attachments)
        except OlderFormError as error:
            return messages.result(False, FORM_ERROR_KEYS[error.reason], field=error.field_key)
        if files is False:
            return messages.result(False, FILES_NOT_TAKEN_KEY)
        child = next(child for child in children if str(child.get("child_id")) == child_id)
        before = _same_child_rows(listed.rows, child, sent)
        if payload.get("send_again") is not True and (before or self._recently_sent(child_id, sent)):
            logger.info("school#%s older absence report held back: the same profile and days were reported before", self.connection.id)
            return messages.result(False, ALREADY_SENT_KEY, already_sent=True)
        answer = self._send(client, form, form_pairs(form, values), form_url, "report", files)
        if self._listed_more(client, child, sent, before):
            return messages.result(True, SENT_KEY)
        if answer is not None:
            present, fields, general = answer_errors(getattr(answer, "text", "") or "", form)
            if present and (fields or general):
                logger.info("school#%s older absence report rejected: field errors %d, form errors %d", self.connection.id, len(fields), len(general))
                return messages.result(False, REJECTED_KEY, field_errors=fields, errors=general)
            if _refused(answer):
                logger.warning("school#%s older absence report refused with status %d", self.connection.id, _status(answer))
                return messages.result(False, SUBMIT_STATUS_KEY, {"status": _status(answer)})
        logger.warning("school#%s older absence report sent but not found in the list", self.connection.id)
        self._remember(child_id, sent)
        return messages.result(False, UNCERTAIN_KEY, uncertain=True)

    def _send(self, client, form, pairs, page_url, what, files=None):
        try:
            if files:
                return client.post_form(form.action, data=pairs, files=files, headers=browser_headers(page_url))
            if form.method == "get":
                return client.fetch_live(urlsplit(form.action).path, params=pairs)
            return client.post_absolute(form.action, data=pairs, headers=browser_headers(page_url))
        except (RequestException, DataError) as error:
            logger.warning("school#%s older absence %s outcome unknown: %s", self.connection.id, what, type(error).__name__)
            return None

    def _listed_more(self, client, child, sent, before):
        try:
            after, _page = self.absences.older_list(client)
        except (DataError, RequestException) as error:
            logger.warning("school#%s older absence list not read after sending: %s", self.connection.id, type(error).__name__)
            return False
        return _same_child_rows(after.rows, child, sent) > before

    def _remember(self, child_id, sent):
        sent_at = datetime.now().replace(microsecond=0).isoformat()
        record = dict(sent, student_id=child_id, sent_at=sent_at)
        key = "%s:%s:%s:%s" % (child_id, sent["from_date"], sent["till_date"], sent_at)
        edit_slot(self.connection.store, PENDING_SLOT, lambda slot: slot.update({key: record}))

    def pending_entries(self, entries, entry_of):
        listed = {(entry.get("student_id"), entry.get("from_date"), entry.get("till_date")) for entry in entries}
        cutoff = datetime.now() - timedelta(days=PENDING_DAYS)
        kept = {}

        def change(slot):
            for key in list(slot):
                record = slot[key]
                if not isinstance(record, dict) or _sent_before(record, cutoff):
                    slot.pop(key)
                elif (record.get("student_id"), record.get("from_date"), record.get("till_date")) in listed:
                    slot.pop(key)
                else:
                    kept[key] = record

        edit_slot(self.connection.store, PENDING_SLOT, change)
        shown = []
        for key, record in kept.items():
            row = OlderAbsenceRow(
                name="", from_date=str(record.get("from_date") or ""), till_date=str(record.get("till_date") or ""),
                from_time=str(record.get("from_time") or ""), till_time=str(record.get("till_time") or ""),
                status=PENDING_STATUS, created=str(record.get("sent_at") or "")[:10],
            )
            entry = entry_of(row, str(record.get("student_id") or ""), "pending:%s" % key)
            entry.update(locked_reason=messages.text(PENDING_KEY), locked_reason_key=PENDING_KEY, unconfirmed=True)
            shown.append(entry)
        return shown

    def withdraw(self, entry_id):
        if not self._busy.acquire(blocking=False):
            return messages.result(False, BUSY_KEY)
        try:
            return self._withdraw(entry_id)
        finally:
            self._busy.release()

    def _owned_row(self, client, entry_id, invalid_key):
        wanted = str(entry_id or "")
        wanted = wanted[len(ENTRY_PREFIX):] if wanted.startswith(ENTRY_PREFIX) else ""
        if not wanted.isdigit() or len(wanted) > ID_LIMIT:
            return None, messages.result(False, invalid_key)
        listed, _page = self.absences.older_list(client)
        row = next((row for row in listed.rows if row.entry_id == wanted), None)
        if row is None:
            return None, messages.result(False, GONE_KEY)
        if not self.absences.owned_rows([row]):
            return None, messages.result(False, UNKNOWN_CHILD_KEY)
        return row, None

    def _withdraw(self, entry_id):
        client = self.connection._session()
        row, refused = self._owned_row(client, entry_id, LOCKED_KEY)
        if refused is not None:
            return refused
        wanted = row.entry_id
        if not row.delete_path:
            return messages.result(False, LOCKED_KEY)
        forget = getattr(client, "forget_kept", None)
        if callable(forget):
            forget()
        try:
            page = client.fetch_or_raise(row.delete_path)
        except DataError as error:
            logger.warning("school#%s older absence delete page not readable: %s", self.connection.id, type(error).__name__)
            return self._gone_after_link(client, wanted)
        form = parse_confirm_form(getattr(page, "text", "") or "", str(getattr(page, "url", "") or ""))
        if form is None or not _own_action(form, getattr(page, "url", "")) or not _confirm_for(form, row):
            logger.info("school#%s older absence withdraw: no confirm form for this entry", self.connection.id)
            return self._gone_after_link(client, wanted)
        logger.info("school#%s older absence confirm form: %s", self.connection.id, structure_text(form, _shape))
        answer = self._send(client, form, form_pairs(form), str(getattr(page, "url", "") or ""), "withdraw")
        if _refused(answer):
            logger.warning("school#%s older absence withdraw refused with status %d", self.connection.id, _status(answer))
            return messages.result(False, WITHDRAW_STATUS_KEY, {"status": _status(answer)})
        try:
            after, _page = self.absences.older_list(client)
        except (DataError, RequestException) as error:
            logger.warning("school#%s older absence list not read after withdrawing: %s", self.connection.id, type(error).__name__)
            return messages.result(False, WITHDRAW_UNCERTAIN_KEY)
        if any(other.entry_id == wanted for other in after.rows):
            logger.warning("school#%s older absence entry still listed after withdrawing", self.connection.id)
            return messages.result(False, WITHDRAW_UNCERTAIN_KEY)
        return messages.result(True, WITHDRAWN_KEY)

    def _gone_after_link(self, client, wanted):
        try:
            after, _page = self.absences.older_list(client)
        except (DataError, RequestException) as error:
            logger.warning("school#%s older absence list not read after the delete link: %s", self.connection.id, type(error).__name__)
            return messages.result(False, WITHDRAW_UNCERTAIN_KEY)
        if any(other.entry_id == wanted for other in after.rows):
            return messages.result(False, LOCKED_KEY)
        logger.info("school#%s older absence entry gone after opening its delete link", self.connection.id)
        return messages.result(True, WITHDRAWN_KEY)

    def _upload_target(self, client, page, entry_id):
        form, field = upload_form(getattr(page, "text", "") or "", str(getattr(page, "url", "") or ""), entry_id)
        url = str(getattr(page, "url", "") or "")
        if form is None:
            path = upload_link(getattr(page, "text", "") or "", url, entry_id)
            if not path:
                return None
            answer = client.fetch_or_raise(path)
            url = str(getattr(answer, "url", "") or "")
            form, field = upload_form(getattr(answer, "text", "") or "", url, entry_id)
        if form is None or not _own_action(form, url):
            return None
        return form, field, url

    def _detail_links(self, client, row):
        page = client.fetch_or_raise(row.detail_path)
        return page, attachment_entries(getattr(page, "text", "") or "", str(getattr(page, "url", "") or ""))

    def detail(self, entry_id):
        client = self.connection._session()
        row, refused = self._owned_row(client, entry_id, GONE_KEY)
        if refused is not None:
            return refused
        if not row.detail_path:
            return {"ok": True, "attachments": [], "can_upload": False, "log": []}
        page, links = self._detail_links(client, row)
        target = self._upload_target(client, page, row.entry_id)
        if target is not None:
            logger.info("school#%s older absence upload form: %s", self.connection.id, structure_text(target[0], _shape))
        return {
            "ok": True,
            "attachments": [
                {"key": attachment_key(item.path), "name": item.name, "deletable": bool(item.delete_link or item.delete_form)}
                for item in links
            ],
            "can_upload": target is not None,
            "log": change_log(getattr(page, "text", "") or ""),
        }

    def attachment(self, entry_id, key):
        client = self.connection._session()
        row, refused = self._owned_row(client, entry_id, GONE_KEY)
        if refused is not None or not row.detail_path:
            raise DataError("older absence attachment not listed")
        _page, links = self._detail_links(client, row)
        item = _by_key(links, key)
        if item is None:
            raise DataError("older absence attachment not listed")
        return read_school_file(client, item.path, self.connection._school_url())

    def attach(self, entry_id, upload):
        if not self._busy.acquire(blocking=False):
            return messages.result(False, BUSY_KEY)
        try:
            return self._attach(entry_id, upload)
        finally:
            self._busy.release()

    def _attach(self, entry_id, upload):
        client = self.connection._session()
        row, refused = self._owned_row(client, entry_id, GONE_KEY)
        if refused is not None:
            return refused
        if not row.detail_path:
            return messages.result(False, ATTACH_UNSUPPORTED_KEY)
        page, before = self._detail_links(client, row)
        target = self._upload_target(client, page, row.entry_id)
        if target is None:
            return messages.result(False, ATTACH_UNSUPPORTED_KEY)
        form, field, url = target
        files = {field: (upload["filename"], upload["content"], upload.get("content_type") or "application/octet-stream")}
        try:
            answer = client.post_form(form.action, data=form_pairs(form), files=files, headers=browser_headers(url))
        except (RequestException, DataError) as error:
            logger.warning("school#%s older absence attachment outcome unknown: %s", self.connection.id, type(error).__name__)
            answer = None
        try:
            _page, after = self._detail_links(client, row)
        except (DataError, RequestException):
            after = before
        if len(after) > len(before):
            return messages.result(True, ATTACHED_KEY)
        if _refused(answer):
            logger.warning("school#%s older absence attachment refused with status %d", self.connection.id, _status(answer))
            return messages.result(False, ATTACH_STATUS_KEY, {"status": _status(answer)})
        if answer is not None:
            present, fields, general = answer_errors(getattr(answer, "text", "") or "", form)
            if present and (fields or general):
                return messages.result(False, REJECTED_KEY, errors=list(fields.values()) + general)
        logger.warning("school#%s older absence attachment sent but not listed", self.connection.id)
        return messages.result(False, ATTACH_UNCERTAIN_KEY)

    def delete_attachment(self, entry_id, key):
        if not self._busy.acquire(blocking=False):
            return messages.result(False, BUSY_KEY)
        try:
            return self._delete_attachment(entry_id, key)
        finally:
            self._busy.release()

    def _delete_attachment(self, entry_id, key):
        client = self.connection._session()
        row, refused = self._owned_row(client, entry_id, GONE_KEY)
        if refused is not None:
            return refused
        if not row.detail_path:
            return messages.result(False, GONE_KEY)
        page, links = self._detail_links(client, row)
        item = _by_key(links, key)
        if item is None:
            return messages.result(False, GONE_KEY)
        if not (item.delete_link or item.delete_form):
            return messages.result(False, ATTACHMENT_LOCKED_KEY)
        page_url = str(getattr(page, "url", "") or "")
        try:
            if item.delete_form is not None and _own_action(item.delete_form, page_url):
                answer = client.post_absolute(item.delete_form.action, data=form_pairs(item.delete_form), headers=browser_headers(page_url))
            else:
                answer = client.fetch_or_raise(item.delete_link)
                confirm = parse_confirm_form(getattr(answer, "text", "") or "", str(getattr(answer, "url", "") or ""))
                if confirm is not None and _own_action(confirm, getattr(answer, "url", "")) and delete_target(urlsplit(confirm.action).path):
                    logger.info("school#%s older absence attachment confirm form: %s", self.connection.id, structure_text(confirm, _shape))
                    answer = client.post_absolute(confirm.action, data=form_pairs(confirm), headers=browser_headers(answer.url))
        except (RequestException, DataError) as error:
            logger.warning("school#%s older absence attachment removal outcome unknown: %s", self.connection.id, type(error).__name__)
            answer = None
        if _refused(answer):
            return messages.result(False, ATTACH_STATUS_KEY, {"status": _status(answer)})
        try:
            _page, after = self._detail_links(client, row)
        except (DataError, RequestException):
            return messages.result(False, ATTACHMENT_KEPT_KEY)
        if any(other.path == item.path for other in after):
            logger.warning("school#%s older absence attachment still listed after removal", self.connection.id)
            return messages.result(False, ATTACHMENT_KEPT_KEY)
        return messages.result(True, ATTACHMENT_REMOVED_KEY)

    def export(self):
        client = self.connection._session()
        _listed, page = self.absences.older_list(client)
        path = export_path(getattr(page, "text", "") or "", str(getattr(page, "url", "") or ""))
        if not path:
            raise DataError("older absence export not linked", message_key=EXPORT_KEY)
        answer = client.fetch_or_raise(path)
        filtered = owned_csv(getattr(answer, "content", b"") or b"", self.absences._known_children())
        if filtered is None:
            logger.info("school#%s older absence export: no name column", self.connection.id)
            raise DataError("older absence export unreadable", message_key=EXPORT_KEY)
        content, withheld = filtered
        if content is None:
            logger.info("school#%s older absence export: no row matched a profile, %d withheld", self.connection.id, withheld)
            raise DataError("older absence export without own rows", message_key=EXPORT_EMPTY_KEY)
        if withheld:
            logger.info("school#%s older absence export: %d rows not matched to a profile", self.connection.id, withheld)
        return content, EXPORT_NAME


def _by_key(links, key):
    if not isinstance(key, str):
        return None
    return next((item for item in links if attachment_key(item.path) == key), None)


def _decoded(raw):
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def owned_csv(raw, children):
    text = _decoded(raw)
    first = text.splitlines()[0] if text.strip() else ""
    if not first:
        return None
    delimiter = max(";,\t", key=first.count)
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    header = rows[0]
    columns = [index for index, cell in enumerate(header) if header_role(cell) == ROLE_NAME]
    if not columns:
        return None
    known = [name_words(child.get("name")) for child in children or []]
    kept = [header]
    for row in rows[1:]:
        found = name_words(" ".join(row[index] for index in columns if index < len(row)))
        if found and sum(1 for child in known if child == found) == 1:
            kept.append(row)
    if len(kept) == 1:
        return None, len(rows) - 1
    out = io.StringIO()
    csv.writer(out, delimiter=delimiter, lineterminator="\r\n").writerows(kept)
    return ("\ufeff" + out.getvalue()).encode("utf-8"), len(rows) - len(kept)
