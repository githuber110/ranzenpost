import base64
import imaplib
import re
import smtplib
import time
from email.message import EmailMessage
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import format_datetime, formataddr, getaddresses, make_msgid
from datetime import datetime, timezone

from .errors import DataError
from .html import clean_html, plain_text
from .mail import (
    MailUnreadable,
    imap_string,
    quote_folder,
    select,
    tls_context,
    uids_of,
)


SMTP_PORT = 587
SMTP_TIMEOUT_SECONDS = 30
RECIPIENT_LIMIT = 200
SUBJECT_LIMIT = 500
TEXT_LIMIT = 1024 * 1024
ATTACHMENT_LIMIT = 25 * 1024 * 1024
MODES = ("new", "reply", "reply_all", "forward", "draft")
ADDRESS = re.compile(r"^[^@\s<>\"(),;:]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z0-9-]{2,63}$")
SEND_FAILED_KEY = "api.mail.sendFailed"
SEND_UNCERTAIN_KEY = "api.mail.sendUncertain"
SEND_REFUSED_KEY = "api.mail.sendRefused"
NO_RECIPIENT_KEY = "api.mail.noRecipient"
INVALID_RECIPIENT_KEY = "api.mail.invalidRecipient"
INVALID_SENDER_KEY = "api.mail.invalidSender"
TOO_LARGE_KEY = "api.mail.tooLarge"
INVALID_REQUEST_KEY = "api.mail.invalidRequest"
REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
FORWARDED = "$Forwarded"
MDN_SENT = "$MDNSent"
DRAFT_FLAGS = "(\\Draft \\Seen)"
SENT_FLAGS = "(\\Seen)"
QUOTE_LIMIT = 200000
MDN_SUBJECT = "Disposition notification"


class MailSendFailed(DataError):
    def __init__(self, note="mail not sent", message_key=SEND_FAILED_KEY, detail=None):
        super().__init__(note, message_key=message_key, detail=detail)


class MailSendUncertain(DataError):
    def __init__(self, note="mail sending not confirmed"):
        super().__init__(note, message_key=SEND_UNCERTAIN_KEY)


class MailComposeError(DataError):
    pass


def clean_address(entry):
    if isinstance(entry, dict):
        name = " ".join(str(entry.get("name") or "").split())
        address = str(entry.get("address") or "").strip()
    else:
        parsed = getaddresses([str(entry or "")])
        name, address = (parsed[0] if parsed else ("", ""))
        name = " ".join(str(name or "").split())
        address = str(address or "").strip()
    if not ADDRESS.match(address):
        raise MailComposeError("invalid recipient", message_key=INVALID_RECIPIENT_KEY, detail={"address": address[:80]})
    return {"name": name[:120], "address": address}


def clean_addresses(values):
    listed = values if isinstance(values, (list, tuple)) else ([values] if values else [])
    found = []
    seen = set()
    for value in listed:
        entry = clean_address(value)
        key = entry["address"].lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(entry)
    return found


def header_addresses(entries):
    return ", ".join(formataddr((entry["name"], entry["address"])) for entry in entries)


def clean_draft(payload, senders):
    payload = payload if isinstance(payload, dict) else {}
    sender = str(payload.get("from") or "").strip().lower()
    known = {entry["address"].lower(): entry for entry in senders}
    if sender not in known:
        if len(senders) == 1 and not sender:
            sender = senders[0]["address"].lower()
        else:
            raise MailComposeError("unknown sender", message_key=INVALID_SENDER_KEY)
    to = clean_addresses(payload.get("to"))
    cc = clean_addresses(payload.get("cc"))
    bcc = clean_addresses(payload.get("bcc"))
    if len(to) + len(cc) + len(bcc) > RECIPIENT_LIMIT:
        raise MailComposeError("too many recipients", message_key=INVALID_RECIPIENT_KEY)
    subject = " ".join(str(payload.get("subject") or "").split())[:SUBJECT_LIMIT]
    html = clean_html(str(payload.get("html") or ""))[:TEXT_LIMIT] if payload.get("html") else ""
    text = str(payload.get("text") or "")[:TEXT_LIMIT]
    if html and not text.strip():
        text = plain_text(html)
    mode = payload.get("mode") if payload.get("mode") in MODES else "new"
    return {
        "from": known[sender],
        "to": to,
        "cc": cc,
        "bcc": bcc,
        "subject": subject,
        "text": text,
        "html": html,
        "mode": mode,
        "receipt": payload.get("receipt") is True,
        "in_reply_to": _message_id(payload.get("in_reply_to")),
        "references": " ".join(_message_id(part) for part in str(payload.get("references") or "").split() if _message_id(part))[:2000],
    }


def request_id_of(value):
    text = str(value or "").strip()
    if not REQUEST_ID.match(text):
        raise MailComposeError("invalid request id", message_key=INVALID_REQUEST_KEY)
    return text


def _message_id(value):
    text = str(value or "").strip()
    return text if re.match(r"^<[^<>\s]{1,250}>$", text) else ""


def build_message(draft, host, uploads=(), carried=(), now=None):
    message = EmailMessage()
    message["From"] = formataddr((draft["from"]["name"], draft["from"]["address"]))
    if draft["to"]:
        message["To"] = header_addresses(draft["to"])
    if draft["cc"]:
        message["Cc"] = header_addresses(draft["cc"])
    if draft["bcc"]:
        message["Bcc"] = header_addresses(draft["bcc"])
    message["Subject"] = draft["subject"]
    message["Date"] = format_datetime(now or datetime.now(timezone.utc))
    message["Message-ID"] = make_msgid(domain=host or None)
    if draft["in_reply_to"]:
        message["In-Reply-To"] = draft["in_reply_to"]
    references = " ".join(part for part in (draft["references"], draft["in_reply_to"]) if part).strip()
    if references:
        message["References"] = references
    if draft["receipt"]:
        message["Disposition-Notification-To"] = formataddr((draft["from"]["name"], draft["from"]["address"]))
    message.set_content(draft["text"] or "")
    if draft["html"]:
        message.add_alternative(draft["html"], subtype="html")
    total = 0
    for item in list(uploads) + list(carried):
        content = item.get("content") or b""
        total += len(content)
        if total > ATTACHMENT_LIMIT:
            raise MailComposeError("attachments too large", message_key=TOO_LARGE_KEY)
        maintype, _, subtype = str(item.get("mimetype") or "application/octet-stream").partition("/")
        if maintype == "text" or maintype == "multipart" or not subtype:
            maintype, subtype = "application", "octet-stream"
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=str(item.get("filename") or "attachment"))
    return message


def envelope(draft):
    recipients = [entry["address"] for entry in draft["to"] + draft["cc"] + draft["bcc"]]
    if not recipients:
        raise MailComposeError("no recipient", message_key=NO_RECIPIENT_KEY)
    return draft["from"]["address"], recipients


def open_smtp(host):
    smtp = smtplib.SMTP(host, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
    smtp.ehlo()
    smtp.starttls(context=tls_context())
    smtp.ehlo()
    return smtp


def smtp_sign_in(smtp, username, password):
    try:
        username.encode("ascii")
        password.encode("ascii")
    except UnicodeEncodeError:
        token = base64.b64encode(b"\0" + username.encode("utf-8") + b"\0" + password.encode("utf-8")).decode("ascii")
        code, answer = smtp.docmd("AUTH", "PLAIN " + token)
        if code != 235:
            raise smtplib.SMTPAuthenticationError(code, answer)
        return
    smtp.login(username, password)


def transmit(smtp, message, sender, recipients):
    try:
        refused = smtp.send_message(message, from_addr=sender, to_addrs=recipients)
    except smtplib.SMTPRecipientsRefused as error:
        raise MailSendFailed("every recipient refused", message_key=SEND_REFUSED_KEY, detail={"refused": len(error.recipients)}) from error
    except (smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as error:
        raise MailSendFailed("the server refused the mail") from error
    except (smtplib.SMTPException, OSError) as error:
        raise MailSendUncertain() from error
    return sorted(refused or {})


def append(imap, folder_id, flags, message):
    raw = message.as_bytes()
    status, data = imap.append(quote_folder(folder_id), flags, imaplib.Time2Internaldate(time.time()), raw)
    if status != "OK":
        raise MailUnreadable("append refused")
    return appended_uid(data)


def appended_uid(data):
    for line in data or []:
        if isinstance(line, bytes):
            match = re.search(rb"APPENDUID\s+\d+\s+(\d+)", line)
            if match:
                return match.group(1).decode("ascii")
    return ""


def quote_text(detail, intro):
    body = detail.get("body_text") or plain_text(detail.get("body_html") or "")
    quoted = "\n".join("> " + line for line in body[:QUOTE_LIMIT].splitlines())
    return "\n\n" + intro + "\n" + quoted + "\n"


def _subject_with(prefix, subject):
    text = subject or ""
    return text if text.lower().startswith(prefix.lower()) else ("%s %s" % (prefix, text)).strip()


def prefill(detail, mode, own_addresses):
    own = {address.lower() for address in own_addresses}
    references = " ".join(part for part in (detail.get("references") or "", detail.get("message_id") or "") if part).strip()
    if mode == "forward":
        return {
            "mode": mode,
            "to": [],
            "cc": [],
            "subject": _subject_with("Fwd:", detail.get("subject")),
            "attachments": detail.get("attachments") or [],
            "quote": detail,
            "in_reply_to": "",
            "references": "",
        }
    reply_to = detail.get("reply_to") or detail.get("from") or []
    to = [entry for entry in reply_to if entry.get("address")]
    cc = []
    if mode == "reply_all":
        listed = {entry["address"].lower() for entry in to}
        for entry in (detail.get("to") or []) + (detail.get("cc") or []):
            key = str(entry.get("address") or "").lower()
            if key and key not in own and key not in listed:
                listed.add(key)
                cc.append(entry)
    return {
        "mode": mode,
        "to": to,
        "cc": cc,
        "subject": _subject_with("Re:", detail.get("subject")),
        "attachments": [],
        "quote": detail,
        "in_reply_to": detail.get("message_id") or "",
        "references": references,
    }


def newest_uid(imap, folder_id, message_id):
    select(imap, folder_id, readonly=True)
    status, data = imap.uid("SEARCH", None, "HEADER", "Message-ID", imap_string(str(message_id or "")))
    if status != "OK":
        return ""
    found = sorted(uids_of(data))
    return str(found[-1]) if found else ""


def receipt_message(detail, sender, host, now=None):
    target = (detail.get("receipt_to") or [None])[0]
    if not target or not ADDRESS.match(str(target.get("address") or "")):
        raise MailComposeError("no receipt address", message_key=INVALID_RECIPIENT_KEY)
    message = MIMEMultipart("report", report_type="disposition-notification")
    message["From"] = formataddr((sender["name"], sender["address"]))
    message["To"] = formataddr((target.get("name") or "", target["address"]))
    message["Subject"] = "%s: %s" % (MDN_SUBJECT, detail.get("subject") or "")
    message["Date"] = format_datetime(now or datetime.now(timezone.utc))
    message["Message-ID"] = make_msgid(domain=host or None)
    if detail.get("message_id"):
        message["References"] = detail["message_id"]
    message.attach(MIMEText("The message was displayed.\n", "plain", "utf-8"))
    fields = "Reporting-UA: %s; Ranzenpost\r\nFinal-Recipient: rfc822;%s\r\n" % (host, sender["address"])
    if detail.get("message_id"):
        fields += "Original-Message-ID: %s\r\n" % detail["message_id"]
    fields += "Disposition: manual-action/MDN-sent-manually; displayed\r\n"
    report = MIMEBase("message", "disposition-notification")
    report.set_payload(fields)
    message.attach(report)
    return message, target["address"]
