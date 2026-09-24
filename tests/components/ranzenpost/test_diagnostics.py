import json

from custom_components.ranzenpost.diagnostics import async_get_config_entry_diagnostics

from . import CHILD_1, CHILD_2, SCHOOL, TOKEN, setup_entry

REDACTED = "**REDACTED**"
PERSONAL_TEXTS = (
    "Sample School",
    "school.example",
    "Alex",
    "Kim",
    "5b",
    "8a",
    "Mrs Example",
    "Mr Stand-in",
    "Ms Brush",
    "Field trip",
    "Photo day",
    "Lost and found",
    "Sick note",
    "Maths",
    "R101",
    "Parent-teacher conference",
    "Autumn holidays",
    "Head Office",
    "Caretaker",
    "Dr Leaf",
    "Main building",
    "Chapter 3",
    "Biology",
)


async def test_diagnostics_redact_the_token_and_carry_the_snapshot(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry"]["data"]["token"] == REDACTED
    assert result["entry"]["data"]["host"] == "addon-host"
    assert TOKEN not in str(result)
    assert result["last_update_success"] is True
    assert result["info"]["version"] == "2609.02.00"
    assert result["info"]["schools"][0]["modules"]["timetable"] is True
    assert result["info"]["schools"][0]["status"] == "ok"
    assert result["info"]["last_poll"] == "2026-09-02T09:00:00+02:00"
    assert set(result["schools"]) == {SCHOOL}
    assert result["schools"][SCHOOL]["children"] == [CHILD_1, CHILD_2]
    assert result["schools"][SCHOOL]["modules"]["letters"] is True
    assert set(result["states"]) == {CHILD_1, CHILD_2}
    assert result["states"][CHILD_1]["unread_letters"]["count"] == 2
    assert result["states"][CHILD_1]["now_lesson"]["subject_code"] == "MA"
    assert result["states"][CHILD_1]["now_lesson"]["start"] == "2026-09-02T09:00:00+02:00"
    assert result["states"][CHILD_1]["open_absences"][0]["status"] == "pending"
    assert result["states"][CHILD_1]["next_absence"]["status"] == "pending"
    assert result["states"][CHILD_1]["next_absence"]["days_until"] == 2
    assert [change["kind"] for change in result["changes"]] == ["substitution", "room_change", "cancellation"]
    assert result["schools"][SCHOOL]["school"]["next_holiday"]["start"] == "2026-10-12"
    assert result["schools"][SCHOOL]["school"]["region"] == "NI"
    assert json.dumps(result)


async def test_diagnostics_carry_no_school_or_person_text(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)

    result = await async_get_config_entry_diagnostics(hass, entry)
    dump = json.dumps(result)

    for text in PERSONAL_TEXTS:
        assert text not in dump, text
    assert result["info"]["schools"][0]["name"] == REDACTED
    assert result["info"]["schools"][0]["url_host"] == REDACTED
    assert [child["key"] for child in result["info"]["schools"][0]["children"]] == [CHILD_1, CHILD_2]
    assert result["info"]["schools"][0]["children"][0]["name"] == REDACTED
    assert result["info"]["schools"][0]["children"][0]["class_name"] == REDACTED
    assert result["states"][CHILD_1]["unread_letters"]["items"][0]["title"] == REDACTED
    assert result["states"][CHILD_1]["unread_letters"]["items"][0]["sender"] == REDACTED
    assert result["states"][CHILD_1]["unread_letters"]["items"][0]["child"] == REDACTED
    assert result["states"][CHILD_1]["unread_letters"]["items"][0]["date"] == "2026-09-01"
    assert result["states"][CHILD_1]["now_lesson"]["teacher"] == REDACTED
    assert result["states"][CHILD_1]["next_lesson"]["before"] == REDACTED
    assert result["states"][CHILD_1]["next_exam"]["name"] == REDACTED
    assert result["states"][CHILD_1]["next_exam"]["date"] == "2026-09-03"
    assert result["states"][CHILD_1]["next_school_day"]["first_lesson"] == REDACTED
    assert result["schools"][SCHOOL]["school"]["next_conference"]["details"] == REDACTED
    assert result["states"][CHILD_1]["open_absences"][0]["summary"] == REDACTED
    assert result["states"][CHILD_1]["next_absence"]["summary"] == REDACTED
    assert result["changes"][0]["summary"] == REDACTED
    assert result["schools"][SCHOOL]["school"]["next_conference"]["title"] == REDACTED
