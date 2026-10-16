import hashlib
import imaplib
import logging
import smtplib
import threading
import time
from urllib.parse import quote, urlsplit

from .failure import failure_cause
from .iserv import mail, mail_compose, mail_frame, mail_manage, mail_structure, sieve
from .iserv.errors import DataError
from .not_configured import NotConfiguredError
from .validate import normalize_school_url

logger = logging.getLogger(__name__)

REFUSAL_HOLD_SECONDS = 15 * 60
NOT_OFFERED_KEY = "api.mail.notOffered"
CONFIRM_KEY = "api.mail.confirmRequired"
CHANGED_KEY = "api.mail.changed"
ALREADY_JUNK_KEY = "api.mail.alreadyJunk"
NOT_A_DRAFT_KEY = "api.mail.notADraft"
SEARCH_RESULT_LIMIT = 200
ORDERS = ("newest", "oldest", "largest", "smallest")
SEND_PENDING = "pending"
SEND_MEMORY = 200
FOLDER_CACHE_SECONDS = 120
DETAIL_CACHE_SECONDS = 120
DETAIL_CACHE_SIZE = 8


class MailNotOffered(DataError):
    def __init__(self):
        super().__init__("the school offers no mail to this account", message_key=NOT_OFFERED_KEY)


class MailConfirmRequired(DataError):
    def __init__(self):
        super().__init__("the action needs a confirmation", message_key=CONFIRM_KEY)


def _fingerprint(username, password):
    return hashlib.sha256(("%s\0%s" % (username, password)).encode("utf-8")).hexdigest()


def sign_in(imap, username, password):
    try:
        username.encode("ascii")
        password.encode("ascii")
    except UnicodeEncodeError:
        token = b"\0" + username.encode("utf-8") + b"\0" + password.encode("utf-8")
        return imap.authenticate("PLAIN", lambda _challenge: token)
    return imap.login(username, password)


def content_disposition(filename):
    return "attachment; filename*=UTF-8''%s" % quote(filename, safe="")


class MailFile:
    def __init__(self, found):
        self.content = found["content"]
        self.headers = {"content-type": found["mimetype"], "content-disposition": content_disposition(found["filename"])}


def _close(imap):
    try:
        imap.logout()
    except Exception:
        logger.debug("mail logout failed", exc_info=True)


def _quit(smtp):
    try:
        smtp.quit()
    except Exception:
        logger.debug("mail submission quit failed", exc_info=True)


def folder_id(value):
    text = str(value or "").strip()
    if not text or len(text) > 400 or any(ord(char) < 32 for char in text):
        raise mail.MailUnreadable("invalid folder", message_key=mail.UNKNOWN_FOLDER_KEY)
    return text


def order_of(value):
    return value if value in ORDERS else "newest"


def expected_ids(expect):
    if not isinstance(expect, dict):
        return {}
    return {mail.clean_uid(uid): str(message_id or "") for uid, message_id in expect.items()}


class MailService:
    def __init__(self, connection, opener=None, clock=None, submitter=None, sieve_opener=None):
        self.connection = connection
        self.opener = opener or mail.open_imap
        self.sieve_opener = sieve_opener or sieve.open_sieve
        self.submitter = submitter or mail_compose.open_smtp
        self.clock = clock or time.time
        self._lock = threading.RLock()
        self._sends_lock = threading.Lock()
        self._refused = None
        self._sends = {}
        self._folder_cache = (0.0, None)
        self._details = {}

    def _account(self):
        config = self.connection.store.load_config()
        secrets = self.connection.store.load_secrets()
        username = str(secrets.get("username") or "")
        password = str(secrets.get("password") or "")
        try:
            host = urlsplit(normalize_school_url(config.get("school_url", ""))).hostname or ""
        except ValueError:
            host = ""
        if not host or not username or not password:
            raise NotConfiguredError("school url or credentials missing")
        return host, username, password

    def school_host(self):
        try:
            return self._account()[0]
        except NotConfiguredError:
            return ""

    def senders(self):
        host, username, _password = self._account()
        name = ""
        reader = getattr(self.connection, "me_if_signed_in", None)
        if callable(reader):
            try:
                me = reader() or {}
                name = str(me.get("displayname") or "").strip()
            except Exception as error:
                logger.info("school#%s mail sender name not read: %s", self.connection.id, failure_cause(error))
        address = username if "@" in username else "%s@%s" % (username.lower(), host)
        senders = [{"name": name, "address": address}]
        for extra in self._web_addresses():
            if extra != address.lower() and extra.endswith("@" + host.lower()):
                senders.append({"name": name, "address": extra})
        return senders

    def _web_addresses(self):
        reader = getattr(self.connection, "mail_web", None)
        if not callable(reader):
            return []
        try:
            return reader().account()["account"].get("addresses") or []
        except Exception as error:
            logger.info("school#%s mail sender addresses not read from the web: %s", self.connection.id, failure_cause(error))
            return []

    def _held(self, fingerprint):
        refused = self._refused
        if not refused:
            return False
        if refused[0] != fingerprint or self.clock() >= refused[1]:
            self._refused = None
            return False
        return True

    def _hold(self, fingerprint):
        self._refused = (fingerprint, self.clock() + REFUSAL_HOLD_SECONDS)
        logger.warning("school#%s mail sign-in refused, next try in %d minutes", self.connection.id, REFUSAL_HOLD_SECONDS // 60)

    def _open(self, host, username, password):
        fingerprint = _fingerprint(username, password)
        if self._held(fingerprint):
            raise mail.MailSignInRefused("mail sign-in held after a refusal")
        try:
            imap = self.opener(host)
        except (OSError, imaplib.IMAP4.error) as error:
            logger.warning("school#%s mail server not reached: %s", self.connection.id, failure_cause(error))
            raise mail.MailUnreachable() from error
        try:
            sign_in(imap, username, password)
        except imaplib.IMAP4.abort as error:
            _close(imap)
            logger.warning("school#%s mail sign-in broke off: %s", self.connection.id, failure_cause(error))
            raise mail.MailUnreachable() from error
        except imaplib.IMAP4.error as error:
            _close(imap)
            self._hold(fingerprint)
            raise mail.MailSignInRefused() from error
        except OSError as error:
            _close(imap)
            logger.warning("school#%s mail sign-in not answered: %s", self.connection.id, failure_cause(error))
            raise mail.MailUnreachable() from error
        self._refused = None
        return imap

    def _run(self, label, work):
        host, username, password = self._account()
        with self._lock:
            imap = self._open(host, username, password)
            try:
                return work(imap)
            except imaplib.IMAP4.abort as error:
                logger.warning("school#%s mail %s broke off: %s", self.connection.id, label, failure_cause(error))
                raise mail.MailUnreachable() from error
            except imaplib.IMAP4.error as error:
                logger.warning("school#%s mail %s refused: %s", self.connection.id, label, failure_cause(error))
                raise mail.MailUnreadable() from error
            except OSError as error:
                logger.warning("school#%s mail %s not answered: %s", self.connection.id, label, failure_cause(error))
                raise mail.MailUnreachable() from error
            except DataError as error:
                logger.warning("school#%s mail %s refused: %s", self.connection.id, label, failure_cause(error))
                raise
            finally:
                _close(imap)

    def _roles(self, imap):
        stamp, cached = self._folder_cache
        if cached is not None and self.clock() - stamp < FOLDER_CACHE_SECONDS:
            return cached
        listed = mail.list_folders(imap, counts=False)
        self._folder_cache = (self.clock(), listed)
        return listed

    def _forget_folders(self):
        self._folder_cache = (0.0, None)

    def _role(self, imap, role):
        return next((entry for entry in self._roles(imap) if entry["role"] == role), None)

    def _check_expected(self, imap, folder, uids, expect):
        wanted = expected_ids(expect)
        if not wanted:
            return
        found = mail_structure.message_ids(imap, folder, [uid for uid in uids if uid in wanted] or list(wanted))
        for uid, message_id in wanted.items():
            if found.get(uid, None) != message_id:
                logger.warning("school#%s mail action refused: the mail is no longer the one opened", self.connection.id)
                raise mail.MailUnreadable("the mail does not match", message_key=CHANGED_KEY)

    def structure(self):
        def work(imap):
            folders = mail.list_folders(imap)
            found = {
                "capabilities": sorted(mail_manage.capabilities(imap)),
                "folders": len(folders),
                "roles": sorted({entry["role"] for entry in folders}),
                "delimiters": sorted({entry["delimiter"] for entry in folders if entry.get("delimiter")}),
            }
            inbox = next((entry for entry in folders if entry["role"] == mail.ROLE_INBOX), None)
            if inbox is None:
                return found
            found["total"] = inbox.get("total")
            found["unread"] = inbox.get("unread")
            mail.select(imap, inbox["id"], readonly=True)
            uids = mail.search_uids(imap)
            if uids:
                found["newest"] = mail_structure.shape(imap, inbox["id"], str(uids[-1]))
            return found

        try:
            return self._run("structure", work)
        except DataError as error:
            return {"error": "not read (%s)" % (error.message_key or type(error).__name__)}

    def folders(self):
        listed = self._run("folder list", mail.list_folders)
        self._folder_cache = (self.clock(), listed)
        return {"folders": listed}

    def _sieve(self, label, work):
        host, username, password = self._account()
        fingerprint = _fingerprint(username, password)
        if self._held(fingerprint):
            raise mail.MailSignInRefused("mail sign-in held after a refusal")
        with self._lock:
            try:
                client = self.sieve_opener(host, username, password)
            except sieve.SieveSignInRefused as error:
                self._hold(fingerprint)
                raise mail.MailSignInRefused() from error
            except (OSError, sieve.SieveError) as error:
                logger.warning("school#%s mail rules not reached: %s", self.connection.id, failure_cause(error))
                raise sieve.SieveUnreachable() from error
            try:
                return work(client)
            except OSError as error:
                logger.warning("school#%s mail rules %s broke off: %s", self.connection.id, label, failure_cause(error))
                raise sieve.SieveUnreachable() from error
            except sieve.SieveError as error:
                logger.warning("school#%s mail rules %s refused: %s", self.connection.id, label, failure_cause(error))
                raise
            finally:
                client.logout()

    def sieve_structure(self):
        def work(client):
            scripts = client.scripts()
            found = []
            for entry in scripts:
                found.append(dict(entry, extensions=sieve.required_extensions(client.script(entry["name"]))))
            return {"scripts": found, "capabilities": dict(client.capabilities)}

        return self._sieve("structure", work)

    def messages(self, folder, offset=0, search=None, order="newest", limit=None):
        folder = folder_id(folder)
        order = order_of(order)
        listed = self._run("message list", lambda imap: mail.list_messages(imap, folder, offset, limit or mail.PAGE_SIZE, search=search, order=order))
        for entry in listed["messages"]:
            entry["folder"] = folder
        return dict(listed, folder=folder, order=order)

    def search_everywhere(self, search, order="newest"):
        order = order_of(order)

        def work(imap):
            found = []
            for entry in self._roles(imap):
                mail.select(imap, entry["id"], readonly=True)
                uids = mail.ordered_uids(imap, mail.search_uids(imap, search), order)[:SEARCH_RESULT_LIMIT]
                for summary in mail.summaries(imap, uids):
                    summary["folder"] = entry["id"]
                    found.append(summary)
            return found

        found = self._run("search", work)
        reverse = order in ("newest", "largest")
        key = (lambda entry: entry.get("size") or 0) if order in ("largest", "smallest") else (lambda entry: entry.get("date") or "")
        found.sort(key=key, reverse=reverse)
        return {"messages": found[:SEARCH_RESULT_LIMIT], "total": len(found), "offset": 0, "more": len(found) > SEARCH_RESULT_LIMIT, "order": order}

    def _detail(self, folder, uid, inline):
        key = (folder, str(uid), inline)
        now = self.clock()
        cached = self._details.get(key)
        if cached is not None and now - cached[0] < DETAIL_CACHE_SECONDS:
            return cached[1]
        host = self.school_host()
        detail = self._run("message", lambda imap: mail_structure.message_detail(imap, folder, uid, host, inline=inline))
        self._details[key] = (now, detail)
        while len(self._details) > DETAIL_CACHE_SIZE:
            self._details.pop(min(self._details, key=lambda entry: self._details[entry][0]))
        return detail

    def message(self, folder, uid):
        folder = folder_id(folder)
        return dict(self._detail(folder, uid, False), folder=folder)

    def body_page(self, folder, uid, theme="light"):
        folder = folder_id(folder)
        detail = self._detail(folder, uid, True)
        return {"html": mail_frame.document(detail, theme)}

    def source(self, folder, uid):
        folder = folder_id(folder)
        return dict(self._run("source", lambda imap: mail_structure.source(imap, folder, uid)), folder=folder)

    def attachment(self, folder, uid, part):
        folder = folder_id(folder)
        section = mail_structure.clean_section(part)
        return self._run("attachment", lambda imap: mail_structure.attachment(imap, folder, uid, section))

    def _forget_detail(self, folder, uids):
        for key in [key for key in self._details if key[0] == folder and key[1] in {str(uid) for uid in uids}]:
            self._details.pop(key, None)

    def mark_seen(self, folder, uid, expect=None):
        folder = folder_id(folder)

        def work(imap):
            self._check_expected(imap, folder, [mail.clean_uid(uid)], expect)
            mail.mark_seen(imap, folder, uid)
            return mail.folder_counts(imap, folder)

        counts = self._run("read mark", work)
        self._forget_detail(folder, [uid])
        return {"ok": True, "folder": folder, "unread": counts.get("unread"), "total": counts.get("total")}

    def set_flag(self, folder, uids, flag, on, expect=None):
        folder = folder_id(folder)

        def work(imap):
            self._check_expected(imap, folder, mail_manage.clean_uids(uids), expect)
            changed = mail_manage.set_flag(imap, folder, uids, flag, on)
            return changed, mail.folder_counts(imap, folder)

        changed, counts = self._run("flag", work)
        self._forget_detail(folder, changed)
        return {"ok": True, "folder": folder, "uids": changed, "flag": flag, "on": bool(on), "unread": counts.get("unread"), "total": counts.get("total")}

    def move(self, folder, uids, target, expect=None):
        folder = folder_id(folder)
        target = folder_id(target)

        def work(imap):
            mail_manage.find_folder(self._roles(imap), target)
            self._check_expected(imap, folder, mail_manage.clean_uids(uids), expect)
            moved = mail_manage.move_messages(imap, folder, uids, target)
            return self._after_move(imap, folder, moved, {target: moved})

        return self._run("move", work)

    def archive(self, folder, uids, expect=None):
        folder = folder_id(folder)

        def work(imap):
            self._check_expected(imap, folder, mail_manage.clean_uids(uids), expect)
            archive = mail_manage.archive_folder(self._roles(imap))
            moved = mail_manage.archive_messages(imap, folder, uids, archive)
            if any(target not in [entry["id"] for entry in self._roles(imap)] for target in moved):
                self._forget_folders()
            return self._after_move(imap, folder, [uid for chosen in moved.values() for uid in chosen], moved)

        return self._run("archive", work)

    def trash(self, folder, uids, confirmed=False, expect=None):
        folder = folder_id(folder)

        def work(imap):
            self._check_expected(imap, folder, mail_manage.clean_uids(uids), expect)
            trash = self._role(imap, mail.ROLE_TRASH)
            if trash is None or trash["id"] == folder:
                if not confirmed:
                    raise MailConfirmRequired()
                deleted = mail_manage.delete_messages(imap, folder, uids)
                left = mail_manage.present_uids(imap, folder, deleted)
                counts = mail.folder_counts(imap, folder)
                return {"ok": not left, "deleted": [uid for uid in deleted if uid not in left], "left": left, "folder": folder,
                        "unread": counts.get("unread"), "total": counts.get("total")}
            moved = mail_manage.move_messages(imap, folder, uids, trash["id"])
            return self._after_move(imap, folder, moved, {trash["id"]: moved})

        return self._run("trash", work)

    def spam(self, folder, uids, confirmed=False, expect=None):
        folder = folder_id(folder)
        if not confirmed:
            raise MailConfirmRequired()

        def work(imap):
            chosen = mail_manage.clean_uids(uids)
            self._check_expected(imap, folder, chosen, expect)
            junk = mail_manage.junk_folder(imap)
            if junk == folder:
                raise mail.MailUnreadable("the mail is in the junk folder already", message_key=ALREADY_JUNK_KEY)
            known = mail_structure.message_ids(imap, folder, chosen)
            wanted = sorted({known[uid] for uid in chosen if known.get(uid)})
            before = {message_id: set(mail_manage.header_uids(imap, junk, message_id)) for message_id in wanted}
            moved = mail_manage.move_messages(imap, folder, chosen, junk)
            result = self._after_move(imap, folder, moved, {junk: moved})
            found = [uid for message_id in wanted for uid in mail_manage.header_uids(imap, junk, message_id) if uid not in before[message_id]]
            logger.info("school#%s mail moved to the junk folder: %d mails, %d found again for undo", self.connection.id, len(result["moved"]), len([uid for uid in found if uid]))
            return dict(result, junk=junk, restore={"folder": junk, "uids": [uid for uid in found if uid], "target": folder})

        return self._run("spam", work)

    def _after_move(self, imap, folder, moved, targets):
        left = mail_manage.present_uids(imap, folder, list(moved)) if moved else []
        counts = mail.folder_counts(imap, folder)
        self._forget_detail(folder, moved)
        return {
            "ok": not left,
            "folder": folder,
            "moved": [uid for uid in moved if uid not in left],
            "left": left,
            "targets": {target: [uid for uid in chosen if uid not in left] for target, chosen in targets.items()},
            "unread": counts.get("unread"),
            "total": counts.get("total"),
        }

    def create_folder(self, name, parent=""):
        def work(imap):
            folders = mail.list_folders(imap, counts=False)
            delimiter = next((entry["delimiter"] for entry in folders if entry.get("delimiter")), "/")
            base = mail_manage.find_folder(folders, parent)["id"] if parent else ""
            target = mail_manage.own_folder_id(name, base, delimiter)
            if any(entry["id"] == target for entry in folders):
                raise mail.MailUnreadable("folder exists", message_key=mail_manage.INVALID_FOLDER_NAME_KEY)
            mail_manage.create_folder(imap, target)
            return target, mail.list_folders(imap)

        self._forget_folders()
        target, folders = self._run("folder create", work)
        return {"ok": any(entry["id"] == target for entry in folders), "folder": target, "folders": folders}

    def rename_folder(self, folder, name):
        folder = folder_id(folder)

        def work(imap):
            target = mail_manage.rename_folder(imap, mail_manage.find_folder(mail.list_folders(imap, counts=False), folder), name)
            return target, mail.list_folders(imap)

        self._forget_folders()
        target, folders = self._run("folder rename", work)
        return {"ok": any(entry["id"] == target for entry in folders), "folder": target, "folders": folders}

    def delete_folder(self, folder, confirmed=False):
        folder = folder_id(folder)
        if not confirmed:
            raise MailConfirmRequired()

        def work(imap):
            mail_manage.delete_folder(imap, mail_manage.find_folder(mail.list_folders(imap, counts=False), folder))
            return mail.list_folders(imap)

        self._forget_folders()
        folders = self._run("folder delete", work)
        return {"ok": not any(entry["id"] == folder for entry in folders), "folder": folder, "folders": folders}

    def compose_start(self, folder="", uid="", mode="new"):
        senders = self.senders()
        if mode not in ("reply", "reply_all", "forward", "draft") or not uid:
            return {"mode": "new", "senders": senders, "to": [], "cc": [], "bcc": [], "subject": "", "text": "", "attachments": []}
        detail = self.message(folder, uid)
        if mode == "draft":
            return {
                "mode": "draft",
                "senders": senders,
                "draft": {"folder": detail["folder"], "uid": detail["uid"]},
                "to": detail["to"],
                "cc": detail["cc"],
                "bcc": detail["bcc"],
                "subject": detail["subject"],
                "text": detail["body_text"],
                "html": detail["body_html"],
                "attachments": detail["attachments"],
                "source": {"folder": detail["folder"], "uid": detail["uid"]},
                "receipt": bool(detail.get("receipt_to")),
            }
        start = mail_compose.prefill(detail, mode, [entry["address"] for entry in senders])
        quoted = start.pop("quote")
        return dict(
            start,
            senders=senders,
            bcc=[],
            source={"folder": detail["folder"], "uid": detail["uid"]},
            original={"from": quoted["from"], "date": quoted["date"], "subject": quoted["subject"], "to": quoted["to"]},
            text=quoted.get("body_text") or "",
            html=quoted.get("body_html") or "",
        )

    def _draft_parts(self, payload, uploads):
        host, _username, _password = self._account()
        draft = mail_compose.clean_draft(payload, self.senders())
        source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        carried_ids = [str(part) for part in payload.get("carry") or []]
        return host, draft, source, carried_ids, list(uploads or [])

    def _carried(self, imap, source, carried_ids):
        if not carried_ids or not source:
            return []
        folder = folder_id(source.get("folder"))
        return [mail_structure.attachment(imap, folder, source.get("uid"), section) for section in carried_ids]

    def save_draft(self, payload, uploads=()):
        host, draft, source, carried_ids, uploads = self._draft_parts(payload, uploads)
        previous = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}

        def work(imap):
            drafts = self._role(imap, mail.ROLE_DRAFTS)
            if drafts is None:
                raise mail.MailUnreadable("no drafts folder", message_key=mail_manage.UNSUPPORTED_KEY)
            message = mail_compose.build_message(draft, host, uploads, self._carried(imap, source, carried_ids))
            uid = mail_compose.append(imap, drafts["id"], mail_compose.DRAFT_FLAGS, message)
            if not uid:
                uid = mail_compose.newest_uid(imap, drafts["id"], message["Message-ID"])
            replaced = self._drop_draft(imap, previous)
            saved = {"folder": drafts["id"], "uid": uid}
            attachments = mail_structure.message_detail(imap, drafts["id"], uid)["attachments"] if uid else []
            return {"ok": True, "draft": saved, "source": saved, "attachments": attachments, "replaced": replaced}

        return self._run("draft", work)

    def _drop_draft(self, imap, previous):
        if not previous or not previous.get("uid"):
            return False
        try:
            folder = folder_id(previous.get("folder"))
            uid = mail.clean_uid(previous.get("uid"))
            if not self._is_draft(imap, folder, uid):
                return False
            mail_manage.delete_messages(imap, folder, [uid])
            gone = not mail_manage.present_uids(imap, folder, [uid])
        except DataError as error:
            logger.info("school#%s old draft not removed: %s", self.connection.id, failure_cause(error))
            return False
        self._forget_detail(folder, [uid])
        return gone

    def _is_draft(self, imap, folder, uid):
        drafts = self._role(imap, mail.ROLE_DRAFTS)
        if drafts is None or drafts["id"] != folder:
            return False
        try:
            head = mail_structure.fetch_head(imap, folder, uid)
        except DataError:
            return False
        return "\\draft" in [flag.lower() for flag in head["flags"]]

    def delete_draft(self, folder, uid, confirmed=False):
        if not confirmed:
            raise MailConfirmRequired()
        folder = folder_id(folder)
        uid = mail.clean_uid(uid)

        def work(imap):
            if not self._is_draft(imap, folder, uid):
                raise mail.MailUnreadable("not a draft", message_key=NOT_A_DRAFT_KEY)
            mail_manage.delete_messages(imap, folder, [uid])
            return mail_manage.present_uids(imap, folder, [uid])

        left = self._run("draft delete", work)
        return {"ok": not left, "folder": folder, "uid": uid}

    def _remember(self, request_id):
        with self._sends_lock:
            earlier = self._sends.get(request_id)
            if earlier is None:
                self._sends[request_id] = SEND_PENDING
            return earlier

    def _settle(self, request_id, result):
        with self._sends_lock:
            if result is None:
                self._sends.pop(request_id, None)
                return
            self._sends[request_id] = result
            while len(self._sends) > SEND_MEMORY:
                self._sends.pop(next(iter(self._sends)))

    def _once(self, request_id, run):
        earlier = self._remember(request_id)
        if earlier is not None:
            if earlier == SEND_PENDING:
                raise mail_compose.MailSendUncertain("the same mail is still being sent")
            return dict(earlier, repeated=True)
        try:
            result = run()
        except mail_compose.MailSendUncertain:
            raise
        except Exception:
            self._settle(request_id, None)
            raise
        self._settle(request_id, result)
        return result

    def send(self, payload, uploads=(), confirmed=False):
        if not confirmed:
            raise MailConfirmRequired()
        request_id = mail_compose.request_id_of(payload.get("request_id"))
        return self._once(request_id, lambda: self._send(payload, uploads))

    def _send(self, payload, uploads):
        host, draft, source, carried_ids, uploads = self._draft_parts(payload, uploads)
        sender, recipients = mail_compose.envelope(draft)
        carried = self._run("forward parts", lambda imap: self._carried(imap, source, carried_ids)) if carried_ids else []
        message = mail_compose.build_message(draft, host, uploads, carried)
        refused = self._submit(host, message, sender, recipients)
        result = {"ok": True, "sent": True, "refused": refused, "message_id": message["Message-ID"]}
        result.update(self._after_send(message, draft, source, payload.get("draft")))
        return result

    def _submit(self, host, message, sender, recipients):
        _host, username, password = self._account()
        fingerprint = _fingerprint(username, password)
        if self._held(fingerprint):
            raise mail.MailSignInRefused("mail sign-in held after a refusal")
        with self._lock:
            try:
                smtp = self.submitter(host)
            except (OSError, smtplib.SMTPException) as error:
                logger.warning("school#%s mail submission not reached: %s", self.connection.id, failure_cause(error))
                raise mail_compose.MailSendFailed() from error
            try:
                try:
                    mail_compose.smtp_sign_in(smtp, username, password)
                except smtplib.SMTPAuthenticationError as error:
                    self._hold(fingerprint)
                    raise mail.MailSignInRefused() from error
                except (OSError, smtplib.SMTPException) as error:
                    logger.warning("school#%s mail submission sign-in failed: %s", self.connection.id, failure_cause(error))
                    raise mail_compose.MailSendFailed() from error
                try:
                    refused = mail_compose.transmit(smtp, message, sender, recipients)
                except DataError as error:
                    logger.warning("school#%s mail not sent: %s", self.connection.id, failure_cause(error))
                    raise
                logger.info("school#%s mail sent to %d recipients, %d refused", self.connection.id, len(recipients), len(refused))
                return refused
            finally:
                _quit(smtp)

    def _after_send(self, message, draft, source, previous):
        outcome = {"saved": False, "marked": False, "draft_removed": False}

        def work(imap):
            sent = self._role(imap, mail.ROLE_SENT)
            if sent is not None:
                mail_compose.append(imap, sent["id"], mail_compose.SENT_FLAGS, message)
                outcome["saved"] = True
            if source and draft["mode"] in ("reply", "reply_all", "forward"):
                flag = "answered" if draft["mode"] != "forward" else mail_compose.FORWARDED
                mail_manage.set_flag(imap, folder_id(source.get("folder")), [source.get("uid")], flag, True)
                outcome["marked"] = True
            outcome["draft_removed"] = self._drop_draft(imap, previous if isinstance(previous, dict) else {})
            return outcome

        try:
            return self._run("after send", work)
        except Exception as error:
            logger.warning("school#%s mail sent but not filed: %s", self.connection.id, failure_cause(error))
            return outcome

    def receipt(self, folder, uid, send, confirmed=False, request_id="", expect=None):
        folder = folder_id(folder)
        uid = mail.clean_uid(uid)
        if not send:
            def decline(imap):
                self._check_expected(imap, folder, [uid], expect)
                mail_manage.set_flag(imap, folder, [uid], mail_compose.MDN_SENT, True)

            self._run("receipt mark", decline)
            self._forget_detail(folder, [uid])
            return {"ok": True, "sent": False, "folder": folder, "uid": uid}
        if not confirmed:
            raise MailConfirmRequired()
        return self._once(mail_compose.request_id_of(request_id), lambda: self._send_receipt(folder, uid, expect))

    def _send_receipt(self, folder, uid, expect):
        host = self.school_host()

        def check(imap):
            self._check_expected(imap, folder, [uid], expect)
            return mail_structure.fetch_head(imap, folder, uid)["flags"]

        flags = self._run("receipt check", check)
        if mail_compose.MDN_SENT.lower() in [flag.lower() for flag in flags]:
            return {"ok": True, "sent": False, "already": True, "folder": folder, "uid": uid}
        self._forget_detail(folder, [uid])
        detail = self.message(folder, uid)
        sender = self.senders()[0]
        message, target = mail_compose.receipt_message(detail, sender, host)
        self._submit(host, message, sender["address"], [target])
        self._run("receipt mark", lambda imap: mail_manage.set_flag(imap, folder, [uid], mail_compose.MDN_SENT, True))
        self._forget_detail(folder, [uid])
        return {"ok": True, "sent": True, "folder": folder, "uid": uid, "to": target}
