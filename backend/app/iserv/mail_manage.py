import base64
from datetime import datetime, timezone

from .mail import (
    KEYWORD_TEXT,
    ROLE_ARCHIVE,
    ROLE_FOLDER,
    ROLE_INBOX,
    SEEN,
    UNKNOWN_FOLDER_KEY,
    UNKNOWN_MESSAGE_KEY,
    MailUnreadable,
    answer_data,
    clean_uid,
    fetch_records,
    imap_string,
    parse_list,
    quote_folder,
    select,
    uids_of,
    UID_FIELD,
    header_date,
    internal_date,
    parse_message,
)

BATCH_LIMIT = 500
FOLDER_NAME_LIMIT = 120
INVALID_FLAG_KEY = "api.mail.invalidFlag"
UNSUPPORTED_KEY = "api.mail.unsupported"
INVALID_FOLDER_NAME_KEY = "api.mail.invalidFolderName"
PROTECTED_FOLDER_KEY = "api.mail.protectedFolder"
FLAG_NAMES = {"seen": SEEN, "flagged": "\\Flagged", "answered": "\\Answered"}
DELETED = "\\Deleted"
DATE_ITEMS = "(UID INTERNALDATE BODY.PEEK[HEADER.FIELDS (DATE)])"
JUNK_FLAG = "\\junk"
NO_JUNK_KEY = "api.mail.noJunk"


def clean_uids(values):
    listed = values if isinstance(values, (list, tuple)) else [values]
    uids = []
    for value in listed:
        uid = clean_uid(value)
        if uid not in uids:
            uids.append(uid)
    if not uids or len(uids) > BATCH_LIMIT:
        raise MailUnreadable("invalid message ids", message_key=UNKNOWN_MESSAGE_KEY)
    return uids


def flag_name(flag):
    text = str(flag or "").strip()
    if text in FLAG_NAMES:
        return FLAG_NAMES[text]
    if KEYWORD_TEXT.match(text):
        return text
    raise MailUnreadable("invalid flag", message_key=INVALID_FLAG_KEY)


def capabilities(imap):
    return {str(entry).upper() for entry in getattr(imap, "capabilities", ()) or ()}


def set_flag(imap, folder_id, uids, flag, on):
    uids = clean_uids(uids)
    name = flag_name(flag)
    select(imap, folder_id, readonly=False)
    answer_data(imap.uid("STORE", ",".join(uids), "+FLAGS.SILENT" if on else "-FLAGS.SILENT", "(%s)" % name))
    return uids


def present_uids(imap, folder_id, uids):
    select(imap, folder_id, readonly=True)
    found = uids_of(answer_data(imap.uid("SEARCH", None, "UID", ",".join(uids))))
    return [uid for uid in uids if int(uid) in found]


def move_messages(imap, folder_id, uids, target):
    uids = clean_uids(uids)
    if str(target) == str(folder_id):
        return uids
    select(imap, folder_id, readonly=False)
    joined = ",".join(uids)
    held = capabilities(imap)
    if "MOVE" in held:
        answer_data(imap.uid("MOVE", joined, quote_folder(target)))
        return uids
    if "UIDPLUS" not in held:
        raise MailUnreadable("the server cannot move single mails", message_key=UNSUPPORTED_KEY)
    answer_data(imap.uid("COPY", joined, quote_folder(target)))
    answer_data(imap.uid("STORE", joined, "+FLAGS.SILENT", "(%s)" % DELETED))
    answer_data(imap.uid("EXPUNGE", joined))
    return uids


def delete_messages(imap, folder_id, uids):
    uids = clean_uids(uids)
    if "UIDPLUS" not in capabilities(imap):
        raise MailUnreadable("the server cannot delete single mails", message_key=UNSUPPORTED_KEY)
    select(imap, folder_id, readonly=False)
    joined = ",".join(uids)
    answer_data(imap.uid("STORE", joined, "+FLAGS.SILENT", "(%s)" % DELETED))
    answer_data(imap.uid("EXPUNGE", joined))
    return uids


def years_of(imap, folder_id, uids):
    select(imap, folder_id, readonly=True)
    data = answer_data(imap.uid("FETCH", ",".join(uids), DATE_ITEMS))
    years = {}
    for record in fetch_records(data):
        uid = UID_FIELD.search(record["meta"])
        if not uid:
            continue
        moment = header_date(parse_message(record["literal"])) or internal_date(record["meta"])
        years[uid.group(1).decode("ascii")] = (moment or datetime.now(timezone.utc)).year
    return years


def folder_exists(imap, name):
    status, _data = imap.status(quote_folder(name), "(MESSAGES)")
    return status == "OK"


def create_folder(imap, name):
    answer_data(imap.create(quote_folder(name)))
    subscribe = getattr(imap, "subscribe", None)
    if callable(subscribe):
        subscribe(quote_folder(name))
    return name


def ensure_folder(imap, name):
    return name if folder_exists(imap, name) else create_folder(imap, name)


def archive_messages(imap, folder_id, uids, archive):
    uids = clean_uids(uids)
    if not archive:
        raise MailUnreadable("no archive folder", message_key=UNSUPPORTED_KEY)
    years = years_of(imap, folder_id, uids)
    targets = {}
    for uid in uids:
        year = years.get(uid)
        target = "%s%s%d" % (archive["id"], archive["delimiter"], year) if year and archive.get("delimiter") else archive["id"]
        targets.setdefault(target, []).append(uid)
    moved = {}
    for target, chosen in targets.items():
        if target != folder_id:
            ensure_folder(imap, target)
            move_messages(imap, folder_id, chosen, target)
        moved[target] = chosen
    return moved


def clean_folder_name(name):
    text = " ".join(str(name or "").split())
    if not text or len(text) > FOLDER_NAME_LIMIT or any(char in text for char in "%*\\\"") or text.upper() == "INBOX":
        raise MailUnreadable("invalid folder name", message_key=INVALID_FOLDER_NAME_KEY)
    return text


def encode_folder_name(name):
    out = []
    pending = []

    def flush():
        if not pending:
            return
        raw = "".join(pending).encode("utf-16-be")
        out.append("&" + base64.b64encode(raw).decode("ascii").rstrip("=").replace("/", ",") + "-")
        pending.clear()

    for char in name:
        if 0x20 <= ord(char) <= 0x7E:
            flush()
            out.append("&-" if char == "&" else char)
        else:
            pending.append(char)
    flush()
    return "".join(out)


def own_folder_id(name, parent, delimiter):
    encoded = encode_folder_name(clean_folder_name(name))
    if delimiter and delimiter in encoded:
        raise MailUnreadable("invalid folder name", message_key=INVALID_FOLDER_NAME_KEY)
    return "%s%s%s" % (parent, delimiter, encoded) if parent and delimiter else encoded


def changeable(folder):
    if not folder or folder.get("role") != ROLE_FOLDER:
        raise MailUnreadable("folder is protected", message_key=PROTECTED_FOLDER_KEY)
    return folder


def rename_folder(imap, folder, name):
    changeable(folder)
    delimiter = folder.get("delimiter") or ""
    parent = folder["id"].rsplit(delimiter, 1)[0] if delimiter and delimiter in folder["id"] else ""
    target = own_folder_id(name, parent, delimiter)
    answer_data(imap.rename(quote_folder(folder["id"]), quote_folder(target)))
    return target


def delete_folder(imap, folder):
    changeable(folder)
    answer_data(imap.delete(quote_folder(folder["id"])))
    return folder["id"]


def is_inbox(folder):
    return bool(folder) and folder.get("role") == ROLE_INBOX


def archive_folder(folders):
    for folder in folders:
        if folder.get("role") == ROLE_ARCHIVE:
            return folder
    return None


def find_folder(folders, folder_id):
    for folder in folders:
        if folder["id"] == folder_id:
            return folder
    raise MailUnreadable("unknown folder", message_key=UNKNOWN_FOLDER_KEY)


def header_uids(imap, folder_id, message_id):
    select(imap, folder_id, readonly=True)
    found = uids_of(answer_data(imap.uid("SEARCH", None, "HEADER", "Message-ID", imap_string(str(message_id or "")))))
    return [str(uid) for uid in sorted(found)]


def junk_folder(imap):
    for entry in parse_list(answer_data(imap.list())):
        if entry["selectable"] and JUNK_FLAG in entry["flags"]:
            return entry["id"]
    raise MailUnreadable("no junk folder marked by the server", message_key=NO_JUNK_KEY)
