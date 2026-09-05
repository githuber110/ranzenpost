import logging
import re
import time
from urllib.parse import quote

import requests

from . import messages
from .iserv.errors import DataError, LoginError
from .iserv.messenger import (
    AUTH_FIELDS,
    BOOTSTRAP_MARKER,
    MAX_CONTINUATION_HOPS,
    STAGE_BOOTSTRAP,
    STAGE_NO_CREDENTIALS,
    STAGE_LOGIN,
    STAGE_MATRIX,
    STAGE_MODULE,
    STAGE_NETWORK,
    STAGE_TIMEOUT,
    TEACHER_AUTOCOMPLETE_PATH,
    TEACHER_AUTOCOMPLETE_TYPE,
    TEACHER_ROOM_FORM_PATH,
    WELL_KNOWN_PATH,
    BootstrapNotFoundError,
    MatrixAuthError,
    MatrixClient,
    MessengerStageError,
    build_teacher_room_payload,
    build_text_message,
    continuation_target,
    discover_matrix_base_url,
    find_teacher_room_token,
    looks_like_auth_page,
    new_txn_id,
    page_diagnosis,
    parse_authenticate_paths,
    parse_authentication,
    parse_bootstrap,
    parse_mxc,
    parse_privileges,
    parse_room_list,
    _shape_only,
    embedded_shape,
    credentials_note,
    granted_privileges,
    credentials_withheld,
    endpoint_hints,
    shape_of,
    parse_room_messages,
    parse_teacher_suggestions,
    room_membership,
    total_unread,
)

logger = logging.getLogger(__name__)

MESSENGER_PAGE_PATH = "/iserv/messenger/"
MEDIA_PROXY_URL = "api/messenger/media/{server_name}/{media_id}"
ROOM_ID_RE = re.compile(r"^![\w.=~-]{1,255}:[\w.-]{1,255}$")
SERVER_NAME_RE = re.compile(r"^[\w.-]{1,255}$")
MEDIA_ID_RE = re.compile(r"^[\w.=~-]{1,255}$")
EVENT_ID_RE = re.compile(r"^\$[\w.=~+/-]{1,255}$")

MATRIX_BASE_URL_KEY = "messenger_matrix_base_url"
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

    def _fetch_page(self, client, path):
        try:
            return client.fetch(path)
        except requests.Timeout as error:
            logger.warning("messenger page timed out at %s", path, exc_info=True)
            raise MessengerStageError(STAGE_TIMEOUT, {"path": path}) from error
        except requests.RequestException as error:
            logger.warning("messenger page unreachable at %s", path, exc_info=True)
            raise MessengerStageError(STAGE_NETWORK, {"path": path}) from error

    def _fetch_messenger_page(self, client):
        response = self._fetch_page(client, MESSENGER_PAGE_PATH)
        hops = 0
        while hops < MAX_CONTINUATION_HOPS:
            target = continuation_target(response)
            if not target:
                break
            hops += 1
            logger.info("messenger bootstrap follows a client-side continuation, hop %s", hops)
            response = self._fetch_page(client, target)
        return response, hops

    def _authentication_over_xhr(self, client, response, diagnosis):
        attempts = []
        shapes = []
        for path in parse_authenticate_paths(response.text):
            try:
                answer = client.fetch(path)
            except requests.RequestException:
                logger.warning("messenger authenticate call failed at %s", path, exc_info=True)
                attempts.append({"path": path, "status": 0})
                continue
            status = int(getattr(answer, "status_code", 0) or 0)
            attempts.append({"path": path, "status": status})
            if status != 200:
                logger.warning("messenger authenticate answered %s at %s", status, path)
                continue
            try:
                body = answer.json()
            except ValueError:
                logger.warning("messenger authenticate answered without json at %s", path, exc_info=True)
                headers = getattr(answer, "headers", None) or {}
                body = getattr(answer, "text", "") or ""
                shapes.append("%s: no json, type=%s, len=%d, starts=%s" % (
                    path,
                    str(headers.get("content-type") or "?").split(";")[0].strip(),
                    len(body),
                    _shape_only(body.strip()[:8]),
                ))
                continue
            try:
                return parse_authentication(body)
            except BootstrapNotFoundError:
                logger.warning("messenger authenticate answered without usable data at %s", path, exc_info=True)
                marked = body.get(BOOTSTRAP_MARKER) if isinstance(body, dict) else None
                shapes.append("%s: %s" % (path, shape_of(marked if isinstance(marked, dict) else body)))
        diagnosis["authenticate_attempts"] = ", ".join(
            f"{attempt['path']} {attempt['status']}" for attempt in attempts
        )
        if shapes:
            diagnosis["authenticate_fields"] = " | ".join(shapes)
        return None

    def _bootstrap(self):
        client = self.iserv.iserv_session()
        response, continuation_hops = self._fetch_messenger_page(client)
        diagnosis = page_diagnosis(response)
        diagnosis["continuation_hops"] = continuation_hops
        status = diagnosis["status"]
        if looks_like_auth_page(getattr(response, "url", "")):
            logger.warning("messenger bootstrap landed on the login flow: %s", diagnosis)
            raise MessengerStageError(STAGE_LOGIN, diagnosis)
        if status != 200:
            logger.warning("messenger module answered %s: %s", status, diagnosis)
            raise MessengerStageError(STAGE_MODULE, diagnosis)
        auth = None
        try:
            auth = parse_bootstrap(response.text)
        except BootstrapNotFoundError:
            diagnosis["page_credentials"] = credentials_note(response.text)
            diagnosis["page_privileges"] = granted_privileges(response.text)
            diagnosis["page_fields"] = embedded_shape(response.text)
            diagnosis["page_endpoints"] = endpoint_hints(response.text)
            if credentials_withheld(response.text):
                logger.warning("iserv served the messenger page without credentials: %s", diagnosis)
                raise MessengerStageError(STAGE_NO_CREDENTIALS, diagnosis)
            logger.warning("messenger page carried no embedded credentials: %s", diagnosis)
            auth = self._authentication_over_xhr(client, response, diagnosis)
        if auth is None:
            logger.warning("messenger bootstrap exhausted every path: %s", diagnosis)
            raise MessengerStageError(STAGE_BOOTSTRAP, diagnosis)
        privileges = parse_privileges(response.text) or {}
        secrets = self.store.load_secrets()
        secrets.update({f"messenger_{field}": auth.get(field, "") for field in AUTH_FIELDS})
        secrets[PRIVILEGES_KNOWN_KEY] = "1"
        secrets[TEACHER_PRIVILEGE_KEY] = "1" if privileges.get("can_write_to_teacher") else ""
        secrets[MATRIX_BASE_URL_KEY] = self._matrix_base_url(client)
        self.store.save_secrets(secrets)
        return auth

    def _matrix_base_url(self, client):
        fallback = client.base_url
        try:
            response = client.fetch(WELL_KNOWN_PATH)
        except requests.RequestException:
            logger.warning("matrix well-known lookup failed at %s", WELL_KNOWN_PATH, exc_info=True)
            return fallback
        discovered = discover_matrix_base_url(response, fallback)
        if discovered != fallback:
            logger.info("matrix homeserver discovered through well-known")
        return discovered

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
            secrets = self.store.load_secrets()
        else:
            auth = {field: secrets.get(f"messenger_{field}", "") for field in AUTH_FIELDS}
        base_url = secrets.get(MATRIX_BASE_URL_KEY) or self.iserv.iserv_session().base_url
        return self.matrix_client_factory(base_url, auth["access_token"])

    def _with_matrix(self, call):
        client = self._matrix_client()
        try:
            return self._guarded(call, client)
        except MatrixAuthError:
            logger.warning("matrix token was rejected, refreshing the messenger bootstrap")
        client = self._matrix_client(force_refresh=True)
        try:
            return self._guarded(call, client)
        except MatrixAuthError as error:
            logger.warning("matrix token was rejected after a fresh bootstrap", exc_info=True)
            raise LoginError("messenger token was rejected after refresh") from error

    def _guarded(self, call, client):
        try:
            return call(client)
        except (MatrixAuthError, MessengerStageError):
            raise
        except requests.Timeout as error:
            logger.warning("matrix call timed out", exc_info=True)
            raise MessengerStageError(STAGE_TIMEOUT, {"where": "matrix"}) from error
        except requests.RequestException as error:
            logger.warning("matrix call failed", exc_info=True)
            raise MessengerStageError(STAGE_NETWORK, {"where": "matrix"}) from error

    def _require_matrix_ok(self, label, response):
        status = int(getattr(response, "status_code", 0) or 0)
        if status == 200:
            return response
        logger.warning("matrix %s answered %s", label, status)
        raise MessengerStageError(STAGE_MATRIX, {"where": label, "status": status})

    def _own_user_id(self):
        return self.store.load_secrets().get("messenger_user_id", "")

    def rooms(self):
        can_write_to_teacher = self._can_write_to_teacher()

        def call(client):
            response = client.sync(timeout_ms=0)
            self._require_matrix_ok("sync", response)
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
            self._require_matrix_ok("sync", response)
            return response.json()

        return self._with_matrix(call)

    def mark_room_read(self, room_id, event_id):
        room_id = _require_room_id(room_id)
        event_id = _require_event_id(event_id)

        def call(client):
            return client.send_read_marker(room_id, event_id)

        response = self._with_matrix(call)
        if response.status_code not in (200, 201, 204):
            logger.warning("the read marker answered %s", response.status_code)
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
            logger.warning("teacher search answered %s", getattr(response, "status_code", 0))
            raise MessengerStageError(
                STAGE_MODULE, {"where": "teacher_search", "status": getattr(response, "status_code", 0)}
            )
        try:
            payload = response.json()
        except ValueError as error:
            logger.warning("teacher search answered without json", exc_info=True)
            raise MessengerStageError(STAGE_BOOTSTRAP, {"where": "teacher_search"}) from error
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
            logger.warning("teacher room form answered %s", getattr(form, "status_code", 0))
            raise MessengerStageError(
                STAGE_MODULE, {"where": "teacher_room_form", "status": getattr(form, "status_code", 0)}
            )
        token = find_teacher_room_token(form.text, form.url)
        if not token:
            logger.warning("teacher room form carried no token: %s", page_diagnosis(form, ""))
            return messages.result(False, ROOM_FAILED_KEY)
        created = client.post_absolute(
            form.url, data=build_teacher_room_payload(token, teacher, wanted, add_other_parents)
        )
        return self._teacher_room_outcome(created)

    def _teacher_room_outcome(self, created):
        if getattr(created, "status_code", 0) not in (200, 201):
            logger.warning("teacher room creation answered %s", getattr(created, "status_code", 0))
            return messages.result(False, ROOM_FAILED_KEY)
        if "json" not in str(created.headers.get("content-type") or "").lower():
            logger.warning("teacher room creation answered without json: %s", page_diagnosis(created, ""))
            return messages.result(False, ROOM_REJECTED_KEY)
        try:
            body = created.json()
        except ValueError:
            logger.warning("teacher room creation answered with broken json", exc_info=True)
            return messages.result(False, ROOM_REJECTED_KEY)
        room_id = str((body or {}).get("room_id") or "")
        if not room_id:
            logger.warning("teacher room creation answered without a room id")
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
                logger.warning("waiting for the new room, a sync failed", exc_info=True)
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
            self._require_matrix_ok("history", response)
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
            logger.warning("sending a message answered %s", response.status_code)
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
            self._require_matrix_ok("pulse", response)
            return total_unread(response.json())

        return self._with_matrix(call)
