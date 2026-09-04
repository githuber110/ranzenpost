import re
import time
from urllib.parse import quote

import requests

from . import messages
from .iserv.errors import DataError, LoginError
from .iserv.messenger import (
    AUTH_FIELDS,
    TEACHER_AUTOCOMPLETE_PATH,
    TEACHER_AUTOCOMPLETE_TYPE,
    TEACHER_ROOM_FORM_PATH,
    BootstrapNotFoundError,
    MatrixAuthError,
    MatrixClient,
    build_teacher_room_payload,
    build_text_message,
    find_teacher_room_token,
    new_txn_id,
    parse_bootstrap,
    parse_mxc,
    parse_privileges,
    parse_room_list,
    parse_room_messages,
    parse_teacher_suggestions,
    room_membership,
    total_unread,
)

MESSENGER_PAGE_PATH = "/iserv/messenger/"
MEDIA_PROXY_URL = "api/messenger/media/{server_name}/{media_id}"
ROOM_ID_RE = re.compile(r"^![\w.=~-]{1,255}:[\w.-]{1,255}$")
SERVER_NAME_RE = re.compile(r"^[\w.-]{1,255}$")
MEDIA_ID_RE = re.compile(r"^[\w.=~-]{1,255}$")
EVENT_ID_RE = re.compile(r"^\$[\w.=~+/-]{1,255}$")

PRIVILEGES_KNOWN_KEY = "messenger_privileges_known"
TEACHER_PRIVILEGE_KEY = "messenger_can_write_to_teacher"
JOIN_TIMEOUT_SECONDS = 15
JOIN_POLL_SECONDS = 1.0

READ_OK_KEY = "api.messenger.read.ok"
READ_FAILED_KEY = "api.messenger.read.failed"
ROOM_OK_KEY = "api.messenger.room.ok"
ROOM_PENDING_KEY = "api.messenger.room.pending"
ROOM_FAILED_KEY = "api.messenger.room.failed"
ROOM_REJECTED_KEY = "api.messenger.room.rejected"
ROOM_INCOMPLETE_KEY = "api.messenger.room.incomplete"
ROOM_FORBIDDEN_KEY = "api.messenger.room.forbidden"


def _require(pattern, value, message):
    value = str(value or "").strip()
    if not pattern.match(value):
        raise DataError(message)
    return value


def _require_room_id(value):
    return _require(ROOM_ID_RE, value, "invalid room id")


def _require_server_name(value):
    return _require(SERVER_NAME_RE, value, "invalid media server name")


def _require_media_id(value):
    return _require(MEDIA_ID_RE, value, "invalid media id")


def _require_event_id(value):
    return _require(EVENT_ID_RE, value, "invalid event id")


def _media_proxy_url(mxc_url):
    parsed = parse_mxc(mxc_url)
    if parsed is None:
        return ""
    server_name, media_id = parsed
    return MEDIA_PROXY_URL.format(
        server_name=quote(server_name, safe=""), media_id=quote(media_id, safe="")
    )


class MessengerService:
    def __init__(self, iserv_service, matrix_client_factory=None):
        self.iserv = iserv_service
        self.store = iserv_service.store
        self.matrix_client_factory = matrix_client_factory or MatrixClient
        self.clock = time.monotonic
        self.sleeper = time.sleep

    def _bootstrap(self):
        client = self.iserv.iserv_session()
        response = client.fetch(MESSENGER_PAGE_PATH)
        if getattr(response, "status_code", 0) != 200:
            raise requests.RequestException(
                f"messenger bootstrap page failed: {response.status_code}"
            )
        try:
            auth = parse_bootstrap(response.text)
        except BootstrapNotFoundError as error:
            raise requests.RequestException("messenger bootstrap data not found") from error
        privileges = parse_privileges(response.text) or {}
        secrets = self.store.load_secrets()
        secrets.update({f"messenger_{field}": auth.get(field, "") for field in AUTH_FIELDS})
        secrets[PRIVILEGES_KNOWN_KEY] = "1"
        secrets[TEACHER_PRIVILEGE_KEY] = "1" if privileges.get("can_write_to_teacher") else ""
        self.store.save_secrets(secrets)
        return auth

    def _can_write_to_teacher(self):
        secrets = self.store.load_secrets()
        if not secrets.get(PRIVILEGES_KNOWN_KEY):
            self._bootstrap()
            secrets = self.store.load_secrets()
        return bool(secrets.get(TEACHER_PRIVILEGE_KEY))

    def _matrix_client(self, force_refresh=False):
        secrets = self.store.load_secrets()
        if force_refresh or not secrets.get("messenger_access_token"):
            auth = self._bootstrap()
        else:
            auth = {field: secrets.get(f"messenger_{field}", "") for field in AUTH_FIELDS}
        base_url = self.iserv.iserv_session().base_url
        return self.matrix_client_factory(base_url, auth["access_token"])

    def _with_matrix(self, call):
        client = self._matrix_client()
        try:
            return call(client)
        except MatrixAuthError:
            pass
        client = self._matrix_client(force_refresh=True)
        try:
            return call(client)
        except MatrixAuthError as error:
            raise LoginError("messenger token was rejected after refresh") from error

    def _own_user_id(self):
        return self.store.load_secrets().get("messenger_user_id", "")

    def rooms(self):
        can_write_to_teacher = self._can_write_to_teacher()

        def call(client):
            response = client.sync(timeout_ms=0)
            if response.status_code != 200:
                raise requests.RequestException(f"messenger sync failed: {response.status_code}")
            own_user_id = self._own_user_id()
            return {
                "rooms": parse_room_list(response.json(), own_user_id),
                "self_user_id": own_user_id,
            }

        payload = self._with_matrix(call)
        payload["can_write_to_teacher"] = can_write_to_teacher
        return payload

    def _sync_body(self):
        def call(client):
            response = client.sync(timeout_ms=0)
            if response.status_code != 200:
                raise requests.RequestException(f"messenger sync failed: {response.status_code}")
            return response.json()

        return self._with_matrix(call)

    def mark_room_read(self, room_id, event_id):
        room_id = _require_room_id(room_id)
        event_id = _require_event_id(event_id)

        def call(client):
            return client.send_read_marker(room_id, event_id)

        response = self._with_matrix(call)
        if response.status_code not in (200, 201, 204):
            return messages.result(False, READ_FAILED_KEY)
        return messages.result(True, READ_OK_KEY)

    def search_teachers(self, query):
        query = str(query or "").strip()
        if not query:
            return {"teachers": [], "allowed": True}
        if not self._can_write_to_teacher():
            return {"teachers": [], "allowed": False}
        client = self.iserv.iserv_session()
        response = client.fetch(
            TEACHER_AUTOCOMPLETE_PATH, params={"type": TEACHER_AUTOCOMPLETE_TYPE, "query": query}
        )
        if getattr(response, "status_code", 0) != 200:
            raise requests.RequestException(f"teacher search failed: {response.status_code}")
        try:
            payload = response.json()
        except ValueError as error:
            raise requests.RequestException("teacher search answered without json") from error
        return {"teachers": parse_teacher_suggestions(payload), "allowed": True}

    def create_teacher_room(self, teacher, child_ids, add_other_parents):
        teacher = str(teacher or "").strip()
        wanted = [str(value or "").strip() for value in (child_ids or [])]
        wanted = [value for value in wanted if value]
        if not teacher or not wanted:
            return messages.result(False, ROOM_INCOMPLETE_KEY)
        if not self._can_write_to_teacher():
            return messages.result(False, ROOM_FORBIDDEN_KEY)
        client = self.iserv.iserv_session()
        form = client.fetch(TEACHER_ROOM_FORM_PATH)
        if getattr(form, "status_code", 0) != 200:
            raise requests.RequestException(f"teacher room form failed: {form.status_code}")
        token = find_teacher_room_token(form.text, form.url)
        if not token:
            return messages.result(False, ROOM_FAILED_KEY)
        created = client.post_absolute(
            form.url, data=build_teacher_room_payload(token, teacher, wanted, add_other_parents)
        )
        return self._teacher_room_outcome(created)

    def _teacher_room_outcome(self, created):
        if getattr(created, "status_code", 0) not in (200, 201):
            return messages.result(False, ROOM_FAILED_KEY)
        if "json" not in str(created.headers.get("content-type") or "").lower():
            return messages.result(False, ROOM_REJECTED_KEY)
        try:
            body = created.json()
        except ValueError:
            return messages.result(False, ROOM_REJECTED_KEY)
        room_id = str((body or {}).get("room_id") or "")
        if not room_id:
            return messages.result(False, ROOM_REJECTED_KEY)
        joined = self._await_join(room_id)
        return messages.result(
            True, ROOM_OK_KEY if joined else ROOM_PENDING_KEY, room_id=room_id, joined=joined
        )

    def _await_join(self, room_id):
        deadline = self.clock() + JOIN_TIMEOUT_SECONDS
        while True:
            try:
                body = self._sync_body()
            except (requests.RequestException, LoginError):
                body = {}
            if room_membership(body, room_id) == "join":
                return True
            if self.clock() >= deadline:
                return False
            self.sleeper(JOIN_POLL_SECONDS)

    def room_messages(self, room_id, before=None):
        room_id = _require_room_id(room_id)

        def call(client):
            response = client.room_messages(room_id, before_token=before or None)
            if response.status_code != 200:
                raise requests.RequestException(
                    f"messenger history failed: {response.status_code}"
                )
            payload = parse_room_messages(response.json(), _media_proxy_url)
            payload["self_user_id"] = self._own_user_id()
            return payload

        return self._with_matrix(call)

    def send_message(self, room_id, text):
        room_id = _require_room_id(room_id)
        text = str(text or "").strip()
        if not text:
            return messages.result(False, "api.messenger.send.empty")
        txn_id = new_txn_id()

        def call(client):
            return client.send_message(room_id, txn_id, build_text_message(text))

        response = self._with_matrix(call)
        if response.status_code not in (200, 201):
            return messages.result(False, "api.messenger.send.failed")
        body = {}
        try:
            body = response.json()
        except ValueError:
            pass
        return messages.result(True, "api.messenger.send.ok", event_id=body.get("event_id", ""))

    def media(self, server_name, media_id):
        server_name = _require_server_name(server_name)
        media_id = _require_media_id(media_id)

        def call(client):
            return client.fetch_media(server_name, media_id)

        return self._with_matrix(call)

    def unread_pulse(self):
        def call(client):
            response = client.sync(timeout_ms=0)
            if response.status_code != 200:
                raise requests.RequestException(f"messenger pulse failed: {response.status_code}")
            return total_unread(response.json())

        return self._with_matrix(call)
