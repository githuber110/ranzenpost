import logging
import re
import socket
import ssl
from urllib.parse import urljoin, urlsplit

from . import valueshape
from .failure import error_kind, failure_cause
from .iserv import mail_web
from .pageshape import html_skeleton
from .scriptscan import script_endpoints, script_sources

logger = logging.getLogger(__name__)

MAIL_HEAD = "### Mail interface"
PATH_WORD = re.compile(r"^(?:[A-Za-z][A-Za-z0-9_-]{0,39}|<expr>|\{[a-z][A-Za-z0-9_]{0,30}\})$")
FOLDER_TYPE = re.compile(r"^[a-z]{2,12}$")
PROTOCOL_WORD = re.compile(r"^[A-Za-z0-9=+_./:-]{1,40}$")
API_MARKS = ("/api", "/preview")
FEATURE_MARKS = ("report", "abuse", "spam", "junk", "todo", "tag", "settings")
ASSET_ENDINGS = (".js", ".mjs", ".css", ".map")
MAX_PATHS = 40
MAX_SCRIPTS = 40
MAIL_ROOT = "/iserv/mail/"
CHUNK = re.compile(r"[\"'`]((?:\.{1,2}/|/iserv/mail/)[A-Za-z0-9_./-]{1,160}\.m?js)[\"'`]")
REPORT_PAGES = ("/iserv/mail/settings/tags", "/iserv/mail/settings/general", "/iserv/account/settings")
MAX_PAGE_LINES = 40
SCRIPT_BYTES = 2 * 1024 * 1024
SCRIPT_SECONDS = 20
SIEVE_PORT = 4190
PROBE_SECONDS = 8
MAX_LINES = 20
ID_DIGITS = 3
MAX_FIELDS = 30
FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_\[\]]{0,80}$")


def path_words(path):
    parts = [part for part in str(path or "").split("?")[0].split("/")[1:] if part]
    return bool(parts) and parts[0] == "iserv" and all(PATH_WORD.match(part) and sum(char.isdigit() for char in part) < ID_DIGITS for part in parts)


def shown_path(path):
    text = str(path or "")
    return text.split("?")[0] if path_words(text) else valueshape.link_shape(text)


def _key_shape(key):
    text = str(key)
    return text if re.match(r"^[A-Za-z][A-Za-z0-9_]{0,40}$", text) else valueshape.safe_key(text)


def config_paths(value, trail=""):
    found = []
    if isinstance(value, dict):
        for key, inner in value.items():
            found.extend(config_paths(inner, (trail + "." if trail else "") + _key_shape(key)))
    elif isinstance(value, list):
        for inner in value:
            found.extend(config_paths(inner, trail + "[]"))
    elif isinstance(value, str) and value.startswith("/"):
        found.append((trail, value))
    return found


def _folder_entries(value):
    found = []
    if isinstance(value, dict):
        if "mailboxId" in value and "type" in value:
            found.append(value)
        for inner in value.values():
            found.extend(_folder_entries(inner))
    elif isinstance(value, list):
        for inner in value:
            found.extend(_folder_entries(inner))
    return found


def php_data_lines(html):
    present, data = mail_web.read_php_data(html)
    if not present:
        return ["- #php-data: not on the page"]
    if data is None:
        return ["- #php-data: unreadable"]
    lines = []
    config = data.get(mail_web.SERVER_CONFIG)
    paths = config_paths(config if isinstance(config, (dict, list)) else {}, mail_web.SERVER_CONFIG)
    lines.append("- #php-data serverConfig paths: %d" % len(paths))
    for trail, path in paths[:MAX_PATHS]:
        lines.append("  - %s: %s" % (trail, shown_path(path)))
    folders = _folder_entries(data)
    types = sorted({str(entry.get("type")) for entry in folders if FOLDER_TYPE.match(str(entry.get("type") or ""))})
    lines.append("- #php-data folders: %d (types: %s)" % (len(folders), ", ".join(types) or "-"))
    other = sorted({path for _trail, path in config_paths({key: value for key, value in data.items() if key != mail_web.SERVER_CONFIG}) if path.startswith("/iserv/")})
    if other:
        lines.append("- #php-data other paths: " + " | ".join(shown_path(path) for path in other[:MAX_PATHS]))
    return lines


def script_api_lines(texts):
    found = []
    features = []
    for text in texts:
        for _method, pattern, _label in script_endpoints(text or "", "mail"):
            if not pattern.startswith("/iserv/"):
                continue
            shown = shown_path(pattern)
            if any(mark in pattern for mark in API_MARKS):
                if shown not in found:
                    found.append(shown)
            elif any(mark in pattern.casefold() for mark in FEATURE_MARKS) and not pattern.endswith(ASSET_ENDINGS) and shown not in features:
                features.append(shown)
    lines = ["- Mail app API paths in scripts: " + (" | ".join(found[:MAX_PATHS]) or "none")]
    if features:
        lines.append("- Mail app paths for reports, to-do, tags and settings: " + " | ".join(features[:MAX_PATHS]))
    return lines


def chunk_paths(text, script_path):
    found = []
    for match in CHUNK.finditer(text or ""):
        path = urlsplit(urljoin("https://mail.invalid" + script_path, match.group(1))).path
        if path.startswith(MAIL_ROOT) and path not in found:
            found.append(path)
    return found


def _script_texts(fetcher, page):
    reader = getattr(fetcher, "fetch_capped", None)
    if not callable(reader):
        return []
    texts = []
    queue = [path for path in script_sources(getattr(page, "text", "") or "", str(getattr(page, "url", "") or "")) if "/mail/" in path]
    seen = []
    while queue and len(seen) < MAX_SCRIPTS:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.append(path)
        try:
            body = reader(path, SCRIPT_BYTES, SCRIPT_SECONDS)
        except Exception as error:
            logger.info("mail report: script not read: %s", failure_cause(error))
            continue
        if int(getattr(body, "status_code", 0) or 0) == 200:
            text = getattr(body, "text", "") or ""
            texts.append(text)
            queue.extend(chunk for chunk in chunk_paths(text, path.split("?", 1)[0]) if chunk not in seen and chunk not in queue)
    return texts


def form_shape_lines(skeleton):
    found = []
    inside = False
    for line in skeleton:
        if line.startswith("- "):
            inside = line.startswith("- Form")
        if inside:
            found.append(line)
    return found


def report_page_lines(fetcher):
    lines = []
    for path in REPORT_PAGES:
        try:
            page = fetcher.fetch(path)
        except Exception as error:
            logger.info("mail report: page not read: %s", failure_cause(error))
            lines.append("- Mail page %s: not read (%s)" % (path, error_kind(error)))
            continue
        status = int(getattr(page, "status_code", 0) or 0)
        final = urlsplit(str(getattr(page, "url", "") or "")).path
        lines.append("- Mail page %s: HTTP %d, final %s" % (path, status, shown_path(final) if final else "-"))
        if status != 200:
            continue
        html = getattr(page, "text", "") or ""
        skeleton = html_skeleton(html, shown_path)
        shape = form_shape_lines(skeleton)
        links = [line for line in skeleton if line.startswith("- Links: ")]
        mail_links = [part for part in links[0][len("- Links: "):].split(" | ") if part.startswith(MAIL_ROOT)] if links else []
        lines.extend("  " + line for line in shape[:MAX_PAGE_LINES])
        if mail_links:
            lines.append("  - mail links: " + " | ".join(mail_links[:MAX_PATHS]))
    return lines


def web_lines(fetcher):
    if fetcher is None:
        return ["- Web mail page: not read, no session"]
    try:
        page = fetcher.fetch(mail_web.MAIL_PAGE)
    except Exception as error:
        logger.info("mail report: web mail page not read: %s", failure_cause(error))
        return ["- Web mail page: not read (%s)" % error_kind(error)]
    status = int(getattr(page, "status_code", 0) or 0)
    lines = ["- Web mail page: HTTP %d" % status]
    if status != 200:
        return lines
    lines.extend(php_data_lines(getattr(page, "text", "") or ""))
    texts = _script_texts(fetcher, page)
    lines.append("- Mail scripts read: %d" % len(texts))
    lines.extend(script_api_lines(texts))
    lines.extend(report_page_lines(fetcher))
    return lines


def _words(values):
    return ", ".join(sorted({str(value) for value in values if PROTOCOL_WORD.match(str(value))})) or "-"


def imap_lines(structure):
    if not isinstance(structure, dict):
        return ["- IMAP: not read"]
    if structure.get("error"):
        return ["- IMAP: %s" % structure["error"]]
    lines = ["- IMAP: signed in, capabilities: %s" % _words(structure.get("capabilities") or [])]
    lines.append("- IMAP folders: %d, roles: %s, delimiters: %s" % (
        structure.get("folders", 0), _words(structure.get("roles") or []), _words(structure.get("delimiters") or [])))
    lines.append("- IMAP inbox: %s mails, %s unread" % (structure.get("total", "-"), structure.get("unread", "-")))
    newest = structure.get("newest")
    if isinstance(newest, dict):
        lines.append("- IMAP newest mail: %d headers, flags %s, keywords %d, parts %s, attachments %d" % (
            newest.get("headers", 0), _words(newest.get("flags") or []), newest.get("keywords", 0),
            newest.get("tree") or "-", newest.get("attachments", 0)))
    return lines


SIEVE_NOT_REACHED = "- ManageSieve %d: not reached" % SIEVE_PORT


def greeting_lines(host, connect=None):
    connect = connect or _sieve_greeting
    try:
        words = connect(host)
    except (OSError, ssl.SSLError) as error:
        logger.info("mail report: sieve greeting not read: %s", failure_cause(error))
        return ["%s (%s)" % (SIEVE_NOT_REACHED, error_kind(error))]
    return ["- ManageSieve %d: %s" % (SIEVE_PORT, _words(words))]


def _sieve_greeting(host):
    words = []
    with socket.create_connection((host, SIEVE_PORT), timeout=PROBE_SECONDS) as raw:
        reader = raw.makefile("rb")
        for _ in range(MAX_LINES):
            line = reader.readline(512).decode("utf-8", "replace").strip()
            if not line or line.upper().startswith(("OK", "NO", "BYE")):
                break
            parts = [part.strip('"') for part in line.split('" "')]
            words.append(parts[0])
            if parts[0].upper() != "IMPLEMENTATION" and len(parts) > 1:
                words.extend(parts[1].split())
    return words


def field_name(name):
    text = str(name or "")
    if FIELD_NAME.match(text) and sum(char.isdigit() for char in text) < ID_DIGITS:
        return text
    return valueshape.safe_key(text)


def _field_shape(field):
    extra = ""
    if field.get("options") is not None:
        extra = " options %d" % len(field["options"])
    if field.get("choices") is not None:
        extra = " choices %d" % len(field["choices"])
    return "%s %s (label len %d)%s" % (field["kind"], field_name(field["name"]), len(field.get("label") or ""), extra)


def form_lines(form):
    lines = ["    - form #%d %s %s -> %s, token %s" % (
        form["index"], field_name(form.get("name")) or "-", form["method"], shown_path(urlsplit(form["action"]).path), "yes" if any("token" in entry["name"].lower() for entry in form["hidden"]) else "no")]
    for field in form["fields"][:MAX_FIELDS]:
        lines.append("      - " + _field_shape(field))
    for collection in form["collections"]:
        lines.append("      - collection: entries %d, prototype fields: %s" % (len(collection["entries"]), ", ".join(_field_shape(field) for field in collection["fields"][:MAX_FIELDS])))
    return lines


def web_settings_lines(structure):
    if not isinstance(structure, dict):
        return ["- Mail settings: not read"]
    if structure.get("error"):
        return ["- Mail settings: %s" % structure["error"]]
    lines = []
    account = structure.get("account")
    if account is None:
        lines.append("- Mail account data: no #php-data")
    else:
        lines.append("- Mail account data: page size %s, tags %d (with colour %d), addresses %d, display name %s, auto archive %d, flags: %s" % (
            account.get("page_size") or "-", len(account["tags"]), len([tag for tag in account["tags"] if tag.get("color")]),
            len(account["addresses"]), "yes" if account.get("display_name") else "no", len(account["auto_archive"]),
            _words(account["flags"].keys())))
    lines.append("- Mail settings pages probed: %d" % len(structure.get("probes") or []))
    for probe in structure.get("probes") or []:
        lines.append("  - %s (%s): %s" % (shown_path(probe["path"]), "guessed" if probe["guessed"] else "linked", probe["verdict"]))
        for form in probe.get("forms") or []:
            lines.extend(form_lines(form))
    event = structure.get("event") or {}
    if event:
        lines.append("- Calendar entry form %s (%s): %s" % (
            shown_path(event.get("path") or "-"), "named on the calendar page" if event.get("found") else "known place",
            "not read (%s)" % event["error"] if event.get("error") else "forms %d" % len(event.get("forms") or [])))
        for key, path in event.get("routes") or []:
            lines.append("  - route %s: %s" % (_key_shape(key), shown_path(path)))
        for form in event.get("forms") or []:
            lines.extend(form_lines(form))
    for lookup in structure.get("lookups") or []:
        for param, response in lookup["answers"]:
            lines.append("- Recipient lookup %s ?%s=: %s" % (shown_path(lookup["path"]), param, _answer_shape(response)))
    return lines


def _answer_shape(response):
    status = int(getattr(response, "status_code", 0) or 0)
    try:
        payload = response.json()
    except (ValueError, AttributeError):
        return "HTTP %d, no json" % status
    first = payload[0] if isinstance(payload, list) and payload else payload
    keys = sorted(first.keys()) if isinstance(first, dict) else []
    kind = "list len %d" % len(payload) if isinstance(payload, list) else type(payload).__name__
    return "HTTP %d json %s, keys: %s" % (status, kind, ", ".join(_key_shape(key) for key in keys[:20]) or "-")


def sieve_lines(structure):
    if not isinstance(structure, dict):
        return ["- Sieve scripts: not read"]
    if structure.get("error"):
        return ["- Sieve scripts: %s" % structure["error"]]
    scripts = structure.get("scripts") or []
    lines = ["- Sieve scripts: %d" % len(scripts)]
    for entry in scripts:
        lines.append("  - %s%s, extensions: %s" % (field_name(entry["name"]), " (active)" if entry.get("active") else "", _words(entry.get("extensions") or [])))
    return lines


def mail_lines(fetcher, connection, greet=None):
    lines = [MAIL_HEAD]
    lines.extend(web_lines(fetcher))
    reader = getattr(connection, "mail", None)
    if not callable(reader):
        lines.append("- IMAP: not read")
        return lines
    try:
        service = reader()
        structure = service.structure()
    except Exception as error:
        logger.info("mail report: imap not read: %s", failure_cause(error))
        structure = {"error": "not read (%s)" % error_kind(error)}
        service = None
    lines.extend(imap_lines(structure))
    host = service.school_host() if service is not None else ""
    reached = True
    if host:
        greeting = greeting_lines(host, greet)
        reached = not any(line.startswith(SIEVE_NOT_REACHED) for line in greeting)
        lines.extend(greeting)
    if service is not None and not reached:
        lines.extend(sieve_lines({"error": "not read (port not reached)"}))
    elif service is not None:
        try:
            sieve_structure = service.sieve_structure()
        except Exception as error:
            logger.info("mail report: sieve not read: %s", failure_cause(error))
            sieve_structure = {"error": "not read (%s)" % error_kind(error)}
        lines.extend(sieve_lines(sieve_structure))
    web = getattr(connection, "mail_web", None)
    if callable(web):
        try:
            settings_structure = web().structure()
        except Exception as error:
            logger.info("mail report: mail settings not read: %s", failure_cause(error))
            settings_structure = {"error": "not read (%s)" % error_kind(error)}
        lines.extend(web_settings_lines(settings_structure))
    return lines
