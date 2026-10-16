import pytest
import requests

from app.iserv.absences import LEAVE_PATH
from app.upstream import write_endpoint
from tests.test_service import FakeAbsenceDsa, with_absences

SICK = {"type": "sick", "student_id": 7, "day_from": "today", "day_till": "today", "comment": "x"}
LEAVE = {"type": "leave", "student_id": 7, "from_date": "2126-09-10", "till_date": "2126-09-11", "subject": "Arzt", "body": "Termin"}


class Answer:
    def __init__(self, status):
        self.status_code = status

    def json(self):
        return {}


class SchoolApp(FakeAbsenceDsa):
    def __init__(self, outcome=201, lands=True):
        super().__init__()
        self.outcome = outcome
        self.lands = lands
        self.sends = 0

    def send_request(self, request):
        self.sends += 1
        self.sent = request
        if self.lands:
            self.land(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return Answer(self.outcome)

    def land(self, request):
        data = request.payload
        if request.path == "sickNotes/":
            self._notes.append({"id": self.sends, "sickUser": data["sickUser"], "sickFromDate": data["sickFromDate"], "sickTillDate": data["sickTillDate"]})
            return
        self._requests.setdefault(LEAVE_PATH, []).append(
            {"id": self.sends, "student": data["student"]["id"], "absentFrom": data["absentFrom"], "absentUntil": data["absentUntil"]}
        )


def report(service, payload, **extra):
    return write_endpoint(lambda: service.report_absence(dict(payload, **extra)))


@pytest.mark.parametrize("outcome", [requests.ReadTimeout("late"), requests.ConnectionError("reset by peer"), 502, 504, 500])
def test_an_answer_lost_after_sending_is_checked_in_the_list_and_counts_as_sent_when_listed(tmp_path, outcome):
    dsa = SchoolApp(outcome)
    service, _ = with_absences(tmp_path, dsa)
    result = report(service, SICK)
    assert result["ok"] is True
    assert result["message_key"] == "api.absence.sent.sick"
    assert dsa.sends == 1


@pytest.mark.parametrize("outcome", [requests.ReadTimeout("late"), 502, 504])
def test_an_answer_lost_after_sending_without_a_listed_report_is_unclear_never_failed(tmp_path, outcome):
    dsa = SchoolApp(outcome, lands=False)
    service, _ = with_absences(tmp_path, dsa)
    result = report(service, SICK)
    assert result["ok"] is False
    assert result.get("uncertain") is True
    assert result["message_key"] == "api.absence.sendUnclear"


def test_the_same_request_again_after_an_unclear_answer_is_not_sent_twice(tmp_path):
    dsa = SchoolApp(requests.ReadTimeout("late"), lands=False)
    service, _ = with_absences(tmp_path, dsa)
    assert report(service, SICK, request_id="r1")["uncertain"] is True
    dsa.land(dsa.sent)
    again = report(service, SICK, request_id="r1")
    assert again["ok"] is True
    assert dsa.sends == 1


def test_a_new_report_for_the_same_days_after_an_unclear_answer_asks_before_sending(tmp_path):
    dsa = SchoolApp(requests.ReadTimeout("late"), lands=False)
    service, _ = with_absences(tmp_path, dsa)
    report(service, SICK, request_id="r1")
    held = report(service, SICK, request_id="r2")
    assert held["already_sent"] is True
    assert held["message_key"] == "api.absence.older.alreadySent"
    assert dsa.sends == 1
    dsa.outcome = 201
    sent = report(service, SICK, request_id="r3", send_again=True)
    assert sent["ok"] is True
    assert dsa.sends == 2


def test_a_report_the_school_already_lists_asks_before_sending_again(tmp_path):
    dsa = SchoolApp(201)
    service, _ = with_absences(tmp_path, dsa)
    assert report(service, LEAVE, request_id="r1")["ok"] is True
    other = with_absences(tmp_path / "other", dsa)[0]
    held = report(other, LEAVE, request_id="r2")
    assert held["already_sent"] is True
    assert dsa.sends == 1
    assert report(other, LEAVE, request_id="r3", send_again=True)["ok"] is True
    assert dsa.sends == 2


def test_a_leave_request_whose_answer_was_lost_is_found_by_profile_and_days(tmp_path):
    dsa = SchoolApp(requests.ReadTimeout("late"))
    service, _ = with_absences(tmp_path, dsa)
    assert report(service, LEAVE)["ok"] is True


def test_a_report_that_never_left_stays_a_network_error_and_can_be_sent_again(tmp_path):
    dsa = SchoolApp(requests.ConnectionError("Connection refused"), lands=False)
    service, _ = with_absences(tmp_path, dsa)
    assert report(service, SICK, request_id="r1")["message_key"] == "api.network"
    dsa.outcome = 201
    assert report(service, SICK, request_id="r1")["ok"] is True
    assert dsa.sends == 2


def test_a_refused_report_can_be_corrected_and_sent_again(tmp_path):
    dsa = SchoolApp(422, lands=False)
    service, _ = with_absences(tmp_path, dsa)
    assert report(service, SICK, request_id="r1")["ok"] is False
    dsa.outcome = 201
    assert report(service, SICK, request_id="r1")["ok"] is True
    assert dsa.sends == 2


def test_an_unreadable_list_does_not_block_sending_but_keeps_a_lost_answer_unclear(tmp_path):
    class Unlisted(SchoolApp):
        def sick_notes_or_raise(self, since=None):
            raise requests.ReadTimeout("list late")

    dsa = Unlisted(201)
    service, _ = with_absences(tmp_path, dsa)
    assert report(service, SICK)["ok"] is True
    lost = Unlisted(requests.ReadTimeout("late"))
    service, _ = with_absences(tmp_path / "lost", lost)
    assert report(service, SICK)["uncertain"] is True


class Withdrawing(FakeAbsenceDsa):
    def __init__(self, outcome, removes=True, list_fails_after=False):
        super().__init__()
        self._requests[LEAVE_PATH] = [{"id": 42, "student": 7, "absentFrom": 4000000000, "absentUntil": 4000000000}]
        self.outcome = outcome
        self.removes = removes
        self.list_fails_after = list_fails_after
        self.deletes = 0

    def user_requests_or_raise(self, path, student_id=None):
        if self.deletes and self.list_fails_after:
            raise requests.ReadTimeout("list late")
        return super().user_requests_or_raise(path, student_id)

    def delete_entry(self, path):
        self.deletes += 1
        if self.removes:
            self._requests[LEAVE_PATH] = []
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return Answer(self.outcome)


def withdraw(service):
    return write_endpoint(lambda: service.delete_absence({"type": "leave", "id": 42}))


@pytest.mark.parametrize("outcome", [requests.ReadTimeout("late"), 502, 504])
def test_a_withdrawal_whose_answer_was_lost_counts_as_done_when_the_entry_is_gone(tmp_path, outcome):
    service, _ = with_absences(tmp_path, Withdrawing(outcome))
    result = withdraw(service)
    assert result["ok"] is True
    assert result["message_key"] == "api.absence.withdrawn"


def test_a_withdrawal_whose_answer_was_lost_and_the_entry_stays_listed_says_so(tmp_path):
    service, _ = with_absences(tmp_path, Withdrawing(requests.ReadTimeout("late"), removes=False))
    result = withdraw(service)
    assert result["ok"] is False
    assert result["message_key"] == "api.absence.older.withdrawUncertain"


def test_a_withdrawal_whose_answer_and_list_were_lost_is_unclear_never_failed(tmp_path):
    service, _ = with_absences(tmp_path, Withdrawing(requests.ReadTimeout("late"), list_fails_after=True))
    result = withdraw(service)
    assert result["ok"] is False
    assert result.get("uncertain") is True
    assert result["message_key"] == "api.absence.withdrawUnclear"


def test_a_withdrawal_that_never_left_stays_a_network_error(tmp_path):
    service, _ = with_absences(tmp_path, Withdrawing(requests.ConnectionError("Connection refused"), removes=False))
    assert withdraw(service)["message_key"] == "api.network"
