import pytest

from app.iserv.messenger import (
    ForbiddenMatrixCallError,
    MatrixAuthError,
    MatrixClient,
    build_text_message,
    new_txn_id,
    parse_mxc,
    parse_room_list,
    parse_room_messages,
    total_unread,
)

BASE = "https://school.example"


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class FakeSession:
    def __init__(self):
        self.calls = []
        self.next_status = 200
        self.next_json = {}

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append(("GET", url, headers, params))
        return FakeResponse(self.next_status, self.next_json)

    def put(self, url, headers=None, json=None, timeout=None):
        self.calls.append(("PUT", url, headers, json))
        return FakeResponse(self.next_status, self.next_json)


def make_client(status=200, body=None):
    session = FakeSession()
    session.next_status = status
    session.next_json = body or {}
    return MatrixClient(BASE, "tok-123", session=session), session


def test_sync_sends_a_bearer_token_and_a_timeout_of_zero_by_default():
    client, session = make_client()
    client.sync()
    method, url, headers, params = session.calls[0]
    assert headers["Authorization"] == "Bearer tok-123"
    assert params["timeout"] == 0
    assert "since" not in params
    assert url.endswith("/_matrix/client/v3/sync")


def test_sync_forwards_the_since_token_for_incremental_polling():
    client, session = make_client()
    client.sync(since="s123", timeout_ms=30000)
    _, _, _, params = session.calls[0]
    assert params == {"timeout": 30000, "since": "s123"}


def test_a_401_response_raises_matrix_auth_error():
    client, _ = make_client(status=401)
    with pytest.raises(MatrixAuthError):
        client.sync()


def test_room_messages_paginates_backwards_with_a_from_token():
    client, session = make_client()
    client.room_messages("!room:school.example", before_token="tok-page-2", limit=10)
    _, url, _, params = session.calls[0]
    assert "!room:school.example/messages" in url
    assert params == {"dir": "b", "limit": 10, "from": "tok-page-2"}


def test_send_message_puts_to_the_txn_scoped_endpoint():
    client, session = make_client(status=200, body={"event_id": "$abc"})
    body = build_text_message("hello")
    response = client.send_message("!room:school.example", "txn-1", body)
    method, url, headers, sent_body = session.calls[0]
    assert method == "PUT"
    assert url.endswith("/rooms/!room:school.example/send/m.room.message/txn-1")
    assert sent_body == {"msgtype": "m.text", "body": "hello"}
    assert response.json()["event_id"] == "$abc"


def test_new_txn_id_is_unique_per_call():
    ids = {new_txn_id() for _ in range(50)}
    assert len(ids) == 50


def test_the_guard_blocks_read_marker_and_receipt_paths_before_any_network_call():
    client, session = make_client()
    with pytest.raises(ForbiddenMatrixCallError):
        client._get("/_matrix/client/v3/rooms/!x:y/read_markers")
    with pytest.raises(ForbiddenMatrixCallError):
        client._get("/_matrix/client/v3/rooms/!x:y/receipt/m.read/$evt")
    with pytest.raises(ForbiddenMatrixCallError):
        client._put("/_matrix/client/v3/rooms/!x:y/receipt/m.read/$evt", {})
    assert session.calls == []


def test_fetch_media_targets_the_authenticated_client_media_endpoint():
    client, session = make_client()
    client.fetch_media("school-server-id", "media-42")
    _, url, _, _ = session.calls[0]
    assert url.endswith("/_matrix/client/v1/media/download/school-server-id/media-42")


def test_parse_mxc_splits_server_and_media_id():
    assert parse_mxc("mxc://school-server/abc123") == ("school-server", "abc123")


def test_parse_mxc_returns_none_for_a_non_mxc_url():
    assert parse_mxc("https://example.com/x") is None
    assert parse_mxc("") is None


SYNC_BODY = {
    "rooms": {
        "join": {
            "!room1:school.example": {
                "state": {
                    "events": [
                        {
                            "type": "m.room.member",
                            "state_key": "@teacher:school.example",
                            "content": {"membership": "join", "displayname": "Teacher A"},
                        },
                        {
                            "type": "m.room.member",
                            "state_key": "@me:school.example",
                            "content": {"membership": "join", "displayname": "Me"},
                        },
                    ]
                },
                "timeline": {
                    "events": [
                        {
                            "type": "m.room.message",
                            "sender": "@teacher:school.example",
                            "origin_server_ts": 1000,
                            "content": {"msgtype": "m.text", "body": "hello"},
                        }
                    ]
                },
                "unread_notifications": {"notification_count": 2},
            },
            "!room2:school.example": {
                "state": {
                    "events": [
                        {
                            "type": "m.room.name",
                            "state_key": "",
                            "content": {"name": "Class 4b"},
                        }
                    ]
                },
                "timeline": {
                    "events": [
                        {
                            "type": "m.room.message",
                            "sender": "@teacher:school.example",
                            "origin_server_ts": 2000,
                            "content": {"msgtype": "m.text", "body": "newer"},
                        }
                    ]
                },
                "unread_notifications": {"notification_count": 0},
            },
        }
    }
}


def test_parse_room_list_derives_the_name_from_members_when_no_room_name_is_set():
    rooms = parse_room_list(SYNC_BODY, own_user_id="@me:school.example")
    room1 = next(r for r in rooms if r["room_id"] == "!room1:school.example")
    assert room1["name"] == "Teacher A"
    assert room1["members"] == ["Teacher A"]
    assert room1["unread_count"] == 2
    assert room1["last_message"] == "hello"


def test_parse_room_list_keeps_a_user_id_to_display_name_map_for_the_room_view():
    rooms = parse_room_list(SYNC_BODY, own_user_id="@me:school.example")
    room1 = next(r for r in rooms if r["room_id"] == "!room1:school.example")
    assert room1["member_names"] == {"@teacher:school.example": "Teacher A"}


def test_parse_room_list_prefers_the_explicit_room_name():
    rooms = parse_room_list(SYNC_BODY, own_user_id="@me:school.example")
    room2 = next(r for r in rooms if r["room_id"] == "!room2:school.example")
    assert room2["name"] == "Class 4b"


def test_parse_room_list_sorts_by_most_recent_message_first():
    rooms = parse_room_list(SYNC_BODY, own_user_id="@me:school.example")
    assert [r["room_id"] for r in rooms] == ["!room2:school.example", "!room1:school.example"]


def test_parse_room_list_handles_no_rooms():
    assert parse_room_list({}, own_user_id="@me:school.example") == []


def test_total_unread_sums_every_joined_room():
    assert total_unread(SYNC_BODY) == 2


def test_total_unread_handles_an_empty_sync_body():
    assert total_unread({}) == 0
    assert total_unread(None) == 0


MESSAGES_BODY = {
    "end": "prev-batch-token",
    "chunk": [
        {
            "type": "m.room.message",
            "event_id": "$1",
            "sender": "@teacher:school.example",
            "origin_server_ts": 100,
            "content": {"msgtype": "m.text", "body": "hi there"},
        },
        {
            "type": "m.room.message",
            "event_id": "$2",
            "sender": "@teacher:school.example",
            "origin_server_ts": 200,
            "content": {
                "msgtype": "m.image",
                "body": "photo.jpg",
                "url": "mxc://school-server/media-1",
                "info": {"mimetype": "image/jpeg", "size": 1234},
            },
        },
        {
            "type": "m.room.member",
            "event_id": "$3",
            "sender": "@teacher:school.example",
            "origin_server_ts": 300,
            "content": {"membership": "join"},
        },
        {
            "type": "m.reaction",
            "event_id": "$4",
            "sender": "@teacher:school.example",
            "origin_server_ts": 400,
            "content": {},
        },
    ],
}


def test_parse_room_messages_maps_text_events():
    result = parse_room_messages(MESSAGES_BODY, media_url_builder=lambda url: f"proxy:{url}")
    text_entry = next(m for m in result["messages"] if m["event_id"] == "$1")
    assert text_entry["kind"] == "text"
    assert text_entry["body"] == "hi there"


def test_parse_room_messages_maps_image_events_through_the_media_proxy():
    result = parse_room_messages(MESSAGES_BODY, media_url_builder=lambda url: f"proxy:{url}")
    image_entry = next(m for m in result["messages"] if m["event_id"] == "$2")
    assert image_entry["kind"] == "image"
    assert image_entry["media_url"] == "proxy:mxc://school-server/media-1"
    assert image_entry["mimetype"] == "image/jpeg"
    assert image_entry["size"] == 1234


def test_parse_room_messages_maps_membership_changes_as_system_entries():
    result = parse_room_messages(MESSAGES_BODY)
    system_entry = next(m for m in result["messages"] if m["event_id"] == "$3")
    assert system_entry["kind"] == "system"
    assert system_entry["system_kind"] == "join"


def test_parse_room_messages_drops_event_types_it_does_not_model():
    result = parse_room_messages(MESSAGES_BODY)
    ids = {m["event_id"] for m in result["messages"]}
    assert "$4" not in ids


def test_parse_room_messages_carries_the_pagination_token():
    result = parse_room_messages(MESSAGES_BODY)
    assert result["before"] == "prev-batch-token"


def test_privileges_are_read_from_the_same_inline_script_as_the_token():
    from app.iserv.messenger import parse_privileges

    html = (
        "<html><body><script>window.data = "
        '{"messenger_user_privileges":{"canCreateRoom":false,"canWriteToTeacher":true}}'
        ";</script></body></html>"
    )
    assert parse_privileges(html) == {"can_write_to_teacher": True}


def test_a_page_without_a_privilege_block_reports_nothing_instead_of_guessing():
    from app.iserv.messenger import parse_privileges

    assert parse_privileges("<html><body></body></html>") is None


def test_the_teacher_suggestion_value_is_handed_through_untouched():
    from app.iserv.messenger import parse_teacher_suggestions

    payload = [
        {"label": "Fr. Behrend", "value": "userid:11111111", "certainty": 1.0},
        {"label": "Hr. Kaya", "value": "userid:22222222", "extra": "Klasse 3b"},
        {"label": "no value", "value": ""},
        "not a dict",
    ]
    assert parse_teacher_suggestions(payload) == [
        {"label": "Fr. Behrend", "value": "userid:11111111", "extra": ""},
        {"label": "Hr. Kaya", "value": "userid:22222222", "extra": "Klasse 3b"},
    ]


def test_the_teacher_room_payload_repeats_the_child_field_for_every_child():
    from app.iserv.messenger import build_teacher_room_payload

    assert build_teacher_room_payload("tok", "userid:1", ["a", "b"], False) == [
        ("teacher_room[_token]", "tok"),
        ("teacher_room[teacher_id]", "userid:1"),
        ("teacher_room[add_other_parents]", "0"),
        ("teacher_room[child_ids][]", "a"),
        ("teacher_room[child_ids][]", "b"),
    ]


def test_the_fresh_csrf_token_is_taken_from_the_form_page():
    from app.iserv.messenger import find_teacher_room_token

    html = (
        '<html><body><form method="post">'
        '<input name="teacher_room[_token]" value="csrf-42">'
        "</form></body></html>"
    )
    assert find_teacher_room_token(html, "https://school.example/form") == "csrf-42"
    assert find_teacher_room_token("<html></html>", "https://school.example/form") == ""


def test_room_membership_names_the_state_the_sync_reports():
    from app.iserv.messenger import room_membership

    body = {"rooms": {"join": {"!a:srv": {}}, "invite": {"!b:srv": {}}}}
    assert room_membership(body, "!a:srv") == "join"
    assert room_membership(body, "!b:srv") == "invite"
    assert room_membership(body, "!c:srv") == ""


def test_the_read_marker_body_names_both_markers_so_the_counter_can_drop():
    from app.iserv.messenger import build_read_marker

    body = build_read_marker("$evt-1")
    assert set(body.values()) == {"$evt-1"}
    assert len(body) == 2
