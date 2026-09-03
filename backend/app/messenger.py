import re
from urllib.parse import quote

import requests

from . import messages
from .iserv.errors import DataError, LoginError
from .iserv.messenger import (
    AUTH_FIELDS,
    BootstrapNotFoundError,
    MatrixAuthError,
    MatrixClient,
    build_text_message,
    new_txn_id,
    parse_bootstrap,
    parse_mxc,
    parse_room_list,
    parse_room_messages,
    total_unread,
)

MESSENGER_PAGE_PATH = "/iserv/messenger/"
MEDIA_PROXY_URL = "api/messenger/media/{server_name}/{media_id}"
ROOM_ID_RE = re.compile(r"^![\w.=~-]{1,255}:[\w.-]{1,255}$")
SERVER_NAME_RE = re.compile(r"^[\w.-]{1,255}$")
MEDIA_ID_RE = re.compile(r"^[\w.=~-]{1,255}$")


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
        secrets = self.store.load_secrets()
        secrets.update({f"messenger_{field}": auth.get(field, "") for field in AUTH_FIELDS})
        self.store.save_secrets(secrets)
        return auth

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
        def call(client):
            response = client.sync(timeout_ms=0)
            if response.status_code != 200:
                raise requests.RequestException(f"messenger sync failed: {response.status_code}")
            return {"rooms": parse_room_list(response.json(), self._own_user_id())}

        return self._with_matrix(call)

    def room_messages(self, room_id, before=None):
        room_id = _require_room_id(room_id)

        def call(client):
            response = client.room_messages(room_id, before_token=before or None)
            if response.status_code != 200:
                raise requests.RequestException(
                    f"messenger history failed: {response.status_code}"
                )
            return parse_room_messages(response.json(), _media_proxy_url)

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
