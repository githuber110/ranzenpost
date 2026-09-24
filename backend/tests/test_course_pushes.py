from app import messages
from app.poller import COURSE_HINT_KEY, PUSH_VIEW_KEY, Poller
from tests.test_poller import SCHOOL, FakeService, FakeStore, NotifierRecorder, _display_lesson, _timetable

CHILD = {"child_id": "c1", "name": "Alice"}
KEY = f"{SCHOOL}:c1"
PLAN_PUSH = messages.text_in("de", "notify.timetable.plan", {"name": "Alice"})
HINT_PUSH = messages.text_in("de", "notify.timetable.courses", {"name": "Alice"})


def lesson(period, subject, teacher, room="R1"):
    entry = _display_lesson(period=period, subject_code=subject, teacher_code=teacher, room=room)
    entry["course_key"] = f"{subject}|{teacher}"
    return entry


def week(e1_room="R1", german_room="R1", chosen=False):
    lessons = [lesson(1, "D", "AAA", german_room), lesson(3, "E1", "CCC", e1_room), lesson(3, "E2", "DDD")]
    if chosen:
        lessons = [entry for entry in lessons if entry["course_key"] != "E2|DDD"]
    timetable = _timetable("2026-08-31T10:00", lessons=lessons)
    timetable["courses"] = {
        "parallel": 2,
        "chosen": chosen,
        "hidden": 1 if chosen else 0,
        "new": 0,
        "signature": "chosen-e1" if chosen else "",
    }
    return timetable


def poller_for(timetables, store=None):
    notifier = NotifierRecorder()
    store = store or FakeStore({"language": "de"})
    poller = Poller(FakeService([CHILD], timetables, store=store), notifier=notifier, store=store)
    return poller, notifier, store


def pushes(notifier):
    return [call["message"] for call in notifier.calls]


def test_without_a_course_choice_a_parallel_course_change_sends_no_push_but_one_hint():
    timetables = {"c1": week()}
    poller, notifier, _ = poller_for(timetables)
    poller.poll_once()
    assert pushes(notifier) == [HINT_PUSH]
    timetables["c1"] = week(e1_room="R9")
    poller.poll_once()
    assert pushes(notifier) == [HINT_PUSH]


def test_without_a_course_choice_a_lesson_outside_parallel_courses_still_pushes():
    timetables = {"c1": week()}
    poller, notifier, _ = poller_for(timetables)
    poller.poll_once()
    timetables["c1"] = week(german_room="R9")
    poller.poll_once()
    assert pushes(notifier) == [HINT_PUSH, PLAN_PUSH]


def test_the_hint_comes_once_and_waits_for_a_device():
    timetables = {"c1": week()}
    poller, notifier, store = poller_for(timetables)
    notifier.delivers = False
    poller.poll_once()
    assert store.load_config()["poll_state"][KEY][COURSE_HINT_KEY] is False
    notifier.delivers = True
    poller.poll_once()
    poller.poll_once()
    assert pushes(notifier).count(HINT_PUSH) == 2
    assert store.load_config()["poll_state"][KEY][COURSE_HINT_KEY] is True


def test_choosing_courses_does_not_push_and_then_chosen_courses_push_again():
    timetables = {"c1": week()}
    poller, notifier, _ = poller_for(timetables)
    poller.poll_once()
    timetables["c1"] = week(chosen=True)
    poller.poll_once()
    assert pushes(notifier) == [HINT_PUSH]
    timetables["c1"] = week(e1_room="R9", chosen=True)
    poller.poll_once()
    assert pushes(notifier) == [HINT_PUSH, PLAN_PUSH]


def test_the_first_poll_after_the_update_sends_no_plan_push():
    timetables = {"c1": week()}
    poller, notifier, store = poller_for(timetables)
    poller.poll_once()
    state = store.load_config()
    state["poll_state"][KEY].pop(PUSH_VIEW_KEY)
    state["poll_state"][KEY]["plan_signature"] = "from-the-old-full-view"
    store.save_config(state)
    poller.poll_once()
    assert PLAN_PUSH not in pushes(notifier)


def test_a_plan_without_parallel_courses_sends_no_hint():
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[lesson(1, "D", "AAA")])}
    poller, notifier, _ = poller_for(timetables)
    poller.poll_once()
    poller.poll_once()
    assert pushes(notifier) == []
