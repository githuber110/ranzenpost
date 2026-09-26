from datetime import date, datetime

from app import feed, integration, messages


def lesson(**changes):
    shown = {
        "date": "10.09.2026",
        "period": 5,
        "subject_code": "L",
        "subject_label": "L",
        "teacher_code": "",
        "teacher_label": "",
        "room": "R0.04",
        "change_kind": "",
        "changed_fields": [],
        "previous": {"subject": "", "teacher": "", "teacher_surname": "", "room": ""},
        "classes": "",
        "teacher_hidden": False,
        "change_note": "",
        "moved_to": None,
        "moved_from": None,
    }
    shown.update(changes)
    return shown


def text(key, **variables):
    return messages.text_in("de", key, variables)


def test_a_moved_lesson_names_its_old_place_in_the_summary():
    shown = lesson(change_kind="changed", changed_fields=["subject"], moved_from={"date": "08.09.2026", "period": 6, "period_end": 6})
    title = text("calendar.event.summary.noTeacher", period=5, subject="L")
    target = text("calendar.move.fromTarget", date="08.09.", period=6, end=6)
    assert feed.lesson_summary("de", shown) == text("calendar.event.summary.movedFrom", target=target, title=title)


def test_a_cancelled_lesson_that_moved_names_its_new_place_in_the_summary():
    shown = lesson(date="08.09.2026", period=6, change_kind="cancelled", moved_to={"date": "10.09.2026", "period": 5, "period_end": 5})
    title = text("calendar.event.summary.noTeacher", period=6, subject="L")
    target = text("calendar.move.target", date="10.09.", period=5, end=5)
    assert feed.lesson_summary("de", shown) == text("calendar.event.summary.movedTo", target=target, title=title)


def test_a_cancelled_lesson_without_a_move_keeps_the_plain_summary():
    shown = lesson(change_kind="cancelled")
    title = text("calendar.event.summary.noTeacher", period=5, subject="L")
    assert feed.lesson_summary("de", shown) == text("calendar.event.summary.cancelled", title=title)


def test_a_double_period_move_names_the_span():
    shown = lesson(change_kind="cancelled", moved_to={"date": "10.09.2026", "period": 3, "period_end": 4})
    assert text("calendar.move.targetRange", date="10.09.", period=3, end=4) in feed.lesson_summary("de", shown)


def test_the_change_note_lists_the_move_the_hidden_teacher_the_classes_and_the_school_note():
    shown = lesson(
        change_kind="changed",
        changed_fields=["class"],
        teacher_hidden=True,
        classes="5A, 5B, 5C",
        previous={"subject": "Eth", "teacher": "", "teacher_surname": "", "room": "R0.06", "class": "5A"},
        change_note="Material mitbringen",
        moved_from={"date": "11.09.2026", "period": 6, "period_end": 6},
    )
    lines = feed.change_note("de", shown).split("\n")
    assert lines == [
        text("calendar.detail.changeLine", field=text("timetable.field.class"), before="5A", after="5A, 5B, 5C"),
        text("calendar.detail.movedFrom", target=text("calendar.move.fromTarget", date="11.09.", period=6, end=6)),
        text("calendar.detail.note", note="Material mitbringen"),
    ]


def test_a_note_alone_still_reaches_the_change_note():
    shown = lesson(change_kind="cancelled", change_note="Material mitbringen")
    assert feed.change_note("de", shown) == text("calendar.detail.note", note="Material mitbringen")


def test_the_home_assistant_change_event_describes_the_move():
    shown = lesson(date="08.09.2026", period=6, change_kind="cancelled", moved_to={"date": "10.09.2026", "period": 5, "period_end": 5})
    event = integration.change_event("de", "school:child", shown, 1_789_000_000)
    assert event["kind"] == integration.KIND_CANCELLATION
    assert event["summary"] == feed.lesson_summary("de", shown)
    assert text("calendar.move.target", date="10.09.", period=5, end=5) in event["summary"]


def test_the_home_assistant_lesson_of_the_day_carries_the_move_and_the_note():
    shown = lesson(change_kind="changed", changed_fields=["subject"], moved_from={"date": "08.09.2026", "period": 6, "period_end": 6}, change_note="Material mitbringen")
    item = integration._lesson_object("de", date(2026, 9, 10), shown, "11:40", False, datetime(2026, 9, 10, 8, 0))
    assert item["substitution"] is True
    assert item["cancelled"] is False
    assert text("calendar.detail.movedFrom", target=text("calendar.move.fromTarget", date="08.09.", period=6, end=6)) in item["note"]
    assert text("calendar.detail.note", note="Material mitbringen") in item["note"]


def test_a_hidden_teacher_replacing_a_named_one_keeps_its_change_line():
    shown = lesson(change_kind="changed", changed_fields=["subject", "teacher"], teacher_hidden=True,
                   previous={"subject": "E", "teacher": "ENG", "teacher_surname": "", "room": ""})
    assert text("calendar.detail.changeLine", field=text("timetable.field.teacher"), before="ENG", after=text("timetable.teacher.hidden")) in feed.change_note("de", shown)


def test_russian_and_ukrainian_name_the_old_place_of_a_move_in_the_genitive():
    shown = lesson(change_kind="changed", changed_fields=["subject"], moved_from={"date": "08.09.2026", "period": 6, "period_end": 6})
    assert "6-го урока" in feed.lesson_summary("ru", shown)
    assert "6-го уроку" in feed.lesson_summary("uk", shown)
    away = lesson(change_kind="cancelled", moved_to={"date": "10.09.2026", "period": 5, "period_end": 5})
    assert "на 5-й урок" in feed.lesson_summary("ru", away)
