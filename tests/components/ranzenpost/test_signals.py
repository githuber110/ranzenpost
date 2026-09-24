from custom_components.ranzenpost.api import Change, Info, State
from custom_components.ranzenpost.signals import Signal, signals_between

from . import CHILD_1, CHILD_2, SCHOOL, fixture

FRESH_CANCELLATION = Change.from_json(
    {
        "child_key": CHILD_1,
        "school_id": SCHOOL,
        "at": "2026-09-02T09:20:00+02:00",
        "kind": "cancellation",
        "summary": "Sport is cancelled",
        "date": "2026-09-03",
        "period": 5,
        "new": True,
    }
)


def states_of(child_1=None, child_2=None):
    return {
        CHILD_1: State.from_json(child_1 or fixture("state_child_1")),
        CHILD_2: State.from_json(child_2 or fixture("state_child_2")),
    }


def info_of(status="ok"):
    info = fixture("info")
    info["schools"][0]["status"] = status
    return Info.from_json(info)


def signals(previous_info, previous_states, info, states, new_changes=()):
    return signals_between(previous_info, previous_states, info, states, list(new_changes))


def test_the_first_poll_yields_no_signals():
    assert signals_between(None, {}, info_of(), states_of(), [FRESH_CANCELLATION]) == []


def test_an_unchanged_poll_yields_no_signals():
    assert signals(info_of(), states_of(), info_of(), states_of()) == []


def test_a_new_timetable_stamp_signals_a_timetable_change_for_that_child_only():
    changed = fixture("state_child_1")
    changed["timetable_last_updated"] = "2026-09-02T09:10:00+02:00"
    changed["timetable_last_updated_source"] = "feed"

    result = signals(info_of(), states_of(), info_of(), states_of(child_1=changed))

    assert result == [
        Signal("timetable_changed", SCHOOL, CHILD_1, {"last_updated": "2026-09-02T09:10:00+02:00", "source": "feed"})
    ]


def test_new_changes_signal_cancellations_and_substitutions_by_kind():
    substitution = Change.from_json(dict(fixture("changes")[0], child_key=CHILD_2, kind="substitution"))
    room_change = Change.from_json(dict(fixture("changes")[1], kind="room_change"))

    result = signals(info_of(), states_of(), info_of(), states_of(), [FRESH_CANCELLATION, substitution, room_change])

    assert result == [
        Signal("lesson_cancelled", SCHOOL, CHILD_1, {"summary": "Sport is cancelled", "date": "2026-09-03", "period": 5}),
        Signal(
            "substitution",
            SCHOOL,
            CHILD_2,
            {"summary": "English with Mr Stand-in instead of Mrs Example", "date": "2026-09-02", "period": 2},
        ),
    ]


def test_a_letter_that_was_not_listed_before_signals_a_new_letter():
    grown = fixture("state_child_1")
    grown["unread_letters"]["count"] += 1
    grown["unread_letters"]["items"].append(
        {"title": "Trip money", "sender": "Mrs Example", "date": "2026-09-02", "child": "Alex"}
    )

    result = signals(info_of(), states_of(), info_of(), states_of(child_1=grown))

    assert result == [
        Signal("new_letter", SCHOOL, CHILD_1, {"title": "Trip money", "sender": "Mrs Example", "date": "2026-09-02"})
    ]


def test_a_grown_count_without_listed_items_signals_one_new_post_with_the_count():
    grown = fixture("state_child_2")
    grown["unread_posts"] = {"count": 3, "items": []}
    before = fixture("state_child_2")
    before["unread_posts"] = {"count": 1, "items": []}

    result = signals(info_of(), states_of(child_2=before), info_of(), states_of(child_2=grown))

    assert result == [Signal("new_noticeboard_post", SCHOOL, CHILD_2, {"count": 3})]


def test_a_read_letter_never_signals():
    fewer = fixture("state_child_1")
    fewer["unread_letters"]["count"] -= 1
    fewer["unread_letters"]["items"].pop()

    assert signals(info_of(), states_of(), info_of(), states_of(child_1=fewer)) == []


def test_an_absence_whose_status_moved_signals_the_change():
    approved = fixture("state_child_1")
    approved["open_absences"]["items"][0]["status"] = "approved"

    result = signals(info_of(), states_of(), info_of(), states_of(child_1=approved))

    assert result == [
        Signal(
            "absence_status_changed",
            SCHOOL,
            CHILD_1,
            {
                "summary": "Sick note",
                "start": "2026-09-04",
                "end": "2026-09-04",
                "status": "approved",
                "previous_status": "pending",
            },
        )
    ]


def test_a_brand_new_absence_is_not_a_status_change():
    more = fixture("state_child_1")
    more["open_absences"]["items"].append(
        {"kind": "sick", "summary": "Flu", "start": "2026-09-10", "end": "2026-09-11", "status": "pending"}
    )

    assert signals(info_of(), states_of(), info_of(), states_of(child_1=more)) == []


def test_a_school_going_offline_and_back_signals_both_ways():
    assert signals(info_of("ok"), states_of(), info_of("unreachable"), states_of()) == [
        Signal("school_unreachable", SCHOOL, "", {"status": "unreachable"})
    ]
    assert signals(info_of("unreachable"), states_of(), info_of("ok"), states_of()) == [
        Signal("school_reachable", SCHOOL, "", {"status": "ok"})
    ]
    assert signals(info_of("unreachable"), states_of(), info_of("unreachable"), states_of()) == []


def test_a_failed_login_signals_once_until_it_recovers():
    assert signals(info_of("ok"), states_of(), info_of("auth_failed"), states_of()) == [
        Signal("login_needed", SCHOOL, "", {"status": "auth_failed"})
    ]
    assert signals(info_of("auth_failed"), states_of(), info_of("auth_failed"), states_of()) == []
    assert signals(info_of("auth_failed"), states_of(), info_of("ok"), states_of()) == []


def test_a_school_or_child_that_was_not_polled_before_yields_no_signal():
    later = fixture("state_child_1")
    later["timetable_last_updated"] = "2026-09-02T09:10:00+02:00"
    result = signals(info_of(), {CHILD_2: states_of()[CHILD_2]}, info_of(), states_of(child_1=later))
    assert result == []

    empty = Info.from_json(dict(fixture("info"), schools=[]))
    assert signals(empty, {}, info_of("unreachable"), states_of()) == []
