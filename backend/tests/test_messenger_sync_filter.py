import json
import threading

import pytest

from app.iserv.messenger import (
    BROAD_SYNC_FILTER,
    INITIAL_SYNC_TIMELINE_LIMIT,
    ROOM_LIST_SYNC_FILTER,
    UNREAD_SYNC_FILTER,
    MatrixClient,
    MessengerStageError,
    filter_misread,
    parse_room_list,
    room_membership,
    total_unread,
)
from app.messenger import NARROW_FILTER_RETRY_SECONDS, MessengerService
from tests.matrix_sync_model import OWN_USER, body_size, build_account, only_fields, serve_sync
from tests.test_messenger_service import (
    KNOWN_PRIVILEGES,
    DictStore,
    FakeIServ,
    FakeIServClient,
    FakeMatrixClient,
    FakeMatrixResponse,
    FakePage,
)

BASE = "https://school.example"
LEGACY_SYNC_FILTER = {
    "room": {
        "timeline": {"limit": 20},
        "ephemeral": {"limit": 0, "types": []},
    },
    "presence": {"limit": 0, "types": []},
}
PROFILES = {
    "typical": dict(class_groups=2, class_size=40, wide_rooms=1, wide_size=150, direct_rooms=6),
    "large": dict(class_groups=4, class_size=45, wide_rooms=3, wide_size=400, direct_rooms=10),
}


@pytest.fixture(params=sorted(PROFILES))
def account(request):
    return build_account(**PROFILES[request.param])


def test_the_room_list_stays_identical_under_the_sharper_filter(account):
    legacy = parse_room_list(serve_sync(account, LEGACY_SYNC_FILTER), OWN_USER)
    sharper = parse_room_list(serve_sync(account, ROOM_LIST_SYNC_FILTER), OWN_USER)
    assert sharper == legacy
    assert any(room["member_names"] for room in sharper)
    assert any(room["name"] == ", ".join(room["members"]) for room in sharper)
    assert any(room["last_message"] for room in sharper)


def test_the_room_list_sync_carries_at_most_forty_percent_of_the_old_volume(account):
    legacy = body_size(serve_sync(account, LEGACY_SYNC_FILTER))
    sharper = body_size(serve_sync(account, ROOM_LIST_SYNC_FILTER))
    assert sharper <= legacy * 0.4, (sharper, legacy)


def test_the_unread_total_stays_identical_under_the_minimal_filter(account):
    legacy = total_unread(serve_sync(account, LEGACY_SYNC_FILTER))
    minimal = total_unread(serve_sync(account, UNREAD_SYNC_FILTER))
    assert minimal == legacy
    assert minimal > 0


def test_the_unread_sync_carries_at_most_three_percent_of_the_old_volume(account):
    legacy = body_size(serve_sync(account, LEGACY_SYNC_FILTER))
    minimal = body_size(serve_sync(account, UNREAD_SYNC_FILTER))
    assert minimal <= legacy * 0.03, (minimal, legacy)


def test_every_room_keeps_its_membership_under_the_minimal_filter(account):
    legacy = serve_sync(account, LEGACY_SYNC_FILTER)
    minimal = serve_sync(account, UNREAD_SYNC_FILTER)
    room_ids = [room.room_id for room in account["rooms"]] + account["invites"]
    assert [room_membership(minimal, room_id) for room_id in room_ids] == [
        room_membership(legacy, room_id) for room_id in room_ids
    ]
    assert {room_membership(minimal, room_id) for room_id in room_ids} == {"join", "invite"}


def test_the_sharper_filter_drops_what_no_reader_uses(account):
    body = serve_sync(account, ROOM_LIST_SYNC_FILTER)
    assert body["account_data"]["events"] == []
    assert body["presence"]["events"] == []
    for room in body["rooms"]["join"].values():
        assert room["account_data"]["events"] == []
        assert room["ephemeral"]["events"] == []
        for event in room["state"]["events"] + room["timeline"]["events"]:
            assert "unsigned" not in event
            assert "event_id" not in event
            assert "avatar_url" not in event.get("content", {})
        assert {event["type"] for event in room["state"]["events"]} <= {"m.room.name", "m.room.member"}


def test_the_room_list_filter_keeps_every_member_and_the_join_burst_margin():
    room = ROOM_LIST_SYNC_FILTER["room"]
    assert "lazy_load_members" not in room["state"]
    assert "lazy_load_members" not in room["timeline"]
    assert room["timeline"]["limit"] == INITIAL_SYNC_TIMELINE_LIMIT
    assert "types" not in room["timeline"]
    assert "not_types" not in room["timeline"]


def test_no_filter_names_a_room_so_new_rooms_stay_visible():
    for sync_filter in (ROOM_LIST_SYNC_FILTER, UNREAD_SYNC_FILTER):
        assert "rooms" not in sync_filter["room"]
        assert "not_rooms" not in sync_filter["room"]
        assert "include_leave" not in sync_filter["room"]


class _Recorder:
    def __init__(self):
        self.params = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.params.append(params)
        return FakePage(200, "", json_data={})


def _sent_filter(**kwargs):
    session = _Recorder()
    MatrixClient(BASE, "tok-secret", session=session).sync(timeout_ms=0, **kwargs)
    return session.params[0]


def test_the_client_sends_the_room_list_filter_by_default():
    params = _sent_filter()
    assert json.loads(params["filter"]) == ROOM_LIST_SYNC_FILTER


def test_the_client_sends_the_filter_it_is_given():
    params = _sent_filter(sync_filter=UNREAD_SYNC_FILTER)
    assert json.loads(params["filter"]) == UNREAD_SYNC_FILTER
    assert "tok-secret" not in params["filter"]


def test_an_incremental_sync_sends_its_filter_too():
    params = _sent_filter(since="s_1", sync_filter=UNREAD_SYNC_FILTER)
    assert params["since"] == "s_1"
    assert json.loads(params["filter"]) == UNREAD_SYNC_FILTER


class _ModelMatrixClient(FakeMatrixClient):
    def __init__(self, base_url, access_token, account, filters):
        super().__init__(base_url, access_token)
        self.account = account
        self.filters = filters

    def sync(self, since=None, timeout_ms=0, sync_filter=None):
        self.filters.append(sync_filter)
        return FakeMatrixResponse(json_data=serve_sync(self.account, sync_filter))


def _model_service(account, filters, store=None):
    store = store or DictStore(
        dict(KNOWN_PRIVILEGES, messenger_access_token="tok-1", messenger_user_id=OWN_USER)
    )

    def factory(base_url, access_token):
        return _ModelMatrixClient(base_url, access_token, account, filters)

    return MessengerService(FakeIServ(store, FakeIServClient()), matrix_client_factory=factory), store


def test_the_rooms_endpoint_returns_the_same_payload_through_the_service(account):
    filters = []
    service, _store = _model_service(account, filters)
    payload = service.rooms()
    assert filters == [ROOM_LIST_SYNC_FILTER]
    assert payload["rooms"] == parse_room_list(serve_sync(account, LEGACY_SYNC_FILTER), OWN_USER)
    assert payload["self_user_id"] == OWN_USER


def test_the_unread_pulse_uses_the_minimal_filter_and_counts_the_same(account):
    filters = []
    service, _store = _model_service(account, filters)
    assert service.unread_pulse() == total_unread(serve_sync(account, LEGACY_SYNC_FILTER))
    assert filters == [UNREAD_SYNC_FILTER]


def test_waiting_for_a_new_room_uses_the_minimal_filter(account):
    filters = []
    service, _store = _model_service(account, filters)
    assert service._await_join(account["rooms"][0].room_id) is True
    assert filters == [UNREAD_SYNC_FILTER]


def test_the_sync_filters_store_nothing_new(account):
    filters = []
    service, store = _model_service(account, filters)
    before = store.load_secrets()
    service.rooms()
    service.unread_pulse()
    service._await_join(account["rooms"][0].room_id)
    assert store.load_secrets() == before


def test_the_model_reads_an_empty_field_list_as_every_field():
    event = {"type": "m.room.member", "state_key": OWN_USER, "content": {"membership": "join"}, "unsigned": {"age": 1}}
    assert only_fields(event, []) == event
    assert only_fields(event, None) == event
    assert only_fields(event, ["type"]) == {"type": "m.room.member"}


def test_the_model_leaves_out_a_joined_room_with_nothing_to_report(account):
    empty = {
        "room": {
            "state": {"types": []},
            "timeline": {"limit": 0},
            "ephemeral": {"types": []},
            "account_data": {"types": []},
        }
    }
    assert serve_sync(account, empty)["rooms"]["join"] == {}


def test_the_pulse_and_the_join_wait_keep_one_timeline_event_per_room(account):
    filters = []
    service, _store = _model_service(account, filters)
    service.unread_pulse()
    service._await_join(account["rooms"][0].room_id)
    assert len(filters) == 2
    for sync_filter in filters:
        assert sync_filter["room"]["timeline"]["limit"] >= 1
        body = serve_sync(account, sync_filter)
        assert sorted(body["rooms"]["join"]) == sorted(room.room_id for room in account["rooms"])


class _SequenceMatrixClient(FakeMatrixClient):
    def __init__(self, base_url, access_token, answers, filters):
        super().__init__(base_url, access_token)
        self.answers = answers
        self.filters = filters

    def sync(self, since=None, timeout_ms=0, sync_filter=None):
        self.filters.append(sync_filter)
        return self.answers.pop(0)


def _sequence_service(answers, filters):
    store = DictStore(dict(KNOWN_PRIVILEGES, messenger_access_token="tok-secret", messenger_user_id=OWN_USER))

    def factory(base_url, access_token):
        return _SequenceMatrixClient(base_url, access_token, answers, filters)

    return MessengerService(FakeIServ(store, FakeIServClient()), matrix_client_factory=factory)


ROOM_ID = "!room1:school.example"


def _room_body(member_content, unread=2):
    return {
        "rooms": {
            "join": {
                ROOM_ID: {
                    "state": {
                        "events": [
                            {"type": "m.room.member", "state_key": "@teacher:school.example", "content": member_content}
                        ]
                    },
                    "timeline": {
                        "events": [
                            {"type": "m.room.message", "origin_server_ts": 5, "content": {"body": "hello"}}
                        ]
                    },
                    "unread_notifications": {"notification_count": unread},
                }
            }
        }
    }


FULL_MEMBER = {"membership": "join", "displayname": "Teacher A"}


def _fallback_lines(caplog):
    return [record.getMessage() for record in caplog.records if "broad filter" in record.getMessage()]


def _assert_quiet_about_secrets(caplog):
    for record in caplog.records:
        message = record.getMessage()
        assert "tok-secret" not in message
        assert ROOM_ID not in message


def test_a_refused_filter_is_asked_once_more_with_the_broad_filter(caplog):
    filters = []
    answers = [FakeMatrixResponse(status_code=400), FakeMatrixResponse(json_data=_room_body(FULL_MEMBER))]
    service = _sequence_service(answers, filters)
    payload = service.rooms()
    assert filters == [ROOM_LIST_SYNC_FILTER, BROAD_SYNC_FILTER]
    assert [room["name"] for room in payload["rooms"]] == ["Teacher A"]
    assert len(_fallback_lines(caplog)) == 1
    _assert_quiet_about_secrets(caplog)


def test_member_events_without_membership_are_asked_once_more_with_the_broad_filter(caplog):
    filters = []
    answers = [
        FakeMatrixResponse(json_data=_room_body({"displayname": "Teacher A"})),
        FakeMatrixResponse(json_data=_room_body(FULL_MEMBER)),
    ]
    service = _sequence_service(answers, filters)
    payload = service.rooms()
    assert filters == [ROOM_LIST_SYNC_FILTER, BROAD_SYNC_FILTER]
    assert payload["rooms"][0]["members"] == ["Teacher A"]
    assert len(_fallback_lines(caplog)) == 1
    _assert_quiet_about_secrets(caplog)


def test_a_normal_answer_is_not_asked_again(caplog):
    filters = []
    service = _sequence_service([FakeMatrixResponse(json_data=_room_body(FULL_MEMBER))], filters)
    service.rooms()
    assert filters == [ROOM_LIST_SYNC_FILTER]
    assert _fallback_lines(caplog) == []


def test_the_pulse_asks_once_more_after_a_refused_filter(caplog):
    filters = []
    answers = [FakeMatrixResponse(status_code=400), FakeMatrixResponse(json_data=_room_body(FULL_MEMBER, unread=3))]
    service = _sequence_service(answers, filters)
    assert service.unread_pulse() == 3
    assert filters == [UNREAD_SYNC_FILTER, BROAD_SYNC_FILTER]
    assert len(_fallback_lines(caplog)) == 1
    _assert_quiet_about_secrets(caplog)


def test_the_pulse_takes_member_events_with_only_a_type_as_asked():
    filters = []
    body = _room_body(FULL_MEMBER, unread=4)
    body["rooms"]["join"][ROOM_ID]["timeline"]["events"] = [{"type": "m.room.member"}]
    body["rooms"]["join"][ROOM_ID]["state"]["events"] = []
    service = _sequence_service([FakeMatrixResponse(json_data=body)], filters)
    assert service.unread_pulse() == 4
    assert filters == [UNREAD_SYNC_FILTER]


def test_the_join_wait_asks_once_more_after_a_refused_filter():
    filters = []
    answers = [FakeMatrixResponse(status_code=400), FakeMatrixResponse(json_data=_room_body(FULL_MEMBER))]
    service = _sequence_service(answers, filters)
    assert service._await_join(ROOM_ID) is True
    assert filters == [UNREAD_SYNC_FILTER, BROAD_SYNC_FILTER]


def test_a_rate_limit_is_not_answered_with_a_second_sync():
    filters = []
    service = _sequence_service([FakeMatrixResponse(status_code=429)], filters)
    with pytest.raises(MessengerStageError):
        service.unread_pulse()
    assert filters == [UNREAD_SYNC_FILTER]


def test_a_broad_retry_that_fails_as_well_reports_the_matrix_error():
    filters = []
    answers = [FakeMatrixResponse(status_code=400), FakeMatrixResponse(status_code=403)]
    service = _sequence_service(answers, filters)
    with pytest.raises(MessengerStageError) as raised:
        service.unread_pulse()
    assert raised.value.detail["status"] == 403
    assert len(filters) == 2
    assert service._narrow_refused == {}


def test_a_misread_whose_broad_retry_fails_switches_nothing_off():
    filters = []
    answers = [
        FakeMatrixResponse(json_data=_room_body({"displayname": "Teacher A"})),
        FakeMatrixResponse(status_code=502),
    ]
    service = _sequence_service(answers, filters)
    payload = service.rooms()
    assert payload["rooms"] == []
    assert payload["messages_unavailable"]["diagnosis"]["status"] == 502
    assert filters == [ROOM_LIST_SYNC_FILTER, BROAD_SYNC_FILTER]
    assert service._narrow_refused == {}


@pytest.mark.parametrize("status", [400, 413, 414])
def test_answers_that_point_at_the_filter_lead_to_the_broad_retry(status):
    filters = []
    service = _sequence_service([FakeMatrixResponse(status_code=status), _ok(unread=2)], filters)
    assert service.unread_pulse() == 2
    assert filters == [UNREAD_SYNC_FILTER, BROAD_SYNC_FILTER]
    assert len(service._narrow_refused) == 1


@pytest.mark.parametrize("status", [403, 404, 408])
def test_other_client_errors_are_reported_without_a_second_sync(status, caplog):
    filters = []
    service = _sequence_service([FakeMatrixResponse(status_code=status)], filters)
    with pytest.raises(MessengerStageError) as raised:
        service.unread_pulse()
    assert raised.value.detail["status"] == status
    assert filters == [UNREAD_SYNC_FILTER]
    assert service._narrow_refused == {}
    assert _fallback_lines(caplog) == []


def test_the_misread_check_stays_quiet_on_bodies_it_cannot_read():
    for body in (None, [], {"rooms": "x"}, {"rooms": {"join": []}}, {"rooms": {"join": {ROOM_ID: "x"}}}):
        assert filter_misread(body, ROOM_LIST_SYNC_FILTER) is False
    assert filter_misread(_room_body({"displayname": "A"}), ROOM_LIST_SYNC_FILTER) is True
    assert filter_misread(_room_body({"displayname": "A"}), UNREAD_SYNC_FILTER) is False
    assert filter_misread(_room_body(FULL_MEMBER), ROOM_LIST_SYNC_FILTER) is False


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _refusing_service(answers, filters, clock):
    service = _sequence_service(answers, filters)
    service.clock = clock
    return service


def _ok(unread=1):
    return FakeMatrixResponse(json_data=_room_body(FULL_MEMBER, unread=unread))


def test_a_refused_narrow_filter_is_switched_off_for_the_next_syncs(caplog):
    filters = []
    clock = _Clock()
    answers = [FakeMatrixResponse(status_code=400), _ok(), _ok(), _ok()]
    service = _refusing_service(answers, filters, clock)
    service.unread_pulse()
    assert filters == [UNREAD_SYNC_FILTER, BROAD_SYNC_FILTER]
    del filters[:]
    service.unread_pulse()
    clock.now += NARROW_FILTER_RETRY_SECONDS - 1
    service.unread_pulse()
    assert filters == [BROAD_SYNC_FILTER, BROAD_SYNC_FILTER]
    assert len(_fallback_lines(caplog)) == 1
    _assert_quiet_about_secrets(caplog)


def test_the_narrow_filter_is_tried_again_after_the_pause():
    filters = []
    clock = _Clock()
    answers = [FakeMatrixResponse(status_code=400), _ok(), _ok()]
    service = _refusing_service(answers, filters, clock)
    service.unread_pulse()
    clock.now += NARROW_FILTER_RETRY_SECONDS
    del filters[:]
    service.unread_pulse()
    assert filters == [UNREAD_SYNC_FILTER]


def test_a_refusal_of_one_filter_leaves_the_other_filter_narrow():
    filters = []
    clock = _Clock()
    answers = [FakeMatrixResponse(status_code=400), _ok(), _ok()]
    service = _refusing_service(answers, filters, clock)
    service.unread_pulse()
    del filters[:]
    service.rooms()
    assert filters == [ROOM_LIST_SYNC_FILTER]


def test_a_new_messenger_login_forgets_the_refusal():
    filters = []
    clock = _Clock()
    store = DictStore(dict(KNOWN_PRIVILEGES, messenger_access_token="tok-old", messenger_user_id=OWN_USER))
    answers = [FakeMatrixResponse(status_code=400), _ok(), _ok()]

    def factory(base_url, access_token):
        return _SequenceMatrixClient(base_url, access_token, answers, filters)

    service = MessengerService(FakeIServ(store, FakeIServClient()), matrix_client_factory=factory)
    service.clock = clock
    service.unread_pulse()
    store.save_secrets(dict(store.load_secrets(), messenger_access_token="tok-new"))
    del filters[:]
    service.unread_pulse()
    assert filters == [UNREAD_SYNC_FILTER]
    assert service._narrow_refused == {}


def test_the_refusal_lives_only_in_memory():
    filters = []
    service = _refusing_service([FakeMatrixResponse(status_code=400), _ok()], filters, _Clock())
    store_before = service.store.load_secrets()
    service.unread_pulse()
    assert service.store.load_secrets() == store_before
    assert all("tok-secret" not in str(key) for key in service._narrow_refused)


def test_the_refusal_key_reads_the_client_attributes_the_real_client_has():
    real = MatrixClient(BASE, "tok-secret", session=_Recorder())
    fake = FakeMatrixClient(BASE, "tok-secret")
    service = _sequence_service([], [])
    assert service._narrow_key(real, UNREAD_SYNC_FILTER) == service._narrow_key(fake, UNREAD_SYNC_FILTER)

    class Renamed:
        url = BASE
        token = "tok-secret"

    with pytest.raises(AttributeError):
        service._narrow_key(Renamed(), UNREAD_SYNC_FILTER)


def test_two_syncs_at_the_end_of_the_pause_do_not_trip_over_each_other(caplog):
    caplog.set_level("INFO")
    service = _sequence_service([], [])
    key = service._narrow_key(FakeMatrixClient(BASE, "tok-secret"), UNREAD_SYNC_FILTER)
    service._narrow_refused[key] = 0.0
    expired = float(NARROW_FILTER_RETRY_SECONDS + 1)
    outcomes = {}
    errors = []

    def run(name):
        try:
            outcomes[name] = service._narrow_switched_off(key)
        except Exception as error:
            errors.append(error)

    other = threading.Thread(target=run, args=("api",))
    hooked = []

    def clock():
        if not hooked:
            hooked.append(True)
            other.start()
            other.join(0.5)
        return expired

    service.clock = clock
    run("poller")
    other.join(5)
    assert not other.is_alive()
    assert errors == []
    assert outcomes == {"poller": False, "api": False}
    assert service._narrow_refused == {}
    assert [record.getMessage() for record in caplog.records].count("matrix sync tries the narrow filter again") == 1


@pytest.mark.parametrize("status", [500, 503])
def test_server_errors_are_reported_without_a_second_sync(status, caplog):
    filters = []
    service = _sequence_service([FakeMatrixResponse(status_code=status)], filters)
    with pytest.raises(MessengerStageError) as raised:
        service.unread_pulse()
    assert raised.value.detail["status"] == status
    assert filters == [UNREAD_SYNC_FILTER]
    assert service._narrow_refused == {}
    assert _fallback_lines(caplog) == []
