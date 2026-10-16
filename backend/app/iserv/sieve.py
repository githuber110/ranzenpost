import base64
import re
import socket

from .errors import DataError
from .mail import imap_string, tls_context

SIEVE_PORT = 4190
SIEVE_TIMEOUT_SECONDS = 20
REQUIRE = re.compile(r"\brequire\s+(\[[^\]]*\]|\"[^\"]*\")", re.IGNORECASE)
NAME_PATTERN = re.compile(r"^[^\x00-\x1f\x7f\"\\]{1,64}$")
LITERAL = re.compile(rb"^\{(\d+)\+?\}$")


class SieveError(DataError):
    def __init__(self, note="sieve failed", message_key="", detail=None):
        super().__init__(note, message_key=message_key, detail=detail)


class SieveUnreachable(SieveError):
    def __init__(self, note="sieve unreachable"):
        super().__init__(note)


class SieveSignInRefused(SieveError):
    def __init__(self, note="sieve sign-in refused"):
        super().__init__(note)


def quote(text):
    return imap_string(str(text))


def clean_name(name):
    text = str(name or "").strip()
    if not NAME_PATTERN.match(text):
        raise SieveError("invalid script name")
    return text


def required_extensions(script):
    found = []
    for match in REQUIRE.finditer(str(script or "")):
        for name in re.findall(r'"([A-Za-z0-9:._-]{1,40})"', match.group(1)):
            if name not in found:
                found.append(name)
    return found


class SocketTransport:
    def __init__(self, host, port=SIEVE_PORT, timeout=SIEVE_TIMEOUT_SECONDS):
        self.host = host
        self.raw = socket.create_connection((host, port), timeout=timeout)
        self.reader = self.raw.makefile("rb")

    def readline(self):
        line = self.reader.readline(65536)
        if not line:
            raise OSError("sieve connection closed")
        return line

    def read(self, size):
        data = self.reader.read(size)
        if data is None or len(data) < size:
            raise OSError("sieve connection closed")
        return data

    def write(self, data):
        self.raw.sendall(data)

    def starttls(self):
        self.reader.close()
        self.raw = tls_context().wrap_socket(self.raw, server_hostname=self.host)
        self.reader = self.raw.makefile("rb")

    def close(self):
        try:
            self.reader.close()
        finally:
            self.raw.close()


def _strings(line):
    found = []
    for match in re.finditer(rb'"((?:[^"\\]|\\.)*)"|([^\s"]+)', line):
        if match.group(1) is not None:
            found.append(re.sub(rb"\\(.)", rb"\1", match.group(1)).decode("utf-8", "replace"))
        else:
            found.append(match.group(2).decode("utf-8", "replace"))
    return found


class SieveClient:
    def __init__(self, transport):
        self.transport = transport
        self.capabilities = {}

    def _response(self):
        lines = []
        while True:
            line = self.transport.readline().rstrip(b"\r\n")
            literal = LITERAL.match(line)
            if literal:
                lines.append(("literal", self.transport.read(int(literal.group(1)))))
                self.transport.readline()
                continue
            upper = line.upper()
            if upper.startswith((b"OK", b"NO", b"BYE")):
                status = upper.split(b" ", 1)[0].decode("ascii")
                text = line[len(status):].strip()
                tail = b""
                trailing = LITERAL.search(text) if text.endswith(b"}") else None
                if trailing:
                    tail = self.transport.read(int(trailing.group(1)))
                    self.transport.readline()
                    text = text[:trailing.start()].strip()
                reason = " ".join(_strings(text)) + (tail.decode("utf-8", "replace") if tail else "")
                return status, lines, reason
            lines.append(("line", line))

    def _command(self, text, payload=None):
        if payload is None:
            self.transport.write(text.encode("utf-8") + b"\r\n")
        else:
            self.transport.write(text.encode("utf-8") + b" {%d+}\r\n" % len(payload) + payload + b"\r\n")
        return self._response()

    def _read_capabilities(self, lines):
        capabilities = {}
        for kind, line in lines:
            if kind != "line":
                continue
            parts = _strings(line)
            if parts:
                capabilities[parts[0].upper()] = parts[1] if len(parts) > 1 else ""
        self.capabilities = capabilities
        return capabilities

    def greet(self):
        status, lines, _reason = self._response()
        if status != "OK":
            raise SieveUnreachable("sieve greeting refused")
        return self._read_capabilities(lines)

    def starttls(self):
        if "STARTTLS" not in self.capabilities:
            raise SieveUnreachable("sieve offers no tls")
        status, _lines, _reason = self._command("STARTTLS")
        if status != "OK":
            raise SieveUnreachable("sieve tls refused")
        self.transport.starttls()
        status, lines, _reason = self._response()
        if status == "OK" and lines:
            self._read_capabilities(lines)
        elif status != "OK":
            raise SieveUnreachable("sieve tls greeting refused")

    def sign_in(self, username, password):
        token = base64.b64encode(b"\0" + username.encode("utf-8") + b"\0" + password.encode("utf-8")).decode("ascii")
        status, _lines, reason = self._command('AUTHENTICATE "PLAIN" ' + quote(token))
        if status != "OK":
            raise SieveSignInRefused(reason or "sieve sign-in refused")

    def scripts(self):
        status, lines, reason = self._command("LISTSCRIPTS")
        if status != "OK":
            raise SieveError(reason or "sieve list refused")
        found = []
        for kind, line in lines:
            if kind != "line":
                continue
            parts = _strings(line)
            if parts:
                found.append({"name": parts[0], "active": len(parts) > 1 and parts[1].upper() == "ACTIVE"})
        return found

    def script(self, name):
        status, lines, reason = self._command("GETSCRIPT " + quote(clean_name(name)))
        if status != "OK":
            raise SieveError(reason or "sieve script refused")
        for kind, value in lines:
            if kind == "literal":
                return value.decode("utf-8", "replace").replace("\r\n", "\n")
        return ""

    def logout(self):
        try:
            self._command("LOGOUT")
        except (OSError, SieveError):
            pass
        self.transport.close()


def open_sieve(host, username, password, transport=None):
    try:
        transport = transport or SocketTransport(host)
    except OSError as error:
        raise SieveUnreachable() from error
    client = SieveClient(transport)
    try:
        client.greet()
        client.starttls()
        client.sign_in(username, password)
    except OSError as error:
        transport.close()
        raise SieveUnreachable() from error
    except SieveError:
        transport.close()
        raise
    return client
