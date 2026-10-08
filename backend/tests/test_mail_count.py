import logging

import pytest

from app import integration
from app.iserv.errors import DataError, OutageError
from app.poller import Poller
from app.store import Store
from tests.support import add_school, connection_service
from tests.test_school_events import Answer, CalendarClient

MAIL_ENTRY = {"segment": "mail", "slug": "mail", "label": "E-Mail"}


class MailConnection:
    def __init__(self, connection_id, counts=None, failure=None, available=True):
        self.id = connection_id
        self.counts = counts if counts is not None else {}
        self.failure = failure
        self.available = available
        self.asked = 0

    def mail_available(self):
        return self.available

    def badges(self):
        self.asked += 1
        if self.failure is not None:
            raise self.failure
        return dict(self.counts)


def poller_for(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example")
    poller = Poller(None, store=store)
    return poller, store, connection_id


def test_the_poll_keeps_the_unread_mail_count_of_the_school(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    poller._poll_mail(MailConnection(connection_id, {"mail": 3, "exercise": 1}), connection_id)
    assert integration.school_mail(store, connection_id) == 3


def test_a_mail_badge_that_is_not_shown_means_no_unread_mail(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    poller._poll_mail(MailConnection(connection_id, {}), connection_id)
    assert integration.school_mail(store, connection_id) == 0


def test_an_unreadable_count_keeps_the_last_one_and_does_not_fail_the_poll(tmp_path, caplog):
    poller, store, connection_id = poller_for(tmp_path)
    poller._poll_mail(MailConnection(connection_id, {"mail": 2}), connection_id)
    with caplog.at_level(logging.WARNING):
        result = poller._poll_mail(MailConnection(connection_id, failure=RuntimeError("broken")), connection_id)
    assert result is None
    assert integration.school_mail(store, connection_id) == 2
    assert any("mail count unreadable" in record.getMessage() for record in caplog.records)


def test_an_outage_still_stops_the_poll(tmp_path):
    poller, _, connection_id = poller_for(tmp_path)
    with pytest.raises(OutageError):
        poller._poll_mail(MailConnection(connection_id, failure=OutageError("down")), connection_id)


def test_a_school_without_mail_is_not_asked_and_has_no_count(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    poller._poll_mail(MailConnection(connection_id, {"mail": 5}), connection_id)
    connection = MailConnection(connection_id, {"mail": 5}, available=False)
    poller._poll_mail(connection, connection_id)
    assert connection.asked == 0
    assert integration.school_mail(store, connection_id) is None


def mail_service(tmp_path, answer, with_mail=True):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example")
    client = CalendarClient("https://school.example", answer)
    service = connection_service(store, connection_id, lambda url: client)
    if with_mail:
        service.store.save_modules({"unsupported": [MAIL_ENTRY]})
    return service, client, store, connection_id


def test_the_badges_are_read_from_the_navigation(tmp_path):
    service, client, _, _ = mail_service(tmp_path, Answer(200, {"mail": 7}))
    assert service.badges() == {"mail": 7}
    assert client.asked[-1] == ("/iserv/app/navigation/badges", None)
    assert service.mail_available() is True


@pytest.mark.parametrize("answer", [Answer(403, None), Answer(200, ValueError("no json")), Answer(200, "text")])
def test_unreadable_badges_are_an_error_and_not_zero(tmp_path, answer):
    service, _, _, _ = mail_service(tmp_path, answer)
    with pytest.raises(DataError):
        service.badges()


def test_mail_is_only_available_when_the_menu_lists_it(tmp_path):
    service, _, _, _ = mail_service(tmp_path, Answer(200, {}), with_mail=False)
    assert service.mail_available() is False


def test_the_app_gets_the_stored_count_and_a_link_per_school_with_mail(tmp_path):
    from tests.test_connections import two_schools

    service, store, one, two, _ = two_schools(tmp_path)
    store.connection_store(one).save_modules({"unsupported": [MAIL_ENTRY]})
    integration.record_school_mail(store, one, 3)
    body = service.mail_counts()
    assert [(entry["connection_id"], entry["unread"]) for entry in body["schools"]] == [(one, 3)]
    assert body["schools"][0]["open_url"].endswith("/iserv/mail")
    assert body["schools"][0]["school"] == "School One"


def test_a_refused_count_is_logged_quietly(tmp_path, caplog):
    poller, store, connection_id = poller_for(tmp_path)
    with caplog.at_level(logging.INFO):
        poller._poll_mail(MailConnection(connection_id, failure=DataError("request failed: 404")), connection_id)
    lines = [record for record in caplog.records if "mail count unreadable" in record.getMessage()]
    assert [record.levelno for record in lines] == [logging.INFO]


def test_a_mail_count_that_cannot_be_read_is_unknown_and_not_zero(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    poller._poll_mail(MailConnection(connection_id, {"mail": 4}), connection_id)
    poller._poll_mail(MailConnection(connection_id, {"mail": None}), connection_id)
    assert integration.school_mail(store, connection_id) is None


def test_a_count_that_keeps_failing_is_dropped_after_a_few_polls(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    poller._poll_mail(MailConnection(connection_id, {"mail": 4}), connection_id)
    failing = MailConnection(connection_id, failure=DataError("request failed: 500"))
    for _ in range(integration.MAIL_FAILURE_LIMIT - 1):
        poller._poll_mail(failing, connection_id)
    assert integration.school_mail(store, connection_id) == 4
    poller._poll_mail(failing, connection_id)
    assert integration.school_mail(store, connection_id) is None
    poller._poll_mail(MailConnection(connection_id, {"mail": 1}), connection_id)
    assert integration.school_mail(store, connection_id) == 1
