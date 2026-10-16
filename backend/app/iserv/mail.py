import base64
import imaplib
import mimetypes
import re
import ssl
from datetime import date, datetime, timedelta, timezone
from email import message_from_bytes, policy
from email.utils import getaddresses, parsedate_to_datetime
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from requests import certs

from .errors import DataError
from .html import clean_html

IMAP_PORT = 993
IMAP_TIMEOUT_SECONDS = 20
PAGE_SIZE = 40
PAGE_LIMIT = 200
INBOX = "INBOX"
LIST_HEADERS = "FROM TO CC SUBJECT DATE CONTENT-TYPE MESSAGE-ID"
LIST_ITEMS = "(UID FLAGS INTERNALDATE RFC822.SIZE BODY.PEEK[HEADER.FIELDS (%s)])" % LIST_HEADERS
SEEN = "\\Seen"
ROLE_INBOX = "inbox"
ROLE_DRAFTS = "drafts"
ROLE_SENT = "sent"
ROLE_ARCHIVE = "archive"
ROLE_JUNK = "junk"
ROLE_TRASH = "trash"
ROLE_FOLDER = "folder"
ROLE_ORDER = (ROLE_INBOX, ROLE_DRAFTS, ROLE_SENT, ROLE_ARCHIVE, ROLE_JUNK, ROLE_TRASH, ROLE_FOLDER)
SPECIAL_USE = {
    "\\drafts": ROLE_DRAFTS,
    "\\sent": ROLE_SENT,
    "\\archive": ROLE_ARCHIVE,
    "\\junk": ROLE_JUNK,
    "\\trash": ROLE_TRASH,
}
ROLE_NAMES = {
    "drafts": ROLE_DRAFTS,
    "draft": ROLE_DRAFTS,
    "entwürfe": ROLE_DRAFTS,
    "sent": ROLE_SENT,
    "sent items": ROLE_SENT,
    "sent messages": ROLE_SENT,
    "gesendet": ROLE_SENT,
    "archive": ROLE_ARCHIVE,
    "archiv": ROLE_ARCHIVE,
    "junk": ROLE_JUNK,
    "spam": ROLE_JUNK,
    "trash": ROLE_TRASH,
    "deleted": ROLE_TRASH,
    "deleted items": ROLE_TRASH,
    "papierkorb": ROLE_TRASH,
}
NOSELECT = ("\\noselect", "\\nonexistent")
LIST_LINE = re.compile(rb'^\((?P<flags>[^)]*)\)\s+(?P<delimiter>"(?:[^"\\]|\\.)*"|NIL)\s*(?P<name>.*)$', re.IGNORECASE)
STATUS_FIELD = re.compile(rb"(MESSAGES|UNSEEN)\s+(\d+)", re.IGNORECASE)
RECORD_START = re.compile(rb"^\d+\s+\(")
UID_FIELD = re.compile(rb"UID\s+(\d+)", re.IGNORECASE)
FLAGS_FIELD = re.compile(rb"FLAGS\s+\(([^)]*)\)", re.IGNORECASE)
DATE_FIELD = re.compile(rb'INTERNALDATE\s+"([^"]+)"', re.IGNORECASE)
SIZE_FIELD = re.compile(rb"RFC822\.SIZE\s+(\d+)", re.IGNORECASE)
UID_TEXT = re.compile(r"^[1-9]\d{0,9}$")
FILENAME_UNSAFE = re.compile(r'[\x00-\x1f\\/:*?"<>|]+')
FILENAME_LIMIT = 120
SIGN_IN_REFUSED_KEY = "api.mail.signInRefused"
UNREACHABLE_KEY = "api.mail.unreachable"
UNREADABLE_KEY = "api.mail.unreadable"
UNKNOWN_FOLDER_KEY = "api.mail.unknownFolder"
UNKNOWN_MESSAGE_KEY = "api.mail.unknownMessage"
UNKNOWN_ATTACHMENT_KEY = "api.mail.unknownAttachment"
DEFAULT_ATTACHMENT_NAME = "attachment"
INVALID_SEARCH_KEY = "api.mail.invalidSearch"
SEARCH_TEXT_LIMIT = 200
FETCH_CHUNK = 500
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
KEYWORD_TEXT = re.compile(r"^\$?[A-Za-z0-9_.-]{1,60}$")
STATUS_SEARCH = {
    "flagged": "FLAGGED",
    "answered": "ANSWERED",
    "unanswered": "UNANSWERED",
    "unread": "UNSEEN",
    "read": "SEEN",
}
SEARCH_SCOPES = {
    "all": ("TEXT",),
    "from": ("FROM",),
    "to": ("TO", "CC"),
    "subject": ("SUBJECT",),
    "body": ("BODY",),
}


class MailSignInRefused(DataError):
    def __init__(self, note="mail sign-in refused"):
        super().__init__(note, message_key=SIGN_IN_REFUSED_KEY)


class MailUnreachable(DataError):
    def __init__(self, note="mail server unreachable"):
        super().__init__(note, message_key=UNREACHABLE_KEY)


class MailUnreadable(DataError):
    def __init__(self, note="mail answer unreadable", message_key=UNREADABLE_KEY):
        super().__init__(note, message_key=message_key)


def tls_context():
    return ssl.create_default_context(cafile=certs.where())


def open_imap(host):
    return imaplib.IMAP4_SSL(host, IMAP_PORT, ssl_context=tls_context(), timeout=IMAP_TIMEOUT_SECONDS)


def decode_folder_name(raw):
    text = raw.decode("ascii", "replace") if isinstance(raw, bytes) else str(raw or "")
    out = []
    index = 0
    while index < len(text):
        char = text[index]
        if char != "&":
            out.append(char)
            index += 1
            continue
        end = text.find("-", index)
        if end < 0:
            out.append(text[index:])
            break
        chunk = text[index + 1:end]
        if not chunk:
            out.append("&")
        else:
            encoded = chunk.replace(",", "/")
            try:
                out.append(base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True).decode("utf-16-be"))
            except (ValueError, UnicodeDecodeError):
                out.append(text[index:end + 1])
        index = end + 1
    return "".join(out)


def quote_folder(name):
    return imap_string(str(name or ""))


def _unquote(raw):
    raw = raw.strip()
    if raw.upper() == b"NIL":
        return b""
    if raw.startswith(b'"') and raw.endswith(b'"') and len(raw) >= 2:
        return re.sub(rb"\\(.)", rb"\1", raw[1:-1])
    return raw


def _list_entries(data):
    entries = []
    for item in data or []:
        if isinstance(item, tuple) and isinstance(item[0], bytes):
            entries.append((item[0], item[1] if isinstance(item[1], bytes) else None))
        elif isinstance(item, bytes) and item.strip():
            entries.append((item, None))
    return entries


def parse_list(data):
    folders = []
    for head, literal in _list_entries(data):
        match = LIST_LINE.match(head.strip())
        if not match:
            continue
        flags = [flag.lower() for flag in match.group("flags").decode("ascii", "replace").split()]
        delimiter = _unquote(match.group("delimiter")).decode("ascii", "replace")
        raw_name = (literal if literal is not None else _unquote(match.group("name"))).decode("utf-8", "replace")
        if not raw_name:
            continue
        folders.append({
            "id": raw_name,
            "flags": flags,
            "delimiter": delimiter,
            "selectable": not any(flag in NOSELECT for flag in flags),
        })
    return folders


def leaf_name(folder_id, delimiter):
    name = decode_folder_name(folder_id)
    if delimiter and delimiter in name:
        return name.rsplit(delimiter, 1)[-1]
    return name


def folder_depth(folder_id, delimiter):
    parts = str(folder_id).split(delimiter) if delimiter else [str(folder_id)]
    if parts and parts[0].upper() == INBOX and len(parts) > 1:
        parts = parts[1:]
    return len(parts) - 1


def folder_role(folder_id, flags, delimiter):
    if str(folder_id).upper() == INBOX:
        return ROLE_INBOX
    for flag in flags:
        if flag in SPECIAL_USE:
            return SPECIAL_USE[flag]
    parent = str(folder_id).split(delimiter, 1)[0] if delimiter else ""
    if delimiter and delimiter in str(folder_id) and parent.upper() != INBOX:
        return ROLE_FOLDER
    return ROLE_NAMES.get(leaf_name(folder_id, delimiter).strip().casefold(), ROLE_FOLDER)


def parse_status(data):
    counts = {}
    for item in data or []:
        line = item[0] if isinstance(item, tuple) else item
        if not isinstance(line, bytes):
            continue
        for key, value in STATUS_FIELD.findall(line):
            counts[key.decode("ascii").lower()] = int(value)
    return counts


def folder_order(folder):
    role = folder["role"]
    return (ROLE_ORDER.index(role), folder["name"].casefold(), folder["id"])


def answer_data(answer, error=MailUnreadable):
    status, data = answer
    if status != "OK":
        raise error("imap answered %s" % status)
    return data


def list_folders(imap, counts=True):
    listed = parse_list(answer_data(imap.list()))
    folders = []
    unique_roles = set()
    for entry in listed:
        if not entry["selectable"]:
            continue
        role = folder_role(entry["id"], entry["flags"], entry["delimiter"])
        if role != ROLE_FOLDER and role != ROLE_INBOX and role in unique_roles:
            role = ROLE_FOLDER
        unique_roles.add(role)
        found = folder_counts(imap, entry["id"]) if counts else {}
        folders.append({
            "id": entry["id"],
            "name": leaf_name(entry["id"], entry["delimiter"]),
            "path": decode_folder_name(entry["id"]),
            "delimiter": entry["delimiter"],
            "depth": folder_depth(entry["id"], entry["delimiter"]),
            "role": role,
            "junk": any(SPECIAL_USE.get(flag) == ROLE_JUNK for flag in entry["flags"]),
            "unread": found.get("unread"),
            "total": found.get("total"),
        })
    folders.sort(key=folder_order)
    return folders


def clean_uid(value):
    text = str(value or "").strip()
    if not UID_TEXT.match(text):
        raise MailUnreadable("invalid message id", message_key=UNKNOWN_MESSAGE_KEY)
    return text




def select(imap, folder_id, readonly=True):
    try:
        status, _data = imap.select(quote_folder(folder_id), readonly=readonly)
    except imaplib.IMAP4.error as error:
        raise MailUnreadable("folder not selectable", message_key=UNKNOWN_FOLDER_KEY) from error
    if status != "OK":
        raise MailUnreadable("folder not selectable", message_key=UNKNOWN_FOLDER_KEY)


def uids_of(data):
    uids = []
    for line in data or []:
        if isinstance(line, tuple):
            line = line[0]
        if isinstance(line, bytes):
            uids.extend(int(part) for part in line.split() if part.isdigit())
    return set(uids)


def _search_day(value):
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def imap_day(day):
    return "%02d-%s-%d" % (day.day, MONTHS[day.month - 1], day.year)


def imap_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _either(keys, value):
    criterion = []
    for index, key in enumerate(keys):
        if index < len(keys) - 1:
            criterion.append("OR")
        criterion.extend([key, value])
    return criterion


def search_terms(search):
    search = search if isinstance(search, dict) else {}
    plain = []
    wide = []
    status = str(search.get("status") or "")
    if status in STATUS_SEARCH:
        plain.append(STATUS_SEARCH[status])
    tag = str(search.get("tag") or "").strip()
    if tag:
        if not KEYWORD_TEXT.match(tag):
            raise MailUnreadable("invalid tag", message_key=INVALID_SEARCH_KEY)
        plain.extend(["KEYWORD", tag])
    since = _search_day(search.get("since"))
    if since:
        plain.extend(["SINCE", imap_day(since)])
    until = _search_day(search.get("until"))
    if until:
        plain.extend(["BEFORE", imap_day(until + timedelta(days=1))])
    keys = SEARCH_SCOPES.get(str(search.get("scope") or "all"), SEARCH_SCOPES["all"])
    for word in " ".join(str(search.get("query") or "").split())[:SEARCH_TEXT_LIMIT].split(" "):
        if not word:
            continue
        try:
            word.encode("ascii")
        except UnicodeEncodeError:
            wide.append([(key, word) for key in keys])
            continue
        plain.extend(_either(keys, imap_string(word)))
    return plain, wide


def search_uids(imap, search=None):
    plain, wide = search_terms(search)
    found = uids_of(answer_data(imap.uid("SEARCH", None, *(plain or ["ALL"]))))
    for alternatives in wide:
        matched = set()
        for key, value in alternatives:
            imap.literal = value.encode("utf-8")
            matched |= uids_of(answer_data(imap.uid("SEARCH", "CHARSET", "UTF-8", *(plain + [key]))))
        found &= matched
    return sorted(found)


def fetch_records(data):
    records = []
    current = None
    for item in data or []:
        if item is None:
            continue
        if isinstance(item, tuple):
            head = item[0] if isinstance(item[0], bytes) else b""
            if RECORD_START.match(head) or current is None:
                current = {"meta": head, "literal": item[1] if isinstance(item[1], bytes) else b""}
                records.append(current)
            else:
                current["meta"] += b" " + head
                if not current["literal"] and isinstance(item[1], bytes):
                    current["literal"] = item[1]
            continue
        if not isinstance(item, bytes):
            continue
        if RECORD_START.match(item):
            current = {"meta": item, "literal": b""}
            records.append(current)
        elif current is not None:
            current["meta"] += b" " + item
    return records


def _flags_of(meta):
    match = FLAGS_FIELD.search(meta)
    if not match:
        return None
    return match.group(1).decode("ascii", "replace").split()


def lowered_flags(flags):
    return [flag.lower() for flag in flags or []]


def keywords_of(flags):
    return [flag for flag in (flags or []) if not flag.startswith("\\")]


def internal_date(meta):
    match = DATE_FIELD.search(meta)
    if not match:
        return None
    parsed = imaplib.Internaldate2tuple(b'INTERNALDATE "' + match.group(1) + b'"')
    if parsed is None:
        return None
    try:
        return datetime(*parsed[:6]).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def header_date(message):
    raw = message.get("date")
    if not raw:
        return None
    try:
        moment = parsedate_to_datetime(str(raw))
    except (TypeError, ValueError, IndexError):
        return None
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def iso_or_empty(moment):
    return moment.isoformat() if moment is not None else ""


def header_text(message, name):
    try:
        value = message.get(name)
    except Exception:
        return ""
    return " ".join(str(value or "").split())


def addresses(message, name):
    try:
        values = [str(value) for value in message.get_all(name) or []]
    except Exception:
        return []
    found = []
    for display, address in getaddresses(values):
        display = " ".join(str(display or "").split())
        address = str(address or "").strip()
        if display or address:
            found.append({"name": display, "address": address})
    return found


def parse_message(raw):
    return message_from_bytes(raw or b"", policy=policy.default)


def _content_type(message):
    try:
        return str(message.get_content_type() or "").lower()
    except Exception:
        return ""


def summary_of(record):
    meta = record["meta"]
    uid = UID_FIELD.search(meta)
    if not uid:
        return None
    message = parse_message(record["literal"])
    raw_flags = _flags_of(meta)
    flags = None if raw_flags is None else lowered_flags(raw_flags)
    size = SIZE_FIELD.search(meta)
    moment = header_date(message) or internal_date(meta)
    content_type = _content_type(message) if message.get("content-type") else ""
    return {
        "uid": uid.group(1).decode("ascii"),
        "subject": header_text(message, "subject"),
        "message_id": header_text(message, "message-id"),
        "from": addresses(message, "from"),
        "to": addresses(message, "to"),
        "cc": addresses(message, "cc"),
        "date": iso_or_empty(moment),
        "unread": None if flags is None else SEEN.lower() not in flags,
        "flagged": bool(flags) and "\\flagged" in flags,
        "answered": bool(flags) and "\\answered" in flags,
        "draft": bool(flags) and "\\draft" in flags,
        "tags": keywords_of(raw_flags),
        "has_attachments": content_type in ("multipart/mixed", "multipart/related") or content_type.startswith("application/"),
        "size": int(size.group(1)) if size else None,
    }


def _sizes(imap, uids):
    sizes = {}
    for start in range(0, len(uids), FETCH_CHUNK):
        chunk = uids[start:start + FETCH_CHUNK]
        data = answer_data(imap.uid("FETCH", ",".join(str(uid) for uid in chunk), "(UID RFC822.SIZE)"))
        for record in fetch_records(data):
            uid = UID_FIELD.search(record["meta"])
            size = SIZE_FIELD.search(record["meta"])
            if uid:
                sizes[int(uid.group(1))] = int(size.group(1)) if size else 0
    return sizes


def ordered_uids(imap, uids, order):
    if order in ("largest", "smallest"):
        sizes = _sizes(imap, list(uids))
        return sorted(uids, key=lambda uid: (sizes.get(uid, 0), uid), reverse=order == "largest")
    return sorted(uids, reverse=order != "oldest")


def summaries(imap, uids):
    if not uids:
        return []
    data = answer_data(imap.uid("FETCH", ",".join(str(uid) for uid in uids), LIST_ITEMS))
    found = {summary["uid"]: summary for summary in (summary_of(record) for record in fetch_records(data)) if summary}
    return [found[str(uid)] for uid in uids if str(uid) in found]


def page_bounds(offset, limit):
    try:
        offset = max(0, int(offset or 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = max(1, min(int(limit or PAGE_SIZE), PAGE_LIMIT))
    except (TypeError, ValueError):
        limit = PAGE_SIZE
    return offset, limit


def list_messages(imap, folder_id, offset=0, limit=PAGE_SIZE, search=None, order="newest"):
    select(imap, folder_id, readonly=True)
    offset, limit = page_bounds(offset, limit)
    uids = ordered_uids(imap, search_uids(imap, search), order)
    return {
        "messages": summaries(imap, uids[offset:offset + limit]),
        "total": len(uids),
        "offset": offset,
        "more": offset + limit < len(uids),
    }
















def safe_filename(name, content_type):
    cleaned = FILENAME_UNSAFE.sub("_", str(name or "")).strip(" .")
    if cleaned:
        return cleaned[:FILENAME_LIMIT]
    extension = ".eml" if content_type == "message/rfc822" else (mimetypes.guess_extension(content_type or "") or "")
    return DEFAULT_ATTACHMENT_NAME + extension




def _school_link(href, school_host):
    target = str(href or "").strip()
    if not target.lower().startswith(("http://", "https://")):
        return not target.lower().startswith(("mailto:", "tel:"))
    parts = urlsplit(target)
    return bool(school_host) and (parts.hostname or "").lower() == school_host and parts.path.startswith("/iserv")


def mail_body_html(raw, school_host=""):
    cleaned = clean_html(raw)
    if not cleaned:
        return ""
    soup = BeautifulSoup(cleaned, "html.parser")
    host = str(school_host or "").lower()
    for anchor in soup.find_all("a"):
        if _school_link(anchor.get("href"), host):
            anchor.unwrap()
    for image in soup.find_all("img"):
        source = str(image.get("src") or "").strip().lower()
        if not source.startswith(("http://", "https://", "data:image/")):
            image.decompose()
    return str(soup)










def mark_seen(imap, folder_id, uid):
    uid = clean_uid(uid)
    select(imap, folder_id, readonly=False)
    answer_data(imap.uid("STORE", uid, "+FLAGS.SILENT", "(%s)" % SEEN))
    return uid


def folder_counts(imap, folder_id):
    try:
        status, data = imap.status(quote_folder(folder_id), "(MESSAGES UNSEEN)")
    except imaplib.IMAP4.error:
        return {}
    if status != "OK":
        return {}
    counts = parse_status(data)
    return {"unread": counts.get("unseen"), "total": counts.get("messages")}
