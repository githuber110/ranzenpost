import json
import re
import uuid

import requests
from bs4 import BeautifulSoup

BOOTSTRAP_MARKER = "messenger_authentication"
AUTH_FIELDS = (
    "access_token",
    "device_id",
    "home_server",
    "user_id",
    "iserv_token",
    "iserv_cryptkey",
)

MATRIX_SYNC_PATH = "/_matrix/client/v3/sync"
MATRIX_MESSAGES_PATH = "/_matrix/client/v3/rooms/{room_id}/messages"
MATRIX_SEND_PATH = "/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}"
MATRIX_MEDIA_PATH = "/_matrix/client/v1/media/download/{server_name}/{media_id}"

FORBIDDEN_MATRIX_PATH_FRAGMENTS = ("/read_markers", "/receipt/")

MXC_RE = re.compile(r"^mxc://([^/]+)/(.+)$")


class BootstrapNotFoundError(Exception):
    pass


class MatrixError(Exception):
    pass


class MatrixAuthError(MatrixError):
    pass


class ForbiddenMatrixCallError(Exception):
    pass


def _candidate_objects(text):
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if isinstance(obj, dict):
            yield obj


def _find_bootstrap(node):
    if isinstance(node, dict):
        candidate = node.get(BOOTSTRAP_MARKER)
        if isinstance(candidate, dict):
            return candidate
        for value in node.values():
            found = _find_bootstrap(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_bootstrap(item)
            if found is not None:
                return found
    return None


def parse_bootstrap(html):
    soup = BeautifulSoup(html or "", "html.parser")
    for script in soup.find_all("script"):
        text = script.string
        if text is None:
            text = script.get_text()
        if not text or BOOTSTRAP_MARKER not in text:
            continue
        for candidate in _candidate_objects(text):
            auth = _find_bootstrap(candidate)
            if auth is None:
                continue
            cleaned = {field: str(auth.get(field) or "") for field in AUTH_FIELDS}
            if cleaned["access_token"] and cleaned["home_server"] and cleaned["user_id"]:
                return cleaned
    raise BootstrapNotFoundError("messenger bootstrap data not found")


def parse_mxc(url):
    match = MXC_RE.match(url or "")
    if not match:
        return None
    return match.group(1), match.group(2)


def new_txn_id():
    return uuid.uuid4().hex


def build_text_message(body):
    return {"msgtype": "m.text", "body": body}


class MatrixClient:
    def __init__(self, base_url, access_token, session=None, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.session = session or requests.Session()
        self.timeout = timeout

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def _guard(self, path):
        for fragment in FORBIDDEN_MATRIX_PATH_FRAGMENTS:
            if fragment in path:
                raise ForbiddenMatrixCallError(path)

    def _get(self, path, params=None):
        self._guard(path)
        response = self.session.get(
            f"{self.base_url}{path}", headers=self._headers(), params=params, timeout=self.timeout
        )
        if response.status_code == 401:
            raise MatrixAuthError("matrix token rejected")
        return response

    def _put(self, path, json_body):
        self._guard(path)
        response = self.session.put(
            f"{self.base_url}{path}", headers=self._headers(), json=json_body, timeout=self.timeout
        )
        if response.status_code == 401:
            raise MatrixAuthError("matrix token rejected")
        return response

    def sync(self, since=None, timeout_ms=0):
        params = {"timeout": timeout_ms}
        if since:
            params["since"] = since
        return self._get(MATRIX_SYNC_PATH, params=params)

    def room_messages(self, room_id, before_token=None, limit=30):
        params = {"dir": "b", "limit": limit}
        if before_token:
            params["from"] = before_token
        return self._get(MATRIX_MESSAGES_PATH.format(room_id=room_id), params=params)

    def send_message(self, room_id, txn_id, body):
        return self._put(MATRIX_SEND_PATH.format(room_id=room_id, txn_id=txn_id), body)

    def fetch_media(self, server_name, media_id):
        return self._get(MATRIX_MEDIA_PATH.format(server_name=server_name, media_id=media_id))


def _all_state_events(room):
    events = list(((room.get("state") or {}).get("events")) or [])
    events += [
        event
        for event in ((room.get("timeline") or {}).get("events")) or []
        if "state_key" in event
    ]
    return events


def _room_name(state_events):
    for event in state_events:
        if event.get("type") == "m.room.name":
            name = (event.get("content") or {}).get("name")
            if name:
                return name
    return ""


def _room_members(state_events, own_user_id):
    members = {}
    for event in state_events:
        if event.get("type") != "m.room.member":
            continue
        if (event.get("content") or {}).get("membership") != "join":
            continue
        user_id = event.get("state_key")
        if not user_id or user_id == own_user_id:
            continue
        display_name = (event.get("content") or {}).get("displayname") or user_id
        members[user_id] = display_name
    return sorted(members.values())


def _last_message_event(room):
    events = ((room.get("timeline") or {}).get("events")) or []
    for event in reversed(events):
        if event.get("type") == "m.room.message":
            return event
    return None


def _preview(event):
    if event is None:
        return ""
    content = event.get("content") or {}
    return str(content.get("body") or "")


def parse_room_list(sync_body, own_user_id=None):
    rooms = []
    joined = ((sync_body or {}).get("rooms") or {}).get("join") or {}
    for room_id, room in joined.items():
        state_events = _all_state_events(room)
        name = _room_name(state_events)
        members = _room_members(state_events, own_user_id)
        last_event = _last_message_event(room)
        unread = int(((room.get("unread_notifications") or {}).get("notification_count")) or 0)
        rooms.append(
            {
                "room_id": room_id,
                "name": name or ", ".join(members),
                "members": members,
                "last_message": _preview(last_event),
                "last_message_at": last_event.get("origin_server_ts") if last_event else None,
                "unread_count": unread,
            }
        )
    rooms.sort(key=lambda entry: entry["last_message_at"] or 0, reverse=True)
    return rooms


def total_unread(sync_body):
    joined = ((sync_body or {}).get("rooms") or {}).get("join") or {}
    return sum(
        int((room.get("unread_notifications") or {}).get("notification_count") or 0)
        for room in joined.values()
    )


def _text_or_media_message(event, media_url_builder):
    content = event.get("content") or {}
    msgtype = content.get("msgtype")
    base = {
        "event_id": event.get("event_id"),
        "sender": event.get("sender"),
        "sent_at": event.get("origin_server_ts"),
    }
    if msgtype == "m.text":
        base.update({"kind": "text", "body": str(content.get("body") or "")})
        return base
    if msgtype in ("m.image", "m.file"):
        info = content.get("info") or {}
        base.update(
            {
                "kind": "image" if msgtype == "m.image" else "file",
                "body": str(content.get("body") or ""),
                "media_url": media_url_builder(content.get("url") or ""),
                "mimetype": info.get("mimetype", ""),
                "size": info.get("size"),
            }
        )
        return base
    return None


def _system_message(event):
    content = event.get("content") or {}
    return {
        "event_id": event.get("event_id"),
        "sender": event.get("sender"),
        "sent_at": event.get("origin_server_ts"),
        "kind": "system",
        "system_kind": content.get("membership", ""),
    }


def _parse_message_event(event, media_url_builder):
    event_type = event.get("type")
    if event_type == "m.room.message":
        return _text_or_media_message(event, media_url_builder)
    if event_type == "m.room.member":
        return _system_message(event)
    return None


def parse_room_messages(messages_body, media_url_builder=None):
    builder = media_url_builder or (lambda url: "")
    events = (messages_body or {}).get("chunk") or []
    parsed = [_parse_message_event(event, builder) for event in events]
    parsed = [entry for entry in parsed if entry is not None]
    return {
        "messages": parsed,
        "before": (messages_body or {}).get("end", ""),
    }
