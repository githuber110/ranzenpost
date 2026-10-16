import base64
import imaplib
import re
import smtplib
from datetime import date, datetime, timezone
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import parsedate_to_datetime

PDF_BYTES = b"%PDF-1.4 fixture"
PNG_BYTES = b"\x89PNG\r\n\x1a\nfixture"
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def html_mail(date_text="Tue, 13 Oct 2026 08:15:00 +0200", subject="Ausflug am Freitag"):
    message = EmailMessage()
    message["From"] = "Class Teacher <teacher@school.example>"
    message["To"] = "Parent Example <parent@school.example>, other@school.example"
    message["Cc"] = "Office <office@school.example>"
    message["Subject"] = subject
    message["Date"] = date_text
    message["Message-ID"] = "<trip-1@school.example>"
    message["Disposition-Notification-To"] = "Class Teacher <teacher@school.example>"
    message.set_content("Plain alternative")
    message.add_alternative(
        '<p>Hello <b>all</b></p><script>alert(1)</script>'
        '<p><a href="https://school.example/iserv/file/-/Files">Files</a> '
        '<a href="https://example.org/trip">Trip</a> <a href="/iserv/mail">Mail</a></p>'
        '<img src="cid:logo"><img src="https://example.org/pic.png">',
        subtype="html",
    )
    message.add_attachment(PDF_BYTES, maintype="application", subtype="pdf", filename="Elternbrief Ausflug.pdf")
    message.add_attachment(PNG_BYTES, maintype="image", subtype="png", filename="map.png")
    return message.as_bytes()


def plain_mail(date_text="Wed, 14 Oct 2026 09:00:00 +0200"):
    message = EmailMessage()
    message["From"] = "=?utf-8?q?Sch=C3=BClerb=C3=BCro?= <office@school.example>"
    message["To"] = "parent@school.example"
    message["Subject"] = "=?utf-8?q?R=C3=BCckmeldung?="
    message["Date"] = date_text
    message["Message-ID"] = "<office-2@school.example>"
    message.set_content("Line one\nLine two\n")
    return message.as_bytes()


def sent_mail():
    message = EmailMessage()
    message["From"] = "parent@school.example"
    message["To"] = "Class Teacher <teacher@school.example>"
    message["Subject"] = "Re: Ausflug"
    message["Date"] = "Mon, 12 Oct 2026 18:00:00 +0200"
    message.set_content("Thanks")
    return message.as_bytes()


def default_folders():
    return {
        "INBOX": [
            {"uid": 7, "flags": {"\\Seen"}, "raw": html_mail()},
            {"uid": 9, "flags": set(), "raw": plain_mail()},
        ],
        "Sent": [{"uid": 3, "flags": {"\\Seen", "\\Answered"}, "raw": sent_mail()}],
        "Drafts": [],
        "Archive": [],
        "Trash": [],
        "INBOX/Projekt &AMQ-": [],
    }


SPECIAL = {"Sent": "\\Sent", "Drafts": "\\Drafts", "Archive": "\\Archive", "Trash": "\\Trash", "Junk": "\\Junk"}


def _unquote(text):
    text = text if isinstance(text, str) else text.decode()
    if text.startswith('"') and text.endswith('"'):
        return re.sub(r"\\(.)", r"\1", text[1:-1])
    return text


def _day(text):
    day, month, year = text.split("-")
    return date(int(year), MONTHS.index(month) + 1, int(day))


def fetch_item_names(text):
    text = text.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    names = []
    current = ""
    depth = 0
    for char in text:
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        if char == " " and depth == 0:
            if current:
                names.append(current)
            current = ""
            continue
        current += char
    if current:
        names.append(current)
    return names


def _quoted(text):
    return '"%s"' % str(text).replace("\\", "\\\\").replace('"', '\\"')


def _param_list(pairs):
    pairs = [(key, value) for key, value in pairs if value]
    if not pairs:
        return "NIL"
    return "(" + " ".join("%s %s" % (_quoted(key), _quoted(value)) for key, value in pairs) + ")"


def _payload_bytes(part):
    payload = part.get_payload(decode=False)
    if isinstance(payload, list):
        return payload[0].as_bytes() if payload else b""
    return str(payload).encode("utf-8", "surrogateescape").replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def bodystructure(part):
    kind = part.get_content_type()
    main, sub = kind.split("/", 1)
    if part.is_multipart() and kind != "message/rfc822":
        children = "".join(bodystructure(child) for child in part.iter_parts())
        return "(%s %s %s NIL NIL NIL)" % (children, _quoted(sub.upper()), _param_list([("BOUNDARY", part.get_boundary())]))
    content_id = part.get("Content-ID")
    encoding = str(part.get("Content-Transfer-Encoding") or "7BIT").upper()
    body = _payload_bytes(part)
    params = _param_list([("CHARSET", part.get_content_charset()), ("NAME", part.get_param("name"))])
    disposition = part.get_content_disposition()
    filename = part.get_filename()
    dsp = "(%s %s)" % (_quoted(disposition.upper()), _param_list([("FILENAME", filename)])) if disposition else "NIL"
    basic = "%s %s %s %s NIL %s %d" % (_quoted(main.upper()), _quoted(sub.upper()), params, _quoted(content_id) if content_id else "NIL", _quoted(encoding), len(body))
    if main == "text":
        return "(%s %d NIL %s NIL NIL)" % (basic, body.count(b"\n") + 1, dsp)
    if kind == "message/rfc822":
        inner = part.get_payload()[0]
        return "(%s NIL %s %d NIL %s NIL NIL)" % (basic, bodystructure(inner), body.count(b"\n") + 1, dsp)
    return "(%s NIL %s NIL NIL)" % (basic, dsp)


def section_bytes(message, section):
    part = message
    for step in section.split("."):
        index = int(step) - 1
        if part.is_multipart() and part.get_content_type() != "message/rfc822":
            part = list(part.iter_parts())[index]
        elif index != 0:
            return b""
    return _payload_bytes(part)


def fetch_answer(number, entry, items):
    raw = entry["raw"].replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    message = message_from_bytes(raw, policy=policy.default)
    texts = []
    literals = []
    for name in items:
        upper = name.upper()
        if upper == "UID":
            texts.append("UID %d" % entry["uid"])
        elif upper == "FLAGS":
            texts.append("FLAGS (%s)" % " ".join(sorted(entry["flags"])))
        elif upper == "INTERNALDATE":
            texts.append('INTERNALDATE "14-Oct-2026 09:00:00 +0200"')
        elif upper == "RFC822.SIZE":
            texts.append("RFC822.SIZE %d" % len(raw))
        elif upper == "BODYSTRUCTURE":
            texts.append("BODYSTRUCTURE " + bodystructure(message))
        elif upper.startswith("BODY.PEEK["):
            inside = name[name.index("[") + 1:name.rindex("]")]
            partial = name[name.rindex("]") + 1:]
            if inside.upper().startswith("HEADER"):
                value = raw.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"
                key = "BODY[%s]" % inside
            elif inside == "":
                value = raw
                key = "BODY[]"
            else:
                value = section_bytes(message, inside)
                key = "BODY[%s]" % inside
            if partial:
                first, length = partial.strip("<>").split(".")
                value = value[int(first):int(first) + int(length)]
                key += "<%s>" % first
            literals.append((key, value))
        else:
            raise AssertionError(name)
    head = "%d (%s" % (number, " ".join(texts))
    answer = []
    for index, (key, value) in enumerate(literals):
        prefix = head + (" " if texts or index else "") if index == 0 else " "
        answer.append(((prefix + "%s {%d}" % (key, len(value))).encode(), value))
    if not literals:
        answer.append((head + ")").encode())
    else:
        answer.append(b")")
    return answer


class FakeImap:
    def __init__(self, password="p", folders=None, capabilities=("IMAP4REV1", "MOVE", "UIDPLUS", "SPECIAL-USE"), special=None):
        self.password = password
        self.special = dict(SPECIAL if special is None else special)
        self.folders = folders if folders is not None else default_folders()
        self.capabilities = tuple(capabilities)
        self.selected = None
        self.readonly = None
        self.calls = []
        self.logged_out = False
        self.literal = None
        self.next_uid = 100
        self.fetched = []

    def login(self, username, password):
        self.calls.append(("login", username))
        if password != self.password:
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Authentication failed.")
        return "OK", [b"Logged in"]

    def authenticate(self, mechanism, callback):
        token = callback(b"")
        self.calls.append(("authenticate", mechanism, token))
        if token.split(b"\0")[-1].decode("utf-8") != self.password:
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Authentication failed.")
        return "OK", [b"Logged in"]

    def list(self):
        self.calls.append(("list",))
        lines = []
        for name in self.folders:
            flags = ["\\HasNoChildren"]
            if name in self.special:
                flags.append(self.special[name])
            encoded = name.encode()
            if " " in name:
                lines.append((b'(%s) "/" {%d}' % (" ".join(flags).encode(), len(encoded)), encoded))
            else:
                lines.append(b'(%s) "/" %s' % (" ".join(flags).encode(), encoded))
        lines.append(b'(\\Noselect \\HasChildren) "/" Container')
        return "OK", lines

    def status(self, quoted, items):
        name = _unquote(quoted)
        listed = self.folders.get(name)
        if listed is None:
            return "NO", [b"Mailbox does not exist"]
        unseen = len([entry for entry in listed if "\\Seen" not in entry["flags"]])
        return "OK", [b'"%s" (MESSAGES %d UNSEEN %d)' % (name.encode(), len(listed), unseen)]

    def select(self, quoted, readonly=False):
        name = _unquote(quoted)
        self.calls.append(("select", name, readonly))
        if name not in self.folders:
            return "NO", [b"Mailbox does not exist"]
        self.selected = name
        self.readonly = readonly
        return "OK", [str(len(self.folders[name])).encode()]

    def create(self, quoted):
        name = _unquote(quoted)
        self.calls.append(("create", name))
        if name in self.folders:
            return "NO", [b"exists"]
        self.folders[name] = []
        return "OK", [b"created"]

    def subscribe(self, quoted):
        return "OK", [b""]

    def rename(self, old, new):
        old, new = _unquote(old), _unquote(new)
        self.calls.append(("rename", old, new))
        self.folders[new] = self.folders.pop(old)
        return "OK", [b"renamed"]

    def delete(self, quoted):
        name = _unquote(quoted)
        self.calls.append(("delete", name))
        self.folders.pop(name)
        return "OK", [b"deleted"]

    def append(self, quoted, flags, when, raw):
        name = _unquote(quoted)
        self.next_uid += 1
        parsed = set(flags.strip("()").split()) if flags else set()
        self.folders[name].append({"uid": self.next_uid, "flags": parsed, "raw": raw})
        self.calls.append(("append", name, flags))
        return "OK", [b"[APPENDUID 1 %d] Append completed." % self.next_uid]

    def _matches(self, entry, terms):
        message = message_from_bytes(entry["raw"], policy=policy.default)
        index = 0

        def one():
            nonlocal index
            key = terms[index].upper()
            index += 1
            if key == "ALL":
                return True
            if key == "OR":
                left = one()
                right = one()
                return left or right
            if key in ("SEEN", "UNSEEN"):
                return ("\\Seen" in entry["flags"]) == (key == "SEEN")
            if key == "FLAGGED":
                return "\\Flagged" in entry["flags"]
            if key in ("ANSWERED", "UNANSWERED"):
                return ("\\Answered" in entry["flags"]) == (key == "ANSWERED")
            value = terms[index]
            index += 1
            if key == "KEYWORD":
                return value in entry["flags"]
            if key == "UID":
                return str(entry["uid"]) in value.split(",")
            if key == "HEADER":
                wanted = _unquote(terms[index]).lower()
                index += 1
                return wanted in str(message[value] or "").lower()
            if key in ("SINCE", "BEFORE"):
                moment = parsedate_to_datetime(str(message["date"])).date() if message["date"] else date.today()
                return moment >= _day(value) if key == "SINCE" else moment < _day(value)
            needle = _unquote(value).lower()
            if key == "TEXT":
                return needle in entry["raw"].decode("utf-8", "replace").lower() or needle in str(message["subject"] or "").lower()
            if key == "BODY":
                body = message.get_body(preferencelist=("plain", "html"))
                return bool(body) and needle in body.get_content().lower()
            return needle in str(message[key.lower()] or "").lower()

        result = True
        while index < len(terms):
            result = one() and result
        return result

    def uid(self, command, *args):
        self.calls.append(("uid", command) + args)
        listed = self.folders[self.selected]
        if command == "SEARCH":
            terms = list(args[1:]) if args[0] is None else list(args[2:])
            if args[0] == "CHARSET":
                terms.append(self.literal.decode("utf-8"))
                self.literal = None
            return "OK", [b" ".join(str(entry["uid"]).encode() for entry in listed if self._matches(entry, terms))]
        if command == "FETCH":
            wanted = {int(part) for part in args[0].split(",")}
            items = fetch_item_names(args[1])
            if any(name.startswith("BODY[") for name in items):
                raise AssertionError("a fetch without PEEK would mark the mail read")
            data = []
            for number, entry in enumerate(listed, 1):
                if entry["uid"] in wanted:
                    data.extend(fetch_answer(number, entry, items))
                    self.fetched.append((entry["uid"], items))
            return "OK", data
        if self.readonly:
            return "NO", [b"Mailbox is read-only"]
        chosen = [entry for entry in listed if str(entry["uid"]) in args[0].split(",")]
        if command == "STORE":
            names = set(args[2].strip("()").split())
            for entry in chosen:
                if args[1].startswith("+"):
                    entry["flags"] |= names
                else:
                    entry["flags"] -= names
            return "OK", [None]
        if command in ("MOVE", "COPY"):
            target = _unquote(args[1])
            for entry in chosen:
                self.next_uid += 1
                self.folders[target].append({"uid": self.next_uid, "flags": set(entry["flags"]), "raw": entry["raw"]})
            if command == "MOVE":
                self.folders[self.selected] = [entry for entry in listed if entry not in chosen]
            return "OK", [b""]
        if command == "EXPUNGE":
            self.folders[self.selected] = [entry for entry in listed if not (entry in chosen and "\\Deleted" in entry["flags"])]
            return "OK", [b""]
        raise AssertionError(command)

    def logout(self):
        self.logged_out = True
        return "BYE", [b""]

    def stores(self):
        return [call for call in self.calls if call[:2] == ("uid", "STORE")]


class FakeSmtp:
    def __init__(self, password="p", failure=None, refuse=None):
        self.password = password
        self.failure = failure
        self.refuse = dict(refuse or {})
        self.sent = []
        self.signed_in = False
        self.quit_called = False

    def login(self, username, password):
        if password != self.password:
            raise smtplib.SMTPAuthenticationError(535, b"authentication failed")
        self.signed_in = True

    def docmd(self, command, argument):
        token = base64.b64decode(argument.split(" ", 1)[1])
        if token.split(b"\0")[-1].decode("utf-8") != self.password:
            return 535, b"authentication failed"
        self.signed_in = True
        return 235, b"ok"

    def send_message(self, message, from_addr=None, to_addrs=None):
        if self.failure is not None:
            raise self.failure
        assert self.signed_in
        raw = message.as_bytes()
        accepted = [address for address in to_addrs if address not in self.refuse]
        self.sent.append({"from": from_addr, "to": accepted, "raw": raw})
        return {address: answer for address, answer in self.refuse.items() if address in to_addrs}

    def quit(self):
        self.quit_called = True


def now_utc():
    return datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)


class FakeSieveTransport:
    def __init__(self, password="p", scripts=None, active="iserv", tls=True):
        self.password = password
        self.scripts = dict(scripts if scripts is not None else {"iserv": 'require ["fileinto"];\r\nif header :contains "subject" "Spam" { fileinto "Junk"; }\r\n'})
        self.active = active
        self.tls = tls
        self.secure = False
        self.signed_in = False
        self.buffer = b""
        self.sent = []
        self.closed = False
        self._queue(self._capabilities())

    def fresh(self):
        again = FakeSieveTransport(self.password, self.scripts, self.active, self.tls)
        again.scripts = self.scripts
        again.sent = self.sent
        return again

    def _capabilities(self):
        lines = ['"IMPLEMENTATION" "Dovecot Pigeonhole"', '"SIEVE" "fileinto reject envelope vacation"', '"SASL" "PLAIN"']
        if self.tls and not self.secure:
            lines.append('"STARTTLS"')
        return "\r\n".join(lines) + '\r\nOK "ready"\r\n'

    def _queue(self, text):
        self.buffer += text.encode("utf-8") if isinstance(text, str) else text

    def readline(self):
        if not self.buffer:
            raise OSError("closed")
        index = self.buffer.find(b"\n")
        line, self.buffer = self.buffer[:index + 1], self.buffer[index + 1:]
        return line

    def read(self, size):
        data, self.buffer = self.buffer[:size], self.buffer[size:]
        return data

    def starttls(self):
        self.secure = True

    def close(self):
        self.closed = True

    def write(self, data):
        self.sent.append(data)
        head = data.partition(b"\r\n")[0]
        words = re.findall(rb'"((?:[^"\\]|\\.)*)"|(\S+)', head)
        parts = [(quoted or bare).decode() for quoted, bare in words]
        command = parts[0].upper()
        if command == "STARTTLS":
            self._queue('OK "go"\r\n')
            self.secure = True
            self._queue(self._capabilities())
        elif command == "AUTHENTICATE":
            token = base64.b64decode(parts[2]).split(b"\0")
            if not self.secure or token[-1].decode() != self.password:
                self._queue('NO "Authentication failed."\r\n')
            else:
                self.signed_in = True
                self._queue('OK "Logged in."\r\n')
        elif command == "LISTSCRIPTS":
            lines = "".join('"%s"%s\r\n' % (name, " ACTIVE" if name == self.active else "") for name in self.scripts)
            self._queue(lines + 'OK "Listscripts completed."\r\n')
        elif command == "GETSCRIPT":
            body = self.scripts.get(parts[1])
            if body is None:
                self._queue('NO "Script does not exist."\r\n')
            else:
                raw = body.encode("utf-8")
                self._queue(b"{%d}\r\n" % len(raw) + raw + b"\r\nOK \"Getscript completed.\"\r\n")
        elif command == "LOGOUT":
            self._queue('OK "Logout completed."\r\n')
        else:
            self._queue('NO "unknown"\r\n')
