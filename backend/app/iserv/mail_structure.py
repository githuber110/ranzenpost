import base64
import binascii
import imaplib
import quopri
import re
from datetime import datetime, timezone

from .mail import (
    SEEN,
    UNKNOWN_ATTACHMENT_KEY,
    UNKNOWN_MESSAGE_KEY,
    MailUnreadable,
    answer_data,
    header_date,
    header_text,
    iso_or_empty,
    lowered_flags,
    parse_message,
    addresses,
    clean_uid,
    keywords_of,
    mail_body_html,
    safe_filename,
    select,
)
SECTION_TEXT = re.compile(r"^[1-9]\d{0,3}(?:\.[1-9]\d{0,3}){0,7}$")
STRUCTURE_ITEMS = "(UID FLAGS INTERNALDATE RFC822.SIZE BODYSTRUCTURE BODY.PEEK[HEADER])"
TEXT_PART_LIMIT = 2 * 1024 * 1024
INLINE_IMAGE_LIMIT = 1024 * 1024
INLINE_TOTAL_LIMIT = 5 * 1024 * 1024
SOURCE_LIMIT = 2 * 1024 * 1024
ATTACHMENT_LIMIT = 40 * 1024 * 1024
TOO_LARGE_KEY = "api.mail.tooLarge"
INLINE_IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp")
CID_SOURCE = re.compile(r"""(src\s*=\s*["']?)cid:([^"'\s>]+)""", re.IGNORECASE)


class Tokens:
    def __init__(self, data):
        self.data = data
        self.at = 0

    def _skip(self):
        while self.at < len(self.data) and self.data[self.at:self.at + 1] in (b" ", b"\r", b"\n"):
            self.at += 1

    def value(self):
        self._skip()
        char = self.data[self.at:self.at + 1]
        if char == b"(":
            self.at += 1
            listed = []
            while True:
                self._skip()
                if self.data[self.at:self.at + 1] == b")":
                    self.at += 1
                    return listed
                if self.at >= len(self.data):
                    return listed
                listed.append(self.value())
        if char == b'"':
            self.at += 1
            out = bytearray()
            while self.at < len(self.data):
                current = self.data[self.at:self.at + 1]
                if current == b"\\":
                    out += self.data[self.at + 1:self.at + 2]
                    self.at += 2
                    continue
                if current == b'"':
                    self.at += 1
                    break
                out += current
                self.at += 1
            return bytes(out)
        if char == b"{":
            end = self.data.index(b"}", self.at)
            size = int(self.data[self.at + 1:end].rstrip(b"+"))
            start = end + 1
            self.at = start + size
            return self.data[start:start + size]
        start = self.at
        depth = 0
        while self.at < len(self.data):
            current = self.data[self.at:self.at + 1]
            if current == b"[":
                depth += 1
            elif current == b"]":
                depth -= 1
            elif depth == 0 and current in (b" ", b"(", b")", b"\r", b"\n"):
                break
            self.at += 1
        word = self.data[start:self.at]
        if word.upper() == b"NIL":
            return None
        return word


def joined(data):
    chunks = []
    current = []
    for item in data or []:
        if item is None:
            continue
        if isinstance(item, tuple):
            head = item[0] if isinstance(item[0], bytes) else b""
            if re.match(rb"^\d+\s+\(", head) and current:
                chunks.append(b"".join(current))
                current = []
            current.append(head)
            current.append(item[1] if isinstance(item[1], bytes) else b"")
            continue
        if isinstance(item, bytes):
            if re.match(rb"^\d+\s+\(", item) and current:
                chunks.append(b"".join(current))
                current = []
            current.append(item)
    if current:
        chunks.append(b"".join(current))
    return chunks


def fetch_items(data):
    found = []
    for chunk in joined(data):
        tokens = Tokens(chunk)
        tokens.value()
        listed = tokens.value()
        if not isinstance(listed, list):
            continue
        items = {}
        for index in range(0, len(listed) - 1, 2):
            key = listed[index]
            if isinstance(key, bytes):
                items[key.decode("ascii", "replace").upper()] = listed[index + 1]
        found.append(items)
    return found


def _text(value):
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else ("" if value is None else str(value))


def _params(value):
    params = {}
    if isinstance(value, list):
        for index in range(0, len(value) - 1, 2):
            params[_text(value[index]).lower()] = _decode_word(_text(value[index + 1]))
    return params


def _decode_word(text):
    if "=?" not in text:
        return text
    try:
        return str(parse_message(("X: %s\r\n\r\n" % text).encode("utf-8", "replace"))["x"] or text)
    except Exception:
        return text


def _disposition(value):
    if isinstance(value, list) and value:
        return _text(value[0]).lower(), _params(value[1] if len(value) > 1 else None)
    return "", {}


def parse_structure(value, section=""):
    if not isinstance(value, list) or not value:
        return None
    if isinstance(value[0], list):
        children = []
        index = 0
        while index < len(value) and isinstance(value[index], list):
            child = parse_structure(value[index], "%s.%d" % (section, index + 1) if section else str(index + 1))
            if child is not None:
                children.append(child)
            index += 1
        subtype = _text(value[index]).lower() if index < len(value) else "mixed"
        return {"section": section, "type": "multipart", "subtype": subtype, "children": children}
    kind = _text(value[0]).lower()
    subtype = _text(value[1]).lower() if len(value) > 1 else ""
    params = _params(value[2] if len(value) > 2 else None)
    try:
        size = int(_text(value[6])) if len(value) > 6 and value[6] is not None else 0
    except ValueError:
        size = 0
    if kind == "text":
        extension = 8
    elif kind == "message" and subtype == "rfc822":
        extension = 10
    else:
        extension = 7
    disposition, disposition_params = _disposition(value[extension + 1] if len(value) > extension + 1 else None)
    content_id = _text(value[3]).strip().strip("<>") if len(value) > 3 and value[3] is not None else ""
    return {
        "section": section or "1",
        "type": kind,
        "subtype": subtype,
        "params": params,
        "id": content_id,
        "encoding": _text(value[5]).lower() if len(value) > 5 and value[5] is not None else "7bit",
        "size": size,
        "disposition": disposition,
        "filename": disposition_params.get("filename") or params.get("name") or "",
        "children": [],
    }


def leaves(part):
    if part is None:
        return []
    if part["type"] == "multipart":
        found = []
        for child in part["children"]:
            found.extend(leaves(child))
        return found
    return [part]


def content_type(part):
    return "%s/%s" % (part["type"], part["subtype"])


def is_body_text(part):
    return content_type(part) in ("text/plain", "text/html") and part["disposition"] != "attachment" and not part["filename"]


def body_parts(parts):
    html = [part for part in parts if is_body_text(part) and part["subtype"] == "html"]
    plain = [part for part in parts if is_body_text(part) and part["subtype"] == "plain"]
    return html, plain


def decode(part, raw):
    encoding = part["encoding"]
    raw = raw or b""
    if encoding == "base64":
        try:
            return base64.b64decode(raw, validate=False)
        except (binascii.Error, ValueError):
            return b""
    if encoding == "quoted-printable":
        return quopri.decodestring(raw)
    return raw


def text_of(part, raw):
    data = decode(part, raw)
    charset = part["params"].get("charset") or "utf-8"
    try:
        text = data.decode(charset, "replace")
    except LookupError:
        text = data.decode("utf-8", "replace")
    return text.replace("\r\n", "\n")


def decoded_size(part):
    if part["encoding"] == "base64":
        return part["size"] * 3 // 4
    return part["size"]


def find_part(structure, section):
    for part in leaves(structure):
        if part["section"] == section:
            return part
    return None


def clean_section(value):
    text = str(value or "").strip()
    if not SECTION_TEXT.match(text):
        raise MailUnreadable("invalid attachment id", message_key=UNKNOWN_ATTACHMENT_KEY)
    return text


def fetch_head(imap, folder_id, uid):
    uid = clean_uid(uid)
    select(imap, folder_id, readonly=True)
    data = answer_data(imap.uid("FETCH", uid, STRUCTURE_ITEMS))
    for items in fetch_items(data):
        if _text(items.get("UID")) == uid:
            return {
                "uid": uid,
                "flags": [_text(flag) for flag in items.get("FLAGS") or []],
                "internal": _text(items.get("INTERNALDATE")),
                "size": int(_text(items.get("RFC822.SIZE")) or 0) if _text(items.get("RFC822.SIZE")).isdigit() else 0,
                "structure": parse_structure(items.get("BODYSTRUCTURE")),
                "header": items.get("BODY[HEADER]") or b"",
            }
    raise MailUnreadable("message not found", message_key=UNKNOWN_MESSAGE_KEY)


def fetch_sections(imap, uid, sections):
    if not sections:
        return {}
    wanted = " ".join("BODY.PEEK[%s]" % section for section in sections)
    data = answer_data(imap.uid("FETCH", uid, "(UID %s)" % wanted))
    found = {}
    for items in fetch_items(data):
        for section in sections:
            value = items.get("BODY[%s]" % section)
            if isinstance(value, bytes):
                found[section] = value
    return found


def _internal(text):
    try:
        parsed = imaplib.Internaldate2tuple(('INTERNALDATE "%s"' % text).encode("ascii"))
    except Exception:
        return None
    if parsed is None:
        return None
    return datetime(*parsed[:6]).astimezone(timezone.utc)


def _inline_images(imap, head, parts, html):
    wanted = {match.group(2).strip("<>") for match in CID_SOURCE.finditer(html)}
    images = {}
    total = 0
    chosen = [part for part in parts if part["id"] and part["id"] in wanted and content_type(part) in INLINE_IMAGE_TYPES and decoded_size(part) <= INLINE_IMAGE_LIMIT]
    raw = fetch_sections(imap, head["uid"], [part["section"] for part in chosen])
    for part in chosen:
        data = decode(part, raw.get(part["section"]))
        total += len(data)
        if not data or total > INLINE_TOTAL_LIMIT:
            continue
        images[part["id"]] = "data:%s;base64,%s" % (content_type(part), base64.b64encode(data).decode("ascii"))
    return images


def with_inline_images(html, images):
    def swap(match):
        found = images.get(match.group(2).strip("<>"))
        return match.group(1) + found if found else match.group(0)

    return CID_SOURCE.sub(swap, html)


def message_detail(imap, folder_id, uid, school_host="", inline=False):
    head = fetch_head(imap, folder_id, uid)
    message = parse_message(head["header"])
    parts = leaves(head["structure"])
    html, plain = body_parts(parts)
    chosen = html if html else plain
    sections = [part["section"] for part in chosen if part["size"] <= TEXT_PART_LIMIT * 2]
    raw = fetch_sections(imap, head["uid"], sections)
    texts = [text_of(part, raw.get(part["section"])) for part in chosen if part["section"] in raw]
    flags = lowered_flags(head["flags"])
    detail = {
        "uid": head["uid"],
        "subject": header_text(message, "subject"),
        "from": addresses(message, "from"),
        "sender": addresses(message, "sender"),
        "reply_to": addresses(message, "reply-to"),
        "to": addresses(message, "to"),
        "cc": addresses(message, "cc"),
        "bcc": addresses(message, "bcc"),
        "date": iso_or_empty(header_date(message) or _internal(head["internal"])),
        "unread": SEEN.lower() not in flags,
        "flagged": "\\flagged" in flags,
        "answered": "\\answered" in flags,
        "draft": "\\draft" in flags,
        "tags": keywords_of(head["flags"]),
        "receipt_to": addresses(message, "disposition-notification-to"),
        "message_id": header_text(message, "message-id"),
        "references": header_text(message, "references"),
        "body_html": "",
        "body_text": "",
        "size": head["size"],
        "attachments": [],
    }
    if html:
        joined_html = "".join(texts)
        if inline:
            joined_html = with_inline_images(joined_html, _inline_images(imap, head, parts, joined_html))
        detail["body_html"] = mail_body_html(joined_html, school_host)
    elif plain:
        detail["body_text"] = "\n\n".join(text.strip("\n") for text in texts)
    for part in parts:
        if part in html or part in plain:
            continue
        kind = content_type(part)
        detail["attachments"].append({
            "id": part["section"],
            "filename": safe_filename(part["filename"], kind),
            "mimetype": kind,
            "size": decoded_size(part),
            "inline": part["disposition"] == "inline" or bool(part["id"]),
        })
    return detail


def attachment(imap, folder_id, uid, section):
    section = clean_section(section)
    head = fetch_head(imap, folder_id, uid)
    part = find_part(head["structure"], section)
    html, plain = body_parts(leaves(head["structure"]))
    if part is None or part in html or part in plain:
        raise MailUnreadable("attachment not found", message_key=UNKNOWN_ATTACHMENT_KEY)
    if decoded_size(part) > ATTACHMENT_LIMIT:
        raise MailUnreadable("attachment too large", message_key=TOO_LARGE_KEY)
    raw = fetch_sections(imap, head["uid"], [section]).get(section, b"")
    kind = content_type(part)
    content = raw if kind == "message/rfc822" else decode(part, raw)
    return {"filename": safe_filename(part["filename"], kind), "mimetype": kind, "content": content}


def source(imap, folder_id, uid, limit=SOURCE_LIMIT):
    uid = clean_uid(uid)
    select(imap, folder_id, readonly=True)
    data = answer_data(imap.uid("FETCH", uid, "(UID RFC822.SIZE BODY.PEEK[]<0.%d>)" % limit))
    for items in fetch_items(data):
        if _text(items.get("UID")) != uid:
            continue
        raw = next((value for key, value in items.items() if key.startswith("BODY[]") and isinstance(value, bytes)), b"")
        size = int(_text(items.get("RFC822.SIZE"))) if _text(items.get("RFC822.SIZE")).isdigit() else len(raw)
        return {"source": raw.decode("utf-8", "replace"), "cut": size > len(raw)}
    raise MailUnreadable("message not found", message_key=UNKNOWN_MESSAGE_KEY)


def message_ids(imap, folder_id, uids):
    select(imap, folder_id, readonly=True)
    data = answer_data(imap.uid("FETCH", ",".join(uids), "(UID BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])"))
    found = {}
    for items in fetch_items(data):
        header = next((value for key, value in items.items() if key.startswith("BODY[HEADER") and isinstance(value, bytes)), b"")
        found[_text(items.get("UID"))] = header_text(parse_message(header), "message-id")
    return found


def shape(imap, folder_id, uid):
    head = fetch_head(imap, folder_id, uid)

    def tree(part):
        if part is None:
            return "?"
        if part["type"] == "multipart":
            return "multipart/%s[%s]" % (part["subtype"], ",".join(tree(child) for child in part["children"]))
        return content_type(part)

    html, plain = body_parts(leaves(head["structure"]))
    return {
        "headers": len(parse_message(head["header"]).keys()),
        "flags": [flag for flag in head["flags"] if flag.startswith("\\")],
        "keywords": len(keywords_of(head["flags"])),
        "tree": tree(head["structure"]),
        "attachments": len([part for part in leaves(head["structure"]) if part not in html and part not in plain]),
    }
