import json
import re
import uuid

import requests
from bs4 import BeautifulSoup

from .forms import parse_forms

BOOTSTRAP_MARKER = "messenger_authentication"
PRIVILEGE_MARKER = "messenger_user_privileges"
TEACHER_PRIVILEGE_FIELD = "canWriteToTeacher"
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
MATRIX_READ_MARKER_PATH = "/_matrix/client/v3/rooms/{room_id}/read_markers"

FORBIDDEN_MATRIX_PATH_FRAGMENTS = ("/read_markers", "/receipt/")
SANCTIONED_READ_MARKER_PATH = re.compile(r"^/_matrix/client/v3/rooms/[^/]+/read_markers$")

TEACHER_AUTOCOMPLETE_PATH = "/iserv/messenger/autocomplete/teacher"
TEACHER_AUTOCOMPLETE_TYPE = "userid"
TEACHER_ROOM_FORM_PATH = "/iserv/messenger/form/room/teacher_new"
TEACHER_ROOM_TOKEN_FIELD = "teacher_room[_token]"
TEACHER_ROOM_TEACHER_FIELD = "teacher_room[teacher_id]"
TEACHER_ROOM_CHILDREN_FIELD = "teacher_room[child_ids][]"
TEACHER_ROOM_PARENTS_FIELD = "teacher_room[add_other_parents]"

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


def _find_marked(node, marker):
    if isinstance(node, dict):
        candidate = node.get(marker)
        if isinstance(candidate, dict):
            return candidate
        for value in node.values():
            found = _find_marked(value, marker)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_marked(item, marker)
            if found is not None:
                return found
    return None


def _marked_objects(html, marker):
    soup = BeautifulSoup(html or "", "html.parser")
    for script in soup.find_all("script"):
        text = script.string
        if text is None:
            text = script.get_text()
        if not text or marker not in text:
            continue
        for candidate in _candidate_objects(text):
            found = _find_marked(candidate, marker)
            if found is not None:
                yield found


def parse_bootstrap(html):
    for auth in _marked_objects(html, BOOTSTRAP_MARKER):
        cleaned = {field: str(auth.get(field) or "") for field in AUTH_FIELDS}
        if cleaned["access_token"] and cleaned["home_server"] and cleaned["user_id"]:
            return cleaned
    raise BootstrapNotFoundError("messenger bootstrap data not found")


def parse_privileges(html):
    for privileges in _marked_objects(html, PRIVILEGE_MARKER):
        return {"can_write_to_teacher": bool(privileges.get(TEACHER_PRIVILEGE_FIELD))}
    return None


def parse_teacher_suggestions(payload):
    items = payload if isinstance(payload, list) else (payload or {}).get("results")
    suggestions = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or "").strip()
        label = str(item.get("label") or "").strip()
        if not value or not label:
            continue
        suggestions.append({"value": value, "label": label, "extra": str(item.get("extra") or "").strip()})
    return suggestions


def build_teacher_room_payload(token, teacher_value, child_ids, add_other_parents):
    payload = [
        (TEACHER_ROOM_TOKEN_FIELD, token),
        (TEACHER_ROOM_TEACHER_FIELD, teacher_value),
        (TEACHER_ROOM_PARENTS_FIELD, "1" if add_other_parents else "0"),
    ]
    payload.extend((TEACHER_ROOM_CHILDREN_FIELD, child_id) for child_id in child_ids)
    return payload


def find_teacher_room_token(html, base_url):
    for form in parse_forms(html or "", base_url):
        token = form.fields.get(TEACHER_ROOM_TOKEN_FIELD)
        if token:
            return str(token)
    return ""


def room_membership(sync_body, room_id):
    rooms = (sync_body or {}).get("rooms") or {}
    for membership in ("join", "invite", "leave"):
        if room_id in (rooms.get(membership) or {}):
            return membership
    return ""


def parse_mxc(url):
    match = MXC_RE.match(url or "")
    if not match:
        return None
    return match.group(1), match.group(2)


def new_txn_id():
    return uuid.uuid4().hex


def build_text_message(body):
    return {"msgtype": "m.text", "body": body}


def build_read_marker(event_id):
    return {"m.fully_read": event_id, "m.read": event_id}


class MatrixClient:
    def __init__(self, base_url, access_token, session=None, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.session = session or requests.Session()
        self.timeout = timeout

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def _guard(self, path, sanctioned=False):
        for fragment in FORBIDDEN_MATRIX_PATH_FRAGMENTS:
            if fragment not in path:
                continue
            if sanctioned and SANCTIONED_READ_MARKER_PATH.match(path):
                continue
            raise ForbiddenMatrixCallError(path)

    def _get(self, path, params=None):
        self._guard(path)
        response = self.session.get(
            f"{self.base_url}{path}", headers=self._headers(), params=params, timeout=self.timeout
        )
        if response.status_code == 401:
            raise MatrixAuthError("matrix token rejected")
        return response

    def _put(self, path, json_body, sanctioned=False):
        self._guard(path, sanctioned=sanctioned)
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

    def send_read_marker(self, room_id, event_id):
        return self._put(
            MATRIX_READ_MARKER_PATH.format(room_id=room_id),
            build_read_marker(event_id),
            sanctioned=True,
        )


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
    return members


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
        member_names = _room_members(state_events, own_user_id)
        members = sorted(member_names.values())
        last_event = _last_message_event(room)
        unread = int(((room.get("unread_notifications") or {}).get("notification_count")) or 0)
        rooms.append(
            {
                "room_id": room_id,
                "name": name or ", ".join(members),
                "members": members,
                "member_names": member_names,
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
