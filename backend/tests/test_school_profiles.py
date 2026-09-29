import logging
from collections import Counter
from datetime import date

import pytest

from app import diagnostics
from app.iserv.errors import DataError
from app.poller import Poller
from app.service import IServService
from app.store import Store
from tests.school_profiles import PROFILES
from tests.support import add_school
from tests.time_table_school import FORBIDDEN, LESSONS, client_factory

WEDNESDAY = date(2026, 9, 9)
CHILD = "500001"
NOW_EPOCH = 1_788_969_600.0
PERSONAL = ("Kim", "Muster", "Parent Example", "Kai Klein", "school.example")


def school_of(tmp_path, profile, school=None):
    store = Store(tmp_path / "data")
    children = [dict(child) for child in profile.stored_children]
    connection_id = add_school(store, "https://school.example", children=children)
    service = IServService(store, client_factory=client_factory(school or profile.school()))
    return store, service, service.connection(connection_id)


@pytest.fixture(params=sorted(PROFILES), ids=sorted(PROFILES))
def profile(request):
    return PROFILES[request.param]


def test_a_poll_of_every_school_profile_runs_without_a_warning(tmp_path, profile, caplog):
    store, service, _ = school_of(tmp_path, profile)
    with caplog.at_level(logging.WARNING):
        Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
    assert [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING] == [], profile.story


def test_every_school_profile_reads_its_timetable_from_the_right_source(tmp_path, profile):
    _, _, connection = school_of(tmp_path, profile)
    connection.refresh_modules()
    if profile.source is None:
        with pytest.raises(DataError):
            connection.timetable(CHILD, reference=WEDNESDAY)
        return
    week = connection.timetable(CHILD, reference=WEDNESDAY)
    assert week["source"] == profile.source, profile.story
    slots = Counter((lesson["day_of_week"], lesson["period"]) for lesson in week["lessons"])
    assert max(slots.values(), default=1) == profile.most_parallel, profile.story
    assert any(lesson["change_kind"] for lesson in week["lessons"]) is profile.changed_lessons, profile.story
    if not week["lessons"]:
        assert week["no_lessons"] is True


def test_every_school_profile_lists_its_children_or_says_it_may_not(tmp_path, profile):
    _, _, connection = school_of(tmp_path, profile)
    if profile.children_listed:
        assert [child["child_id"] for child in connection.children()] == [CHILD], profile.story
        return
    with pytest.raises(DataError) as refused:
        connection.children()
    assert refused.value.message_key == "api.children.forbidden"


def test_every_school_profile_names_its_modules_as_the_school_offers_them(tmp_path, profile):
    _, _, connection = school_of(tmp_path, profile)
    registry = connection.refresh_modules()
    assert registry["modules"]["timetable"] is profile.timetable_module, profile.story
    assert [entry["slug"] for entry in registry["covered"]] == list(profile.covered), profile.story
    assert [entry["slug"] for entry in registry["unsupported"]] == list(profile.unsupported), profile.story
    assert [entry["segment"] for entry in registry["unknown"]] == list(profile.unknown), profile.story


def test_the_report_of_every_school_profile_is_honest_and_anonymous(tmp_path, profile):
    store, service, _ = school_of(tmp_path, profile)
    Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
    report = diagnostics.build_report(service, versions={"app": "x", "home_assistant": "y"})
    text = report if isinstance(report, str) else report[0]
    assert "- Timetable source: %s" % profile.report_source in text.splitlines(), profile.story
    if profile.substitution_line:
        assert profile.substitution_line in text.splitlines(), profile.story
    for slug in profile.covered:
        assert "| %s | obsolete | present, covered by the school app |" % slug in text
    for slug in profile.unsupported:
        assert "| %s | current | present, not supported |" % slug in text
    assert [word for word in PERSONAL if word in text] == [], profile.story


def test_a_stored_child_whose_school_refuses_the_timetable_is_polled_quietly(tmp_path, caplog):
    profile = PROFILES["second_school_with_a_stored_child"]
    school = profile.school()
    store, service, _ = school_of(tmp_path, profile, school)
    poller = Poller(service, store=store, clock=lambda: NOW_EPOCH)
    with caplog.at_level(logging.INFO):
        first = poller.poll_once()
        second = poller.poll_once()
    assert not [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING]
    refused = [entry for entry in first + second if entry.get("module") == "timetable"]
    assert [entry["state"] for entry in refused] == ["refused", "refused"]
    assert not [entry for entry in first + second if entry.get("error")]
    lines = [record.getMessage() for record in caplog.records if "no timetable released" in record.getMessage()]
    assert len(lines) == 1
    assert len(school.paths("/iserv/time-table/data")) == 1
    assert [line for line in (record.getMessage() for record in caplog.records) if "poll end" in line and " 0 errors" in line]


def test_a_single_refusal_after_a_delivered_week_is_a_poll_error_and_the_next_poll_reads_again(tmp_path):
    profile = PROFILES["time_table_with_changes"]
    school = profile.school()
    store, service, _ = school_of(tmp_path, profile, school)
    poller = Poller(service, store=store, clock=lambda: NOW_EPOCH)
    first = poller.poll_once()
    assert not [entry for entry in first if entry.get("error") or entry.get("state") == "refused"]
    school.time_table = FORBIDDEN
    second = poller.poll_once()
    assert not [entry for entry in second if entry.get("state") == "refused"]
    assert [entry for entry in second if entry.get("error")]
    school.time_table = LESSONS
    reads = len(school.paths("/iserv/time-table/data"))
    third = poller.poll_once()
    assert not [entry for entry in third if entry.get("error") or entry.get("state") == "refused"]
    assert len(school.paths("/iserv/time-table/data")) > reads
