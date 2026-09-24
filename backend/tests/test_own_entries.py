import random
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import own_entries, period_grid
from app.own_entries import OwnEntryError
from app.server import create_app
from app.service import IServService
from app.store import ConnectionStore, Store
from tests.support import add_school

TODAY = date(2026, 9, 23)
UNTIL = date(2027, 6, 30)
MONDAY = date(2026, 9, 21)
BASE = (470, 520, 585, 635, 695, 745, 830, 880)
ISERV = {str(n): {"start": period_grid.clock_of(start), "end": period_grid.clock_of(start + 45)} for n, start in enumerate(BASE, 1)}
TIMES = {key: slot["start"] for key, slot in ISERV.items()}
PROFILE = {"sam": {"0": [1, 2, 3, 4, 5, 6], "1": [1, 2, 3, 4, 5, 6, 7, 8], "2": [1, 2, 3, 4, 5], "3": [1, 2, 3, 4, 5, 6], "4": [1, 2, 3, 4, 5]}, "mika": {"0": [1, 2, 3, 4, 5, 6], "1": [1, 2, 3, 4, 5, 6], "2": [1, 2, 3, 4, 5, 6, 7], "3": [1, 2, 3, 4, 5, 6], "4": [1, 2, 3, 4, 5, 6]}}
CHILDREN = [{"child_id": "sam", "name": "Sam Example"}, {"child_id": "mika", "name": "Mika Example"}]


def config(entries=None, lessons=None):
    return {
        "children": [dict(child) for child in CHILDREN],
        "period_times": dict(TIMES),
        "period_grid": {"iserv": dict(ISERV), "lessons": dict(lessons or {}), "days": {key: dict(value) for key, value in PROFILE.items()}},
        "own_entries": list(entries or []),
    }


def raw(**fields):
    base = {"type": "club", "name": "Chess club", "start": "15:30", "duration": 60, "repeat": "weekly", "days": [2], "from": "2026-09-01", "until": UNTIL.isoformat(), "holidays": False, "child": "sam"}
    base.update(fields)
    return base


def normalized(**fields):
    entry = own_entries.normalize(raw(**fields), config(), TODAY, UNTIL)
    entry["id"] = fields.get("id", "e-" + str(random.random()))
    return entry


def context(conf):
    return period_grid.resolve(conf), period_grid.profiles(conf), own_entries.child_ids(conf)


def spans_on(conf, child, day):
    rows, profiles, _ = context(conf)
    return period_grid.spans_for(rows, profiles[child].get(day.weekday()))


@pytest.mark.parametrize(
    "fields, key",
    [
        ({"type": "party"}, own_entries.ERROR_TYPE),
        ({"name": "  "}, own_entries.ERROR_NAME),
        ({"name": "x" * 61}, own_entries.ERROR_NAME_LENGTH),
        ({"name": "Sam's club"}, own_entries.ERROR_NAME_PERSON),
        ({"start": "25:00"}, own_entries.ERROR_START),
        ({"duration": 0}, own_entries.ERROR_DURATION),
        ({"duration": "abc"}, own_entries.ERROR_DURATION),
        ({"start": "23:30", "duration": 31}, own_entries.ERROR_MIDNIGHT),
        ({"repeat": "yearly"}, own_entries.ERROR_REPEAT),
        ({"days": []}, own_entries.ERROR_DAYS),
        ({"days": [7]}, own_entries.ERROR_DAYS),
        ({"repeat": "weeks", "interval": 1}, own_entries.ERROR_INTERVAL),
        ({"repeat": "weeks", "interval": 9}, own_entries.ERROR_INTERVAL),
        ({"until": "2027-07-01"}, own_entries.ERROR_UNTIL),
        ({"from": "2026-10-01", "until": "2026-09-30"}, own_entries.ERROR_RANGE),
        ({"repeat": "once", "date": "2026-09-22"}, own_entries.ERROR_DATE),
        ({"repeat": "once", "date": "2027-07-01"}, own_entries.ERROR_DATE),
        ({"child": "someone"}, own_entries.ERROR_CHILD),
    ],
)
def test_a_broken_entry_is_refused_with_its_message(fields, key):
    with pytest.raises(OwnEntryError) as caught:
        own_entries.normalize(raw(**fields), config(), TODAY, UNTIL)
    assert caught.value.message_key == key


def test_the_normalized_entry_keeps_only_what_its_repetition_needs():
    daily = own_entries.normalize(raw(repeat="daily", days=[6], type="pause", child=""), config(), TODAY, UNTIL)
    assert daily["days"] == [0, 1, 2, 3, 4]
    once = own_entries.normalize(raw(repeat="once", date="2026-09-24", holidays=False), config(), TODAY, UNTIL)
    assert once["holidays"] is True and once["days"] == [] and once["from"] == ""
    open_end = own_entries.normalize(raw(until=""), config(), TODAY, UNTIL)
    assert open_end["until"] == UNTIL.isoformat()


def test_every_n_weeks_counts_from_the_week_it_starts():
    entry = normalized(repeat="weeks", interval=3, days=[2], **{"from": "2026-09-23"})
    hits = [day for day in (MONDAY + timedelta(days=offset) for offset in range(0, 70)) if own_entries.occurs_on(entry, day)]
    assert hits == [date(2026, 9, 23), date(2026, 10, 14), date(2026, 11, 4), date(2026, 11, 25)]


def test_daily_means_every_school_day():
    entry = normalized(repeat="daily", type="pause", child="", start="09:15", duration=5)
    week = [MONDAY + timedelta(days=offset) for offset in range(7)]
    assert [own_entries.occurs_on(entry, day) for day in week] == [True] * 5 + [False] * 2


def test_a_longer_lesson_shortens_a_pause_and_hides_the_one_it_covers():
    lunch = normalized(type="pause", name="Lunch", start="13:15", duration=35, repeat="daily", child="")
    move = normalized(type="pause", name="Room change", start="13:10", duration=5, repeat="daily", child="")
    conf = config([lunch, move], {"6": {"duration": 60}})
    items = own_entries.resolve_day([lunch, move], spans_on(conf, "sam", MONDAY), MONDAY, "sam")
    states = {item["entry"]["name"]: (item["state"], item["number"], item["start"]) for item in items}
    assert states["Room change"] == (own_entries.STATE_HIDDEN, 6, states["Room change"][2])
    assert states["Lunch"][0] == own_entries.STATE_CUT and states["Lunch"][1] == 6
    assert states["Lunch"][2] == 13 * 60 + 25
    rows, profiles, children = context(conf)
    assert own_entries.entry_status(move, rows, profiles, children)["state"] == own_entries.STATE_HIDDEN
    assert own_entries.entry_status(lunch, rows, profiles, children) == {"state": own_entries.STATE_CUT, "number": 6, "start": 805, "end": 830}


def test_a_one_off_appointment_shortens_the_series_on_its_day_only():
    series = normalized(type="appointment", name="Training", start="18:00", duration=120, days=[3])
    once = normalized(type="appointment", name="Evening", start="19:00", duration=90, repeat="once", date="2026-09-24")
    day = date(2026, 9, 24)
    items = own_entries.resolve_day([series, once], [], day, "sam")
    shown = {item["entry"]["name"]: (item["start"], item["end"], item["state"]) for item in items}
    assert shown["Training"] == (18 * 60, 19 * 60, own_entries.STATE_CUT)
    assert shown["Evening"] == (19 * 60, 20 * 60 + 30, own_entries.STATE_OK)
    next_week = own_entries.resolve_day([series, once], [], day + timedelta(days=7), "sam")
    assert [(item["start"], item["end"]) for item in next_week] == [(18 * 60, 20 * 60)]


def test_series_without_the_holiday_tick_fall_silent_on_free_days():
    series = normalized(start="16:00", days=[2])
    ticked = normalized(name="Swim", start="18:00", days=[2], holidays=True)
    once = normalized(name="Doctor", start="17:10", repeat="once", date="2026-09-23", duration=30)
    names = [item["entry"]["name"] for item in own_entries.resolve_day([series, ticked, once], [], TODAY, "sam", free=True)]
    assert names == ["Doctor", "Swim"]


def test_an_entry_for_one_child_does_not_reach_the_other():
    entry = normalized(child="sam", start="16:00")
    assert own_entries.resolve_day([entry], [], TODAY, "mika") == []
    shared = normalized(child="", start="16:00")
    assert len(own_entries.resolve_day([shared], [], TODAY, "mika")) == 1


def test_a_start_inside_a_lesson_of_the_child_is_refused():
    conf = config()
    rows, profiles, children = context(conf)
    candidate = normalized(start="14:00", days=[1])
    with pytest.raises(OwnEntryError) as caught:
        own_entries.check_conflicts(candidate, [], rows, profiles, children)
    assert caught.value.message_key == own_entries.ERROR_LESSON
    assert caught.value.variables == {"number": 7}
    free = normalized(start="14:00", days=[2])
    own_entries.check_conflicts(free, [], rows, profiles, children)
    for_all = normalized(start="14:00", days=[2], child="")
    with pytest.raises(OwnEntryError):
        own_entries.check_conflicts(for_all, [], rows, profiles, children)


def test_a_pause_after_the_last_lesson_of_a_day_blocks_nothing_that_day():
    conf = config()
    rows, profiles, children = context(conf)
    lunch = normalized(type="pause", name="Lunch", start="13:15", duration=35, repeat="daily", child="")
    club = normalized(start="13:20", duration=20, days=[4])
    own_entries.check_conflicts(club, [lunch], rows, profiles, children)
    tuesday_club = normalized(start="13:20", duration=20, days=[1])
    with pytest.raises(OwnEntryError) as caught:
        own_entries.check_conflicts(tuesday_club, [lunch], rows, profiles, children)
    assert caught.value.message_key == own_entries.ERROR_TAKEN


def test_series_that_never_meet_on_a_date_do_not_collide():
    rows, profiles, children = context(config())
    autumn = normalized(start="16:00", until="2026-10-31")
    spring = normalized(name="Chess two", start="16:00", **{"from": "2026-11-01"})
    own_entries.check_conflicts(spring, [autumn], rows, profiles, children)
    even = normalized(repeat="weeks", interval=2, start="16:00", **{"from": "2026-09-23"})
    odd = normalized(name="Chess odd", repeat="weeks", interval=2, start="16:00", **{"from": "2026-09-30"})
    own_entries.check_conflicts(odd, [even], rows, profiles, children)
    with pytest.raises(OwnEntryError):
        own_entries.check_conflicts(normalized(name="Chess three", start="16:30"), [autumn], rows, profiles, children)


def test_the_summer_holidays_bound_every_series():
    periods = [{"type": "summer", "kind": "school", "start": "2026-07-02"}, {"type": "summer", "kind": "school", "start": "2027-07-01"}, {"type": "autumn", "kind": "school", "start": "2026-10-12"}]
    assert own_entries.until_limit(TODAY, periods) == (date(2027, 6, 30), date(2027, 7, 1))
    assert own_entries.until_limit(TODAY, []) == (date(2027, 7, 31), None)
    assert own_entries.until_limit(date(2027, 5, 2), []) == (date(2027, 7, 31), None)


def random_entry(rng, index):
    kind = rng.choice(own_entries.TYPES)
    repeat = rng.choice(own_entries.REPEATS)
    start = rng.randrange(6 * 60, 22 * 60, 5)
    fields = {
        "type": kind,
        "name": f"Entry {index}",
        "start": period_grid.clock_of(start),
        "duration": rng.choice([5, 10, 20, 30, 45, 60, 90, 120]),
        "repeat": repeat,
        "days": rng.sample(range(7), rng.randint(1, 3)),
        "interval": rng.randint(2, 4),
        "date": (TODAY + timedelta(days=rng.randint(0, 40))).isoformat(),
        "from": (TODAY - timedelta(days=rng.randint(0, 20))).isoformat(),
        "until": (TODAY + timedelta(days=rng.randint(10, 60))).isoformat(),
        "holidays": rng.random() < 0.5,
        "child": rng.choice(["", "sam", "mika"]),
    }
    return fields


def test_accepted_entries_never_overlap_lessons_or_each_other():
    rng = random.Random(289)
    for _ in range(25):
        conf = config()
        rows, profiles, children = context(conf)
        accepted = []
        for index in range(30):
            try:
                entry = own_entries.normalize(random_entry(rng, index), conf, TODAY, UNTIL)
            except OwnEntryError:
                continue
            entry["id"] = f"e{index}"
            try:
                own_entries.check_conflicts(entry, accepted, rows, profiles, children)
            except OwnEntryError:
                continue
            accepted.append(entry)
        for offset in range(0, 70):
            day = TODAY + timedelta(days=offset)
            for child in ("sam", "mika"):
                spans = spans_on(conf, child, day)
                items = [item for item in own_entries.resolve_day(accepted, spans, day, child) if item["state"] != own_entries.STATE_HIDDEN]
                for item in items:
                    assert item["start"] >= own_entries.start_of(item["entry"])
                    assert item["end"] <= own_entries.end_of(item["entry"]) <= period_grid.DAY_MINUTES
                    assert item["state"] == own_entries.STATE_OK or item["entry"]["repeat"] != "once" or spans
                    for block_start, block_end, _ in spans:
                        if own_entries.pause_counts(item["entry"], spans):
                            assert not own_entries.overlaps(item["start"], item["end"], block_start, block_end)
                counting = [item for item in items if own_entries.pause_counts(item["entry"], spans)]
                for first, second in ((a, b) for i, a in enumerate(counting) for b in counting[i + 1:]):
                    assert not own_entries.overlaps(first["start"], first["end"], second["start"], second["end"]), (day, first, second)


def test_clipping_never_grows_an_entry_or_touches_a_blocker():
    rng = random.Random(30)
    for _ in range(2000):
        start = rng.randrange(0, 1400)
        end = rng.randrange(start + 1, 1441)
        blockers = []
        for _ in range(rng.randint(0, 6)):
            left = rng.randrange(0, 1430)
            blockers.append((left, rng.randrange(left + 1, 1441), rng.randint(1, 10)))
        clipped_start, clipped_end, _ = own_entries.clip(start, end, blockers)
        if clipped_end <= clipped_start:
            continue
        assert start <= clipped_start < clipped_end <= end
        for left, right, _ in blockers:
            assert not own_entries.overlaps(clipped_start, clipped_end, left, right)


@pytest.fixture
def school(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, children=[dict(child) for child in CHILDREN], period_times=dict(TIMES), period_grid={"iserv": dict(ISERV), "days": PROFILE})
    return store, connection_id, ConnectionStore(store, connection_id)


def test_entries_are_stored_per_school_and_survive_a_lesson_change(school):
    store, connection_id, scoped = school
    created = own_entries.create(scoped, raw(type="pause", name="Room change", start="13:10", duration=5, repeat="daily", child=""), TODAY, UNTIL)
    assert store.connection(connection_id)["own_entries"][0]["id"] == created["id"]
    own_entries.set_lesson(scoped, 6, "12:25", 60)
    stored = store.connection(connection_id)
    assert stored["period_grid"]["lessons"] == {"6": {"duration": 60}}
    assert [entry["id"] for entry in stored["own_entries"]] == [created["id"]]
    shown = own_entries.view(scoped.load_config(), connection_id, TODAY, UNTIL)
    assert shown["entries"][0]["status"]["state"] == own_entries.STATE_HIDDEN
    assert shown["entries"][0]["status"]["number"] == 6
    own_entries.reset_lessons(scoped, [6])
    assert "lessons" not in store.connection(connection_id)["period_grid"]
    assert own_entries.view(scoped.load_config(), connection_id, TODAY, UNTIL)["entries"][0]["status"]["state"] == own_entries.STATE_OK


def test_a_lesson_edit_keeps_the_neighbours_apart(school):
    _, _, scoped = school
    with pytest.raises(OwnEntryError):
        own_entries.set_lesson(scoped, 2, "08:10", 45)
    with pytest.raises(OwnEntryError):
        own_entries.set_lesson(scoped, 2, "08:40", 70)
    with pytest.raises(OwnEntryError):
        own_entries.set_lesson(scoped, 12, "08:40", 45)


def test_added_lessons_follow_the_last_one_and_only_they_can_be_removed(school):
    store, connection_id, scoped = school
    assert own_entries.add_lesson(scoped, "15:30", 45) == 9
    with pytest.raises(OwnEntryError):
        own_entries.add_lesson(scoped, "15:40", 45)
    assert own_entries.add_lesson(scoped, "16:20", 45) == 10
    with pytest.raises(OwnEntryError):
        own_entries.remove_lesson(scoped, 3)
    own_entries.remove_lesson(scoped, 10)
    assert "10" not in store.connection(connection_id)["period_times"]
    rows = {row["number"]: row for row in period_grid.resolve(scoped.load_config())}
    assert rows[9]["added"] and rows[9]["start"] == 15 * 60 + 30


def test_editing_only_the_name_of_a_colliding_entry_is_allowed(school):
    store, connection_id, scoped = school
    created = own_entries.create(scoped, raw(start="15:30", days=[1]), TODAY, UNTIL)
    own_entries.set_lesson(scoped, 8, "14:40", 80)
    renamed = own_entries.update(scoped, created["id"], raw(start="15:30", days=[1], name="Chess"), TODAY, UNTIL)
    assert renamed["name"] == "Chess"
    with pytest.raises(OwnEntryError):
        own_entries.update(scoped, created["id"], raw(start="15:35", days=[1], name="Chess"), TODAY, UNTIL)
    own_entries.delete(scoped, created["id"])
    assert store.connection(connection_id)["own_entries"] == []
    with pytest.raises(OwnEntryError):
        own_entries.delete(scoped, created["id"])


class Holidays:
    def range_info(self, start, end, config=None):
        return {"status": "ok", "days": {}, "periods": [{"type": "summer", "kind": "school", "start": "2027-07-01"}]}


def test_the_api_saves_entries_and_answers_with_message_keys(tmp_path, monkeypatch):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, children=[dict(child) for child in CHILDREN], period_times=dict(TIMES), period_grid={"iserv": dict(ISERV), "days": PROFILE})
    monkeypatch.setattr("app.holidays.berlin_today", lambda moment=None: TODAY)
    client = TestClient(create_app(IServService(store), holiday_calendar=Holidays(), calendar_warmer=lambda child: None))
    base = f"/api/connections/{connection_id}"
    shown = client.get(f"{base}/periods").json()
    assert shown["until_max"] == "2027-06-30" and shown["summer_start"] == "2027-07-01"
    assert len(shown["grid"]) == 8 and shown["iserv_ends"] is True
    assert shown["profiles"]["sam"]["1"] == [1, 2, 3, 4, 5, 6, 7, 8]
    made = client.post(f"{base}/own-entries", json=raw())
    assert made.status_code == 200 and made.json()["message_key"] == "api.ownEntries.added"
    entry_id = made.json()["entry_id"]
    assert made.json()["entries"][0]["child_key"] == f"{connection_id}:sam"
    clash = client.post(f"{base}/own-entries", json=raw(name="Chess two", start="15:45"))
    assert clash.status_code == 400 and clash.json()["message_key"] == own_entries.ERROR_TAKEN
    late = client.post(f"{base}/own-entries", json=raw(until="2027-07-02"))
    assert late.status_code == 400 and late.json()["message_key"] == own_entries.ERROR_UNTIL
    saved = client.post(f"{base}/own-entries/{entry_id}", json=raw(name="Chess"))
    assert saved.json()["message_key"] == "api.ownEntries.saved"
    lesson = client.post(f"{base}/periods/lessons/6", json={"start": "12:25", "duration": 60})
    assert lesson.json()["message_key"] == "api.periods.saved"
    assert [row for row in lesson.json()["grid"] if row["number"] == 6][0]["own_duration"] is True
    added = client.post(f"{base}/periods/lessons", json={"start": "15:30", "duration": 45})
    assert added.json()["number"] == 9
    assert client.delete(f"{base}/periods/lessons/9").json()["message_key"] == "api.periods.removed"
    assert client.post(f"{base}/periods/reset").json()["message_key"] == "api.periods.resetAll"
    assert client.delete(f"{base}/own-entries/{entry_id}").json()["entries"] == []
    assert client.delete(f"{base}/own-entries/{entry_id}").status_code == 404
    assert client.get("/api/connections/nope/periods").status_code == 404
    refused = client.post(f"{base}", json={"own_entries": []})
    assert refused.status_code == 400


def test_a_start_saved_before_iserv_was_known_stays_when_iserv_arrives(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, children=[dict(child) for child in CHILDREN], period_times={"1": "07:50", "2": "08:40", "3": "09:45"})
    scoped = ConnectionStore(store, connection_id)
    rows = {row["number"]: row for row in period_grid.resolve(scoped.load_config())}
    assert not rows[3]["added"] and rows[3]["source"] == period_grid.SOURCE_SAVED
    own_entries.set_lesson(scoped, 3, "09:50", 45)
    with pytest.raises(OwnEntryError):
        own_entries.remove_lesson(scoped, 3)
    merged = period_grid.merge_iserv(scoped.load_config(), {"3": {"start": "09:40", "end": "10:25"}})
    assert merged["period_times"]["3"] == "09:50"
    assert {row["number"]: row for row in period_grid.resolve(merged)}[3]["own_start"]


def test_an_entry_past_a_moved_limit_can_still_be_renamed_but_not_moved_further():
    earlier = date(2027, 6, 15)
    stored = normalized(until="2027-06-30")
    renamed = own_entries.normalize(raw(name="Chess", until="2027-06-30"), config(), TODAY, earlier, existing=stored)
    assert renamed["until"] == "2027-06-30"
    with pytest.raises(OwnEntryError):
        own_entries.normalize(raw(until="2027-06-29"), config(), TODAY, earlier, existing=stored)
    once = normalized(repeat="once", date="2027-06-25")
    assert own_entries.normalize(raw(repeat="once", date="2027-06-25", name="Chess"), config(), TODAY, earlier, existing=once)["date"] == "2027-06-25"


def test_a_series_without_a_single_date_is_refused():
    with pytest.raises(OwnEntryError) as caught:
        own_entries.normalize(raw(days=[6], **{"from": "2026-09-21", "until": "2026-09-25"}), config(), TODAY, UNTIL)
    assert caught.value.message_key == own_entries.ERROR_EMPTY



SUMMERS = [
    {"type": "summer", "kind": "school", "start": "2027-07-01", "end": "2027-08-11"},
    {"type": "summer", "kind": "school", "start": "2028-07-06", "end": "2028-08-16"},
]


def series(entry_id, **fields):
    entry = own_entries.normalize(raw(**fields), config(), TODAY, date(2029, 7, 31))
    entry["id"] = entry_id
    return entry


@pytest.mark.parametrize(
    "today, offered",
    [
        (date(2027, 6, 1), False),
        (date(2027, 6, 2), True),
        (date(2027, 6, 30), True),
        (date(2027, 7, 20), True),
        (date(2027, 8, 12), False),
    ],
)
def test_the_rollover_is_offered_from_four_weeks_before_the_end_until_school_starts(today, offered):
    plan = own_entries.rollover_plan([series("s1", until="2027-06-30")], today, SUMMERS)
    assert (plan is not None) == offered
    if offered:
        assert plan["ids"] == ["s1"]
        assert (plan["until"], plan["year_end"], plan["from"], plan["to"]) == (date(2027, 6, 30), date(2027, 6, 30), date(2027, 8, 12), date(2028, 7, 5))


def test_only_series_that_run_in_the_school_year_and_end_with_it_are_carried_over():
    entries = [
        series("s1", until="2027-06-30"),
        series("s2", until="2027-05-31", start="17:00"),
        series("o1", repeat="once", date="2027-06-15", start="18:00"),
        series("s3", until="2027-07-31", start="19:00"),
        series("c1", start="20:00", **{"from": "2027-07-05", "until": "2027-07-20"}),
    ]
    plan = own_entries.rollover_plan(entries, date(2027, 6, 10), SUMMERS)
    assert plan["ids"] == ["s1", "s3"]
    assert plan["until"] == date(2027, 6, 30)


def test_without_summer_holidays_the_school_year_ends_on_the_last_of_july():
    plan = own_entries.rollover_plan([series("s1", until="2027-07-31")], date(2027, 7, 10), [])
    assert (plan["year_end"], plan["from"], plan["to"]) == (date(2027, 7, 31), date(2027, 8, 2), date(2028, 7, 31))
    assert own_entries.rollover_plan([series("s1", until="2027-07-31")], date(2027, 6, 1), []) is None


def test_the_new_end_comes_from_the_holidays_after_the_summer():
    near = [SUMMERS[0]]
    later = lambda first: [dict(SUMMERS[1], start="2028-07-13", end="2028-08-23")] if first == date(2027, 8, 12) else []
    plan = own_entries.rollover_plan([series("s1", until="2027-06-30")], date(2027, 6, 2), near, later)
    assert plan["to"] == date(2028, 7, 12)


def test_the_rollover_copies_the_series_into_the_new_year_and_marks_one_that_would_overlap(school):
    store, connection_id, scoped = school
    config = scoped.load_config()
    config["own_entries"] = [
        series("s1", until="2027-06-30"),
        series("s2", until="2027-06-30", start="17:00", child="mika"),
        series("n1", start="17:30", child="mika", **{"from": "2027-08-16", "until": "2028-07-05"}),
        series("l1", start="09:00", days=[1], until="2027-06-30"),
    ]
    scoped.save_config(config)
    before = {entry["id"]: dict(entry) for entry in config["own_entries"]}
    outcome = own_entries.rollover(scoped, date(2027, 6, 10), SUMMERS, clock=lambda: 1000)
    assert outcome == {"copied": 2, "skipped": 1}
    entries = store.connection(connection_id)["own_entries"]
    stored = {entry["id"]: entry for entry in entries}
    assert [entry["id"] for entry in entries[:4]] == ["s1", "s2", "n1", "l1"]
    assert len(entries) == 6
    for original in ("s1", "l1"):
        assert stored[original] == dict(before[original], rollover_copied="2027-06-30")
    copies = entries[4:]
    for copy, original in zip(copies, ("s1", "l1")):
        assert copy["id"] not in before and len(copy["id"]) == 12
        assert (copy["from"], copy["until"], copy["created_at"], copy["updated_at"]) == ("2027-08-12", "2028-07-05", 1000, 1000)
        timing = {key: value for key, value in before[original].items() if key not in ("id", "from", "until", "created_at", "updated_at")}
        assert {key: copy[key] for key in timing} == timing
        assert own_entries.ROLLOVER_COPIED not in copy and own_entries.ROLLOVER_SKIPPED not in copy
    assert stored["s2"] == dict(before["s2"], rollover_skipped="2027-06-30")
    assert stored["n1"] == before["n1"]
    assert own_entries.rollover_plan(entries, date(2027, 6, 10), SUMMERS) is None
    with pytest.raises(OwnEntryError) as caught:
        own_entries.rollover(scoped, date(2027, 6, 10), SUMMERS)
    assert caught.value.message_key == own_entries.ERROR_ROLLOVER
    renamed = own_entries.update(scoped, "s2", dict(stored["s2"], name="Choir two"), TODAY, date(2027, 6, 30))
    assert own_entries.ROLLOVER_SKIPPED not in renamed
    kept = own_entries.update(scoped, "s1", dict(stored["s1"], name="Chess club two"), TODAY, date(2027, 6, 30))
    assert kept[own_entries.ROLLOVER_COPIED] == "2027-06-30"
    assert own_entries.rollover_plan(entries_after(scoped), date(2027, 6, 10), SUMMERS)["ids"] == ["s2"]


def test_a_copy_in_the_next_school_year_stays_editable_within_that_year_only(school):
    _, _, scoped = school
    config = scoped.load_config()
    config["own_entries"] = [series("s1", until="2027-06-30")]
    scoped.save_config(config)
    own_entries.rollover(scoped, date(2027, 6, 10), SUMMERS)
    copy = entries_after(scoped)[1]
    now, until_max = date(2027, 6, 10), date(2027, 6, 30)
    later_limit = lambda first: own_entries.until_limit(first, SUMMERS)[0]
    shown = own_entries.view(scoped.load_config(), "c1", now, until_max, None, SUMMERS)["entries"]
    assert [(entry["from_min"], entry["until_max"]) for entry in shown] == [("", ""), ("2027-07-01", "2028-07-05")]
    shorter = own_entries.update(scoped, copy["id"], dict(copy, until="2028-03-01", name="Chess"), now, until_max, later_limit=later_limit)
    assert (shorter["from"], shorter["until"], shorter["name"]) == ("2027-08-12", "2028-03-01", "Chess")
    later = own_entries.update(scoped, copy["id"], dict(shorter, until="2028-07-05", **{"from": "2027-09-01"}), now, until_max, later_limit=later_limit)
    assert (later["from"], later["until"]) == ("2027-09-01", "2028-07-05")
    for fields in ({"from": "2027-06-28"}, {"until": "2028-07-06"}):
        with pytest.raises(OwnEntryError) as caught:
            own_entries.update(scoped, copy["id"], dict(later, **fields), now, until_max, later_limit=later_limit)
        assert caught.value.message_key == own_entries.ERROR_UNTIL
    with pytest.raises(OwnEntryError) as caught:
        own_entries.update(scoped, copy["id"], dict(later, **{"from": "2027-06-28"}), now, until_max)
    assert caught.value.message_key == own_entries.ERROR_UNTIL
    assert entries_after(scoped)[1]["from"] == "2027-09-01"


def test_a_series_whose_stored_end_lies_past_a_shrunken_limit_keeps_it_when_only_the_start_moves(school):
    _, _, scoped = school
    config = scoped.load_config()
    config["own_entries"] = [series("s1", until="2027-06-30")]
    config["own_entries"][0]["until"] = "2027-07-31"
    scoped.save_config(config)
    later_limit = lambda first: own_entries.until_limit(first, SUMMERS)[0]
    stored = entries_after(scoped)[0]
    moved = own_entries.update(scoped, "s1", dict(stored, **{"from": "2026-10-01"}), TODAY, UNTIL, later_limit=later_limit)
    assert (moved["from"], moved["until"]) == ("2026-10-01", "2027-07-31")
    with pytest.raises(OwnEntryError) as caught:
        own_entries.update(scoped, "s1", dict(moved, until="2027-07-30"), TODAY, UNTIL, later_limit=later_limit)
    assert caught.value.message_key == own_entries.ERROR_UNTIL


def test_a_series_starts_in_the_next_school_year_at_the_latest(school):
    _, _, scoped = school
    later_limit = lambda first: own_entries.until_limit(first, SUMMERS)[0]
    for start, until in (("2028-07-06", "2028-07-20"), ("2099-03-04", "2099-03-10")):
        with pytest.raises(OwnEntryError) as caught:
            own_entries.create(scoped, raw(**{"from": start, "until": until}), TODAY, UNTIL, later_limit=later_limit)
        assert caught.value.message_key == own_entries.ERROR_FROM
    created = own_entries.create(scoped, raw(**{"from": "2028-07-05", "until": "2028-07-05"}), TODAY, UNTIL, later_limit=later_limit)
    assert (created["from"], created["until"]) == ("2028-07-05", "2028-07-05")
    assert entries_after(scoped) == [created]


def test_a_series_already_carried_over_is_not_offered_again_when_the_year_end_moves():
    copied = dict(series("s1", until="2027-06-30"), rollover_copied="2027-07-31")
    assert own_entries.rollover_plan([copied], date(2027, 6, 10), SUMMERS) is None
    stale = dict(series("s1", until="2027-06-30"), rollover_copied="2026-07-31")
    assert own_entries.rollover_plan([stale], date(2027, 6, 10), SUMMERS)["ids"] == ["s1"]


def test_a_series_the_old_rollover_had_extended_is_not_offered_again():
    extended = dict(series("s1", until="2027-06-30"), until="2028-07-05")
    assert own_entries.rollover_plan([extended], date(2027, 6, 10), SUMMERS) is None


def test_a_rollover_that_would_overfill_the_list_changes_nothing(school):
    _, _, scoped = school
    config = scoped.load_config()
    config["own_entries"] = [series("s1", until="2027-06-30")] + [series(f"o{index}", repeat="once", date="2027-06-15", start="18:00") for index in range(own_entries.MAX_ENTRIES - 1)]
    scoped.save_config(config)
    with pytest.raises(OwnEntryError) as caught:
        own_entries.rollover(scoped, date(2027, 6, 10), SUMMERS)
    assert caught.value.message_key == own_entries.ERROR_FULL
    assert entries_after(scoped) == config["own_entries"]


def entries_after(scoped):
    return own_entries.entries_of(scoped.load_config())


def test_a_rollover_that_can_extend_nothing_says_why(school):
    _, _, scoped = school
    config = scoped.load_config()
    config["own_entries"] = [
        series("s2", until="2027-06-30", start="17:00", child="mika"),
        series("n1", start="17:30", child="mika", **{"from": "2027-08-16", "until": "2028-07-05"}),
    ]
    scoped.save_config(config)
    with pytest.raises(OwnEntryError) as caught:
        own_entries.rollover(scoped, date(2027, 6, 10), SUMMERS)
    assert caught.value.message_key == own_entries.ERROR_ROLLOVER_TAKEN
    assert own_entries.rollover_plan(entries_after(scoped), date(2027, 6, 10), SUMMERS) is None


def test_a_rollover_without_series_to_move_is_refused(school):
    _, _, scoped = school
    with pytest.raises(OwnEntryError) as caught:
        own_entries.rollover(scoped, date(2027, 6, 10), SUMMERS)
    assert caught.value.message_key == own_entries.ERROR_ROLLOVER


def test_a_rollover_leaves_every_old_date_alone_and_copies_the_rhythm_into_the_next_school_year_only(school):
    _, _, scoped = school
    rng = random.Random(31)
    checked = 0
    for _ in range(60):
        entries = [series(f"s{index}", start=period_grid.clock_of(rng.randrange(16 * 60, 21 * 60, 5)), duration=5, repeat=rng.choice(["daily", "weekly", "weeks"]), days=sorted(rng.sample(range(7), rng.randint(1, 3))), interval=rng.randint(2, 4), until=rng.choice(["2027-06-30", "2027-05-01", "2027-07-15"])) for index in range(rng.randint(1, 5))]
        today = date(2027, 6, 2) + timedelta(days=rng.randint(0, 70))
        plan = own_entries.rollover_plan(entries, today, SUMMERS)
        if plan is None:
            continue
        config = scoped.load_config()
        config["own_entries"] = entries
        scoped.save_config(config)
        try:
            own_entries.rollover(scoped, today, SUMMERS)
        except OwnEntryError as error:
            assert error.message_key == own_entries.ERROR_ROLLOVER_TAKEN
        after = entries_after(scoped)
        originals = {entry["id"]: entry for entry in entries}
        copies = [entry for entry in after if entry["id"] not in originals]
        for entry in after:
            if entry["id"] in originals:
                assert own_entries.occurrence_days(entry) == own_entries.occurrence_days(originals[entry["id"]])
        copied = [entry for entry in after if entry.get(own_entries.ROLLOVER_COPIED)]
        skipped = [entry for entry in after if entry.get(own_entries.ROLLOVER_SKIPPED)]
        assert len(copies) == len(copied)
        assert sorted(entry["id"] for entry in copied + skipped) == sorted(plan["ids"])
        for copy, source in zip(copies, copied):
            days = own_entries.occurrence_days(copy)
            assert days and min(days) >= date(2027, 8, 12) and max(days) < date(2028, 7, 6)
            assert {day.weekday() for day in days} == set(source["days"])
            assert (copy["start"], copy["duration"], copy["repeat"], copy["child"]) == (source["start"], source["duration"], source["repeat"], source["child"])
        checked += 1
    assert checked > 10


class SummerHolidays:
    def range_info(self, start, end, config=None):
        return {"status": "ok", "days": {}, "periods": list(SUMMERS)}


def test_the_api_offers_and_performs_the_rollover(tmp_path, monkeypatch):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, children=[dict(child) for child in CHILDREN], period_times=dict(TIMES), period_grid={"iserv": dict(ISERV), "days": PROFILE}, own_entries=[series("s1", until="2027-06-30")])
    today = {"value": date(2027, 5, 20)}
    monkeypatch.setattr("app.holidays.berlin_today", lambda moment=None: today["value"])
    client = TestClient(create_app(IServService(store), holiday_calendar=SummerHolidays(), calendar_warmer=lambda child: None))
    base = f"/api/connections/{connection_id}"
    assert client.get(f"{base}/periods").json()["rollover"] is None
    early = client.post(f"{base}/own-entries/rollover")
    assert early.status_code == 400 and early.json()["message_key"] == own_entries.ERROR_ROLLOVER
    today["value"] = date(2027, 6, 10)
    assert client.get(f"{base}/periods").json()["rollover"] == {"count": 1, "until": "2027-06-30", "from": "2027-08-12", "to": "2028-07-05"}
    done = client.post(f"{base}/own-entries/rollover")
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["message_key"] == "api.ownEntries.rolledOver" and body["message_vars"] == {"count": 1, "skipped": 0}
    assert body["rollover"] is None
    assert [(entry["name"], entry["from"], entry["until"]) for entry in body["entries"]] == [("Chess club", "2026-09-01", "2027-06-30"), ("Chess club", "2027-08-12", "2028-07-05")]
    assert client.post(f"{base}/own-entries/rollover").status_code == 400
    assert client.post("/api/connections/nope/own-entries/rollover").status_code == 404
